"""Studio console: client records, manual plan control, newsletter list.

The owner manages every registered user here: grant or revoke plans by
hand (bank transfer, crypto approval, goodwill), pause accounts, and
review the payment log. Clients never reach these endpoints.
"""
import csv
import io
import json
import os
import uuid

from flask import Response, jsonify, request, session
from web.i18n import t as _t, locale_now

from web.accounts import send_branded, valid_email
from web.agent_tools import owner_locked
from web.billing import ANNUAL_DAYS, PERIOD_DAYS, TIERS, grant_tier


def ensure_console(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS newsletter_subscribers(
            email TEXT PRIMARY KEY, source TEXT, active INTEGER DEFAULT 1, created TEXT)''')


def _denied():
    if owner_locked() and not session.get('owner'):
        return jsonify(error=_t('er_083', locale_now())), 403
    return None


def register_console(app, db, now, log):
    ensure_console(db)

    @app.post('/api/newsletter')
    def newsletter_subscribe():
        v = request.get_json(silent=True) or {}
        email = str(v.get('email', '')).strip().lower()
        if not valid_email(email):
            return jsonify(error=_t('au.e_email', locale_now())), 400
        source = str(v.get('source', ''))[:120]
        with db() as c:
            c.execute('INSERT INTO newsletter_subscribers VALUES(?,?,1,?) '
                      'ON CONFLICT(email) DO UPDATE SET active=1', (email, source, now()))
        try:
            base = os.getenv('PUBLIC_BASE_URL', '').strip().rstrip('/') or request.host_url.rstrip('/')
            _nl = locale_now()
            send_branded(email, _t('au.m_n_sub', _nl),
                         _t('au.m_n_body', _nl, email=email),
                         html_title=_t('au.m_n_title', _nl), cta_url=f'{base}/showcase',
                         cta_label=_t('au.m_n_cta', _nl), db=db)
        except Exception:
            pass
        return jsonify(ok=True, message=_t('au.m_n_ok', locale_now()))

    @app.get('/api/admin/users')
    def admin_users():
        if (denied := _denied()):
            return denied
        q = '%' + (request.args.get('q') or '').strip().lower() + '%'
        with db() as c:
            rows = [dict(r) for r in c.execute(
                'SELECT id,email,name,role,created,email_verified,is_active,tier,tier_expires FROM users '
                'WHERE lower(email) LIKE ? OR lower(name) LIKE ? ORDER BY created DESC LIMIT 200', (q, q))]
            for r in rows:
                r['payments'] = [dict(p) for p in c.execute(
                    'SELECT reference,tier,currency,amount_minor,status,paid_at,created,tx_hash '
                    'FROM payments WHERE user_id=? ORDER BY created DESC LIMIT 10', (r['id'],))]
        return jsonify(users=rows)

    @app.patch('/api/admin/users/<uid>')
    def admin_update_user(uid):
        if (denied := _denied()):
            return denied
        v = request.get_json(silent=True) or {}
        with db() as c:
            row = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            if not row:
                return jsonify(error=_t('er_152', locale_now())), 404
            user = dict(row)
        if 'is_active' in v:
            with db() as c:
                c.execute('UPDATE users SET is_active=? WHERE id=?',
                          (1 if v['is_active'] else 0, uid))
        tier = str(v.get('tier', '')).lower()
        if tier:
            if tier not in TIERS:
                return jsonify(error=_t('er_147', locale_now())), 400
            try:
                days = max(1, min(int(v.get('days', PERIOD_DAYS)), 3650))
            except (TypeError, ValueError):
                days = PERIOD_DAYS
            if tier == 'free':
                with db() as c:
                    c.execute("UPDATE users SET tier='free',tier_expires='' WHERE id=?", (uid,))
            else:
                grant_tier(db, now, log, uid, tier, days)
                with db() as c:
                    c.execute('INSERT INTO payments(id,user_id,email,tier,currency,amount_minor,'
                              'reference,status,paid_at,created,raw,tx_hash,coin_amount,coin_address) '
                              'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                              (uuid.uuid4().hex, uid, user['email'], tier, 'MANUAL', 0,
                               'manual-' + uuid.uuid4().hex[:16], 'paid', now(), now(),
                               json.dumps({'method': 'manual', 'days': days,
                                           'note': str(v.get('note', ''))[:300]}), '', '', ''))
            log('billing', f"Owner set {user['email']} to {tier}.")
        return jsonify(ok=True)

    @app.get('/api/admin/payments')
    def admin_payments():
        if (denied := _denied()):
            return denied
        status = (request.args.get('status') or '').strip()
        with db() as c:
            if status:
                rows = [dict(r) for r in c.execute(
                    'SELECT * FROM payments WHERE status=? ORDER BY created DESC LIMIT 100', (status,))]
            else:
                rows = [dict(r) for r in c.execute(
                    'SELECT * FROM payments ORDER BY created DESC LIMIT 100')]
        return jsonify(payments=rows)

    @app.post('/api/admin/payments/<ref>/approve')
    def admin_approve(ref):
        if (denied := _denied()):
            return denied
        with db() as c:
            row = c.execute('SELECT * FROM payments WHERE reference=?', (ref[:64],)).fetchone()
            if not row:
                return jsonify(error=_t('er_086', locale_now())), 404
            p = dict(row)
            if p['status'] == 'paid':
                return jsonify(ok=True, already=True)
            if p['status'] not in ('pending', 'awaiting_approval'):
                return jsonify(error=_t('er_081', locale_now())), 400
            c.execute("UPDATE payments SET status='paid',paid_at=? WHERE reference=?",
                      (now(), p['reference']))
        _days = ANNUAL_DAYS if (p.get('period') or 'monthly') == 'annual' else PERIOD_DAYS
        grant_tier(db, now, log, p['user_id'], p['tier'], _days)
        log('billing', f"Owner approved {p['reference']} ({p['email']} → {p['tier']}).")
        return jsonify(ok=True)

    @app.post('/api/admin/payments/<ref>/reject')
    def admin_reject(ref):
        if (denied := _denied()):
            return denied
        with db() as c:
            row = c.execute('SELECT * FROM payments WHERE reference=?', (ref[:64],)).fetchone()
            if not row:
                return jsonify(error=_t('er_086', locale_now())), 404
            if dict(row)['status'] == 'paid':
                return jsonify(error=_t('er_084', locale_now())), 400
            c.execute("UPDATE payments SET status='rejected' WHERE reference=?", (dict(row)['reference'],))
        log('billing', f"Owner rejected {dict(row)['reference']}.")
        return jsonify(ok=True)

    @app.get('/api/admin/newsletter')
    def admin_newsletter():
        if (denied := _denied()):
            return denied
        with db() as c:
            rows = [dict(r) for r in c.execute(
                'SELECT email,source,active,created FROM newsletter_subscribers ORDER BY created DESC LIMIT 500')]
        return jsonify(subscribers=rows)

    @app.get('/api/admin/newsletter/export')
    def admin_newsletter_export():
        if (denied := _denied()):
            return denied
        with db() as c:
            rows = c.execute('SELECT email,source,active,created FROM newsletter_subscribers ORDER BY created').fetchall()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['email', 'source', 'active', 'created'])
        w.writerows(rows)
        return Response(buf.getvalue(), mimetype='text/csv',
                        headers={'Content-Disposition': 'attachment; filename=reachmark-newsletter.csv'})
