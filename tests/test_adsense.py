"""AdSense account verification and public-page loader regression tests."""
import os
import unittest

import tests.test_app as test_app

CLIENT = 'ca-pub-5678865896620902'
META = f'<meta name="google-adsense-account" content="{CLIENT}">'
LOADER = f'pagead/js/adsbygoogle.js?client={CLIENT}'
SELLER = 'google.com, pub-5678865896620902, DIRECT, f08c47fec0942fa0'


class AdSenseTests(unittest.TestCase):
    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def test_public_pages_carry_account_meta_and_loader_once(self):
        for i, path in enumerate(('/', '/about', '/showcase', '/showcase/ember-coffee',
                                  '/enquire', '/receptionist', '/reviews', '/pricing'), start=1):
            body = self.client.get(path, environ_overrides={'REMOTE_ADDR': f'192.0.2.{i}'}).get_data(as_text=True)
            self.assertIn(META, body, path)
            self.assertIn(LOADER, body, path)
            self.assertEqual(body.count('adsbygoogle.js'), 1, f'double injection on {path}')

    def test_private_pages_and_apis_are_excluded(self):
        for i, path in enumerate(('/signin', '/signup', '/workspace', '/dashboard'), start=21):
            body = self.client.get(path, environ_overrides={'REMOTE_ADDR': f'192.0.2.{i}'}).get_data(as_text=True)
            self.assertNotIn('adsbygoogle', body, path)
            self.assertNotIn('google-adsense-account', body, path)
        api = self.client.get('/api/state')
        self.assertNotIn('adsbygoogle', api.get_data(as_text=True))

    def test_ads_txt_declares_the_supplied_publisher(self):
        response = self.client.get('/ads.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response.headers.get('Content-Type', ''))
        self.assertEqual(response.get_data(as_text=True).strip(), SELLER)

    def test_no_manual_ad_unit_renders_without_a_configured_slot(self):
        for path in ('/', '/about', '/showcase', '/enquire', '/pricing',
                     '/receptionist', '/workspace'):
            body = self.client.get(path, environ_overrides={'REMOTE_ADDR': '192.0.2.41'}).get_data(as_text=True)
            self.assertNotIn('data-ad-slot=', body, path)

    def test_content_security_policy_allows_the_ad_loader(self):
        policy = self.client.get('/').headers.get('Content-Security-Policy', '')
        self.assertIn('https://pagead2.googlesyndication.com', policy)
        self.assertIn('https://googleads.g.doubleclick.net', policy)
        self.assertIn('https://tpc.googlesyndication.com', policy)
        self.assertNotIn('\\\\', policy)


if __name__ == '__main__':
    unittest.main()
