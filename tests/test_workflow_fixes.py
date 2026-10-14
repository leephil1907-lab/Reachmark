"""Map → crew workflow fixes: SMTP aliases, sender defaults, pitch fit, WhatsApp links,
Overpass fallback, Google Places in map scans, and the outreach e-mail copy.

No test touches the network: providers and requests are patched.
"""
import os
import unittest
from unittest.mock import patch, MagicMock

from tests.test_app import ProspectTests, module
from web import mail_env, places_provider
import web.map_provider as map_provider


class SmtpEnvTests(unittest.TestCase):
    def test_aliases_fill_canonical_names_without_overwriting(self):
        env = {'SMTP_SERVER': 'smtp.gmail.com', 'SMTP_USERNAME': 'studio@gmail.com',
               'SMTP_PASS': 'abcd efgh ijkl mnop', 'SMTP_PORT': '465'}
        mail_env.normalize_smtp_env(env)
        self.assertEqual(env['SMTP_HOST'], 'smtp.gmail.com')
        self.assertEqual(env['SMTP_USER'], 'studio@gmail.com')
        self.assertEqual(env['SMTP_PASSWORD'], 'abcd efgh ijkl mnop')
        self.assertEqual(env['SMTP_FROM'], 'studio@gmail.com')  # Gmail: From = login
        self.assertEqual(env['SMTP_SECURITY'], 'ssl')           # port 465 → implicit TLS
        env2 = {'SMTP_HOST': 'smtp.resend.com', 'SMTP_SERVER': 'ignored', 'SMTP_FROM': 'hi@x.test',
                'SMTP_SECURITY': 'TLS'}
        mail_env.normalize_smtp_env(env2)
        self.assertEqual(env2['SMTP_HOST'], 'smtp.resend.com')
        self.assertEqual(env2['SMTP_SECURITY'], 'starttls')

    def test_from_header_adds_a_person_and_studio(self):
        with patch.dict(os.environ, {'SMTP_FROM': 'studio@gmail.com'}):
            header = mail_env.from_header({'sender_name': 'Ernest Micheal', 'agency': 'Reachmark'})
            self.assertIn('Ernest Micheal', header)
            self.assertIn('<studio@gmail.com>', header)
            self.assertEqual(mail_env.from_domain(), 'gmail.com')
        with patch.dict(os.environ, {'SMTP_FROM': 'Reachmark Studio <hi@reachmarkdigital.xyz>'}):
            self.assertIn('Reachmark Studio', mail_env.from_header({'sender_name': 'X'}))
            self.assertEqual(mail_env.from_domain(), 'reachmarkdigital.xyz')


class SenderProfileTests(unittest.TestCase):
    setUp = ProspectTests.setUp
    tearDown = ProspectTests.tearDown

    def test_blank_profile_falls_back_to_studio_details(self):
        s = module.settings()
        self.assertEqual(s['sender_name'], 'Ernest Micheal')
        self.assertEqual(s['agency'], 'Reachmark')
        self.assertEqual(s['reply_email'], 'support@reachmarkdigital.xyz')
        self.assertTrue(s['postal_address'])

    def test_saved_values_still_win(self):
        with module.db() as c:
            c.execute("INSERT OR REPLACE INTO settings(id,data) VALUES(1,?)",
                      ('{"sender_name":"Ada","agency":"Studio A","reply_email":"","postal_address":"1 Road"}',))
        s = module.settings()
        self.assertEqual((s['sender_name'], s['agency'], s['postal_address']), ('Ada', 'Studio A', '1 Road'))
        self.assertEqual(s['reply_email'], 'support@reachmarkdigital.xyz')  # blank → default


class OutreachCopyTests(unittest.TestCase):
    def _email(self, settings, lead=None):
        from web.outreach_email import build_outreach_email
        lead = lead or {'name': 'Kilimanjaro Restaurant', 'category': 'Restaurant', 'city': 'Lagos', 'token': 't1'}
        site = {'copy': {'tag': 'Fresh flavour, daily', 'about': 'A restaurant. From the first morning bake…'}}
        return build_outreach_email(lead, {'token': 'tok'}, site, settings, audit=None, locale='en')

    def test_no_duplicate_identity_and_no_empty_heading(self):
        text = self._email({'agency': 'Reachmark', 'sender_name': 'Reachmark',
                            'public_base_url': 'https://reachmarkdigital.xyz'})['text']
        self.assertNotIn('Reachmark from Reachmark', text)
        self.assertNotIn('Reachmark\nReachmark', text)
        self.assertIn('“Fresh flavour, daily”.', text)
        self.assertNotIn('morning bake', text)
        head = text.index('What the page would give you')
        self.assertTrue(text[head:].split('\n')[1].strip().startswith('\u2022'))
        self.assertLessEqual(len(text.split()), 150)

    def test_named_sender(self):
        mail = self._email({'agency': 'Reachmark', 'sender_name': 'Ernest Micheal',
                            'public_base_url': 'https://reachmarkdigital.xyz'})
        self.assertIn("I'm Ernest Micheal from Reachmark", mail['text'])
        self.assertIn('<li', mail['html'])

    def test_live_site_gets_a_refresh_intro(self):
        lead = {'name': 'Kili', 'category': 'Restaurant', 'website': 'https://kili.example', 'status': 'HAS_WEBSITE'}
        text = self._email({'agency': 'Reachmark', 'sender_name': 'Ernest Micheal'}, lead)['text']
        self.assertIn('refreshed', text)


class DiningImageryTests(unittest.TestCase):
    def test_restaurants_get_dining_photos_and_bakeries_keep_theirs(self):
        from web.concept import build_theme
        dining = build_theme('food', {}, 'Restaurant Mama Put')['showcase']
        bakery = build_theme('food', {}, 'Bakery Sunrise')['showcase']
        self.assertIn('/dining/', dining['hero'])
        self.assertEqual(dining['kicker_key'], 'pc.case_k_dining')
        self.assertIn('hero-oven', bakery['hero'])
        for path in [dining['hero'], dining['craft'], dining['strip'], *dining['offers']]:
            self.assertTrue(os.path.exists(path.lstrip('/')), path)


class PitchFitTests(unittest.TestCase):
    def test_working_site_without_a_gap_is_held_back(self):
        from agents.agent_scribe import pitch_fit
        live = {'website': 'https://x.example', 'audit_status': 'LIVE'}
        ok_obs = {'ok': True, 'signals': {'viewport': True, 'has_contact_link': True}}
        self.assertFalse(pitch_fit(live, ok_obs)[0])
        self.assertTrue(pitch_fit(live, {'ok': True, 'signals': {'viewport': False, 'has_contact_link': True}})[0])
        self.assertTrue(pitch_fit({'website': ''}, {})[0])
        self.assertTrue(pitch_fit({'website': 'https://x', 'audit_status': 'DNS_UNRESOLVED'}, {})[0])
        self.assertFalse(pitch_fit({'website': 'https://x', 'audit_status': 'BLOCKED'}, {})[0])
        # Not observed (offline demo / not audited): nothing proves the site works.
        self.assertTrue(pitch_fit({'website': 'https://x', 'audit_status': 'NOT_OBSERVED'}, {})[0])

    def test_whatsapp_link_normalises_local_numbers(self):
        from agents.agent_closer import whatsapp_url
        self.assertTrue(whatsapp_url('0803 639 5555', 'Hi').startswith('https://wa.me/2348036395555?text=Hi'))
        self.assertTrue(whatsapp_url('+44 7700 900123', 'x').startswith('https://wa.me/447700900123'))
        self.assertEqual(whatsapp_url('', 'x'), '')
        self.assertEqual(whatsapp_url('12', 'x'), '')


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self.headers = {}
        self._payload = payload or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, n):
        import json
        yield json.dumps(self._payload).encode()

    def json(self):
        return self._payload


class OverpassFallbackTests(unittest.TestCase):
    def setUp(self):
        map_provider._cooldown.clear()
        map_provider._rate_until = 0.0
        map_provider._last = 0.0

    tearDown = setUp

    def test_406_moves_to_the_next_mirror_instead_of_freezing(self):
        replies = [_Resp(406), _Resp(200, {'elements': [{'type': 'node', 'id': 1}]})]
        with patch.object(map_provider, 'ENDPOINTS', ['https://a.test/api', 'https://b.test/api']), \
             patch('web.map_provider.time.sleep'), \
             patch('web.map_provider.requests.post', side_effect=replies) as post:
            data = map_provider.query_overpass('[out:json];', {})
        self.assertEqual(len(data['elements']), 1)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(map_provider._rate_until, 0.0)

    def test_429_is_still_respected(self):
        with patch.object(map_provider, 'ENDPOINTS', ['https://a.test/api', 'https://b.test/api']), \
             patch('web.map_provider.time.sleep'), \
             patch('web.map_provider.requests.post', side_effect=[_Resp(429)]) as post:
            with self.assertRaises(ValueError):
                map_provider.query_overpass('[out:json];', {})
        self.assertEqual(post.call_count, 1)


class GoogleMapScanTests(unittest.TestCase):
    setUp = ProspectTests.setUp
    tearDown = ProspectTests.tearDown

    def test_box_search_sends_a_rectangle_and_tags_the_category(self):
        payload = {'places': [{'id': 'g1', 'displayName': {'text': 'Mama Put Yaba'}, 'websiteUri': '',
                               'internationalPhoneNumber': '+234 803 000 0000',
                               'location': {'latitude': 6.51, 'longitude': 3.37}}]}
        with patch.dict(os.environ, {'GOOGLE_PLACES_API_KEY': 'k'}), \
             patch('web.places_provider.time.sleep'), \
             patch('web.places_provider.requests.post', return_value=_Resp(200, payload)) as post:
            rows, reason, capped = places_provider.discover_in_box('Restaurant', [6.5, 3.36, 6.52, 3.38], 'Yaba')
        body = post.call_args.kwargs['json']
        self.assertEqual(body['locationRestriction']['rectangle']['low'], {'latitude': 6.5, 'longitude': 3.36})
        self.assertEqual((reason, capped), ('', False))
        self.assertEqual(rows[0]['category'], 'Restaurant')
        self.assertEqual(rows[0]['source'], 'Google Maps')

    def test_scan_saves_google_rows_when_overpass_is_down(self):
        with patch('web.maps.threading.Thread'):
            sid = self.client.post('/api/map/scans', json={'category': 'Restaurant', 'label': 'Yaba',
                                                          'bounds': [6.50, 3.36, 6.52, 3.38]}).json['id']
        google = [{'source_key': 'google:g1', 'name': 'Mama Put Yaba', 'category': 'Restaurant', 'city': 'Yaba',
                   'phone': '+234 803 000 0000', 'latitude': 6.51, 'longitude': 3.37, 'source': 'Google Maps'}]
        with patch('web.maps.places_available', return_value=True), \
             patch('web.maps.discover_in_box', return_value=(google, '', False)), \
             patch('web.maps.query_overpass', side_effect=ValueError('down')), \
             self.assertLogs(module.app.logger, level='WARNING'):
            module.app.extensions['map_worker'](sid)
        scan = self.client.get('/api/map/state').json['scans'][0]
        self.assertEqual(scan['cells'][0]['state'], 'checked')
        self.assertIn('Google Maps', scan['cells'][0]['message'])
        leads = self.client.get('/api/state').json['leads']
        self.assertEqual([l['name'] for l in leads], ['Mama Put Yaba'])

    def test_google_and_osm_twins_merge_but_chain_branches_stay(self):
        from web.maps import _combine
        g = [{'name': 'Chicken Spot', 'latitude': 6.5100, 'longitude': 3.3700, 'email': ''}]
        osm = [{'name': 'Chicken Spot', 'latitude': 6.5101, 'longitude': 3.3701, 'email': 'hi@spot.example'},
               {'name': 'Chicken Spot', 'latitude': 6.6000, 'longitude': 3.4500}]
        rows = _combine(g, osm)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['email'], 'hi@spot.example')


if __name__ == '__main__':
    unittest.main()
