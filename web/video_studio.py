"""Reachmark Studio video production workspace.

The web process owns projects and job metadata. Heavy diffusion inference runs on a
separate GPU worker; no model is falsely reported as available when it is not configured.
"""
import json
import os
import re
import uuid
from urllib.parse import urlparse

import requests
from flask import abort, jsonify, redirect, render_template, request, session


def register_video_studio(app, db, now):
    def studio_user():
        if session.get("owner"):
            return "owner"
        if session.get("client_id") and session.get("role") == "client":
            return str(session["client_id"])
        return None

    def require_user():
        owner = studio_user()
        if not owner:
            abort(401)
        return owner

    def ensure_tables():
        with db() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS video_projects (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, title TEXT NOT NULL,
                brief TEXT NOT NULL DEFAULT '', aspect_ratio TEXT NOT NULL DEFAULT '9:16',
                style TEXT NOT NULL DEFAULT 'cinematic', duration INTEGER NOT NULL DEFAULT 30,
                status TEXT NOT NULL DEFAULT 'draft', created TEXT NOT NULL, updated TEXT NOT NULL
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS video_jobs (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                provider TEXT NOT NULL, status TEXT NOT NULL, prompt TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}', output_url TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL
            )""")
    ensure_tables()

    @app.route("/studio")
    def video_studio_home():
        if not studio_user():
            return redirect("/signin?next=/studio")
        return render_template("video_studio.html")

    @app.route("/api/studio/capabilities")
    def video_studio_capabilities():
        require_user()
        worker = os.getenv("VIDEO_STUDIO_WORKER_URL", "").strip().rstrip("/")
        return jsonify(
            status="ready" if worker else "worker_not_configured",
            renderer="HyperFrames",
            providers=[
                {"id": "wangp", "label": "Wan2GP", "configured": bool(worker)},
                {"id": "ltx2", "label": "LTX-2", "configured": bool(worker)},
                {"id": "hunyuan", "label": "HunyuanVideo", "configured": bool(worker)},
                {"id": "opensora", "label": "Open-Sora", "configured": bool(worker)},
            ],
            features={"projects": True, "job_history": True, "rendering": bool(worker),
                      "message": "GPU worker connected" if worker else
                      "Workspace is ready. Connect VIDEO_STUDIO_WORKER_URL to a GPU worker to enable AI generation."}
        )

    @app.route("/api/studio/projects", methods=["GET", "POST"])
    def video_studio_projects():
        owner = require_user()
        if request.method == "GET":
            with db() as c:
                rows = c.execute(
                    "SELECT * FROM video_projects WHERE owner_id=? ORDER BY updated DESC LIMIT 100",
                    (owner,)
                ).fetchall()
            return jsonify(projects=[dict(r) for r in rows])
        data = request.get_json(silent=True) or {}
        title = str(data.get("title") or "Untitled film").strip()[:120]
        brief = str(data.get("brief") or "").strip()[:8000]
        ratio = str(data.get("aspect_ratio") or "9:16")
        style = str(data.get("style") or "cinematic")
        duration = data.get("duration", 30)
        if ratio not in ("9:16", "16:9", "1:1", "4:5"):
            return jsonify(error="Unsupported aspect ratio."), 400
        if style not in ("cinematic", "editorial", "product", "surreal", "documentary", "motion"):
            return jsonify(error="Unsupported visual direction."), 400
        if not isinstance(duration, int) or duration not in (15, 30, 45, 60, 90):
            return jsonify(error="Choose a supported duration."), 400
        pid = uuid.uuid4().hex
        stamp = now()
        with db() as c:
            c.execute("INSERT INTO video_projects VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (pid, owner, title, brief, ratio, style, duration, "draft", stamp, stamp))
        return jsonify(project={"id": pid, "owner_id": owner, "title": title, "brief": brief,
                                "aspect_ratio": ratio, "style": style, "duration": duration,
                                "status": "draft", "created": stamp, "updated": stamp}), 201

    @app.route("/api/studio/projects/<pid>", methods=["GET", "PATCH", "DELETE"])
    def video_studio_project(pid):
        owner = require_user()
        with db() as c:
            row = c.execute("SELECT * FROM video_projects WHERE id=? AND owner_id=?", (pid, owner)).fetchone()
        if not row:
            abort(404)
        if request.method == "GET":
            with db() as c:
                jobs = c.execute("SELECT * FROM video_jobs WHERE project_id=? AND owner_id=? ORDER BY created DESC",
                                 (pid, owner)).fetchall()
            return jsonify(project=dict(row), jobs=[dict(j) for j in jobs])
        if request.method == "DELETE":
            with db() as c:
                c.execute("DELETE FROM video_jobs WHERE project_id=? AND owner_id=?", (pid, owner))
                c.execute("DELETE FROM video_projects WHERE id=? AND owner_id=?", (pid, owner))
            return jsonify(ok=True)
        data = request.get_json(silent=True) or {}
        allowed = {"title": 120, "brief": 8000}
        changes = {k: str(data[k]).strip()[:limit] for k, limit in allowed.items() if k in data}
        if "aspect_ratio" in data and data["aspect_ratio"] in ("9:16", "16:9", "1:1", "4:5"):
            changes["aspect_ratio"] = data["aspect_ratio"]
        if "style" in data and data["style"] in ("cinematic", "editorial", "product", "surreal", "documentary", "motion"):
            changes["style"] = data["style"]
        if "duration" in data and isinstance(data["duration"], int) and data["duration"] in (15,30,45,60,90):
            changes["duration"] = data["duration"]
        changes["updated"] = now()
        if changes:
            sql = ", ".join(k + "=?" for k in changes)
            with db() as c:
                c.execute("UPDATE video_projects SET " + sql + " WHERE id=? AND owner_id=?",
                          (*changes.values(), pid, owner))
        return jsonify(ok=True)

    @app.route("/api/studio/projects/<pid>/generate", methods=["POST"])
    def video_studio_generate(pid):
        owner = require_user()
        worker = os.getenv("VIDEO_STUDIO_WORKER_URL", "").strip().rstrip("/")
        with db() as c:
            row = c.execute("SELECT * FROM video_projects WHERE id=? AND owner_id=?", (pid, owner)).fetchone()
        if not row:
            abort(404)
        if not worker:
            return jsonify(error="AI generation is not connected yet. Configure VIDEO_STUDIO_WORKER_URL for the GPU worker; no fake render was created."), 503
        data = request.get_json(silent=True) or {}
        provider = str(data.get("provider") or "ltx2")
        if provider not in ("wangp", "ltx2", "hunyuan", "opensora"):
            return jsonify(error="Unsupported generation provider."), 400
        prompt = str(data.get("prompt") or row["brief"]).strip()[:8000]
        if len(prompt) < 8:
            return jsonify(error="Add a creative brief or prompt before generating."), 400
        jid = uuid.uuid4().hex
        stamp = now()
        payload = {"project_id": pid, "provider": provider, "prompt": prompt,
                   "aspect_ratio": row["aspect_ratio"], "style": row["style"],
                   "duration": row["duration"], "callback_path": "/api/studio/jobs/" + jid}
        with db() as c:
            c.execute("INSERT INTO video_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (jid, pid, owner, provider, "queued", prompt, json.dumps(payload), "", "", stamp, stamp))
            c.execute("UPDATE video_projects SET status='queued',updated=? WHERE id=?", (stamp, pid))
        try:
            response = requests.post(worker + "/jobs", json={"id": jid, **payload}, timeout=12)
            response.raise_for_status()
            remote = response.json() if response.content else {}
            state = str(remote.get("status") or "queued")
            output = str(remote.get("output_url") or "")
            if state not in ("queued", "running", "completed", "failed"):
                state = "queued"
            with db() as c:
                c.execute("UPDATE video_jobs SET status=?,output_url=?,payload=?,updated=? WHERE id=?",
                          (state, output, json.dumps({**payload, "worker_job": remote}), now(), jid))
                c.execute("UPDATE video_projects SET status=?,updated=? WHERE id=?",
                          (state, now(), pid))
            return jsonify(job={"id": jid, "status": state, "output_url": output}), 202
        except (requests.RequestException, ValueError) as exc:
            with db() as c:
                c.execute("UPDATE video_jobs SET status='failed',error=?,updated=? WHERE id=?",
                          (type(exc).__name__, now(), jid))
                c.execute("UPDATE video_projects SET status='failed',updated=? WHERE id=?", (now(), pid))
            return jsonify(error="The GPU worker did not accept this job. Check worker health and logs."), 502

    @app.route("/api/studio/jobs/<jid>")
    def video_studio_job(jid):
        owner = require_user()
        with db() as c:
            row = c.execute("SELECT * FROM video_jobs WHERE id=? AND owner_id=?", (jid, owner)).fetchone()
        if not row:
            abort(404)
        return jsonify(job=dict(row))

