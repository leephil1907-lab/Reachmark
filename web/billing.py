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

from flask import Response, redirect, render_template, request, jsonify, session
from web.i18n import t as _t, locale_now

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
        'name': 'Starter', 'rank': 1, 'usd_minor': 1900, 'ngn_minor': 3000000,
        'usd': '$19', 'ngn': '₦30,000',
        'usd_minor_annual': 19000, 'ngn_minor_annual': 30000000,
        'usd_annual': '$190', 'ngn_annual': '₦300,000', 'per': '30 days',
        'tag': 'Find businesses that need websites.',
        'features': ['Everything in Free', 'Lead directory: add, import & manage',
                     'Website health audits', 'Business discovery & map search', 'CSV exports'],
    },
    'pro': {
        'name': 'Pro', 'rank': 2, 'usd_minor': 5900, 'ngn_minor': 9000000,
        'usd': '$59', 'ngn': '₦90,000',
        'usd_minor_annual': 59000, 'ngn_minor_annual': 90000000,
        'usd_annual': '$590', 'ngn_annual': '₦900,000', 'per': '30 days',
        'tag': 'Outreach and automation, unlocked.',
        'features': ['Everything in Starter', 'Outreach composer & sending', 'AI crew campaigns',
                     'Review-link creation', 'Mail templates & outbox'],
    },
}
PERIOD_DAYS = 30
ANNUAL_DAYS = 365

def price_for(tier, currency, period):
    """Return (amount_minor, days) for a tier/currency/period combo."""
    t = TIERS[tier]
    if period == 'annual':
        key = 'usd_minor_annual' if currency == 'USD' else 'ngn_minor_annual'
        return t[key], ANNUAL_DAYS
    key = 'usd_minor' if currency == 'USD' else 'ngn_minor'
    return t[key], PERIOD_DAYS

# First regex match wins — specific rules before general ones. Anything not
# listed here stays owner-only (the guard answers 403 as before).
RULES = [
    (r'^/api/billing/checkout$', 'free'),
    (r'^/api/billing/crypto', 'free'),
    (r'^/api/billing/receipt', 'free'),
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
    (r'^/api/documents/audit', 'starter'),
    (r'^/api/state$', 'free'),
    (r'^/api/cards(/|$)', 'free'),
    (r'^/api/qr', 'free'),
    (r'^/api/events(/|$)', 'starter'),
    (r'^/api/scans(/|$)', 'starter'),
    (r'^/api/leads/[^/]+/followup$', 'pro'),
    (r'^/api/booking(/|$)', 'starter'),
    (r'^/api/book(/|$)', 'free'),
    (r'^/api/bookings(/|$)', 'starter'),
    (r'^/api/webhooks(/|$)', 'pro'),
    (r'^/api/auth/oauth', 'free'),
]


def ensure_billing(db):
    with db() as c:
        cols = {r[1] for r in c.execute('PRAGMA table_info(users)')}
        for col, typ in [('tier', "TEXT DEFAULT 'free'"), ('tier_expires', 'TEXT'),
                         ('paystack_customer', 'TEXT'), ('expiry_warned', 'TEXT')]:
            if col not in cols:
                c.execute(f'ALTER TABLE users ADD COLUMN {col} {typ}')
        c.execute("UPDATE users SET tier='free' WHERE tier IS NULL OR tier=''")
        c.execute('''CREATE TABLE IF NOT EXISTS payments(
            id TEXT PRIMARY KEY, user_id TEXT, email TEXT, tier TEXT, currency TEXT,
            amount_minor INTEGER, reference TEXT UNIQUE, status TEXT, paid_at TEXT,
            created TEXT, raw TEXT, tx_hash TEXT, coin_amount TEXT, coin_address TEXT,
            period TEXT DEFAULT 'monthly')''')
        pcols = {r[1] for r in c.execute('PRAGMA table_info(payments)')}
        if 'period' not in pcols:
            c.execute("ALTER TABLE payments ADD COLUMN period TEXT DEFAULT 'monthly'")


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
        raise BillingError(_t('pay.e_nopay', locale_now()))
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
            msg = json.load(e).get('message', _t('pay.e_prov', locale_now()))
        except Exception:
            msg = _t('pay.e_prov', locale_now())
        raise BillingError(msg)
    except Exception:
        raise BillingError(_t('pay.e_reach', locale_now()))
    if not out.get('status'):
        raise BillingError(out.get('message') or _t('pay.e_prov', locale_now()))
    return out['data']


def payments_configured():
    return bool(os.getenv('PAYSTACK_SECRET_KEY', '').strip())


_TIER_I18N = {
    'free': ('pay.t_free', 'pay.t_free_tag', 'pay.t_free_per',
             ['pay.t_free_f1', 'pay.t_free_f2', 'pay.t_free_f3', 'pay.t_free_f4', 'pay.t_free_f5']),
    'starter': ('pay.t_st', 'pay.t_st_tag', 'pay.t_st_per',
                ['pay.t_st_f1', 'pay.t_st_f2', 'pay.t_st_f3', 'pay.t_st_f4', 'pay.t_st_f5']),
    'pro': ('pay.t_pro', 'pay.t_pro_tag', 'pay.t_st_per',
            ['pay.t_pro_f1', 'pay.t_pro_f2', 'pay.t_pro_f3', 'pay.t_pro_f4', 'pay.t_pro_f5']),
}


def localized_tiers(locale=None):
    loc = locale or locale_now()
    out = {}
    for tid, tier in TIERS.items():
        nk, tk, pk, fks = _TIER_I18N[tid]
        row = dict(tier)
        row['name'] = _t(nk, loc)
        row['tag'] = _t(tk, loc)
        row['per'] = _t(pk, loc)
        row['features'] = [_t(fk, loc) for fk in fks]
        out[tid] = row
    return out


def public_prices():
    loc = locale_now()
    out = {}
    for k, v in TIERS.items():
        nk, tk, pk, fks = _TIER_I18N[k]
        out[k] = {'usd': v['usd'], 'ngn': v['ngn'], 'per': _t(pk, loc), 'name': _t(nk, loc),
                    'usd_annual': v.get('usd_annual', ''), 'ngn_annual': v.get('ngn_annual', '')}
    return out


def grant_tier(db, now, log, user_id, tier, days=PERIOD_DAYS):
    """Extend a user's plan by `days` from the later of now / current expiry."""
    with db() as c:
        row = c.execute('SELECT tier_expires FROM users WHERE id=?', (user_id,)).fetchone()
        current = (row['tier_expires'] or '') if row else ''
    stamp = now()
    base = current if current and current > stamp else stamp
    try:
        base_dt = datetime.fromisoformat(base)
    except ValueError:
        base_dt = datetime.now(timezone.utc)
    if base_dt.tzinfo is None:
        base_dt = base_dt.replace(tzinfo=timezone.utc)
    new_exp = (base_dt + timedelta(days=days)).isoformat()
    with db() as c:
        c.execute('UPDATE users SET tier=?,tier_expires=? WHERE id=?', (tier, new_exp, user_id))
    return new_exp


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
                try:
                    from web.accounts import get_base_url, send_branded
                    _fbase = get_base_url()
                    _floc = locale_now()
                    _ftier = localized_tiers(_floc).get(p['tier'], {}).get('name', p['tier'])
                    send_branded(p['email'], _t('au.m_f_sub', _floc),
                                 _t('au.m_f_body', _floc, tier=_ftier, ref=reference),
                                 html_title=_t('au.m_f_title', _floc), cta_url=f'{_fbase}/pricing',
                                 cta_label=_t('au.m_f_cta', _floc), db=db)
                except Exception:
                    pass
                return None
            try:
                paid_amount = int((verify_data or {}).get('amount') or 0)
            except (TypeError, ValueError):
                paid_amount = 0
            if paid_amount != (p['amount_minor'] or 0):
                c.execute('UPDATE payments SET status=?,raw=? WHERE reference=?',
                          ('mismatch', json.dumps(verify_data or {})[:4000], reference))
                return None
            stamp = now()
            c.execute('UPDATE payments SET status=?,paid_at=?,raw=? WHERE reference=?',
                      ('paid', stamp, json.dumps(verify_data or {})[:4000], reference))
        days = ANNUAL_DAYS if (p.get('period') or 'monthly') == 'annual' else PERIOD_DAYS
        grant_tier(db, now, log, p['user_id'], p['tier'], days)
        log('billing', f"{p['email']} upgraded to {p['tier']} ({p['currency']}).")
        try:
            from web.accounts import get_base_url, send_branded
            base = get_base_url()
            _bloc = locale_now()
            _tname = localized_tiers(_bloc)[p['tier']]['name']
            _rurl = f"{base}/api/billing/receipt/{reference}.pdf"
            send_branded(p['email'], _t('pay.mail_sub', _bloc, name=_tname),
                         _t('pay.mail_body', _bloc, email=p['email'], name=_tname, days=days,
                            ref=reference, url=_rurl),
                         html_title=_t('pay.mail_title', _bloc), cta_url=_rurl,
                         cta_label=_t('pay.mail_cta', _bloc), db=db)
        except Exception:
            pass
        p.update(status='paid', paid_at=stamp)
        return p

    @app.get('/pricing')
    def pricing_page():
        return render_template('pricing.html', tiers=localized_tiers(), configured=payments_configured())

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
            return jsonify(error=_t('pay.e_owner', locale_now())), 400
        cid = session.get('client_id')
        if not cid or session.get('role') != 'client':
            return jsonify(error=_t('pay.e_signin', locale_now())), 401
        v = request.get_json() or {}
        tier = str(v.get('tier', '')).lower()
        currency = str(v.get('currency', '')).upper()
        if tier not in ('starter', 'pro'):
            return jsonify(error=_t('pay.e_tier', locale_now())), 400
        if currency not in ('USD', 'NGN'):
            return jsonify(error=_t('pay.e_cur', locale_now())), 400
        period = str(v.get('period', 'monthly')).lower()
        if period not in ('monthly', 'annual'):
            return jsonify(error=_t('pay.e_period', locale_now())), 400
        with db() as c:
            row = c.execute('SELECT * FROM users WHERE id=? AND is_active=1', (cid,)).fetchone()
        if not row:
            session.clear()
            return jsonify(error=_t('pay.e_acct', locale_now())), 401
        user = dict(row)
        amount, _days = price_for(tier, currency, period)
        try:
            data = paystack_request('POST', '/transaction/initialize', {
                'email': user['email'], 'amount': amount, 'currency': currency,
                'reference': 'rm-' + uuid.uuid4().hex[:24],
                'callback_url': request.url_root.rstrip('/') + '/billing/callback',
                'metadata': {'user_id': cid, 'tier': tier, 'period': period, 'purpose': 'workspace-plan'}})
        except BillingError as e:
            return jsonify(error=str(e)), 503
        with db() as c:
            c.execute('INSERT INTO payments(id,user_id,email,tier,currency,amount_minor,reference,'
                      'status,paid_at,created,raw,period) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                      (uuid.uuid4().hex, cid, user['email'], tier, currency, amount,
                       data['reference'], 'pending', '', now(),
                       json.dumps({'method': 'paystack',
                                   'authorization_url': data.get('authorization_url')}),
                       period))
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
            return jsonify(error=_t('pay.e_sig', locale_now())), 401
        event = request.get_json(silent=True) or {}
        if event.get('event') == 'charge.success':
            data = event.get('data') or {}
            if data.get('reference'):
                activate(data['reference'], data)
        return jsonify(ok=True)

    @app.post('/api/cron/expiry-warnings')
    def cron_expiry_warnings():
        """Daily cron (Railway Cron Job): warn paid users expiring within 72h. Once per expiry."""
        secret = os.getenv('CRON_SECRET', '')
        supplied = request.headers.get('X-Cron-Secret', '') or (request.get_json(silent=True) or {}).get('secret', '')
        if not secret or not hmac.compare_digest(str(supplied), secret):
            return jsonify(error=_t('pay.e_sig', locale_now())), 401
        horizon = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
        with db() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM users WHERE tier IN ('starter','pro') AND tier_expires>? AND tier_expires<=? "
                'AND (expiry_warned IS NULL OR expiry_warned!=tier_expires)', (now(), horizon))]
        warned = 0
        try:
            from web.accounts import get_base_url, send_branded
            base = get_base_url()
            _cl = locale_now()
            for u in rows:
                try:
                    exp = datetime.fromisoformat(u['tier_expires'])
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=timezone.utc)
                    days = max(0, (exp - datetime.now(timezone.utc)).days)
                except Exception:
                    days = 0
                _tname = localized_tiers(_cl).get(u['tier'], {}).get('name', u['tier'])
                send_branded(u['email'], _t('au.m_x_sub', _cl, days=days, tier=_tname),
                             _t('au.m_x_body', _cl, days=days, tier=_tname),
                             html_title=_t('au.m_x_title', _cl), cta_url=f'{base}/pricing',
                             cta_label=_t('au.m_x_cta', _cl), db=db)
                with db() as c:
                    c.execute('UPDATE users SET expiry_warned=tier_expires WHERE id=?', (u['id'],))
                warned += 1
        except Exception:
            pass
        log('billing', f'Expiry warnings sent: {warned}')
        return jsonify(ok=True, warned=warned)

    @app.get('/api/billing/receipt/<reference>.pdf')
    def billing_receipt(reference):
        with db() as c:
            row = c.execute('SELECT * FROM payments WHERE reference=?', (reference[:64],)).fetchone()
        if not row:
            return jsonify(error=_t('pay.e_norect', locale_now())), 404
        p = dict(row)
        if not session.get('owner') and session.get('client_id') != p['user_id']:
            return jsonify(error=_t('rx.e_owner', locale_now())), 403
        if p['status'] != 'paid':
            return jsonify(error=_t('pay.e_nopdf', locale_now())), 400
        from web.documents import pdf
        try:
            meta = json.loads(p['raw'] or '{}')
        except Exception:
            meta = {}
        method = meta.get('method') or p['currency']
        _ploc = locale_now()
        if method == 'paystack':
            method = _t('pay.pdf_card', _ploc)
        elif method == 'manual':
            method = _t('pay.pdf_manual', _ploc)
        elif method == 'crypto':
            method = _t('pay.pdf_crypto', _ploc) + ' (' + str(meta.get('coin', '')).replace('_', ' ') + ')'
        amount = (_t('pay.pdf_recorded', _ploc) if p['currency'] == 'MANUAL'
                  else f"{p['currency']} {(p['amount_minor'] or 0) / 100:,.2f}")
        _pname = localized_tiers(_ploc).get(p['tier'], {}).get('name', p['tier'])
        _days = ANNUAL_DAYS if (p.get('period') or 'monthly') == 'annual' else PERIOD_DAYS
        blob = pdf(_t('pay.pdf_title', _ploc),
                   _t('pay.pdf_sub', _ploc, name=_pname),
                   [(_t('pay.pdf_plan', _ploc), f"{_pname} — {_t('pay.pdf_days', _ploc, n=_days)}"),
                    (_t('pay.pdf_amount', _ploc), amount), (_t('pay.pdf_ref', _ploc), p['reference']),
                    (_t('pay.pdf_paid', _ploc), p['paid_at'] or ''), (_t('pay.pdf_method', _ploc), method),
                    (_t('pay.pdf_bill', _ploc), p['email'])], now(), 'Reachmark', loc=_ploc)
        return Response(blob, mimetype='application/pdf', headers={
            'Content-Disposition': f"attachment; filename=reachmark-receipt-{p['reference'][:12]}.pdf"})
