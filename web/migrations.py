"""Single-source SQLite migrations for Reachmark.

web.schema owns CREATE TABLE bootstrap.
This module owns every additive schema upgrade and migration version.
"""
from datetime import datetime, timezone

MIGRATION_VERSION = 3


def _tables(c):
    return {row[0] for row in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}


def _columns(c, table):
    return {row[1] for row in c.execute(f"PRAGMA table_info({table})")}


def _add_column(c, table, column, definition):
    if table not in _tables(c):
        return False
    if column in _columns(c, table):
        return False
    c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    return True


def _apply_v1(c):
    """Original lead/job audit fields."""
    lead_columns = [
        ('audit_status', 'TEXT'),
        ('audit_reason', 'TEXT'),
        ('checked_at', 'TEXT'),
        ('http_code', 'INTEGER'),
        ('latitude', 'REAL'),
        ('longitude', 'REAL'),
        ('opening_hours', 'TEXT'),
        ('social_url', 'TEXT'),
        ('source_tags', 'TEXT'),
        ('owner_user_id', 'TEXT'),
        ('html', 'TEXT'),
    ]
    for column, definition in lead_columns:
        _add_column(c, 'leads', column, definition)
    _add_column(c, 'jobs', 'owner_user_id', 'TEXT')


def _apply_v2(c):
    """Introduce durable source observation timestamps."""
    _add_column(c, 'leads', 'source_seen_at', 'TEXT')
    if 'source_seen_at' in _columns(c, 'leads'):
        c.execute(
            "UPDATE leads SET source_seen_at=COALESCE(source_seen_at, created)"
        )


def _apply_v3(c):
    """Complete legacy feature-table compatibility upgrades."""
    upgrades = {
        'projects': [('client_user_id', 'TEXT')],
        'invoices': [('client_user_id', 'TEXT')],
        'review_responses': [('rating', 'INTEGER')],
        'review_links': [('chat_message', 'TEXT')],
        'users': [
            ('is_active', 'INTEGER DEFAULT 1'),
            ('name', 'TEXT'),
            ('email_verified', 'INTEGER DEFAULT 0'),
            ('verification_token', 'TEXT'),
            ('verification_expires', 'TEXT'),
            ('reset_token', 'TEXT'),
            ('reset_expires', 'TEXT'),
            ('tier', "TEXT DEFAULT 'free'"),
            ('tier_expires', 'TEXT'),
            ('paystack_customer', 'TEXT'),
            ('expiry_warned', 'TEXT'),
        ],
        'payments': [('period', "TEXT DEFAULT 'monthly'")],
    }
    for table, columns in upgrades.items():
        for column, definition in columns:
            _add_column(c, table, column, definition)

    if 'users' in _tables(c) and 'tier' in _columns(c, 'users'):
        c.execute("UPDATE users SET tier='free' WHERE tier IS NULL OR tier=''")


def run_migrations(db):
    """Apply pending migrations in order, idempotently.

    Older databases may already contain migration version 1 or 2 from the
    previous bootstrap implementation. They are respected and only missing
    versions are applied. A fresh database receives all three versions.
    """
    with db() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {
            row[0] for row in c.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        }

        migrations = ((1, _apply_v1), (2, _apply_v2), (3, _apply_v3))
        for version, migration in migrations:
            if version in applied:
                continue
            migration(c)
            c.execute(
                "INSERT INTO schema_migrations(version, applied_at) "
                "VALUES(?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )

        # Keep this restart recovery in the centralized database lifecycle.
        if 'jobs' in _tables(c):
            c.execute(
                "UPDATE jobs SET state='interrupted', "
                "message='Server restarted; start a new search to continue.' "
                "WHERE state IN ('queued','running')"
            )
