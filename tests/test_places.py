"""Google Places discovery — key-gated, bounded, and never fatal.

These tests never touch the network: ``requests.post`` is patched.
"""
import os
import unittest
from unittest.mock import patch, MagicMock

from web import places_provider


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


SAMPLE = {
    'places': [
        {
            'id': 'ChIJabc',
            'displayName': {'text': 'Copper Kettle Cafe'},
            'formattedAddress': 'Rua do Ouro 1, Lisbon',
            'internationalPhoneNumber': '+351 21 000 0000',
            'websiteUri': 'https://copperkettle.example',
            'location': {'latitude': 38.71, 'longitude': -9.14},
            'primaryTypeDisplayName': {'text': 'Cafe'},
            'googleMapsUri': 'https://maps.google.com/?cid=123',
            'regularOpeningHours': {'weekdayDescriptions': ['Monday: 8 AM–6 PM']},
        },
        {'displayName': {'text': ''}},  # unnamed -> dropped
    ]
}


class PlacesProviderTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop('GOOGLE_PLACES_API_KEY', None)

    def tearDown(self):
        if self._old is not None:
            os.environ['GOOGLE_PLACES_API_KEY'] = self._old
        else:
            os.environ.pop('GOOGLE_PLACES_API_KEY', None)

    def test_unavailable_without_key(self):
        self.assertFalse(places_provider.available())
        rows, reason = places_provider.discover_places('Lisbon', 'Cafe')
        self.assertEqual(rows, [])
        self.assertIn('not configured', reason)

    def test_available_with_key(self):
        os.environ['GOOGLE_PLACES_API_KEY'] = 'test-key'
        self.assertTrue(places_provider.available())

    def test_rows_are_mapped_and_unnamed_dropped(self):
        os.environ['GOOGLE_PLACES_API_KEY'] = 'test-key'
        with patch('web.places_provider.requests.post', return_value=_Resp(200, SAMPLE)) as post:
            rows, reason = places_provider.discover_places('Lisbon', 'Cafe', limit=20)
        self.assertEqual(reason, '')
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['name'], 'Copper Kettle Cafe')
        self.assertEqual(row['source'], 'Google Maps')
        self.assertEqual(row['source_key'], 'google:ChIJabc')
        self.assertEqual(row['website'], 'https://copperkettle.example')
        self.assertEqual(row['phone'], '+351 21 000 0000')
        self.assertEqual(row['latitude'], 38.71)
        self.assertIn('Monday', row['opening_hours'])
        self.assertEqual(row['email'], '')  # never invented
        # The request carried the key and a bounded result count.
        _, kwargs = post.call_args
        self.assertEqual(kwargs['headers']['X-Goog-Api-Key'], 'test-key')
        self.assertEqual(kwargs['json']['maxResultCount'], 20)
        self.assertIn('Cafe in Lisbon', kwargs['json']['textQuery'])

    def test_result_count_is_capped_at_twenty(self):
        os.environ['GOOGLE_PLACES_API_KEY'] = 'test-key'
        with patch('web.places_provider.requests.post', return_value=_Resp(200, {'places': []})) as post:
            places_provider.discover_places('Lisbon', 'Cafe', limit=999)
        self.assertEqual(post.call_args.kwargs['json']['maxResultCount'], 20)

    def test_bad_key_is_reported_not_raised(self):
        os.environ['GOOGLE_PLACES_API_KEY'] = 'bad'
        with patch('web.places_provider.requests.post', return_value=_Resp(403, {})):
            rows, reason = places_provider.discover_places('Lisbon', 'Cafe')
        self.assertEqual(rows, [])
        self.assertIn('403', reason)

    def test_rate_limit_is_reported(self):
        os.environ['GOOGLE_PLACES_API_KEY'] = 'k'
        with patch('web.places_provider.requests.post', return_value=_Resp(429, {})):
            rows, reason = places_provider.discover_places('Lisbon', 'Cafe')
        self.assertEqual(rows, [])
        self.assertIn('429', reason)

    def test_network_error_is_reported(self):
        os.environ['GOOGLE_PLACES_API_KEY'] = 'k'
        import requests
        with patch('web.places_provider.requests.post', side_effect=requests.RequestException('boom')):
            rows, reason = places_provider.discover_places('Lisbon', 'Cafe')
        self.assertEqual(rows, [])
        self.assertIn('failed', reason)

    def test_merge_dedupes_and_fills_empty_fields(self):
        osm = [{'name': 'Copper Kettle Cafe', 'city': 'Lisbon', 'phone': '', 'website': 'https://osm.example',
                'source': 'OpenStreetMap'}]
        google = [{'name': 'Copper Kettle Cafe', 'city': 'Lisbon', 'phone': '+351 21 000 0000', 'website': '',
                   'source': 'Google Maps'}]
        merged = places_provider.merge_rows(osm, google)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['source'], 'OpenStreetMap')  # earlier source wins
        self.assertEqual(merged[0]['phone'], '+351 21 000 0000')  # empty field filled
        self.assertEqual(merged[0]['website'], 'https://osm.example')

    def test_merge_keeps_distinct_businesses(self):
        a = [{'name': 'A', 'city': 'Lisbon'}]
        b = [{'name': 'B', 'city': 'Lisbon'}]
        self.assertEqual(len(places_provider.merge_rows(a, b)), 2)


class _Ctx:
    """Minimal Scout context: records receipts, ignores everything else."""
    def __init__(self):
        self.receipts = []

    def receipt(self, kind, message, **kw):
        self.receipts.append((kind, message))


class ScoutSourceTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop('GOOGLE_PLACES_API_KEY', None)

    def tearDown(self):
        if self._old is not None:
            os.environ['GOOGLE_PLACES_API_KEY'] = self._old
        else:
            os.environ.pop('GOOGLE_PLACES_API_KEY', None)

    def test_osm_only_when_no_google_key(self):
        from agents import agent_scout
        osm = [{'name': 'OSM Cafe', 'city': 'Lisbon', 'source': 'OpenStreetMap'}]
        with patch('web.services.discover_location', return_value=(osm, 'Lisbon')), \
             patch('web.places_provider.discover_places') as g:
            rows, _ = agent_scout.discover_from_sources('Lisbon', 'Cafe', 8, _Ctx())
        self.assertEqual(len(rows), 1)
        g.assert_not_called()

    def test_google_merges_when_key_present(self):
        os.environ['GOOGLE_PLACES_API_KEY'] = 'k'
        from agents import agent_scout
        osm = [{'name': 'OSM Cafe', 'city': 'Lisbon', 'source': 'OpenStreetMap', 'phone': ''}]
        google = [{'name': 'OSM Cafe', 'city': 'Lisbon', 'source': 'Google Maps', 'phone': '+351 1'},
                  {'name': 'Google Only Cafe', 'city': 'Lisbon', 'source': 'Google Maps'}]
        with patch('web.services.discover_location', return_value=(osm, 'Lisbon')), \
             patch('web.places_provider.discover_places', return_value=(google, '')):
            rows, _ = agent_scout.discover_from_sources('Lisbon', 'Cafe', 8, _Ctx())
        names = sorted(r['name'] for r in rows)
        self.assertEqual(names, ['Google Only Cafe', 'OSM Cafe'])
        merged = next(r for r in rows if r['name'] == 'OSM Cafe')
        self.assertEqual(merged['phone'], '+351 1')  # filled from Google


if __name__ == '__main__':
    unittest.main()
