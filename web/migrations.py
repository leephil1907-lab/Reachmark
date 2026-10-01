"""Single-source SQLite migrations for Reachmark."""
from datetime import datetime, timezone

MIGRATION_VERSION=4

def _tables(c):
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
def _columns(c,table):
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
def _add_column(c,table,column,definition):
    if table not in _tables(c) or column in _columns(c,table): return False
    c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"); return True

def _apply_v1(c):
    for column,definition in [('audit_status','TEXT'),('audit_reason','TEXT'),('checked_at','TEXT'),('http_code','INTEGER'),
        ('latitude','REAL'),('longitude','REAL'),('opening_hours','TEXT'),('social_url','TEXT'),('source_tags','TEXT'),
        ('owner_user_id','TEXT'),('html','TEXT')]: _add_column(c,'leads',column,definition)
    _add_column(c,'jobs','owner_user_id','TEXT')

def _apply_v2(c):
    _add_column(c,'leads','source_seen_at','TEXT')
    if 'source_seen_at' in _columns(c,'leads'): c.execute("UPDATE leads SET source_seen_at=COALESCE(source_seen_at,created)")

def _apply_v3(c):
    upgrades={'projects':[('client_user_id','TEXT')],'invoices':[('client_user_id','TEXT')],
      'review_responses':[('rating','INTEGER')],'review_links':[('chat_message','TEXT')],
      'users':[('is_active','INTEGER DEFAULT 1'),('name','TEXT'),('email_verified','INTEGER DEFAULT 0'),
        ('verification_token','TEXT'),('verification_expires','TEXT'),('reset_token','TEXT'),('reset_expires','TEXT'),
        ('tier',"TEXT DEFAULT 'free'"),('tier_expires','TEXT'),('paystack_customer','TEXT'),('expiry_warned','TEXT')],
      'payments':[('period',"TEXT DEFAULT 'monthly')]}
    for table,cols in upgrades.items():
        for column,definition in cols: _add_column(c,table,column,definition)
    if 'users' in _tables(c) and 'tier' in _columns(c,'users'): c.execute("UPDATE users SET tier='free' WHERE tier IS NULL OR tier=''")

def _apply_v4(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS outreach_campaigns(
      id TEXT PRIMARY KEY, owner_user_id TEXT, name TEXT NOT NULL,
      provider TEXT NOT NULL CHECK(provider IN ('instantly','smartlead')),
      provider_campaign_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
      stop_on_reply INTEGER NOT NULL DEFAULT 1, stop_on_unsubscribe INTEGER NOT NULL DEFAULT 1,
      created TEXT NOT NULL, updated TEXT NOT NULL);
      CREATE UNIQUE INDEX IF NOT EXISTS idx_outreach_provider_campaign ON outreach_campaigns(provider,provider_campaign_id);
      CREATE TABLE IF NOT EXISTS outreach_enrollments(
      id TEXT PRIMARY KEY,campaign_id TEXT NOT NULL,lead_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',
      created TEXT NOT NULL,updated TEXT NOT NULL,UNIQUE(campaign_id,lead_id));
      CREATE TABLE IF NOT EXISTS outreach_events(
      id TEXT PRIMARY KEY,provider TEXT NOT NULL,provider_event_id TEXT NOT NULL UNIQUE,event_type TEXT NOT NULL,
      provider_campaign_id TEXT,provider_lead_id TEXT,email TEXT,occurred_at TEXT,payload TEXT NOT NULL,created TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS idx_outreach_events_email ON outreach_events(email);""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_outreach_enrollments_campaign ON outreach_enrollments(campaign_id)")

def run_migrations(db):
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)")
        applied={r[0] for r in c.execute("SELECT version FROM schema_migrations ORDER BY version")}
        for version,migration in ((1,_apply_v1),(2,_apply_v2),(3,_apply_v3),(4,_apply_v4)):
            if version not in applied:
                migration(c)
                c.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(?,?)",(version,datetime.now(timezone.utc).isoformat()))
        if 'jobs' in _tables(c) and 'state' in _columns(c,'jobs'):
            c.execute("UPDATE jobs SET state='interrupted',message='Server restarted; start a new search to continue.' WHERE state IN ('queued','running')")
