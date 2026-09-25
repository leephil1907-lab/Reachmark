"""Core SQLite schema and migration regression tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from web.app import db, add_lead, DB

class SchemaTests(unittest.TestCase):
    def test_source_seen_at_exists_and_is_updated(self):
        with db() as c:
            columns={r[1] for r in c.execute("PRAGMA table_info(leads)")}
            self.assertIn("source_seen_at", columns)
        add_lead({"name":"Schema fixture","city":"Fixture City","phone":"0000000000","website":""})
        with db() as c:
            row=c.execute("SELECT source_seen_at FROM leads WHERE name=?",("Schema fixture",)).fetchone()
            self.assertIsNotNone(row)
            self.assertTrue(row[0])

if __name__=="__main__":
    unittest.main()
