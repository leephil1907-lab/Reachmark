import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from web.migrations import run_migrations


class MigrationTests(unittest.TestCase):
    def test_legacy_schema_is_upgraded_once_and_backfilled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'legacy.sqlite3'
            c = sqlite3.connect(path)
            c.executescript('''
                CREATE TABLE leads(id TEXT PRIMARY KEY, created TEXT);
                CREATE TABLE jobs(id TEXT PRIMARY KEY);
                CREATE TABLE projects(id TEXT PRIMARY KEY);
                CREATE TABLE invoices(id TEXT PRIMARY KEY);
                CREATE TABLE review_responses(id TEXT PRIMARY KEY);
                CREATE TABLE review_links(id TEXT PRIMARY KEY);
                CREATE TABLE users(id TEXT PRIMARY KEY);
                CREATE TABLE payments(id TEXT PRIMARY KEY);
                INSERT INTO leads(id,created) VALUES('lead-1','2026-01-01T00:00:00+00:00');
            ''')
            c.commit()
            c.close()

            @contextmanager
            def db():
                conn = sqlite3.connect(path)
                try:
                    yield conn
                    conn.commit()
                finally:
                    conn.close()

            run_migrations(db)
            run_migrations(db)

            c = sqlite3.connect(path)
            self.assertIn('source_seen_at', {r[1] for r in c.execute('PRAGMA table_info(leads)')})
            self.assertIn('tier', {r[1] for r in c.execute('PRAGMA table_info(users)')})
            self.assertIn('period', {r[1] for r in c.execute('PRAGMA table_info(payments)')})
            self.assertEqual(
                c.execute("SELECT source_seen_at FROM leads WHERE id='lead-1'").fetchone()[0],
                '2026-01-01T00:00:00+00:00')
            self.assertEqual(c.execute('SELECT count(*) FROM schema_migrations').fetchone()[0], 1)
            c.close()


if __name__ == '__main__':
    unittest.main()
