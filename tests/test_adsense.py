"""AdSense: the loader + account meta are served on marketing pages + workspace.

The tags are injected at serve time, so templates are never edited for ads.
"""
import os
import unittest
from unittest.mock import patch

import tests.test_app as test_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = 'ca-pub-5678865896620902'
META = f'<meta name="google-adsense-account" content="{CLIENT}">'
LOADER = f'pagead/js/adsbygoogle.js?client={CLIENT}'


class AdSenseTests(unittest.TestCase):
    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def test_public_pages_carry_the_tags_exactly_once(self):
        for path in ('/about', '/showcase', '/showcase/ember-coffee', '/enquire',
                     '/receptionist', '/reviews', '/pricing', '/privacy', '/terms',
                     '/disclosure', '/app'):
            body = self.client.get(path).get_data(as_text=True)
            self.assertIn(META, body, path)
            self.assertIn(LOADER, body, path)
            self.assertEqual(body.count('adsbygoogle.js'), 1, f'double injection on {path}')

    def test_homepage_carries_verification_but_no_ad_units(self):
        """Google verifies the site on the homepage, so the account tag lives there once.

        No ad units are placed on the homepage.
        """
        body = self.client.get('/').get_data(as_text=True)
        self.assertIn(META, body)
        self.assertIn(LOADER, body)
        self.assertEqual(body.count('adsbygoogle.js'), 1, 'double injection on /')
        self.assertNotIn('<ins class="adsbygoogle"', body)
        self.assertNotIn('adsense-homepage-banner', body)
        self.assertNotIn('adsense-footer', body)

    def test_unsubscribe_and_prospect_mockups_carry_the_tags(self):
        import web.app as webapp
        self.assertIn('/unsubscribe/', webapp.ADSENSE_PREFIXES)
        self.assertIn('/preview/', webapp.ADSENSE_PREFIXES)

    def test_publisher_id_comes_from_the_environment(self):
        import web.app as webapp
        self.assertEqual(webapp.ADSENSE_CLIENT, os.getenv('ADSENSE_CLIENT', CLIENT).strip())

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
                         'google.com, pub-5678865896620902, DIRECT, f08c47fec0942fa0\n')

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
        self.assertNotIn('adsense-homepage-banner', home)
        self.assertNotIn('data-ad-slot="1905478104"', home)
        self.assertNotIn('adsense-footer', home)
        for path in ('/showcase', '/enquire', '/pricing', '/receptionist'):
            body = self.client.get(path).get_data(as_text=True)
            self.assertIn('data-ad-slot="6774661404"', body, path)
        sample = self.client.get('/showcase/ember-coffee').get_data(as_text=True)
        self.assertIn('adsense-footer', sample)
        self.assertIn('data-ad-slot="6774661404"', sample)
        with self.client.session_transaction() as session:
            session['owner'] = True
            session['csrf'] = 'test-csrf'
        desk = self.client.get('/workspace').get_data(as_text=True)
        self.assertIn('adsense-sidebar', desk)
        self.assertIn('data-ad-slot="2566903210"', desk)

    def test_real_units_ignore_the_old_display_slot_env(self):
        with patch.dict(os.environ, {'ADSENSE_DISPLAY_SLOT': ''}):
            body = self.client.get('/showcase').get_data(as_text=True)
            self.assertIn('data-ad-slot="6774661404"', body)

    def test_about_template_file_is_untouched(self):
        with open(os.path.join(ROOT, 'templates', 'about.html'), encoding='utf-8') as handle:
            source = handle.read()
        self.assertNotIn('adsbygoogle', source)
        self.assertNotIn('google-adsense-account', source)

    def test_only_the_homepage_template_hardcodes_the_tag(self):
        """Ads are injected at serve time; no other template carries the loader by hand."""
        templates = os.path.join(ROOT, 'templates')
        offenders = []
        for name in sorted(os.listdir(templates)):
            if not name.endswith('.html') or name == 'home.html':
                continue
            with open(os.path.join(templates, name), encoding='utf-8') as handle:
                if 'adsbygoogle.js' in handle.read():
                    offenders.append(name)
        self.assertEqual(offenders, [])
