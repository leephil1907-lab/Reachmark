"""Funnel events from real inserts only.

Counts on dashboards come from this table (and existing sends / leads / reports).
Nothing here is estimated, forecast, or filled in for empty days.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid

from flask import jsonify, request, session

EVENTS = (
    'visit',
    'sample_viewed',
    'enquiry',
    'audit_started',
    'audit_completed',
    'report_viewed',
    'signup',
    'first_lead_opened',
    'first_send_approved',
)
PUBLIC_COOLDOWN_SEC = {
    'visit': 3600,
    'sample_viewed': 3600,
}

FIRST_ONLY = frozenset(('first_lead_opened', 'first_send_approved'))


def ensure_tables(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS funnel_events(
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            user_id TEXT,
            ip_hash TEXT,
            meta TEXT NOT NULL,
            created TEXT NOT NULL)''')
        c.execute('CREATE INDEX IF NOT EXISTS funnel_name_created ON funnel_events(name, created)')
        c.execute('CREATE INDEX IF NOT EXISTS funnel_user ON funnel_events(user_id, name)')


def _ip_hash():
    raw = (request.headers.get('X-Forwarded-For') or request.remote_addr or '').split(',')[0].strip()
    if not raw:
        return ''
    salt = os.getenv('SECRET_KEY') or os.getenv('ADMIN_PASSWORD') or 'reachmark'
    return hashlib.sha256((salt + '|' + raw).encode()).hexdigest()[:32]


def _actor():
    return session.get('client_id') or (session.get('owner') and 'owner') or None


def record(db, now, name, meta=None, user_id=None):
    """Insert one named event. first_* events insert at most once per user."""
    if name not in EVENTS:
        return None
    uid = user_id if user_id is not None else _actor()
    payload = json.dumps(meta or {}, ensure_ascii=False)[:2000]
    with db() as c:
        if name in FIRST_ONLY and uid:
            exists = c.execute(
                'SELECT 1 FROM funnel_events WHERE name=? AND user_id=? LIMIT 1',
                (name, uid),
            ).fetchone()
            if exists:
                return None
        cool = PUBLIC_COOLDOWN_SEC.get(name)
        if cool:
            from datetime import datetime, timedelta, timezone
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=cool)).isoformat()
            iph = _ip_hash()
            if iph and c.execute(
                'SELECT 1 FROM funnel_events WHERE name=? AND ip_hash=? AND created>=? LIMIT 1',
                (name, iph, cutoff),
            ).fetchone():
                return None
        eid = uuid.uuid4().hex
        c.execute(
            'INSERT INTO funnel_events(id,name,user_id,ip_hash,meta,created) VALUES(?,?,?,?,?,?)',
            (eid, name, uid, _ip_hash(), payload, now()),
        )
    return eid


def counts(db):
    """Real row counts. Missing events stay at 0 — never invented."""
    with db() as c:
        rows = c.execute(
            'SELECT name, count(*) AS n FROM funnel_events GROUP BY name'
        ).fetchall()
    out = {name: 0 for name in EVENTS}
    for row in rows:
        out[row['name']] = int(row['n'])
    return out


def register_funnel(app, db, now, log):
    ensure_tables(db)

    @app.get('/api/funnel/summary')
    def funnel_summary():
        if not session.get('owner'):
            return jsonify(error='Owner only.'), 403
        return jsonify(events=counts(db))

    @app.post('/api/funnel/event')
    def funnel_event():
        if not (session.get('owner') or session.get('client_id')):
            return jsonify(error='Sign in first.'), 401
        body = request.get_json(silent=True) or {}
        name = str(body.get('name') or '').strip()
        if name not in FIRST_ONLY and name not in EVENTS:
            return jsonify(error='Unknown event.'), 400
        # Clients may only record first_* from the workspace, not arbitrary names.
        if not session.get('owner') and name not in FIRST_ONLY:
            return jsonify(error='Not allowed.'), 403
        eid = record(db, now, name, meta=body.get('meta') if isinstance(body.get('meta'), dict) else {})
        return jsonify(ok=True, id=eid)
