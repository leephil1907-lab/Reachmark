"""Social sign-in (Google / Microsoft) for client accounts.

Providers appear ONLY when their env credentials are configured:
  GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET
  MICROSOFT_CLIENT_ID + MICROSOFT_CLIENT_SECRET
With nothing configured, /api/auth/oauth reports all providers unconfigured
and the auth pages render no social buttons at all.
Owner workspace sign-in stays password-only by design.
"""
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
import uuid

from flask import jsonify, redirect, request, session

from .i18n import t as _t, locale_now

PROVIDERS = {
    'google': {
        'name': 'Google',
        'auth': 'https://accounts.google.com/o/oauth2/v2/auth',
        'token': 'https://oauth2.googleapis.com/token',
        'userinfo': 'https://openidconnect.googleapis.com/v1/userinfo',
        'scope': 'openid email profile',
        'id_key': 'GOOGLE_CLIENT_ID', 'secret_key': 'GOOGLE_CLIENT_SECRET',
    },
    'microsoft': {
        'name': 'Microsoft',
        'auth': 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
        'token': 'https://login.microsoftonline.com/common/oauth2/v2.0/token',
        'userinfo': 'https://graph.microsoft.com/v1.0/me',
        'scope': 'openid email profile User.Read',
        'id_key': 'MICROSOFT_CLIENT_ID', 'secret_key': 'MICROSOFT_CLIENT_SECRET',
    },
}


def configured(p):
    return bool(os.environ.get(p['id_key'], '').strip() and os.environ.get(p['secret_key'], '').strip())


def _redirect_uri(provider):
    return request.url_root.rstrip('/') + f'/api/auth/oauth/{provider}/callback'


def _http_json(url, data=None, headers=None, timeout=8):
    body = urllib.parse.urlencode(data).encode() if isinstance(data, dict) else data
    req = urllib.request.Request(url, data=body, headers=headers or {}, method='POST' if body else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def register_oauth(app, db, now, log):
    @app.get('/api/auth/oauth')
    def oauth_status():
        return jsonify(providers=[
            {'id': pid, 'name': p['name'], 'configured': configured(p)}
            for pid, p in PROVIDERS.items()])

    @app.get('/api/auth/oauth/<provider>')
    def oauth_start(provider):
        p = PROVIDERS.get(provider)
        if not p:
            return jsonify(error=_t('au.e_oauth_unknown', locale_now())), 404
        if not configured(p):
            return jsonify(error=_t('au.e_oauth_off', locale_now())), 400
        mode = request.args.get('mode', 'signin')
        if mode not in ('signin', 'signup'):
            mode = 'signin'
        state = secrets.token_urlsafe(24)
        pending = session.get('oauth_pending') or {}
        pending[state] = {'provider': provider, 'mode': mode, 'ts': time.time()}
        session['oauth_pending'] = pending
        q = urllib.parse.urlencode({
            'client_id': os.environ[p['id_key']].strip(),
            'redirect_uri': _redirect_uri(provider),
            'response_type': 'code', 'scope': p['scope'], 'state': state,
        })
        return redirect(p['auth'] + '?' + q, 302)

    @app.get('/api/auth/oauth/<provider>/callback')
    def oauth_callback(provider):
        p = PROVIDERS.get(provider)
        state = request.args.get('state', '')
        pending = session.get('oauth_pending') or {}
        slot = pending.pop(state, None)
        session['oauth_pending'] = pending
        if not p or not slot or slot.get('provider') != provider or time.time() - slot.get('ts', 0) > 600:
            log('auth', f'OAuth callback rejected (bad state) provider={provider}')
            return redirect('/signin?oauth=invalid', 302)
        code = request.args.get('code', '')
        if not code:
            return redirect('/signin?oauth=denied', 302)
        try:
            tok = _http_json(p['token'], {
                'client_id': os.environ[p['id_key']].strip(),
                'client_secret': os.environ[p['secret_key']].strip(),
                'grant_type': 'authorization_code', 'code': code,
                'redirect_uri': _redirect_uri(provider)})
            access = tok.get('access_token', '')
            me = _http_json(p['userinfo'], headers={'Authorization': 'Bearer ' + access})
        except Exception:
            log('auth', f'OAuth provider error provider={provider}')
            return redirect('/signin?oauth=error', 302)
        email = str(me.get('email') or (me.get('mail') or '')).strip().lower()
        name = str(me.get('name') or me.get('displayName') or '').strip()[:120]
        if '@' not in email:
            return redirect('/signin?oauth=noemail', 302)
        with db() as c:
            user = c.execute('SELECT * FROM users WHERE lower(email)=lower(?)', (email,)).fetchone()
            if user:
                uid = user['id']
                c.execute('UPDATE users SET email_verified=1, updated=? WHERE id=?', (now(), uid))
                fresh = False
            else:
                uid = uuid.uuid4().hex
                stamp = now()
                c.execute(
                    'INSERT INTO users(id,email,name,password_hash,role,created,updated,is_active,email_verified)'
                    ' VALUES(?,?,?,?,?,?,?,1,1)',
                    (uid, email, name, '!oauth!' + secrets.token_hex(16), 'client', stamp, stamp))
                fresh = True
        session.clear()
        session.permanent = True
        session['client_id'] = uid
        session['role'] = 'client'
        session['csrf'] = secrets.token_urlsafe(32)
        log('account', f"Client {'created' if fresh else 'signed in'} via {p['name']}: {email}")
        return redirect('/dashboard' + ('?new=1' if fresh and slot.get('mode') == 'signup' else ''), 302)
