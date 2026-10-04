"""Reachmark platform layer — the replacement-resistant conversion system.

Sits on saved leads, measured audits, opportunity reports, projects and invoices.
Unknown factors stay unknown. Nothing is invented: ability to pay, competitor
page scores, funding news and response likelihood are recorded or absent.
"""
from __future__ import annotations

import json, secrets, uuid
from datetime import datetime, timezone, timedelta
from flask import jsonify, render_template, request, abort, session

from web.intelligence import _fit
from web.opportunity import (
    money_leaks, opportunity_score, qualify, recommend_solution, _latest_audit,
    build_report, save_report, _lead as _opp_lead,
)

MODES = ('manual', 'assisted', 'autopilot')
SIGNAL_KINDS = (
    'new_site', 'site_changed', 'hiring', 'funding', 'new_location', 'new_product',
    'new_executive', 'reviews_worsening', 'competitor_visibility', 'advertising',
    'tech_obsolete', 'operator_note',
)
MEMORY_KINDS = ('not_now', 'no_budget', 'has_site', 'timing', 'won', 'lost', 'reply', 'note')
POTENTIALS = ('high', 'medium', 'low', 'unknown')

OSM_TAGS = {
    'restaurant': ('amenity', 'restaurant'), 'cafe': ('amenity', 'cafe'), 'café': ('amenity', 'cafe'),
    'bakery': ('shop', 'bakery'), 'dentist': ('amenity', 'dentist'), 'clinic': ('amenity', 'clinic'),
    'lawyer': ('office', 'lawyer'), 'plumber': ('craft', 'plumber'), 'electrician': ('craft', 'electrician'),
    'hair': ('shop', 'hairdresser'), 'hotel': ('tourism', 'hotel'), 'gym': ('leisure', 'fitness_centre'),
    'pharmacy': ('amenity', 'pharmacy'), 'florist': ('shop', 'florist'),
}

CONV_KEYS = {'no_form_or_booking', 'no_contact_path', 'no_viewport', 'no_website_listed', 'social_only'}
TECH_KEYS = {'http_error', 'unreachable', 'dns_unresolved', 'parked_suspected', 'no_https', 'slow_first_byte', 'mixed_content'}
SEO_KEYS = {'missing_title', 'no_description', 'no_h1', 'thin_page'}


def ensure_tables(db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS revenue_rankings(
            lead_id TEXT PRIMARY KEY, score INTEGER NOT NULL, coverage INTEGER NOT NULL,
            factors TEXT NOT NULL, why TEXT NOT NULL, updated TEXT NOT NULL, owner_user_id TEXT
        );
        CREATE TABLE IF NOT EXISTS competitor_sets(
            id TEXT PRIMARY KEY, lead_id TEXT NOT NULL, city TEXT, category TEXT,
            rows TEXT NOT NULL, notes TEXT NOT NULL, created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS generated_proposals(
            id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, lead_id TEXT NOT NULL,
            report_id TEXT, packages TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL,
            views INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, updated TEXT NOT NULL,
            owner_user_id TEXT
        );
        CREATE TABLE IF NOT EXISTS price_books(
            id TEXT PRIMARY KEY, currency TEXT NOT NULL, packages TEXT NOT NULL,
            updated TEXT NOT NULL, owner_user_id TEXT
        );
        CREATE TABLE IF NOT EXISTS timing_signals(
            id TEXT PRIMARY KEY, lead_id TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL,
            source TEXT NOT NULL, source_url TEXT NOT NULL, observed_at TEXT NOT NULL,
            created TEXT NOT NULL, owner_user_id TEXT
        );
        CREATE TABLE IF NOT EXISTS lead_sources(
            id TEXT PRIMARY KEY, lead_id TEXT NOT NULL, source TEXT NOT NULL, source_url TEXT,
            fields TEXT NOT NULL, confidence INTEGER NOT NULL, seen_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS memory_events(
            id TEXT PRIMARY KEY, lead_id TEXT NOT NULL, kind TEXT NOT NULL, reason TEXT NOT NULL,
            potential TEXT NOT NULL, follow_up_at TEXT, note TEXT NOT NULL,
            created TEXT NOT NULL, owner_user_id TEXT
        );
        CREATE TABLE IF NOT EXISTS delivery_watches(
            id TEXT PRIMARY KEY, project_id TEXT, lead_id TEXT, invoice_id TEXT,
            findings TEXT NOT NULL, next_offer TEXT NOT NULL, started TEXT NOT NULL,
            updated TEXT NOT NULL, owner_user_id TEXT
        );
        CREATE TABLE IF NOT EXISTS market_briefs(
            id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, name TEXT NOT NULL, email TEXT,
            city TEXT, category TEXT, need TEXT NOT NULL, spec TEXT NOT NULL,
            status TEXT NOT NULL, created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS prototypes(
            id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, lead_id TEXT NOT NULL,
            review_token TEXT, concept TEXT NOT NULL, created TEXT NOT NULL, views INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS rankings_score ON revenue_rankings(score DESC);
        CREATE INDEX IF NOT EXISTS memory_follow ON memory_events(follow_up_at);
        CREATE INDEX IF NOT EXISTS signals_lead ON timing_signals(lead_id, created);
        ''')


def _owner_clause(alias=''):
    prefix = (alias + '.') if alias else ''
    cid = session.get('client_id') if session.get('role') == 'client' else None
    if cid:
        return prefix + 'owner_user_id=?', (cid,)
    return '1=1', ()


def _settings(db):
    with db() as c:
        row = c.execute('SELECT data FROM settings WHERE id=1').fetchone()
    data = json.loads(row[0]) if row else {}
    if not isinstance(data, dict):
        data = {}
    return data


def _save_settings(db, data):
    blob = json.dumps(data)
    with db() as c:
        exists = c.execute('SELECT id FROM settings WHERE id=1').fetchone()
        if exists:
            c.execute('UPDATE settings SET data=? WHERE id=1', (blob,))
        else:
            c.execute('INSERT INTO settings(id, data) VALUES(1,?)', (blob,))


def operator_mode(db):
    mode = (_settings(db).get('operator_mode') or 'assisted').strip().lower()
    return mode if mode in MODES else 'assisted'


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def _days_ago(stamp):
    dt = _parse_iso(stamp)
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


def _table(c, name):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _json(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or ('[]' if fallback == [] else '{}'))
    except (TypeError, ValueError):
        return fallback


def record_source(db, lead, extra=None):
    """Persist the listing source so the waterfall is visible, not implied."""
    source = (lead.get('source') or '').strip() or 'Unknown'
    url = (lead.get('source_url') or '').strip()
    fields = [k for k in ('name', 'city', 'category', 'phone', 'email', 'website', 'address') if (lead.get(k) or '').strip()]
    if extra:
        fields = sorted(set(fields + list(extra)))
    confidence = min(100, 20 + 10 * len(fields) + (15 if url else 0))
    stamp = lead.get('source_seen_at') or lead.get('updated') or lead.get('created')
    with db() as c:
        row = c.execute('SELECT id FROM lead_sources WHERE lead_id=? AND source=?', (lead['id'], source)).fetchone()
        if row:
            c.execute('UPDATE lead_sources SET source_url=?,fields=?,confidence=?,seen_at=? WHERE id=?',
                      (url, json.dumps(fields), confidence, stamp, row['id']))
        else:
            c.execute('INSERT INTO lead_sources VALUES(?,?,?,?,?,?,?)',
                      (uuid.uuid4().hex, lead['id'], source, url, json.dumps(fields), confidence, stamp))


def _closed_in_category(db, category, owner_id=None):
    if not (category or '').strip():
        return []
    cat = category.strip().lower()
    with db() as c:
        if not _table(c, 'invoices'):
            return []
        sql = '''SELECT i.currency, i.status, i.client_name, l.category
                 FROM invoices i LEFT JOIN leads l ON l.id=i.lead_id
                 WHERE lower(ifnull(l.category,''))=? AND i.status='Paid' LIMIT 8'''
        rows = [dict(r) for r in c.execute(sql, (cat,))]
        if _table(c, 'projects'):
            prows = c.execute(
                '''SELECT p.currency, p.quote_minor, p.stage, l.category
                   FROM projects p JOIN leads l ON l.id=p.lead_id
                   WHERE lower(ifnull(l.category,''))=? AND p.stage IN ('Delivered','Completed') LIMIT 8''',
                (cat,),
            )
            for r in prows:
                rows.append(dict(r))
    return rows


def score_lead(db, lead):
    """Priority ranking of who to work first. Unknown factors contribute 0."""
    audit = _latest_audit(db, lead['id'])
    leaks, packed = money_leaks(lead, audit)
    leak_ids = {item['id'] for item in leaks}
    fit = _fit(lead.get('category'))
    factors = []

    def add(fid, label, points, ceiling, state, evidence):
        factors.append({
            'id': fid, 'label': label, 'points': int(max(0, min(ceiling, points))),
            'max': ceiling, 'state': state, 'evidence': evidence,
        })

    listing_pts = 0
    bits = []
    for field, w in (('name', 2), ('city', 2), ('category', 2), ('address', 1)):
        if (lead.get(field) or '').strip():
            listing_pts += w
            bits.append(field)
    contact = bool((lead.get('email') or '').strip() or (lead.get('phone') or '').strip())
    if contact:
        listing_pts += 3
        bits.append('contact')
    add('listing', 'Listing completeness', listing_pts, 10, 'listing',
        ', '.join(bits) or 'Name only is missing — record is incomplete')

    website = (lead.get('website') or '').strip()
    status = lead.get('status') or ''
    audit_status = (audit or {}).get('status') or lead.get('audit_status') or ''
    if not website:
        add('website', 'Website observation', 16, 18, 'listing',
            'No owned URL on the listing. Not proof there is no site.')
    elif status == 'SOCIAL_ONLY':
        add('website', 'Website observation', 14, 18, 'listing', 'Listed URL is a social profile.')
    elif not audit and not audit_status:
        add('website', 'Website observation', 3, 18, 'unknown', 'No page check stored yet.')
    else:
        pts = 6 + min(12, sum(item['weight'] for item in leaks))
        add('website', 'Website observation', pts, 18, 'measured',
            f"Last check: {audit_status or 'recorded'}. {len(leaks)} observed gap(s).")

    tech = [i for i in leaks if i['id'] in TECH_KEYS]
    add('technical', 'Technical problems', min(12, 4 * len(tech) + sum(i['weight'] for i in tech)), 12,
        'measured' if (audit or tech) else 'unknown',
        ', '.join(i['title'] for i in tech) or ('None observed on the last check' if audit else 'No check'))

    seo = [i for i in leaks if i['id'] in SEO_KEYS]
    add('seo', 'SEO opportunity', min(10, 3 * len(seo) + sum(i['weight'] for i in seo)), 10,
        'measured' if (audit or seo) else 'unknown',
        ', '.join(i['title'] for i in seo) or ('None observed' if audit else 'No check'))

    conv = [i for i in leaks if i['id'] in CONV_KEYS]
    if audit:
        conv_state = 'measured'
        conv_ev = ', '.join(i['title'] for i in conv) or 'None observed'
    elif not website or status == 'SOCIAL_ONLY':
        conv_state = 'listing'
        conv_ev = ', '.join(i['title'] for i in conv) or 'No owned conversion page on the listing'
    else:
        conv_state = 'unknown'
        conv_ev = 'No check'
    add('conversion', 'Conversion weaknesses', min(14, 4 * len(conv) + sum(i['weight'] for i in conv)), 14,
        conv_state, conv_ev)

    with db() as c:
        signals = [dict(r) for r in c.execute(
            'SELECT * FROM timing_signals WHERE lead_id=? ORDER BY created DESC LIMIT 12', (lead['id'],))]
        memory = [dict(r) for r in c.execute(
            'SELECT * FROM memory_events WHERE lead_id=? ORDER BY created DESC LIMIT 12', (lead['id'],))]
        sources = [dict(r) for r in c.execute(
            'SELECT * FROM lead_sources WHERE lead_id=? ORDER BY seen_at DESC', (lead['id'],))]

    recent_signals = []
    for sig in signals:
        age = _days_ago(sig.get('observed_at') or sig.get('created'))
        if age is not None and age <= 45:
            recent_signals.append(sig)
    if recent_signals:
        add('timing', 'Buying-window signals', min(12, 6 * len(recent_signals)), 12, 'recorded',
            '; '.join(f"{s['kind']}: {s['detail'][:80]}" for s in recent_signals[:3]))
    else:
        add('timing', 'Buying-window signals', 0, 12, 'unknown',
            'None recorded. Add a sourced signal — do not invent news.')

    age = _days_ago(lead.get('updated') or lead.get('created'))
    if age is None:
        add('activity', 'Recent activity', 0, 6, 'unknown', 'No timestamp on the record.')
    elif age <= 7:
        add('activity', 'Recent activity', 6, 6, 'recorded', f'Record touched {age} day(s) ago.')
    elif age <= 30:
        add('activity', 'Recent activity', 3, 6, 'recorded', f'Record touched {age} day(s) ago.')
    else:
        add('activity', 'Recent activity', 1, 6, 'recorded', f'Record last touched {age} day(s) ago.')

    matched = (lead.get('category') or '').lower()
    known = any(k in matched for k in (
        'restaurant', 'cafe', 'café', 'dental', 'clinic', 'law', 'real estate', 'saas', 'finance',
        'bakery', 'salon', 'plumb', 'electric', 'hotel',
    ))
    add('fit', 'Fit with Reachmark services', 8 if known else 4, 8, 'listing',
        f"{fit['direction']} · goal: {fit['goal']}")

    stage = (lead.get('stage') or 'New').strip()
    stage_map = {
        'Replied': (12, 'They already replied. Stored stage, not a prediction.'),
        'Won': (0, 'Already a client (stage Won). Queue others first.'),
        'Contacted': (4, 'Already contacted. Follow the stored conversation.'),
        'Drafted': (7, 'Outreach drafted, not sent.'),
        'Not a fit': (0, 'Marked not a fit.'),
        'New': (8, 'Unworked. Reachability still unproven.'),
    }
    pts, ev = stage_map.get(stage, (5, f'Stage {stage} as stored.'))
    add('response', 'Likelihood of a conversation', pts, 12,
        'recorded' if stage != 'New' else 'listing', ev)

    pay_flag = next((m for m in memory if 'pay' in (m.get('reason') or '').lower() or m.get('kind') == 'no_budget'), None)
    closed = _closed_in_category(db, lead.get('category'))
    if pay_flag and pay_flag.get('kind') == 'no_budget':
        add('pay', 'Ability to pay', 0, 8, 'recorded', 'Operator recorded no budget / not now.')
    elif closed:
        add('pay', 'Ability to pay', 5, 8, 'recorded',
            f'{len(closed)} paid/completed job(s) in this category in this workspace — not a quote for this lead.')
    else:
        add('pay', 'Ability to pay', 0, 8, 'unknown',
            'No operator estimate and no closed job in this category. Left at zero.')

    score = min(100, sum(f['points'] for f in factors))
    known_n = sum(1 for f in factors if f['state'] != 'unknown')
    why_bits = [f['label'] + ': ' + f['evidence'] for f in sorted(factors, key=lambda x: -x['points'])[:3] if f['points']]
    why = ' · '.join(why_bits) if why_bits else 'Not enough stored evidence to rank this lead yet.'
    payload = {
        'score': score,
        'coverage': known_n,
        'coverage_of': len(factors),
        'factors': factors,
        'why': why,
        'leaks': leaks[:8],
        'opportunity_score': opportunity_score(leaks, lead),
        'qualified': qualify(lead, leaks, opportunity_score(leaks, lead)),
        'fit': fit,
        'solution': recommend_solution(leaks, lead),
        'audit_status': audit_status or 'NOT_ANALYZED',
        'sources': [{'source': s['source'], 'url': s.get('source_url'), 'confidence': s['confidence'],
                     'fields': _json(s.get('fields'), [])} for s in sources],
        'signals': [{'id': s['id'], 'kind': s['kind'], 'detail': s['detail'], 'source': s['source'],
                     'url': s.get('source_url'), 'observed_at': s.get('observed_at')} for s in signals],
        'memory': [{'id': m['id'], 'kind': m['kind'], 'reason': m['reason'], 'potential': m['potential'],
                    'follow_up_at': m.get('follow_up_at'), 'note': m.get('note'), 'created': m['created']} for m in memory],
    }
    return payload


def persist_rank(db, lead, payload, now):
    stamp = now()
    with db() as c:
        c.execute(
            '''INSERT INTO revenue_rankings(lead_id,score,coverage,factors,why,updated,owner_user_id)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(lead_id) DO UPDATE SET score=excluded.score,coverage=excluded.coverage,
                 factors=excluded.factors,why=excluded.why,updated=excluded.updated''',
            (lead['id'], payload['score'], payload['coverage'], json.dumps(payload['factors']),
             payload['why'][:800], stamp, lead.get('owner_user_id')),
        )
    payload['updated'] = stamp
    return payload


def workspace_peers(db, lead, limit=8):
    city = (lead.get('city') or '').strip().lower()
    cat = (lead.get('category') or '').strip().lower()
    if not city and not cat:
        return []
    with db() as c:
        rows = c.execute(
            '''SELECT id,name,city,category,website,status,stage,source,source_url FROM leads
               WHERE id!=? AND ( (?='' OR lower(ifnull(city,''))=? ) AND (?='' OR lower(ifnull(category,''))=? ) )
               ORDER BY updated DESC LIMIT ?''',
            (lead['id'], city, city, cat, cat, limit),
        ).fetchall()
    out = []
    for row in rows:
        peer = dict(row)
        audit = _latest_audit(db, peer['id'])
        leaks, _ = money_leaks(peer, audit)
        out.append({
            'lead_id': peer['id'], 'name': peer['name'], 'city': peer.get('city'),
            'category': peer.get('category'), 'website': peer.get('website') or '',
            'status': peer.get('status'), 'source': peer.get('source'),
            'source_url': peer.get('source_url'),
            'audited': bool(audit),
            'leak_ids': [i['id'] for i in leaks],
            'leak_titles': [i['title'] for i in leaks[:5]],
            'origin': 'workspace',
        })
    return out


def compare_gaps(prospect_leaks, peers):
    """Gaps on the prospect that audited peers did not show. Requires measured peers."""
    ours = {i['id']: i for i in prospect_leaks}
    audited = [p for p in peers if p.get('audited')]
    if not audited:
        return {
            'gaps': [],
            'note': 'No competitor in this set has a stored page check, so competitive gaps cannot be claimed.',
        }
    peer_keys = set()
    for p in audited:
        peer_keys |= set(p.get('leak_ids') or [])
    unique = []
    for key, item in ours.items():
        if key not in peer_keys:
            unique.append({'id': key, 'title': item.get('title'), 'leak': item.get('leak')})
    return {
        'gaps': unique[:6],
        'note': f'Compared against {len(audited)} audited peer(s) in this workspace. Unaudited listings are ignored.',
    }


def live_city_scan(lead, limit=8):
    """Bounded OSM scan. Returns listing rows only — no invented scores."""
    city = (lead.get('city') or '').strip()
    cat = (lead.get('category') or '').strip().lower()
    if not city:
        return [], 'A city on the lead is required before a live competitor scan.'
    tag = None
    for key, osm in OSM_TAGS.items():
        if key in cat:
            tag = osm
            break
    if not tag:
        return [], f'No OpenStreetMap tag mapped for category “{lead.get("category") or "blank"}”. Saved peers only.'
    try:
        from web.services import discover_location
        rows, place = discover_location(city, tag, limit=limit)
    except Exception as exc:
        return [], f'Live scan did not complete ({type(exc).__name__}). Workspace peers still apply.'
    out = []
    pname = (lead.get('name') or '').strip().lower()
    for row in rows:
        if (row.get('name') or '').strip().lower() == pname:
            continue
        out.append({
            'lead_id': None, 'name': row.get('name'), 'city': row.get('city'),
            'category': lead.get('category'), 'website': row.get('website') or '',
            'status': 'HAS_WEBSITE' if (row.get('website') or '').strip() else 'NOT_LISTED',
            'source': row.get('source') or 'OpenStreetMap',
            'source_url': row.get('source_url'),
            'audited': False, 'leak_ids': [], 'leak_titles': [],
            'origin': 'osm',
        })
    return out[:limit], (place or city)


def price_book(db):
    with db() as c:
        row = c.execute('SELECT * FROM price_books ORDER BY updated DESC LIMIT 1').fetchone()
    if not row:
        return {
            'currency': '',
            'packages': [
                {'id': 'basic', 'name': 'Basic implementation', 'amount': None,
                 'includes': ['Mobile-first homepage', 'One enquiry path', 'Contact details the business confirms']},
                {'id': 'growth', 'name': 'Growth implementation', 'amount': None,
                 'includes': ['Service pages', 'Enquiry or booking path', 'On-page SEO basics', 'Analytics install']},
                {'id': 'advanced', 'name': 'Advanced implementation', 'amount': None,
                 'includes': ['Full site IA', 'Automation on the enquiry path', 'CMS training', '30-day care']},
            ],
            'note': 'Amounts stay empty until you set a price book. Closed jobs in this workspace can inform, not invent, a number.',
            'history': [],
        }
    data = dict(row)
    data['packages'] = _json(data.get('packages'), [])
    return data


def packages_for(lead, leaks, book):
    ids = {i['id'] for i in leaks}
    packs = []
    for pack in book.get('packages') or []:
        item = dict(pack)
        if pack.get('id') == 'basic':
            item['why'] = 'Fixes the first conversion leak on a phone.'
        elif pack.get('id') == 'growth':
            item['why'] = 'Covers conversion plus the search and service-page gaps we actually recorded.'
        else:
            item['why'] = 'For businesses where several commercial leaks were observed, or no owned site is listed.'
        if not ids and pack.get('id') != 'basic':
            item['caution'] = 'Few or no leaks recorded — do not upsell on empty evidence.'
        packs.append(item)
    return packs


def build_proposal_body(lead, report, packs, prototype, fit):
    leaks = report.get('leaks') or []
    evidence = report.get('evidence') or {}
    solution = report.get('solution') or {}
    return {
        'business': {'name': lead.get('name'), 'city': lead.get('city'), 'category': lead.get('category'),
                     'website': lead.get('website')},
        'problems': [{'title': i.get('title'), 'leak': i.get('leak'), 'source': i.get('source')} for i in leaks],
        'evidence': evidence,
        'solution': solution,
        'fit': fit,
        'packages': packs,
        'objectives': [
            f"Typical goal for this category: {fit.get('goal')}. Not a promised result.",
            'Confirm every objective with the business before a contract.',
        ],
        'timeline': [
            {'id': 'basic', 'weeks': 2},
            {'id': 'growth', 'weeks': 4},
            {'id': 'advanced', 'weeks': 8},
        ],
        'prototype': prototype,
        'terms': 'This is a draft diagnosis-to-scope note, not a contract and not a quote until amounts are set and accepted.',
        'disclaimer': 'Every problem listed was observed on a listing field or a measured page check. Empty sections stay empty.',
    }


def inferred_timing(db, lead):
    """Signals derived only from stored audits / stage — never from the news."""
    out = []
    with db() as c:
        if not _table(c, 'site_audits'):
            return out
        rows = [dict(r) for r in c.execute(
            'SELECT url,status,created FROM site_audits WHERE lead_id=? ORDER BY created DESC LIMIT 4',
            (lead['id'],))]
    if len(rows) >= 2:
        a, b = rows[0], rows[1]
        if (a.get('url') or '') != (b.get('url') or ''):
            out.append({'kind': 'site_changed', 'detail': 'Listed URL differed between two stored checks.',
                        'source': 'site_audits', 'observed_at': a.get('created')})
        if (a.get('status') or '') != (b.get('status') or '') and a.get('status') == 'LIVE' and b.get('status') not in ('LIVE', None, ''):
            out.append({'kind': 'new_site', 'detail': f"Status moved {b.get('status')} → LIVE on a stored check.",
                        'source': 'site_audits', 'observed_at': a.get('created')})
    with db() as c:
        if _table(c, 'review_responses'):
            later = c.execute(
                "SELECT created FROM review_responses WHERE lead_id=? AND choice='later' ORDER BY created DESC LIMIT 1",
                (lead['id'],)).fetchone()
            if later:
                out.append({'kind': 'operator_note', 'detail': 'They answered “not right now” on a concept page.',
                            'source': 'review_responses', 'observed_at': later['created']})
    return out


def due_memory(db, now_iso):
    today = (now_iso or '')[:10]
    cid = session.get('client_id') if session.get('role') == 'client' else None
    sql = '''SELECT m.*, l.name AS lead_name, l.city AS lead_city, l.stage AS lead_stage
             FROM memory_events m JOIN leads l ON l.id=m.lead_id
             WHERE m.follow_up_at IS NOT NULL AND m.follow_up_at<=?'''
    args = [today]
    if cid:
        sql += ' AND m.owner_user_id=?'
        args.append(cid)
    sql += ' ORDER BY m.follow_up_at ASC LIMIT 40'
    with db() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def delivery_snapshot(db):
    where, args = _owner_clause()
    watches = []
    with db() as c:
        projects = []
        if _table(c, 'projects'):
            projects = [dict(r) for r in c.execute(
                '''SELECT p.*, l.name AS lead_name, l.category AS lead_category, l.website AS lead_website
                   FROM projects p LEFT JOIN leads l ON l.id=p.lead_id
                   WHERE p.stage IN ('Delivered','Completed','In progress')
                   ORDER BY p.updated DESC LIMIT 40''').fetchall()]
        invoices = []
        if _table(c, 'invoices'):
            invoices = [dict(r) for r in c.execute(
                "SELECT * FROM invoices WHERE status='Paid' ORDER BY updated DESC LIMIT 20").fetchall()]
        stored = [dict(r) for r in c.execute('SELECT * FROM delivery_watches ORDER BY updated DESC LIMIT 40')]
    return {
        'projects': [{'id': p['id'], 'title': p.get('title'), 'stage': p.get('stage'),
                      'lead_id': p.get('lead_id'), 'lead_name': p.get('lead_name'),
                      'next_action': p.get('next_action')} for p in projects],
        'paid_invoices': len(invoices),
        'watches': [{'id': w['id'], 'lead_id': w.get('lead_id'), 'next_offer': w.get('next_offer'),
                     'findings': _json(w.get('findings'), []), 'updated': w.get('updated')} for w in stored],
        'note': 'Watch items exist only for projects and paid invoices on record. Empty means no delivery yet.',
    }


def refresh_delivery(db, now):
    """For delivered projects, re-read stored audits and name the next observed offer."""
    stamp = now()
    created = 0
    with db() as c:
        if not _table(c, 'projects'):
            return 0
        rows = c.execute(
            "SELECT * FROM projects WHERE stage IN ('Delivered','Completed') AND lead_id IS NOT NULL AND lead_id!=''"
        ).fetchall()
    for row in rows:
        project = dict(row)
        lead = _opp_lead(db, project['lead_id'])
        if not lead:
            continue
        audit = _latest_audit(db, lead['id'])
        leaks, _ = money_leaks(lead, audit)
        commercial = [i for i in leaks if i.get('commercial')]
        if commercial:
            offer = commercial[0]['fix']
            findings = [{'title': i['title'], 'source': i['source']} for i in commercial[:5]]
        else:
            offer = 'No new commercial leak on the last check. Retention only — do not invent an upsell.'
            findings = []
        with db() as c:
            existing = c.execute('SELECT id FROM delivery_watches WHERE project_id=?', (project['id'],)).fetchone()
            blob_f, blob_o = json.dumps(findings), offer[:400]
            if existing:
                c.execute('UPDATE delivery_watches SET findings=?,next_offer=?,updated=? WHERE id=?',
                          (blob_f, blob_o, stamp, existing['id']))
            else:
                c.execute(
                    'INSERT INTO delivery_watches VALUES(?,?,?,?,?,?,?,?,?)',
                    (uuid.uuid4().hex, project['id'], lead['id'], None, blob_f, blob_o, stamp, stamp,
                     lead.get('owner_user_id')),
                )
                created += 1
    return created


def market_spec(name, category, city, need):
    fit = _fit(category)
    return {
        'name': name, 'category': category, 'city': city,
        'direction': fit['direction'], 'goal': fit['goal'],
        'pages': fit['pages'], 'modules': fit['modules'],
        'need': need,
        'note': 'This specification is a starting brief from the category, not a signed scope.',
    }


def _lead(db, lid):
    return _opp_lead(db, lid)


def register_platform(app, db, now, log):
    ensure_tables(db)

    @app.get('/api/platform/state')
    def platform_state():
        mode = operator_mode(db)
        where, args = _owner_clause()
        with db() as c:
            def n(sql, extra=()):
                return c.execute(sql, args + extra).fetchone()[0]
            leads = n(f'SELECT count(*) FROM leads WHERE {where}')
            ranked = n(f'SELECT count(*) FROM revenue_rankings WHERE {where}') if _table(c, 'revenue_rankings') else 0
            proposals = n(f'SELECT count(*) FROM generated_proposals WHERE {where}') if _table(c, 'generated_proposals') else 0
            briefs = c.execute("SELECT count(*) FROM market_briefs WHERE status!='closed'").fetchone()[0]
            due = c.execute(
                "SELECT count(*) FROM memory_events WHERE follow_up_at IS NOT NULL AND follow_up_at<=?",
                (now()[:10],),
            ).fetchone()[0]
            prototypes = c.execute('SELECT count(*) FROM prototypes').fetchone()[0]
        book = price_book(db)
        priced = any((p.get('amount') not in (None, '', 0) for p in book.get('packages') or []))
        return jsonify(
            mode=mode,
            counts={'leads': leads, 'ranked': ranked, 'proposals': proposals, 'briefs': briefs,
                    'due_memory': due, 'prototypes': prototypes},
            price_book_set=priced,
            disclaimer='Counts are live SQL totals. Empty workspaces stay at zero.',
        )

    @app.post('/api/platform/mode')
    def platform_mode():
        body = request.get_json(silent=True) or {}
        mode = str(body.get('mode') or '').strip().lower()
        if mode not in MODES:
            return jsonify(error='Mode must be manual, assisted or autopilot.'), 400
        data = _settings(db)
        data['operator_mode'] = mode
        _save_settings(db, data)
        log('platform', f'Operator mode set to {mode}')
        return jsonify(mode=mode)

    @app.get('/api/platform/queue')
    def platform_queue():
        where, args = _owner_clause('l')
        with db() as c:
            rows = c.execute(
                f'''SELECT l.id,l.name,l.city,l.category,l.website,l.stage,l.status,l.email,l.phone,
                           r.score,r.coverage,r.why,r.updated AS ranked_at
                    FROM leads l LEFT JOIN revenue_rankings r ON r.lead_id=l.id
                    WHERE {where}
                    ORDER BY CASE WHEN r.score IS NULL THEN 1 ELSE 0 END, r.score DESC, l.updated DESC
                    LIMIT 50''',
                args,
            ).fetchall()
        items = []
        for row in rows:
            d = dict(row)
            d['reachable'] = bool((d.get('email') or '').strip() or (d.get('phone') or '').strip())
            items.append(d)
        return jsonify(
            items=items, count=len(items),
            disclaimer='Ranked from stored evidence. Unscored leads sit at the bottom until you refresh.',
        )

    @app.post('/api/platform/queue/refresh')
    def platform_refresh():
        where, args = _owner_clause()
        with db() as c:
            leads = [dict(r) for r in c.execute(
                f'SELECT * FROM leads WHERE {where} ORDER BY updated DESC LIMIT 200', args)]
        scored = 0
        for lead in leads:
            record_source(db, lead)
            payload = persist_rank(db, lead, score_lead(db, lead), now)
            scored += 1 if payload else 0
        log('platform', f'Rescored {scored} lead(s) from stored evidence')
        return jsonify(scored=scored)

    @app.get('/api/platform/lead/<lid>')
    def platform_lead(lid):
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        payload = score_lead(db, lead)
        peers = workspace_peers(db, lead)
        comparison = compare_gaps(payload.get('leaks') or [], peers)
        with db() as c:
            proto = c.execute('SELECT * FROM prototypes WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lid,)).fetchone()
            prop = c.execute('SELECT * FROM generated_proposals WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lid,)).fetchone()
            cset = c.execute('SELECT * FROM competitor_sets WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lid,)).fetchone()
        return jsonify(
            lead={k: lead.get(k) for k in ('id', 'name', 'city', 'category', 'website', 'stage', 'status', 'email', 'phone', 'source', 'source_url')},
            ranking=payload,
            peers=peers,
            comparison=comparison,
            inferred_timing=inferred_timing(db, lead),
            prototype=dict(proto) if proto else None,
            proposal={'id': prop['id'], 'token': prop['token'], 'created': prop['created']} if prop else None,
            competitor_set=_json(cset['rows'], []) if cset else [],
        )

    @app.post('/api/platform/lead/<lid>/score')
    def platform_score_one(lid):
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        record_source(db, lead)
        payload = persist_rank(db, lead, score_lead(db, lead), now)
        return jsonify(ranking=payload)

    @app.post('/api/platform/lead/<lid>/competitors')
    def platform_competitors(lid):
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        live = bool((request.get_json(silent=True) or {}).get('live'))
        peers = workspace_peers(db, lead)
        note = 'Workspace peers in the same city and category.'
        osm_rows = []
        if live:
            osm_rows, place = live_city_scan(lead, limit=8)
            note = f'Workspace peers plus a bounded OpenStreetMap scan around {place}.'
        rows = peers + osm_rows
        seen = set()
        uniq = []
        for row in rows:
            key = (row.get('name') or '').strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            uniq.append(row)
        leaks, _ = money_leaks(lead, _latest_audit(db, lead['id']))
        comparison = compare_gaps(leaks, uniq)
        sid = uuid.uuid4().hex
        with db() as c:
            c.execute('INSERT INTO competitor_sets VALUES(?,?,?,?,?,?,?)',
                      (sid, lead['id'], lead.get('city'), lead.get('category'),
                       json.dumps(uniq)[:80000], comparison['note'], now()))
        return jsonify(id=sid, rows=uniq, comparison=comparison, note=note)

    @app.post('/api/platform/lead/<lid>/prototype')
    def platform_prototype(lid):
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        settings = _settings(db)
        review_token = ''
        concept = {}
        try:
            from agents.agent_builder import compose_concept
            from web.review_links import create_link
            concept = compose_concept(lead, settings)
            link = create_link(db, now, lead, concept, f"Concept for {lead.get('name')}")
            review_token = (link or {}).get('token') or ''
        except Exception:
            concept = {'headline': f"{lead.get('name') or 'This business'} — a clearer first section.",
                       'intro': 'Independent concept from saved listing fields. Missing facts stay missing.',
                       'sections': []}
        audit = _latest_audit(db, lead['id'])
        leaks, _ = money_leaks(lead, audit)
        concept['leaks'] = [{'title': i['title'], 'leak': i['leak'], 'fix': i['fix']} for i in leaks[:5]]
        concept['disclaimer'] = (
            'Independent first-section concept prepared by Reachmark. '
            'It is not their live website and not a claim they asked for this work.'
        )
        token = secrets.token_urlsafe(16)
        pid = uuid.uuid4().hex
        with db() as c:
            c.execute('INSERT INTO prototypes VALUES(?,?,?,?,?,?,0)',
                      (pid, token, lead['id'], review_token, json.dumps(concept)[:40000], now()))
        log('platform', f'Prototype stored for {lead.get("name")}')
        return jsonify(id=pid, token=token, url=f'/p/{token}', review=f'/r/{review_token}' if review_token else '')

    @app.post('/api/platform/lead/<lid>/proposal')
    def platform_proposal(lid):
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        report_row = None
        with db() as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='opportunity_reports'").fetchone():
                report_row = c.execute(
                    'SELECT * FROM opportunity_reports WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lid,)
                ).fetchone()
        if report_row:
            from web.opportunity import serialize_row
            report = serialize_row(report_row)
        else:
            built = build_report(db, lead, now, observe_live=False)
            saved = save_report(db, lead, built, now)
            report = saved
        book = price_book(db)
        packs = packages_for(lead, report.get('leaks') or [], book)
        proto = None
        with db() as c:
            prow = c.execute('SELECT token FROM prototypes WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lid,)).fetchone()
            if prow:
                proto = {'url': f"/p/{prow['token']}"}
        body = build_proposal_body(lead, report, packs, proto, report.get('fit') or _fit(lead.get('category')))
        token = secrets.token_urlsafe(16)
        pid = uuid.uuid4().hex
        stamp = now()
        with db() as c:
            c.execute(
                '''INSERT INTO generated_proposals
                   (id,token,lead_id,report_id,packages,body,status,views,created,updated,owner_user_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                (pid, token, lead['id'], report.get('id'), json.dumps(packs), json.dumps(body),
                 'draft', 0, stamp, stamp, lead.get('owner_user_id')),
            )
        log('platform', f'Proposal drafted for {lead.get("name")}')
        return jsonify(id=pid, token=token, url=f'/proposal/{token}', body=body)

    @app.post('/api/platform/lead/<lid>/memory')
    def platform_memory(lid):
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        body = request.get_json(silent=True) or {}
        kind = str(body.get('kind') or 'note').strip()
        if kind not in MEMORY_KINDS:
            return jsonify(error='Unknown memory kind.'), 400
        potential = str(body.get('potential') or 'unknown').strip().lower()
        if potential not in POTENTIALS:
            potential = 'unknown'
        reason = str(body.get('reason') or '').strip()[:400]
        note = str(body.get('note') or '').strip()[:2000]
        follow = str(body.get('follow_up_at') or '').strip()[:10] or None
        if kind == 'not_now' and not follow:
            follow = (datetime.now(timezone.utc) + timedelta(days=90)).date().isoformat()
        if not reason:
            return jsonify(error='Record why. Empty reasons are not stored.'), 400
        mid = uuid.uuid4().hex
        with db() as c:
            c.execute('INSERT INTO memory_events VALUES(?,?,?,?,?,?,?,?,?)',
                      (mid, lead['id'], kind, reason, potential, follow, note, now(), lead.get('owner_user_id')))
        return jsonify(id=mid, follow_up_at=follow)

    @app.post('/api/platform/lead/<lid>/signal')
    def platform_signal(lid):
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        body = request.get_json(silent=True) or {}
        kind = str(body.get('kind') or '').strip()
        if kind not in SIGNAL_KINDS:
            return jsonify(error='Unknown signal kind.'), 400
        detail = str(body.get('detail') or '').strip()[:500]
        source = str(body.get('source') or '').strip()[:200]
        url = str(body.get('source_url') or '').strip()[:500]
        if len(detail) < 12 or not source:
            return jsonify(error='A sourced detail is required. Do not log unsourced rumours.'), 400
        sid = uuid.uuid4().hex
        observed = str(body.get('observed_at') or now())[:40]
        with db() as c:
            c.execute('INSERT INTO timing_signals VALUES(?,?,?,?,?,?,?,?,?)',
                      (sid, lead['id'], kind, detail, source, url, observed, now(), lead.get('owner_user_id')))
        persist_rank(db, lead, score_lead(db, lead), now)
        return jsonify(id=sid)

    @app.get('/api/platform/memory/due')
    def platform_due():
        rows = due_memory(db, now())
        return jsonify(items=rows, count=len(rows))

    @app.get('/api/platform/prices')
    def platform_prices_get():
        book = price_book(db)
        book['history_note'] = 'Closed jobs in a category can be shown on a proposal as workspace history, never as this lead’s quote.'
        return jsonify(book)

    @app.post('/api/platform/prices')
    def platform_prices_set():
        body = request.get_json(silent=True) or {}
        currency = str(body.get('currency') or '').strip().upper()[:8]
        packages = body.get('packages')
        if not isinstance(packages, list) or not packages:
            return jsonify(error='packages array required'), 400
        clean = []
        for p in packages[:5]:
            if not isinstance(p, dict):
                continue
            amount = p.get('amount')
            if amount in ('', None):
                amount = None
            else:
                try:
                    amount = int(amount)
                except (TypeError, ValueError):
                    return jsonify(error='Amount must be a whole number in minor units, or empty.'), 400
            includes = p.get('includes') if isinstance(p.get('includes'), list) else []
            clean.append({
                'id': str(p.get('id') or uuid.uuid4().hex)[:32],
                'name': str(p.get('name') or 'Package')[:80],
                'amount': amount,
                'includes': [str(x)[:120] for x in includes[:8]],
            })
        owner = session.get('client_id') if session.get('role') == 'client' else None
        with db() as c:
            row = c.execute('SELECT id FROM price_books ORDER BY updated DESC LIMIT 1').fetchone()
            blob = json.dumps(clean)
            if row:
                c.execute('UPDATE price_books SET currency=?,packages=?,updated=? WHERE id=?',
                          (currency, blob, now(), row['id']))
                pid = row['id']
            else:
                pid = uuid.uuid4().hex
                c.execute('INSERT INTO price_books VALUES(?,?,?,?,?)', (pid, currency, blob, now(), owner))
        log('platform', 'Price book updated')
        return jsonify(id=pid, currency=currency, packages=clean)

    @app.get('/api/platform/delivery')
    def platform_delivery():
        return jsonify(delivery_snapshot(db))

    @app.post('/api/platform/delivery/refresh')
    def platform_delivery_refresh():
        n = refresh_delivery(db, now)
        return jsonify(updated=n, **delivery_snapshot(db))

    @app.get('/api/platform/market')
    def platform_market():
        with db() as c:
            rows = [dict(r) for r in c.execute(
                'SELECT id,token,name,email,city,category,need,status,created FROM market_briefs ORDER BY created DESC LIMIT 50')]
        return jsonify(briefs=rows, count=len(rows))

    @app.post('/api/platform/autopilot/tick')
    def platform_tick():
        mode = operator_mode(db)
        if mode != 'autopilot':
            return jsonify(error='Autopilot is off. Switch mode to autopilot to run a tick.', mode=mode), 400
        where, args = _owner_clause()
        actions = []
        with db() as c:
            leads = [dict(r) for r in c.execute(
                f'SELECT * FROM leads WHERE {where} ORDER BY updated DESC LIMIT 40', args)]
        for lead in leads:
            record_source(db, lead)
            persist_rank(db, lead, score_lead(db, lead), now)
        actions.append(f'scored {len(leads)} leads')
        with db() as c:
            top = [dict(r) for r in c.execute(
                '''SELECT l.* FROM leads l JOIN revenue_rankings r ON r.lead_id=l.id
                   WHERE r.score>=40 ORDER BY r.score DESC LIMIT 5''')]
        for lead in top:
            with db() as c:
                has = c.execute('SELECT id FROM opportunity_reports WHERE lead_id=? LIMIT 1', (lead['id'],)).fetchone()
            if not has:
                saved = save_report(db, lead, build_report(db, lead, now, observe_live=False), now)
                actions.append(f"report {lead.get('name')} {saved['score']}")
            with db() as c:
                proto = c.execute('SELECT id FROM prototypes WHERE lead_id=? LIMIT 1', (lead['id'],)).fetchone()
            if not proto and mode == 'autopilot':
                # Prototypes still need an explicit operator in manual/assisted; autopilot may prepare them.
                try:
                    from agents.agent_builder import compose_concept
                    concept = compose_concept(lead, _settings(db))
                except Exception:
                    concept = {'headline': lead.get('name') or 'Concept', 'sections': []}
                token = secrets.token_urlsafe(16)
                with db() as c:
                    c.execute('INSERT INTO prototypes VALUES(?,?,?,?,?,?,0)',
                              (uuid.uuid4().hex, token, lead['id'], '', json.dumps(concept)[:40000], now()))
                actions.append(f"prototype {lead.get('name')}")
        log('platform', 'Autopilot tick: ' + '; '.join(actions)[:400])
        return jsonify(mode=mode, actions=actions, sent=0, note='Autopilot never sends. Humans still approve outreach.')

    @app.post('/api/need')
    def public_need():
        body = request.get_json(silent=True) or request.form or {}
        name = str(body.get('name') or '').strip()[:120]
        email = str(body.get('email') or '').strip()[:200]
        city = str(body.get('city') or '').strip()[:120]
        category = str(body.get('category') or '').strip()[:80]
        need = str(body.get('need') or '').strip()[:2000]
        if len(name) < 2 or len(need) < 20:
            return jsonify(error='Name and a short description of what you need are required.'), 400
        spec = market_spec(name, category, city, need)
        token = secrets.token_urlsafe(12)
        bid = uuid.uuid4().hex
        with db() as c:
            c.execute('INSERT INTO market_briefs VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (bid, token, name, email, city, category, need, json.dumps(spec), 'new', now()))
        log('market', f'Brief from {name}')
        return jsonify(ok=True, token=token, url=f'/brief/{token}')

    @app.get('/need')
    def need_page():
        return render_template('need.html')

    @app.get('/brief/<token>')
    def brief_public(token):
        with db() as c:
            row = c.execute('SELECT * FROM market_briefs WHERE token=?', (token,)).fetchone()
        if not row:
            abort(404)
        data = dict(row)
        data['spec'] = _json(data.get('spec'), {})
        return render_template('brief.html', brief=data)

    @app.get('/proposal/<token>')
    def proposal_public(token):
        with db() as c:
            row = c.execute('SELECT * FROM generated_proposals WHERE token=?', (token,)).fetchone()
            if not row:
                abort(404)
            c.execute('UPDATE generated_proposals SET views=views+1 WHERE token=?', (token,))
            lead = c.execute('SELECT * FROM leads WHERE id=?', (row['lead_id'],)).fetchone()
        prop = dict(row)
        prop['body'] = _json(prop.get('body'), {})
        prop['packages'] = _json(prop.get('packages'), [])
        return render_template('proposal-doc.html', proposal=prop, lead=dict(lead) if lead else {})

    @app.get('/p/<token>')
    def prototype_public(token):
        with db() as c:
            row = c.execute('SELECT * FROM prototypes WHERE token=?', (token,)).fetchone()
            if not row:
                abort(404)
            c.execute('UPDATE prototypes SET views=views+1 WHERE token=?', (token,))
            lead = c.execute('SELECT * FROM leads WHERE id=?', (row['lead_id'],)).fetchone()
        proto = dict(row)
        proto['concept'] = _json(proto.get('concept'), {})
        return render_template('prototype.html', proto=proto, lead=dict(lead) if lead else {})
