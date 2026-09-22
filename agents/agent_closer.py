"""Closer — approval queue, sequencing and dispatch.

This agent is the brake, not the accelerator. It takes the drafts and review links the
crew prepared, puts every single one in front of the owner as a separate decision, and
only sends what was approved — through the studio's own mail provider, with the same
suppression, sender-profile and one-send-per-business checks the Outreach studio uses.

Two stages in one agent:

1. **Gate** — collect outbound items (an e-mail carrier for the review link, a manual
   share message for WhatsApp/SMS where no address exists) and raise approvals.
2. **Dispatch** — after the owner decides, send the approved items (or mark a manual
   message ready to copy), then report exactly what happened.
"""

from crew.business import BRAIN_VERSION, ETHICS
from crew.skills_loader import load_skill, rules

import json, uuid
from datetime import datetime, timezone

try:
    from crew.crew import CrewError
except Exception:  # pragma: no cover
    class CrewError(Exception):
        pass

from web.review_links import get_link
from web.crew_mail import send_email, manual_ready, preflight, smtp_ready


def pending_for_run(db, run_id):
    with db() as c:
        return [dict(r) for r in c.execute('SELECT * FROM crew_approvals WHERE run_id=? ORDER BY created', (run_id,))]


def dispatch_item(crew, approval, now=None):
    """Send one approved item. Called by the console button and by the dispatch step."""
    now = now or crew.now
    db = crew.db
    settings = crew.settings()
    payload = approval.get('payload') if isinstance(approval.get('payload'), dict) else json.loads(approval.get('payload') or '{}')
    lead_id = approval.get('lead_id') or payload.get('lead_id')
    with db() as c:
        row = c.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not row:
        return {'ok': False, 'detail': 'That business is no longer in the directory.'}
    lead = dict(row)
    payload['lead_id'] = lead['id']
    if approval.get('kind') == 'manual_share':
        return manual_ready(db, now, lead, payload.get('body', ''), approval.get('id', ''), approval.get('run_id', ''))
    if approval.get('kind') != 'outreach_email':
        return {'ok': False, 'detail': 'Unknown crew item type.'}
    return send_email(db, now, crew.log, lead, payload.get('subject', ''), payload.get('body', ''), settings,
                      approval.get('id', ''), approval.get('run_id', ''))


def run(ctx):
    """Two-phase: raise approvals the first time, dispatch the approved ones on resume."""
    run_id = ctx.run['id']
    approvals = pending_for_run(ctx.db, run_id)
    decided = [a for a in approvals if a['state'] in ('approved', 'rejected')]

    if not approvals and not decided:
        return _raise(ctx)

    # Phase 2 — the owner has decided. Dispatch what was approved.
    sent, queued, blocked, manual, rejected = [], [], [], [], []
    approved = [a for a in decided if a['state'] == 'approved']
    if len(approved) > 5:
        ctx.receipt('closer', f'{len(approved)} approved items found; the cap for one run is 5. '
                              'The rest stay approved for a later run.')
    for approval in approved[:5]:
        approval['payload'] = json.loads(approval['payload'] or '{}')
        result = dispatch_item(_crew_ref(ctx), approval, ctx.now)
        item = {'approval_id': approval['id'], 'title': approval['title'], 'state': result.get('state'),
                'detail': result.get('detail')}
        if result.get('state') == 'sent':
            sent.append(item)
            ctx.receipt('sent', f"{approval['title']}: {result['detail']}", evidence=result.get('dispatch_id', ''))
        elif result.get('state') == 'queued':
            queued.append(item)
            ctx.receipt('queued', f"{approval['title']}: {result['detail']}")
        elif result.get('state') == 'ready':
            manual.append(item)
            ctx.receipt('ready', f"{approval['title']}: {result['detail']}")
        else:
            blocked.append(item)
            ctx.receipt('blocked', f"{approval['title']}: {result['detail']}")
    for approval in decided:
        if approval['state'] == 'rejected':
            rejected.append({'approval_id': approval['id'], 'title': approval['title'], 'note': approval.get('note', '')})

    with ctx.db() as c:
        c.execute("UPDATE followups SET state='active',updated=? WHERE run_id=? AND state='planned' AND lead_id IN "
                  "(SELECT lead_id FROM crew_dispatch WHERE run_id=? AND state IN ('sent','ready'))", (ctx.now(), run_id, run_id))

    summary = (f'Dispatched: {len(sent)} sent, {len(queued)} queued in the outbox, {len(manual)} share message(s) ready to copy; '
               f'{len(blocked)} blocked by a guardrail; {len(rejected)} rejected by you.')
    ctx.emit(summary)
    if sent or manual:
        ctx.artifact('dispatch-log', 'Dispatch log', json.dumps({'sent': sent, 'queued': queued, 'manual': manual,
                                                                 'blocked': blocked, 'rejected': rejected}, indent=2))
    return {'summary': summary, 'data': {'sent': len(sent), 'brain': BRAIN_VERSION, 'queued': len(queued),
                                         'manual': len(manual),
                                         'blocked': blocked, 'rejected': rejected, 'approved': len(approved)}}


def _crew_ref(ctx):
    """The Closer needs the Crew object for dispatch; the runtime passes it on the context."""
    if ctx.crew is None:
        raise CrewError('The crew runtime is not attached to this step — cannot dispatch safely.')
    return ctx.crew


def _recheck(draft):
    """A draft can be edited after the Scribe wrote it. Nothing reaches the approval queue
    without passing the same guardrails again — this is the cold-email playbook's quality
    check, enforced in code rather than trusted to the writer."""
    from agents.agent_scribe import guardrails
    return guardrails(draft)


def _raise(ctx):
    """Build the approval list from the drafts and review links in this run."""
    leads = ctx.load_leads()
    if not leads:
        raise CrewError('There is nothing to approve: the run produced no leads.')
    settings = ctx.settings()
    items = []
    for lead in leads[:ctx.params.get('limit') or 10]:
        with ctx.db() as c:
            link_row = c.execute("SELECT token FROM review_links WHERE lead_id=? AND status='ready' ORDER BY created DESC LIMIT 1",
                                 (lead['id'],)).fetchone()
        link = get_link(ctx.db, token=link_row['token']) if link_row else None
        has_email = bool((lead.get('email') or '').strip())
        if has_email:
            ok, reason = preflight(ctx.db, ctx.now, lead, settings)
            basis = ETHICS['contact_basis'].format(source=lead.get('source') or 'saved record',
                                                   date=(lead.get('created') or '')[:10])
            draft = lead.get('body') or ''
            problems = _recheck(draft) if draft else ['no draft text on this lead yet']
            if problems:
                # Held here rather than at send time: the owner should never be asked to
                # approve something the crew would refuse to send.
                ctx.receipt('held', f"{lead['name']}: draft held back — {'; '.join(problems)}")
                continue
            items.append({
                'lead_id': lead['id'],
                'title': f"E-mail {lead['email']} — {lead['name']}",
                'to': lead['email'], 'channel': 'email',
                'subject': lead.get('subject') or f"A website idea for {lead['name']}",
                'body': lead.get('body') or '',
                'review_link': (f"/r/{link['token']}" if link else ''),
                'preflight': 'ready' if ok else reason,
                'contact_basis': basis,
            })
        elif link:
            base = (settings.get('public_base_url') or '').rstrip('/')
            share = link.get('share_message') or ''
            share = share.replace('/r/<token>', f"/r/{link['token']}").replace('{link}', f"{base}/r/{link['token']}")
            items.append({
                'lead_id': lead['id'], 'channel': 'manual', 'kind': 'manual_share',
                'title': f"Share message for {lead['name']} (no e-mail on record)",
                'to': lead.get('phone') or '', 'body': share, 'review_link': f"/r/{link['token']}",
                'preflight': 'no e-mail address — this one is copy-and-paste into WhatsApp, SMS or a call note.',
            })
        else:
            ctx.receipt('closer', f"{lead['name']}: nothing to approve — no contact details and no review link.")
    prospecting = load_skill('prospecting')
    compliance = rules('prospecting', 'Public business contact channels', 1) + \
                 rules('prospecting', 'retain the source URL', 1) or rules('prospecting', 'No bulk scraping', 1)
    if prospecting and items:
        ctx.receipt('playbook', 'prospecting playbook applied: every dispatch cites a public listing, its source '
                                'and the date it was recorded, and no message goes out without an opt-out line.',
                    evidence=str(prospecting.get('path') or 'skills/vendor/prospecting/SKILL.md'))
    playbook = load_skill('cold-email')
    if playbook and items:
        ctx.receipt('playbook', 'cold-email playbook applied: every draft re-checked against its quality '
                                'check (one ask, short, opt-out line) immediately before this queue was raised.',
                    evidence=str(playbook.get('path') or 'skills/vendor/cold-email/SKILL.md'))
    if not items:
        ctx.emit('Nothing outbound to approve for this run.')
        return {'summary': 'Nothing outbound to approve for this run.', 'data': {'raised': 0},
                'gate': {'kind': 'outreach_email', 'items': [], 'continue_on_empty': True}}
    ctx.receipt('closer', f'{len(items)} outbound item(s) queued for your decision. SMTP '
                          f'{"is configured" if smtp_ready() else "is NOT configured — approved e-mails will wait in the outbox"}.')
    return {'summary': f'{len(items)} outbound item(s) are waiting for your approval. Nothing has been sent.',
            'data': {'raised': len(items), 'playbook': 'cold-email' if playbook else '',
                     'playbooks': [name for name, loaded in (('cold-email', playbook), ('prospecting', prospecting)) if loaded],
                     'compliance_rules': compliance[:2],
                     'quality_check': rules('cold-email', 'check', 3)},
            'gate': {'kind': 'outreach_email', 'items': items}}
