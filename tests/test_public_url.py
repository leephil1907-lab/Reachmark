"""Owned domain wins over Railway hostnames for canonical URLs."""
import os
import unittest
from unittest.mock import patch

from web.public_url import BRAND_PUBLIC_URL, google_site_tokens, is_ephemeral_public_url, resolve_public_base_url


class PublicUrlTests(unittest.TestCase):
    def test_brand_constant(self):
        self.assertEqual(BRAND_PUBLIC_URL, 'https://reachmarkdigital.xyz')

    def test_search_console_token_for_owned_domain(self):
        tokens = google_site_tokens()
        self.assertIn('zVYthfXOcAda_Sxphe3f8dYmVrRZ66cogYgTHWeaq7c', tokens)

    def test_railway_is_ephemeral(self):
        self.assertTrue(is_ephemeral_public_url('https://reachmark-production.up.railway.app'))
        self.assertTrue(is_ephemeral_public_url('https://localhost:8000'))
        self.assertFalse(is_ephemeral_public_url('https://reachmarkdigital.xyz'))
        self.assertFalse(is_ephemeral_public_url('https://example.test'))

    def test_resolve_skips_railway_env(self):
        with patch.dict(os.environ, {'PUBLIC_BASE_URL': 'https://reachmark-production.up.railway.app'}):
            self.assertEqual(resolve_public_base_url(), BRAND_PUBLIC_URL)
            self.assertEqual(resolve_public_base_url('https://studio.example'), 'https://studio.example')

    def test_resolve_keeps_explicit_https_host(self):
        with patch.dict(os.environ, {'PUBLIC_BASE_URL': 'https://env.test'}):
            self.assertEqual(resolve_public_base_url('https://settings.test'), 'https://env.test')

    def test_resolve_default_is_brand(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('PUBLIC_BASE_URL', None)
            self.assertEqual(resolve_public_base_url(''), BRAND_PUBLIC_URL)
            self.assertEqual(resolve_public_base_url('http://insecure.example'), BRAND_PUBLIC_URL)


if __name__ == '__main__':
    unittest.main()
