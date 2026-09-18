"""Public project requests and a private owner inbox; no simulated submissions."""
import hashlib, os, re, uuid
from datetime import datetime, timezone, timedelta
from flask import request, jsonify, render_template, abort
from portfolio import SAMPLES, find_sample

def register_enquiries(app, db, now, log):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS enquiries (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, business TEXT,
        kind TEXT, budget TEXT, timeline TEXT, message TEXT NOT NULL, sample TEXT,
        status TEXT DEFAULT 'New', notes TEXT DEFAULT '', fingerprint TEXT, created TEXT, updated TEXT)''')
        c.execute('CREATE INDEX IF NOT EXISTS enquiry_created ON enquiries(created)')

    @app.route('/showcase')
    def showcase():
        from flask import request
        base = (lambda: __import__('app').settings()['public_base_url'].rstrip('/'))() if 'app' in __import__('sys').modules else ''
        try:
            from app import settings
            base = settings()['public_base_url'].rstrip('/')
        except: base = request.url_root.rstrip('/')
        seo = {
            'title': 'Website Samples — 8 Premium Figma-inspired designs | Reachmark',
            'description': 'Explore 8 premium Figma-inspired fictional website concepts — café, wellness, homes, clinic, law, boutique, fintech, SaaS invoice — each with a live 3D preview. Find your direction and enquire.',
            'keywords': 'website samples, Figma templates, Reachmark portfolio, 3D previews, clinic, law, boutique, fintech',
            'canonical': (base + '/showcase') if base else None,
            'og_image': (base + '/static/social-card.png') if base else '/static/social-card.png',
            'noindex': False,
        }
        gsv = os.getenv('GOOGLE_SITE_VERIFICATION','ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg').strip() or 'ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg'
        ga_id = os.getenv('GOOGLE_ANALYTICS_ID','').strip() or 'G-CPSB1EDNFE'
        gt_id = os.getenv('GOOGLE_TAG_ID','').strip() or 'GT-M6XWG99J'
        gtm_id = os.getenv('GOOGLE_TAG_MANAGER_ID','').strip() or 'GTM-M3SJZ8S7'
        structured=[{'@context':'https://schema.org','@type':'CollectionPage','name':'Website Samples — Reachmark','description': seo['description'], 'url': seo['canonical'] or request.url}]
        return render_template('showcase.html',samples=SAMPLES,seo=seo,google_verification=gsv,structured=structured,ga_id=ga_id,gt_id=gt_id,gtm_id=gtm_id)

    @app.route('/showcase/<slug>')
    def sample_site(slug):
        from flask import request
        sample=find_sample(slug)
        if not sample: abort(404)
        try:
            from app import settings
            base = settings()['public_base_url'].rstrip('/')
        except: base = request.url_root.rstrip('/')
        seo = {
            'title': f"{sample['name']} — {sample['category']} Website Sample | Reachmark",
            'description': sample['description'] + f" Fictional {sample['category'].lower()} design by Reachmark — Figma {sample['figma']}. Enquire about a similar website.",
            'keywords': f"{sample['name']}, {sample['category']}, Reachmark, {sample['figma']}, website sample",
            'canonical': (base + f"/showcase/{slug}") if base else None,
            'og_image': (base + f"/static/samples/{slug}-preview.jpg") if base else f"/static/samples/{slug}-preview.jpg",
            'noindex': False,
        }
        gsv = os.getenv('GOOGLE_SITE_VERIFICATION','ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg').strip() or 'ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg'
        ga_id = os.getenv('GOOGLE_ANALYTICS_ID','').strip() or 'G-CPSB1EDNFE'
        gt_id = os.getenv('GOOGLE_TAG_ID','').strip() or 'GT-M6XWG99J'
        gtm_id = os.getenv('GOOGLE_TAG_MANAGER_ID','').strip() or 'GTM-M3SJZ8S7'
        structured=[{'@context':'https://schema.org','@type':'CreativeWork','name': sample['name'], 'description': seo['description'], 'url': seo['canonical'] or request.url, 'image': seo['og_image']}]
        return render_template('sample-site.html',sample=sample,seo=seo,google_verification=gsv,structured=structured,ga_id=ga_id,gt_id=gt_id,gtm_id=gtm_id)

    @app.route('/enquire')
    def enquire():
        from flask import request
        slug=request.args.get('sample','')
        try:
            from app import settings
            base = settings()['public_base_url'].rstrip('/')
        except: base = request.url_root.rstrip('/')
        seo = {
            'title': 'Enquire — Start your website project | Reachmark',
            'description': 'Tell Reachmark about your business and the website you need. Choose a sample direction or describe your idea — we reply with a tailored estimate. No commitment.',
            'keywords': 'enquire Reachmark, website estimate, start project, contact studio',
            'canonical': (base + '/enquire') if base else None,
            'og_image': (base + '/static/social-card.png') if base else '/static/social-card.png',
            'noindex': False,
        }
        gsv = os.getenv('GOOGLE_SITE_VERIFICATION','ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg').strip() or 'ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg'
        ga_id = os.getenv('GOOGLE_ANALYTICS_ID','').strip() or 'G-CPSB1EDNFE'
        gt_id = os.getenv('GOOGLE_TAG_ID','').strip() or 'GT-M6XWG99J'
        gtm_id = os.getenv('GOOGLE_TAG_MANAGER_ID','').strip() or 'GTM-M3SJZ8S7'
        structured=[{'@context':'https://schema.org','@type':'ContactPage','name':'Enquire — Reachmark','description': seo['description'], 'url': seo['canonical'] or request.url}]
        return render_template('enquire.html',samples=SAMPLES,chosen_sample=slug if find_sample(slug) else '',seo=seo,google_verification=gsv,structured=structured,ga_id=ga_id,gt_id=gt_id,gtm_id=gtm_id)

    @app.route('/api/enquiries',methods=['POST'])
    def submit_enquiry():
        v=request.get_json(silent=True)
        if not isinstance(v,dict): return jsonify(error='Please submit the enquiry form.'),400
        if v.get('company_url'): return jsonify(error='Unable to accept this submission.'),400
        limits={'name':120,'email':250,'business':200,'kind':80,'budget':150,'timeline':150,'message':5000,'sample':80,'request_id':40,'project_details':3000}
        data={k:str(v.get(k,'')).strip() for k in limits}
        # Merge free-form project details into the main message so the inbox shows everything
        if data.get('project_details'):
            extra=data['project_details']
            if len(data['message'])+len(extra)+40 <= limits['message']:
                data['message']=(data['message']+"\n\n— Project details (your own words):\n"+extra).strip()
            else:
                data['message']=(data['message']+"\n\n— Project details:\n"+extra[:3000]).strip()[:5000]
        if any(len(data[k])>limits[k] for k in limits if k!='project_details') or len(data['message'])>5000: return jsonify(error='One of the fields is too long. Keep your message under 5,000 characters.'),400
        if len(data['name'])<2 or len(data['message'])<15: return jsonify(error='Please add your name and a message of at least 15 characters.'),400
        if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',data['email']): return jsonify(error='Please enter a valid email address.'),400
        if data['kind'] not in ('Website estimate','Project question','Other enquiry'): return jsonify(error='Choose an enquiry type.'),400
        if data['sample'] and not find_sample(data['sample']): return jsonify(error='Choose one of the listed samples, or no preference.'),400
        if v.get('consent') is not True: return jsonify(error='Please confirm we may contact you about this request.'),400
        rid=data['request_id']
        if rid and not re.fullmatch(r'[a-f0-9]{32}',rid): return jsonify(error='Please refresh the form and try again.'),400
        rid=rid or uuid.uuid4().hex
        stamp=now();cutoff=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
        email=data['email'].lower();fingerprint=hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            existing=c.execute('SELECT email FROM enquiries WHERE id=?',(rid,)).fetchone()
            if existing:
                if existing['email']==email: return jsonify(ok=True,reference=rid[:8].upper()),200
                return jsonify(error='Please refresh the form and try again.'),409
            if c.execute('SELECT count(*) FROM enquiries WHERE email=? AND created>?',(email,cutoff)).fetchone()[0]>=3 or c.execute('SELECT count(*) FROM enquiries WHERE fingerprint=? AND created>?',(fingerprint,cutoff)).fetchone()[0]>=30:
                return jsonify(error='Too many recent requests. Please try again later.'),429
            c.execute('INSERT INTO enquiries(id,name,email,business,kind,budget,timeline,message,sample,fingerprint,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(rid,data['name'],email,data['business'],data['kind'],data['budget'],data['timeline'],data['message'],data['sample'],fingerprint,stamp,stamp))
        log('enquiry','A new project enquiry was received')
        return jsonify(ok=True,reference=rid[:8].upper()),201

    @app.route('/api/enquiries',methods=['GET'])
    def inbox():
        with db() as c: rows=[dict(r) for r in c.execute('SELECT id,name,email,business,kind,budget,timeline,message,sample,status,notes,created,updated FROM enquiries ORDER BY created DESC')]
        return jsonify(enquiries=rows)

    @app.route('/api/enquiries/<eid>',methods=['PATCH','DELETE'])
    def update_enquiry(eid):
        with db() as c:
            if not c.execute('SELECT 1 FROM enquiries WHERE id=?',(eid,)).fetchone(): abort(404)
            if request.method=='DELETE':
                c.execute('DELETE FROM enquiries WHERE id=?',(eid,));return jsonify(ok=True)
            v=request.get_json(silent=True) or {}
            status=v.get('status');notes=v.get('notes','')
            if status not in ('New','In progress','Answered','Closed') or not isinstance(notes,str) or len(notes)>5000: return jsonify(error='Choose a valid status and keep notes under 5,000 characters.'),400
            c.execute('UPDATE enquiries SET status=?,notes=?,updated=? WHERE id=?',(status,notes,now(),eid))
        return jsonify(ok=True)
