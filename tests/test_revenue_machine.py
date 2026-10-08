"""The diagnosis machine: public audit, send gates, sample count, sourcing."""
import json
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RevenueMachineSourceTests(unittest.TestCase):
    def test_public_audit_is_on_the_public_whitelist(self):
        sec = (ROOT / 'web' / 'security.py').read_text(encoding='utf-8')
        self.assertIn("/api/public/audit", sec)
        self.assertIn("'/sourcing'", sec)
        self.assertIn("'/sending'", sec)
        self.assertIn("'/sample-report'", sec)

    def test_observe_rechecks_every_redirect_hop(self):
        probe = (ROOT / 'web' / 'web_probe.py').read_text(encoding='utf-8')
        self.assertIn('def _fetch_public', probe)
        self.assertIn('allow_redirects=False', probe)
        self.assertIn('_public_host(current)', probe)

    def test_send_keeps_approval_and_adds_daily_cap(self):
        app = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
        self.assertIn("if not v.get('approved') or not v.get('basis')", app)
        self.assertIn('SEND_DAILY_CAP', app)
        self.assertIn('Daily send cap reached', app)
        self.assertIn('List-Unsubscribe', app)

    def test_branded_html_includes_unsubscribe_url(self):
        html = (ROOT / 'web' / 'outreach_email.py').read_text(encoding='utf-8')
        self.assertIn('/unsubscribe/', html)
        self.assertIn('Unsubscribe', html)

    def test_homepage_has_url_field_and_audience_toggle(self):
        home = (ROOT / 'templates' / 'home.html').read_text(encoding='utf-8')
        self.assertIn('id="x-audit-url"', home)
        self.assertIn('/api/public/audit', home)
        self.assertIn('/sample-report', home)
        self.assertIn('href="/signup"', home)
        self.assertNotIn('id="x-who-design"', home)
        header = (ROOT / 'templates' / 'header-public.html').read_text(encoding='utf-8')
        self.assertIn("request.path != '/'", header)

    def test_sample_count_is_ten_everywhere(self):
        portfolio = (ROOT / 'web' / 'portfolio.py').read_text(encoding='utf-8')
        self.assertGreaterEqual(portfolio.count("'slug':"), 10)
        self.assertGreaterEqual(portfolio.count('"slug":') + portfolio.count("'slug':"), 10)
        about = json.loads((ROOT / 'static' / 'locales' / 'en.json').read_text(encoding='utf-8'))
        self.assertIn('10', about['about.b2_cta2'])
        self.assertNotIn('8 Templates', about['about.b2_cta2'])
        self.assertIn('10', about['about.founder_cta'])
        app = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
        self.assertIn('all 10 showcase samples', app)
        self.assertNotIn('all 8 showcase samples', app)

    def test_locales_stay_in_lockstep(self):
        keys = None
        for path in sorted((ROOT / 'static' / 'locales').glob('*.json')):
            data = json.loads(path.read_text(encoding='utf-8'))
            k = set(data)
            if keys is None:
                keys = k
            else:
                self.assertEqual(keys, k, path.name)

    def test_healthz_reports_volume_writable(self):
        app = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
        self.assertIn('persist_writable', app)
        self.assertIn('persist_path', app)

    def test_onboard_and_funnel_are_free_client_paths(self):
        billing = (ROOT / 'web' / 'billing.py').read_text(encoding='utf-8')
        self.assertIn('/api/onboard', billing)
        self.assertIn('/api/funnel/event', billing)

    def test_lead_cards_and_not_now_reason(self):
        js = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function uiStage', js)
        self.assertIn('lead-cards', js)
        self.assertIn("kind:'not_now'", js)
        self.assertIn('Work these first', js)
        index = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('value="Found"', index)
        self.assertIn('Not now', index)


@unittest.skipUnless(__import__('importlib.util').util.find_spec('flask'), 'flask not installed')
class PublicAuditLogicTests(unittest.TestCase):
    def test_preview_leaks_uses_stored_copy_not_a_forecast(self):
        from web.public_audit import preview_leaks

        def fake_observe(url, **kwargs):
            self.assertLessEqual(kwargs.get('timeout', 99), 8)
            self.assertLessEqual(kwargs.get('max_bytes', 10**9), 65536)
            return {
                'ok': True, 'reason': None, 'final_url': url, 'status': 200,
                'https': True, 'ms': 12, 'bytes': 800, 'headers': {'content-type': 'text/html'},
                'signals': {
                    'has_viewport': False, 'has_form': False, 'has_tel_or_mailto': False,
                    'has_booking_or_whatsapp': False, 'word_count': 40, 'title': '',
                    'description': '', 'https': True,
                },
                'robots': {'allowed': True}, 'link_check': {}, 'fetched_at': '2026-10-07',
            }

        out = preview_leaks('https://example.com', observe_fn=fake_observe)
        self.assertTrue(out['measured'])
        self.assertFalse(out['full_report'])
        self.assertIn('not a revenue forecast', (out.get('label') or '').lower())
        self.assertLessEqual(out['leak_count'], 3)
        self.assertTrue(out['leaks'])
        for leak in out['leaks']:
            self.assertIn('title', leak)
            self.assertIn('leak', leak)
        story = out.get('narrative') or ''
        self.assertIn('https://example.com', story)
        self.assertIn('HTTP 200', story)
        self.assertTrue(any(leak['title'] in story for leak in out['leaks']))
        self.assertIn('not a revenue forecast', story.lower())
        self.assertNotIn('will earn', story.lower())


if __name__ == '__main__':
    unittest.main()
