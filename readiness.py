import os,time
from pathlib import Path
from flask import jsonify

def register_readiness(app):
    @app.get('/api/operations/readiness')
    def readiness():
        backup='Not configured / no successful backup recorded'
        try:
            stamp=float((Path(os.getenv('BACKUP_DIR','/backups'))/'last-success').read_text());age=(time.time()-stamp)/3600
            backup=f'Last successful backup {age:.1f} hours ago'+(' — STALE: investigate now' if age>26 else '')
        except (OSError,ValueError):pass
        return jsonify({'Runtime mode':os.getenv('APP_ENV','development — do not expose publicly without owner credentials'),'Owner authentication':'Configured' if os.getenv('OWNER_PASSWORD_HASH') or os.getenv('DASHBOARD_PASSWORD') else 'NOT CONFIGURED — local preview only','Release':os.getenv('RELEASE_SHA','local / not deployed'),'Database':'Persistent volume required in production; SQLite WAL enabled','Backups':backup,'Error monitoring':'Sentry configured; verify with a controlled test' if os.getenv('SENTRY_DSN') else 'Not connected','Uptime alerts':'External monitor must be configured and tested separately','Map provider':'Custom endpoints configured' if os.getenv('OVERPASS_URLS') else 'Community endpoints — no uptime SLA'})
