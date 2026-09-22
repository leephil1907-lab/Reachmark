# Vercel serverless entry — wraps the Flask app
# Vercel filesystem is read-only except /tmp — use /tmp for SQLite.
import os
if os.getenv("VERCEL") and not os.getenv("DATABASE_PATH"):
    os.environ["DATABASE_PATH"] = "/tmp/reachmark.sqlite3"
# Ensure required secrets have safe defaults for preview (ephemeral demo)
os.environ.setdefault("SECRET_KEY", "vercel-preview-not-for-production-please-rotate")
from web.app import app
# Vercel expects `app` or `handler`
