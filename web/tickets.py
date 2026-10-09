"""Support tickets from signed-in clients. Mailed to support@ and listed for the owner."""
from __future__ import annotations

import uuid
from flask import jsonify, request, session

from web.accounts import send_branded, support_email


def register_tickets(app, db, now, log):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS support_tickets (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            email TEXT NOT NULL,
            name TEXT DEFAULT '',
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created TEXT NOT NULL)''')
        c.execute('CREATE INDEX IF NOT EXISTS support_tickets_created ON support_tickets(created)')

    def _client():
        if session.get('client_id') and session.get('role') == 'client':
            return session.get('client_id')
        return None

    @app.post('/api/support/tickets')
    def create_support_ticket():
        uid = _client()
        if not uid:
            return jsonify(error='Sign in to send a support ticket.'), 401
        payload = request.get_json(silent=True) or request.form or {}
        subject = (payload.get('subject') or '').strip()[:160]
        body = (payload.get('body') or '').strip()[:4000]
        if len(subject) < 3 or len(body) < 8:
            return jsonify(error='Write a subject and a short message.'), 400
        with db() as c:
            row = c.execute('SELECT email, name FROM users WHERE id=?', (uid,)).fetchone()
        if not row:
            return jsonify(error='Account not found.'), 401
        email, name = (row['email'] or '').strip().lower(), (row['name'] or '').strip()
        tid = uuid.uuid4().hex
        stamp = now()
        with db() as c:
            c.execute(
                'INSERT INTO support_tickets(id,user_id,email,name,subject,body,status,created) VALUES(?,?,?,?,?,?,?,?)',
                (tid, uid, email, name, subject, body, 'open', stamp),
            )
        dest = support_email()
        text = (
            f'From: {name or email} <{email}>\n'
            f'Subject: {subject}\n\n{body}\n\n'
            f'Ticket {tid} · signed-in client on reachmarkdigital.xyz'
        )
        try:
            send_branded(
                dest,
                f'Support ticket: {subject}',
                text,
                html_title='Support ticket',
                db=db,
            )
        except Exception:
            log('ticket', 'mail failed for ' + tid)
        log('ticket', f'{email} · {subject}')
        return jsonify(ok=True, id=tid, emailed_to=dest)

    @app.get('/api/support/tickets')
    def list_support_tickets():
        if not session.get('owner'):
            return jsonify(error='Owner only.'), 401
        with db() as c:
            rows = c.execute(
                'SELECT id, email, name, subject, body, status, created FROM support_tickets ORDER BY created DESC LIMIT 80'
            ).fetchall()
        return jsonify(tickets=[dict(r) for r in rows])

    @app.post('/api/support/tickets/<tid>/status')
    def update_support_ticket(tid):
        if not session.get('owner'):
            return jsonify(error='Owner only.'), 401
        payload = request.get_json(silent=True) or {}
        status = (payload.get('status') or '').strip().lower()
        if status not in ('open', 'closed'):
            return jsonify(error='Status is open or closed.'), 400
        with db() as c:
            cur = c.execute('UPDATE support_tickets SET status=? WHERE id=?', (status, tid))
            if cur.rowcount == 0:
                return jsonify(error='Not found.'), 404
        return jsonify(ok=True, id=tid, status=status)
