#!/bin/sh
# Railway / Docker start — print a clear reason if production env is still a template.
set -e
if [ -z "$RELEASE_SHA" ] || [ "$RELEASE_SHA" = "local" ]; then
  if [ -n "$RAILWAY_GIT_COMMIT_SHA" ]; then
    RELEASE_SHA="$RAILWAY_GIT_COMMIT_SHA"
  fi
fi
export RELEASE_SHA
DBPATH="${DATABASE_PATH:-/data/reachmark.sqlite3}"
mkdir -p "$(dirname "$DBPATH")" /backups 2>/dev/null || true
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
        errors.append('SECRET_KEY must be 32+ characters (got %d).' % len(key))
    if not hashed.startswith(('scrypt:', 'pbkdf2:')):
        errors.append('OWNER_PASSWORD_HASH is still a placeholder. Paste the scrypt hash with no quotes.')
    if not os.getenv('PUBLIC_BASE_URL', '').startswith('https://'):
        errors.append('PUBLIC_BASE_URL must start with https://')
    path = os.getenv('DATABASE_PATH', '')
    if not os.path.isabs(path):
        errors.append('DATABASE_PATH must be absolute, e.g. /data/reachmark.sqlite3')
    if errors:
        sys.stderr.write('Reachmark production boot failed:\n')
        for item in errors:
            sys.stderr.write('  - %s\n' % item)
        sys.exit(1)
sys.stderr.write('Reachmark env checks passed. Starting gunicorn on 0.0.0.0:%s\n' % os.getenv('PORT', '8000'))
PY
exec gunicorn --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - web.app:app
