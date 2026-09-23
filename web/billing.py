"""Workspace plans: Free / Starter / Pro access tiers with Paystack checkout.

Straightforward model: one verified payment = 30 days on that tier.
No subscription objects and no dashboard plan codes — each successful
charge simply extends ``users.tier_expires`` by 30 days.

Prices live in TIERS below (minor units: kobo for NGN, cents for USD).
"""
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from flask import redirect, render_template, request, jsonify, session

TIERS = {
    'free': {
        'name': 'Free', 'rank': 0, 'usd_minor': 0, 'ngn_minor': 0,
        'usd': '$0', 'ngn': '₦0', 'per': 'forever',
        'tag': 'Look around and stay in touch.',
        'features': ['Website samples gallery', 'Project enquiry form',
                     'Review links you are invited to', 'Your invoices, projects & documents',
                     'Workspace overview stats'],
    },
    'starter': {
        'name': 'Starter', 'rank': 1, 'usd_minor': 900, 'ngn_minor': 1200000,
        'usd': '$9', 'ngn': '₦12,000', 'per': '30 days',
        'tag': 'Find businesses that need websites.',
        'features': ['Everything in Free', 'Lead directory: add, import & manage',
                     'Website health audits', 'Business discovery & map search', 'CSV exports'],
    },
    'pro': {
        'name': 'Pro', 'rank': 2, 'usd_minor': 2900, 'ngn_minor': 4000000,
        'usd': '$29', 'ngn': '₦40,000', 'per': '30 days',
        'tag': 'Outreach and automation, unlocked.',
        'features': ['Everything in Starter', 'Outreach composer & sending', 'AI crew campaigns',
                     'Review-link creation', 'Mail templates & outbox'],
    },
}
PERIOD_DAYS = 30

# First regex match wins — specific rules before general ones. Anything not
# listed here stays owner-only (the guard answers 403 as before).
RULES = [
    (r'^/api/billing/checkout$', 'free'),
    (r'^/api/leads/[^/]+/(send|compose|suppress)$', 'pro'),
    (r'^/api/leads(/|$)', 'starter'),
    (r'^/api/(import|export|discover|jobs|map)(/|$)', 'starter'),
    (r'^/api/(outbox|mail-templates|crew|review-links)(/|$)', 'pro'),
    (r'^/api/analytics', 'free'),
    (r'^/api/operations/readiness', 'free'),
    (r'^/api/quality', 'starter'),  # raw directory rows: paying members only
    (r'^/api/auth/(me|logout|export|close|request-verification)', 'free'),
    (r'^/api/(invoices|projects)(/|$)', 'free'),
    (r'^/api/documents/(invoice|brief|proposal)(/|$)', 'free'),
    (r'^/api/state$', 'free'),
]


def ensure_billing(db):
    with db() as c:
        cols = {r[1] for r in c.execute('PRAGMA table_info(users)')}
        for col, typ in [('tier', "TEXT DEFAULT 'free'"), ('tier_expires', 'TEXT'),
                         ('paystack_customer', 'TEXT')]:
            if col not in cols:
                c.execute(f'ALTER TABLE users ADD COLUMN {col} {typ}')
        c.execute("UPDATE users SET tier='free' WHERE tier IS NULL OR tier=''")
        c.execute('''CREATE TABLE IF NOT EXISTS payments(
            id TEXT PRIMARY KEY, user_id TEXT, email TEXT, tier TEXT, currency TEXT,
            amount_minor INTEGER, reference TEXT UNIQUE, status TEXT, paid_at TEXT,
            created TEXT, raw TEXT)''')


def tier_status(user):
    """Return (effective_tier, active, expires) for a users row (or None)."""
    t = ((user.get('tier') or 'free').lower() if user else 'free')
    if t not in TIERS:
        t = 'free'
    exp = (user.get('tier_expires') or '') if user else ''
    active = t != 'free' and bool(exp) and exp > datetime.now(timezone.utc).isoformat()
    return (t if (active or t == 'free') else 'free'), active, exp


def check_client_path(path, effective_tier):
    """Return ('ok'|'upgrade'|'deny', tier_needed) for a client request path."""
    rank = TIERS.get(effective_tier, TIERS['free'])['rank']
    for pattern, need in RULES:
        if re.match(pattern, path):
            if rank >= TIERS[need]['rank']:
                return 'ok', need
            return 'upgrade', need
    return 'deny', 'owner'


class BillingError(Exception):
    pass


def paystack_request(method, path, payload=None):
    """Call the Paystack API with the secret key. Separated for test stubbing."""
    secret = os.getenv('PAYSTACK_SECRET_KEY', '').strip()
    if not secret:
        raise BillingError('Payments are not connected yet. The studio is finishing setup.')
    req = urllib.request.Request(
        'https://api.paystack.co' + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get('message', 'Payment provider error.')
        except Exception:
            msg = 'Payment provider error.'
        raise BillingError(msg)
    except Exception:
        raise BillingError('Could not reach the payment provider. Try again.')
    if not out.get('status'):
        raise BillingError(out.get('message') or 'Payment provider error.')
    return out['data']


def payments_configured():
    return bool(os.getenv('PAYSTACK_SECRET_KEY', '').strip())


def public_prices():
    return {k: {'usd': v['usd'], 'ngn': v['ngn'], 'per': v['per'], 'name': v['name']}
            for k, v in TIERS.items()}


def register_billing(app, db, now, log):
    ensure_billing(db)

    def activate(reference, verify_data):
        """Mark a pending payment paid and extend the tier. Idempotent."""
        with db() as c:
            row = c.execute('SELECT * FROM payments WHERE reference=?', (reference,)).fetchone()
            if not row:
                return None
            p = dict(row)
            if p['status'] == 'paid':
                return p
            if (verify_data or {}).get('status') != 'success':
                c.execute('UPDATE payments SET status=?,raw=? WHERE reference=?',
                          ('failed', json.dumps(verify_data or {})[:4000], reference))
                return None
            try:
                paid_amount = int((verify_data or {}).get('amount') or 0)
            except (TypeError, ValueError):
                paid_amount = 0
            if paid_amount != (p['amount_minor'] or 0):
                c.execute('UPDATE payments SET status=?,raw=? WHERE reference=?',
                          ('mismatch', json.dumps(verify_data or {})[:4000], reference))
                return None
            current = ''
            user = c.execute('SELECT tier_expires FROM users WHERE id=?', (p['user_id'],)).fetchone()
            if user:
                current = user['tier_expires'] or ''
            stamp = now()
            base = current if current and current > stamp else stamp
            try:
                base_dt = datetime.fromisoformat(base)
            except ValueError:
                base_dt = datetime.now(timezone.utc)
            if base_dt.tzinfo is None:
                base_dt = base_dt.replace(tzinfo=timezone.utc)
            new_exp = (base_dt + timedelta(days=PERIOD_DAYS)).isoformat()
            c.execute('UPDATE payments SET status=?,paid_at=?,raw=? WHERE reference=?',
                      ('paid', stamp, json.dumps(verify_data or {})[:4000], reference))
            c.execute('UPDATE users SET tier=?,tier_expires=? WHERE id=?',
                      (p['tier'], new_exp, p['user_id']))
        log('billing', f"{p['email']} upgraded to {p['tier']} ({p['currency']}).")
        p.update(status='paid', paid_at=stamp)
        return p

    @app.get('/pricing')
    def pricing_page():
        return render_template('pricing.html', tiers=TIERS, configured=payments_configured())

    @app.get('/api/billing/status')
    def billing_status():
        if session.get('owner'):
            return jsonify(authenticated=True, role='owner', tier='owner', tier_active=True,
                           configured=payments_configured(), prices=public_prices())
        cid = session.get('client_id')
        if cid and session.get('role') == 'client':
            with db() as c:
                row = c.execute('SELECT * FROM users WHERE id=?', (cid,)).fetchone()
            if row:
                t, active, exp = tier_status(dict(row))
                return jsonify(authenticated=True, role='client', tier=t, tier_active=active,
                               tier_expires=exp, configured=payments_configured(),
                               prices=public_prices())
        return jsonify(authenticated=False, configured=payments_configured(),
                       prices=public_prices())

    @app.post('/api/billing/checkout')
    def billing_checkout():
        if session.get('owner'):
            return jsonify(error='The owner account already has full access.'), 400
        cid = session.get('client_id')
        if not cid or session.get('role') != 'client':
            return jsonify(error='Sign in to choose a plan.'), 401
        v = request.get_json() or {}
        tier = str(v.get('tier', '')).lower()
        currency = str(v.get('currency', '')).upper()
        if tier not in ('starter', 'pro'):
            return jsonify(error='Choose the Starter or Pro plan.'), 400
        if currency not in ('USD', 'NGN'):
            return jsonify(error='Choose USD or NGN.'), 400
        with db() as c:
            row = c.execute('SELECT * FROM users WHERE id=? AND is_active=1', (cid,)).fetchone()
        if not row:
            session.clear()
            return jsonify(error='Account not found. Sign in again.'), 401
        user = dict(row)
        amount = TIERS[tier]['usd_minor' if currency == 'USD' else 'ngn_minor']
        try:
            data = paystack_request('POST', '/transaction/initialize', {
                'email': user['email'], 'amount': amount, 'currency': currency,
                'reference': 'rm-' + uuid.uuid4().hex[:24],
                'callback_url': request.url_root.rstrip('/') + '/billing/callback',
                'metadata': {'user_id': cid, 'tier': tier, 'purpose': 'workspace-plan'}})
        except BillingError as e:
            return jsonify(error=str(e)), 503
        with db() as c:
            c.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (uuid.uuid4().hex, cid, user['email'], tier, currency, amount,
                       data['reference'], 'pending', '', now(),
                       json.dumps({'authorization_url': data.get('authorization_url')})))
        return jsonify(authorization_url=data['authorization_url'], reference=data['reference'])

    @app.get('/billing/callback')
    def billing_callback():
        ref = (request.args.get('reference') or '')[:64]
        if not ref:
            return redirect('/pricing?error=missing')
        try:
            data = paystack_request('GET', '/transaction/verify/' + ref)
        except BillingError:
            return redirect('/pricing?error=verify')
        if activate(ref, data):
            return redirect('/dashboard?upgraded=1')
        return redirect('/pricing?error=payment')

    @app.post('/api/billing/webhook')
    def billing_webhook():
        secret = os.getenv('PAYSTACK_SECRET_KEY', '')
        sig = request.headers.get('x-paystack-signature', '')
        good = secret and sig and hmac.compare_digest(
            sig, hmac.new(secret.encode(), request.get_data(), hashlib.sha512).hexdigest())
        if not good:
            return jsonify(error='Bad signature.'), 401
        event = request.get_json(silent=True) or {}
        if event.get('event') == 'charge.success':
            data = event.get('data') or {}
            if data.get('reference'):
                activate(data['reference'], data)
        return jsonify(ok=True)
