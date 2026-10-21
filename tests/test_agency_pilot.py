"""Agency pilot public page smoke tests."""
import unittest
import tests.test_app as _appmod
from tests.test_app import module


class AgencyPilotPageTests(unittest.TestCase):
    def setUp(self):
        _appmod.ProspectTests.setUp(self)

    def tearDown(self):
        _appmod.ProspectTests.tearDown(self)

    def test_pilot_page_is_public_and_explains_bounded_offer(self):
        response = self.client.get("/agency-pilot")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Find your next web project", body)
        self.assertIn("$299", body)
        self.assertIn("up to 25 candidate businesses", body)
        self.assertIn("up to 5 evidence-backed opportunity reports", body)
        self.assertIn("No automatic sending", body)
        self.assertIn('rel="canonical"', body)

    def test_pilot_page_uses_configured_canonical_domain(self):
        from unittest.mock import patch
        with patch.object(module, "settings", return_value={"public_base_url": "https://reachmarkdigital.xyz/"}):
            response = self.client.get("/agency-pilot")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="https://reachmarkdigital.xyz/agency-pilot"', response.get_data(as_text=True))
