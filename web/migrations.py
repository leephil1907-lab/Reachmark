"""Centralized legacy SQLite schema migrations for Reachmark.

Feature modules own CREATE TABLE statements; this module owns ALTER TABLE upgrades.
Migrations are idempotent and run after all feature tables have been registered.
"""
from datetime import datetime, timezone

MIGRATION_VERSION = 1


def _columns(c, table):
    return {row[1] for row in c.execute(f'PRAGMA table_info({table})')}


def _add_column(c, table, column, definition):
    if table not in {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        return False
    if column in _columns(c, table):
        return False
    c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
    return True


def run_migrations(db):
    """Apply all legacy schema upgrades in one place.

    The function intentionally checks table existence so a partially assembled
    database can be upgraded safely on the next startup after its feature tables
    are created.
    """
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
        applied = {row[0] for row in c.execute('SELECT version FROM schema_migrations')}

        if MIGRATION_VERSION not in applied:
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
                ('source_seen_at', 'TEXT'),
            ]
            job_columns = [('owner_user_id', 'TEXT')]
            project_columns = [('client_user_id', 'TEXT')]
            invoice_columns = [('client_user_id', 'TEXT')]
            review_response_columns = [('rating', 'INTEGER')]
            review_link_columns = [('chat_message', 'TEXT')]

            required_tables = ('leads', 'jobs', 'projects', 'invoices', 'review_responses', 'review_links')
            tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if all(table in tables for table in required_tables):
                for column, definition in lead_columns:
                    _add_column(c, 'leads', column, definition)
                for column, definition in job_columns:
                    _add_column(c, 'jobs', column, definition)
                for column, definition in project_columns:
                    _add_column(c, 'projects', column, definition)
                for column, definition in invoice_columns:
                    _add_column(c, 'invoices', column, definition)
                for column, definition in review_response_columns:
                    _add_column(c, 'review_responses', column, definition)
                for column, definition in review_link_columns:
                    _add_column(c, 'review_links', column, definition)

                # Preserve historical lead timestamps when source_seen_at was
                # introduced. New writes continue to update it explicitly.
                c.execute("UPDATE leads SET source_seen_at=COALESCE(source_seen_at, created)")

                stamp = datetime.now(timezone.utc).isoformat()
                c.execute('INSERT INTO schema_migrations(version, applied_at) VALUES(?,?)',
                          (MIGRATION_VERSION, stamp))
