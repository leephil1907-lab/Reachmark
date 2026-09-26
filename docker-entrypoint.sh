#!/bin/sh
set -e

# Ensure persistent mount paths exist
mkdir -p /data /backups

# If running as root, fix ownership and permissions on persistent volumes
# then drop privileges to the unprivileged 'reachmark' user.
if [ "$(id -u)" = '0' ]; then
    chown -R reachmark:reachmark /data /backups 2>/dev/null || true
    chmod 775 /data /backups 2>/dev/null || true
    exec gosu reachmark "$@"
fi

exec "$@"
