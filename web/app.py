import os, csv, io, json, sqlite3, uuid, re, ssl, smtplib, time, threading
from datetime import datetime, timezone
from urllib.parse import urlparse
from email.message import EmailMessage
import requests
from flask import Flask, request, jsonify, render_template, Response, abort, redirect

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config['MAX_CONTENT_LENGTH'] = 3 * 1024 * 1024
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.getenv('DATABASE_PATH', os.path.join(ROOT, 'prospect.sqlite3'))
lock = threading.Lock()
last_discovery = 0
CATEGORIES = {'Auto repair':('shop','car_repair'),'Hair salon':('shop','hairdresser'),'Bakery':('shop','bakery'),'Restaurant':('amenity','restaurant'),'Dentist':('amenity','dentist'),'Florist':('shop','florist'),'Plumber':('craft','plumber'),'Electrician':('craft','electrician'),'HVAC contractor':('craft','hvac'),'Roofing contractor':('craft','roofer'),'Tattoo studio':('shop','tattoo'),'Physiotherapist':('healthcare','physiotherapist'),'Pet groomer':('shop','pet_grooming'),'Accountant':('office','accountant')}
CATEGORIES.update({'Café':('amenity','cafe'),'Fast food':('amenity','fast_food'),'Bar':('amenity','bar'),'Hotel':('tourism','hotel'),'Guest house':('tourism','guest_house'),'Pharmacy':('amenity','pharmacy'),'Clinic':('amenity','clinic'),'Veterinarian':('amenity','veterinary'),'Gym':('leisure','fitness_centre'),'Beauty salon':('shop','beauty'),'Clothing shop':('shop','clothes'),'Supermarket':('shop','supermarket'),'Convenience store':('shop','convenience'),'Laundry':('shop','laundry'),'Car wash':('amenity','car_wash'),'Carpenter':('craft','carpenter'),'Painter':('craft','painter'),'Photographer':('craft','photographer'),'Lawyer':('office','lawyer'),'Estate agent':('office','estate_agent'),'Travel agency':('shop','travel_agency')})
SOCIAL = ('facebook.com','instagram.com','linktr.ee','linktree.com','fb.com','business.site')
def now(): return datetime.now(timezone.utc).isoformat()
from contextlib import contextmanager
@contextmanager
def db():
    c = sqlite3.connect(DB, timeout=20); c.row_factory=sqlite3.Row
    c.execute('PRAGMA busy_timeout=20000')
    try:
        with c:
            yield c
    finally:
        c.close()
with db() as c:
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY, source_key TEXT UNIQUE, name TEXT NOT NULL, category TEXT, city TEXT, address TEXT, phone TEXT, email TEXT, website TEXT, status TEXT, stage TEXT DEFAULT 'New', source TEXT, source_url TEXT, note TEXT DEFAULT '', subject TEXT DEFAULT '', body TEXT DEFAULT '', token TEXT UNIQUE, created TEXT, updated TEXT);
    CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, data TEXT);
    CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY, kind TEXT, message TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS sends (id TEXT PRIMARY KEY, lead_id TEXT, recipient TEXT, state TEXT, error TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS suppression (email TEXT PRIMARY KEY, created TEXT);
    CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,state TEXT,locations TEXT,category TEXT,progress INTEGER,total INTEGER,added INTEGER,checked INTEGER,message TEXT,created TEXT,updated TEXT);
    CREATE TABLE IF NOT EXISTS optout_links (token TEXT PRIMARY KEY, email TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS client_reviews (id TEXT PRIMARY KEY, name TEXT NOT NULL, business TEXT, rating INTEGER NOT NULL, text TEXT NOT NULL, created TEXT NOT NULL, approved INTEGER DEFAULT 1);''')
# Non-destructive migrations for earlier workspaces.
with db() as c:
    columns={r[1] for r in c.execute('PRAGMA table_info(leads)')}
    for name,kind in [('audit_status','TEXT'),('audit_reason','TEXT'),('checked_at','TEXT'),('http_code','INTEGER'),('latitude','REAL'),('longitude','REAL'),('opening_hours','TEXT'),('social_url','TEXT'),('source_tags','TEXT')]:
        if name not in columns: c.execute(f'ALTER TABLE leads ADD COLUMN {name} {kind}')
    c.execute("UPDATE jobs SET state='interrupted',message='Server restarted; start a new search to continue.' WHERE state IN ('queued','running')")
from web.services import discover_location, audit_website
from web.portfolio import SAMPLES
DEFAULTS={'sender_name':'','agency':'','reply_email':'','postal_address':'','public_base_url':'','offer':'clear, mobile-friendly websites that make it easier for customers to learn about services and get in touch'}
def settings():
    with db() as c: r=c.execute('SELECT data FROM settings WHERE id=1').fetchone()
    base={**DEFAULTS,**(json.loads(r[0]) if r else {})}
    # Env takes precedence for public URL (useful for container secrets)
    if os.getenv('PUBLIC_BASE_URL'): base['public_base_url']=os.environ['PUBLIC_BASE_URL'].rstrip('/')
    return base
def log(kind, message):
    with db() as c: c.execute('INSERT INTO activity(kind,message,created) VALUES(?,?,?)',(kind,message,now()))
def lead(lid):
    with db() as c: r=c.execute('SELECT * FROM leads WHERE id=?',(lid,)).fetchone()
    if not r: abort(404)
    return dict(r)
def classify(url):
    if not url.strip(): return 'NOT_LISTED'
    try: host=(urlparse(url if '://' in url else 'https://'+url).hostname or '').lower()
    except ValueError: return 'HAS_WEBSITE'
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
        c.execute('UPDATE leads SET source_seen_at=? WHERE source_key=?',(stamp,key))
        return count
from web.security import install_security
install_security(app,db)
from web.accounts import register_accounts
register_accounts(app,db,log)
@app.context_processor
def inject_branding():
    try: s=settings()
    except Exception: s={}
    return {'app_settings': s}
@app.before_request
def custom_domain_redirect():
    # If a custom domain is set via PUBLIC_BASE_URL (e.g. https://reachmark.co), redirect the temporary Railway host to it for SEO/canonical
    try:
        base = (os.getenv('PUBLIC_BASE_URL','').strip().rstrip('/') or settings().get('public_base_url','').strip().rstrip('/'))
        if base and base.startswith('https://') and 'up.railway.app' in request.host:
            # Only redirect if base is not the railway host itself
            if 'reachmark.co' in base or 'sitegapreveal' not in base:
                # Preserve path + query, avoid redirecting healthz via is_json etc? Keep simple: redirect all
                if request.path.startswith(('/healthz','/static/')):
                    return None
                target = base + request.full_path if request.query_string else base + request.path
                # Fix full_path includes ? already
                if request.query_string and target.endswith('?'):
                    target = base + request.path + '?' + request.query_string.decode()
                return redirect(target, code=301)
    except Exception:
        pass

@app.before_request
def same_origin():
    if request.is_json and request.method in ('POST','PATCH','PUT'):
        body=request.get_json(silent=True)
        if not isinstance(body,dict): return jsonify(error='Send a JSON object.'),400
    if request.method in ('POST','PATCH','DELETE'):
        origin=request.headers.get('Origin')
        if origin and urlparse(origin).netloc != request.host: return jsonify(error='Cross-origin request rejected.'),403
@app.after_request
def headers(r):
    if request.path.startswith(('/api/','/preview/','/unsubscribe/','/workspace','/dashboard')): r.headers['X-Robots-Tag']='noindex, nofollow'; r.headers['Cache-Control']='no-store'
    r.headers['X-Content-Type-Options']='nosniff'; r.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    return r

ADSENSE_CLIENT = os.getenv('ADSENSE_CLIENT', 'ca-pub-3894582071697384').strip()
ADSENSE_PATHS = {'/', '/about', '/showcase', '/enquire', '/receptionist'}

@app.after_request
def adsense_tags(response):
    """Serve the AdSense loader + account meta on public marketing pages.

    Injected at serve time so templates -- including about.html, which must stay
    byte-identical -- are never touched. Workspace, APIs, review links and the ad
    recording stage are excluded.
    """
    try:
        if not ADSENSE_CLIENT or request.path not in ADSENSE_PATHS:
            return response
        if 'text/html' not in response.headers.get('Content-Type', ''):
            return response
        body = response.get_data(as_text=True)
        if 'googlesyndication.com/pagead/js/adsbygoogle.js' in body:
            return response
        tags = ('\n<meta name="google-adsense-account" content="' + ADSENSE_CLIENT + '">'
                '\n<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='
                + ADSENSE_CLIENT + '" crossorigin="anonymous"></script>')
        updated, count = re.subn(r'(<head[^>]*>)', r'\g<1>' + tags, body, count=1)
        if not count:
            return response
        response.set_data(updated)
        if 'Content-Length' in response.headers:
            response.headers['Content-Length'] = str(len(response.get_data()))
    except Exception:
        pass
    return response
@app.errorhandler(413)
def too_big(e): return jsonify(error='File too large. Limit: 3 MB.'),413
@app.route('/')
def home():
    base=settings()['public_base_url'].rstrip('/')
    canonical = (base + '/') if base else None
    seo = {
        'title': 'Reachmark — Find Potential. Make Your Mark. | World-class website designer',
        'description': 'Discover businesses worldwide, verify website opportunities, and start meaningful conversations with personalized website proposals. 8 premium Figma-inspired samples, live 3D previews, OpenStreetMap discovery — no Google API key needed.',
        'keywords': 'website designer, Figma templates, 3D website previews, OpenStreetMap leads, business discovery, Reachmark',
        'canonical': canonical,
        'og_image': (base + '/static/social-card.png') if base else '/static/social-card.png',
        'noindex': False,
    }
    gsv = os.getenv('GOOGLE_SITE_VERIFICATION','ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg').strip() or 'ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg'
    structured=[{
        '@context':'https://schema.org','@type':'Organization','name':'Reachmark','url': base or request.url_root.rstrip('/'),
        'logo': (base or request.url_root.rstrip('/')) + '/static/icon.svg',
        'description': seo['description'], 'foundingDate':'2026', 'areaServed':'Worldwide'
    },{
        '@context':'https://schema.org','@type':'WebSite','name':'Reachmark','url': base or request.url_root.rstrip('/'),
        'potentialAction': {'@type':'SearchAction','target': (base or request.url_root.rstrip('/')) + '/showcase?q={search_term_string}', 'query-input':'required name=search_term_string'}
    },{
        '@context':'https://schema.org','@type':'BreadcrumbList','itemListElement':[
            {'@type':'ListItem','position':1,'name':'Home','item': base or request.url_root.rstrip('/')},
            {'@type':'ListItem','position':2,'name':'Website samples','item': (base or request.url_root.rstrip('/')) + '/showcase'},
            {'@type':'ListItem','position':3,'name':'Enquire','item': (base or request.url_root.rstrip('/')) + '/enquire'}
        ]
    }]
    ga_id = os.getenv('GOOGLE_ANALYTICS_ID','').strip() or 'G-CPSB1EDNFE'  # GA4 ID provided by user
    gt_id = os.getenv('GOOGLE_TAG_ID','').strip() or 'GT-M6XWG99J'  # second Google tag alongside GA4
    gtm_id = os.getenv('GOOGLE_TAG_MANAGER_ID','').strip() or 'GTM-M3SJZ8S7'  # placeholder — replace via GOOGLE_TAG_MANAGER_ID env for real GTM verification
    return render_template('home.html',base=base,structured=structured,samples=SAMPLES,seo=seo,google_verification=gsv,ga_id=ga_id,gt_id=gt_id,gtm_id=gtm_id)
@app.route('/workspace')
def workspace():
    return render_template('index.html',samples=SAMPLES)
@app.route('/dashboard')
def client_dashboard():
    return render_template('index.html',samples=SAMPLES)
@app.route('/healthz')
def healthz():
    with db() as c: c.execute('SELECT id FROM leads LIMIT 1').fetchone()
    return jsonify(status='ok',release=os.getenv('RELEASE_SHA','local'))

@app.route('/ads.txt')
def ads_txt():
    seller = ADSENSE_CLIENT[3:] if ADSENSE_CLIENT.startswith('ca-') else ADSENSE_CLIENT
    return Response('google.com, %s, DIRECT, f08c47fec0942fa0\n' % seller, mimetype='text/plain')
@app.route('/about')
def about():
    base=settings()['public_base_url'].rstrip('/')
    canonical = (base + '/about') if base else None
    seo = {
        'title': 'About Reachmark — World-class website designer | Global discovery & 3D previews',
        'description': 'Reachmark is a world-class website designer — Figma-inspired, Framer-smooth. Global OpenStreetMap discovery, honest website health checks, live 3D previews. 8 templates, crystal green design.',
        'keywords': 'about Reachmark, world-class website designer, OpenStreetMap, website health check, Figma to website',
        'canonical': canonical,
        'og_image': (base + '/static/social-card.png') if base else '/static/social-card.png',
        'noindex': False,
    }
    gsv = os.getenv('GOOGLE_SITE_VERIFICATION','ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg').strip() or 'ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg'
    structured=[{
        '@context':'https://schema.org','@type':'Organization','name':'Reachmark','url': base or request.url_root.rstrip('/'),
        'logo': (base or request.url_root.rstrip('/')) + '/static/icon.svg'
    },{
        '@context':'https://schema.org','@type':'WebSite','name':'Reachmark','url': base or request.url_root.rstrip('/'),
        'potentialAction': {'@type':'SearchAction','target': (base or request.url_root.rstrip('/')) + '/showcase?q={search_term_string}', 'query-input':'required name=search_term_string'}
    }]
    ga_id = os.getenv('GOOGLE_ANALYTICS_ID','').strip() or 'G-CPSB1EDNFE'  # GA4 ID provided by user
    gt_id = os.getenv('GOOGLE_TAG_ID','').strip() or 'GT-M6XWG99J'  # second Google tag alongside GA4
    gtm_id = os.getenv('GOOGLE_TAG_MANAGER_ID','').strip() or 'GTM-M3SJZ8S7'  # placeholder — replace via GOOGLE_TAG_MANAGER_ID env for real GTM verification
    return render_template('about.html',base=base,structured=structured,samples=SAMPLES,seo=seo,google_verification=gsv,ga_id=ga_id,gt_id=gt_id,gtm_id=gtm_id)
@app.after_request
def pwa_headers(response):
    """Let the service worker control the whole site, and never cache the worker itself."""
    if request.path == '/static/sw.js':
        response.headers['Service-Worker-Allowed'] = '/'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    elif request.path == '/static/manifest.webmanifest':
        response.headers['Content-Type'] = 'application/manifest+json'
        response.headers['Cache-Control'] = 'public, max-age=3600'
    return response


@app.route('/offline')
def offline_page():
    # Served by the service worker when a page was never visited on this device.
    return Response('''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Offline · Reachmark</title><link rel="stylesheet" href="/static/fonts.css">
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#F5F5EF;color:#20251F;font:16px/1.6 Manrope,system-ui,sans-serif;padding:24px}
main{max-width:520px;background:#fff;border:1px solid #e2e6d8;border-radius:20px;padding:32px}h1{font-size:26px;letter-spacing:-.6px;margin:0 0 10px}
p{color:#535f4c}a{color:#20251F;font-weight:700}</style></head><body><main>
<img src="/static/logo-primary.svg" alt="Reachmark" style="height:34px;margin-bottom:16px">
<h1>You are offline.</h1>
<p>This page has not been saved on this device, so there is nothing honest to show you. The
pages you have already visited still work, and nothing is ever displayed as live data when it
is not.</p>
<p>When the connection is back, <a href="/">start at the home page</a>.</p>
</main></body></html>''', mimetype='text/html')


@app.route('/robots.txt')
def robots():
    base=settings()['public_base_url'].rstrip('/') or request.url_root.rstrip('/')
    return Response('User-agent: *\nAllow: /\nAllow: /about\nAllow: /showcase\nAllow: /enquire\nAllow: /receptionist\nAllow: /static/\nAllow: /showcase/\nDisallow: /api/\nDisallow: /preview/\nDisallow: /unsubscribe/\nDisallow: /workspace\nDisallow: /dashboard\nDisallow: /*?*\nSitemap: '+base+'/sitemap.xml\n',mimetype='text/plain')
@app.route('/sitemap.xml')
def sitemap():
    from xml.sax.saxutils import escape
    from datetime import datetime, timezone
    base=settings()['public_base_url'].rstrip('/') or request.url_root.rstrip('/')
    now = datetime.now(timezone.utc).date().isoformat()
    # Core public pages + all 8 showcase samples — every indexable route for Google
    paths = ['/','/about','/showcase','/enquire','/receptionist'] + [f'/showcase/{s["slug"]}' for s in SAMPLES]
    urls = []
    for path in paths:
        loc = escape(base+path)
        # Priority & changefreq tuned for Google crawl budget
        if path == '/': pri, freq = '1.0', 'weekly'
        elif path == '/showcase': pri, freq = '0.9', 'weekly'
        elif path.startswith('/showcase/'): pri, freq = '0.8', 'monthly'
        elif path == '/enquire': pri, freq = '0.7', 'monthly'
        else: pri, freq = '0.8', 'weekly'
        urls.append(f'<url><loc>{loc}</loc><lastmod>{now}</lastmod><changefreq>{freq}</changefreq><priority>{pri}</priority></url>')
    body = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(urls) + '</urlset>'
    return Response(body, mimetype='application/xml', headers={'Cache-Control':'public, max-age=3600'})

@app.route('/<filename>')
def google_verify_file_generic(filename):
    # Google Search Console HTML file verification — serve google*.html
    # Supports both meta-token fallback and specific HTML file upload verification
    if filename.startswith('google') and filename.endswith('.html'):
        # Specific file requested by user: googlee75a778b14224ae6.html
        if filename == 'googlee75a778b14224ae6.html':
            return Response('google-site-verification: googlee75a778b14224ae6.html', mimetype='text/html')
        token = os.getenv('GOOGLE_SITE_VERIFICATION','').strip() or 'ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg'
        if token:
            return Response('google-site-verification: ' + token, mimetype='text/html')
        return Response('google-site-verification: ' + filename, mimetype='text/html')
    abort(404)
@app.route('/api/state')
def state():
    from flask import session
    is_client = bool(session.get('client_id') and session.get('role')=='client')
    with db() as c:
        if is_client:
            # Clients see no leads/jobs; they have filtered invoices/projects elsewhere
            leads=[]
            activity=[]
            sent=0
            suppressed=[]
            enquiry_count=0
            jobs=[]
        else:
            leads=[dict(r) for r in c.execute("SELECT l.*,r.verification,r.reviewed_at FROM leads l LEFT JOIN lead_reviews r ON r.lead_id=l.id ORDER BY l.created DESC")]
            activity=[dict(r) for r in c.execute('SELECT * FROM activity ORDER BY id DESC LIMIT 12')]
            sent=c.execute("SELECT count(*) FROM sends WHERE state='sent'").fetchone()[0]
            suppressed=[r[0] for r in c.execute('SELECT email FROM suppression')]
            enquiry_count=c.execute("SELECT count(*) FROM enquiries WHERE status='New'").fetchone()[0]
            jobs=[dict(r) for r in c.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 15')]
    role='client' if is_client else 'owner' if session.get('owner') else 'none'
    return jsonify(leads=leads,enquiry_count=enquiry_count,jobs=jobs,activity=activity,sent=sent,settings=settings(),categories=list(CATEGORIES),smtp_ready=bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM')),suppressed=suppressed,role=role)
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
            with db() as c:c.execute('DELETE FROM lead_reviews WHERE lead_id=?',(lid,))
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
    if not city or len(city)>150 or not isinstance(category,str) or category not in CATEGORIES: return jsonify(error='Choose a location and category.'),400
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
    if not isinstance(locations,list) or not 1<=len(locations)<=8 or any(not isinstance(x,str) or not x.strip() or len(x)>150 for x in locations) or not isinstance(category,str) or category not in CATEGORIES: return jsonify(error='Enter 1–8 city/country locations and a supported category.'),400
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

from web.readiness import register_readiness
register_readiness(app)
from web.workflow import register_workflow
register_workflow(app,db,now,log)
from web.invoices import register_invoices
register_invoices(app,db,now,log)
from web.documents import register_documents
register_documents(app,db,now,settings)
from web.maps import register_maps
register_maps(app, db, now, add_lead, CATEGORIES)
from web.enquiries import register_enquiries
register_enquiries(app, db, now, log)
from web.operations import register_operations
register_operations(app, db, now, log)
from web.standard import register_standard
register_standard(app, db, log, settings)

# --- Reachmark AI crew: agents, quick review links and the AI receptionist ---
from crew.crew import register_crew
crew = register_crew(app, db, now, log, settings, add_lead, CATEGORIES)
from web.review_links import register_review_links
register_review_links(app, db, now, log, settings)
from web.receptionist import register_receptionist
register_receptionist(app, db, now, log, settings)


# Client reviews — leave a review for good job done
@app.route('/api/client-reviews', methods=['GET'])
def list_client_reviews():
    with db() as c:
        rows = [dict(r) for r in c.execute('SELECT * FROM client_reviews WHERE approved=1 ORDER BY created DESC LIMIT 50')]
    return jsonify(rows)

@app.route('/api/client-reviews', methods=['POST'])
def create_client_review():
    d = request.get_json() or {}
    name = str(d.get('name','')).strip()[:80]
    business = str(d.get('business','')).strip()[:120]
    rating = d.get('rating')
    text = str(d.get('text','')).strip()[:800]
    if not name or not text or not isinstance(rating, int) or rating not in (1,2,3,4,5):
        return jsonify(error='Name, 1-5 rating and review text are required.'), 400
    if len(text) < 12:
        return jsonify(error='Review text should be at least 12 characters.'), 400
    rid = __import__('uuid').uuid4().hex
    created = now()
    with db() as c:
        c.execute('INSERT INTO client_reviews VALUES(?,?,?,?,?,?,1)', (rid, name, business, rating, text, created))
    log('review', f'New client review from {name} ({rating}★)')
    return jsonify(ok=True, id=rid), 201

@app.route('/reviews')
def reviews_page():
    base=settings()['public_base_url'].rstrip('/')
    structured={'@context':'https://schema.org','@type':'CollectionPage','name':'Client Reviews — Reachmark'}
    if base: structured['url']=base+'/reviews'
    with db() as c:
        revs=[dict(r) for r in c.execute('SELECT * FROM client_reviews WHERE approved=1 ORDER BY created DESC LIMIT 50')]
    return render_template('about.html', base=base, structured=structured, samples=SAMPLES, client_reviews=revs)


if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','8000')),debug=False)
