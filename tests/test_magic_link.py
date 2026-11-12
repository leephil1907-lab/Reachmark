"""Passwordless sign-in regression tests. Uses an isolated SQLite database and mocks email delivery."""
import os
import tempfile
import unittest
from unittest.mock import patch

_bootstrap = tempfile.TemporaryDirectory()
_original_path = os.environ.get("DATABASE_PATH")
os.environ["DATABASE_PATH"] = os.path.join(_bootstrap.name, "bootstrap.sqlite3")
import web.app as module
if _original_path is None:
    os.environ.pop("DATABASE_PATH", None)
else:
    os.environ["DATABASE_PATH"] = _original_path


class MagicLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = module.DB
        with module.db() as c:
            schema = [
                r[0] for r in c.execute(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='table' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
                )
            ]
        module.DB = os.path.join(self.tmp.name, "isolated.sqlite3")
        with module.db() as c:
            for sql in schema:
                c.execute(sql)
        self.client = module.app.test_client()
        self.mail = patch("web.accounts.send_branded", return_value=(True, "test-outbox"))
        self.send = self.mail.start()

    def tearDown(self):
        self.mail.stop()
        module.DB = self.old_db
        self.tmp.cleanup()

    def add_user(self, email="person@example.test"):
        from werkzeug.security import generate_password_hash
        stamp = module.now()
        with module.db() as c:
            c.execute(
                "INSERT INTO users(id,email,name,password_hash,role,created,updated,is_active,email_verified) "
                "VALUES(?,?,?,?,?,?,?,1,1)",
                ("test-user", email, "Test User", generate_password_hash("not-a-production-password"),
                 "client", stamp, stamp),
            )

    def test_invalid_email_is_rejected_without_email(self):
        response = self.client.post("/api/auth/magic-link", json={"email": "not-an-email"})
        self.assertEqual(response.status_code, 400)
        self.send.assert_not_called()

    def test_unknown_and_known_addresses_have_same_safe_response(self):
        unknown = self.client.post("/api/auth/magic-link", json={"email": "unknown@example.test"})
        self.add_user()
        known = self.client.post("/api/auth/magic-link", json={"email": "person@example.test"})
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.json["message"], known.json["message"])
        self.assertEqual(self.send.call_count, 1)

    def test_link_requires_confirmation_and_is_single_use(self):
        self.add_user()
        self.client.post("/api/auth/magic-link", json={"email": "person@example.test"})
        link = self.send.call_args.kwargs["cta_url"]
        token = link.rsplit("/", 1)[-1]
        page = self.client.get("/magic-link/" + token)
        self.assertEqual(page.status_code, 200)
        import re
        csrf = re.search(r'name="csrf" value="([^"]+)"', page.get_data(as_text=True)).group(1)
        confirmed = self.client.post("/magic-link/" + token, data={"csrf": csrf})
        self.assertEqual(confirmed.status_code, 302)
        self.assertEqual(confirmed.headers["Location"], "/dashboard")
        again = self.client.get("/magic-link/" + token)
        self.assertEqual(again.status_code, 400)

    def test_magic_link_request_is_rate_limited(self):
        for _ in range(5):
            response = self.client.post("/api/auth/magic-link", json={"email": "unknown@example.test"})
            self.assertEqual(response.status_code, 200)
        limited = self.client.post("/api/auth/magic-link", json={"email": "unknown@example.test"})
        self.assertEqual(limited.status_code, 429)


if __name__ == "__main__":
    unittest.main()
