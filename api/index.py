# Vercel serverless entry — wraps the Flask app.
# Vercel filesystem is read-only except /tmp — use /tmp for SQLite.
import os

if os.getenv("VERCEL"):
    if not os.getenv("DATABASE_PATH"):
        os.environ["DATABASE_PATH"] = "/tmp/reachmark.sqlite3"
    # Fail closed: no hardcoded secrets. A Vercel deployment without the required
    # env vars serves a clear 503 instead of booting with an insecure default key.
    missing = [k for k in ("SECRET_KEY", "OWNER_PASSWORD_HASH") if not os.getenv(k)]
    if missing:
        from flask import Flask, Response

        app = Flask(__name__)

        @app.get("/")
        @app.get("/<path:_>")
        def not_configured(_=""):
            return Response(
                "Reachmark is not configured. Set the following environment "
                "variables on Vercel and redeploy: " + ", ".join(missing) + ".",
                status=503,
                mimetype="text/plain",
            )
    else:
        from app import app
else:
    from app import app
