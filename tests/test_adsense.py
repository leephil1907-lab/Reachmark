"""AdSense: the loader + account meta are served on marketing pages + workspace.

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
        for path in ('/', '/about', '/showcase', '/showcase/ember-coffee', '/enquire',
                     '/receptionist', '/reviews', '/pricing', '/workspace'):
            body = self.client.get(path).get_data(as_text=True)
            self.assertIn(META, body, path)
            self.assertIn(LOADER, body, path)
            self.assertEqual(body.count('adsbygoogle.js'), 1, f'double injection on {path}')

    def test_private_pages_and_apis_are_excluded(self):
        for path in ('/login',):
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

    def test_real_ad_units_render_in_place(self):
        home = self.client.get('/').get_data(as_text=True)
        self.assertIn('adsense-homepage-banner', home)
        self.assertIn('data-ad-slot="1905478104"', home)
        self.assertIn('adsense-footer', home)
        self.assertIn('data-ad-slot="6774661404"', home)
        # Banner sits between the hero and the rest of the homepage.
        self.assertLess(home.index('1905478104'), home.index('Fresh from the gallery'))
        for path in ('/showcase', '/enquire', '/pricing', '/receptionist'):
            body = self.client.get(path).get_data(as_text=True)
            self.assertIn('data-ad-slot="6774661404"', body, path)
        sample = self.client.get('/showcase/ember-coffee').get_data(as_text=True)
        self.assertIn('adsense-footer', sample)
        self.assertIn('data-ad-slot="6774661404"', sample)
        desk = self.client.get('/workspace').get_data(as_text=True)
        self.assertIn('adsense-sidebar', desk)
        self.assertIn('data-ad-slot="2566903210"', desk)

    def test_real_units_ignore_the_old_display_slot_env(self):
        with patch.dict(os.environ, {'ADSENSE_DISPLAY_SLOT': ''}):
            body = self.client.get('/').get_data(as_text=True)
            self.assertIn('data-ad-slot="1905478104"', body)
            self.assertIn('data-ad-slot="6774661404"', body)

    def test_about_template_file_is_untouched(self):
        with open(os.path.join(ROOT, 'templates', 'about.html'), encoding='utf-8') as handle:
            source = handle.read()
        self.assertNotIn('adsbygoogle', source)
        self.assertNotIn('google-adsense-account', source)
