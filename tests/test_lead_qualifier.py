"""Regression tests for authenticated, owner-scoped lead qualification."""
import unittest
from tests.test_app import ProspectTests, module


class LeadQualifierTests(unittest.TestCase):
    setUp = ProspectTests.setUp
    tearDown = ProspectTests.tearDown
    def _as_owner(self):
        with self.client.session_transaction() as session:
            session["owner"] = True

    def _payload(self, **overrides):
        data = {
            "name": "Jordan Lee",
            "company": "Northstar Dental",
            "email": "jordan@northstar.example",
            "phone": "+1 555 0100",
            "website": "https://northstar.example",
            "industry": "Dental",
            "pain_point": "The website does not generate appointment enquiries.",
            "goal": "Increase qualified appointment bookings.",
            "budget": "$2,000-$4,000",
            "timeline": "Within 30 days",
            "authority": "decision_maker",
            "preferred_next_step": "book a call",
        }
        data.update(overrides)
        return data

    def test_capture_requires_an_authenticated_owner(self):
        response = self.client.post("/api/qualifier/leads", json=self._payload())
        self.assertEqual(response.status_code, 401)

    def test_capture_persists_lead_score_and_audit_event(self):
        self._as_owner()
        response = self.client.post("/api/qualifier/leads", json=self._payload())
        self.assertEqual(response.status_code, 201, response.get_json())
        result = response.get_json()
        self.assertTrue(result["ok"])
        self.assertEqual(result["qualification"]["tier"], "A")
        with module_db() as c:
            row = c.execute(
                "SELECT company,total_score,tier FROM lead_qualifications WHERE lead_id=?",
                (result["lead_id"],),
            ).fetchone()
            event = c.execute(
                "SELECT event_type FROM lead_qualification_events WHERE lead_id=?",
                (result["lead_id"],),
            ).fetchone()
        self.assertEqual(row["company"], "Northstar Dental")
        self.assertEqual(row["tier"], "A")
        self.assertEqual(event["event_type"], "qualified")

    def test_duplicate_email_does_not_create_a_second_lead(self):
        self._as_owner()
        first = self.client.post("/api/qualifier/leads", json=self._payload())
        self.assertEqual(first.status_code, 201, first.get_json())
        second = self.client.post("/api/qualifier/leads", json=self._payload(name="Jordan L."))
        self.assertEqual(second.status_code, 200, second.get_json())
        self.assertTrue(second.get_json()["duplicate"])
        with module_db() as c:
            count = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        self.assertEqual(count, 1)

    def test_invalid_email_is_rejected_before_persistence(self):
        self._as_owner()
        response = self.client.post("/api/qualifier/leads", json=self._payload(email="not-an-email"))
        self.assertEqual(response.status_code, 400)
        with module_db() as c:
            count = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        self.assertEqual(count, 0)

    def test_list_and_detail_are_owner_scoped(self):
        self._as_owner()
        created = self.client.post("/api/qualifier/leads", json=self._payload())
        lead_id = created.get_json()["lead_id"]
        self.assertEqual(self.client.get("/api/qualifier/leads").status_code, 200)
        self.assertEqual(self.client.get(f"/api/qualifier/leads/{lead_id}").status_code, 200)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get("/api/qualifier/leads").status_code, 401)
        self.assertEqual(self.client.get(f"/api/qualifier/leads/{lead_id}").status_code, 401)

    def test_conversation_updates_qualification_and_is_recorded(self):
        self._as_owner()
        created = self.client.post("/api/qualifier/leads", json=self._payload(pain_point="", goal=""))
        self.assertEqual(created.status_code, 201, created.get_json())
        lead_id = created.get_json()["lead_id"]
        response = self.client.post(
            f"/api/qualifier/leads/{lead_id}/message",
            json={"message": "We need more website leads and customer bookings."},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        detail = self.client.get(f"/api/qualifier/leads/{lead_id}").get_json()["lead"]
        self.assertTrue(detail["conversation"])
        self.assertTrue(any(x["role"] == "user" for x in detail["conversation"]))
        self.assertTrue(any(x["role"] == "agent" for x in detail["conversation"]))


def module_db():
    return module.db()
