import os, csv, io, json, sqlite3, uuid, re, ssl, smtplib, time, threading
from datetime import datetime, timezone
from urllib.parse import urlparse
from email.message import EmailMessage
import requests
from flask import Flask, request, jsonify, render_template, Response, abort

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 3 * 1024 * 1024
DB = os.getenv('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'prospect.sqlite3'))
lock = threading.Lock()
last_discovery = 0
CATEGORIES = {'Auto repair':('shop','car_repair'),'Hair salon':('shop','hairdresser'),'Bakery':('shop','bakery'),'Restaurant':('amenity','restaurant'),'Dentist':('amenity','dentist'),'Florist':('shop','florist'),'Plumber':('craft','plumber'),'Electrician':('craft','electrician'),'HVAC contractor':('craft','hvac'),'Roofing contractor':('craft','roofer'),'Tattoo studio':('shop','tattoo'),'Physiotherapist':('healthcare','physiotherapist'),'Pet groomer':('shop','pet_grooming'),'Accountant':('office','accountant')}
SOCIAL = ('facebook.com','instagram.com','linktr.ee','linktree.com','fb.com','business.site')
def now(): return datetime.now(timezone.utc).isoformat()
from contextlib import contextmanager
@contextmanager
def db():
    c = sqlite3.connect(DB, timeout=20); c.row_factory=sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()
with db() as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, source_key TEXT UNIQUE, name TEXT NOT NULL, category TEXT, city TEXT, address TEXT, phone TEXT, email TEXT, website TEXT, status TEXT, stage TEXT DEFAULT 'New', source TEXT, source_url TEXT, note TEXT DEFAULT '', subject TEXT DEFAULT '', body TEXT DEFAULT '', token TEXT UNIQUE, created TEXT, updated TEXT);
    CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, data TEXT);
    CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY, kind TEXT, message TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS sends (id TEXT PRIMARY KEY, lead_id TEXT, recipient TEXT, state TEXT, error TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS suppression (email TEXT PRIMARY KEY, created TEXT);
    CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,state TEXT,locations TEXT,category TEXT,progress INTEGER,total INTEGER,added INTEGER,checked INTEGER,message TEXT,created TEXT,updated TEXT);
    CREATE TABLE IF NOT EXISTS optout_links (token TEXT PRIMARY KEY, email TEXT NOT NULL);''')
# Non-destructive migrations for earlier workspaces.
with db() as c:
    columns={r[1] for r in c.execute('PRAGMA table_info(leads)')}
    for name,kind in [('audit_status','TEXT'),('audit_reason','TEXT'),('checked_at','TEXT'),('http_code','INTEGER'),('latitude','REAL'),('longitude','REAL'),('opening_hours','TEXT'),('social_url','TEXT'),('source_tags','TEXT')]:
        if name not in columns: c.execute(f'ALTER TABLE leads ADD COLUMN {name} {kind}')
    c.execute("UPDATE jobs SET state='interrupted',message='Server restarted; start a new search to continue.' WHERE state IN ('queued','running')")
from services import discover_location, audit_website
DEFAULTS={'sender_name':'','agency':'','reply_email':'','postal_address':'','public_base_url':'','offer':'clear, mobile-friendly websites that make it easier for customers to learn about services and get in touch'}
def settings():
    with db() as c: r=c.execute('SELECT data FROM settings WHERE id=1').fetchone()
    return {**DEFAULTS,**(json.loads(r[0]) if r else {})}
def log(kind, message):
    with db() as c: c.execute('INSERT INTO activity(kind,message,created) VALUES(?,?,?)',(kind,message,now()))
def lead(lid):
    with db() as c: r=c.execute('SELECT * FROM leads WHERE id=?',(lid,)).fetchone()
    if not r: abort(404)
    return dict(r)
def classify(url):
    if not url.strip(): return 'NOT_LISTED'
    host=urlparse(url if '://' in url else 'https://'+url).hostname or ''
    return 'SOCIAL_ONLY' if any(host==s or host.endswith('.'+s) for s in SOCIAL) else 'HAS_WEBSITE'
def add_lead(v):
    lid=uuid.uuid4().hex; stamp=now()
    website=v.get('website','').strip()
    key=v.get('source_key') or '|'.join(v.get(k,'').strip().lower() for k in ('name','city','phone'))
    with db() as c:
        cur=c.execute('INSERT OR IGNORE INTO leads(id,source_key,name,category,city,address,phone,email,website,status,source,source_url,token,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(lid,key,v['name'][:200],v.get('category','')[:100],v.get('city','')[:200],v.get('address','')[:500],v.get('phone','')[:100],v.get('email','')[:250],website[:1000],classify(website),v.get('source','CSV'),v.get('source_url',''),uuid.uuid4().hex,stamp,stamp))
        count=cur.rowcount
        if count:
            c.execute('UPDATE leads SET latitude=?,longitude=?,opening_hours=?,social_url=?,source_tags=? WHERE id=?',(v.get('latitude'),v.get('longitude'),v.get('opening_hours',''),v.get('social_url',''),json.dumps(v.get('source_tags',{})),lid))
        return count
@app.before_request
def same_origin():
    if request.method in ('POST','PATCH','DELETE'):
        origin=request.headers.get('Origin')
        if origin and urlparse(origin).netloc != request.host: return jsonify(error='Cross-origin request rejected.'),403
    # Optional protection for a public deployment. Preview and opt-out remain public.
    password=os.getenv('DASHBOARD_PASSWORD')
    if password and not request.path.startswith(('/preview/','/unsubscribe/','/static/','/about','/robots.txt','/sitemap.xml','/healthz')):
        auth=request.authorization
        if not auth or auth.username!='admin' or auth.password!=password:
            return Response('Authentication required',401,{'WWW-Authenticate':'Basic realm="Prospect"'})
@app.after_request
def headers(r):
    if request.path=='/' or request.path.startswith(('/api/','/preview/','/unsubscribe/')): r.headers['X-Robots-Tag']='noindex, nofollow'
    r.headers['X-Content-Type-Options']='nosniff'; r.headers['Referrer-Policy']='same-origin'
    return r
@app.errorhandler(413)
def too_big(e): return jsonify(error='File too large. Limit: 3 MB.'),413
@app.route('/')
def index(): return render_template('index.html')
@app.route('/healthz')
def healthz():
    with db() as c: c.execute('SELECT 1').fetchone()
    return jsonify(status='ok')
@app.route('/about')
def about():
    base=settings()['public_base_url'].rstrip('/')
    structured={'@context':'https://schema.org','@type':'SoftwareApplication','name':'Reachmark','applicationCategory':'BusinessApplication','operatingSystem':'Web','description':'Discover businesses worldwide, verify website opportunities, and start meaningful conversations with personalized website proposals.'}
    if base: structured['url']=base+'/about'
    return render_template('about.html',base=base,structured=structured)
@app.route('/robots.txt')
def robots():
    base=settings()['public_base_url'].rstrip('/')
    return Response('User-agent: *\nAllow: /about\nAllow: /static/\nDisallow: /api/\nDisallow: /preview/\nDisallow: /unsubscribe/\nDisallow: /$\n'+('Sitemap: '+base+'/sitemap.xml\n' if base else ''),mimetype='text/plain')
@app.route('/sitemap.xml')
def sitemap():
    from xml.sax.saxutils import escape
    base=settings()['public_base_url'].rstrip('/')
    entry='<url><loc>'+escape(base+'/about')+'</loc></url>' if base else ''
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+entry+'</urlset>',mimetype='application/xml')
@app.route('/api/state')
def state():
    with db() as c:
        leads=[dict(r) for r in c.execute('SELECT * FROM leads ORDER BY created DESC')]
        activity=[dict(r) for r in c.execute('SELECT * FROM activity ORDER BY id DESC LIMIT 12')]
        sent=c.execute("SELECT count(*) FROM sends WHERE state='sent'").fetchone()[0]
        suppressed=[r[0] for r in c.execute('SELECT email FROM suppression')]
        jobs=[dict(r) for r in c.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 15')]
    return jsonify(leads=leads,jobs=jobs,activity=activity,sent=sent,settings=settings(),categories=list(CATEGORIES),smtp_ready=bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM')),suppressed=suppressed)
@app.route('/api/settings',methods=['POST'])
def save_settings():
    data=request.get_json() or {}; s={k:str(data.get(k,''))[:1500].strip() for k in DEFAULTS}
    u=s['public_base_url']
    if s['reply_email'] and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',s['reply_email']): return jsonify(error='Enter a valid reply-to email.'),400
    if u and (urlparse(u).scheme!='https' or not urlparse(u).netloc): return jsonify(error='Public preview URL must start with https://.'),400
    with db() as c: c.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps(s),))
    log('settings','Sender profile updated'); return jsonify(ok=True)
@app.route('/api/leads',methods=['POST'])
def create_lead():
    v=request.get_json() or {}
    if not str(v.get('name','')).strip(): return jsonify(error='Business name is required.'),400
    v={k:str(val).strip() for k,val in v.items()}; v['source']='Manual'
    count=add_lead(v); log('import',f'{count} business added manually'); return jsonify(added=count)
@app.route('/api/leads/<lid>',methods=['PATCH','DELETE'])
def update_lead(lid):
    lead(lid)
    if request.method=='DELETE':
        with db() as c: c.execute('DELETE FROM leads WHERE id=?',(lid,))
        return jsonify(ok=True)
    data=request.get_json() or {}; allowed={'name','email','phone','website','note','stage','subject','body'}
    data={k:str(v)[:10000] for k,v in data.items() if k in allowed}
    if 'name' in data and not data['name'].strip(): return jsonify(error='Business name is required.'),400
    if 'stage' in data and data['stage'] not in ['New','Drafted','Contacted','Replied','Won','Not a fit']: return jsonify(error='Invalid stage.'),400
    if 'website' in data:
        data['status']=classify(data['website'])
        if data['website']!=lead(lid)['website']:
            data.update(audit_status=None,audit_reason=None,http_code=None,checked_at=None)
    data['updated']=now()
    with db() as c: c.execute('UPDATE leads SET '+','.join(k+'=?' for k in data)+' WHERE id=?',[*data.values(),lid])
    return jsonify(ok=True)
@app.route('/api/import',methods=['POST'])
def import_csv():
    f=request.files.get('file')
    if not f: return jsonify(error='Choose a CSV file.'),400
    try:
        reader=csv.DictReader(io.StringIO(f.read().decode('utf-8-sig')))
        if not reader.fieldnames or 'name' not in reader.fieldnames: return jsonify(error='CSV must have a name column. Optional: category, city, address, phone, email, website.'),400
        rows=list(reader)
        if len(rows)>5000: return jsonify(error='Import up to 5,000 rows per file.'),400
        count=0
        for r in rows:
            v={k:(val or '').strip() for k,val in r.items() if isinstance(val,(str,type(None))) and k}
            v['website']=v.get('website') or v.get('listed_website',''); v['city']=v.get('city') or v.get('city_searched',''); v['source']='CSV'
            if v.get('name'): count+=add_lead(v)
        log('import',f'Imported {count} businesses from CSV'); return jsonify(added=count,skipped=len(rows)-count)
    except (UnicodeError,csv.Error,TypeError): return jsonify(error='Could not read this file. Upload a UTF-8 CSV.'),400
@app.route('/api/export')
def export():
    with db() as c: rows=[dict(r) for r in c.execute('SELECT * FROM leads ORDER BY created DESC')]
    fields=['name','category','city','address','phone','email','website','status','stage','source','source_url','note','audit_status','audit_reason','checked_at','http_code','latitude','longitude','opening_hours','social_url']
    f=io.StringIO(); w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader()
    for row in rows:
        w.writerow({k: ("'"+str(v) if str(v).startswith(('=','+','-','@','\t','\r')) else v) for k,v in row.items()})
    return Response(f.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=reachmark-leads.csv'})
def search_save(location, category, include_websites=False):
    rows, resolved=discover_location(location,CATEGORIES[category])
    added=0; candidates=0
    for row in rows:
        row['category']=category
        if not include_websites and classify(row['website'])=='HAS_WEBSITE': continue
        candidates+=1; added+=add_lead(row)
    return {'added':added,'scanned':len(rows),'candidates':candidates,'resolved':resolved},rows

@app.route('/api/discover',methods=['POST'])
def discover():
    global last_discovery
    v=request.get_json() or {}; city=str(v.get('city','')).strip(); category=v.get('category')
    if not city or len(city)>150 or category not in CATEGORIES: return jsonify(error='Choose a location and category.'),400
    with lock:
        if time.monotonic()-last_discovery<10: return jsonify(error='Wait 10 seconds between searches.'),429
        last_discovery=time.monotonic()
    try:
        result,_=search_save(city,category)
        log('discovery',f"{city} · {category}: {result['added']} new candidates from {result['scanned']} listings")
        return jsonify(result)
    except (requests.RequestException,ValueError,KeyError): return jsonify(error='Public map service unavailable or location not found. Retry later or import CSV.'),502

def run_job(jid,locations,category,check):
    added=checked=failures=0
    try:
        for i,location in enumerate(locations):
            with db() as c:
                if c.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone()[0]=='cancelled': return
                c.execute("UPDATE jobs SET state='running',message=?,updated=? WHERE id=?",('Searching '+location,now(),jid))
            try:
                result,rows=search_save(location,category,include_websites=check);added+=result['added']
                # Bound website audits per location; remaining saved URLs can be checked manually.
                if check:
                    for row in [r for r in rows if r.get('website')][:12]:
                        with db() as c:
                            if c.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone()[0]=='cancelled': return
                            l=c.execute('SELECT id FROM leads WHERE source_key=?',(row['source_key'],)).fetchone()
                        if l:
                            save_audit(l['id']);checked+=1
                            with db() as c: c.execute('UPDATE jobs SET added=?,checked=?,message=?,updated=? WHERE id=?',(added,checked,'Checking websites in '+location,now(),jid))
                message=f"{location}: {result['scanned']} listings checked, {result['added']} added"
                log('discovery',message)
            except (requests.RequestException,ValueError,KeyError):
                failures+=1;message=location+': source unavailable or location not found';log('error',message)
            with db() as c:
                c.execute('UPDATE jobs SET progress=?,added=?,checked=?,message=?,updated=? WHERE id=?',(i+1,added,checked,message,now(),jid))
            if i<len(locations)-1: time.sleep(2)
        with db() as c: c.execute("UPDATE jobs SET state=?,message=?,updated=? WHERE id=? AND state!='cancelled'",('completed' if failures==0 else 'partial' if failures<len(locations) else 'failed',f'{added} businesses saved; {checked} URL checks; {failures} source failures.',now(),jid))
    except Exception:
        with db() as c: c.execute("UPDATE jobs SET state='failed',message='Job interrupted by a server error; saved results remain available.',updated=? WHERE id=?",(now(),jid))

@app.route('/api/jobs',methods=['POST'])
def start_job():
    v=request.get_json() or {}; locations=v.get('locations',[]); category=v.get('category')
    if not isinstance(locations,list) or not 1<=len(locations)<=8 or any(not isinstance(x,str) or not x.strip() or len(x)>150 for x in locations) or category not in CATEGORIES: return jsonify(error='Enter 1–8 city/country locations and a supported category.'),400
    locations=list(dict.fromkeys(x.strip() for x in locations));jid=uuid.uuid4().hex
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running')").fetchone(): return jsonify(error='A discovery job is already running. Wait or cancel it first.'),409
        c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',(jid,'queued',json.dumps(locations),category,0,len(locations),0,0,'Waiting for public map services',now(),now()))
    threading.Thread(target=run_job,args=(jid,locations,category,bool(v.get('check_websites'))),daemon=True).start()
    return jsonify(id=jid),202

@app.route('/api/jobs/<jid>/cancel',methods=['POST'])
def cancel_job(jid):
    with db() as c: c.execute("UPDATE jobs SET state='cancelled',message='Cancelled. An in-flight source request may finish saving results.',updated=? WHERE id=? AND state IN ('queued','running')",(now(),jid))
    return jsonify(ok=True)

def save_audit(lid):
    l=lead(lid);result=audit_website(l['website'])
    with db() as c: c.execute('UPDATE leads SET audit_status=?,audit_reason=?,http_code=?,checked_at=? WHERE id=?',(result['status'],result['reason'],result.get('http_code'),now(),lid))
    return result

@app.route('/api/leads/<lid>/audit',methods=['POST'])
def audit_lead(lid):
    result=save_audit(lid);log('audit',f"Website checked for {lead(lid)['name']}: {result['status']}");return jsonify(result)

def compose(l, tone, include_preview):
    s=settings(); who=s['sender_name'] or 'Your name'; agency=s['agency'] or 'Your studio'
    subject=f"A website idea for {l['name']}"
    intro=f"Hi {l['name']} team,"
    context=f"I’m {who} from {agency}. I came across your business"+(f" in {l['city']}" if l['city'] else '')+" and wanted to introduce myself."
    pitch=f"We build {s['offer'].rstrip('.')} .".replace(' .','.')
    if tone=='Concise': pitch='We build straightforward, mobile-friendly websites with clear services and an easy way for customers to get in touch.'
    if tone=='Warm': context+= ' I thought a simple website concept might be useful to your team.'
    preview=''
    if include_preview:
        if s['public_base_url']: preview=f"I put together an initial concept for your business: {s['public_base_url'].rstrip('/')}/preview/{l['token']}\nIt’s an independent design proposal, not your official website. The content is a starting point for your review."
        else: preview='I’ve put together an initial website concept for your business. If you’re interested, I can share a preview for your review.'
    close='Would you be interested in taking a look? If it feels like a good fit, reply with what you need and your budget. We can provide a tailored quote before you commit to a build.'
    footer=f"Best,\n{who}\n{agency}"
    if s['reply_email']: footer+='\n'+s['reply_email']
    if s['postal_address']: footer+='\n'+s['postal_address']
    footer+='\n\nIf this isn’t relevant, reply “no thanks” and I won’t follow up.'
    if s['public_base_url']: footer+=f"\nOr opt out here: {s['public_base_url'].rstrip('/')}/unsubscribe/{l['token']}"
    return subject,'\n\n'.join(x for x in [intro,context,pitch,preview,close,footer] if x)
@app.route('/api/leads/<lid>/compose',methods=['POST'])
def draft(lid):
    l=lead(lid); v=request.get_json() or {}; subject,body=compose(l,v.get('tone','Professional'),v.get('preview',True))
    with db() as c: c.execute("UPDATE leads SET subject=?,body=?,stage=CASE WHEN stage='New' THEN 'Drafted' ELSE stage END,updated=? WHERE id=?",(subject,body,now(),lid))
    log('draft',f'Draft created for {l["name"]}'); return jsonify(subject=subject,body=body)
@app.route('/preview/<token>')
def preview(token):
    with db() as c: r=c.execute('SELECT * FROM leads WHERE token=?',(token,)).fetchone()
    if not r: abort(404)
    return render_template('preview.html',lead=dict(r),studio=settings()['agency'] or 'Reachmark Studio')
@app.route('/unsubscribe/<token>',methods=['GET','POST'])
def unsubscribe(token):
    with db() as c:
        l=c.execute('SELECT email FROM optout_links WHERE token=?',(token,)).fetchone() or c.execute('SELECT email FROM leads WHERE token=?',(token,)).fetchone()
    if not l: abort(404)
    done=False
    if request.method=='POST':
        with db() as c:
            if l['email']: c.execute('INSERT OR IGNORE INTO suppression VALUES(?,?)',(l['email'].strip().lower(),now()))
        done=True
    return render_template('unsubscribe.html',done=done)
@app.route('/api/leads/<lid>/suppress',methods=['POST'])
def suppress(lid):
    l=lead(lid)
    if not l['email']: return jsonify(error='Add an email address first.'),400
    with db() as c: c.execute('INSERT OR IGNORE INTO suppression VALUES(?,?)',(l['email'].lower().strip(),now()))
    log('suppression',f'Outreach blocked for {l["name"]}'); return jsonify(ok=True)
@app.route('/api/leads/<lid>/send',methods=['POST'])
def send(lid):
    l=lead(lid); v=request.get_json() or {}; s=settings(); recipient=l['email'].strip().lower()
    if not v.get('approved') or not v.get('basis'): return jsonify(error='Confirm review and a lawful basis for contacting this recipient.'),400
    if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',recipient): return jsonify(error='Add a valid recipient email.'),400
    if not l['subject'] or not l['body']: return jsonify(error='Save a subject and message first.'),400
    if any(not s[k] for k in ['sender_name','agency','reply_email','postal_address']): return jsonify(error='Complete your sender profile, including postal address, in Settings.'),400
    if '\n' in l['subject'] or '\r' in l['subject']: return jsonify(error='Invalid subject.'),400
    if not os.getenv('SMTP_HOST') or not os.getenv('SMTP_FROM'): return jsonify(error='SMTP is not configured. See Settings and README.'),400
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM suppression WHERE email=?',(recipient,)).fetchone(): return jsonify(error='This recipient has opted out. Sending is blocked.'),400
        if c.execute("SELECT 1 FROM sends WHERE lead_id=? AND state IN ('sending','sent','unknown')",(lid,)).fetchone(): return jsonify(error='A message was already sent, is sending, or has an uncertain result. Check your mail provider before any follow-up.'),409
        sid=uuid.uuid4().hex
        c.execute('INSERT INTO sends VALUES(?,?,?,?,?,?)',(sid,lid,recipient,'sending','',now()))
        c.execute('INSERT OR IGNORE INTO optout_links VALUES(?,?)',(l['token'],recipient))
    log('approval',f'User confirmed message review and contact basis for {l["name"]}')
    try:
        msg=EmailMessage(); msg['From']=os.environ['SMTP_FROM']; msg['To']=recipient; msg['Reply-To']=s['reply_email']; msg['Subject']=l['subject']; msg['Message-ID']=f'<{sid}@{os.environ["SMTP_FROM"].split("@")[-1]}>'
        body=l['body']
        # Keep sender identification and opt-out instructions even if the draft was edited.
        body+=f"\n\n—\n{s['sender_name']} | {s['agency']}\n{s['postal_address']}\nContact: {s['reply_email']}\nTo stop receiving emails, reply ‘no thanks’."
        if s['public_base_url']: body+=f"\nOpt out: {s['public_base_url'].rstrip('/')}/unsubscribe/{l['token']}"
        msg.set_content(body)
        host=os.environ['SMTP_HOST']; port=int(os.getenv('SMTP_PORT','587')); mode=os.getenv('SMTP_SECURITY','starttls')
        if mode not in ('ssl','starttls'): raise ValueError('TLS is required')
        cls=smtplib.SMTP_SSL if mode=='ssl' else smtplib.SMTP
        with cls(host,port,timeout=25) as smtp:
            if mode=='starttls': smtp.starttls(context=ssl.create_default_context())
            if os.getenv('SMTP_USER'): smtp.login(os.environ['SMTP_USER'],os.getenv('SMTP_PASSWORD',''))
            smtp.send_message(msg)
        with db() as c:
            c.execute("UPDATE sends SET state='sent' WHERE id=?",(sid,)); c.execute("UPDATE leads SET stage='Contacted',updated=? WHERE id=?",(now(),lid))
        log('sent',f'Mail server accepted email for {l["name"]}'); return jsonify(ok=True)
    except Exception as e:
        # Explicit rejection is retryable; dropped connections may leave acceptance uncertain.
        rejected=isinstance(e,(smtplib.SMTPAuthenticationError,smtplib.SMTPRecipientsRefused,smtplib.SMTPSenderRefused,smtplib.SMTPDataError,smtplib.SMTPNotSupportedError,ValueError))
        with db() as c: c.execute("UPDATE sends SET state=?,error=? WHERE id=?",('failed' if rejected else 'unknown',type(e).__name__,sid))
        log('error',f'SMTP needs review for {l["name"]}: {type(e).__name__}')
        return jsonify(error=('SMTP rejected the message. Check your provider configuration and credentials before retrying.' if rejected else 'SMTP did not confirm success. Check credentials and your provider’s sent logs. Resending is blocked to avoid duplicates.')),502

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','8000')),debug=False)
