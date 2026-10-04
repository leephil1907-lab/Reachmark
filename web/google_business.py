"""Google Business Profile integration for Reachmark.

Real OAuth/API integration only. No demo or simulated Business Profile data is
created by this module. Credentials and tokens stay server-side.
"""
import base64
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
import uuid

from flask import jsonify, redirect, request, session

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
ACCOUNTS_API = "https://mybusinessaccountmanagement.googleapis.com/v1"
LOCATIONS_API = "https://mybusinessbusinessinformation.googleapis.com/v1"
REVIEWS_API = "https://mybusiness.googleapis.com/v4"
PERFORMANCE_API = "https://businessprofileperformance.googleapis.com/v1"
SCOPE = "https://www.googleapis.com/auth/business.manage"


def _configured():
    return bool(os.getenv("GOOGLE_CLIENT_ID", "").strip()
                and os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
                and os.getenv("GOOGLE_BUSINESS_TOKEN_KEY", "").strip())


def _token_key():
    raw = os.getenv("GOOGLE_BUSINESS_TOKEN_KEY", "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_BUSINESS_TOKEN_KEY is not configured")
    try:
        from cryptography.fernet import Fernet
        return Fernet(raw.encode())
    except Exception as exc:
        raise RuntimeError("GOOGLE_BUSINESS_TOKEN_KEY must be a valid Fernet key") from exc


def _seal(value):
    return _token_key().encrypt(value.encode()).decode()


def _open(value):
    return _token_key().decrypt(value.encode()).decode()


def _redirect_uri():
    # Business Profile uses a separate OAuth scope and callback even though it may reuse the same Google client ID/secret.
    override = os.environ.get("GOOGLE_BUSINESS_REDIRECT_URI", "").strip()
    if override:
        return override.rstrip("/")
    root = request.url_root.rstrip("/")
    parsed = urllib.parse.urlparse(root)
    host = (parsed.hostname or "").lower()
    local = host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")
    if root.startswith("http://") and not local:
        root = "https://" + root[len("http://"):]
    return root + "/api/google-business/oauth/callback"


def _actor():
    if session.get("role") == "client" and session.get("client_id"):
        return str(session["client_id"])
    if session.get("owner"):
        return "owner"
    return None

def _http_json(method, url, access_token=None, payload=None, params=None, timeout=20):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if access_token:
        headers["Authorization"] = "Bearer " + access_token
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", "replace")
        return json.loads(raw) if raw else {}


def _exchange(code):
    return _http_json("POST", GOOGLE_TOKEN, payload={
        "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": _redirect_uri(),
    })


def _refresh(account):
    refresh_token = _open(account["refresh_token"])
    token = _http_json("POST", GOOGLE_TOKEN, payload={
        "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    access = token.get("access_token")
    if not access:
        raise RuntimeError("Google did not return a refreshed access token")
    return access


def _access(c, actor, account_id):
    row = c.execute(
        "SELECT * FROM google_accounts WHERE id=? AND owner_user_id=?",
        (account_id, actor)).fetchone()
    if not row:
        return None, None
    try:
        access = _open(row["access_token"]) if row["access_token"] else ""
        if not access or float(row["expires_at"] or 0) <= time.time() + 60:
            access = _refresh(row)
            expires = time.time() + 3600
            c.execute(
                "UPDATE google_accounts SET access_token=?, expires_at=?, updated=? WHERE id=?",
                (_seal(access), expires, _now(), row["id"]))
        return dict(row), access
    except Exception:
        return dict(row), None


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def register_google_business(app, db, now, log):
    @app.get("/api/google-business/status")
    def google_business_status():
        actor = _actor()
        configured = _configured()
        if not actor:
            return jsonify(configured=configured, connected=False, locations=0)
        with db() as c:
            accounts = c.execute(
                "SELECT id,google_account_id,email,created,updated FROM google_accounts WHERE owner_user_id=? ORDER BY created DESC",
                (actor,)).fetchall()
            locations = c.execute(
                "SELECT COUNT(*) n FROM google_locations WHERE owner_user_id=?",
                (actor,)).fetchone()["n"]
        return jsonify(configured=configured, connected=bool(accounts),
                       accounts=[dict(x) for x in accounts], locations=locations)

    @app.get("/api/google-business/connect")
    def google_business_connect():
        if not _actor():
            return jsonify(error="Authentication required"), 401
        if not _configured():
            return jsonify(error="Google Business integration is not configured on this server"), 503
        state = secrets.token_urlsafe(32)
        session["google_business_oauth_state"] = state
        session["google_business_oauth_at"] = time.time()
        query = urllib.parse.urlencode({
            "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
            "redirect_uri": _redirect_uri(),
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        })
        return redirect(GOOGLE_AUTH + "?" + query)

    @app.get("/api/google-business/oauth/callback")
    def google_business_callback():
        expected = session.pop("google_business_oauth_state", "")
        started = session.pop("google_business_oauth_at", 0)
        if not expected or request.args.get("state") != expected or time.time() - started > 600:
            return redirect("/workspace?google_business=invalid_state")
        code = request.args.get("code", "")
        if not code:
            return redirect("/workspace?google_business=denied")
        actor = _actor()
        if not actor:
            return redirect("/signin?google_business=auth_required")
        try:
            token = _exchange(code)
            access = token.get("access_token")
            refresh = token.get("refresh_token")
            if not access:
                raise RuntimeError("Google authorization did not return an access token")
            profile = _http_json("GET", "https://openidconnect.googleapis.com/v1/userinfo", access)
            accounts = _http_json("GET", ACCOUNTS_API + "/accounts", access).get("accounts", [])
            if not accounts:
                raise RuntimeError("No Google Business Profile accounts are available to this Google user")
            expires = time.time() + int(token.get("expires_in", 3600))
            with db() as c:
                for item in accounts:
                    gid = str(item.get("name", "")).split("/")[-1]
                    if not gid:
                        continue
                    existing = c.execute(
                        "SELECT id FROM google_accounts WHERE owner_user_id=? AND google_account_id=?",
                        (actor, gid)).fetchone()
                    values = (
                        profile.get("email", ""),
                        _seal(access),
                        _seal(refresh) if refresh else None,
                        expires,
                        now(),
                    )
                    if existing:
                        if refresh:
                            c.execute(
                                "UPDATE google_accounts SET email=?,access_token=?,refresh_token=?,expires_at=?,updated=? WHERE id=?",
                                values + (existing["id"],))
                        else:
                            c.execute(
                                "UPDATE google_accounts SET email=?,access_token=?,expires_at=?,updated=? WHERE id=?",
                                (profile.get("email", ""), _seal(access), expires, now(), existing["id"]))
                    else:
                        c.execute(
                            "INSERT INTO google_accounts(id,owner_user_id,google_account_id,email,access_token,refresh_token,expires_at,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                            (uuid.uuid4().hex, actor, gid, profile.get("email", ""), _seal(access),
                             _seal(refresh) if refresh else "", expires, now(), now()))
            log("google-business", "Google Business Profile account connected")
            return redirect("/workspace?google_business=connected")
        except Exception as exc:
            log("google-business", "Google Business connection failed: %s" % exc)
            return redirect("/workspace?google_business=error")

    @app.post("/api/google-business/sync")
    def google_business_sync():
        actor = _actor()
        if not actor:
            return jsonify(error="Authentication required"), 401
        account_id = str((request.get_json(silent=True) or {}).get("account_id", "")).strip()
        if not account_id:
            return jsonify(error="account_id is required"), 400
        with db() as c:
            account, access = _access(c, actor, account_id)
            if not account:
                return jsonify(error="Google account not found"), 404
            if not access:
                return jsonify(error="Google authorization needs to be reconnected"), 401
            data = _http_json("GET", ACCOUNTS_API + "/accounts", access)
            for item in data.get("accounts", []):
                gid = str(item.get("name", "")).split("/")[-1]
                if gid != account["google_account_id"]:
                    continue
                url = LOCATIONS_API + "/accounts/%s/locations" % urllib.parse.quote(gid, safe="")
                locations = _http_json("GET", url, access, params={
                    "readMask": "name,title,storeCode,phoneNumbers,websiteUri,regularHours,specialHours,categories,latlng,metadata"
                }).get("locations", [])
                for loc in locations:
                    name = str(loc.get("name", ""))
                    existing = c.execute(
                        "SELECT id FROM google_locations WHERE owner_user_id=? AND resource_name=?",
                        (actor, name)).fetchone()
                    row = (
                        actor, account_id, name, loc.get("title", ""), loc.get("storeCode", ""),
                        json.dumps(loc.get("phoneNumbers", {}), ensure_ascii=False),
                        loc.get("websiteUri", ""), json.dumps(loc.get("regularHours", {}), ensure_ascii=False),
                        json.dumps(loc.get("categories", {}), ensure_ascii=False),
                        json.dumps(loc.get("latlng", {}), ensure_ascii=False),
                        json.dumps(loc.get("metadata", {}), ensure_ascii=False), now()
                    )
                    if existing:
                        c.execute(
                            "UPDATE google_locations SET google_account_id=?,title=?,store_code=?,phone_numbers=?,website_uri=?,regular_hours=?,categories=?,latlng=?,metadata=?,updated=? WHERE id=?",
                            (account_id, row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11], existing["id"]))
                    else:
                        c.execute(
                            "INSERT INTO google_locations(id,owner_user_id,google_account_id,resource_name,title,store_code,phone_numbers,website_uri,regular_hours,categories,latlng,metadata,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (uuid.uuid4().hex,) + row + (now(),))
                return jsonify(synced=len(locations))
        return jsonify(synced=0)

    @app.get("/api/google-business/locations")
    def google_business_locations():
        actor = _actor()
        if not actor:
            return jsonify(error="Authentication required"), 401
        with db() as c:
            rows = c.execute(
                "SELECT id,google_account_id,resource_name,title,store_code,phone_numbers,website_uri,regular_hours,categories,latlng,updated FROM google_locations WHERE owner_user_id=? ORDER BY title",
                (actor,)).fetchall()
        return jsonify(locations=[dict(x) for x in rows])

    @app.get("/api/google-business/reviews")
    def google_business_reviews():
        actor = _actor()
        location_id = request.args.get("location_id", "").strip()
        if not actor or not location_id:
            return jsonify(error="Authentication and location_id are required"), 400
        with db() as c:
            loc = c.execute(
                "SELECT * FROM google_locations WHERE id=? AND owner_user_id=?",
                (location_id, actor)).fetchone()
            if not loc:
                return jsonify(error="Location not found"), 404
            account, access = _access(c, actor, loc["google_account_id"])
            if not access:
                return jsonify(error="Google authorization needs to be reconnected"), 401
            resource = loc["resource_name"]
            url = REVIEWS_API + "/" + resource + "/reviews"
            data = _http_json("GET", url, access, params={"pageSize": 50, "orderBy": "updateTime desc"})
            reviews = data.get("reviews", [])
            for review in reviews:
                rid = review.get("reviewId") or review.get("name", "").split("/")[-1]
                if not rid:
                    continue
                c.execute(
                    "INSERT OR REPLACE INTO google_reviews(id,owner_user_id,google_location_id,review_id,rating,comment,reviewer,create_time,update_time,reply,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex, actor, location_id, rid,
                     review.get("starRating", ""), review.get("comment", ""),
                     json.dumps(review.get("reviewer", {}), ensure_ascii=False),
                     review.get("createTime"), review.get("updateTime"),
                     json.dumps(review.get("reviewReply", {}), ensure_ascii=False),
                     json.dumps(review, ensure_ascii=False)))
            return jsonify(reviews=reviews)
    @app.post("/api/google-business/reviews/reply")
    def google_business_reply():
        actor = _actor()
        body = request.get_json(silent=True) or {}
        location_id = str(body.get("location_id", "")).strip()
        review_id = str(body.get("review_id", "")).strip()
        comment = str(body.get("comment", "")).strip()
        if not actor or not location_id or not review_id or not comment:
            return jsonify(error="Authentication, location_id, review_id and comment are required"), 400
        with db() as c:
            loc = c.execute("SELECT * FROM google_locations WHERE id=? AND owner_user_id=?", (location_id, actor)).fetchone()
            if not loc:
                return jsonify(error="Location not found"), 404
            account, access = _access(c, actor, loc["google_account_id"])
            if not access:
                return jsonify(error="Google authorization needs to be reconnected"), 401
            resource = loc["resource_name"] + "/reviews/" + urllib.parse.quote(review_id, safe="")
            data = _http_json("PUT", REVIEWS_API + "/" + resource + "/reply", access,
                              {"comment": comment})
            c.execute("UPDATE google_reviews SET reply=?,update_time=? WHERE owner_user_id=? AND google_location_id=? AND review_id=?",
                      (json.dumps(data, ensure_ascii=False), now(), actor, location_id, review_id))
            log("google-business", "Published an approved Google review reply")
            return jsonify(review_reply=data)

    @app.get("/api/google-business/performance")
    def google_business_performance():
        actor = _actor()
        location_id = request.args.get("location_id", "").strip()
        start = request.args.get("start", "").strip()
        end = request.args.get("end", "").strip()
        if not actor or not location_id or not start or not end:
            return jsonify(error="Authentication, location_id, start and end are required"), 400
        try:
            sy, sm, sd = [int(x) for x in start.split("-")]
            ey, em, ed = [int(x) for x in end.split("-")]
        except Exception:
            return jsonify(error="Dates must use YYYY-MM-DD"), 400
        with db() as c:
            loc = c.execute("SELECT * FROM google_locations WHERE id=? AND owner_user_id=?", (location_id, actor)).fetchone()
            if not loc:
                return jsonify(error="Location not found"), 404
            account, access = _access(c, actor, loc["google_account_id"])
            if not access:
                return jsonify(error="Google authorization needs to be reconnected"), 401
            resource = loc["resource_name"]
            url = PERFORMANCE_API + "/" + resource + ":fetchMultiDailyMetricsTimeSeries"
            data = _http_json("GET", url, access, params=[
                ("dailyMetrics", "WEBSITE_CLICKS"),
                ("dailyMetrics", "CALL_CLICKS"),
                ("dailyMetrics", "BUSINESS_DIRECTION_REQUESTS"),
                ("dailyMetrics", "BUSINESS_IMPRESSIONS_DESKTOP_MAPS"),
                ("dailyMetrics", "BUSINESS_IMPRESSIONS_MOBILE_MAPS"),
                ("dailyMetrics", "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH"),
                ("dailyMetrics", "BUSINESS_IMPRESSIONS_MOBILE_SEARCH"),
                ("daily_range.start_date.year", sy),
                ("daily_range.start_date.month", sm),
                ("daily_range.start_date.day", sd),
                ("daily_range.end_date.year", ey),
                ("daily_range.end_date.month", em),
                ("daily_range.end_date.day", ed),
            ])
            return jsonify(performance=data)

    @app.post("/api/google-business/posts")
    def google_business_create_post():
        actor = _actor()
        body = request.get_json(silent=True) or {}
        location_id = str(body.get("location_id", "")).strip()
        summary = str(body.get("summary", "")).strip()
        topic = str(body.get("topic_type", "STANDARD")).strip().upper()
        language = str(body.get("language_code", "en-US")).strip()
        if not actor or not location_id or not summary:
            return jsonify(error="Authentication, location_id and summary are required"), 400
        if len(summary) > 1500:
            return jsonify(error="summary is too long"), 400
        allowed = {"STANDARD", "EVENT", "OFFER", "PRODUCT"}
        if topic not in allowed:
            return jsonify(error="Unsupported topic_type"), 400
        with db() as c:
            loc = c.execute("SELECT * FROM google_locations WHERE id=? AND owner_user_id=?", (location_id, actor)).fetchone()
            if not loc:
                return jsonify(error="Location not found"), 404
            account, access = _access(c, actor, loc["google_account_id"])
            if not access:
                return jsonify(error="Google authorization needs to be reconnected"), 401
            payload = {"languageCode": language, "summary": summary, "topicType": topic}
            cta_url = str(body.get("cta_url", "")).strip()
            cta_type = str(body.get("cta_type", "")).strip().upper()
            if cta_url:
                if cta_type not in {"BOOK", "ORDER", "SHOP", "LEARN_MORE", "SIGN_UP", "CALL"}:
                    return jsonify(error="Unsupported cta_type"), 400
                payload["callToAction"] = {"actionType": cta_type, "url": cta_url}
            data = _http_json("POST", REVIEWS_API + "/" + loc["resource_name"] + "/localPosts", access, payload)
            log("google-business", "Published a Google Business Profile post")
            return jsonify(post=data)
    return None