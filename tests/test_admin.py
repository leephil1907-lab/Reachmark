"""Admin console: reached only at /admin, never linked from the public site,
and it shows what visitors and customers do (sign-ups first)."""
import os
import re
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from tests.test_app import module
from tests.test_growth import SwitchedBase

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'admin-test-password'
STRICT = {'OWNER_PASSWORD_HASH': generate_password_hash(PASSWORD, method='pbkdf2:sha256:1000')}
PUBLIC_PAGES = ('/', '/about', '/showcase', '/pricing', '/reviews', '/receptionist', '/enquire',
                '/privacy', '/terms', '/disclosure', '/signin', '/signup', '/app')


class AdminAddressTests(SwitchedBase):
    def test_admin_signed_out_is_the_owner_password_form(self):
        with patch.dict(os.environ, STRICT):
            r = self.client.get('/admin')
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn('name="password"', body)
        self.assertNotIn('id="page-activity"', body)
        self.assertIn('noindex', r.headers.get('X-Robots-Tag', ''))
        self.assertIn('no-store', r.headers.get('Cache-Control', ''))

    def test_owner_signs_in_at_admin_and_lands_on_activity(self):
        with patch.dict(os.environ, STRICT):
            page = self.client.get('/admin').get_data(as_text=True)
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
            r = self.client.post('/admin', data={'password': PASSWORD, 'csrf_token': csrf})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(r.headers['Location'], '/admin')
            body = self.client.get('/admin').get_data(as_text=True)
        self.assertIn('id="page-activity"', body)
        self.assertIn('data-page="activity"', body)
        self.assertIn('/static/activity.js', body)

    def test_old_addresses_forward(self):
        self.assertEqual(self.client.get('/login').headers['Location'], '/signin')
        self.switch_owner()
        self.assertEqual(self.client.get('/workspace').headers['Location'], '/admin')
        self.assertEqual(self.client.get('/dashboard').headers['Location'], '/admin')

    def test_customers_never_get_the_admin_console(self):
        self.make_client()
        with patch.dict(os.environ, STRICT):
            body = self.client.get('/admin').get_data(as_text=True)
            self.assertNotIn('id="page-activity"', body)
            self.assertIn(self.client.get('/api/admin/activity').status_code, (401, 403))
            dash = self.client.get('/dashboard').get_data(as_text=True)
        self.assertNotIn('page-activity', dash)
        self.assertNotIn('activity.js', dash)

    def test_public_site_has_no_way_into_admin(self):
        for who in ('anon', 'owner'):
            if who == 'owner':
                self.switch_owner()
            for path in PUBLIC_PAGES:
                r = self.client.get(path)
                if r.status_code in (301, 302):  # e.g. a signed-in owner on /signin is sent to /admin
                    continue
                body = r.get_data(as_text=True)
                for needle in ('href="/admin', 'href="/workspace', 'href="/login', "location.href='/login'"):
                    self.assertNotIn(needle, body, f'{who} {path} links the admin console: {needle}')
        theme = (ROOT / 'static' / 'theme.js').read_text()
        self.assertNotRegex(theme, r"location[^;\n]*['\"]/(admin|login|workspace)",
                            'hidden keyboard/click shortcut to the owner console')

    def test_verify_banner_help_link_goes_somewhere_real(self):
        self.make_client()
        body = self.client.get('/dashboard').get_data(as_text=True)
        self.assertNotIn('href="/verify"', body)  # only /verify/<token> exists
        self.assertIn('href="/enquire"', body)

    def test_google_verification_files_are_public(self):
        with patch.dict(os.environ, STRICT):
            r = self.client.get('/googled647aceebb4093df.html')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_data(as_text=True), 'google-site-verification: googled647aceebb4093df.html')

    def test_customer_dashboard_skips_owner_only_modules(self):
        self.make_client()
        body = self.client.get('/dashboard').get_data(as_text=True)
        self.assertIn('data-view="client"', body)
        self.assertNotIn('rm-command-center', body)  # owner revenue card
        for script in ('production.js', 'outreach.js', 'crew.js', 'google-business.js', 'opportunity.js'):
            src = (ROOT / 'static' / script).read_text()
            self.assertIn("dataset.view", src, f'{script} must not auto-load owner APIs for customers')

    def test_robots_does_not_advertise_admin(self):
        self.assertNotIn('/admin', self.client.get('/robots.txt').get_data(as_text=True))


class AdminActivityTests(SwitchedBase):
    def activity(self):
        with patch.dict(os.environ, STRICT):
            # owner_guard's session revision is sha256 of the stored hash
            self.switch_owner(STRICT['OWNER_PASSWORD_HASH'])
            r = self.client.get('/api/admin/activity')
        self.assertEqual(r.status_code, 200)
        return r.get_json()

    def test_activity_api_is_owner_only(self):
        with patch.dict(os.environ, STRICT):
            self.assertEqual(self.client.get('/api/admin/activity').status_code, 401)

    def test_new_signup_shows_up_in_admin(self):
        before = self.activity()
        self.assertEqual(before['users']['total'], 0)
        with self.client.session_transaction() as s:
            s.clear()
        page = self.client.get('/signup').get_data(as_text=True)
        tok = re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)
        r = self.client.post('/api/auth/signup', json={'name': 'Ada Lovelace', 'email': 'ada@example.test',
                                                       'password': 'password123'}, headers={'X-CSRF-Token': tok})
        self.assertEqual(r.status_code, 201)
        after = self.activity()
        self.assertEqual(after['users']['total'], 1)
        self.assertEqual(after['users']['today'], 1)
        self.assertEqual(after['users']['week'], 1)
        self.assertEqual(after['users']['verified'], 0)
        newest = after['signups'][0]
        self.assertEqual((newest['email'], newest['name'], newest['via']), ('ada@example.test', 'Ada Lovelace', 'Email'))
        self.assertNotIn('password_hash', newest)
        self.assertTrue(any('Client account created: ada@example.test' in f['message'] for f in after['feed']))
        self.assertGreater(after['latest_id'], before['latest_id'])

    def test_feed_shows_customer_actions_not_owner_chores(self):
        module.log('enquiry', 'New quote request from Sam (sam@example.test)')
        module.log('newsletter', 'Newsletter sign-up: fan@example.test')
        module.log('account', 'Owner closed a client account')
        module.log('crew', 'Scout found 12 businesses')
        module.log('receptionist', 'Receptionist thread marked handled')
        msgs = [f['message'] for f in self.activity()['feed']]
        self.assertIn('New quote request from Sam (sam@example.test)', msgs)
        self.assertIn('Newsletter sign-up: fan@example.test', msgs)
        for hidden in ('Owner closed a client account', 'Scout found 12 businesses', 'Receptionist thread marked handled'):
            self.assertNotIn(hidden, msgs)

    def test_since_counts_new_entries(self):
        module.log('review', 'New review from Tobi')
        first = self.activity()['latest_id']
        module.log('review', 'New review from Kemi')
        with patch.dict(os.environ, STRICT):
            d = self.client.get(f'/api/admin/activity?since={first}').get_json()
        self.assertEqual(d['new_since'], 1)


class VercelStoppedTests(SwitchedBase):
    def test_vercel_does_not_deploy_and_only_redirects(self):
        import json
        cfg = json.loads((ROOT / 'vercel.json').read_text())
        self.assertIs(cfg.get('git', {}).get('deploymentEnabled'), False)
        src = (ROOT / 'api' / 'index.py').read_text()
        self.assertNotIn('web.app', src)
        self.assertNotIn('SECRET_KEY', src)
        self.assertIn('reachmarkdigital.xyz', src)
