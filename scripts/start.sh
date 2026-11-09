#!/bin/sh
# Platform-neutral production entrypoint for Render and Railway.
set -eu
if [ -z "${RELEASE_SHA:-}" ] || [ "${RELEASE_SHA:-}" = "local" ]; then
  if [ -n "${RENDER_GIT_COMMIT:-}" ]; then
    RELEASE_SHA="$RENDER_GIT_COMMIT"
  elif [ -n "${RAILWAY_GIT_COMMIT_SHA:-}" ]; then
    RELEASE_SHA="$RAILWAY_GIT_COMMIT_SHA"
  fi
fi
export RELEASE_SHA
DBPATH="${DATABASE_PATH:-/data/reachmark.sqlite3}"
mkdir -p "$(dirname "$DBPATH")" "${BACKUP_DIR:-/data/backups}" 2>/dev/null || true
python - <<'PY'
import os, sys
def clean(value):
    value = (value or '').strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]
    if value.startswith('<') or value.startswith('&lt;'):
        return ''
    return value
if os.getenv('APP_ENV') == 'production':
    errors = []
    key = clean(os.getenv('SECRET_KEY', ''))
    hashed = clean(os.getenv('OWNER_PASSWORD_HASH', ''))
    if len(key) < 32:
        errors.append('SECRET_KEY must be 32+ characters.')
    if not hashed.startswith(('scrypt:', 'pbkdf2:')):
        errors.append('OWNER_PASSWORD_HASH is missing or still a placeholder.')
    if not os.getenv('PUBLIC_BASE_URL', '').startswith('https://'):
        errors.append('PUBLIC_BASE_URL must start with https://')
    path = os.getenv('DATABASE_PATH', '')
    if not os.path.isabs(path):
        errors.append('DATABASE_PATH must be an absolute path.')
    if errors:
        sys.stderr.write('Reachmark production boot failed:' + chr(10))
        for item in errors:
            sys.stderr.write('  - ' + item + chr(10))
        sys.exit(1)
sys.stderr.write('Reachmark production checks passed. Starting Gunicorn on 0.0.0.0:%s' % os.getenv('PORT', '8000') + chr(10))
PY
exec gunicorn --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-1}" --threads "${GUNICORN_THREADS:-4}" --timeout 120 --access-logfile - --error-logfile - web.app:app
