"""Central SQLite schema bootstrap and additive migrations for Reachmark."""
from __future__ import annotations
SCHEMA_VERSION=2
CORE_SQL="""
CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, source_key TEXT UNIQUE, name TEXT NOT NULL, category TEXT, city TEXT, address TEXT, phone TEXT, email TEXT, website TEXT, status TEXT, stage TEXT DEFAULT 'New', source TEXT, source_url TEXT, note TEXT DEFAULT '', subject TEXT DEFAULT '', body TEXT DEFAULT '', token TEXT UNIQUE, created TEXT, updated TEXT, owner_user_id TEXT);
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY, kind TEXT, message TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS sends (id TEXT PRIMARY KEY, lead_id TEXT, recipient TEXT, state TEXT, error TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS suppression (email TEXT PRIMARY KEY, created TEXT);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,state TEXT,locations TEXT,category TEXT,progress INTEGER,total INTEGER,added INTEGER,checked INTEGER,message TEXT,created TEXT,updated TEXT,owner_user_id TEXT);
CREATE TABLE IF NOT EXISTS optout_links (token TEXT PRIMARY KEY, email TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS client_reviews (id TEXT PRIMARY KEY, name TEXT NOT NULL, business TEXT, rating INTEGER NOT NULL, text TEXT NOT NULL, created TEXT NOT NULL, approved INTEGER DEFAULT 1);
"""
LEAD_COLUMNS={"audit_status":"TEXT","audit_reason":"TEXT","checked_at":"TEXT","http_code":"INTEGER","latitude":"REAL","longitude":"REAL","opening_hours":"TEXT","social_url":"TEXT","source_tags":"TEXT","owner_user_id":"TEXT","html":"TEXT","source_seen_at":"TEXT"}
def _columns(c,table): return {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
def _add_missing(c,table,columns):
    existing=_columns(c,table)
    for name,kind in columns.items():
        if name not in existing: c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
def initialize_database(db):
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL"); c.executescript(CORE_SQL)
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        applied={row[0] for row in c.execute("SELECT version FROM schema_migrations")}
        if 1 not in applied:
            _add_missing(c,"leads",{k:v for k,v in LEAD_COLUMNS.items() if k!="source_seen_at"}); _add_missing(c,"jobs",{"owner_user_id":"TEXT"})
            c.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(1,datetime('now'))")
        if 2 not in applied:
            _add_missing(c,"leads",{"source_seen_at":"TEXT"}); c.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(2,datetime('now'))")
        _add_missing(c,"leads",LEAD_COLUMNS); _add_missing(c,"jobs",{"owner_user_id":"TEXT"})
        c.execute("UPDATE jobs SET state='interrupted',message='Server restarted; start a new search to continue.' WHERE state IN ('queued','running')")
