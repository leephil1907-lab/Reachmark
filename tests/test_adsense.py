"""AdSense: the loader + account meta are served on public pages only.

The tags are injected at serve time, so templates — including about.html, which
must stay byte-identical — are never touched.
"""
import os
import unittest
from unittest.mock import patch

import tests.test_app as test_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = 'ca-pub-3894582071697384'
META = f'<meta name="google-adsense-account" content="{CLIENT}">'
LOADER = f'pagead/js/adsbygoogle.js?client={CLIENT}'


class AdSenseTests(unittest.TestCase):
    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def test_public_pages_carry_the_tags_exactly_once(self):
        for path in ('/', '/about', '/showcase', '/enquire', '/receptionist'):
            body = self.client.get(path).get_data(as_text=True)
            self.assertIn(META, body, path)
            self.assertIn(LOADER, body, path)
            self.assertEqual(body.count('adsbygoogle.js'), 1, f'double injection on {path}')

    def test_private_pages_and_apis_are_excluded(self):
        for path in ('/workspace', '/login'):
            body = self.client.get(path).get_data(as_text=True)
            self.assertNotIn('adsbygoogle', body, path)
            self.assertNotIn('google-adsense-account', body, path)
        api = self.client.get('/api/state')
        self.assertNotIn('adsbygoogle', api.get_data(as_text=True))

    def test_ads_txt_declares_the_seller(self):
        response = self.client.get('/ads.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response.headers.get('Content-Type', ''))
        self.assertEqual(response.get_data(as_text=True),
                         'google.com, pub-3894582071697384, DIRECT, f08c47fec0942fa0\n')

    def test_content_security_policy_allows_the_loader(self):
        policy = self.client.get('/').headers.get('Content-Security-Policy', '')
        self.assertIn('https://pagead2.googlesyndication.com', policy)
        self.assertIn('https://googleads.g.doubleclick.net', policy)
        self.assertNotIn('\\', policy)
        self.assertIn("img-src 'self'", policy)

    def test_content_security_policy_allows_display_ad_creatives(self):
        policy = self.client.get('/').headers.get('Content-Security-Policy', '')
        self.assertIn('https://tpc.googlesyndication.com', policy)

    def test_display_placements_render_when_slot_configured(self):
        with patch.dict(os.environ, {'ADSENSE_DISPLAY_SLOT': '1234567890'}):
            for path in ('/', '/showcase'):
                body = self.client.get(path).get_data(as_text=True)
                self.assertIn('ADVERTISEMENT', body, path)
                self.assertIn('data-ad-slot="1234567890"', body, path)
                self.assertIn(f'data-ad-client="{CLIENT}"', body, path)

    def test_display_placements_hidden_without_slot(self):
        with patch.dict(os.environ, {'ADSENSE_DISPLAY_SLOT': ''}):
            for path in ('/', '/showcase'):
                body = self.client.get(path).get_data(as_text=True)
                self.assertNotIn('data-ad-slot', body, path)
                self.assertNotIn('ADVERTISEMENT', body, path)

    def test_about_template_file_is_untouched(self):
        with open(os.path.join(ROOT, 'templates', 'about.html'), encoding='utf-8') as handle:
            source = handle.read()
        self.assertNotIn('adsbygoogle', source)
        self.assertNotIn('google-adsense-account', source)
