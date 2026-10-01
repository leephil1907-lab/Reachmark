import os, tempfile, unittest, sqlite3
from web import migrations

class OutreachSchemaTests(unittest.TestCase):
    def test_v4_tables(self):
        fd,path=tempfile.mkstemp(suffix=".sqlite3"); os.close(fd)
        try:
            conn=sqlite3.connect(path)
            conn.executescript("""CREATE TABLE leads(id TEXT PRIMARY KEY,source_key TEXT UNIQUE,name TEXT NOT NULL,category TEXT,city TEXT,address TEXT,phone TEXT,email TEXT,website TEXT,status TEXT,stage TEXT,source TEXT,source_url TEXT,note TEXT,subject TEXT,body TEXT,token TEXT,created TEXT,updated TEXT); CREATE TABLE jobs(id TEXT PRIMARY KEY,state TEXT);""")
            class Ctx:
                def __enter__(self): return conn
                def __exit__(self,*args): conn.commit()
            migrations.run_migrations(lambda: Ctx())
            tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"outreach_campaigns","outreach_enrollments","outreach_events"} <= tables)
            self.assertEqual(conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],4)
        finally: os.unlink(path)
