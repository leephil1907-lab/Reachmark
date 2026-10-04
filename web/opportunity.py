"""Reachmark Opportunity Engine.

Sits between discovery and outreach. Every number and sentence is derived from
saved leads, measured website observations, projects and contracts. Nothing is
invented: if a signal was not observed, the report says so.
"""
from __future__ import annotations

import json, secrets, uuid
from flask import jsonify, render_template, request, abort, session

from web.web_probe import gaps_from
from web.intelligence import _fit

LEAK_COPY = {
    'no_website_listed': {
        'title': 'No owned website is listed',
        'leak': 'There is no website URL in the public listing we used. Visitors who search the business name may have nowhere to enquire.',
        'fix': 'A simple lead-generation website with a clear enquiry path.',
    },
    'social_only': {
        'title': 'Social profile only',
        'leak': 'The only listed URL is a social profile. Social posts are not a conversion page you control.',
        'fix': 'An owned page that captures enquiries independently of an algorithm.',
    },
    'http_error': {
        'title': 'Listed page did not load',
        'leak': 'The listed website returned an error at check time. People who tap the listing may bounce.',
        'fix': 'Restore or replace the public page, then add a working enquiry path.',
    },
    'unreachable': {
        'title': 'Listed page did not connect',
        'leak': 'The listed website did not connect at check time. This may be temporary — it is not proof the site is gone.',
        'fix': 'Re-check, then repair hosting or DNS if the failure repeats.',
    },
    'dns_unresolved': {
        'title': 'Domain did not resolve',
        'leak': 'The listed domain did not resolve at check time.',
        'fix': 'Correct DNS or point visitors to a working site.',
    },
    'parked_suspected': {
        'title': 'Domain looks parked',
        'leak': 'Parking or domain-sale wording appeared on the page we read.',
        'fix': 'Replace the parked page with a real business site.',
    },
    'no_https': {
        'title': 'No TLS on the page we read',
        'leak': 'The page was served over plain HTTP. Browsers warn visitors; some will not submit a form.',
        'fix': 'Serve the site over HTTPS before asking for contact details.',
    },
    'no_viewport': {
        'title': 'No mobile scaling declared',
        'leak': 'The page has no viewport meta tag. Booking or contact controls can be hard to use on a phone.',
        'fix': 'A mobile-first layout with a visible tap target for the next step.',
    },
    'no_form_or_booking': {
        'title': 'No lead-capture path on the page we read',
        'leak': 'No form, booking link or enquiry path was found. Interested visitors have no obvious way to act.',
        'fix': 'A single, visible enquiry or booking path above the fold on mobile.',
    },
    'no_contact_path': {
        'title': 'No contact path on the page we read',
        'leak': 'No contact link, telephone or email link was found. People cannot start a conversation from the page.',
        'fix': 'A contact block with a real phone, email or form the business actually uses.',
    },
    'thin_page': {
        'title': 'Very little visible copy',
        'leak': 'Fewer than 120 words of visible text were read. Services may not be explained well enough to convert.',
        'fix': 'Clear service pages written from facts the business can confirm.',
    },
    'missing_title': {
        'title': 'No page title',
        'leak': 'Search results and browser tabs will show a bare URL instead of the business name.',
        'fix': 'A specific title on every important page.',
    },
    'no_description': {
        'title': 'No meta description',
        'leak': 'Search engines will invent the snippet. The business does not control the first impression in search.',
        'fix': 'A written description for the homepage and each service page.',
    },
    'no_h1': {
        'title': 'No H1 heading',
        'leak': 'The page never states its topic in a top heading. Visitors and search engines guess.',
        'fix': 'One clear H1 that names the business and the offer.',
    },
    'slow_first_byte': {
        'title': 'Slow first byte on this check',
        'leak': 'First byte took over 2.5 seconds. Slow pages lose mobile visitors before the offer appears.',
        'fix': 'Hosting and image pass so the first screen arrives quickly.',
    },
    'stale_copyright': {
        'title': 'Oldest-looking year on the page',
        'leak': 'The newest year printed on the page is two or more years old. The business can look inactive.',
        'fix': 'Update the site, then keep a real year and a current offer.',
    },
    'broken_links': {
        'title': 'Sampled links failed',
        'leak': 'Some on-site links failed at check time. Dead ends stop an enquiry.',
        'fix': 'Repair or remove broken links, especially around contact and services.',
    },
    'broken_anchors': {
        'title': 'In-page links go nowhere',
        'leak': 'In-page links point at sections that do not exist. Taps do nothing.',
        'fix': 'Match every in-page link to a real section, especially CTAs.',
    },
    'no_images': {
        'title': 'No images on the page we read',
        'leak': 'The page we read had no images. Service businesses usually convert better with real work shown.',
        'fix': 'A short gallery of real, permitted photographs.',
    },
    'images_missing_alt': {
        'title': 'Images without alt text',
        'leak': 'Images without alt text are skipped by screen readers and image search.',
        'fix': 'Describe each image in plain language.',
    },
    'mixed_content': {
        'title': 'Secure page loads insecure files',
        'leak': 'A HTTPS page loads resources over HTTP. Browsers may block them.',
        'fix': 'Serve every asset over HTTPS.',
    },
}

COMMERCIAL_KEYS = (
    'no_website_listed', 'social_only', 'http_error', 'unreachable', 'dns_unresolved',
    'parked_suspected', 'no_form_or_booking', 'no_contact_path', 'no_viewport',
    'thin_page', 'missing_title', 'no_description', 'no_h1', 'slow_first_byte',
    'stale_copyright', 'broken_links', 'broken_anchors',
)


def ensure_tables(db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS opportunity_reports(
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            score INTEGER NOT NULL,
            priority TEXT NOT NULL,
            qualified INTEGER NOT NULL DEFAULT 0,
            leak_count INTEGER NOT NULL DEFAULT 0,
            leaks TEXT NOT NULL,
            solution TEXT NOT NULL,
            fit TEXT NOT NULL,
            evidence TEXT NOT NULL,
            outreach TEXT NOT NULL,
            views INTEGER NOT NULL DEFAULT 0,
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            owner_user_id TEXT
        );
        CREATE INDEX IF NOT EXISTS opportunity_reports_lead ON opportunity_reports(lead_id, created);
        CREATE INDEX IF NOT EXISTS opportunity_reports_token ON opportunity_reports(token);
        ''')


def _owner_clause(alias=''):
    prefix = (alias + '.') if alias else ''
    cid = session.get('client_id') if session.get('role') == 'client' else None
    if cid:
        return prefix + 'owner_user_id=?', (cid,)
    return '1=1', ()


def _lead(db, lid):
    with db() as c:
        row = c.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
    if not row:
        return None
    lead = dict(row)
    cid = session.get('client_id') if session.get('role') == 'client' else None
    if cid and lead.get('owner_user_id') != cid:
        return None
    return lead


def _latest_audit(db, lid):
    with db() as c:
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='site_audits'").fetchone()
        if not exists:
            return None
        row = c.execute('SELECT * FROM site_audits WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lid,)).fetchone()
    if not row:
        return None
    audit = dict(row)
    for key in ('signals', 'observations', 'gaps'):
        try:
            audit[key] = json.loads(audit.get(key) or '{}')
        except (TypeError, ValueError):
            audit[key] = {}
    return audit


def money_leaks(lead, audit):
    observations = (audit or {}).get('observations') or {}
    if isinstance(observations, str):
        try:
            observations = json.loads(observations)
        except ValueError:
            observations = {}
    packed = gaps_from(observations, lead)
    leaks = []
    for gap in packed.get('gaps') or []:
        key = gap.get('key')
        meta = LEAK_COPY.get(key)
        if not meta:
            continue
        leaks.append({
            'id': key,
            'title': meta['title'],
            'leak': meta['leak'],
            'fix': meta['fix'],
            'weight': gap.get('weight') or 1,
            'source': gap.get('source') or 'Observed',
            'reason': gap.get('reason') or meta['leak'],
            'commercial': key in COMMERCIAL_KEYS,
        })
    return leaks, packed


def opportunity_score(leaks, lead):
    """Relative 0–100 ranking of observed gaps. Not a revenue forecast."""
    weight = sum(item['weight'] for item in leaks)
    score = min(100, 18 + weight * 9)
    if not (lead.get('website') or '').strip():
        score = max(score, 78)
    if (lead.get('status') or '') == 'SOCIAL_ONLY':
        score = max(score, 74)
    if not leaks:
        score = 12 if (lead.get('website') or '').strip() else 64
    return int(score)


def priority_for(score, leaks):
    ids = {item['id'] for item in leaks}
    if score >= 70 or ids & {'no_website_listed', 'social_only', 'http_error', 'parked_suspected'}:
        return 'High'
    if score >= 40 or any(item['commercial'] for item in leaks):
        return 'Medium'
    return 'Low'


def qualify(lead, leaks, score):
    if (lead.get('stage') or '') == 'Not a fit':
        return False
    if not (lead.get('website') or '').strip() or (lead.get('status') or '') == 'SOCIAL_ONLY':
        return True
    if score >= 40 and any(item['commercial'] for item in leaks):
        return True
    if lead.get('email') or lead.get('phone'):
        return score >= 30
    return bool(leaks)


def recommend_solution(leaks, lead):
    ids = {item['id'] for item in leaks}
    category = (lead.get('category') or 'this business').strip() or 'this business'
    if ids & {'no_website_listed', 'social_only', 'parked_suspected'}:
        name = 'Lead-generation website + automated inquiry system'
        why = 'There is no owned conversion page in the listing we checked. One site can present services and take enquiries.'
    elif 'no_form_or_booking' in ids and 'no_contact_path' in ids:
        name = 'Lead-generation website + automated inquiry system'
        why = 'The page we read has neither a form nor a contact path. The same build can fix both.'
    elif 'no_form_or_booking' in ids or 'no_contact_path' in ids:
        name = 'Conversion path on the existing site'
        why = 'The page we read does not give a visitor a clear next step. A visible enquiry path is the first fix.'
    elif 'no_viewport' in ids or 'slow_first_byte' in ids:
        name = 'Mobile conversion pass'
        why = 'The observation points at a mobile or speed problem that can hide the offer on a phone.'
    elif ids & {'missing_title', 'no_description', 'no_h1', 'thin_page'}:
        name = 'Search-visibility and service pages'
        why = 'The page we read is thin or missing basic search signals. Service pages can carry the offer.'
    elif ids & {'http_error', 'unreachable', 'dns_unresolved'}:
        name = 'Restore the public page, then add an enquiry path'
        why = 'The listed URL did not serve a working page at check time. Repair comes before design.'
    elif leaks:
        name = 'Focused website improvement'
        why = 'Observed gaps can be addressed on the current site without claiming a full rebuild is required.'
    else:
        name = 'No clear digital leak from this check'
        why = 'The observation did not produce a commercial gap. Do not pitch a rebuild on this evidence alone.'
    addressed = [item['id'] for item in leaks if item['commercial']][:7]
    return {
        'name': name,
        'why': why,
        'category': category,
        'addresses': addressed,
        'addressed_count': len(addressed),
        'note': 'The recommendation follows observed gaps only. Confirm fit with the business before any proposal.',
    }


def draft_outreach(lead, leaks, solution, score):
    name = lead.get('name') or 'there'
    city = lead.get('city') or ''
    first_leak = leaks[0]['leak'] if leaks else 'We looked at the public listing and the page we could read.'
    body = (
        f"Hello {name},\n\n"
        f"I looked at the public web presence for {name}"
        f"{' in ' + city if city else ''}. "
        f"This is a short observation, not a sales script.\n\n"
        f"{first_leak}\n\n"
        f"Recommended next step, based only on that check: {solution['name']}.\n"
        f"{solution['why']}\n\n"
        f"Opportunity ranking from this check: {score}/100 "
        f"(a ranking of observed gaps, not a forecast of revenue).\n\n"
        f"The full note is on the report link. If it is useful, I can walk through it. "
        f"If it is not, no need to reply.\n"
    )
    return {
        'subject': f'A short digital observation for {name}',
        'body': body,
        'basis': 'Grounded in the saved listing and, where a page was fetched, measured on-page signals.',
    }


def build_report(db, lead, now, observe_live=False):
    audit = _latest_audit(db, lead['id'])
    if observe_live and (lead.get('website') or '').strip():
        try:
            from agents.agent_auditor import audit_lead as run_audit
            class _Ctx:
                def __init__(self, db, now):
                    self.db = db
                    self.now = now
                    self.params = {}
                def receipt(self, *args, **kwargs):
                    return None
                def emit(self, *args, **kwargs):
                    return None
                def expired(self):
                    return False
            audit = run_audit(_Ctx(db, now), lead) or audit
        except Exception:
            pass
    leaks, packed = money_leaks(lead, audit)
    score = opportunity_score(leaks, lead)
    priority = priority_for(score, leaks)
    ok = qualify(lead, leaks, score)
    solution = recommend_solution(leaks, lead)
    fit = _fit(lead.get('category'))
    outreach = draft_outreach(lead, leaks, solution, score)
    evidence = {
        'website': lead.get('website') or '',
        'listing_status': lead.get('status') or '',
        'audit_status': (audit or {}).get('status') or lead.get('audit_status') or 'NOT_ANALYZED',
        'checked_at': (audit or {}).get('created') or lead.get('checked_at'),
        'http_code': (audit or {}).get('http_code'),
        'gap_score_raw': packed.get('score'),
        'disclaimer': packed.get('disclaimer') or (
            'A ranked list of observed gaps at this point in time — not a claim that the business wants a new website.'
        ),
    }
    return {
        'score': score,
        'priority': priority,
        'qualified': 1 if ok else 0,
        'leak_count': len(leaks),
        'leaks': leaks,
        'solution': solution,
        'fit': fit,
        'evidence': evidence,
        'outreach': outreach,
    }


def save_report(db, lead, payload, now):
    rid = uuid.uuid4().hex
    token = secrets.token_urlsafe(16)
    stamp = now()
    with db() as c:
        c.execute(
            '''INSERT INTO opportunity_reports(
                id, lead_id, token, score, priority, qualified, leak_count,
                leaks, solution, fit, evidence, outreach, views, created, updated, owner_user_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?)''',
            (rid, lead['id'], token, payload['score'], payload['priority'], payload['qualified'],
             payload['leak_count'], json.dumps(payload['leaks']), json.dumps(payload['solution']),
             json.dumps(payload['fit']), json.dumps(payload['evidence']), json.dumps(payload['outreach']),
             stamp, stamp, lead.get('owner_user_id')),
        )
    payload = dict(payload)
    payload.update(id=rid, token=token, lead_id=lead['id'], created=stamp, views=0)
    try:
        from web.revenue_os import on_report_saved
        on_report_saved(db, lead, payload, now)
    except Exception:
        pass
    return payload


def serialize_row(row):
    data = dict(row)
    for key in ('leaks', 'solution', 'fit', 'evidence', 'outreach'):
        try:
            data[key] = json.loads(data.get(key) or '{}')
        except (TypeError, ValueError):
            data[key] = {}
    return data


def funnel_counts(db):
    """Canonical Revenue OS counts. A project or contract is never a proposal."""
    from web.revenue_os import canonical_funnel, ensure_tables
    ensure_tables(db)
    return canonical_funnel(db)


def register_opportunity(app, db, now, log):
    ensure_tables(db)

    @app.get('/api/opportunity/funnel')
    def opportunity_funnel():
        return jsonify(funnel_counts(db))

    @app.get('/api/opportunity/reports')
    def opportunity_reports():
        with db() as c:
            where, args = _owner_clause('r')
            rows = c.execute(
                f'''SELECT r.*, l.name AS lead_name, l.city AS lead_city, l.category AS lead_category,
                           l.website AS lead_website, l.stage AS lead_stage
                    FROM opportunity_reports r
                    JOIN leads l ON l.id=r.lead_id
                    WHERE {where}
                    ORDER BY r.created DESC LIMIT 80''',
                args,
            ).fetchall()
        out = []
        for row in rows:
            item = serialize_row(row)
            item['leaks'] = item['leaks'] if isinstance(item['leaks'], list) else []
            out.append(item)
        return jsonify(reports=out, count=len(out))

    @app.get('/api/opportunity/lead/<lid>')
    def opportunity_for_lead(lid):
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        with db() as c:
            row = c.execute(
                'SELECT * FROM opportunity_reports WHERE lead_id=? ORDER BY created DESC LIMIT 1',
                (lid,),
            ).fetchone()
        preview = build_report(db, lead, now, observe_live=False)
        stored = serialize_row(row) if row else None
        return jsonify(lead={k: lead.get(k) for k in ('id', 'name', 'city', 'category', 'website', 'stage', 'status', 'email')},
                       preview=preview, report=stored)

    @app.post('/api/opportunity/lead/<lid>/run')
    def opportunity_run(lid):
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        live = bool((request.get_json(silent=True) or {}).get('live'))
        payload = build_report(db, lead, now, observe_live=live)
        saved = save_report(db, lead, payload, now)
        log('opportunity', f"Opportunity report for {lead.get('name')}: {saved['score']}/100, {saved['priority']}")
        return jsonify(report=saved)

    @app.get('/o/<token>')
    def opportunity_public(token):
        with db() as c:
            row = c.execute('SELECT * FROM opportunity_reports WHERE token=?', (token,)).fetchone()
            if not row:
                abort(404)
            c.execute('UPDATE opportunity_reports SET views=views+1 WHERE token=?', (token,))
            lead = c.execute('SELECT * FROM leads WHERE id=?', (row['lead_id'],)).fetchone()
        report = serialize_row(row)
        lead = dict(lead) if lead else {}
        return render_template('opportunity-report.html', report=report, lead=lead)
