"""Single-owner login; production refuses to boot without explicit secure configuration."""
import os, secrets, time, hmac, hashlib
from datetime import timedelta
from flask import request, session, jsonify, redirect, render_template, url_for
from werkzeug.security import check_password_hash
from web.i18n import t as _t, locale_now
from web.billing import check_client_path, tier_status
from werkzeug.middleware.proxy_fix import ProxyFix

def install_security(app, db):
    production=os.getenv('APP_ENV')=='production'
    key=os.getenv('SECRET_KEY',''); password_hash=os.getenv('OWNER_PASSWORD_HASH','')
    if production:
        if len(key)<32 or not password_hash.startswith(('scrypt:','pbkdf2:')): raise RuntimeError('Production requires SECRET_KEY (32+ characters) and OWNER_PASSWORD_HASH.')
        if not os.getenv('PUBLIC_BASE_URL','').startswith('https://'): raise RuntimeError('Production requires an HTTPS PUBLIC_BASE_URL.')
        if not os.path.isabs(os.getenv('DATABASE_PATH','')): raise RuntimeError('Production requires an absolute persistent DATABASE_PATH.')
        app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=0)
    app.secret_key=key or secrets.token_hex(32)
    # Lax: keep the session across top-level navigation from emails, Tawk.to and shared links
    # (Strict silently drops the cookie on those, which looked like an automatic logout).
    # 30-day sliding window refreshed on each request so active users are never kicked mid-work.
    app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=production or os.getenv('SECURE_COOKIES')=='1',PERMANENT_SESSION_LIFETIME=timedelta(days=30),SESSION_REFRESH_EACH_REQUEST=True)
    with db() as c:c.execute('CREATE TABLE IF NOT EXISTS login_attempts(client TEXT PRIMARY KEY,failures INTEGER,blocked_until REAL)')
    def public():
        p=request.path
        if p in ('/','/login','/healthz','/about','/offline','/robots.txt','/sitemap.xml','/showcase','/enquire','/receptionist','/reviews','/ads.txt','/signup','/signin','/client-login','/forgot','/reset','/verify','/pricing','/billing/callback','/api/billing/status','/api/billing/webhook','/api/newsletter'): return True
        if p.startswith(('/static/','/preview/','/unsubscribe/','/showcase/','/verify/','/reset/','/forgot')): return True
        # Quick review links a business is invited to answer, and the public AI receptionist.
        if p.startswith(('/r/','/api/r/')): return True
        # Network: public cards, booking pages, QR art, OAuth entry points.
        if p.startswith(('/c/','/book/','/api/book/','/api/qr','/api/auth/oauth')): return True
        if p.startswith('/api/bookings/') and p.endswith('.ics'): return True
        if p in ('/api/receptionist/message','/api/receptionist/offer-review-link','/api/frontdesk/status'): return True
        if p.startswith(('/api/auth/verify','/api/auth/forgot','/api/auth/reset','/api/auth/request-verification','/api/deploy-check')): return True
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
    app.context_processor(lambda:dict(csrf_token=csrf,owner_logged_in=bool(session.get('owner')),client_logged_in=bool(session.get('client_id')),current_role=current_role(),production_mode=production,support_email=os.getenv('SUPPORT_EMAIL','reachmarkofficial@gmail.com').strip() or 'reachmarkofficial@gmail.com'))
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
        configured=bool(os.getenv('OWNER_PASSWORD_HASH') or os.getenv('DASHBOARD_PASSWORD'))
        # Credential rotation invalidates existing sessions as well as future logins.
        revision=hashlib.sha256((os.getenv('OWNER_PASSWORD_HASH') or os.getenv('DASHBOARD_PASSWORD','')).encode()).hexdigest()
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
    @app.route('/login',methods=['GET','POST'])
    def owner_login():
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
            value=request.form.get('password','')[:1024]; hashed=os.getenv('OWNER_PASSWORD_HASH'); legacy=os.getenv('DASHBOARD_PASSWORD','')
            valid=check_password_hash(hashed,value) if hashed else bool(legacy) and hmac.compare_digest(value,legacy)
            if valid:
                with db() as c:c.execute('DELETE FROM login_attempts WHERE client=?',(client,))
                session.clear();session.permanent=True;session['owner']=True;session['revision']=hashlib.sha256((hashed or legacy).encode()).hexdigest();csrf()
                return redirect('/workspace')
            message=_t('au.sec_badpw', locale_now())
        return render_template('login.html',message=message)
    @app.post('/logout')
    def owner_logout():session.clear();return redirect('/login')
    @app.after_request
    def security_headers(response):
        if production:response.headers['X-Frame-Options']='SAMEORIGIN'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline' https://pagead2.googlesyndication.com https://googleads.g.doubleclick.net https://tpc.googlesyndication.com https://embed.tawk.to https://va.tawk.to https://*.tawk.to; style-src 'self' 'unsafe-inline' https://embed.tawk.to https://*.tawk.to; img-src 'self' data: https://tile.openstreetmap.org https://pagead2.googlesyndication.com https://googleads.g.doubleclick.net https://tpc.googlesyndication.com https://*.tawk.to https://embed.tawk.to https://va.tawk.to; font-src 'self' https://*.tawk.to; connect-src 'self' https://pagead2.googlesyndication.com https://*.tawk.to https://embed.tawk.to https://va.tawk.to wss://*.tawk.to; frame-src 'self' https://pagead2.googlesyndication.com https://googleads.g.doubleclick.net https://tpc.googlesyndication.com https://*.tawk.to https://embed.tawk.to https://va.tawk.to; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'" if production else "default-src 'self'; script-src 'self' 'unsafe-inline' https://pagead2.googlesyndication.com https://googleads.g.doubleclick.net https://tpc.googlesyndication.com https://embed.tawk.to https://va.tawk.to https://*.tawk.to; style-src 'self' 'unsafe-inline' https://embed.tawk.to https://*.tawk.to; img-src 'self' data: https://tile.openstreetmap.org https://pagead2.googlesyndication.com https://googleads.g.doubleclick.net https://tpc.googlesyndication.com https://*.tawk.to https://embed.tawk.to https://va.tawk.to; font-src 'self' https://*.tawk.to; connect-src 'self' https://pagead2.googlesyndication.com https://*.tawk.to https://embed.tawk.to https://va.tawk.to wss://*.tawk.to; frame-src 'self' https://pagead2.googlesyndication.com https://googleads.g.doubleclick.net https://tpc.googlesyndication.com https://*.tawk.to https://embed.tawk.to https://va.tawk.to; object-src 'none'; base-uri 'self'; form-action 'self'"
        if production:response.headers['Strict-Transport-Security']='max-age=31536000'
        if request.path in ('/login','/logout'):response.headers['Cache-Control']='no-store';response.headers['X-Robots-Tag']='noindex, nofollow'
        return response
    if os.getenv('SENTRY_DSN'):
        import sentry_sdk
        def scrub(event,hint):
            event.pop('request',None);event.pop('user',None);event.pop('breadcrumbs',None);event.pop('extra',None)
            # Retain exception types/frames, not values which might contain contacts or secrets.
            for value in event.get('exception',{}).get('values',[]):value['value']='Exception details redacted; inspect protected server logs.'
            return event
        sentry_sdk.init(dsn=os.environ['SENTRY_DSN'],send_default_pii=False,include_local_variables=False,max_request_body_size='never',traces_sample_rate=0,before_send=scrub,release=os.getenv('RELEASE_SHA','local'))
    @app.errorhandler(500)
    def server_error(error):
        reference=secrets.token_hex(6);app.logger.error('Request failed; reference=%s',reference)
        if request.path.startswith('/api/'):return jsonify(error=_t('au.sec_srv', locale_now(), ref=reference)),500
        return render_template('error.html',reference=reference),500
