import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import Flask

from web.video_studio import register_video_studio


class VideoStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "video-studio.sqlite3")

        @contextmanager
        def db():
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

        self.db = db
        self.app = Flask(__name__)
        self.app.secret_key = "test-only"
        self.app.config.update(TESTING=True)
        register_video_studio(self.app, self.db, lambda: datetime.now(timezone.utc).isoformat())
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["owner"] = True
        os.environ.pop("VIDEO_STUDIO_WORKER_URL", None)

    def tearDown(self):
        self.temp.cleanup()

    def test_capabilities_reports_worker_not_configured(self):
        response = self.client.get("/api/studio/capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "worker_not_configured")
        self.assertFalse(response.json["features"]["rendering"])

    def test_project_create_list_update_delete(self):
        created = self.client.post("/api/studio/projects", json={
            "title": "Launch film", "brief": "A premium product reveal in soft light",
            "aspect_ratio": "16:9", "duration": 30, "style": "cinematic"
        })
        self.assertEqual(created.status_code, 201)
        pid = created.json["project"]["id"]
        self.assertEqual(self.client.get("/api/studio/projects").json["projects"][0]["id"], pid)
        updated = self.client.patch(f"/api/studio/projects/{pid}", json={"title": "Launch film v2"})
        self.assertEqual(updated.status_code, 200)
        detail = self.client.get(f"/api/studio/projects/{pid}")
        self.assertEqual(detail.json["project"]["title"], "Launch film v2")
        self.assertEqual(self.client.delete(f"/api/studio/projects/{pid}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/studio/projects/{pid}").status_code, 404)

    def test_rejects_invalid_aspect_ratio(self):
        response = self.client.post("/api/studio/projects", json={
            "title": "Bad format", "brief": "An actual brief for testing",
            "aspect_ratio": "2:7", "duration": 30, "style": "cinematic"
        })
        self.assertEqual(response.status_code, 400)

    def test_generation_does_not_fake_a_render_without_worker(self):
        created = self.client.post("/api/studio/projects", json={
            "title": "Real film", "brief": "Create a cinematic launch sequence",
            "aspect_ratio": "9:16", "duration": 30, "style": "cinematic"
        })
        pid = created.json["project"]["id"]
        response = self.client.post(f"/api/studio/projects/{pid}/generate",
                                    json={"provider": "ltx2", "prompt": "Cinematic product launch"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("VIDEO_STUDIO_WORKER_URL", response.json["error"])


if __name__ == "__main__":
    unittest.main()
