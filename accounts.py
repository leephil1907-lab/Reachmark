"""Client accounts: signup, login, session, plus Reachmark-standard hardening: email verification, password reset, export & close."""
import re, uuid, time, hashlib, hmac, secrets, os, ssl, smtplib
from datetime import datetime, timezone, timedelta
from flask import request, jsonify, session, render_template, redirect, url_for, Response, g as flask_g
from werkzeug.security import generate_password_hash, check_password_hash
from email.message import EmailMessage

EMAIL_RE = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')

def _with_csp_nonce(html):
    """Add the per-request CSP nonce to bare inline <script> tags in fallback HTML pages."""
    try:
        nonce = flask_g.csp_nonce
    except Exception:
        nonce = ''
    return html.replace('<script>', '<script nonce="%s">' % nonce)


def now_iso():
    return datetime.now(timezone.utc).isoformat()

def normalize_email(e):
    return e.strip().lower()

def valid_email(e):
    return bool(EMAIL_RE.fullmatch(e.strip())) and len(e) <= 250

def get_base_url():
    # Public base from env or request, for emails
    base = os.getenv('PUBLIC_BASE_URL','').strip().rstrip('/')
    if base:
        return base
    try:
        # fallback to request host
        return request.host_url.rstrip('/')
    except Exception:
        return 'http://localhost:8000'

def branded_html(title, text_body, cta_url=None, cta_label=None):
    # Simple branded HTML, no external assets, uses inline styles
    safe = text_body.replace('\n','<br>')
    cta = f'<p style="margin:22px 0"><a href="{cta_url}" style="display:inline-block;background:#0f1a0a;color:#d5f268;padding:13px 20px;border-radius:8px;text-decoration:none;font-weight:700;font-family:Manrope,Arial,sans-serif">{cta_label}</a></p>' if cta_url else ''
    html = f"""<!doctype html><html><body style="margin:0;background:#eef6d1;font-family:Manrope,Arial,sans-serif;color:#1a2315">
<div style="max-width:560px;margin:0 auto;padding:28px">
<div style="background:#ffffff;border:1px solid #e2e7d6;border-radius:16px;padding:28px">
<div style="margin-bottom:18px"><img src="https://reachmark.co/static/logo-primary.svg" alt="Reachmark" style="height:32px" onerror="this.style.display='none'"><div style="font-weight:800;letter-spacing:-0.5px;font-size:18px;color:#0f1a0a">Reachmark</div><div style="font-size:11px;letter-spacing:1.2px;color:#8c9c77">FIND POTENTIAL · MAKE YOUR MARK</div></div>
<h1 style="margin:8px 0 10px;font-size:20px;letter-spacing:-0.5px;color:#0f1a0a">{title}</h1>
<div style="line-height:1.7;color:#2d4a0a;font-size:14px">{safe}</div>
{cta}
<div style="margin-top:22px;padding-top:16px;border-top:1px solid #eef1e4;font-size:12px;color:#8a9976">If you didn't ask for this, you can ignore this email. Reply to hello@reachmark.co for help.</div>
</div>
<div style="text-align:center;margin-top:14px;font-size:11px;color:#8a9976">Reachmark · Global · reachmark.co</div>
</div></body></html>"""
    return html

def send_branded(to_email, subject, text_body, html_title=None, cta_url=None, cta_label=None, db=None):
    """Try SMTP; on missing config or failure, queue to mail_outbox for owner review. Returns (sent:bool, outbox_id)."""
    to_email = to_email.strip().lower()
    base = get_base_url() if 'request' in globals() else 'https://reachmark.co'
    # Build HTML if title given
    html_body = branded_html(html_title or subject, text_body, cta_url, cta_label) if html_title or cta_url else None
    outbox_id = uuid.uuid4().hex
    created = now_iso()
    # Try SMTP if configured
    host = os.getenv('SMTP_HOST','').strip()
    frm = os.getenv('SMTP_FROM','').strip()
    if host and frm:
        try:
            msg = EmailMessage()
            msg['From'] = frm
            msg['To'] = to_email
            # Use reply_email if set, else frm
            # We can't read settings here easily; use frm
            msg['Reply-To'] = os.getenv('SMTP_FROM','')
            msg['Subject'] = subject
            msg['Message-ID'] = f'<{outbox_id}@{frm.split("@")[-1]}>'
            msg.set_content(text_body)
            if html_body:
                msg.add_alternative(html_body, subtype='html')
            port = int(os.getenv('SMTP_PORT','587'))
            mode = os.getenv('SMTP_SECURITY','starttls')
            cls = smtplib.SMTP_SSL if mode=='ssl' else smtplib.SMTP
            with cls(host, port, timeout=25) as smtp:
                if mode=='starttls':
                    smtp.starttls(context=ssl.create_default_context())
                if os.getenv('SMTP_USER'):
                    smtp.login(os.environ['SMTP_USER'], os.getenv('SMTP_PASSWORD',''))
                smtp.send_message(msg)
            # Record as sent
            if db is not None:
                try:
                    with db() as c:
                        c.execute('INSERT INTO mail_outbox VALUES(?,?,?,?,?,?,?)', (outbox_id, to_email, subject, text_body, html_body or '', created, 'sent'))
                except Exception:
                    pass
            return True, outbox_id
        except Exception as e:
            # queue as failed/queued for retry
            if db is not None:
                try:
                    with db() as c:
                        c.execute('INSERT INTO mail_outbox VALUES(?,?,?,?,?,?,?)', (outbox_id, to_email, subject, text_body, html_body or '', created, 'failed:'+type(e).__name__))
                except Exception:
                    pass
            return False, outbox_id
    else:
        # No SMTP — queue
        if db is not None:
            try:
                with db() as c:
                    c.execute('INSERT INTO mail_outbox VALUES(?,?,?,?,?,?,?)', (outbox_id, to_email, subject, text_body, html_body or '', created, 'queued'))
            except Exception:
                pass
        return False, outbox_id

def verified_client(db, cid):
    """Return (email, is_verified) for a client user id.

    Gate for ALL client data access: an unverified account (email_verified=0)
    must see nothing, because the account holder has not proven mailbox control.
    Returns (None, False) for missing or unverified users."""
    if not cid:
        return None, False
    with db() as c:
        r = c.execute('SELECT email, email_verified FROM users WHERE id=?', (cid,)).fetchone()
    if not r:
        return None, False
    return r['email'].lower(), bool(r['email_verified'])

_CAPTCHA_VERIFIERS = {}

def register_captcha_verifier(provider, fn):
    """Register a CAPTCHA verifier fn(token, ip) -> bool. CAPTCHA-ready hook:
    set CAPTCHA_PROVIDER=<name> in env to enforce the registered verifier."""
    _CAPTCHA_VERIFIERS[provider.strip().lower()] = fn

def captcha_ok(token, ip):
    """No-op (True) until CAPTCHA_PROVIDER is set. When a provider is configured
    but no verifier is registered, fail closed."""
    provider = os.getenv('CAPTCHA_PROVIDER','').strip().lower()
    if not provider:
        return True
    fn = _CAPTCHA_VERIFIERS.get(provider)
    if fn is None:
        return False
    try:
        return bool(fn(token or '', ip or ''))
    except Exception:
        return False

def check_throttle(db, kind, ip, email, max_hits, window_seconds):
    """Per-IP + per-email sliding throttle. Returns False when over the limit.
    Used by signup and forgot-password."""
    now = time.time()
    key = f'{kind}|{(ip or "unknown")[:64]}|{(email or "").lower()[:250]}'
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS auth_throttle(key TEXT PRIMARY KEY, hits INTEGER, first REAL)')
        c.execute('DELETE FROM auth_throttle WHERE first < ?', (now - window_seconds,))
        row = c.execute('SELECT hits, first FROM auth_throttle WHERE key=?', (key,)).fetchone()
        if row:
            if row['hits'] >= max_hits:
                return False
            c.execute('UPDATE auth_throttle SET hits=hits+1 WHERE key=?', (key,))
        else:
            c.execute('INSERT INTO auth_throttle(key,hits,first) VALUES(?,?,?)', (key, 1, now))
    return True

def register_accounts(app, db, log):
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS users(
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE COLLATE NOCASE,
            name TEXT,
            password_hash TEXT,
            role TEXT,
            created TEXT,
            updated TEXT,
            is_active INTEGER DEFAULT 1
        );''')
        # Ensure columns exists for older DBs
        cols = {r[1] for r in c.execute('PRAGMA table_info(users)')}
        for col, typ in [
            ('is_active','INTEGER DEFAULT 1'),
            ('name','TEXT'),
            ('email_verified','INTEGER DEFAULT 0'),
            ('verification_token','TEXT'),
            ('verification_expires','TEXT'),
            ('reset_token','TEXT'),
            ('reset_expires','TEXT'),
        ]:
            if col not in cols:
                c.execute(f'ALTER TABLE users ADD COLUMN {col} {typ}')
        # Outbox for branded mail when SMTP not configured
        c.executescript('''CREATE TABLE IF NOT EXISTS mail_outbox(
            id TEXT PRIMARY KEY,
            to_email TEXT,
            subject TEXT,
            body TEXT,
            html TEXT,
            created TEXT,
            state TEXT
        );
        CREATE TABLE IF NOT EXISTS login_attempts(client TEXT PRIMARY KEY,failures INTEGER,blocked_until REAL);
        ''')

    def get_user_by_email(email):
        with db() as c:
            r = c.execute('SELECT * FROM users WHERE lower(email)=lower(?)', (email.strip(),)).fetchone()
            return dict(r) if r else None

    def get_user_by_id(uid):
        with db() as c:
            r = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            return dict(r) if r else None

    def current_client():
        cid = session.get('client_id')
        if not cid or session.get('role') != 'client':
            return None
        with db() as c:
            r = c.execute('SELECT * FROM users WHERE id=? AND is_active=1', (cid,)).fetchone()
            return dict(r) if r else None

    # --- Public pages ---
    @app.get('/signup')
    def signup_page():
        if session.get('client_id'):
            return redirect('/dashboard')
        if session.get('owner'):
            return redirect('/workspace')
        return render_template('signup.html')

    @app.get('/signin')
    def signin_page():
        if session.get('client_id'):
            return redirect('/dashboard')
        if session.get('owner'):
            return redirect('/workspace')
        return render_template('client_login.html')

    @app.get('/client-login')
    def client_login_alias():
        return redirect('/signin')

    @app.get('/forgot')
    def forgot_page():
        return render_template('forgot.html') if os.path.exists(os.path.join(app.root_path,'templates','forgot.html')) else Response(_with_csp_nonce("""
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reset password · Reachmark</title><link rel="stylesheet" href="/static/fonts.css"><style>
.auth-page{margin:0;background:#e9edde;color:#26351e;min-height:100vh;display:grid;place-items:center;font-family:Manrope,Arial,sans-serif}.auth-card{box-sizing:border-box;width:min(480px,calc(100% - 32px));padding:40px;background:#fff;border:1px solid #d2d8c7;border-radius:22px;box-shadow:0 22px 70px #24311b10}
.auth-card h1{font-size:28px;letter-spacing:-1px;margin:14px 0 8px}.auth-card p{line-height:1.7;color:#535f4c;font-size:14px}
.auth-card label{display:block;margin:14px 0 6px;font-weight:600;font-size:13px}.auth-card input{box-sizing:border-box;width:100%;padding:12px;border:1px solid #a1ad95;border-radius:8px;font-size:15px}
.auth-card button{width:100%;margin:18px 0 10px;padding:13px;background:#26351e;color:#d2e985;border:0;border-radius:8px;font-weight:700;font-size:15px;cursor:pointer}
.auth-error{background:#f9e7e1;padding:10px;color:#8b3524;border-radius:6px;font-size:13px;display:none}.auth-ok{background:#eef6d1;padding:12px;border:1px solid #d8e9b8;border-radius:8px;color:#2d4a0a;font-size:13px;display:none}
</style></head><body class="auth-page"><main class="auth-card"><a href="/" style="text-decoration:none"><img src="/static/logo-primary.svg" alt="Reachmark" style="height:38px"></a><h1>Reset your password.</h1><p>Enter your work email and we'll send a secure link. It expires in 60 minutes.</p><div id="msg" class="auth-error"></div><div id="ok" class="auth-ok"></div><form id="f"><label for="email">Work email</label><input id="email" type="email" required placeholder="you@company.com"><button type="submit">Send reset link →</button></form><p style="font-size:12px;color:#8a9976">Remembered? <a href="/signin">Sign in</a> · <a href="/">About</a></p></main>
<script>
let csrf='';(async()=>{try{let r=await fetch('/login');let t=await r.text();let m=t.match(/name=\\"csrf_token\\" value=\\"([^\\"]+)\\"/);csrf=m?m[1]:''}catch(e){}})();
const f=document.getElementById('f'),msg=document.getElementById('msg'),ok=document.getElementById('ok');
f.onsubmit=async e=>{e.preventDefault();msg.style.display='none';ok.style.display='none';try{let r=await fetch('/api/auth/forgot',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({email:document.getElementById('email').value.trim()})});let j=await r.json();if(!r.ok) throw new Error(j.error||'Could not send link');ok.textContent='If an account exists, a reset link has been sent. Check your email (and spam).';ok.style.display='block';}catch(err){msg.textContent=err.message;msg.style.display='block';}};
</script></body></html>"""), mimetype='text/html')

    @app.get('/reset/<token>')
    def reset_page(token):
        return render_template('reset.html', token=token) if os.path.exists(os.path.join(app.root_path,'templates','reset.html')) else Response(_with_csp_nonce(f"""
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Choose new password · Reachmark</title><link rel="stylesheet" href="/static/fonts.css"><style>
.auth-page{{margin:0;background:#e9edde;color:#26351e;min-height:100vh;display:grid;place-items:center;font-family:Manrope,Arial,sans-serif}}.auth-card{{box-sizing:border-box;width:min(480px,calc(100% - 32px));padding:40px;background:#fff;border:1px solid #d2d8c7;border-radius:22px;box-shadow:0 22px 70px #24311b10}}
.auth-card h1{{font-size:28px;letter-spacing:-1px;margin:14px 0 8px}}.auth-card p{{line-height:1.7;color:#535f4c;font-size:14px}}
.auth-card label{{display:block;margin:14px 0 6px;font-weight:600;font-size:13px}}.auth-card input{{box-sizing:border-box;width:100%;padding:12px;border:1px solid #a1ad95;border-radius:8px;font-size:15px}}
.auth-card button{{width:100%;margin:18px 0 10px;padding:13px;background:#d2e985;border:0;border-radius:8px;color:#26351e;font-weight:700;font-size:15px;cursor:pointer}}
.auth-error{{background:#f9e7e1;padding:10px;color:#8b3524;border-radius:6px;font-size:13px;display:none}}.auth-ok{{background:#eef6d1;padding:12px;border:1px solid #d8e9b8;border-radius:8px;color:#2d4a0a;font-size:13px;display:none}}
</style></head><body class="auth-page"><main class="auth-card"><a href="/"><img src="/static/logo-primary.svg" alt="Reachmark" style="height:38px"></a><h1>Choose a new password.</h1><p>At least 8 characters. This link expires in 60 minutes and can be used once.</p><div id="msg" class="auth-error"></div><div id="ok" class="auth-ok"></div><form id="f"><label>New password</label><input id="pw" type="password" required minlength="8"><label>Confirm</label><input id="pw2" type="password" required><button type="submit">Update password →</button></form><p style="font-size:12px;color:#8a9976"><a href="/signin">Back to sign in</a></p></main>
<script>
let csrf='';(async()=>{{try{{let r=await fetch('/login');let t=await r.text();let m=t.match(/name=\\"csrf_token\\" value=\\"([^\\"]+)\\"/);csrf=m?m[1]:''}}catch(e){{}}}})();
const f=document.getElementById('f'),msg=document.getElementById('msg'),ok=document.getElementById('ok');
f.onsubmit=async e=>{{e.preventDefault();msg.style.display='none';const pw=document.getElementById('pw').value, pw2=document.getElementById('pw2').value; if(pw!==pw2){{msg.textContent='Passwords do not match.';msg.style.display='block';return}}; try{{let r=await fetch('/api/auth/reset',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':csrf}},body:JSON.stringify({{token:"{token}",password:pw}})}});let j=await r.json();if(!r.ok) throw new Error(j.error||'Could not reset'); ok.textContent='Password updated. Redirecting to sign in…';ok.style.display='block'; setTimeout(()=>location.href='/signin',1200);}}catch(err){{msg.textContent=err.message;msg.style.display='block';}} }};
</script></body></html>"""), mimetype='text/html')

    @app.get('/verify/<token>')
    def verify_page(token):
        # Verify token and show result — avoid nesting db() inside open transaction
        row = None
        with db() as c:
            row = c.execute('SELECT * FROM users WHERE verification_token=?', (token,)).fetchone()
            if row:
                row = dict(row)
        if not row:
            return Response("""<!doctype html><html><body style="font-family:Manrope,Arial,sans-serif;background:#e9edde;display:grid;place-items:center;min-height:100vh"><div style="background:#fff;padding:32px;border-radius:16px;max-width:480px"><h2>Link invalid or expired.</h2><p>Request a new verification email from your dashboard or sign-in page.</p><a href="/signin">Sign in</a></div></body></html>""", mimetype='text/html'), 400
        exp = row['verification_expires']
        try:
            if exp and datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                return Response("""<!doctype html><html><body style="font-family:Manrope,Arial,sans-serif;background:#e9edde;display:grid;place-items:center;min-height:100vh"><div style="background:#fff;padding:32px;border-radius:16px;max-width:480px"><h2>Link expired.</h2><p>Your verification link was valid for 24 hours. Request a new one.</p><a href="/signin">Sign in</a></div></body></html>""", mimetype='text/html'), 400
        except Exception:
            pass
        with db() as c:
            c.execute('UPDATE users SET email_verified=1, verification_token=NULL, verification_expires=NULL, updated=? WHERE id=?', (now_iso(), row['id']))
        try:
            log('account', f'Email verified: {row["email"]}')
        except Exception:
            pass
        return Response("""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Email verified · Reachmark</title><link rel="stylesheet" href="/static/fonts.css"></head><body style="margin:0;background:#e9edde;display:grid;place-items:center;min-height:100vh;font-family:Manrope,Arial,sans-serif"><div style="background:#fff;border:1px solid #d2d8c7;border-radius:22px;padding:40px;max-width:480px;text-align:center"><img src="/static/logo-primary.svg" alt="Reachmark" style="height:38px"><h1 style="font-size:26px;letter-spacing:-0.8px">Email verified ✓</h1><p style="color:#535f4c;line-height:1.6">Your Reachmark account is now verified. You can close this tab and continue to your dashboard.</p><a href="/signin" style="display:inline-block;margin-top:12px;background:#0f1a0a;color:#d5f268;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:700">Continue to sign in →</a></div></body></html>""", mimetype='text/html')

    # --- Auth APIs ---
    def _create_verification(user_id, email):
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        with db() as c:
            c.execute('UPDATE users SET verification_token=?, verification_expires=?, updated=? WHERE id=?', (token, expires, now_iso(), user_id))
        base = get_base_url()
        link = f"{base}/verify/{token}"
        text = f"Hi {email},\n\nConfirm your Reachmark account by opening this link (valid 24 hours):\n{link}\n\nIf you didn't create an account, you can ignore this email.\n\n— Reachmark · Global\nreachmark.co"
        send_branded(email, "Confirm your Reachmark account", text, html_title="Confirm your email", cta_url=link, cta_label="Verify email →", db=db)
        return token

    @app.post('/api/auth/signup')
    def signup():
        data = request.get_json(silent=True) or {}
        email = str(data.get('email','')).strip()
        password = str(data.get('password',''))
        name = str(data.get('name','')).strip()
        if not valid_email(email):
            return jsonify(error='Enter a valid email address.'),400
        if len(password) < 8 or len(password) > 1024:
            return jsonify(error='Password must be at least 8 characters.'),400
        if len(name) > 120:
            return jsonify(error='Name is too long.'),400
        if get_user_by_email(email):
            return jsonify(error='An account with that email already exists. Try signing in.'),409
        client_hash = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM login_attempts WHERE blocked_until < ?', (time.time()-3600,))
            row = c.execute('SELECT * FROM login_attempts WHERE client=?', (client_hash,)).fetchone()
            if row and row['failures'] >= 10 and row['blocked_until'] > time.time():
                return jsonify(error='Too many attempts. Wait a few minutes.'),429
        # Throttle on both dimensions: per-IP cap and per-IP+email cap.
        if not check_throttle(db, 'signup-ip', request.remote_addr, '', 10, 3600) or not check_throttle(db, 'signup', request.remote_addr, email, 5, 3600):
            return jsonify(error='Too many account attempts from this connection. Try again in an hour.'),429
        if not captcha_ok(str(data.get('captcha_token','')), request.remote_addr):
            return jsonify(error='Verification challenge failed. Reload the page and try again.'),400
        uid = uuid.uuid4().hex
        hashed = generate_password_hash(password)
        stamp = now_iso()
        try:
            with db() as c:
                # Insert with unverified status
                c.execute('INSERT INTO users(id,email,name,password_hash,role,created,updated,is_active,email_verified) VALUES(?,?,?,?,?,?,?,1,0)',
                          (uid, email.strip().lower(), name[:120], hashed, 'client', stamp, stamp))
                c.execute('DELETE FROM login_attempts WHERE client=?', (client_hash,))
        except Exception:
            return jsonify(error='Could not create account. Try again.'),500
        # Create verification email (non-blocking)
        try:
            _create_verification(uid, email.strip().lower())
        except Exception:
            pass
        session.clear()
        session.permanent = True
        session['client_id'] = uid
        session['role'] = 'client'
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        log('account', f'Client account created: {email}')
        return jsonify(ok=True, id=uid, needs_verification=True),201

    @app.post('/api/auth/login')
    def login():
        data = request.get_json(silent=True) or {}
        email = str(data.get('email','')).strip()
        password = str(data.get('password',''))
        if not valid_email(email) or not password:
            return jsonify(error='Enter your email and password.'),400
        client_hash = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM login_attempts WHERE blocked_until < ?', (time.time()-3600,))
            row = c.execute('SELECT * FROM login_attempts WHERE client=?', (client_hash,)).fetchone()
            if row and row['failures'] >= 5 and row['blocked_until'] > time.time():
                return jsonify(error='Too many attempts. Wait 15 minutes before trying again.'),429
            user = c.execute('SELECT * FROM users WHERE lower(email)=lower(?)', (email,)).fetchone()
            valid = False
            if user and user['is_active']:
                valid = check_password_hash(user['password_hash'], password)
            if not valid:
                failures = (row['failures'] if row and row['blocked_until'] > time.time() else 0) + 1
                c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)', (client_hash, failures, time.time()+900))
                return jsonify(error='Invalid email or password.'),401
            c.execute('DELETE FROM login_attempts WHERE client=?', (client_hash,))
            uid = user['id']
            needs_verification = not bool(user['email_verified'])
        session.clear()
        session.permanent = True
        session['client_id'] = uid
        session['role'] = 'client'
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        log('account', f'Client signed in: {email}')
        resp = jsonify(ok=True, needs_verification=needs_verification)
        if needs_verification:
            resp.headers['X-Needs-Verification'] = '1'
        return resp

    @app.post('/api/auth/logout')
    def client_logout():
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/auth/me')
    def me():
        if session.get('owner'):
            return jsonify(role='owner', authenticated=True)
        cid = session.get('client_id')
        if cid and session.get('role') == 'client':
            user = get_user_by_id(cid)
            if user:
                return jsonify(role='client', authenticated=True, email=user['email'], name=user['name'], id=user['id'], email_verified=bool(user['email_verified']), is_active=bool(user['is_active']))
        return jsonify(role='none', authenticated=False),401

    @app.post('/api/auth/request-verification')
    def request_verification():
        # Auth required: client or email provided
        data = request.get_json(silent=True) or {}
        email = str(data.get('email','')).strip().lower()
        # If logged in as client, use that
        cid = session.get('client_id')
        target = None
        if cid and session.get('role')=='client':
            target = get_user_by_id(cid)
        elif email and valid_email(email):
            target = get_user_by_email(email)
        else:
            return jsonify(error='Sign in or provide your email.'),400
        if not target:
            return jsonify(error='Account not found.'),404
        if target['email_verified']:
            return jsonify(ok=True, already_verified=True)
        # Rate limit: don't spam
        with db() as c:
            row = c.execute('SELECT verification_expires FROM users WHERE id=?', (target['id'],)).fetchone()
            if row and row['verification_expires']:
                try:
                    exp = datetime.fromisoformat(row['verification_expires'])
                    if exp > datetime.now(timezone.utc) + timedelta(hours=23):  # sent within last hour
                        return jsonify(ok=True, throttled=True)
                except Exception:
                    pass
        try:
            _create_verification(target['id'], target['email'])
        except Exception:
            pass
        return jsonify(ok=True)

    @app.post('/api/auth/forgot')
    def forgot():
        data = request.get_json(silent=True) or {}
        email = str(data.get('email','')).strip()
        if not valid_email(email):
            return jsonify(error='Enter a valid email address.'),400
        # Throttle + CAPTCHA-ready hook. Keep the generic ok response on both failure
        # paths so rate limits and challenges do not leak which emails exist.
        if not check_throttle(db, 'forgot-ip', request.remote_addr, '', 10, 3600) or not check_throttle(db, 'forgot', request.remote_addr, email, 3, 3600):
            return jsonify(ok=True)
        if not captcha_ok(str(data.get('captcha_token','')), request.remote_addr):
            return jsonify(ok=True)
        user = get_user_by_email(email)
        # Always return ok to avoid enumeration
        if user and user['is_active']:
            token = secrets.token_urlsafe(32)
            expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            with db() as c:
                c.execute('UPDATE users SET reset_token=?, reset_expires=?, updated=? WHERE id=?', (token, expires, now_iso(), user['id']))
            base = get_base_url()
            link = f"{base}/reset/{token}"
            text = f"Hi {user['name'] or user['email']},\n\nReset your Reachmark password by opening this link (valid 60 minutes, one-time):\n{link}\n\nIf you didn't ask for this, you can ignore this email — your password won't change.\n\n— Reachmark"
            send_branded(user['email'], "Reset your Reachmark password", text, html_title="Reset your password", cta_url=link, cta_label="Choose new password →", db=db)
            log('account', f'Password reset requested: {user["email"]}')
        return jsonify(ok=True)

    @app.post('/api/auth/reset')
    def do_reset():
        data = request.get_json(silent=True) or {}
        token = str(data.get('token','')).strip()
        password = str(data.get('password',''))
        if not token or len(password) < 8 or len(password) > 1024:
            return jsonify(error='Invalid token or password must be 8+ characters.'),400
        with db() as c:
            row = c.execute('SELECT * FROM users WHERE reset_token=?', (token,)).fetchone()
            if not row:
                return jsonify(error='This reset link is invalid or has already been used.'),400
            if not row['is_active']:
                return jsonify(error='Account is closed.'),400
            try:
                exp = datetime.fromisoformat(row['reset_expires']) if row['reset_expires'] else None
                if not exp or exp < datetime.now(timezone.utc):
                    return jsonify(error='This reset link has expired. Request a new one from /forgot.'),400
            except Exception:
                return jsonify(error='This reset link has expired.'),400
            hashed = generate_password_hash(password)
            c.execute('UPDATE users SET password_hash=?, reset_token=NULL, reset_expires=NULL, updated=? WHERE id=?', (hashed, now_iso(), row['id']))
            # Invalidate other sessions? Clear login attempts
            c.execute('DELETE FROM login_attempts WHERE client=?', (hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest(),))
        log('account', f'Password reset completed: {row["email"]}')
        return jsonify(ok=True)

    @app.get('/api/auth/export')
    def export_account():
        cid = session.get('client_id')
        if not cid or session.get('role')!='client':
            return jsonify(error='Sign in required.'),401
        user = get_user_by_id(cid)
        if not user or not user['is_active']:
            session.clear()
            return jsonify(error='Account not found.'),401
        with db() as c:
            # Projects, invoices, documents linked to this user
            projects = [dict(r) for r in c.execute('SELECT * FROM projects WHERE client_user_id=? ORDER BY updated DESC', (cid,))] if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'").fetchone() else []
            invoices = [dict(r) for r in c.execute('SELECT * FROM invoices WHERE client_user_id=? ORDER BY updated DESC', (cid,))] if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='invoices'").fetchone() else []
            # Also invoices matched by email when not yet linked
            if not invoices and user['email']:
                try:
                    invoices = [dict(r) for r in c.execute('SELECT * FROM invoices WHERE lower(client_email)=lower(?) ORDER BY updated DESC', (user['email'],))]
                except Exception:
                    pass
            enquiries = []
            # include any enquiries? Not per user in this schema
            out = {
                'account': {'id': user['id'], 'email': user['email'], 'name': user['name'], 'created': user['created'], 'email_verified': bool(user['email_verified'])},
                'projects': projects,
                'invoices': invoices,
                'exported_at': now_iso(),
                'notice': 'Reachmark account export — private to you.'
            }
        return jsonify(out)

    @app.post('/api/auth/close')
    def close_account():
        cid = session.get('client_id')
        if not cid or session.get('role')!='client':
            return jsonify(error='Sign in required.'),401
        data = request.get_json(silent=True) or {}
        confirm = str(data.get('confirm','')).strip().lower()
        # Require explicit confirmation
        if confirm not in ('close','delete','confirm'):
            return jsonify(error='Type "close" to confirm.'),400
        with db() as c:
            c.execute('UPDATE users SET is_active=0, updated=? WHERE id=?', (now_iso(), cid))
        log('account', f'Client account closed: {cid}')
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/clients')
    def list_clients():
        if not session.get('owner'):
            return jsonify(error='Owner login required.'),401
        with db() as c:
            rows = [dict(r) for r in c.execute('SELECT id,email,name,created,email_verified,is_active FROM users WHERE role="client" ORDER BY created DESC')]
        return jsonify(clients=rows)

    app._current_client = current_client
    app._get_user_by_email = get_user_by_email
