"""Manual crypto payments for workspace plans.

Deliberately human-verified (no chain node, no API keys):
1. A signed-in client picks a plan + coin and sees the studio wallet, a QR
   code and the USD amount (plus a live coin estimate when reachable).
2. The client pays from their own wallet, then pastes the transaction hash.
3. The owner confirms the coins in their wallet app and approves the
   payment in Clients & plans — the plan activates like any payment.

Wallet addresses come from environment variables so they never sit in
chat or code: BTC_WALLET, ETH_WALLET (also receives USDT on ERC20),
SOL_WALLET, USDT_TRC20_WALLET (a TRON address starting with T).
"""
import base64
import io
import json
import os
import time
import urllib.request
import uuid

from flask import jsonify, request, session

from web.billing import TIERS
from web.i18n import t as _t, locale_now

COINS = {
    'BTC': {'label': 'Bitcoin', 'coingecko': 'bitcoin', 'env': 'BTC_WALLET', 'decimals': 8,
            'note': 'Send BTC to this address.'},
    'ETH': {'label': 'Ethereum', 'coingecko': 'ethereum', 'env': 'ETH_WALLET', 'decimals': 6,
            'note': 'Send ETH to this address.'},
    'SOL': {'label': 'Solana', 'coingecko': 'solana', 'env': 'SOL_WALLET', 'decimals': 4,
            'note': 'Send SOL to this address.'},
    'USDT_ERC20': {'label': 'USDT · ERC20', 'coingecko': 'tether', 'env': 'ETH_WALLET', 'decimals': 2,
                   'note': 'USDT on the Ethereum network only — same address as ETH.'},
    'USDT_TRC20': {'label': 'USDT · TRC20', 'coingecko': 'tether', 'env': 'USDT_TRC20_WALLET',
                   'decimals': 2, 'note': 'USDT on the TRON network only.'},
}

_rates = {'at': 0.0, 'usd': {}}


def coin_prices():
    """USD price per coin, cached 10 minutes. Empty dict when unreachable."""
    if time.time() - _rates['at'] < 600 and _rates['usd']:
        return _rates['usd']
    try:
        req = urllib.request.Request(
            'https://api.coingecko.com/api/v3/simple/price'
            '?ids=bitcoin,ethereum,solana,tether&vs_currencies=usd',
            headers={'User-Agent': 'Reachmark/1.0'})
        with urllib.request.urlopen(req, timeout=12) as r:
            out = json.load(r)
        prices = {k: float(v['usd']) for k, v in out.items() if v.get('usd')}
        if prices:
            _rates.update(at=time.time(), usd=prices)
    except Exception:
        pass
    return _rates['usd']


def wallets():
    return {coin: os.getenv(meta['env'], '').strip() for coin, meta in COINS.items()}


def qr_data_uri(text):
    try:
        import qrcode
        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def ensure_crypto(db):
    with db() as c:
        cols = {r[1] for r in c.execute('PRAGMA table_info(payments)')}
        for col in ('tx_hash', 'coin_amount', 'coin_address'):
            if col not in cols:
                c.execute(f'ALTER TABLE payments ADD COLUMN {col} TEXT')


def _client_id():
    if session.get('owner'):
        return 'owner'
    if session.get('client_id') and session.get('role') == 'client':
        return session.get('client_id')
    return None


def register_crypto(app, db, now, log):
    ensure_crypto(db)

    def quote(tier):
        usd = TIERS[tier]['usd_minor'] / 100
        prices = coin_prices()
        options = []
        for coin, meta in COINS.items():
            addr = wallets()[coin]
            if not addr:
                continue
            px = prices.get(meta['coingecko']) or 0
            amount = round(usd / px, meta['decimals']) if px else None
            _ck = {'BTC': 'pay.coin_btc', 'ETH': 'pay.coin_eth', 'SOL': 'pay.coin_sol',
                   'USDT_ERC20': 'pay.coin_usdt_e', 'USDT_TRC20': 'pay.coin_usdt_t'}[coin]
            options.append({'coin': coin, 'label': meta['label'], 'address': addr,
                            'qr': qr_data_uri(addr), 'usd': usd, 'coin_amount': amount,
                            'note': _t(_ck, locale_now())})
        return options

    @app.get('/api/billing/crypto')
    def crypto_options():
        who = _client_id()
        if not who:
            return jsonify(error=_t('pay.c_signin', locale_now())), 401
        tier = (request.args.get('tier') or '').lower()
        if tier not in ('starter', 'pro'):
            return jsonify(error=_t('pay.e_tier', locale_now())), 400
        return jsonify(tier=tier, coins=quote(tier))

    @app.post('/api/billing/crypto/checkout')
    def crypto_checkout():
        who = _client_id()
        if not who or who == 'owner':
            return jsonify(error=_t('pay.c_client', locale_now())), 401
        v = request.get_json() or {}
        tier = str(v.get('tier', '')).lower()
        coin = str(v.get('coin', '')).upper()
        if tier not in ('starter', 'pro') or coin not in COINS:
            return jsonify(error=_t('pay.c_pick', locale_now())), 400
        addr = wallets()[coin]
        if not addr:
            return jsonify(error=_t('pay.c_off', locale_now())), 400
        with db() as c:
            row = c.execute('SELECT * FROM users WHERE id=? AND is_active=1', (who,)).fetchone()
        if not row:
            session.clear()
            return jsonify(error=_t('pay.e_acct', locale_now())), 401
        option = next(o for o in quote(tier) if o['coin'] == coin)
        ref = 'crypto-' + uuid.uuid4().hex[:20]
        amount = TIERS[tier]['usd_minor']
        with db() as c:
            c.execute('INSERT INTO payments(id,user_id,email,tier,currency,amount_minor,reference,'
                      'status,paid_at,created,raw,tx_hash,coin_amount,coin_address) '
                      'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (uuid.uuid4().hex, who, dict(row)['email'], tier, coin, amount, ref,
                       'pending', '', now(), json.dumps({'method': 'crypto', 'coin': coin,
                                                         'address': addr, 'coin_amount': option['coin_amount'],
                                                         'usd': option['usd']}), '', str(option['coin_amount'] or ''), addr))
        log('billing', f'Crypto checkout started: {tier} via {coin}.')
        return jsonify(reference=ref, coin=coin, label=option['label'], address=addr,
                       qr=option['qr'], usd=option['usd'], coin_amount=option['coin_amount'],
                       note=option['note'])

    @app.post('/api/billing/crypto/submit')
    def crypto_submit():
        who = _client_id()
        if not who or who == 'owner':
            return jsonify(error=_t('pay.c_client', locale_now())), 401
        v = request.get_json() or {}
        ref = str(v.get('reference', ''))[:64]
        tx = str(v.get('tx_hash', '')).strip()
        if len(tx) < 16 or len(tx) > 200:
            return jsonify(error=_t('pay.c_tx', locale_now())), 400
        with db() as c:
            row = c.execute('SELECT * FROM payments WHERE reference=? AND user_id=?',
                            (ref, who)).fetchone()
            if not row:
                return jsonify(error=_t('pay.c_nopay', locale_now())), 404
            if dict(row)['status'] != 'pending':
                return jsonify(error=_t('pay.c_dup', locale_now())), 400
            c.execute("UPDATE payments SET tx_hash=?,status='awaiting_approval' WHERE reference=?",
                      (tx, ref))
        log('billing', f'Crypto payment {ref} awaiting owner approval.')
        return jsonify(ok=True, message=_t('pay.c_ok', locale_now()))
