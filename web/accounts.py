"""Client accounts: signup, login, session, plus Reachmark-standard hardening: email verification, password reset, export & close."""
import re, uuid, time, hashlib, hmac, secrets, os, ssl, smtplib
from datetime import datetime, timezone, timedelta
from flask import request, jsonify, session, render_template, redirect, url_for, Response
from web.i18n import t as _t, locale_now
from werkzeug.security import generate_password_hash, check_password_hash
from email.message import EmailMessage

EMAIL_RE = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')

def support_email():
    return os.getenv('SUPPORT_EMAIL', 'reachmarkofficial@gmail.com').strip() or 'reachmarkofficial@gmail.com'

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def normalize_email(e):
    return e.strip().lower()

def valid_email(e):
    return bool(EMAIL_RE.fullmatch(e.strip())) and len(e) <= 250

def get_base_url():
    # Public base from env, workspace Settings, or request — for emails.
    base = os.getenv('PUBLIC_BASE_URL','').strip().rstrip('/')
    if base:
        return base
    try:
        from web.app import settings
        s = settings()
        if (s.get('public_base_url') or '').strip():
            return s['public_base_url'].strip().rstrip('/')
    except Exception:
        pass
    try:
        # fallback to request host
        return request.host_url.rstrip('/')
    except Exception:
        return 'http://localhost:8000'

def branded_html(title, text_body, cta_url=None, cta_label=None, base_url=None):
    # Branded HTML mail matching the site: cream canvas, white card, lime CTA.
    base = (base_url or 'https://reachmark.co').rstrip('/')
    host = base.replace('https://', '').replace('http://', '')
    safe = text_body.replace('\n', '<br>')
    foot = _t('au.m_foot', locale_now(), email=support_email())
    cta = f'<p style="margin:22px 0"><a href="{cta_url}" style="display:inline-block;background:#0f1a0a;color:#d5f268;padding:13px 20px;border-radius:8px;text-decoration:none;font-weight:700;font-family:Manrope,Arial,sans-serif">{cta_label}</a></p>' if cta_url else ''
    html = f"""<!doctype html><html><body style="margin:0;background:#eef6d1;font-family:Manrope,Arial,sans-serif;color:#1a2315">
<div style="max-width:560px;margin:0 auto;padding:28px">
<div style="background:#ffffff;border:1px solid #e2e7d6;border-radius:16px;padding:28px">
<div style="margin-bottom:18px"><img src="{base}/static/logo-primary.png" alt="Reachmark" style="height:34px" onerror="this.style.display='none'"><div style="font-weight:800;letter-spacing:-0.5px;font-size:18px;color:#0f1a0a">Reachmark</div><div style="font-size:11px;letter-spacing:1.2px;color:#8c9c77">FIND POTENTIAL · MAKE YOUR MARK</div></div>
<h1 style="margin:8px 0 10px;font-size:20px;letter-spacing:-0.5px;color:#0f1a0a">{title}</h1>
<div style="line-height:1.7;color:#33402a;font-size:14px">{safe}</div>
{cta}
<div style="margin-top:22px;padding-top:16px;border-top:1px solid #eef1e4;font-size:12px;color:#8a9976">{foot}</div>
</div>
<div style="text-align:center;margin-top:14px;font-size:11px;color:#8a9976">Reachmark · Global · {host}</div>
</div></body></html>"""
    return html

def send_branded(to_email, subject, text_body, html_title=None, cta_url=None, cta_label=None, db=None):
    """Try SMTP; on missing config or failure, queue to mail_outbox for owner review. Returns (sent:bool, outbox_id)."""
    to_email = to_email.strip().lower()
    base = get_base_url() if 'request' in globals() else 'https://reachmark.co'
    # Build HTML if title given
    html_body = branded_html(html_title or subject, text_body, cta_url, cta_label, base_url=base) if html_title or cta_url else None
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
        _fl = locale_now()
        return render_template('forgot.html') if os.path.exists(os.path.join(app.root_path,'templates','forgot.html')) else Response(("""
<!doctype html><html lang="__LOC__"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reset password · Reachmark</title><link rel="stylesheet" href="/static/fonts.css"><style>
.auth-page{margin:0;background:#e9edde;color:#26351e;min-height:100vh;display:grid;place-items:center;font-family:Manrope,Arial,sans-serif}.auth-card{box-sizing:border-box;width:min(480px,calc(100% - 32px));padding:40px;background:#fff;border:1px solid #d2d8c7;border-radius:22px;box-shadow:0 22px 70px #24311b10}
.auth-card h1{font-size:28px;letter-spacing:-1px;margin:14px 0 8px}.auth-card p{line-height:1.7;color:#535f4c;font-size:14px}
.auth-card label{display:block;margin:14px 0 6px;font-weight:600;font-size:13px}.auth-card input{box-sizing:border-box;width:100%;padding:12px;border:1px solid #a1ad95;border-radius:8px;font-size:15px}
.auth-card button{width:100%;margin:18px 0 10px;padding:13px;background:#26351e;color:#d2e985;border:0;border-radius:8px;font-weight:700;font-size:15px;cursor:pointer}
.auth-error{background:#f9e7e1;padding:10px;color:#8b3524;border-radius:6px;font-size:13px;display:none}.auth-ok{background:#eef6d1;padding:12px;border:1px solid #d8e9b8;border-radius:8px;color:#2d4a0a;font-size:13px;display:none}
</style></head><body class="auth-page"><main class="auth-card"><a href="/" style="text-decoration:none"><img src="/static/logo-primary.svg" alt="Reachmark" style="height:38px"></a><h1>Reset your password.</h1><p>Enter your work email and we'll send a secure link. It expires in 60 minutes.</p><div id="msg" class="auth-error"></div><div id="ok" class="auth-ok"></div><form id="f"><label for="email">Work email</label><input id="email" type="email" required placeholder="you@company.com"><button type="submit">Send reset link →</button></form><p style="font-size:12px;color:#8a9976">Remembered? <a href="/signin">Sign in</a> · <a href="/">About</a></p></main>
<script>
let csrf='';(async()=>{try{let r=await fetch('/login');let t=await r.text();let m=t.match(/name=\\"csrf_token\\" value=\\"([^\\"]+)\\"/);csrf=m?m[1]:''}catch(e){}})();
const f=document.getElementById('f'),msg=document.getElementById('msg'),ok=document.getElementById('ok');
f.onsubmit=async e=>{e.preventDefault();msg.style.display='none';ok.style.display='none';try{let r=await fetch('/api/auth/forgot',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({email:document.getElementById('email').value.trim()})});let j=await r.json();if(!r.ok) throw new Error(j.error||'__NOLINK__');ok.textContent='__SENT__';ok.style.display='block';}catch(err){msg.textContent=err.message;msg.style.display='block';}};
</script></body></html>""".replace('__LOC__', _fl).replace('<h1>Reset your password.</h1>', '<h1>'+_t('au.f_h', _fl)+'</h1>').replace("<p>Enter your work email and we'll send a secure link. It expires in 60 minutes.</p>", '<p>'+_t('au.f_p', _fl)+'</p>').replace('<label for="email">Work email</label>', '<label for="email">'+_t('au.s_email', _fl)+'</label>').replace('<button type="submit">Send reset link →</button>', '<button type="submit">'+_t('au.f_send', _fl)+'</button>').replace('Remembered? <a href="/signin">Sign in</a> · <a href="/">About</a>', _t('au.f_rem', _fl)+' <a href="/signin">'+_t('au.s_signin', _fl)+'</a> · <a href="/">'+_t('au.f_about', _fl)+'</a>').replace('__NOLINK__', _t('au.f_nolink', _fl)).replace('__SENT__', _t('au.f_sent', _fl))), mimetype='text/html')

    @app.get('/reset/<token>')
    def reset_page(token):
        _rl = locale_now()
        return render_template('reset.html', token=token) if os.path.exists(os.path.join(app.root_path,'templates','reset.html')) else Response((f"""
<!doctype html><html lang="{_rl}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Choose new password · Reachmark</title><link rel="stylesheet" href="/static/fonts.css"><style>
.auth-page{{margin:0;background:#e9edde;color:#26351e;min-height:100vh;display:grid;place-items:center;font-family:Manrope,Arial,sans-serif}}.auth-card{{box-sizing:border-box;width:min(480px,calc(100% - 32px));padding:40px;background:#fff;border:1px solid #d2d8c7;border-radius:22px;box-shadow:0 22px 70px #24311b10}}
.auth-card h1{{font-size:28px;letter-spacing:-1px;margin:14px 0 8px}}.auth-card p{{line-height:1.7;color:#535f4c;font-size:14px}}
.auth-card label{{display:block;margin:14px 0 6px;font-weight:600;font-size:13px}}.auth-card input{{box-sizing:border-box;width:100%;padding:12px;border:1px solid #a1ad95;border-radius:8px;font-size:15px}}
.auth-card button{{width:100%;margin:18px 0 10px;padding:13px;background:#d2e985;border:0;border-radius:8px;color:#26351e;font-weight:700;font-size:15px;cursor:pointer}}
.auth-error{{background:#f9e7e1;padding:10px;color:#8b3524;border-radius:6px;font-size:13px;display:none}}.auth-ok{{background:#eef6d1;padding:12px;border:1px solid #d8e9b8;border-radius:8px;color:#2d4a0a;font-size:13px;display:none}}
</style></head><body class="auth-page"><main class="auth-card"><a href="/"><img src="/static/logo-primary.svg" alt="Reachmark" style="height:38px"></a><h1>{_t('au.r_h', _rl)}</h1><p>{_t('au.r_p', _rl)}</p><div id="msg" class="auth-error"></div><div id="ok" class="auth-ok"></div><form id="f"><label>{_t('au.r_pw', _rl)}</label><input id="pw" type="password" required minlength="8"><label>{_t('au.r_conf', _rl)}</label><input id="pw2" type="password" required><button type="submit">{_t('au.r_upd', _rl)}</button></form><p style="font-size:12px;color:#8a9976"><a href="/signin">{_t('au.r_back', _rl)}</a></p></main>
<script>
let csrf='';(async()=>{{try{{let r=await fetch('/login');let t=await r.text();let m=t.match(/name=\\"csrf_token\\" value=\\"([^\\"]+)\\"/);csrf=m?m[1]:''}}catch(e){{}}}})();
const f=document.getElementById('f'),msg=document.getElementById('msg'),ok=document.getElementById('ok');
f.onsubmit=async e=>{{e.preventDefault();msg.style.display='none';const pw=document.getElementById('pw').value, pw2=document.getElementById('pw2').value; if(pw!==pw2){{msg.textContent='{_t('au.js_nomatch', _rl)}';msg.style.display='block';return}}; try{{let r=await fetch('/api/auth/reset',{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':csrf}},body:JSON.stringify({{token:"{token}",password:pw}})}});let j=await r.json();if(!r.ok) throw new Error(j.error||'{_t('au.r_noreset', _rl)}'); ok.textContent='{_t('au.r_done', _rl)}';ok.style.display='block'; setTimeout(()=>location.href='/signin',1200);}}catch(err){{msg.textContent=err.message;msg.style.display='block';}} }};
</script></body></html>"""), mimetype='text/html')

    @app.get('/verify/<token>')
    def verify_page(token):
        # Verify token and show result — avoid nesting db() inside open transaction
        _vl = locale_now()
        row = None
        with db() as c:
            row = c.execute('SELECT * FROM users WHERE verification_token=?', (token,)).fetchone()
            if row:
                row = dict(row)
        if not row:
            return Response(f"""<!doctype html><html lang="{_vl}"><body style="font-family:Manrope,Arial,sans-serif;background:#e9edde;display:grid;place-items:center;min-height:100vh"><div style="background:#fff;padding:32px;border-radius:16px;max-width:480px"><h2>{_t('au.v_inv_h', _vl)}</h2><p>{_t('au.v_inv_p', _vl)}</p><a href="/signin">{_t('au.s_signin', _vl)}</a></div></body></html>""", mimetype='text/html'), 400
        exp = row['verification_expires']
        try:
            if exp and datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                return Response(f"""<!doctype html><html lang="{_vl}"><body style="font-family:Manrope,Arial,sans-serif;background:#e9edde;display:grid;place-items:center;min-height:100vh"><div style="background:#fff;padding:32px;border-radius:16px;max-width:480px"><h2>{_t('au.v_exp_h', _vl)}</h2><p>{_t('au.v_exp_p', _vl)}</p><a href="/signin">{_t('au.s_signin', _vl)}</a></div></body></html>""", mimetype='text/html'), 400
        except Exception:
            pass
        with db() as c:
            c.execute('UPDATE users SET email_verified=1, verification_token=NULL, verification_expires=NULL, updated=? WHERE id=?', (now_iso(), row['id']))
        try:
            log('account', f'Email verified: {row["email"]}')
        except Exception:
            pass
        try:
            base = get_base_url()
            send_branded(row['email'], _t('au.m_w_sub', _vl),
                         _t('au.m_w_body', _vl, email=row['email'], url=f'{base}/pricing'),
                         html_title=_t('au.m_w_title', _vl), cta_url=f'{base}/dashboard',
                         cta_label=_t('au.m_w_cta', _vl), db=db)
        except Exception:
            pass
        if session.get('client_id'):
            next_btn = '<a href="/dashboard" style="display:inline-block;margin-top:12px;background:#0f1a0a;color:#d5f268;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:700">' + _t('au.v_cont_d', _vl) + '</a>'
        else:
            next_btn = '<a href="/signin" style="display:inline-block;margin-top:12px;background:#0f1a0a;color:#d5f268;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:700">' + _t('au.v_cont_s', _vl) + '</a>'
        return Response(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Email verified · Reachmark</title><link rel="stylesheet" href="/static/fonts.css"></head><body style="margin:0;background:#e9edde;display:grid;place-items:center;min-height:100vh;font-family:Manrope,Arial,sans-serif"><div style="background:#fff;border:1px solid #d2d8c7;border-radius:22px;padding:40px;max-width:480px;text-align:center"><img src="/static/logo-primary.svg" alt="Reachmark" style="height:38px"><h1 style="font-size:26px;letter-spacing:-0.8px">{_t('au.v_ok_h', _vl)}</h1><p style="color:#535f4c;line-height:1.6">{_t('au.v_ok_p', _vl)}</p>{next_btn}</div></body></html>""", mimetype='text/html')

    # --- Auth APIs ---
    def _create_verification(user_id, email):
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        with db() as c:
            c.execute('UPDATE users SET verification_token=?, verification_expires=?, updated=? WHERE id=?', (token, expires, now_iso(), user_id))
        base = get_base_url()
        host = base.replace("https://", "").replace("http://", "")
        link = f"{base}/verify/{token}"
        _cl = locale_now()
        text = _t('au.m_c_body', _cl, email=email, link=link, host=host)
        send_branded(email, _t('au.m_c_sub', _cl), text, html_title=_t('au.m_c_title', _cl), cta_url=link, cta_label=_t('au.m_c_cta', _cl), db=db)
        return token

    @app.post('/api/auth/signup')
    def signup():
        data = request.get_json(silent=True) or {}
        email = str(data.get('email','')).strip()
        password = str(data.get('password',''))
        name = str(data.get('name','')).strip()
        if not valid_email(email):
            return jsonify(error=_t('au.e_email', locale_now())),400
        if len(password) < 8 or len(password) > 1024:
            return jsonify(error=_t('au.e_pw8', locale_now())),400
        if len(name) > 120:
            return jsonify(error=_t('au.e_namelong', locale_now())),400
        if get_user_by_email(email):
            return jsonify(error=_t('au.e_exists', locale_now())),409
        client_hash = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM login_attempts WHERE blocked_until < ?', (time.time()-3600,))
            row = c.execute('SELECT * FROM login_attempts WHERE client=?', (client_hash,)).fetchone()
            if row and row['failures'] >= 10 and row['blocked_until'] > time.time():
                return jsonify(error=_t('au.e_many', locale_now())),429
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
            return jsonify(error=_t('au.e_nocreate', locale_now())),500
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
            return jsonify(error=_t('au.e_both', locale_now())),400
        client_hash = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM login_attempts WHERE blocked_until < ?', (time.time()-3600,))
            row = c.execute('SELECT * FROM login_attempts WHERE client=?', (client_hash,)).fetchone()
            if row and row['failures'] >= 5 and row['blocked_until'] > time.time():
                return jsonify(error=_t('au.e_lock', locale_now())),429
            user = c.execute('SELECT * FROM users WHERE lower(email)=lower(?)', (email,)).fetchone()
            valid = False
            if user and user['is_active']:
                valid = check_password_hash(user['password_hash'], password)
            if not valid:
                failures = (row['failures'] if row and row['blocked_until'] > time.time() else 0) + 1
                c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)', (client_hash, failures, time.time()+900))
                return jsonify(error=_t('au.e_invalid', locale_now())),401
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
                from web.billing import tier_status
                tier, tier_active, tier_expires = tier_status(user)
                return jsonify(role='client', authenticated=True, email=user['email'], name=user['name'], id=user['id'], email_verified=bool(user['email_verified']), is_active=bool(user['is_active']), tier=tier, tier_active=tier_active, tier_expires=tier_expires)
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
            return jsonify(error=_t('au.e_signin_email', locale_now())),400
        if not target:
            return jsonify(error=_t('au.e_noacct', locale_now())),404
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
            return jsonify(error=_t('au.e_email', locale_now())),400
        user = get_user_by_email(email)
        # Always return ok to avoid enumeration
        if user and user['is_active']:
            token = secrets.token_urlsafe(32)
            expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            with db() as c:
                c.execute('UPDATE users SET reset_token=?, reset_expires=?, updated=? WHERE id=?', (token, expires, now_iso(), user['id']))
            base = get_base_url()
            link = f"{base}/reset/{token}"
            _ml = locale_now()
            text = _t('au.m_r_body', _ml, name=user['name'] or user['email'], link=link)
            send_branded(user['email'], _t('au.m_r_sub', _ml), text, html_title=_t('au.m_r_title', _ml), cta_url=link, cta_label=_t('au.m_r_cta', _ml), db=db)
            log('account', f'Password reset requested: {user["email"]}')
        return jsonify(ok=True)

    @app.post('/api/auth/reset')
    def do_reset():
        data = request.get_json(silent=True) or {}
        token = str(data.get('token','')).strip()
        password = str(data.get('password',''))
        if not token or len(password) < 8 or len(password) > 1024:
            return jsonify(error=_t('au.e_token', locale_now())),400
        with db() as c:
            row = c.execute('SELECT * FROM users WHERE reset_token=?', (token,)).fetchone()
            if not row:
                return jsonify(error=_t('au.e_used', locale_now())),400
            if not row['is_active']:
                return jsonify(error=_t('au.e_closed', locale_now())),400
            try:
                exp = datetime.fromisoformat(row['reset_expires']) if row['reset_expires'] else None
                if not exp or exp < datetime.now(timezone.utc):
                    return jsonify(error=_t('au.e_exp_forgot', locale_now())),400
            except Exception:
                return jsonify(error=_t('au.e_exp', locale_now())),400
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
            return jsonify(error=_t('au.e_signin_req', locale_now())),401
        user = get_user_by_id(cid)
        if not user or not user['is_active']:
            session.clear()
            return jsonify(error=_t('au.e_noacct', locale_now())),401
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
            return jsonify(error=_t('au.e_signin_req', locale_now())),401
        data = request.get_json(silent=True) or {}
        confirm = str(data.get('confirm','')).strip().lower()
        # Require explicit confirmation
        if confirm not in ('close','delete','confirm'):
            return jsonify(error=_t('au.e_close', locale_now())),400
        with db() as c:
            c.execute('UPDATE users SET is_active=0, updated=? WHERE id=?', (now_iso(), cid))
        log('account', f'Client account closed: {cid}')
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/clients')
    def list_clients():
        if not session.get('owner'):
            return jsonify(error=_t('rx.e_owner', locale_now())),401
        with db() as c:
            rows = [dict(r) for r in c.execute('SELECT id,email,name,created,email_verified,is_active FROM users WHERE role="client" ORDER BY created DESC')]
        return jsonify(clients=rows)

    app._current_client = current_client
    app._get_user_by_email = get_user_by_email
