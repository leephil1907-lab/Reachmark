"""Single-owner login; production refuses to boot without explicit secure configuration."""
import os, re, secrets, time, hmac, hashlib
from datetime import timedelta
from flask import request, session, jsonify, redirect, render_template, url_for
from werkzeug.security import check_password_hash
from web.i18n import t as _t, locale_now
from web.billing import check_client_path, tier_status
from werkzeug.middleware.proxy_fix import ProxyFix
from web.public_url import support_email as brand_support_email

def _clean_secret(value):
    value=(value or '').strip()
    if len(value)>=2 and value[0]==value[-1] and value[0] in ('"', "'"):
        value=value[1:-1]
    if value.startswith('<') or value.startswith('&lt;'):
        return ''
    return value

# One Content-Security-Policy, built from a source list so prod and dev cannot drift.
# Google Analytics / Tag Manager and AdSense's ad-quality endpoints must be allowed,
# otherwise analytics silently record nothing and AdSense flags the inventory.
_GOOGLE_ADS = ['https://pagead2.googlesyndication.com', 'https://googleads.g.doubleclick.net',
               'https://tpc.googlesyndication.com', 'https://*.adtrafficquality.google',
               'https://csi.gstatic.com', 'https://www.google.com']
_GOOGLE_TAGS = ['https://www.googletagmanager.com', 'https://*.googletagmanager.com',
                'https://www.google-analytics.com', 'https://*.google-analytics.com',
                'https://analytics.google.com', 'https://*.analytics.google.com',
                'https://stats.g.doubleclick.net', 'https://*.g.doubleclick.net']
_TAWK = ['https://embed.tawk.to', 'https://va.tawk.to', 'https://*.tawk.to']
_MAPS = ['https://maps.googleapis.com', 'https://maps.gstatic.com']
_CSP_SOURCES = {
    'default-src': ["'self'"],
    'script-src': ["'self'", "'unsafe-inline'", *_GOOGLE_ADS, *_GOOGLE_TAGS, *_TAWK, *_MAPS],
    'style-src': ["'self'", "'unsafe-inline'", 'https://embed.tawk.to', 'https://*.tawk.to'],
    'img-src': ["'self'", 'data:', 'https://tile.openstreetmap.org', 'https://tile.openstreetmap.de',
                'https://*.basemaps.cartocdn.com', *_MAPS, 'https://*.googleapis.com', 'https://*.ggpht.com',
                *_GOOGLE_ADS, *_GOOGLE_TAGS, *_TAWK],
    'font-src': ["'self'", 'https://*.tawk.to'],
    'connect-src': ["'self'", *_GOOGLE_ADS, *_GOOGLE_TAGS, *_TAWK, 'wss://*.tawk.to',
                    'https://maps.googleapis.com', 'https://places.googleapis.com'],
    'frame-src': ["'self'", *_GOOGLE_ADS, 'https://www.googletagmanager.com', *_TAWK],
    'object-src': ["'none'"],
    'base-uri': ["'self'"],
    'form-action': ["'self'"],
}
def _csp(extra=None):
    parts = dict(_CSP_SOURCES, **(extra or {}))
    return '; '.join(k + ' ' + ' '.join(dict.fromkeys(v)) for k, v in parts.items())
_CSP_DEV = _csp()
_CSP_PROD = _csp({'frame-ancestors': ["'self'"]})


def install_security(app, db):
    production=os.getenv('APP_ENV')=='production'
    key=_clean_secret(os.getenv('SECRET_KEY','')); password_hash=_clean_secret(os.getenv('OWNER_PASSWORD_HASH',''))
    if production:
        missing=[]
        if len(key)<32:
            missing.append('SECRET_KEY must be at least 32 characters (got %d). Do not use the short example key, and avoid $ in the value.' % len(key))
        if not password_hash.startswith(('scrypt:','pbkdf2:')):
            missing.append('OWNER_PASSWORD_HASH must start with scrypt: or pbkdf2: — not the <placeholder> from the example file. Paste the hash with no quotes.')
        if not os.getenv('PUBLIC_BASE_URL','').startswith('https://'):
            missing.append('PUBLIC_BASE_URL must be an https:// URL.')
        if not os.path.isabs(os.getenv('DATABASE_PATH','')):
            missing.append('DATABASE_PATH must be absolute (use /data/reachmark.sqlite3) and a volume should be mounted at /data.')
        if missing:
            raise RuntimeError('Production requires a real boot config. ' + ' '.join(missing))
        app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=0)
    app.secret_key=key or secrets.token_hex(32)
    # Lax: keep the session across top-level navigation from emails, Tawk.to and shared links
    # (Strict silently drops the cookie on those, which looked like an automatic logout).
    # 30-day sliding window refreshed on each request so active users are never kicked mid-work.
    app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=production or os.getenv('SECURE_COOKIES')=='1',PERMANENT_SESSION_LIFETIME=timedelta(days=30),SESSION_REFRESH_EACH_REQUEST=True)
    with db() as c:c.execute('CREATE TABLE IF NOT EXISTS login_attempts(client TEXT PRIMARY KEY,failures INTEGER,blocked_until REAL)')
    def public():
        p=request.path
        if p.startswith('/api/webhooks/'): return True  # Provider callbacks authenticate with their own webhook secret, not browser CSRF.
        if p in ('/','/app','/sw.js','/login','/admin','/api/auth/csrf','/healthz','/about','/offline','/robots.txt','/sitemap.xml','/showcase','/enquire','/receptionist','/reviews','/ads.txt','/signup','/signin','/client-login','/forgot','/reset','/verify','/pricing','/billing/callback','/api/billing/status','/api/billing/webhook','/api/newsletter','/privacy','/terms','/disclosure','/api/cron/expiry-warnings'): return True
        if p.startswith(('/static/','/preview/','/unsubscribe/','/showcase/','/verify/','/reset/','/forgot')): return True
        # Quick review links a business is invited to answer, and the public AI receptionist.
        if p.startswith(('/r/','/api/r/')): return True
        if p.startswith('/o/'): return True
        if p in ('/need','/sourcing','/sending','/sample-report'): return True
        # Google Search Console HTML-file verification (/google<token>.html) must reach the route, not /signin.
        if re.fullmatch(r'/google[a-z0-9]+\.html', p): return True
        if p in ('/api/client-reviews',): return True
        if p == '/api/public/audit' and request.method == 'POST': return True
        if p.startswith(('/proposal/','/brief/','/p/')): return True
        if p=='/api/need' and request.method=='POST': return True
        # Network: public cards, booking pages, QR art, OAuth entry points.
        if p.startswith(('/c/','/book/','/api/book/','/api/qr','/api/auth/oauth')): return True
        if p.startswith('/api/bookings/') and p.endswith('.ics'): return True
        if p in ('/api/receptionist/message','/api/receptionist/offer-review-link','/api/frontdesk/status'): return True
        if p.startswith(('/api/auth/verify','/api/auth/forgot','/api/auth/reset','/api/auth/request-verification',)): return True
        return p.startswith(('/static/','/preview/','/unsubscribe/','/showcase/')) or (p=='/api/enquiries' and request.method=='POST') or (p in ('/api/auth/signup','/api/auth/login') and request.method=='POST') or (p=='/api/auth/me' and request.method=='GET')
    def csrf():
        if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(32)
        return session['csrf']
    def current_role():
        if session.get('owner'):
            return 'owner'
        if session.get('client_id') and session.get('role')=='client':
            return 'client'
        return 'none'
    app.context_processor(lambda:dict(csrf_token=csrf,owner_logged_in=bool(session.get('owner')),client_logged_in=bool(session.get('client_id')),current_role=current_role(),account_home=('/admin' if session.get('owner') else '/dashboard'),production_mode=production,support_email=brand_support_email()))
    @app.before_request
    def owner_guard():
        if public():return
        # Client sessions are allowed for specific routes and pages; owner guard handles them first.
        if session.get('client_id') and session.get('role')=='client':
            # Validate client still active
            try:
                with db() as c:
                    row=c.execute('SELECT * FROM users WHERE id=? AND is_active=1',(session.get('client_id'),)).fetchone()
                    if not row:
                        session.clear()
                    else:
                        # Allow client-allowed APIs and all non-API pages
                        tier,_,_=tier_status(dict(row))
                        verdict,need=check_client_path(request.path,tier)
                        if request.path.startswith('/api/'):
                            if verdict=='ok':
                                # For /api/state, clients get filtered view elsewhere; allow but check CSRF for writes
                                if request.method in ('POST','PATCH','DELETE','PUT'):
                                    supplied=request.headers.get('X-CSRF-Token') or request.form.get('csrf_token','')
                                    if not hmac.compare_digest(supplied,session.get('csrf','')):return jsonify(error=_t('au.sec_csrf', locale_now())),403
                                return
                            if verdict=='upgrade':return jsonify(error=_t('er_138', locale_now(), p=need.title()),upgrade='/pricing',required=need,tier=tier),402
                            return jsonify(error=_t('er_022', locale_now())),403
                        # Non-API page like '/' — allow client to view portal
                        if request.method in ('POST','PATCH','DELETE','PUT'):
                            supplied=request.headers.get('X-CSRF-Token') or request.form.get('csrf_token','')
                            if not hmac.compare_digest(supplied,session.get('csrf','')):return jsonify(error=_t('au.sec_csrf', locale_now())),403
                        return
            except Exception:
                pass
        configured=bool(_clean_secret(os.getenv('OWNER_PASSWORD_HASH')) or os.getenv('DASHBOARD_PASSWORD'))
        # Credential rotation invalidates existing sessions as well as future logins.
        revision=hashlib.sha256((_clean_secret(os.getenv('OWNER_PASSWORD_HASH')) or os.getenv('DASHBOARD_PASSWORD','')).encode()).hexdigest()
        authenticated=session.get('owner') and session.get('revision')==revision
        if configured and not authenticated:
            # If a client is logged in, don't force owner redirect for pages — they have a valid client session
            if session.get('client_id') and session.get('role')=='client':
                return
            # Backward-compatible Basic auth for local development/tests only.
            auth=request.authorization; legacy=os.getenv('DASHBOARD_PASSWORD')
            if not production and legacy and auth and auth.username=='admin' and hmac.compare_digest(auth.password or '',legacy):return
            if request.path.startswith('/api/'):return jsonify(error=_t('er_083', locale_now())),401
            # Clients (or expired sessions) belong on the client sign-in, not the hidden owner login.
            return redirect('/signin')
        # CSRF for owner writes
        check_csrf = authenticated or (session.get('client_id') and session.get('role')=='client')
        if request.path == '/api/newsletter':
            check_csrf = False  # footer form works for visitors and clients alike
        if check_csrf and request.method in ('POST','PATCH','DELETE','PUT'):
            supplied=request.headers.get('X-CSRF-Token') or request.form.get('csrf_token','')
            if not hmac.compare_digest(supplied,session.get('csrf','')):return jsonify(error=_t('au.sec_csrf', locale_now())),403
    def owner_ok():
        """True when this request carries a valid owner session (same rules as owner_guard)."""
        hashed=_clean_secret(os.getenv('OWNER_PASSWORD_HASH')); legacy=os.getenv('DASHBOARD_PASSWORD','')
        configured=bool(hashed or legacy)
        if session.get('owner') and (not configured or session.get('revision')==hashlib.sha256((hashed or legacy).encode()).hexdigest()):
            return True
        auth=request.authorization
        return bool(not production and legacy and auth and auth.username=='admin' and hmac.compare_digest(auth.password or '',legacy))
    app._owner_ok=owner_ok
    @app.get('/api/auth/csrf')
    def csrf_token_json():
        return jsonify(csrf=csrf())
    @app.route('/login',methods=['GET','POST'])
    def legacy_login():
        # The admin console lives only at /admin. /login is the everyday word for
        # customers, so it opens the user sign-in instead of an owner door.
        return redirect('/signin')
    def owner_login():
        """Owner sign-in form for /admin (GET renders, POST verifies)."""
        message=''
        if request.method=='POST':
            if not hmac.compare_digest(request.form.get('csrf_token',''),session.get('csrf','')) or not session.get('csrf'):return _t('au.sec_reload', locale_now()),403
            client=hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                c.execute('DELETE FROM login_attempts WHERE blocked_until < ?',(time.time()-3600,))
                row=c.execute('SELECT * FROM login_attempts WHERE client=?',(client,)).fetchone()
                if row and row['failures']>=5 and row['blocked_until']>time.time():return render_template('login.html',message=_t('au.e_lock', locale_now())),429
                failures=(row['failures'] if row and row['blocked_until']>time.time() else 0)+1
                c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)',(client,failures,time.time()+900))
            value=request.form.get('password','')[:1024]; hashed=_clean_secret(os.getenv('OWNER_PASSWORD_HASH')); legacy=os.getenv('DASHBOARD_PASSWORD','')
            valid=check_password_hash(hashed,value) if hashed else bool(legacy) and hmac.compare_digest(value,legacy)
            if valid:
                with db() as c:c.execute('DELETE FROM login_attempts WHERE client=?',(client,))
                session.clear();session.permanent=True;session['owner']=True;session['revision']=hashlib.sha256((hashed or legacy).encode()).hexdigest();csrf()
                return redirect('/admin')
            message=_t('au.sec_badpw', locale_now())
        return render_template('login.html',message=message)
    app._owner_login=owner_login
    @app.post('/logout')
    def owner_logout():session.clear();return redirect('/admin')
    @app.after_request
    def security_headers(response):
        if production:response.headers['X-Frame-Options']='SAMEORIGIN'
        response.headers['Content-Security-Policy']=_CSP_PROD if production else _CSP_DEV
        if production:response.headers['Strict-Transport-Security']='max-age=31536000'
        if request.path in ('/login','/logout','/admin'):response.headers['Cache-Control']='no-store';response.headers['X-Robots-Tag']='noindex, nofollow'
        return response
    sentry_dsn=_clean_secret(os.getenv('SENTRY_DSN',''))
    if sentry_dsn.startswith(('http://','https://')):
        import sentry_sdk
        def scrub(event,hint):
            event.pop('request',None);event.pop('user',None);event.pop('breadcrumbs',None);event.pop('extra',None)
            # Retain exception types/frames, not values which might contain contacts or secrets.
            for value in event.get('exception',{}).get('values',[]):value['value']='Exception details redacted; inspect protected server logs.'
            return event
        sentry_sdk.init(dsn=sentry_dsn,send_default_pii=False,include_local_variables=False,max_request_body_size='never',traces_sample_rate=0,before_send=scrub,release=os.getenv('RELEASE_SHA','local'))
    @app.errorhandler(500)
    def server_error(error):
        reference=secrets.token_hex(6);app.logger.error('Request failed; reference=%s',reference)
        if request.path.startswith('/api/'):return jsonify(error=_t('au.sec_srv', locale_now(), ref=reference)),500
        return render_template('error.html',reference=reference),500
