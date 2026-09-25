"""Core SQLite schema and migration regression tests."""
import tempfile
import unittest
from pathlib import Path

import web.app as module
from web.schema import initialize_database

class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=module.DB
        module.DB=str(Path(self.tmp.name)/"schema.sqlite3")
        initialize_database(module.db)

    def tearDown(self):
        module.DB=self.old
        self.tmp.cleanup()

    def test_source_seen_at_exists_and_is_updated(self):
        with module.db() as c:
            columns={r[1] for r in c.execute("PRAGMA table_info(leads)")}
            self.assertIn("source_seen_at", columns)
        module.add_lead({"name":"Schema fixture","city":"Fixture City","phone":"0000000000","website":""})
        with module.db() as c:
            row=c.execute("SELECT source_seen_at FROM leads WHERE name=?",("Schema fixture",)).fetchone()
            self.assertIsNotNone(row)
            self.assertTrue(row[0])

if __name__=="__main__":
    unittest.main()
