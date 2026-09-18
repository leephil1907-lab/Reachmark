"""Evidence-based lead review, duplicate candidates and a manual client project board."""
import re,uuid,itertools,unicodedata
from urllib.parse import urlsplit
from collections import defaultdict
from datetime import date,datetime
from flask import request,jsonify,abort
from operations import CURRENCIES,money
STAGES=['Discover','Verify','Preview','Proposal','Agreement','Build','Delivered','On hold']
VERIFICATIONS={'UNREVIEWED','WORKING','LISTED_URL_UNAVAILABLE','NO_SITE_FOUND','INCONCLUSIVE'}
def normalized(text):return re.sub(r'\W+','',unicodedata.normalize('NFKC',text or '').casefold())
def duplicates(leads):
    groups=defaultdict(list)
    for l in leads:
        keys=[];phone=re.sub(r'\D','',l.get('phone') or '');name=normalized(l['name']);city=normalized(l.get('city'));address=normalized(l.get('address'))
        if len(phone)>=8:keys.append(('Matching phone',phone))
        if l.get('email'):keys.append(('Matching email',l['email'].strip().casefold()))
        if name and city:keys.append(('Matching name and city',name+'|'+city))
        if name and address:keys.append(('Matching name and address',name+'|'+address))
        for key in keys:groups[key].append(l['id'])
    pairs=defaultdict(set);truncated=False
    for (reason,key),ids in groups.items():
        if len(ids)>30:truncated=True
        for a,b in itertools.combinations(sorted(ids)[:30],2):
            if len(pairs)>=200 and (a,b) not in pairs:truncated=True;continue
            pairs[(a,b)].add(reason)
    return [{'first':a,'second':b,'reasons':sorted(reasons)} for (a,b),reasons in pairs.items()],truncated

def register_workflow(app,db,now,log):
    with db() as c:
        if 'source_seen_at' not in {r[1] for r in c.execute('PRAGMA table_info(leads)')}:
            c.execute('ALTER TABLE leads ADD COLUMN source_seen_at TEXT');c.execute('UPDATE leads SET source_seen_at=created')
        c.executescript('''CREATE TABLE IF NOT EXISTS lead_reviews(lead_id TEXT PRIMARY KEY,verification TEXT,note TEXT,evidence_url TEXT,reviewed_at TEXT);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,title TEXT,lead_id TEXT,contract_id TEXT,stage TEXT,next_action TEXT,due_date TEXT,scope TEXT,currency TEXT,quote_minor INTEGER,created TEXT,updated TEXT);''')
        # Migration for client assignment
        proj_cols={r[1] for r in c.execute('PRAGMA table_info(projects)')}
        if 'client_user_id' not in proj_cols:
            try:
                c.execute('ALTER TABLE projects ADD COLUMN client_user_id TEXT')
            except Exception:
                pass
    @app.get('/api/quality')
    def quality():
        with db() as c:
            leads=[dict(r) for r in c.execute('SELECT id,name,city,address,phone,email FROM leads')]
            reviews=[dict(r) for r in c.execute('SELECT * FROM lead_reviews WHERE lead_id IN (SELECT id FROM leads)')]
        pairs,truncated=duplicates(leads)
        return jsonify(duplicates=pairs,truncated=truncated,reviews=reviews)
    @app.post('/api/leads/<lid>/review')
    def save_review(lid):
        v=request.get_json();status=v.get('verification');note=v.get('note','');url=v.get('evidence_url','')
        if not isinstance(status,str) or status not in VERIFICATIONS or not isinstance(note,str) or not isinstance(url,str) or len(note)>3000 or len(url)>1000:return jsonify(error='Provide a supported review state, notes and an evidence URL.'),400
        try:
            parsed=urlsplit(url)
            validurl=not url or (parsed.scheme in ('http','https') and parsed.hostname and not parsed.username and not parsed.password)
        except ValueError:validurl=False
        if not validurl:return jsonify(error='Evidence must be a valid HTTP(S) URL.'),400
        if status not in ('UNREVIEWED','INCONCLUSIVE') and (len(note.strip())<20 or not url):return jsonify(error='Add an evidence URL and at least 20 characters describing your manual research. Automated failures are not confirmation.'),400
        with db() as c:
            if not c.execute('SELECT id FROM leads WHERE id=?',(lid,)).fetchone():abort(404)
            c.execute('INSERT OR REPLACE INTO lead_reviews VALUES(?,?,?,?,?)',(lid,status,note.strip(),url.strip(),now()))
        log('review','Manual business verification recorded');return jsonify(ok=True)
    @app.get('/api/projects')
    def list_projects():
        from flask import session
        with db() as c:
            rows=[dict(r) for r in c.execute('SELECT p.*,u.email as client_email FROM projects p LEFT JOIN users u ON u.id=p.client_user_id ORDER BY p.updated DESC')]
        if session.get('client_id') and session.get('role')=='client' and not session.get('owner'):
            cid=session.get('client_id')
            user_email=None
            with db() as cc:
                r=cc.execute('SELECT email FROM users WHERE id=?',(cid,)).fetchone()
                user_email=r['email'].lower() if r else None
            filtered=[]
            for p in rows:
                if p.get('client_user_id')==cid:
                    filtered.append(p)
                elif not p.get('client_user_id') and p.get('lead_id') and user_email:
                    with db() as cc2:
                        lead=cc2.execute('SELECT email FROM leads WHERE id=?',(p['lead_id'],)).fetchone()
                        if lead and lead['email'] and lead['email'].strip().lower()==user_email:
                            filtered.append(p)
            rows=filtered
        return jsonify(projects=rows,stages=STAGES,currencies=CURRENCIES,today=date.today().isoformat())
    @app.route('/api/projects',methods=['POST'])
    @app.route('/api/projects/<pid>',methods=['PATCH','DELETE'])
    def project_write(pid=None):
        from flask import session
        # Clients cannot create/modify projects
        if request.method in ('POST','PATCH','DELETE') and session.get('client_id') and not session.get('owner'):
            return jsonify(error='Only the studio owner can manage projects.'),403
        if request.method=='DELETE':
            with db() as c:c.execute('DELETE FROM projects WHERE id=?',(pid,))
            log('project','A project record was deleted');return jsonify(ok=True)
        v=request.get_json();fields=['title','lead_id','contract_id','stage','next_action','due_date','scope','currency','client_user_id','client_email']
        if any(not isinstance(v.get(k,''),str) for k in fields if k in v):return jsonify(error='Project fields must be text.'),400
        title=v.get('title','').strip();stage=v.get('stage','Discover');currency=v.get('currency','USD');due=v.get('due_date','');lead=v.get('lead_id','');contract=v.get('contract_id','')
        if not title or len(title)>180 or stage not in STAGES or currency not in CURRENCIES or len(v.get('scope',''))>10000 or len(v.get('next_action',''))>500:return jsonify(error='Provide a title, supported stage/currency and bounded scope.'),400
        # Resolve client assignment: accept client_email or client_user_id
        client_user_id=str(v.get('client_user_id','')).strip() or None
        client_email=str(v.get('client_email','')).strip().lower() or None
        if client_email and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',client_email):
            return jsonify(error='Enter a valid client email.'),400
        if client_email and not client_user_id:
            with db() as c:
                u=c.execute('SELECT id FROM users WHERE lower(email)=lower(?)',(client_email,)).fetchone()
                if u:
                    client_user_id=u['id']
        if client_user_id:
            with db() as c:
                if not c.execute('SELECT 1 FROM users WHERE id=? AND role=\"client\"',(client_user_id,)).fetchone():
                    return jsonify(error='Client account not found.'),400
        try:
            if due and (not re.fullmatch(r'\d{4}-\d{2}-\d{2}',due) or date.fromisoformat(due).isoformat()!=due):raise ValueError()
            quote=money(v.get('quote'),currency,optional=True)
        except ValueError:return jsonify(error='Enter a valid date and non-negative quote amount, or leave them blank.'),400
        # Preserve existing client assignment if not explicitly changed
        if pid:
            with db() as cc:
                existing=cc.execute('SELECT client_user_id FROM projects WHERE id=?',(pid,)).fetchone()
                if existing and 'client_user_id' not in v and 'client_email' not in v:
                    client_user_id=existing['client_user_id']
        with db() as c:
            old=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone() if pid else None
            if pid and not old:abort(404)
            if lead and not c.execute('SELECT 1 FROM leads WHERE id=?',(lead,)).fetchone():return jsonify(error='Linked business not found.'),400
            if contract and not c.execute('SELECT 1 FROM contracts WHERE id=?',(contract,)).fetchone():return jsonify(error='Linked contract not found.'),400
            pid=pid or uuid.uuid4().hex;stamp=now()
            # Explicit column list avoids ordering issues after migration
            try:
                c.execute('INSERT OR REPLACE INTO projects(id,title,lead_id,contract_id,stage,next_action,due_date,scope,currency,quote_minor,created,updated,client_user_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(pid,title,lead,contract,stage,v.get('next_action','').strip(),due,v.get('scope','').strip(),currency,quote,old['created'] if old else stamp,stamp,client_user_id))
            except Exception as e:
                # Fallback for very old DBs without client column
                if 'no column named client_user_id' in str(e) or 'has no column' in str(e):
                    c.execute('INSERT OR REPLACE INTO projects(id,title,lead_id,contract_id,stage,next_action,due_date,scope,currency,quote_minor,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(pid,title,lead,contract,stage,v.get('next_action','').strip(),due,v.get('scope','').strip(),currency,quote,old['created'] if old else stamp,stamp))
                else:
                    raise
        log('project',f'Project saved: {title} · {stage}')
        return jsonify(id=pid),200 if old else 201
