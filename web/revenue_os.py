"""Reachmark Revenue OS — one machine, not another dashboard.

Canonical objects, each with its own state and timestamps:

    Lead → Opportunity → Conversation → Proposal → Contract → Project
         → Invoice → Paid → Delivered → Result → Retention

Nothing here invents a forecast. Gap scores stay gap scores. A project is never
counted as a proposal. A reply is classified from its text, then a human still
approves the next send.
"""
from __future__ import annotations

import json, re, uuid
from flask import jsonify, request, session

INTENTS = (
    ('unsubscribe', ('unsubscribe', 'opt out', 'stop emailing', 'remove me', 'do not contact')),
    ('not_interested', ('not interested', 'no thanks', 'no thank you', 'leave me alone', 'go away')),
    ('not_now', ('not now', 'not right now', 'maybe later', 'next year', 'after the season', 'too busy')),
    ('wrong_person', ('wrong person', 'not the owner', 'no longer work', 'wrong email')),
    ('has_provider', ('already have a', 'we have an agency', 'already working with', 'our developer')),
    ('pricing', ('how much', 'what would it cost', 'pricing', 'price', 'quote', 'cost')),
    ('wants_proposal', ('send a proposal', 'send the proposal', 'scope of work', 'formal proposal')),
    ('wants_meeting', ('book a call', 'schedule', 'let’s talk', 'lets talk', 'meeting', 'zoom', 'call me')),
    ('wants_changes', ('change this', 'tweak', 'different colour', 'can you edit', 'revise')),
    ('interested', ('interested', 'tell me more', 'this looks useful', 'let’s do it', 'lets do it', 'yes please')),
    ('question', ('how does', 'what is', 'can you', 'could you', '?')),
)

ACTIONS = {
    'unsubscribe': 'suppress',
    'not_interested': 'close',
    'not_now': 'park_90_days',
    'wrong_person': 'ask_for_right_person',
    'has_provider': 'park_90_days',
    'pricing': 'send_proposal',
    'wants_proposal': 'send_proposal',
    'wants_meeting': 'schedule',
    'wants_changes': 'revise_concept',
    'interested': 'send_proposal',
    'question': 'reply',
    'unknown': 'review',
}

FUNNEL = (
    ('lead', 'Lead', 'Saved businesses'),
    ('opportunity', 'Opportunity', 'Canonical opportunity rows (from a stored report)'),
    ('conversation', 'Conversation', 'Inbound threads with at least one recorded message or Replied stage'),
    ('proposal', 'Proposal', 'Rows in generated_proposals — not projects, not contracts'),
    ('contract', 'Contract', 'Contract records'),
    ('project', 'Project', 'Project board rows'),
    ('invoice', 'Invoice', 'Invoice records'),
    ('paid', 'Paid', 'Invoices with status Paid'),
    ('delivered', 'Delivered', 'Projects in Delivered or Completed'),
    ('result', 'Result', 'Post-delivery observations stored as results'),
    ('retained', 'Retention', 'Growth offers on delivered work'),
)


def ensure_tables(db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS revenue_opportunities(
            id TEXT PRIMARY KEY,
            lead_id TEXT UNIQUE NOT NULL,
            report_id TEXT,
            gap_score INTEGER,
            work_score INTEGER,
            priority TEXT,
            state TEXT NOT NULL,
            problem_severity INTEGER,
            fit INTEGER,
            contactability INTEGER,
            commercial_readiness INTEGER,
            buying_signals INTEGER,
            evidence_confidence INTEGER,
            why TEXT NOT NULL,
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            opened_at TEXT,
            qualified_at TEXT,
            conversing_at TEXT,
            proposed_at TEXT,
            won_at TEXT,
            lost_at TEXT,
            owner_user_id TEXT
        );
        CREATE TABLE IF NOT EXISTS revenue_conversations(
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            opportunity_id TEXT,
            state TEXT NOT NULL,
            last_intent TEXT,
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            owner_user_id TEXT
        );
        CREATE TABLE IF NOT EXISTS revenue_messages(
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            lead_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            channel TEXT NOT NULL,
            body TEXT NOT NULL,
            intent TEXT,
            suggested_response TEXT,
            suggested_action TEXT,
            source TEXT NOT NULL,
            created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS revenue_results(
            id TEXT PRIMARY KEY,
            lead_id TEXT,
            project_id TEXT,
            kind TEXT NOT NULL,
            detail TEXT NOT NULL,
            source TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS revenue_growth(
            id TEXT PRIMARY KEY,
            lead_id TEXT,
            project_id TEXT,
            reason TEXT NOT NULL,
            offer TEXT NOT NULL,
            effort_hours INTEGER,
            amount INTEGER,
            evidence TEXT NOT NULL,
            state TEXT NOT NULL,
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ros_opp_state ON revenue_opportunities(state, updated);
        CREATE INDEX IF NOT EXISTS ros_conv_lead ON revenue_conversations(lead_id, updated);
        CREATE INDEX IF NOT EXISTS ros_msg_conv ON revenue_messages(conversation_id, created);
        CREATE TABLE IF NOT EXISTS revenue_events(
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT,
            detail TEXT NOT NULL,
            evidence_id TEXT,
            created TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ros_events_lead ON revenue_events(lead_id, created);
        CREATE TABLE IF NOT EXISTS evidence_vault(
            id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            claim TEXT NOT NULL,
            url TEXT,
            source TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            observed_at TEXT,
            created TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ros_vault_lead ON evidence_vault(lead_id, created);
        CREATE TABLE IF NOT EXISTS commercial_scores(
            lead_id TEXT PRIMARY KEY,
            severity INTEGER,
            business_fit INTEGER,
            service_fit INTEGER,
            contactability INTEGER,
            buying_signals INTEGER,
            evidence_confidence INTEGER,
            estimated_value INTEGER,
            urgency INTEGER,
            index_score INTEGER,
            coverage INTEGER,
            coverage_of INTEGER,
            why TEXT NOT NULL,
            updated TEXT NOT NULL
        );
        ''')


def _table(c, name):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _owner_clause(alias=''):
    prefix = (alias + '.') if alias else ''
    cid = session.get('client_id') if session.get('role') == 'client' else None
    if cid:
        return prefix + 'owner_user_id=?', (cid,)
    return '1=1', ()


def _client_owns_lead(db, lead_id):
    """Return True for owner sessions; client sessions must own the lead."""
    cid = session.get('client_id') if session.get('role') == 'client' else None
    if not cid:
        return True
    with db() as c:
        row = c.execute('SELECT owner_user_id FROM leads WHERE id=?', (lead_id,)).fetchone()
    return bool(row and row['owner_user_id'] == cid)


def _json(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or ('[]' if fallback == [] else '{}'))
    except (TypeError, ValueError):
        return fallback


def classify_reply(text):
    """Deterministic intent from the reply text. Unknown if nothing matches."""
    blob = ' '.join((text or '').lower().split())
    if len(blob) < 2:
        return 'unknown', 0
    for intent, needles in INTENTS:
        for needle in needles:
            if needle in blob:
                return intent, 1
    return 'unknown', 0


def draft_response(lead, intent, solution, book):
    name = lead.get('name') or 'there'
    offer = (solution or {}).get('name') or 'the recommendation from the last check'
    packs = (book or {}).get('packages') or []
    growth = next((p for p in packs if p.get('id') == 'growth'), None)
    currency = (book or {}).get('currency') or ''
    if intent == 'pricing':
        if growth and growth.get('amount') not in (None, ''):
            price_line = (
                f"Our Growth implementation is listed at {growth['amount']} {currency} in this workspace price book. "
                "That is the book, not a quote, until scope is confirmed."
            )
        else:
            price_line = "I have not put a number on this yet. Amounts stay empty until we agree a scope."
        body = (
            f"Hello {name},\n\nYou asked about cost. {price_line}\n\n"
            f"The last check pointed at: {offer}.\n\nI can send the draft proposal next if useful.\n"
        )
        return body, 'send_proposal'
    if intent == 'wants_proposal':
        return (
            f"Hello {name},\n\nI will send the draft proposal built from the last observation. "
            "It is a draft, not a contract.\n",
            'send_proposal',
        )
    if intent == 'wants_meeting':
        return (
            f"Hello {name},\n\nHappy to walk through the observation. Tell me a time that works.\n",
            'schedule',
        )
    if intent == 'not_now':
        return (
            f"Hello {name},\n\nUnderstood. I will leave this on a 90-day reminder and will not chase.\n",
            'park_90_days',
        )
    if intent == 'not_interested':
        return (
            f"Hello {name},\n\nUnderstood — I will close this and stop. Thank you for the reply.\n",
            'close',
        )
    if intent == 'unsubscribe':
        return (
            f"Hello {name},\n\nYou are off the list. Sorry for the noise.\n",
            'suppress',
        )
    if intent == 'interested':
        return (
            f"Hello {name},\n\nGlad it was useful. Next step is the draft proposal from the stored diagnosis.\n",
            'send_proposal',
        )
    if intent == 'wants_changes':
        return (
            f"Hello {name},\n\nTell me what to change. I will only edit from facts you confirm.\n",
            'revise_concept',
        )
    if intent == 'has_provider':
        return (
            f"Hello {name},\n\nUnderstood. I will park this and not compete for the work.\n",
            'park_90_days',
        )
    if intent == 'wrong_person':
        return (
            f"Hello {name},\n\nThanks for saying. Who should I speak to instead?\n",
            'ask_for_right_person',
        )
    if intent == 'question':
        return (
            f"Hello {name},\n\nHappy to answer from the stored observation — I will not invent a claim.\n",
            'reply',
        )
    return (
        f"Hello {name},\n\nThanks for the reply. I will read it before I suggest a next step.\n",
        'review',
    )


def canonical_funnel(db):
    """Counts of first-class objects only. Empty stages stay at zero."""
    with db() as c:
        where, args = _owner_clause()

        def n(sql, extra=()):
            try:
                return c.execute(sql, args + extra).fetchone()[0]
            except Exception:
                return 0

        def exists(name):
            return _table(c, name)

        lead = n(f'SELECT count(*) FROM leads WHERE {where}') if exists('leads') else 0
        opportunity = n(f'SELECT count(*) FROM revenue_opportunities WHERE {where}') if exists('revenue_opportunities') else 0
        conversation = 0
        if exists('revenue_conversations'):
            conversation = n(f'SELECT count(*) FROM revenue_conversations WHERE {where}')
        proposal = 0
        if exists('generated_proposals'):
            proposal = n(f'SELECT count(*) FROM generated_proposals WHERE {where}')
        # Legacy commercial tables do not carry owner_user_id. Scope them
        # through their lead so client workspaces remain private.
        cid = session.get('client_id') if session.get('role') == 'client' else None
        scope = ' AND l.owner_user_id=?' if cid else ''
        scope_args = (cid,) if cid else ()
        contract = project = invoice = paid = delivered = result = retained = 0
        if exists('contracts'):
            try:
                contract = c.execute(
                    f'''SELECT count(*) FROM contracts x JOIN leads l ON l.id=x.lead_id
                        WHERE 1=1{scope}''', scope_args).fetchone()[0]
            except Exception:
                contract = 0
        if exists('projects'):
            try:
                project = c.execute(
                    f'''SELECT count(*) FROM projects x JOIN leads l ON l.id=x.lead_id
                        WHERE 1=1{scope}''', scope_args).fetchone()[0]
                delivered = c.execute(
                    f'''SELECT count(*) FROM projects x JOIN leads l ON l.id=x.lead_id
                        WHERE x.stage IN ('Delivered','Completed'){scope}''', scope_args).fetchone()[0]
            except Exception:
                project = delivered = 0
        if exists('invoices'):
            try:
                invoice = c.execute(
                    f'''SELECT count(*) FROM invoices x JOIN leads l ON l.id=x.lead_id
                        WHERE 1=1{scope}''', scope_args).fetchone()[0]
                paid = c.execute(
                    f'''SELECT count(*) FROM invoices x JOIN leads l ON l.id=x.lead_id
                        WHERE x.status='Paid'{scope}''', scope_args).fetchone()[0]
            except Exception:
                invoice = paid = 0
        if exists('revenue_results'):
            result = c.execute(
                f'''SELECT count(*) FROM revenue_results x JOIN leads l ON l.id=x.lead_id
                    WHERE 1=1{scope}''', scope_args).fetchone()[0]
        if exists('revenue_growth'):
            retained = c.execute(
                f'''SELECT count(*) FROM revenue_growth x JOIN leads l ON l.id=x.lead_id
                    WHERE 1=1{scope}''', scope_args).fetchone()[0]
        counts = {
            'lead': lead, 'opportunity': opportunity, 'conversation': conversation,
            'proposal': proposal, 'contract': contract, 'project': project,
            'invoice': invoice, 'paid': paid, 'delivered': delivered,
            'result': result, 'retained': retained,
        }
    steps = [{'id': i, 'label': l, 'count': counts[i], 'basis': b} for i, l, b in FUNNEL]
    return {
        'steps': steps,
        'counts': counts,
        'disclaimer': (
            'Canonical objects only. Proposals are generated_proposals rows, never projects or contracts. '
            'Empty stages stay at zero.'
        ),
    }


def upsert_opportunity(db, lead, report, ranking, now):
    """One opportunity row per lead, updated from a stored report / ranking."""
    stamp = now()
    report = report or {}
    ranking = ranking or {}
    factors = {f.get('id'): f for f in (ranking.get('factors') or []) if isinstance(f, dict)}
    fit_pts = (factors.get('fit') or {}).get('points')
    contact_pts = 1 if ((lead.get('email') or '').strip() or (lead.get('phone') or '').strip()) else 0
    ready = 1 if report.get('qualified') else 0
    signals = 1 if (factors.get('timing') or {}).get('points') else 0
    coverage = ranking.get('coverage') or 0
    coverage_of = ranking.get('coverage_of') or 10
    confidence = int(round(100 * coverage / coverage_of)) if coverage_of else 0
    gap = report.get('score') if report.get('score') is not None else ranking.get('opportunity_score')
    work = ranking.get('score')
    why = ranking.get('why') or report.get('solution', {}).get('why') or 'Stored report. Not a revenue forecast.'
    state = 'open'
    if lead.get('stage') == 'Won':
        state = 'won'
    elif lead.get('stage') == 'Not a fit':
        state = 'lost'
    elif report.get('id'):
        state = 'qualified' if report.get('qualified') else 'open'
    oid = uuid.uuid4().hex
    with db() as c:
        row = c.execute('SELECT id,state,created,opened_at,qualified_at FROM revenue_opportunities WHERE lead_id=?',
                        (lead['id'],)).fetchone()
        if row:
            oid = row['id']
            c.execute(
                '''UPDATE revenue_opportunities SET report_id=?,gap_score=?,work_score=?,priority=?,state=?,
                   problem_severity=?,fit=?,contactability=?,commercial_readiness=?,buying_signals=?,
                   evidence_confidence=?,why=?,updated=?,qualified_at=CASE WHEN ?='qualified' AND qualified_at IS NULL THEN ? ELSE qualified_at END
                   WHERE id=?''',
                (report.get('id'), gap, work, report.get('priority') or ranking.get('priority'),
                 state, gap, fit_pts, contact_pts, ready, signals, confidence, str(why)[:800], stamp,
                 state, stamp, oid),
            )
        else:
            c.execute(
                '''INSERT INTO revenue_opportunities(
                    id,lead_id,report_id,gap_score,work_score,priority,state,problem_severity,fit,
                    contactability,commercial_readiness,buying_signals,evidence_confidence,why,
                    created,updated,opened_at,qualified_at,owner_user_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (oid, lead['id'], report.get('id'), gap, work, report.get('priority'),
                 state, gap, fit_pts, contact_pts, ready, signals, confidence, str(why)[:800],
                 stamp, stamp, stamp, stamp if state == 'qualified' else None, lead.get('owner_user_id')),
            )
    return oid


def on_report_saved(db, lead, report, now):
    ranking = {}
    try:
        from web.platform import score_lead, price_book
        ranking = score_lead(db, lead)
        score = commercial_score(lead, ranking, report, price_book(db))
        persist_commercial(db, lead['id'], score, now)
    except Exception:
        ranking = {}
    oid = upsert_opportunity(db, lead, report, ranking, now)
    try:
        vault_from_report(db, lead, report, now)
        log_event(db, lead['id'], 'opportunity', 'opportunity_report', report.get('id'),
                  f"Report {report.get('score')}/100", now)
    except Exception:
        pass
    return oid


def on_proposal_saved(db, lead, now):
    stamp = now()
    with db() as c:
        row = c.execute('SELECT id FROM revenue_opportunities WHERE lead_id=?', (lead['id'],)).fetchone()
        if row:
            c.execute(
                '''UPDATE revenue_opportunities SET state='proposed', proposed_at=COALESCE(proposed_at,?), updated=?
                   WHERE id=?''',
                (stamp, stamp, row['id']),
            )


def _conversation_for(db, lead, now):
    with db() as c:
        row = c.execute('SELECT * FROM revenue_conversations WHERE lead_id=? ORDER BY created DESC LIMIT 1',
                        (lead['id'],)).fetchone()
        if row:
            return dict(row)
        cid = uuid.uuid4().hex
        stamp = now()
        opp = c.execute('SELECT id FROM revenue_opportunities WHERE lead_id=?', (lead['id'],)).fetchone()
        c.execute(
            'INSERT INTO revenue_conversations VALUES(?,?,?,?,?,?,?,?)',
            (cid, lead['id'], opp['id'] if opp else None, 'open', None, stamp, stamp, lead.get('owner_user_id')),
        )
        if opp:
            c.execute(
                '''UPDATE revenue_opportunities SET state=CASE WHEN state IN ('won','lost') THEN state ELSE 'conversing' END,
                   conversing_at=COALESCE(conversing_at,?), updated=? WHERE id=?''',
                (stamp, stamp, opp['id']),
            )
        return {'id': cid, 'lead_id': lead['id']}


def ingest_reply(db, lead, body, now, channel='email', source='manual'):
    """Store an inbound message, classify it, suggest a response. Never sends."""
    intent, _conf = classify_reply(body)
    conv = _conversation_for(db, lead, now)
    solution = {}
    try:
        from web.opportunity import money_leaks, recommend_solution, _latest_audit
        leaks, _ = money_leaks(lead, _latest_audit(db, lead['id']))
        solution = recommend_solution(leaks, lead)
    except Exception:
        solution = {}
    book = {}
    try:
        from web.platform import price_book
        book = price_book(db)
    except Exception:
        book = {}
    suggested, action = draft_response(lead, intent, solution, book)
    action = ACTIONS.get(intent, action)
    mid = uuid.uuid4().hex
    stamp = now()
    with db() as c:
        c.execute(
            'INSERT INTO revenue_messages VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (mid, conv['id'], lead['id'], 'inbound', channel, (body or '')[:4000],
             intent, suggested, action, source, stamp),
        )
        c.execute(
            'UPDATE revenue_conversations SET last_intent=?, state=?, updated=? WHERE id=?',
            (intent, 'waiting' if intent not in ('unsubscribe', 'not_interested') else 'closed', stamp, conv['id']),
        )
        if intent == 'unsubscribe':
            email = (lead.get('email') or '').strip().lower()
            if email:
                c.execute('INSERT OR IGNORE INTO suppression(email,created) VALUES(?,?)', (email, stamp))
        if intent in ('not_interested',):
            c.execute("UPDATE leads SET stage='Not a fit', updated=? WHERE id=?", (stamp, lead['id']))
            c.execute("UPDATE revenue_opportunities SET state='lost', lost_at=?, updated=? WHERE lead_id=?",
                      (stamp, stamp, lead['id']))
        elif intent == 'not_now':
            try:
                from datetime import datetime, timezone, timedelta
                follow = (datetime.now(timezone.utc) + timedelta(days=90)).date().isoformat()
                c.execute(
                    'INSERT INTO memory_events VALUES(?,?,?,?,?,?,?,?,?)',
                    (uuid.uuid4().hex, lead['id'], 'not_now', 'Reply classified as not now',
                     'unknown', follow, (body or '')[:400], stamp, lead.get('owner_user_id')),
                )
            except Exception:
                pass
        else:
            c.execute("UPDATE leads SET stage='Replied', updated=? WHERE id=? AND stage!='Won'", (stamp, lead['id']))
    try:
        log_event(db, lead['id'], 'conversation', 'revenue_message', mid,
                  f'Inbound classified as {intent}', now)
    except Exception:
        pass
    return {
        'message_id': mid,
        'conversation_id': conv['id'],
        'intent': intent,
        'suggested_action': action,
        'suggested_response': suggested,
        'solution': solution.get('name'),
        'note': 'Suggested only. Nothing was sent.',
    }


def on_outreach_reply(db, email, now, body=''):
    if not email:
        return None
    with db() as c:
        row = c.execute('SELECT * FROM leads WHERE lower(email)=lower(?) LIMIT 1', (email,)).fetchone()
    if not row:
        return None
    lead = dict(row)
    text = body or 'Replied (provider event; no body stored).'
    return ingest_reply(db, lead, text, now, channel='email', source='outreach_event')


def dossier(db, lead, now):
    """Why → observed → recommend → built → cost → send. One record for the operator."""
    from web.opportunity import _latest_audit, money_leaks, recommend_solution, serialize_row
    from web.platform import score_lead, price_book
    audit = _latest_audit(db, lead['id'])
    leaks, packed = money_leaks(lead, audit)
    ranking = score_lead(db, lead)
    solution = recommend_solution(leaks, lead)
    book = price_book(db)
    with db() as c:
        report = c.execute(
            'SELECT * FROM opportunity_reports WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lead['id'],)
        ).fetchone() if _table(c, 'opportunity_reports') else None
        proto = c.execute(
            'SELECT token,review_token,created FROM prototypes WHERE lead_id=? ORDER BY created DESC LIMIT 1',
            (lead['id'],),
        ).fetchone() if _table(c, 'prototypes') else None
        prop = c.execute(
            'SELECT id,token,status,created FROM generated_proposals WHERE lead_id=? ORDER BY created DESC LIMIT 1',
            (lead['id'],),
        ).fetchone() if _table(c, 'generated_proposals') else None
        conv = c.execute(
            'SELECT * FROM revenue_conversations WHERE lead_id=? ORDER BY updated DESC LIMIT 1', (lead['id'],)
        ).fetchone()
        messages = []
        if conv:
            messages = [dict(r) for r in c.execute(
                'SELECT direction,channel,body,intent,suggested_action,suggested_response,created '
                'FROM revenue_messages WHERE conversation_id=? ORDER BY created DESC LIMIT 12',
                (conv['id'],),
            )]
        opp = c.execute('SELECT * FROM revenue_opportunities WHERE lead_id=?', (lead['id'],)).fetchone()
        pending = []
        if _table(c, 'crew_approvals'):
            pending = [dict(r) for r in c.execute(
                "SELECT id,title,state,kind,created FROM crew_approvals WHERE lead_id=? AND state='pending' "
                "ORDER BY created DESC LIMIT 8",
                (lead['id'],),
            )]
        growth = [dict(r) for r in c.execute(
            'SELECT * FROM revenue_growth WHERE lead_id=? ORDER BY created DESC LIMIT 5', (lead['id'],)
        )] if _table(c, 'revenue_growth') else []
    last = messages[0] if messages else None
    next_action = (last or {}).get('suggested_action') or (
        'generate_report' if not report else ('generate_proposal' if not prop else 'review')
    )
    return {
        'lead': {k: lead.get(k) for k in ('id', 'name', 'city', 'category', 'website', 'stage', 'status', 'email', 'phone')},
        'why': ranking.get('why'),
        'ranking': {
            'work_score': ranking.get('score'),
            'gap_score': ranking.get('opportunity_score'),
            'coverage': ranking.get('coverage'),
            'coverage_of': ranking.get('coverage_of'),
            'factors': ranking.get('factors'),
            'note': 'work_score is who to contact first. gap_score is observed-problem severity. Neither is revenue.',
        },
        'observed': {
            'leaks': leaks[:8],
            'audit_status': (audit or {}).get('status') or lead.get('audit_status') or 'NOT_ANALYZED',
            'disclaimer': packed.get('disclaimer'),
        },
        'recommend': solution,
        'built': {
            'prototype': f"/p/{proto['token']}" if proto else None,
            'review': f"/r/{proto['review_token']}" if proto and proto['review_token'] else None,
        },
        'costs': {
            'packages': book.get('packages') or [],
            'currency': book.get('currency') or '',
            'note': book.get('note') or 'Amounts empty until a price book is set. Not a quote for this lead.',
        },
        'proposal': {'token': prop['token'], 'url': f"/proposal/{prop['token']}", 'status': prop['status'],
                     'created': prop['created']} if prop else None,
        'report': {'id': report['id'], 'token': report['token'], 'score': report['score'],
                   'priority': report['priority']} if report else None,
        'opportunity': dict(opp) if opp else None,
        'conversation': {
            'id': conv['id'] if conv else None,
            'state': conv['state'] if conv else None,
            'last_intent': conv['last_intent'] if conv else None,
            'messages': messages,
        },
        'approvals': pending,
        'growth': growth,
        'next_action': next_action,
        'thread': thread_for(db, lead['id']),
        'disclaimer': 'Suggested next action is derived from stored artefacts. Nothing is sent until a human approves.',
    }


def record_result(db, lead_id, project_id, kind, detail, source, now):
    rid = uuid.uuid4().hex
    stamp = now()
    with db() as c:
        c.execute('INSERT INTO revenue_results VALUES(?,?,?,?,?,?,?,?)',
                  (rid, lead_id, project_id, kind, detail[:800], source, stamp, stamp))
    return rid


def refresh_growth(db, now):
    """Post-delivery offers from observed leaks only."""
    from web.opportunity import _lead, _latest_audit, money_leaks
    from web.platform import price_book
    stamp = now()
    book = price_book(db)
    packs = {p.get('id'): p for p in (book.get('packages') or [])}
    created = 0
    with db() as c:
        if not _table(c, 'projects'):
            return 0
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM projects WHERE stage IN ('Delivered','Completed') AND lead_id IS NOT NULL AND lead_id!=''"
        )]
    for project in rows:
        lead = _lead(db, project['lead_id'])
        if not lead:
            continue
        audit = _latest_audit(db, lead['id'])
        leaks, _ = money_leaks(lead, audit)
        commercial = [i for i in leaks if i.get('commercial')]
        if commercial:
            top = commercial[0]
            offer = top.get('fix') or 'Observed leak after delivery'
            reason = f"{len(commercial)} commercial leak(s) on the latest check after delivery."
            evidence = [{'title': i.get('title'), 'source': i.get('source')} for i in commercial[:5]]
            pack = packs.get('growth') or packs.get('basic') or {}
            amount = pack.get('amount')
            hours = 12 if pack.get('id') == 'basic' else 24 if pack.get('id') == 'growth' else 8
        else:
            offer = 'No new commercial leak on the last check. Do not invent an upsell.'
            reason = 'Latest check produced no commercial gap.'
            evidence = []
            amount = None
            hours = None
        record_result(db, lead['id'], project['id'], 'post_delivery_check', reason, 'site_audits_or_listing', now)
        with db() as c:
            existing = c.execute('SELECT id FROM revenue_growth WHERE project_id=?', (project['id'],)).fetchone()
            blob = json.dumps(evidence)
            if existing:
                c.execute(
                    'UPDATE revenue_growth SET reason=?,offer=?,effort_hours=?,amount=?,evidence=?,updated=? WHERE id=?',
                    (reason, offer[:400], hours, amount, blob, stamp, existing['id']),
                )
            else:
                c.execute(
                    'INSERT INTO revenue_growth VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (uuid.uuid4().hex, lead['id'], project['id'], reason, offer[:400], hours, amount,
                     blob, 'open' if commercial else 'none', stamp, stamp),
                )
                created += 1
    return created


def backfill(db, now):
    """Create canonical rows from existing reports / Replied stages. No invented values."""
    stamp = now()
    n_opp = n_conv = 0
    with db() as c:
        if _table(c, 'opportunity_reports'):
            rows = c.execute(
                '''SELECT r.id AS report_id, r.lead_id, r.score, r.priority, r.qualified, r.created, r.owner_user_id,
                          l.name, l.email, l.phone, l.stage, l.category, l.city, l.website, l.status
                   FROM opportunity_reports r JOIN leads l ON l.id=r.lead_id'''
            ).fetchall()
        else:
            rows = []
    for row in rows:
        lead = dict(row)
        lead['id'] = row['lead_id']
        report = {'id': row['report_id'], 'score': row['score'], 'priority': row['priority'],
                  'qualified': row['qualified']}
        upsert_opportunity(db, lead, report, {}, now)
        n_opp += 1
    with db() as c:
        replied = c.execute("SELECT * FROM leads WHERE stage IN ('Replied','Won')").fetchall()
    for row in replied:
        lead = dict(row)
        with db() as c:
            exists = c.execute('SELECT id FROM revenue_conversations WHERE lead_id=?', (lead['id'],)).fetchone()
        if exists:
            continue
        _conversation_for(db, lead, now)
        n_conv += 1
    return {'opportunities': n_opp, 'conversations': n_conv, 'at': stamp}


def log_event(db, lead_id, stage, object_type, object_id, detail, now, evidence_id=None):
    eid = uuid.uuid4().hex
    with db() as c:
        c.execute(
            'INSERT INTO revenue_events VALUES(?,?,?,?,?,?,?,?)',
            (eid, lead_id, stage, object_type, object_id, (detail or '')[:800], evidence_id, now()),
        )
    return eid


def put_evidence(db, lead_id, claim, source, now, url='', confidence=50, observed_at=None):
    vid = uuid.uuid4().hex
    with db() as c:
        c.execute(
            'INSERT INTO evidence_vault VALUES(?,?,?,?,?,?,?,?)',
            (vid, lead_id, (claim or '')[:800], (url or '')[:500], source[:120],
             int(max(0, min(100, confidence))), observed_at or now(), now()),
        )
    return vid


def vault_from_report(db, lead, report, now):
    """Each leak on a stored report becomes an evidence row. No extra claims."""
    url = (lead.get('website') or lead.get('source_url') or '')
    observed = ((report.get('evidence') or {}) if isinstance(report.get('evidence'), dict) else {}).get('checked_at')
    ids = []
    for leak in (report.get('leaks') or [])[:12]:
        src = leak.get('source') or 'observation'
        conf = 80 if 'measur' in src.lower() or src.lower() in ('observed', 'page') else 45
        ids.append(put_evidence(db, lead['id'], leak.get('leak') or leak.get('title') or '', src, now,
                                url=url, confidence=conf, observed_at=observed))
    return ids


def commercial_score(lead, ranking, report, book):
    """Separate from gap score. Unknown factors stay None and do not invent value."""
    factors = {f.get('id'): f for f in (ranking.get('factors') or []) if isinstance(f, dict)}

    def pts(fid):
        f = factors.get(fid) or {}
        if f.get('state') == 'unknown':
            return None, f.get('max') or 0
        if not f:
            return None, 0
        mx = f.get('max') or 0
        if not mx:
            return None, 0
        return int(round(100 * (f.get('points') or 0) / mx)), mx

    severity = report.get('score') if report and report.get('score') is not None else ranking.get('opportunity_score')
    fit, _ = pts('fit')
    contact, _ = pts('listing')
    if (lead.get('email') or '').strip() or (lead.get('phone') or '').strip():
        contact = 100
    else:
        contact = 0
    buying, _ = pts('timing')
    coverage = ranking.get('coverage') or 0
    coverage_of = ranking.get('coverage_of') or 10
    confidence = int(round(100 * coverage / coverage_of)) if coverage_of else None
    packs = (book or {}).get('packages') or []
    growth = next((p for p in packs if p.get('id') == 'growth'), None)
    estimated = growth.get('amount') if growth and growth.get('amount') not in (None, '') else None
    urgency = buying
    known = [v for v in (severity, fit, contact if contact else None, buying, confidence, urgency) if v is not None]
    # contact 0 is known (not contactable)
    if contact is not None:
        known = [v for v in (severity, fit, contact, buying, confidence, urgency) if v is not None]
    index = int(round(sum(known) / len(known))) if known else None
    why_bits = []
    if severity is not None:
        why_bits.append(f'gap {severity}')
    if fit is not None:
        why_bits.append(f'fit {fit}')
    why_bits.append('contactable' if contact == 100 else 'no contact on file')
    if estimated is None:
        why_bits.append('project value unknown (price book empty)')
    else:
        why_bits.append(f'book value {estimated} (not a quote)')
    return {
        'severity': severity,
        'business_fit': fit,
        'service_fit': fit,
        'contactability': contact,
        'buying_signals': buying,
        'evidence_confidence': confidence,
        'estimated_value': estimated,
        'urgency': urgency,
        'index_score': index,
        'coverage': coverage,
        'coverage_of': coverage_of,
        'why': '; '.join(why_bits),
        'note': 'Commercial index averages known factors only. estimated_value is the price-book figure, not a forecast.',
    }


def persist_commercial(db, lead_id, score, now):
    with db() as c:
        c.execute(
            '''INSERT INTO commercial_scores(
                lead_id,severity,business_fit,service_fit,contactability,buying_signals,
                evidence_confidence,estimated_value,urgency,index_score,coverage,coverage_of,why,updated
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(lead_id) DO UPDATE SET
                severity=excluded.severity,business_fit=excluded.business_fit,service_fit=excluded.service_fit,
                contactability=excluded.contactability,buying_signals=excluded.buying_signals,
                evidence_confidence=excluded.evidence_confidence,estimated_value=excluded.estimated_value,
                urgency=excluded.urgency,index_score=excluded.index_score,coverage=excluded.coverage,
                coverage_of=excluded.coverage_of,why=excluded.why,updated=excluded.updated''',
            (lead_id, score.get('severity'), score.get('business_fit'), score.get('service_fit'),
             score.get('contactability'), score.get('buying_signals'), score.get('evidence_confidence'),
             score.get('estimated_value'), score.get('urgency'), score.get('index_score'),
             score.get('coverage'), score.get('coverage_of'), score.get('why'), now()),
        )


def thread_for(db, lead_id):
    with db() as c:
        rows = [dict(r) for r in c.execute(
            'SELECT * FROM revenue_events WHERE lead_id=? ORDER BY created ASC', (lead_id,))]
        evidence = [dict(r) for r in c.execute(
            'SELECT * FROM evidence_vault WHERE lead_id=? ORDER BY created DESC LIMIT 40', (lead_id,))]
        commercial = c.execute('SELECT * FROM commercial_scores WHERE lead_id=?', (lead_id,)).fetchone()
    return {
        'events': rows,
        'evidence': evidence,
        'commercial': dict(commercial) if commercial else None,
        'note': 'Thread is append-only. Missing stages are missing — they are not inferred.',
    }


def advance_to_proposal(db, lead, now):
    """One operator click: report → prototype → proposal from stored evidence. Never sends."""
    from web.opportunity import build_report, save_report, serialize_row, _latest_audit, money_leaks
    from web.platform import _settings, price_book, packages_for, build_proposal_body
    import secrets, json as _json
    steps = []
    with db() as c:
        report_row = c.execute(
            'SELECT * FROM opportunity_reports WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lead['id'],)
        ).fetchone() if _table(c, 'opportunity_reports') else None
    if report_row:
        report = serialize_row(report_row)
        steps.append('report_exists')
    else:
        report = save_report(db, lead, build_report(db, lead, now, observe_live=False), now)
        vault_from_report(db, lead, report, now)
        log_event(db, lead['id'], 'opportunity', 'opportunity_report', report.get('id'),
                  f"Report {report.get('score')}/100 {report.get('priority')}", now)
        steps.append('report')
    with db() as c:
        proto = c.execute('SELECT token FROM prototypes WHERE lead_id=? ORDER BY created DESC LIMIT 1',
                          (lead['id'],)).fetchone()
    proto_url = f"/p/{proto['token']}" if proto else None
    if not proto:
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
                       'sections': []}
        audit = _latest_audit(db, lead['id'])
        leaks, _ = money_leaks(lead, audit)
        concept['leaks'] = [{'title': i['title'], 'leak': i['leak'], 'fix': i['fix']} for i in leaks[:5]]
        token = secrets.token_urlsafe(16)
        with db() as c:
            c.execute('INSERT INTO prototypes VALUES(?,?,?,?,?,?,0)',
                      (uuid.uuid4().hex, token, lead['id'], review_token, _json.dumps(concept)[:40000], now()))
        proto_url = f'/p/{token}'
        log_event(db, lead['id'], 'concept', 'prototype', token, 'First-section concept stored', now)
        steps.append('prototype')
    else:
        steps.append('prototype_exists')
    with db() as c:
        prop = c.execute('SELECT token,status FROM generated_proposals WHERE lead_id=? ORDER BY created DESC LIMIT 1',
                         (lead['id'],)).fetchone()
    if prop:
        steps.append('proposal_exists')
        prop_url = f"/proposal/{prop['token']}"
    else:
        book = price_book(db)
        packs = packages_for(lead, report.get('leaks') or [], book)
        body = build_proposal_body(lead, report, packs, {'url': proto_url} if proto_url else None,
                                   report.get('fit') or {})
        token = secrets.token_urlsafe(16)
        pid = uuid.uuid4().hex
        stamp = now()
        with db() as c:
            c.execute(
                '''INSERT INTO generated_proposals
                   (id,token,lead_id,report_id,packages,body,status,views,created,updated,owner_user_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                (pid, token, lead['id'], report.get('id'), _json.dumps(packs), _json.dumps(body),
                 'draft', 0, stamp, stamp, lead.get('owner_user_id')),
            )
        on_proposal_saved(db, lead, now)
        log_event(db, lead['id'], 'proposal', 'generated_proposal', pid, 'Draft proposal stored', now)
        steps.append('proposal')
        prop_url = f'/proposal/{token}'
    return {'steps': steps, 'proposal_url': prop_url, 'prototype_url': proto_url, 'sent': False}


def accept_proposal(db, lead, now, package_id='growth'):
    """Proposal → contract → project → invoice. Invoice only if the price book has an amount."""
    from web.platform import price_book
    stamp = now()
    book = price_book(db)
    packs = book.get('packages') or []
    pack = next((p for p in packs if p.get('id') == package_id), None) or next(iter(packs), {})
    amount = pack.get('amount') if pack and pack.get('amount') not in (None, '') else None
    currency = (book.get('currency') or 'USD')[:8]
    with db() as c:
        prop = c.execute('SELECT * FROM generated_proposals WHERE lead_id=? ORDER BY created DESC LIMIT 1',
                         (lead['id'],)).fetchone()
    if not prop:
        return {'error': 'No draft proposal on this lead. Advance to a proposal first.'}, 400
    cid = uuid.uuid4().hex
    pid = uuid.uuid4().hex
    iid = None
    with db() as c:
        c.execute(
            '''INSERT INTO contracts(id,title,client,email,lead_id,currency,amount_minor,paid_minor,status,notes,created,updated)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
            (cid, f"{pack.get('name') or 'Website'} — {lead.get('name')}",
             lead.get('name'), lead.get('email'), lead['id'], currency,
             int(amount) if amount is not None else None, 0, 'Draft',
             'Opened from an accepted draft proposal. Not a legally signed instrument until recorded as Signed.',
             stamp, stamp),
        )
        c.execute(
            '''INSERT INTO projects(id,title,lead_id,contract_id,stage,next_action,scope,currency,quote_minor,created,updated)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
            (pid, f"{lead.get('name')} — {pack.get('name') or 'implementation'}",
             lead['id'], cid, 'Agreement', 'Confirm scope with the client',
             (pack.get('name') or 'Implementation') + ': ' + ', '.join(pack.get('includes') or [])[:500],
             currency, int(amount) if amount is not None else None, stamp, stamp),
        )
        c.execute("UPDATE generated_proposals SET status='accepted', updated=? WHERE id=?", (stamp, prop['id']))
        if amount is not None:
            iid = uuid.uuid4().hex
            number = 'INV-' + iid[:8].upper()
            c.execute(
                '''INSERT INTO invoices(id,number,client_name,client_email,lead_id,project_id,currency,status,
                    issue_date,notes,terms,tax_rate,discount_type,discount_value,subtotal_minor,tax_minor,
                    discount_minor,total_minor,created,updated)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (iid, number, lead.get('name'), lead.get('email'), lead['id'], pid, currency, 'Draft',
                 stamp[:10], 'Opened from accepted proposal. Draft until sent.',
                 'Due on receipt unless agreed otherwise.', 0, 'none', 0,
                 int(amount), 0, 0, int(amount), stamp, stamp),
            )
            if _table(c, 'invoice_items'):
                c.execute(
                    'INSERT INTO invoice_items VALUES(?,?,?,?,?,?,?)',
                    (uuid.uuid4().hex, iid, pack.get('name') or 'Implementation', 1,
                     int(amount), int(amount), stamp),
                )
        c.execute("UPDATE revenue_opportunities SET state='proposed', proposed_at=COALESCE(proposed_at,?), updated=? WHERE lead_id=?",
                  (stamp, stamp, lead['id']))
    log_event(db, lead['id'], 'contract', 'contract', cid, 'Contract opened from accepted proposal', now)
    log_event(db, lead['id'], 'project', 'project', pid, 'Project opened from accepted proposal', now)
    if iid:
        log_event(db, lead['id'], 'invoice', 'invoice', iid, f'Draft invoice {amount} {currency}', now)
    return {
        'contract_id': cid, 'project_id': pid, 'invoice_id': iid,
        'amount': amount, 'currency': currency,
        'note': ('Invoice created from the price book amount — still a draft, not a forecast.'
                 if iid else 'No invoice: the price book has no amount for this package.'),
    }, 200


def mark_invoice_paid(db, invoice_id, now):
    stamp = now()
    with db() as c:
        inv = c.execute('SELECT * FROM invoices WHERE id=?', (invoice_id,)).fetchone()
        if not inv:
            return {'error': 'Invoice not found.'}, 404
        c.execute("UPDATE invoices SET status='Paid', updated=? WHERE id=?", (stamp, invoice_id))
        if inv['lead_id']:
            c.execute("UPDATE leads SET stage='Won', updated=? WHERE id=?", (stamp, inv['lead_id']))
            c.execute("UPDATE revenue_opportunities SET state='won', won_at=?, updated=? WHERE lead_id=?",
                      (stamp, stamp, inv['lead_id']))
            if inv['project_id']:
                c.execute("UPDATE projects SET stage='Build', updated=? WHERE id=?", (stamp, inv['project_id']))
            log_event(db, inv['lead_id'], 'paid', 'invoice', invoice_id,
                      f"Invoice marked Paid ({inv['total_minor']} {inv['currency']})", now)
    return {'ok': True, 'invoice_id': invoice_id, 'status': 'Paid'}, 200


def mark_delivered(db, project_id, now):
    stamp = now()
    with db() as c:
        proj = c.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        if not proj:
            return {'error': 'Project not found.'}, 404
        c.execute("UPDATE projects SET stage='Delivered', updated=? WHERE id=?", (stamp, project_id))
        if proj['lead_id']:
            log_event(db, proj['lead_id'], 'delivered', 'project', project_id, 'Project marked Delivered', now)
    n = refresh_growth(db, now)
    return {'ok': True, 'project_id': project_id, 'growth_created': n}, 200


def command_center(db):
    """One screen: what happened, what needs attention, where is the money."""
    funnel = canonical_funnel(db)
    with db() as c:
        events = [dict(r) for r in c.execute(
            '''SELECT e.*, l.name AS lead_name FROM revenue_events e
               LEFT JOIN leads l ON l.id=e.lead_id ORDER BY e.created DESC LIMIT 12''')]
        waiting = [dict(r) for r in c.execute(
            '''SELECT c.lead_id, c.last_intent, l.name AS lead_name FROM revenue_conversations c
               JOIN leads l ON l.id=c.lead_id WHERE c.state='waiting' ORDER BY c.updated DESC LIMIT 12''')] \
            if _table(c, 'revenue_conversations') else []
        hottest = [dict(r) for r in c.execute(
            '''SELECT s.lead_id, s.index_score, s.why, s.estimated_value, l.name AS lead_name, l.city
               FROM commercial_scores s JOIN leads l ON l.id=s.lead_id
               ORDER BY CASE WHEN s.index_score IS NULL THEN 1 ELSE 0 END, s.index_score DESC LIMIT 12''')] \
            if _table(c, 'commercial_scores') else []
        approvals = [dict(r) for r in c.execute(
            "SELECT id, lead_id, title, kind, created FROM crew_approvals WHERE state='pending' ORDER BY created DESC LIMIT 12"
        )] if _table(c, 'crew_approvals') else []
        growth = [dict(r) for r in c.execute(
            "SELECT g.lead_id, g.offer, g.amount, l.name AS lead_name FROM revenue_growth g "
            "LEFT JOIN leads l ON l.id=g.lead_id WHERE g.state='open' ORDER BY g.updated DESC LIMIT 8"
        )] if _table(c, 'revenue_growth') else []
        paid_sum = c.execute("SELECT ifnull(sum(total_minor),0) FROM invoices WHERE status='Paid'").fetchone()[0] \
            if _table(c, 'invoices') else 0
        unpaid = c.execute("SELECT count(*) FROM invoices WHERE status IN ('Draft','Sent','Overdue')").fetchone()[0] \
            if _table(c, 'invoices') else 0
    return {
        'funnel': funnel,
        'happened': events,
        'attention': {
            'replies': waiting,
            'approvals': approvals,
            'upsells': growth,
        },
        'money': {
            'paid_minor_sum': paid_sum,
            'unpaid_invoices': unpaid,
            'note': 'paid_minor_sum is SUM of invoices marked Paid. Zero means none paid, not a missing feed.',
        },
        'hottest': hottest,
        'disclaimer': 'Every list is a live query. Empty lists stay empty.',
    }


def outcome_metrics(db):
    """Conversion and timing from stored rows. Ratios are null when the denominator is 0."""
    with db() as c:
        def rows(sql, args=()):
            return [dict(r) for r in c.execute(sql, args)]

        leads = c.execute('SELECT count(*) FROM leads').fetchone()[0]
        won = c.execute("SELECT count(*) FROM leads WHERE stage='Won'").fetchone()[0]
        replied = c.execute("SELECT count(*) FROM leads WHERE stage IN ('Replied','Won')").fetchone()[0]
        contacted = c.execute("SELECT count(*) FROM leads WHERE stage IN ('Contacted','Replied','Won')").fetchone()[0]
        by_source = rows(
            "SELECT ifnull(source,'unknown') k, count(*) n, "
            "sum(CASE WHEN stage='Won' THEN 1 ELSE 0 END) won FROM leads GROUP BY ifnull(source,'unknown') ORDER BY n DESC LIMIT 12"
        )
        by_city = rows(
            "SELECT ifnull(city,'unknown') k, count(*) n, "
            "sum(CASE WHEN stage='Won' THEN 1 ELSE 0 END) won FROM leads GROUP BY ifnull(city,'unknown') ORDER BY n DESC LIMIT 12"
        )
        by_industry = rows(
            "SELECT ifnull(category,'unknown') k, count(*) n, "
            "sum(CASE WHEN stage='Won' THEN 1 ELSE 0 END) won FROM leads GROUP BY ifnull(category,'unknown') ORDER BY n DESC LIMIT 12"
        )
        paid = rows("SELECT id, lead_id, total_minor, currency, updated, created FROM invoices WHERE status='Paid'") \
            if _table(c, 'invoices') else []
        avg_deal = None
        if paid:
            avg_deal = int(sum(p['total_minor'] or 0 for p in paid) / len(paid))
        durations = []
        for inv in paid:
            if not inv.get('lead_id'):
                continue
            lead = c.execute('SELECT created FROM leads WHERE id=?', (inv['lead_id'],)).fetchone()
            if not lead or not lead['created'] or not inv.get('updated'):
                continue
            try:
                from datetime import datetime
                a = datetime.fromisoformat(str(lead['created']).replace('Z', '+00:00'))
                b = datetime.fromisoformat(str(inv['updated']).replace('Z', '+00:00'))
                durations.append(max(0, (b - a).total_seconds()))
            except Exception:
                pass
        avg_seconds = int(sum(durations) / len(durations)) if durations else None

        def rate(num, den):
            return round(num / den, 4) if den else None

    return {
        'leads': leads,
        'contacted': contacted,
        'replies': replied,
        'won': won,
        'contact_rate': rate(contacted, leads),
        'reply_rate': rate(replied, contacted),
        'win_rate': rate(won, leads),
        'avg_deal_minor': avg_deal,
        'avg_discovery_to_paid_seconds': avg_seconds,
        'by_source': by_source,
        'by_city': by_city,
        'by_industry': by_industry,
        'note': 'Rates are null when the denominator is 0. avg_deal_minor is the mean of Paid invoices only.',
    }


def register_revenue_os(app, db, now, log):
    ensure_tables(db)
    try:
        backfill(db, now)
    except Exception:
        pass

    @app.get('/api/os/funnel')
    def os_funnel():
        return jsonify(canonical_funnel(db))

    @app.get('/api/os/lead/<lid>')
    def os_dossier(lid):
        from web.opportunity import _lead
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        return jsonify(dossier(db, lead, now))

    @app.post('/api/os/lead/<lid>/reply')
    def os_reply(lid):
        from web.opportunity import _lead
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        body = request.get_json(silent=True) or {}
        text = str(body.get('body') or '').strip()
        if len(text) < 2:
            return jsonify(error='Reply text is required.'), 400
        result = ingest_reply(db, lead, text, now, channel=str(body.get('channel') or 'email'), source='operator')
        log('conversation', f"{lead.get('name')}: intent {result['intent']}")
        return jsonify(result)

    @app.get('/api/os/inbox')
    def os_inbox():
        where, args = _owner_clause('c')
        with db() as c:
            rows = [dict(r) for r in c.execute(
                f'''SELECT c.id, c.lead_id, c.state, c.last_intent, c.updated, l.name AS lead_name, l.email,
                           (SELECT body FROM revenue_messages m WHERE m.conversation_id=c.id
                            ORDER BY m.created DESC LIMIT 1) last_body,
                           (SELECT suggested_action FROM revenue_messages m WHERE m.conversation_id=c.id
                            ORDER BY m.created DESC LIMIT 1) suggested_action
                    FROM revenue_conversations c JOIN leads l ON l.id=c.lead_id
                    WHERE {where}
                    ORDER BY c.updated DESC LIMIT 50''',
                args,
            )]
        return jsonify(items=rows, count=len(rows),
                       disclaimer='Threads that exist as rows. Empty inbox stays empty.')

    @app.get('/api/os/growth')
    def os_growth():
        with db() as c:
            rows = [dict(r) for r in c.execute(
                '''SELECT g.*, l.name AS lead_name FROM revenue_growth g
                   LEFT JOIN leads l ON l.id=g.lead_id ORDER BY g.updated DESC LIMIT 40''')]
        return jsonify(items=rows, count=len(rows))

    @app.post('/api/os/growth/refresh')
    def os_growth_refresh():
        n = refresh_growth(db, now)
        log('growth', f'Refreshed post-delivery watches; {n} new offer(s)')
        return jsonify(created=n)

    @app.post('/api/os/backfill')
    def os_backfill():
        result = backfill(db, now)
        return jsonify(result)

    @app.get('/api/os/command')
    def os_command():
        return jsonify(command_center(db))

    @app.get('/api/os/metrics')
    def os_metrics():
        return jsonify(outcome_metrics(db))

    @app.get('/api/os/lead/<lid>/thread')
    def os_thread(lid):
        from web.opportunity import _lead
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        return jsonify(thread_for(db, lid))

    @app.post('/api/os/lead/<lid>/advance')
    def os_advance(lid):
        from web.opportunity import _lead
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        result = advance_to_proposal(db, lead, now)
        log('os', f"Advanced {lead.get('name')} → {result['steps']}")
        return jsonify(result)

    @app.post('/api/os/lead/<lid>/accept')
    def os_accept(lid):
        from web.opportunity import _lead
        lead = _lead(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        body = request.get_json(silent=True) or {}
        result, code = accept_proposal(db, lead, now, str(body.get('package_id') or 'growth'))
        if code != 200:
            return jsonify(result), code
        log('os', f"Accepted proposal for {lead.get('name')}")
        return jsonify(result)

    @app.post('/api/os/invoice/<iid>/paid')
    def os_paid(iid):
        with db() as c:
            inv = c.execute('SELECT lead_id FROM invoices WHERE id=?', (iid,)).fetchone()
        if not inv or not _client_owns_lead(db, inv['lead_id']):
            return jsonify(error='Invoice not found.'), 404
        result, code = mark_invoice_paid(db, iid, now)
        if code != 200:
            return jsonify(result), code
        log('os', f'Invoice {iid} marked Paid')
        return jsonify(result)

    @app.post('/api/os/project/<pid>/delivered')
    def os_delivered(pid):
        with db() as c:
            proj = c.execute('SELECT lead_id FROM projects WHERE id=?', (pid,)).fetchone()
        if not proj or not _client_owns_lead(db, proj['lead_id']):
            return jsonify(error='Project not found.'), 404
        result, code = mark_delivered(db, pid, now)
        if code != 200:
            return jsonify(result), code
        log('os', f'Project {pid} marked Delivered')
        return jsonify(result)
