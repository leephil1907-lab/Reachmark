import unittest
from tests.test_app import module


class BrowserbaseAccessTests(unittest.TestCase):
    def test_run_history_requires_owner_session(self):
        client = module.app.test_client()
        response = client.get("/api/owner/browserbase/runs")
        self.assertEqual(response.status_code, 403)

    def test_owner_dashboard_contains_agent_panel(self):
        client = module.app.test_client()
        with client.session_transaction() as session:
            session["owner"] = True
        response = client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Website Opportunity Report", response.data)


if __name__ == "__main__":
    unittest.main()
