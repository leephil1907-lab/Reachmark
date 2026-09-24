"""Motion refresh: one shared header, Framer-style transitions, live pipeline,
no dead clicks, and crypto prices locked in line with the cards."""
import json
import os
import re
import unittest
from unittest.mock import patch

import tests.test_app as test_app
from tests.test_billing import BillingBase
from web.billing import TIERS, price_for

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADER_PAGES = ('/', '/pricing', '/showcase', '/enquire')
MOTION_PAGES = HEADER_PAGES + ('/receptionist', '/showcase/ember-coffee')
PUBLIC_PAGES = ('/', '/about', '/pricing', '/showcase', '/enquire',
                '/receptionist', '/reviews', '/signup', '/signin')


class SharedHeaderTests(unittest.TestCase):
    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def test_one_professional_header_everywhere(self):
        for path in HEADER_PAGES:
            body = self.client.get(path).get_data(as_text=True)
            for needle in ('pub-head', 'pub-menu-btn', 'theme-toggle-public',
                           '/static/header.css', '/static/theme.js', 'page-veil'):
                self.assertIn(needle, body, f'{needle} on {path}')

    def test_header_nav_stays_slim_on_every_page(self):
        for path in HEADER_PAGES:
            body = self.client.get(path).get_data(as_text=True)
            nav = body.split('<nav class="main"')[1].split('</nav>')[0]
            for label in ('Reviews', 'About', 'Enquire', 'Plans'):
                self.assertIn(label, nav, f'{label} on {path}')
            for label in ('Samples', 'Receptionist'):
                self.assertNotIn(label, nav, f'{label} leaked into header on {path}')

    def test_current_page_is_marked(self):
        body = self.client.get('/pricing').get_data(as_text=True)
        self.assertIn('<a href="/pricing" aria-current="page">', body)


class MotionTests(unittest.TestCase):
    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def test_motion_kit_loads_on_marketing_pages(self):
        for path in MOTION_PAGES:
            body = self.client.get(path).get_data(as_text=True)
            self.assertIn('/static/motion.css', body, path)
            self.assertIn('/static/motion.js', body, path)
            self.assertIn('page-veil', body, path)

    def test_heroes_split_and_sections_reveal(self):
        for path in ('/', '/pricing', '/showcase', '/receptionist',
                     '/showcase/ember-coffee'):
            body = self.client.get(path).get_data(as_text=True)
            self.assertIn('data-split', body, f'split hero on {path}')
            # /receptionist animates through the older data-reveal system.
            self.assertTrue('data-motion' in body or 'data-reveal' in body,
                            f'reveals on {path}')

    def test_homepage_is_a_live_illustrator(self):
        body = self.client.get('/').get_data(as_text=True)
        for needle in ('data-pipeline', 'Watch a stranger become a customer',
                       'pipeline-dots', 'data-count="10"', 'data-count="8"',
                       'data-count="6"', 'Illustrated demo of the real crew',
                       'data-magnet'):
            self.assertIn(needle, body)

    def test_no_dead_header_css_left_on_pricing(self):
        body = self.client.get('/pricing').get_data(as_text=True)
        self.assertNotIn('public-nav', body)
        self.assertNotIn('public-links', body)

    def test_script_tags_are_all_closed(self):
        for path in PUBLIC_PAGES + ('/showcase/ember-coffee',):
            body = self.client.get(path).get_data(as_text=True)
            opens = len(re.findall(r'<script[\s>]', body))
            closes = body.count('</script>')
            self.assertEqual(opens, closes, f'unclosed <script> on {path}')


class ClickMeaningTests(unittest.TestCase):
    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def test_no_dead_hash_links_on_public_pages(self):
        for path in PUBLIC_PAGES:
            body = self.client.get(path).get_data(as_text=True)
            self.assertNotIn('href="#"', body, f'dead link on {path}')

    def test_resend_controls_are_real_buttons(self):
        for path in ('/signup', '/signin'):
            body = self.client.get(path).get_data(as_text=True)
            self.assertIn('requestVerify(event)', body, path)
            self.assertIn('<button type="button" onclick="requestVerify(event)"', body, path)

    def test_outreach_surface_lists_reviews(self):
        sitemap = self.client.get('/sitemap.xml').get_data(as_text=True)
        self.assertIn('/reviews', sitemap)
        robots = self.client.get('/robots.txt').get_data(as_text=True)
        self.assertIn('Allow: /reviews', robots)


class PricingParityTests(BillingBase):
    def test_crypto_options_match_the_cards(self):
        body = self.client.get('/pricing').get_data(as_text=True)
        m = re.search(r'<select id="crypto-tier">(.*?)</select>', body, re.S)
        self.assertIsNotNone(m)
        options = m.group(1)
        for tier in ('starter', 'pro'):
            self.assertIn(f'data-m="{TIERS[tier]["usd"]}"', options, tier)
            self.assertIn(f'data-a="{TIERS[tier]["usd_annual"]}"', options, tier)
            self.assertIn(TIERS[tier]['usd'], options, tier)
        self.assertNotIn('$25', body)
        self.assertNotIn('$35', body)

    def test_crypto_api_quotes_card_prices(self):
        self.make_client()
        with patch.dict('os.environ', {'BTC_WALLET': 'bc1testwalletaddress0000000000000000000',
                                       'ETH_WALLET': '', 'SOL_WALLET': '',
                                       'USDT_TRC20_WALLET': ''}, clear=False):
            for tier in ('starter', 'pro'):
                for period in ('monthly', 'annual'):
                    r = self.client.get(f'/api/billing/crypto?tier={tier}&period={period}')
                    self.assertEqual(r.status_code, 200, f'{tier}/{period}')
                    coins = r.get_json()['coins']
                    self.assertTrue(coins, f'no coins for {tier}/{period}')
                    self.assertEqual(coins[0]['usd'], price_for(tier, 'USD', period)[0] / 100)

    def test_no_stale_prices_in_any_locale(self):
        for code in ('en', 'es', 'fr', 'de', 'pt', 'zh'):
            with open(os.path.join(ROOT, 'static', 'locales', code + '.json'), encoding='utf-8') as handle:
                text = handle.read()
            self.assertNotIn('$25', text, code)
            self.assertNotIn('$35', text, code)
            data = json.loads(text)
            self.assertIn(TIERS['starter']['usd'].replace('$', ''), data['pay.c_os'], code)
            self.assertIn(TIERS['pro']['usd'].replace('$', ''), data['pay.c_op'], code)


if __name__ == '__main__':
    unittest.main()
