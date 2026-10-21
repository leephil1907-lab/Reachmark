"""Smoke tests for the focused HVAC agency landing page."""
import unittest
import tests.test_app as _appmod
from tests.test_app import module


class HvacGrowthPageTests(unittest.TestCase):
    def setUp(self):
        _appmod.ProspectTests.setUp(self)

    def tearDown(self):
        _appmod.ProspectTests.tearDown(self)

    def test_hvac_growth_page_and_offer_are_public(self):
        response = self.client.get("/hvac-growth")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("More qualified service enquiries", body)
        self.assertIn("$3,000", body)
        self.assertIn("$5,000", body)
        self.assertIn("$7,500", body)
        self.assertIn("Ad spend stays in your account", body)
        self.assertIn("No guaranteed rankings or job counts", body)
        self.assertIn('rel="canonical"', body)

    def test_hvac_growth_form_uses_existing_enquiry_endpoint(self):
        response = self.client.get("/hvac-growth")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("fetch('/api/enquiries'", body)
        self.assertIn("Request assessment", body)
        self.assertIn("g-consent", body)
        self.assertIn("company_url", body)
