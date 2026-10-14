"""Admin activity: what visitors and customers did on the website.

The admin console (/admin) polls this every few seconds, so a new sign-up,
enquiry, payment or front-desk hand-off shows up without a reload.

Everything here is read from rows the app already writes:
- users                 -> sign-ups, verification, plans
- activity (log())      -> sign-ins, enquiries, payments, reviews, unsubscribes ...
- funnel_events         -> 7-day visits, free checks, report views
Nothing is estimated or back-filled.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import jsonify, request

# activity.kind values that describe something a visitor or customer did.
USER_KINDS = ('account', 'billing', 'enquiry', 'receptionist', 'review', 'ticket',
              'newsletter', 'public-audit', 'suppression', 'onboard')

# Rows of those kinds that are really the owner's own actions or system jobs.
NOT_USER_ACTIVITY = ('Owner %', 'Receptionist thread marked%', 'Manual business verification%',
                     'Expiry warnings sent%', 'public audit failed%')

FEED_LIMIT = 80


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _table_exists(c, name):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _columns(c, table):
    return {r[1] for r in c.execute(f'PRAGMA table_info({table})')}


def snapshot(db, since_id=0):
    now = datetime.now(timezone.utc)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    out = {'generated': _iso(now)}
    with db() as c:
        # --- people -------------------------------------------------------
        cols = _columns(c, 'users') if _table_exists(c, 'users') else set()
        if cols:
            one = lambda sql, *a: c.execute(sql, a).fetchone()[0]  # noqa: E731
            base = "FROM users WHERE role='client'"
            out['users'] = {
                'total': one(f'SELECT count(*) {base}'),
                'today': one(f'SELECT count(*) {base} AND created>=?', _iso(start_today)),
                'week': one(f'SELECT count(*) {base} AND created>=?', _iso(week)),
                'verified': one(f'SELECT count(*) {base} AND email_verified=1') if 'email_verified' in cols else 0,
                'paying': one(f"SELECT count(*) {base} AND coalesce(tier,'free') NOT IN ('','free')") if 'tier' in cols else 0,
            }
            pick = ['id', 'email', 'name', 'created'] + [k for k in ('email_verified', 'is_active', 'tier', 'oauth_google_sub') if k in cols]
            rows = c.execute(f"SELECT {','.join(pick)} {base} ORDER BY created DESC LIMIT 12").fetchall()
            signups = []
            for r in rows:
                d = dict(r)
                d['via'] = 'Google' if d.pop('oauth_google_sub', None) else 'Email'
                signups.append(d)
            out['signups'] = signups
        else:
            out['users'] = {'total': 0, 'today': 0, 'week': 0, 'verified': 0, 'paying': 0}
            out['signups'] = []

        # --- 7-day website numbers -----------------------------------------
        week_counts = {}
        if _table_exists(c, 'funnel_events'):
            for r in c.execute('SELECT name, count(*) AS n FROM funnel_events WHERE created>=? GROUP BY name', (_iso(week),)):
                week_counts[r['name']] = r['n']
        if _table_exists(c, 'enquiries'):
            week_counts['enquiry'] = c.execute('SELECT count(*) FROM enquiries WHERE created>=?', (_iso(week),)).fetchone()[0]
        out['week'] = {
            'visits': week_counts.get('visit', 0),
            'checks': week_counts.get('audit_completed', 0),
            'enquiries': week_counts.get('enquiry', 0),
            'reports': week_counts.get('report_viewed', 0) + week_counts.get('sample_viewed', 0),
        }

        # --- live feed -----------------------------------------------------
        feed = []
        if _table_exists(c, 'activity'):
            marks = ','.join('?' * len(USER_KINDS))
            nots = ' '.join('AND message NOT LIKE ?' for _ in NOT_USER_ACTIVITY)
            feed = [dict(r) for r in c.execute(
                f'SELECT id, kind, message, created FROM activity WHERE kind IN ({marks}) {nots} '
                'ORDER BY id DESC LIMIT ?', (*USER_KINDS, *NOT_USER_ACTIVITY, FEED_LIMIT))]
        out['feed'] = feed
        out['latest_id'] = feed[0]['id'] if feed else 0
        out['new_since'] = sum(1 for f in feed if f['id'] > since_id) if since_id else 0
    return out


def register_admin_activity(app, db):
    @app.get('/api/admin/activity')
    def admin_activity():
        if not app._owner_ok():
            return jsonify(error='Owner only.'), 401
        try:
            since = int(request.args.get('since') or 0)
        except ValueError:
            since = 0
        return jsonify(snapshot(db, since))
