"""Regression coverage for cross-workspace outreach enrollment."""
import unittest
from unittest.mock import patch, MagicMock

from tests.test_app import ProspectTests, module


class OutreachTenantIsolationTests(unittest.TestCase):
    def setUp(self):
        ProspectTests.setUp(self)
        with module.db() as c:
            for cid, email in (("client-a", "a@example.test"), ("client-b", "b@example.test")):
                c.execute(
                    "INSERT OR REPLACE INTO users(id,email,password_hash,name,role,is_active,created,updated,tier,tier_expires) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (cid, email, "x", cid, "client", 1, module.now(), module.now(), "pro", "9999-12-31T23:59:59+00:00"),
                )
            for lid, owner, email in (
                ("lead-a", "client-a", "a-lead@example.test"),
                ("lead-b", "client-b", "b-lead@example.test"),
            ):
                c.execute(
                    "INSERT OR REPLACE INTO leads(id,source_key,name,email,stage,token,created,updated,owner_user_id) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (lid, "source-" + lid, lid.title(), email, "New", "token-" + lid,
                     module.now(), module.now(), owner),
                )
            c.execute(
                "INSERT OR REPLACE INTO outreach_campaigns "
                "(id,owner_user_id,name,provider,provider_campaign_id,status,stop_on_reply,stop_on_unsubscribe,created,updated) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("campaign-a", "client-a", "A campaign", "instantly", "remote-a", "draft", 1, 1,
                 module.now(), module.now()),
            )
        with self.client.session_transaction() as s:
            s.clear()
            s["client_id"] = "client-a"
            s["role"] = "client"
            s["tier"] = "pro"
            s["csrf"] = "test-csrf"

    def tearDown(self):
        ProspectTests.tearDown(self)

    def test_reply_webhook_updates_only_the_campaign_enrolled_lead(self):
        with module.db() as c:
            c.execute("UPDATE leads SET email=? WHERE id='lead-b'", ("a-lead@example.test",))
            c.execute(
                "INSERT INTO outreach_enrollments(id,campaign_id,lead_id,status,created,updated) "
                "VALUES(?,?,?,?,?,?)",
                ("enroll-a", "campaign-a", "lead-a", "queued", module.now(), module.now()),
            )

        with patch.dict("os.environ", {"APP_ENV": "test", "INSTANTLY_WEBHOOK_SECRET": "test-webhook-secret"}):
            response = self.client.post(
                "/api/webhooks/instantly",
                json={"event_id": "reply-event-1", "event_type": "reply",
                      "campaign_id": "remote-a", "email": "a-lead@example.test",
                      "text": "Could you send details?"},
                headers={"X-CSRF-Token": "test-csrf", "X-Reachmark-Webhook-Secret": "test-webhook-secret"},
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        with module.db() as c:
            stages = {r["id"]: r["stage"] for r in c.execute(
                "SELECT id,stage FROM leads WHERE id IN ('lead-a','lead-b')"
            )}
            enrollment = c.execute(
                "SELECT status FROM outreach_enrollments WHERE id='enroll-a'"
            ).fetchone()
        self.assertEqual(stages["lead-a"], "Replied")
        self.assertEqual(stages["lead-b"], "New")
        self.assertEqual(enrollment["status"], "replied")

    def test_client_cannot_enroll_another_clients_lead(self):
        provider = MagicMock()
        with patch("web.outreach.provider_for", return_value=provider):
            response = self.client.post(
                "/api/outreach/campaigns/campaign-a/leads",
                json={"lead_ids": ["lead-a", "lead-b"]},
                headers={"X-CSRF-Token": "test-csrf"},
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["added"], 1)
        self.assertEqual(response.get_json()["skipped"], 0)
        provider.add_leads.assert_called_once()
        sent_leads = provider.add_leads.call_args.args[1]
        self.assertEqual([lead["email"] for lead in sent_leads], ["a-lead@example.test"])

        with module.db() as c:
            enrolled = {r["lead_id"] for r in c.execute(
                "SELECT lead_id FROM outreach_enrollments WHERE campaign_id='campaign-a'"
            )}
        self.assertEqual(enrolled, {"lead-a"})


    def test_repeated_enrollment_does_not_resend_existing_lead(self):
        with module.db() as c:
            c.execute(
                "INSERT INTO outreach_enrollments(id,campaign_id,lead_id,status,created,updated) "
                "VALUES(?,?,?,?,?,?)",
                ("enroll-existing", "campaign-a", "lead-a", "queued", module.now(), module.now()),
            )
        provider = MagicMock()
        with patch("web.outreach.provider_for", return_value=provider):
            response = self.client.post(
                "/api/outreach/campaigns/campaign-a/leads",
                json={"lead_ids": ["lead-a"]},
                headers={"X-CSRF-Token": "test-csrf"},
            )
        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
        provider.add_leads.assert_not_called()

    def test_unsubscribe_suppresses_email_and_updates_existing_enrollments(self):
        with module.db() as c:
            c.execute(
                "INSERT INTO outreach_enrollments(id,campaign_id,lead_id,status,created,updated) "
                "VALUES(?,?,?,?,?,?)",
                ("enroll-unsub", "campaign-a", "lead-a", "queued", module.now(), module.now()),
            )
        with patch.dict("os.environ", {"APP_ENV": "test", "INSTANTLY_WEBHOOK_SECRET": "test-webhook-secret"}):
            response = self.client.post(
                "/api/webhooks/instantly",
                json={"event_id": "unsubscribe-event-1", "event_type": "unsubscribe",
                      "campaign_id": "remote-a", "email": "a-lead@example.test"},
                headers={"X-Reachmark-Webhook-Secret": "test-webhook-secret"},
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        with module.db() as c:
            suppression = c.execute(
                "SELECT 1 FROM suppression WHERE lower(email)=?",
                ("a-lead@example.test",),
            ).fetchone()
            enrollment = c.execute(
                "SELECT status FROM outreach_enrollments WHERE id='enroll-unsub'"
            ).fetchone()
        self.assertIsNotNone(suppression)
        self.assertEqual(enrollment["status"], "unsubscribed")


    def test_webhook_rejects_requests_when_secret_is_not_configured(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("INSTANTLY_WEBHOOK_SECRET", None)
            response = self.client.post(
                "/api/webhooks/instantly",
                json={"event_id": "unauthenticated-event", "event_type": "reply",
                      "campaign_id": "remote-a", "email": "a-lead@example.test"},
            )
        self.assertEqual(response.status_code, 401)

    def test_suppressed_contact_is_never_sent_to_provider(self):
        with module.db() as c:
            c.execute("INSERT OR IGNORE INTO suppression(email,created) VALUES(?,?)",
                      ("a-lead@example.test", module.now()))

        provider = MagicMock()
        with patch("web.outreach.provider_for", return_value=provider):
            response = self.client.post(
                "/api/outreach/campaigns/campaign-a/leads",
                json={"lead_ids": ["lead-a"]},
                headers={"X-CSRF-Token": "test-csrf"},
            )

        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
        provider.add_leads.assert_not_called()
        with module.db() as c:
            count = c.execute(
                "SELECT count(*) FROM outreach_enrollments WHERE campaign_id='campaign-a' AND lead_id='lead-a'"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_provider_transport_errors_do_not_echo_api_keys(self):
        import requests
        from web.outreach import ProviderError, SmartleadProvider

        secret = "smartlead-secret-value"
        with patch("web.outreach.requests.request",
                   side_effect=requests.ConnectionError(f"request failed with api_key={secret}")):
            with self.assertRaises(ProviderError) as caught:
                SmartleadProvider(secret)._request("GET", "/campaigns")

        self.assertNotIn(secret, str(caught.exception))
        self.assertIn("ConnectionError", str(caught.exception))

    def test_provider_http_errors_do_not_echo_response_body(self):
        from types import SimpleNamespace
        from web.outreach import ProviderError, SmartleadProvider

        secret = "smartlead-secret-value"
        fake_response = SimpleNamespace(status_code=403, content=b"api_key=" + secret.encode(),
                                        text="api_key=" + secret)
        with patch("web.outreach.requests.request", return_value=fake_response):
            with self.assertRaises(ProviderError) as caught:
                SmartleadProvider(secret)._request("GET", "/campaigns")

        self.assertNotIn(secret, str(caught.exception))
        self.assertIn("HTTP 403", str(caught.exception))


    def test_ambiguous_provider_failure_keeps_reservation_and_prevents_duplicate_retry(self):
        from web.outreach import ProviderError

        provider = MagicMock()
        provider.add_leads.side_effect = ProviderError("Instantly request failed (Timeout).")
        with patch("web.outreach.provider_for", return_value=provider):
            first = self.client.post(
                "/api/outreach/campaigns/campaign-a/leads",
                json={"lead_ids": ["lead-a"]},
                headers={"X-CSRF-Token": "test-csrf"},
            )
            self.assertEqual(first.status_code, 502, first.get_data(as_text=True))
            self.assertTrue(first.get_json()["reconciliation_required"])

            # A second request must not resend the same lead while the first
            # provider result is ambiguous.
            second = self.client.post(
                "/api/outreach/campaigns/campaign-a/leads",
                json={"lead_ids": ["lead-a"]},
                headers={"X-CSRF-Token": "test-csrf"},
            )

        self.assertEqual(second.status_code, 400, second.get_data(as_text=True))
        provider.add_leads.assert_called_once()
        with module.db() as c:
            row = c.execute(
                "SELECT status FROM outreach_enrollments WHERE campaign_id='campaign-a' AND lead_id='lead-a'"
            ).fetchone()
        self.assertEqual(row["status"], "needs_reconciliation")


if __name__ == "__main__":
    unittest.main()
