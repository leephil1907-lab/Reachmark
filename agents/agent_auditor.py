"""Auditor — measured website observation for the Reachmark crew.

Runs a bounded, robots-aware look at each lead's listed website, stores the raw
observations in ``site_audits`` and turns them into a ranked list of *observed
gaps* with a source for every line. It also keeps the lead's existing audit columns
(``audit_status`` / ``audit_reason`` / ``checked_at``) in step with the workspace
so the rest of the app stays truthful.
"""

from crew.business import BRAIN_VERSION
from crew.skills_loader import load_skill, rules

import json, uuid

try:
    from crew.crew import CrewError
except Exception:  # pragma: no cover
    class CrewError(Exception):
        pass

from web.services import audit_website
from web.web_probe import observe, gaps_from


def ensure_tables(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS site_audits(
            id TEXT PRIMARY KEY, lead_id TEXT, url TEXT, status TEXT, http_code INTEGER,
            ms INTEGER, bytes INTEGER, signals TEXT, observations TEXT, gaps TEXT, tier TEXT,
            score INTEGER, created TEXT)''')
        c.execute('CREATE INDEX IF NOT EXISTS site_audits_lead ON site_audits(lead_id, created)')


def latest_audit(db, lead_id):
    with db() as c:
        row = c.execute('SELECT * FROM site_audits WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lead_id,)).fetchone()
    if not row:
        return None
    audit = dict(row)
    for key in ('signals', 'observations', 'gaps'):
        try:
            audit[key] = json.loads(audit[key] or '{}')
        except ValueError:
            audit[key] = {}
    return audit


def audit_lead(ctx, lead):
    """Observe one lead and persist everything. Returns the stored audit dict."""
    website = (lead.get('website') or '').strip()
    if ctx.params.get('fixtures'):
        # Offline demo: record the listing evidence only, and say so.
        listing = {'status': classify_listing(lead), 'reason': 'Offline demo — the listed URL was not fetched and no '
                                                               'network call was made. Run a live audit for real observations.',
                   'http_code': None}
        observations = {'ok': False, 'reason': listing['reason'], 'signals': {}, 'final_url': website,
                        'status': None, 'https': website.startswith('https://'), 'ms': None, 'bytes': 0,
                        'headers': {}, 'robots': {}, 'fetched_at': ctx.now()}
        return _store_audit(ctx, lead, website, listing, observations)
    listing = audit_website(website) if website else {'status': 'NOT_LISTED',
                                                      'reason': 'The source listing has no website URL. Not proof there is none.',
                                                      'http_code': None}
    observations = observe(website) if website and listing.get('status') == 'HAS_WEBSITE' else {
        'ok': False, 'reason': listing.get('reason'), 'signals': {}, 'final_url': website, 'status': listing.get('http_code'),
        'https': website.startswith('https://'), 'ms': None, 'bytes': 0, 'headers': {}, 'robots': {}, 'fetched_at': ctx.now()}
    return _store_audit(ctx, lead, website, listing, observations)


def classify_listing(lead):
    """Listing-only classification: what the source says, before any live check."""
    from web.services import classify
    if not (lead.get('website') or '').strip():
        return 'NOT_LISTED'
    if classify(lead['website']) == 'SOCIAL_ONLY':
        return 'SOCIAL_ONLY'
    return 'NOT_OBSERVED'


def _store_audit(ctx, lead, website, listing, observations):
    status = listing.get('status') or 'CHECK_FAILED'
    reason = listing.get('reason') or ''
    if observations.get('reason') and status == 'LIVE':
        reason = f"{reason} {observations['reason']}".strip()
    gaps = gaps_from(observations, {**lead, 'audit_status': status})

    audit_id = uuid.uuid4().hex
    stamp = ctx.now()
    with ctx.db() as c:
        c.execute('INSERT INTO site_audits(id,lead_id,url,status,http_code,ms,bytes,signals,observations,gaps,tier,score,created) '
                  'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (audit_id, lead['id'], website, status, listing.get('http_code'), observations.get('ms'),
                   observations.get('bytes') or 0, json.dumps(observations.get('signals', {}))[:20000],
                   json.dumps(observations)[:40000], json.dumps(gaps)[:20000], gaps['tier'], gaps['score'], stamp))
        c.execute('UPDATE leads SET audit_status=?,audit_reason=?,checked_at=?,http_code=?,updated=? WHERE id=?',
                  (status, (reason + f" · ranked gaps: {gaps['score']} ({gaps['tier']})")[:600],
                   stamp, listing.get('http_code'), stamp, lead['id']))
    ctx.receipt('observation', f"{lead['name']}: {status} — {reason or 'no URL to observe'}",
                url=website or lead.get('source_url', ''), evidence=json.dumps(observations.get('signals', {}))[:500])
    for gap in gaps['gaps'][:4]:
        ctx.receipt('gap', f"{lead['name']}: {gap['reason']} ({gap['source']}, weight {gap['weight']})", url=website)
    if status == 'NOT_OBSERVED':
        ctx.receipt('gap', f"{lead['name']}: no live page was read, so no gap ranking was produced. "
                            'Run a live audit for real observations.', url=website)
    elif not gaps['gaps']:
        ctx.receipt('gap', f"{lead['name']}: no gap observed on the page read. Recorded as-is — no invented shortfall.", url=website)
    return {'id': audit_id, 'status': status, 'reason': reason, 'gaps': gaps,
            'observations': observations, 'checked_at': stamp}


def fault_report(gaps, lead, checked_at=''):
    """Turn a ranked gap list into a business-readable fault report.

    Pure function: every line quotes a measured gap, nothing is invented. Returns
    {'lines', 'proposal_lines', 'fault_count', 'fix_first'}.
    """
    items = (gaps or {}).get('gaps') or []
    lines, fix_first = [], 0
    for gap in items:
        tag = 'fix first' if gap.get('weight', 1) >= 2 else 'worth fixing'
        if gap.get('weight', 1) >= 2:
            fix_first += 1
        line = f"- [{tag}] {gap.get('reason', '')} ({gap.get('source', 'Measured on page')})"
        shown = gap.get('evidence')
        if isinstance(shown, list) and shown:
            line += f" Seen at: {', '.join(shown[:2])}"
        elif isinstance(shown, str) and shown:
            line += f' Seen at: {shown}'
        lines.append(line)
    stamp = f"measured {checked_at[:10]}" if checked_at else 'measured on the last check'
    name = (lead or {}).get('name') or 'The business'
    proposal = [f"{name}: {gap.get('reason', '')} ({stamp}; {gap.get('source', 'Measured on page').lower()})."
                for gap in items[:3]]
    return {'lines': lines, 'proposal_lines': proposal, 'fault_count': len(lines), 'fix_first': fix_first}


def run(ctx):
    leads = ctx.load_leads()
    if not leads:
        raise CrewError('Auditor has no leads to observe. Run Scout first or pick a saved business.')
    ensure_tables(ctx.db)
    audited, hot, no_site = [], 0, 0
    full_audits = {}
    signals_read = set()
    for lead in leads[:ctx.params.get('limit') or 10]:
        if ctx.expired():
            ctx.emit('Auditor stopped at the step time budget; remaining leads are untouched.')
            break
        try:
            audit = audit_lead(ctx, lead)
        except Exception as exc:
            ctx.receipt('error', f"{lead['name']}: observation failed ({type(exc).__name__}) — nothing recorded.",
                        url=lead.get('website', ''))
            continue
        audited.append({'lead_id': lead['id'], 'name': lead['name'], 'status': audit['status'],
                        'tier': audit['gaps']['tier'], 'score': audit['gaps']['score'],
                        'gaps': [g['key'] for g in audit['gaps']['gaps']]})
        full_audits[lead['id']] = (lead, audit)
        if audit['gaps']['tier'] == 'hot':
            hot += 1
        if not (lead.get('website') or '').strip():
            no_site += 1
        with ctx.db() as c:
            row = c.execute('SELECT signals FROM site_audits WHERE lead_id=? ORDER BY created DESC LIMIT 1',
                            (lead['id'],)).fetchone()
        if row and row['signals']:
            try:
                signals_read |= set(json.loads(row['signals']) or {})
            except (TypeError, ValueError):
                pass

    playbook = load_skill('seo-audit')
    checklist = rules('seo-audit', 'check', 5)
    summary = (f'Observed {len(audited)} listed website(s): {no_site} with no URL in the source and '
               f'{hot} with a strong ranked gap list. Observations are dated and stored; '
               f'none of them prove a business needs work.')
    if playbook:
        ctx.receipt('playbook', f"seo-audit playbook applied: {len(signals_read)} signal(s) read across "
                                f"{len(audited)} site(s) from its on-page checklist "
                                f"({', '.join(sorted(signals_read)[:6]) or 'none available'}); "
                                "nothing is scored that was not measured.",
                    evidence=str(playbook.get('path') or 'skills/vendor/seo-audit/SKILL.md'))
    ctx.emit(summary)
    ctx.artifact('audit-brief', f'Website observation brief — {len(audited)} business(es)',
                 '\n'.join(f"- {row['name']}: {row['status']} · ranked gaps {row['score']} ({row['tier']}) · "
                           f"{', '.join(row['gaps']) or 'none observed'}" for row in audited),
                 meta={'leads': audited, 'brain': BRAIN_VERSION, 'stage': 'verify', 'playbook': 'seo-audit',
                       'playbook_version': '2.11.1',
                       'playbook_checks': checklist[:5],
                       'signals_read': sorted(signals_read)})
    faults_total = 0
    for row in audited:
        lead, audit = full_audits[row['lead_id']]
        report = fault_report(audit['gaps'], lead, audit.get('checked_at') or '')
        if not report['lines']:
            continue
        faults_total += report['fault_count']
        ctx.artifact('website-fault-report', f"Website fault report — {lead['name']}",
                     '\n'.join(report['lines'] + ['', 'Proposal lines (measured, quote freely):'] +
                               [f'- {line}' for line in report['proposal_lines']] +
                               ['', audit['gaps'].get('disclaimer', '')]),
                     meta={'lead_id': lead['id'], 'brain': BRAIN_VERSION, 'stage': 'verify',
                           'checked_at': audit.get('checked_at') or '', 'fault_count': report['fault_count'],
                           'tier': row['tier']})
    return {'summary': summary, 'data': {'lead_ids': [row['lead_id'] for row in audited], 'audits': audited,
                                         'stage': 'verify',
                                         'hot': hot, 'no_website': no_site, 'fault_reports': faults_total}}
