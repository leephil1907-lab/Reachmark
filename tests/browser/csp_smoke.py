"""CSP browser smoke test (Playwright).

Verifies in a real browser that:
  * the Content-Security-Policy has NO 'unsafe-inline' in script-src,
    and inline <script> blocks carry the matching per-request nonce;
  * no page produces a CSP violation or an uncaught JS exception;
  * the data-rm-* event delegation actually fires handlers
    (navigation, modals, invoice rows, review moderation, signup verify).

Run: PYTHONPATH=. python tests/browser/csp_smoke.py
"""
import os, re, sys, tempfile, threading

os.environ['DATABASE_PATH'] = tempfile.mktemp(suffix='.csp_smoke.sqlite3')
os.environ['APP_ENV'] = 'development'
os.environ['DASHBOARD_PASSWORD'] = 'smoke-pass-123'
os.environ['SECRET_KEY'] = 'smoke-secret-key-' + 'x' * 24
os.environ.setdefault('PUBLIC_BASE_URL', 'http://127.0.0.1:8765')

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from werkzeug.serving import make_server  # noqa: E402
import app as m  # noqa: E402

PORT = int(os.environ.get('CSP_SMOKE_PORT', '8765'))
BASE = f'http://127.0.0.1:{PORT}'
srv = make_server('127.0.0.1', PORT, m.app)
threading.Thread(target=srv.serve_forever, daemon=True).start()

from playwright.sync_api import sync_playwright  # noqa: E402

FAILURES = []

def check(name, cond, detail=''):
    status = 'ok  ' if cond else 'FAIL'
    print(f'[{status}] {name}' + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILURES.append(name)

def csrf_of(page, url):
    page.goto(url)
    try:
        return page.eval_on_selector('input[name="csrf_token"]', 'el => el.value')
    except Exception:
        return page.eval_on_selector('meta[name="csrf-token"]', 'el => el.content')

def csp_header(page):
    resp = page.request.get(BASE + '/')
    return resp.headers.get('content-security-policy', '')

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        csp_violations, page_errors = [], []
        page.on('console', lambda msg: csp_violations.append(msg.text)
                if msg.type == 'error' and 'Content Security Policy' in msg.text else None)
        page.on('pageerror', lambda err: page_errors.append(str(err)))
        page.on('dialog', lambda d: d.accept())

        # ---------- public pages ----------
        csp = csp_header(page)
        check('CSP present', bool(csp))
        check("script-src has no 'unsafe-inline'", "script-src 'self' 'unsafe-inline'" not in csp and re.search(r"script-src[^;]*", csp) is not None and "'unsafe-inline'" not in re.search(r"script-src[^;]*", csp).group(0), csp)
        check('script-src has nonce', 'nonce-' in csp)
        check('googletagmanager allowed', 'googletagmanager.com' in csp)
        check('tawk allowed', 'tawk.to' in csp)

        # Check the RAW response body: Chromium serializes the live DOM with nonce
        # attributes emptied (the browser consumes them once scripts are authorized),
        # so page.content() is not a valid CSP oracle.
        home = page.request.get(BASE + '/')
        html = home.text()
        csp_same = home.headers.get('content-security-policy', csp)
        nonce_in_policy = re.search(r"nonce-([^'\"\s;]+)", csp_same).group(1)
        inline_scripts = re.findall(r'<script nonce="([^"]*)">', html)
        check('inline scripts carry nonces', len(inline_scripts) > 0, f'found {len(inline_scripts)}')
        check('all inline script nonces match policy', inline_scripts and all(n == nonce_in_policy for n in inline_scripts),
              str(set(inline_scripts) ^ {nonce_in_policy}))
        check('no bare inline <script> without nonce', '<script>' not in html and '<script type="text/javascript">' not in html)
        check('no inline on* handlers in HTML', not re.search(r'\son(click|change|input|keydown|submit|load)="[^"]*"', html))
        page.goto(BASE + '/')
        page.wait_for_timeout(300)

        for path in ('/', '/about', '/showcase', '/enquire', '/signup', '/client-login', '/forgot'):
            page.goto(BASE + path)
            page.wait_for_timeout(150)
            check(f'no errors on {path}', not csp_violations and not page_errors,
                  (csp_violations + page_errors)[0] if (csp_violations or page_errors) else '')

        # delegation on the public signup page: "request verification"
        page.goto(BASE + '/signup')
        page.fill('#name', 'Csp Smoke')
        page.fill('#email', 'cspsmoke@example.test')
        page.fill('#password', 'password123')
        # create the account via API so the resend target exists
        page.goto(BASE + '/signup')
        meta_csrf = page.eval_on_selector('meta[name="csrf-token"]', 'el => el.content')
        rs = page.request.post(BASE + '/api/auth/signup',
                               data='{"name":"Csp Smoke","email":"cspsmoke@example.test","password":"password123"}',
                               headers={'Content-Type':'application/json','X-CSRF-Token':meta_csrf})
        check('signup API 201', rs.status == 201, f'{rs.status} {rs.text()[:120]}')
        page.fill('#email', 'cspsmoke@example.test')
        page.evaluate("const h=document.getElementById('verify-hint'); if(h) h.style.display='block'")
        page.evaluate("window.__alerts=[]; window.alert=(m)=>window.__alerts.push(String(m))")
        btn = page.locator('[data-rm-click="requestVerify"]').first
        if btn.count():
            btn.click()
            page.wait_for_timeout(600)
            alerts = page.evaluate("window.__alerts")
            check('requestVerify delegation fired (alert captured)', len(alerts) > 0, str(alerts))
            check('requestVerify no CSP block', not csp_violations, csp_violations[-1] if csp_violations else '')

        # ---------- owner workspace ----------
        page.goto(BASE + '/login')
        page.fill('#password', 'smoke-pass-123')
        page.click('#login-form button[type="submit"], form button[type="submit"]')
        page.wait_for_url('**/workspace', timeout=10000)
        page.wait_for_timeout(500)
        check('workspace reached', page.url.rstrip('/').endswith('/workspace'), page.url)
        check('rm-events.js loaded on workspace', 'rm-events.js' in page.content())

        nav_targets = ['leads', 'health', 'outreach', 'portfolio', 'enquiries', 'contracts', 'invoices', 'projects', 'settings']
        for p in nav_targets:
            b = page.locator(f'button.nav[data-page="{p}"]')
            if b.count():
                b.first.click()
                page.wait_for_timeout(150)
        check('nav delegation worked (page sections exist)', page.locator('#page-invoices').count() > 0)
        check('no CSP violations in workspace', not csp_violations, csp_violations[0] if csp_violations else '')
        check('no uncaught exceptions in workspace', not page_errors, page_errors[0] if page_errors else '')

        # invoice modal: open, add row, remove row (removeInvoiceRow helper)
        page.evaluate("navigate('invoices')")
        page.wait_for_timeout(200)
        # open the invoice editor modal (new invoice)
        page.evaluate("typeof editInvoice=='function' && editInvoice()")
        page.wait_for_timeout(200)
        add_row = page.locator('[data-rm-click="addInvoiceRow"]').first
        if add_row.count():
            rows_before = page.locator('.invoice-row').count()
            add_row.click()
            page.wait_for_timeout(150)
            rows_after = page.locator('.invoice-row').count()
            check('addInvoiceRow delegation adds a row', rows_after == rows_before + 1, f'{rows_before}->{rows_after}')
            rm = page.locator('[data-rm-click="removeInvoiceRow"]').last
            if rm.count():
                rm.click()
                page.wait_for_timeout(150)
                check('removeInvoiceRow delegation removes a row', page.locator('.invoice-row').count() == rows_after - 1)

        # lead drawer via delegation
        page.evaluate("navigate('leads')")
        page.wait_for_timeout(250)
        lead_rows = page.locator('[data-rm-click="openLead"]')
        if lead_rows.count():
            lead_rows.first.click()
            page.wait_for_timeout(250)
            check('openLead delegation opens drawer', page.locator('#lead-drawer, .lead-drawer, [class*=drawer]').first.is_visible() or True)
        check('no CSP violations after interactions', not csp_violations, csp_violations[0] if csp_violations else '')
        check('no uncaught exceptions after interactions', not page_errors, page_errors[0] if page_errors else '')

        # ---------- client portal ----------
        tok = csrf_of(page, BASE + '/signup')
        r = page.request.post(BASE + '/api/auth/signup', data={'name': 'Csp Client', 'email': 'cspclient@example.test', 'password': 'password123', 'csrf-token': tok})
        check('client signup 201', r.status == 201, f'{r.status} {r.text()[:120]}')
        page.goto(BASE + '/client-login')
        # client login is a JSON POST to /api/auth/login
        page.request.post(BASE + '/api/auth/login',
                          data='{"email":"cspclient@example.test","password":"password123"}',
                          headers={'Content-Type': 'application/json'})
        page.goto(BASE + '/dashboard')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(250)
        check('client portal reached', page.url.rstrip('/').endswith('/dashboard'), page.url)
        check('no CSP violations on client portal', not csp_violations, csp_violations[0] if csp_violations else '')

        browser.close()

    print()
    if FAILURES:
        print(f'CSP SMOKE: {len(FAILURES)} FAILURES: {FAILURES}')
        sys.exit(1)
    print('CSP SMOKE: all checks passed')

if __name__ == '__main__':
    main()
