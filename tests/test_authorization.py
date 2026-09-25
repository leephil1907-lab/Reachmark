"""Authorization regression matrix for the Reachmark API surface."""
import unittest
from unittest.mock import patch
from tests.test_app import ProspectTests

class ApiAuthorizationTests(ProspectTests):
    def test_unauthenticated_private_gets_are_closed(self):
        with patch.dict('os.environ', {'DASHBOARD_PASSWORD':'ci-owner-password'}):
            for path in [
                "/api/state", "/api/analytics", "/api/export", "/api/quality",
                "/api/clients", "/api/settings", "/api/outbox", "/api/snapshots",
                "/api/projects", "/api/invoices", "/api/contracts",
                "/api/operations/readiness", "/api/verify-config", "/api/deploy-check",
            ]:
                r = self.client.get(path)
                self.assertIn(r.status_code, (401, 402), path)

    def test_unauthenticated_mutations_are_closed(self):
        cases = [
            ("/api/leads", {}),
            ("/api/jobs", {"locations":["Lagos"],"category":"Bakery"}),
            ("/api/map/scans", {"category":"Bakery","label":"Lagos","bounds":[6.5,3.3,6.54,3.34]}),
            ("/api/settings", {}),
            ("/api/snapshots", {}),
            ("/api/projects", {"title":"Unauthorized"}),
            ("/api/invoices", {"client_name":"Unauthorized"}),
        ]
        with patch.dict('os.environ', {'DASHBOARD_PASSWORD':'ci-owner-password'}):
            for path,payload in cases:
                r = self.client.post(path, json=payload)
                self.assertIn(r.status_code, (401,402), path)

    def test_intentionally_public_auth_and_marketing_endpoints_remain_public(self):
        for path in ["/api/auth/me","/api/auth/oauth","/api/billing/status","/api/client-reviews"]:
            self.assertIn(self.client.get(path).status_code, (200,401), path)
        self.assertEqual(self.client.post("/api/auth/signup", json={
            "email":"auth-matrix@example.test","password":"temporary-test-password","name":"Matrix"
        }).status_code, 201)

if __name__ == "__main__":
    unittest.main()
