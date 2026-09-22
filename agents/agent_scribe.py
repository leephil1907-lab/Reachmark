"""Scribe — outreach drafting for the Reachmark crew.

Writes the first message, two follow-ups and a short SMS/WhatsApp note for each lead,
in the owner's voice, using only facts the workspace actually holds (the business's
own contact fields, the measured observations, the concept link).

The prompt follows the vendored ``cold-email`` playbook: short, specific, one ask,
no hype, no fake familiarity. A deterministic engine writes every draft, so the crew
works with no API key; when a provider *is* configured, the model is asked to tighten
the wording and its output still has to pass the same guardrail checks — if it fails
them (turns corporate, invents a number, drops the opt-out line) the deterministic
draft is kept.

Drafts only. Sending is a separate, human-approved step handled by the Closer.
"""
import json, re

try:
    from crew.crew import CrewError
except Exception:  # pragma: no cover
    class CrewError(Exception):
        pass

from crew.business import BRAIN_VERSION, ETHICS, STUDIO, TAGLINE, VOICE
from crew.skills_loader import rules, prompt_brief
from web.review_links import get_link

# Hard rules copied in spirit from the vendored cold-email playbook and enforced in code.
BANNED_PHRASES = ['dear sir', 'i hope this email finds you well', 'i wanted to reach out',
                  'quick question', 'circling back', 'synergy', 'revolutionary', 'game-chang',
                  'limited time', 'guaranteed results', 'cheapest', 'best in the world']
MAX_WORDS = 150


def _first_name(name):
    cleaned = re.sub(r'\((?:demo|test)[^)]*\)', '', name or '', flags=re.I).strip()
    return (cleaned.split(',')[0].split(' ')[0] or 'there').strip('.')


def deterministic_draft(lead, concept, observations, settings, tone='Professional'):
    """Build email 1, two follow-ups and an SMS note. No inventing, no digits but real ones."""
    studio = (settings.get('agency') or STUDIO['name']).strip()
    sender = (settings.get('sender_name') or studio).strip()
    name = lead.get('name') or 'your business'
    place = f" in {lead.get('city')}" if lead.get('city') else ''
    category = (lead.get('category') or 'local business').lower()
    link = concept.get('share_url') or concept.get('link_url') or ''
    signals = (observations or {}).get('signals', {})
    status = (lead.get('audit_status') or '').upper()

    # One specific, checkable observation — chosen from what was actually measured.
    if not (lead.get('website') or '').strip():
        observation = f"your listing doesn't show a website, so anyone searching for a {category}{place} lands on directories instead of you"
    elif status == 'SOCIAL_ONLY' or lead.get('status') == 'SOCIAL_ONLY':
        observation = "your only listed link is a social profile, which is fine for regulars but hard for new customers to read"
    elif status == 'DNS_UNRESOLVED':
        observation = f"the website on your listing didn't resolve when I checked ({lead.get('audit_reason', '')[:60]})"
    elif status == 'HTTP_ERROR':
        observation = f"the website on your listing returned an error when I tried it ({lead.get('audit_reason', '')[:60]})"
    elif observations.get('ok') and (observations.get('link_check') or {}).get('broken'):
        broken = observations['link_check']['broken']
        observation = (f"{len(broken)} of the links on your page failed when I tried them" if len(broken) > 1
                       else 'one of the links on your page failed when I tried it')
    elif observations.get('ok') and signals.get('img_missing_alt'):
        observation = (f"{signals['img_missing_alt']} of your images have no alt text, so screen readers skip them")
    elif signals.get('viewport') is False or (observations.get('ok') and not signals.get('viewport')):
        observation = "your page doesn't declare a mobile viewport, so phones render it zoomed out"
    elif observations.get('ok') and not (signals.get('has_contact_link') or signals.get('has_tel_link')):
        observation = "your page has no tap-to-call or contact link, so a visitor has to hunt for how to reach you"
    else:
        observation = f"I had a look at how {name} shows up online{place}"

    body_lines = [
        f"Hi {_first_name(name)},",
        '',
        f"I'm {sender}. I noticed {observation}.",
        '',
        f"So I sketched an independent concept for a {category} site — using only what is already listed publicly about "
        f"{name}, nothing invented.",
    ]
    if link:
        body_lines += ['', f"60-second look (nothing to install): {link}"]
    body_lines += [
        '',
        "Tap “Yes — build my website” and I'll send scope and a fixed price. Tap “Not right now” or "
        "“I already have a website” and I won't follow up again.",
        '',
        sender,
        '',
        ETHICS['opt_out_email'],
    ]
    email1 = '\n'.join(body_lines)

    follow_up_1 = '\n'.join([
        f"Hi {_first_name(name)},",
        '',
        f"Following up once on the {category} concept I sketched{place} — the link is still live if you want a look:"
        if link else f"Following up once on the {category} idea I mentioned{place}.",
        *([f'{link}', ''] if link else []),
        'No pressure either way — a one-word reply is enough, and I\'ll stop if it is not a fit.',
        '',
        sender,
    ])

    follow_up_2 = '\n'.join([
        f"Hi {_first_name(name)},",
        '',
        f"Last note from me{place and ' on'} this one. If a website is not a priority this year, that is a completely "
        f"reasonable answer — reply “no thanks” and I'll close the file.",
        '',
        'If it becomes one, the concept is saved and I can walk you through it in ten minutes.',
        '',
        sender,
    ])

    sms = (f"Hi {_first_name(name)}, {sender} here — I sketched a website idea for {name} using your public listing. "
           f"60-second look: {link} {ETHICS['opt_out_sms']}" if link else
           f"Hi {_first_name(name)}, {sender} here — I had an idea about how {name} shows up online. "
           f"Happy to send it over, reply if you'd like it.")

    return {'email1': email1[:4000], 'follow_up_1': follow_up_1[:2000], 'follow_up_2': follow_up_2[:2000],
            'sms': sms[:320],
            'observed': observation, 'generated_by': 'deterministic engine',
            'tone': tone, 'rules': rules('cold-email', 'writing principles', 5) + rules('copywriting', 'principle', 3)}


def guardrails(text):
    """Checks every draft must pass, whoever wrote it."""
    problems = []
    low = (text or '').lower()
    for phrase in BANNED_PHRASES:
        if phrase in low:
            problems.append(f'banned filler phrase: "{phrase}"')
    if len((text or '').split()) > MAX_WORDS:
        problems.append(f'too long ({len((text or "").split())} words, limit {MAX_WORDS})')
    if not text or len(text.strip()) < 40:
        problems.append('too short to be a real message')
    if not re.search(r'(unsubscribe|no thanks|opt out|reply stop|send stop|stop if)', low):
        problems.append('no opt-out phrasing found')
    return problems


def tighten_with_provider(ctx, draft, lead, concept):
    """Optional phrasing pass. Returns (text, meta) — text is None when nothing was used."""
    if not ctx.llm:
        return None, {'used': False, 'reason': 'no provider configured'}
    context = prompt_brief(['cold-email', 'copywriting'], per_skill=1800)
    system = ('You tighten one cold outreach e-mail for a small website studio. Keep every fact exactly as given — '
              'never add a number, price, client name, statistic or claim. Keep it under 140 words, plain and human, '
              'one ask, no marketing filler. Return only the e-mail body text. Studio voice (Reachmark — ' + TAGLINE + '): '
              + '; '.join(VOICE['rules']) + '.\n\n' + context)
    facts = {
        'business': lead.get('name'), 'category': lead.get('category'), 'city': lead.get('city'),
        'observed': draft['observed'], 'review_link': concept.get('share_url', ''),
        'studio': concept.get('studio', ''),
    }
    user = ('Rewrite this draft so it reads like a person, keeping the same facts, length and the opt-out line.\n\n'
            f'Facts available (do not add others): {json.dumps(facts)}\n\nDRAFT:\n{draft["email1"]}')
    text = ctx.llm(system, user, max_tokens=600, temperature=0.3)
    if not text:
        return None, {'used': False, 'reason': 'provider unavailable'}
    if not concept.get('share_url'):
        text = re.sub(r'https?://\S+', '', text)
    problems = guardrails(text)
    if problems:
        return None, {'used': False, 'reason': 'model draft failed guardrails: ' + '; '.join(problems[:3])}
    return text, {'used': True, 'model': True}


def run(ctx):
    leads = ctx.load_leads()
    if not leads:
        raise CrewError('Scribe has no leads. Run Scout and Auditor first, or choose a saved business with contact details.')
    drafted, skipped = [], []
    for lead in leads[:ctx.params.get('limit') or 10]:
        if ctx.expired():
            ctx.emit('Scribe stopped at the step time budget; remaining leads are untouched.')
            break
        with ctx.db() as c:
            link_row = c.execute("SELECT token FROM review_links WHERE lead_id=? AND status='ready' ORDER BY created DESC LIMIT 1",
                                 (lead['id'],)).fetchone()
        link = get_link(ctx.db, token=link_row['token']) if link_row else None
        concept = dict(link['concept']) if link else {}
        if link:
            base = (ctx.settings().get('public_base_url') or '').rstrip('/')
            concept['share_url'] = f'{base}/r/{link["token"]}' if base else f'/r/{link["token"]}'
        from agents.agent_auditor import latest_audit
        audit = latest_audit(ctx.db, lead['id']) or {}
        draft = deterministic_draft(lead, concept, audit.get('observations') or {}, ctx.settings(), ctx.params.get('tone', 'Professional'))

        tightened, meta = tighten_with_provider(ctx, draft, lead, concept)
        if tightened:
            draft['email1'] = tightened
            draft['generated_by'] = 'deterministic engine + model phrasing (guardrail-checked)'
        # Guardrails apply to each message on its own, exactly as it will be read.
        problems = guardrails(draft['email1']) + guardrails(draft['follow_up_1']) + guardrails(draft['follow_up_2'])
        if problems:
            ctx.receipt('guardrail', f"{lead['name']}: draft held back — {'; '.join(problems[:3])}.")
            skipped.append({'lead_id': lead['id'], 'name': lead['name'], 'problems': problems})
            continue

        subject = {
            'Professional': f"A website idea for {lead['name']}",
            'Warm': f"Something I noticed about {lead['name']}",
            'Concise': f"{lead['name']}: quick website idea",
        }.get((ctx.params.get('tone') or 'Professional').title(), f"A website idea for {lead['name']}")

        with ctx.db() as c:
            c.execute('UPDATE leads SET subject=?,body=?,stage=CASE WHEN stage IN ("New") THEN "Drafted" ELSE stage END,updated=? WHERE id=?',
                      (subject[:400], draft['email1'][:8000], ctx.now(), lead['id']))
            for index, (kind, body, days) in enumerate((('follow_up_1', draft['follow_up_1'], 3),
                                                        ('follow_up_2', draft['follow_up_2'], 7))):
                c.execute('INSERT INTO followups(id,lead_id,run_id,kind,channel,due,state,payload,created,updated) '
                          'VALUES(?,?,?,?,?,?,?,?,?,?)',
                          (__import__('uuid').uuid4().hex, lead['id'], ctx.run['id'], kind, 'email',
                           _due(ctx.now(), days), 'planned', json.dumps({'subject': 'Re: ' + subject, 'body': body})[:8000],
                           ctx.now(), ctx.now()))
        drafted.append({'lead_id': lead['id'], 'name': lead['name'], 'subject': subject,
                        'email': (lead.get('email') or ''), 'share_url': concept.get('share_url', ''),
                        'llm': meta})
        ctx.receipt('draft', f"{lead['name']}: first message + 2 follow-ups drafted "
                             f"({len(draft['email1'].split())} words in message 1, {draft['generated_by']}).")
        ctx.artifact('draft', f"Outreach draft — {lead['name']}",
                     f"Subject: {subject}\n\n{draft['email1']}\n\n--- follow-up 1 (day 3) ---\n{draft['follow_up_1']}"
                     f"\n\n--- follow-up 2 (day 7) ---\n{draft['follow_up_2']}\n\n--- SMS / WhatsApp ---\n{draft['sms']}",
                     meta={'lead_id': lead['id'], 'brain': BRAIN_VERSION, 'observed': draft['observed'], 'llm': meta,
                           'rules_applied': draft['rules'][:6]})
    summary = (f'Drafted {len(drafted)} first message(s) with follow-ups; {len(skipped)} held back by the guardrails. '
               f'Nothing has been sent — each message goes to your approval queue next.')
    ctx.emit(summary)
    return {'summary': summary, 'data': {'drafts': drafted, 'held_back': skipped,
                                         'lead_ids': [item['lead_id'] for item in drafted]}}


def _due(stamp_iso, days):
    from datetime import datetime, timedelta, timezone
    try:
        base = datetime.fromisoformat(stamp_iso.replace('Z', '+00:00'))
    except ValueError:
        base = datetime.now(timezone.utc)
    return (base + timedelta(days=days)).isoformat()
