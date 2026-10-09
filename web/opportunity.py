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
    'cookie_interstitial': {
        'title': 'Cookie or consent wall',
        'leak': 'The HTML we received is a cookie or consent screen, not the working site. Forms, copy, and contact paths on the real page were not measured.',
        'fix': 'The live site may be fine behind the wall. A person has to open it in a browser to see the offer.',
    },
    'js_shell': {
        'title': 'JavaScript shell',
        'leak': 'The HTML is mostly scripts with little readable copy. What a visitor sees after the page paints was not in this check.',
        'fix': 'Server-render the offer and a contact path so a fetch — and a search engine — can read them.',
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
    'parked_suspected', 'cookie_interstitial', 'js_shell',
    'no_form_or_booking', 'no_contact_path', 'no_viewport',
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


def compose_sales_asset(lead, report, prototype_url=None, proposal_url=None, book=None, next_step=None):
    """Turn a stored report into the commercial artefact a prospect can read.

    Your business → problem → evidence → visitor impact → solution → prototype
    → scope → next step. Amounts come from the price book or stay empty.
    Observation is not proof the business wants work.
    """
    lead = lead or {}
    report = report or {}
    leaks = report.get('leaks') if isinstance(report.get('leaks'), list) else []
    commercial = [item for item in leaks if item.get('commercial')]
    top = (commercial or leaks or [None])[0]
    solution = report.get('solution') if isinstance(report.get('solution'), dict) else {}
    evidence_meta = report.get('evidence') if isinstance(report.get('evidence'), dict) else {}
    website = (lead.get('website') or evidence_meta.get('website') or '').strip()
    rows = []
    for item in (commercial or leaks)[:6]:
        rows.append({
            'claim': item.get('leak') or item.get('title') or '',
            'title': item.get('title') or '',
            'source': item.get('source') or 'observation',
            'url': website,
            'reason': item.get('reason') or '',
        })
    packs = []
    for pack in ((book or {}).get('packages') or []):
        amount = pack.get('amount')
        if amount in ('',):
            amount = None
        packs.append({
            'id': pack.get('id'),
            'name': pack.get('name') or pack.get('id') or 'Package',
            'amount': amount,
            'includes': pack.get('includes') or [],
        })
    if top:
        impact = top.get('leak') or top.get('title') or ''
        impact_note = (
            'Visitor-facing consequence of the observation. '
            'It is not a measured loss of revenue and not proof the business wants work.'
        )
        problem = {
            'id': top.get('id'),
            'title': top.get('title') or 'Observed gap',
            'detected': impact,
            'source': top.get('source') or 'observation',
        }
    else:
        impact = 'This check did not produce a commercial gap.'
        impact_note = 'Do not pitch a rebuild on empty evidence.'
        problem = None
    if next_step:
        step = next_step
    elif prototype_url and proposal_url:
        step = 'Open the concept and the draft proposal. Reply if you want it built. Nothing is a contract until you say so.'
    elif prototype_url:
        step = 'Open the first-section concept, then reply if you want a walkthrough. There is no invented quote.'
    elif problem:
        step = 'Reply if you want a walkthrough of this observation. There is no invented quote attached to this note.'
    else:
        step = 'No commercial gap was recorded. There is nothing to sell from this check.'
    return {
        'business': {
            'name': lead.get('name') or 'This business',
            'category': lead.get('category') or '',
            'city': lead.get('city') or '',
            'website': website,
        },
        'problem': problem,
        'evidence': rows,
        'customer_impact': impact,
        'customer_impact_note': impact_note,
        'solution': {
            'name': solution.get('name') or '',
            'why': solution.get('why') or '',
            'note': solution.get('note') or '',
        },
        'prototype': {'url': prototype_url} if prototype_url else None,
        'proposal': {'url': proposal_url} if proposal_url else None,
        'scope': {
            'packages': packs,
            'currency': (book or {}).get('currency') or '',
            'note': (book or {}).get('note') or (
                'Amounts appear only from the workspace price book. Empty means not priced.'
            ),
        },
        'next_step': step,
        'disclaimer': evidence_meta.get('disclaimer') or (
            'Observed gaps only. Not a claim that the business wants a new website. Not a revenue forecast.'
        ),
    }


def fictional_sample_report():
    """The public sample: real report template, labelled fictional, no invented prices."""
    lead = {
        'name': 'Harbour Street Bakery',
        'category': 'Bakery',
        'city': 'Sample city',
        'website': '',
        'email': '',
        'id': 'sample',
    }
    leaks = [
        {
            'id': 'no_form_or_booking',
            'title': 'No booking or enquiry path',
            'leak': 'Example: the page we read had no form, booking link, or enquiry path.',
            'fix': 'A single, visible enquiry or booking path above the fold on mobile.',
            'weight': 3, 'source': 'Example observation', 'commercial': True,
        },
        {
            'id': 'no_viewport',
            'title': 'Hard to use on a phone',
            'leak': 'Example: no viewport meta tag, so contact controls can be hard to tap.',
            'fix': 'A mobile-first layout with a visible tap target for the next step.',
            'weight': 2, 'source': 'Example observation', 'commercial': True,
        },
        {
            'id': 'thin_page',
            'title': 'Very little visible copy',
            'leak': 'Example: services may not be explained well enough to convert.',
            'fix': 'Clear service pages written from facts the business can confirm.',
            'weight': 1, 'source': 'Example observation', 'commercial': True,
        },
    ]
    report = {
        'score': 64,
        'priority': 'High',
        'qualified': True,
        'leak_count': 3,
        'leaks': leaks,
        'solution': {
            'name': 'A visible enquiry path on a page you own',
            'why': 'The example findings all point at one missing next step on mobile.',
            'note': 'Example only. This is not a quote and not a live audit.',
            'addresses': True,
            'addressed_count': 3,
        },
        'evidence': {
            'disclaimer': 'Fictional example. Format only. Not a live audit, not a revenue forecast, not proof anyone wants work.',
        },
        'created': '2026-10-07',
    }
    asset = compose_sales_asset(lead, report, prototype_url='/showcase/ember-coffee')
    return lead, report, asset


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


QUEUE_LIMIT = 12


def queue_leads(db, limit=QUEUE_LIMIT):
    """Next businesses worth a diagnosis: contactable first, listing leaks first.

    Skips Won / Not a fit. Skips a lead that already has a report unless a
    newer stored audit exists. Does not fetch the live web.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = QUEUE_LIMIT
    limit = max(1, min(limit, 15))
    where, args = _owner_clause('l')
    with db() as c:
        has_reports = bool(c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='opportunity_reports'"
        ).fetchone())
        has_audits = bool(c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='site_audits'"
        ).fetchone())
        if not has_reports:
            rows = c.execute(
                f'''SELECT l.* FROM leads l WHERE {where}
                    AND ifnull(l.stage,'') NOT IN ('Not a fit','Won')
                    ORDER BY CASE WHEN ifnull(l.email,'')!='' OR ifnull(l.phone,'')!='' THEN 0 ELSE 1 END,
                             l.updated DESC LIMIT ?''',
                (*args, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        audit_join = '''LEFT JOIN (
                SELECT lead_id, MAX(created) AS last_audit FROM site_audits GROUP BY lead_id
            ) a ON a.lead_id = l.id''' if has_audits else ''
        audit_fresh = '(a.last_audit IS NOT NULL AND a.last_audit > r.last_report)' if has_audits else '0'
        audit_rank = 'CASE WHEN a.last_audit IS NOT NULL THEN 0 ELSE 1 END,' if has_audits else ''
        rows = c.execute(
            f'''SELECT l.* FROM leads l
                LEFT JOIN (
                    SELECT lead_id, MAX(created) AS last_report
                    FROM opportunity_reports GROUP BY lead_id
                ) r ON r.lead_id = l.id
                {audit_join}
                WHERE {where}
                  AND ifnull(l.stage,'') NOT IN ('Not a fit','Won')
                  AND (r.last_report IS NULL OR {audit_fresh})
                ORDER BY
                  CASE WHEN ifnull(l.email,'')!='' OR ifnull(l.phone,'')!='' THEN 0 ELSE 1 END,
                  CASE WHEN ifnull(l.website,'')='' OR l.status IN ('SOCIAL_ONLY','NOT_LISTED') THEN 0 ELSE 1 END,
                  {audit_rank}
                  l.updated DESC
                LIMIT ?''',
            (*args, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def run_queue(db, now, log=None, limit=QUEUE_LIMIT):
    """Store diagnoses for the next queued leads from saved evidence only."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = QUEUE_LIMIT
    limit = max(1, min(limit, 15))
    leads = queue_leads(db, limit)
    saved = []
    for lead in leads:
        payload = build_report(db, lead, now, observe_live=False)
        row = save_report(db, lead, payload, now)
        saved.append({
            'id': row.get('id'),
            'token': row.get('token'),
            'lead_id': lead.get('id'),
            'lead_name': lead.get('name'),
            'score': row.get('score'),
            'priority': row.get('priority'),
            'leak_count': row.get('leak_count'),
            'contactable': bool((lead.get('email') or '').strip() or (lead.get('phone') or '').strip()),
        })
        if log:
            log('opportunity', f"Queue report for {lead.get('name')}: {row.get('score')}/100")
    return {
        'ran': len(saved),
        'limit': limit,
        'reports': saved,
        'note': 'Built from stored listings and audits only. Gap ranking is not revenue.',
    }


def serialize_row(row):
    data = dict(row)
    for key in ('leaks', 'solution', 'fit', 'evidence', 'outreach'):
        try:
            data[key] = json.loads(data.get(key) or '{}')
        except (TypeError, ValueError):
            data[key] = {}
    return data


def attach_latest(db, leads):
    """Stamp each lead dict with the latest stored report score and first leak title."""
    ids = [l.get('id') for l in (leads or []) if l.get('id')]
    if not ids:
        return leads
    q = ','.join('?' * len(ids))
    with db() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='opportunity_reports'").fetchone():
            return leads
        rows = c.execute(
            f'''SELECT r.lead_id, r.score, r.priority, r.leaks
                FROM opportunity_reports r
                JOIN (
                    SELECT lead_id, MAX(created) AS created
                    FROM opportunity_reports WHERE lead_id IN ({q})
                    GROUP BY lead_id
                ) x ON r.lead_id=x.lead_id AND r.created=x.created''',
            ids,
        ).fetchall()
    by = {}
    for row in rows:
        leaks = row['leaks']
        if isinstance(leaks, str):
            try:
                leaks = json.loads(leaks)
            except ValueError:
                leaks = []
        if not isinstance(leaks, list):
            leaks = []
        first = leaks[0] if leaks else {}
        by[row['lead_id']] = {
            'opp_score': row['score'],
            'opp_priority': row['priority'],
            'opp_leak': (first.get('title') or first.get('leak') or '') if isinstance(first, dict) else '',
        }
    for lead in leads:
        extra = by.get(lead.get('id'))
        if extra:
            lead.update(extra)
    return leads


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
                           l.website AS lead_website, l.stage AS lead_stage,
                           l.email AS lead_email, l.phone AS lead_phone
                    FROM opportunity_reports r
                    JOIN leads l ON l.id=r.lead_id
                    WHERE {where}
                    ORDER BY CASE r.priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
                             r.score DESC, r.created DESC LIMIT 80''',
                args,
            ).fetchall()
        out = []
        for row in rows:
            item = serialize_row(row)
            item['leaks'] = item['leaks'] if isinstance(item['leaks'], list) else []
            item['contactable'] = bool((item.get('lead_email') or '').strip() or (item.get('lead_phone') or '').strip())
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
        proto_url = prop_url = None
        book = {}
        try:
            from web.platform import price_book
            book = price_book(db)
        except Exception:
            book = {}
        with db() as c:
            prow = c.execute(
                'SELECT token FROM prototypes WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lid,)
            ).fetchone() if c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='prototypes'"
            ).fetchone() else None
            gprow = c.execute(
                'SELECT token FROM generated_proposals WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lid,)
            ).fetchone() if c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='generated_proposals'"
            ).fetchone() else None
        if prow:
            proto_url = f"/p/{prow['token']}"
        if gprow:
            prop_url = f"/proposal/{gprow['token']}"
        source = stored or preview
        asset = compose_sales_asset(lead, source, prototype_url=proto_url, proposal_url=prop_url, book=book)
        return jsonify(lead={k: lead.get(k) for k in ('id', 'name', 'city', 'category', 'website', 'stage', 'status', 'email')},
                       preview=preview, report=stored, sales_asset=asset)

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

    @app.get('/api/opportunity/work-first')
    def opportunity_work_first():
        queued = queue_leads(db, limit=8)
        attach_latest(db, queued)
        due = []
        try:
            from web.platform import due_memory
            due = due_memory(db, now())
        except Exception:
            due = []
        items = []
        seen = set()
        for row in due:
            lid = row.get('lead_id')
            if not lid or lid in seen:
                continue
            seen.add(lid)
            items.append({
                'id': lid,
                'name': row.get('lead_name') or '',
                'why': 'Follow-up is due',
                'action': 'Follow up',
                'follow_up_at': row.get('follow_up_at'),
                'reason': row.get('reason') or '',
            })
        for row in queued:
            lid = row.get('id')
            if not lid or lid in seen:
                continue
            seen.add(lid)
            items.append({
                'id': lid,
                'name': row.get('name') or '',
                'why': (
                    f"Stored score {row.get('opp_score')}/100"
                    if row.get('opp_score') is not None else 'Queued from stored listing evidence'
                ),
                'action': 'Draft' if row.get('email') else 'Audit',
                'score': row.get('opp_score'),
                'priority': row.get('opp_priority'),
            })
        return jsonify(items=items[:8])

    @app.post('/api/opportunity/run-queue')
    def opportunity_run_queue():
        body = request.get_json(silent=True) or {}
        try:
            limit = int(body.get('limit') or QUEUE_LIMIT)
        except (TypeError, ValueError):
            limit = QUEUE_LIMIT
        result = run_queue(db, now, log=log, limit=limit)
        return jsonify(result)

    @app.get('/sample-report')
    def sample_report_page():
        lead, report, asset = fictional_sample_report()
        try:
            from web.funnel import record as funnel_record
            funnel_record(db, now, 'sample_viewed')
        except Exception:
            pass
        return render_template('opportunity-report.html', report=report, lead=lead, asset=asset, sample=True)

    @app.get('/o/<token>')
    def opportunity_public(token):
        with db() as c:
            row = c.execute('SELECT * FROM opportunity_reports WHERE token=?', (token,)).fetchone()
            if not row:
                abort(404)
            c.execute('UPDATE opportunity_reports SET views=views+1 WHERE token=?', (token,))
            lead = c.execute('SELECT * FROM leads WHERE id=?', (row['lead_id'],)).fetchone()
        try:
            from web.funnel import record as funnel_record
            funnel_record(db, now, 'report_viewed', {'token': token})
        except Exception:
            pass
        report = serialize_row(row)
        lead = dict(lead) if lead else {}
        proto_url = prop_url = None
        book = {}
        try:
            from web.platform import price_book
            book = price_book(db)
        except Exception:
            book = {}
        if lead.get('id'):
            with db() as c:
                prow = c.execute(
                    'SELECT token FROM prototypes WHERE lead_id=? ORDER BY created DESC LIMIT 1',
                    (lead['id'],),
                ).fetchone() if c.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='prototypes'"
                ).fetchone() else None
                gprow = c.execute(
                    'SELECT token FROM generated_proposals WHERE lead_id=? ORDER BY created DESC LIMIT 1',
                    (lead['id'],),
                ).fetchone() if c.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='generated_proposals'"
                ).fetchone() else None
            if prow:
                proto_url = f"/p/{prow['token']}"
            if gprow:
                prop_url = f"/proposal/{gprow['token']}"
        asset = compose_sales_asset(lead, report, prototype_url=proto_url, proposal_url=prop_url, book=book)
        return render_template('opportunity-report.html', report=report, lead=lead, asset=asset)
