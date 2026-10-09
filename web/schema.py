"""Central SQLite schema bootstrap for Reachmark.

Table creation lives here. Schema upgrades live exclusively in web.migrations.
"""
from __future__ import annotations

CORE_SQL = """
CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, source_key TEXT UNIQUE, name TEXT NOT NULL, category TEXT, city TEXT, address TEXT, phone TEXT, email TEXT, website TEXT, status TEXT, stage TEXT DEFAULT 'New', source TEXT, source_url TEXT, note TEXT DEFAULT '', subject TEXT DEFAULT '', body TEXT DEFAULT '', token TEXT UNIQUE, created TEXT, updated TEXT, owner_user_id TEXT);
CREATE TABLE IF NOT EXISTS lead_reviews (lead_id TEXT PRIMARY KEY, verification TEXT NOT NULL, evidence_url TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', reviewed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY, kind TEXT, message TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS sends (id TEXT PRIMARY KEY, lead_id TEXT, recipient TEXT, state TEXT, error TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS suppression (email TEXT PRIMARY KEY, created TEXT);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,state TEXT,locations TEXT,category TEXT,progress INTEGER,total INTEGER,added INTEGER,checked INTEGER,message TEXT,created TEXT,updated TEXT,owner_user_id TEXT);
CREATE TABLE IF NOT EXISTS optout_links (token TEXT PRIMARY KEY, email TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS client_reviews (id TEXT PRIMARY KEY, name TEXT NOT NULL, business TEXT, rating INTEGER NOT NULL, text TEXT NOT NULL, created TEXT NOT NULL, approved INTEGER DEFAULT 1);
"""

def initialize_database(db):
    """Create the base tables and SQLite settings required before feature registration.

    No ALTER TABLE or migration-version logic belongs here. All schema upgrades
    are owned by web.migrations and run once the feature modules have registered
    their tables.
    """
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(CORE_SQL)
