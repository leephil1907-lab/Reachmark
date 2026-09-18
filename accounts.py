"""Client accounts: signup, login, and session handling for assigned projects/invoices."""
import re, uuid, time, hashlib, hmac, secrets
from datetime import datetime, timezone
from flask import request, jsonify, session, render_template, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

EMAIL_RE = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def normalize_email(e):
    return e.strip().lower()

def valid_email(e):
    return bool(EMAIL_RE.fullmatch(e.strip())) and len(e) <= 250

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
        # Ensure is_active column exists for older DBs
        cols = {r[1] for r in c.execute('PRAGMA table_info(users)')}
        if 'is_active' not in cols:
            c.execute('ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1')
        if 'name' not in cols:
            c.execute('ALTER TABLE users ADD COLUMN name TEXT')

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

    # Public pages
    @app.get('/signup')
    def signup_page():
        # If already client logged in, go to portal
        if session.get('client_id'):
            return redirect('/')
        return render_template('signup.html')

    @app.get('/signin')
    def signin_page():
        if session.get('client_id') or session.get('owner'):
            return redirect('/')
        return render_template('client_login.html')

    # Also alias /client-login for clarity
    @app.get('/client-login')
    def client_login_alias():
        return redirect('/signin')

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
        # Simple rate limit by IP using existing login_attempts table
        client_hash = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            # clean old blocks
            c.execute('DELETE FROM login_attempts WHERE blocked_until < ?', (time.time()-3600,))
            row = c.execute('SELECT * FROM login_attempts WHERE client=?', (client_hash,)).fetchone()
            if row and row['failures'] >= 10 and row['blocked_until'] > time.time():
                return jsonify(error='Too many attempts. Wait a few minutes.'),429
        # Create user
        uid = uuid.uuid4().hex
        hashed = generate_password_hash(password)
        stamp = now_iso()
        try:
            with db() as c:
                c.execute('INSERT INTO users(id,email,name,password_hash,role,created,updated,is_active) VALUES(?,?,?,?,?,?,?,1)',
                          (uid, email.strip().lower(), name[:120], hashed, 'client', stamp, stamp))
                # clear attempts on success
                c.execute('DELETE FROM login_attempts WHERE client=?', (client_hash,))
        except Exception:
            return jsonify(error='Could not create account. Try again.'),500
        # Log in immediately
        session.clear()
        session.permanent = True
        session['client_id'] = uid
        session['role'] = 'client'
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        log('account', f'Client account created: {email}')
        return jsonify(ok=True, id=uid)

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
            # Check user
            user = c.execute('SELECT * FROM users WHERE lower(email)=lower(?)', (email,)).fetchone()
            valid = False
            if user and user['is_active']:
                valid = check_password_hash(user['password_hash'], password)
            if not valid:
                failures = (row['failures'] if row and row['blocked_until'] > time.time() else 0) + 1
                c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)', (client_hash, failures, time.time()+900))
                return jsonify(error='Invalid email or password.'),401
            # Success clear attempts
            c.execute('DELETE FROM login_attempts WHERE client=?', (client_hash,))
            uid = user['id']
        session.clear()
        session.permanent = True
        session['client_id'] = uid
        session['role'] = 'client'
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        log('account', f'Client signed in: {email}')
        return jsonify(ok=True)

    @app.post('/api/auth/logout')
    def client_logout():
        # Allow both owner and client to logout via this endpoint
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/auth/me')
    def me():
        # Returns current authenticated identity
        if session.get('owner'):
            return jsonify(role='owner', authenticated=True)
        cid = session.get('client_id')
        if cid and session.get('role') == 'client':
            user = get_user_by_id(cid)
            if user:
                return jsonify(role='client', authenticated=True, email=user['email'], name=user['name'], id=user['id'])
        return jsonify(role='none', authenticated=False),401

    @app.get('/api/clients')
    def list_clients():
        # Owner only
        if not session.get('owner'):
            return jsonify(error='Owner login required.'),401
        with db() as c:
            rows = [dict(r) for r in c.execute('SELECT id,email,name,created FROM users WHERE role=\"client\" AND is_active=1 ORDER BY created DESC')]
        return jsonify(clients=rows)

    # Helper for other modules
    app._current_client = current_client
    app._get_user_by_email = get_user_by_email
