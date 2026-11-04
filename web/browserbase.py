"""Owner-only Browserbase Agent runs for Website Opportunity Report.

Browserbase credentials stay server-side. Runs are persisted locally so the
owner can leave the dashboard and return to inspect or resume polling later.
"""
from __future__ import annotations

import json
import os
import uuid

import requests
from flask import jsonify, request

API_URL = "https://api.browserbase.com/v1/agents/runs"
DEFAULT_AGENT_ID = "7cf78926-5b51-496e-9c18-67863a3b6591"
TERMINAL = {"COMPLETED", "FAILED", "STOPPED", "TIMED_OUT"}


def _json_body(response):
    try:
        data = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        data = {"message": (response.text or "")[:2000]}
    return data if isinstance(data, dict) else {"data": data}


def _run_id(data):
    nested = data.get("run") if isinstance(data.get("run"), dict) else {}
    return data.get("runId") or data.get("id") or nested.get("runId") or nested.get("id")


def _status(data, fallback="QUEUED"):
    nested = data.get("run") if isinstance(data.get("run"), dict) else {}
    value = data.get("status") or nested.get("status") or fallback
    return str(value).upper()


def _result(data):
    for key in ("result", "output", "response", "data"):
        if data.get(key) is not None:
            return data[key]
    nested = data.get("run")
    if isinstance(nested, dict):
        for key in ("result", "output", "response", "data"):
            if nested.get(key) is not None:
                return nested[key]
    return None


def register_browserbase(app, db, now, log):
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS browserbase_runs(
            id TEXT PRIMARY KEY,
            browserbase_run_id TEXT NOT NULL UNIQUE,
            agent_id TEXT NOT NULL,
            task TEXT NOT NULL,
            status TEXT NOT NULL,
            result_json TEXT,
            error TEXT,
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_browserbase_runs_created ON browserbase_runs(created DESC)")

    def owner_only():
        if not app._owner_ok():
            return jsonify(error="Owner access is required."), 403
        return None

    def credentials():
        key = (os.getenv("BROWSERBASE_API_KEY") or "").strip()
        agent_id = (os.getenv("BROWSERBASE_AGENT_ID") or DEFAULT_AGENT_ID).strip()
        if not key:
            return None, None, (jsonify(error="Browserbase is not configured: BROWSERBASE_API_KEY is missing."), 503)
        if not agent_id:
            return None, None, (jsonify(error="Browserbase agent ID is missing."), 503)
        return key, agent_id, None

    def save_run(local_id, remote_id, agent_id, task, status, result=None, error=None):
        with db() as c:
            c.execute(
                """INSERT INTO browserbase_runs
                   (id,browserbase_run_id,agent_id,task,status,result_json,error,created,updated)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (local_id, remote_id, agent_id, task, status,
                 json.dumps(result, ensure_ascii=False) if result is not None else None,
                 error, now(), now()),
            )

    @app.get("/api/owner/browserbase/runs")
    def browserbase_run_history():
        denied = owner_only()
        if denied:
            return denied
        with db() as c:
            rows = c.execute(
                """SELECT id,task,status,result_json,error,created,updated
                   FROM browserbase_runs ORDER BY created DESC LIMIT 12"""
            ).fetchall()
        runs = []
        for row in rows:
            item = dict(row)
            try:
                item["result"] = json.loads(item.pop("result_json")) if item.get("result_json") else None
            except (TypeError, ValueError):
                item["result"] = None
            runs.append(item)
        return jsonify(runs=runs)

    @app.post("/api/owner/browserbase/runs")
    def browserbase_start_run():
        denied = owner_only()
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        task = str(body.get("task") or "").strip()
        if len(task) < 12:
            return jsonify(error="Describe the website report task (at least 12 characters)."), 400
        if len(task) > 4000:
            return jsonify(error="Task is too long. Keep it under 4,000 characters."), 400

        key, agent_id, problem = credentials()
        if problem:
            return problem

        with db() as c:
            active = c.execute(
                "SELECT count(*) FROM browserbase_runs WHERE status NOT IN (?,?,?,?)",
                tuple(TERMINAL),
            ).fetchone()[0]
        if int(active or 0) >= 3:
            return jsonify(error="Three Browserbase runs are already active. Wait for one to finish."), 429

        headers = {"x-bb-api-key": key, "Content-Type": "application/json"}
        try:
            response = requests.post(
                API_URL, headers=headers,
                json={"task": task, "agentId": agent_id}, timeout=(10, 45),
            )
        except requests.RequestException as exc:
            app.logger.warning("Browserbase start request failed: %s", type(exc).__name__)
            return jsonify(error="Could not reach Browserbase. Try again shortly."), 502

        data = _json_body(response)
        if not response.ok:
            app.logger.warning("Browserbase rejected a run (HTTP %s).", response.status_code)
            message = data.get("message") or data.get("error") or "Browserbase rejected the run."
            return jsonify(error=str(message)[:500]), 502
        remote_id = _run_id(data)
        if not remote_id:
            return jsonify(error="Browserbase accepted the request but did not return a run ID.", details=data), 502

        local_id = uuid.uuid4().hex
        status = _status(data)
        result = _result(data)
        save_run(local_id, str(remote_id), agent_id, task, status, result=result)
        log("agent", "Started Browserbase Website Opportunity Report run " + str(remote_id)[:80])
        return jsonify(
            id=local_id, runId=str(remote_id), status=status,
            task=task, result=result, created=now(),
        ), 201

    @app.get("/api/owner/browserbase/runs/<local_id>")
    def browserbase_get_run(local_id):
        denied = owner_only()
        if denied:
            return denied
        with db() as c:
            row = c.execute("SELECT * FROM browserbase_runs WHERE id=?", (local_id,)).fetchone()
        if not row:
            return jsonify(error="Browserbase run not found."), 404
        item = dict(row)
        if item["status"] in TERMINAL:
            try:
                result = json.loads(item["result_json"]) if item.get("result_json") else None
            except (TypeError, ValueError):
                result = None
            return jsonify(id=item["id"], runId=item["browserbase_run_id"], task=item["task"],
                           status=item["status"], result=result, error=item["error"],
                           created=item["created"], updated=item["updated"])

        key, _, problem = credentials()
        if problem:
            return problem
        headers = {"x-bb-api-key": key, "Content-Type": "application/json"}
        try:
            response = requests.get(
                API_URL + "/" + item["browserbase_run_id"],
                headers=headers, timeout=(10, 30),
            )
        except requests.RequestException as exc:
            app.logger.warning("Browserbase poll request failed: %s", type(exc).__name__)
            return jsonify(error="Could not check Browserbase run status. Try again shortly.",
                           id=item["id"], status=item["status"]), 502

        data = _json_body(response)
        if not response.ok:
            message = data.get("message") or data.get("error") or "Browserbase status request failed."
            return jsonify(error=str(message)[:500], id=item["id"], status=item["status"]), 502

        status = _status(data, fallback=item["status"])
        result = _result(data)
        error = data.get("error") or data.get("message") if status in ("FAILED", "STOPPED", "TIMED_OUT") else None
        with db() as c:
            c.execute(
                "UPDATE browserbase_runs SET status=?,result_json=?,error=?,updated=? WHERE id=?",
                (status, json.dumps(result if result is not None else data, ensure_ascii=False),
                 str(error)[:1000] if error else None, now(), local_id),
            )
        log("agent", "Browserbase Website Opportunity Report run " + item["browserbase_run_id"][:80] + " → " + status)
        return jsonify(id=local_id, runId=item["browserbase_run_id"], task=item["task"],
                       status=status, result=result if result is not None else data,
                       error=error, created=item["created"], updated=now())
