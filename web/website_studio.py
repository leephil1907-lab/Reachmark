"""Prompt-driven, revisioned Reachmark Website Studio."""
import json,re,uuid
from flask import jsonify,request,session,Response,abort

def register_website_studio(app,db,now,log):
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS website_studio_projects(
        id TEXT PRIMARY KEY,title TEXT NOT NULL,prompt TEXT NOT NULL,site_data TEXT NOT NULL,
        theme TEXT NOT NULL DEFAULT 'editorial',status TEXT NOT NULL DEFAULT 'draft',slug TEXT UNIQUE,
        revision INTEGER NOT NULL DEFAULT 1,history TEXT NOT NULL DEFAULT '[]',
        created TEXT NOT NULL,updated TEXT NOT NULL,published_at TEXT)""")
    themes={
      'editorial':('#f6f3ec','#17211b','#c9f06a','#657067','Georgia,serif'),
      'midnight':('#11131b','#f7f7fb','#b4a1ff','#a2a4b7','Arial,sans-serif'),
      'ocean':('#edf7f7','#12383e','#72d6ce','#4b7479','Arial,sans-serif'),
      'terracotta':('#fbf0e8','#34221d','#e58c68','#84695e','Arial,sans-serif'),
      'luxury':('#10100f','#f4eddf','#d6b777','#b2a795','Georgia,serif')}
    def denied():
        return None if session.get('owner') else (jsonify(error='Website Studio requires a workspace owner account.'),403)
    def clean(v,n=500): return re.sub(r'\s+',' ',str(v or '')).strip()[:n]
    def slugify(v): return re.sub(r'[^a-z0-9]+','-',clean(v,100).lower()).strip('-')[:52] or 'reachmark-site'
    def generate(prompt,title,existing=None):
        data=None
        try:
            from web.ai_provider import complete
            raw,_=complete('You are Reachmark Website Studio, a senior web designer and conversion copywriter. Return only valid JSON with title, eyebrow, headline, subheadline, primary_cta, sections (3-5 objects with heading, body, bullets array), footer. No HTML/scripts, fake reviews, fake metrics, or unverifiable claims.', 'Brief: '+clean(prompt,3000)+'\nCurrent title: '+clean(title,100)+'\nExisting site content: '+json.dumps(existing or {})[:4000]+'\nCreate or revise the site.', max_tokens=1200,temperature=.6,budget_calls=2)
            m=re.search(r'\{.*\}',raw,re.S)
            if m:data=json.loads(m.group())
        except Exception: pass
        if not isinstance(data,dict):
            business=clean(title or prompt.split('.')[0] or 'Your business',90)
            data={'title':business,'eyebrow':'A considered approach','headline':'Make your next move matter.','subheadline':'Thoughtful service, clear information, and a simpler way to get started.','primary_cta':'Get in touch','sections':[
            {'heading':'Made around your needs','body':'A clear, considered approach that puts your goals first.','bullets':['A personal, helpful experience','Clear next steps','Care in every detail']},
            {'heading':'What you can expect','body':'Useful information, dependable communication, and a service experience designed around real people.','bullets':['Straightforward guidance','Responsive support','A focus on quality']},
            {'heading':'Let’s talk about what you need','body':'Tell us a little about your goals and we will help you plan the next step.','bullets':['No-pressure conversation','A tailored recommendation','A clear way forward']}],'footer':'Thoughtfully made for the people we serve.'}
        def txt(k,fb,n):return clean(data.get(k),n) or fb
        sections=[]
        for s in (data.get('sections') if isinstance(data.get('sections'),list) else [])[:5]:
            if isinstance(s,dict):
                bullets=s.get('bullets',[])
                sections.append({'heading':clean(s.get('heading'),100) or 'What we do','body':clean(s.get('body'),700) or 'Discover a more considered approach.','bullets':[clean(b,120) for b in bullets[:4] if clean(b,120)] if isinstance(bullets,list) else []})
        defaults=[{'heading':'Built around your needs','body':'A thoughtful service with clear next steps.','bullets':['Personal guidance','Clear communication','Practical solutions']},{'heading':'A simpler experience','body':'Useful information to help you decide what comes next.','bullets':['Helpful information','Responsive support','Quality-focused work']},{'heading':'Start a conversation','body':'Tell us what you need and we will help you plan the next step.','bullets':['No-pressure discussion','Tailored guidance','Clear expectations']}]
        sections=(sections+defaults)[:max(3,len(sections))]
        return {'title':txt('title',clean(title,90) or 'Your new website',90),'eyebrow':txt('eyebrow','A considered approach',100),'headline':txt('headline','Make your next move matter.',150),'subheadline':txt('subheadline','A better experience starts here.',500),'primary_cta':txt('primary_cta','Get in touch',60),'sections':sections[:5],'footer':txt('footer','Thoughtfully made for the people we serve.',220),'brief':clean(prompt,3000)}
    def project(r):
        d=dict(r)
        for k in ('site_data','history'):
            try:d[k]=json.loads(d.get(k) or ('{}' if k=='site_data' else '[]'))
            except Exception:d[k]={} if k=='site_data' else []
        return d
    @app.route('/api/website-studio/projects',methods=['GET','POST'])
    def ws_projects():
        no=denied()
        if no:return no
        if request.method=='GET':
            with db() as c: rows=[project(r) for r in c.execute('SELECT * FROM website_studio_projects ORDER BY updated DESC LIMIT 100')]
            try:
                from web.ai_provider import provider_status
                ai=provider_status()['configured']
            except Exception:ai=False
            return jsonify(projects=rows,themes=list(themes),ai_available=ai)
        d=request.get_json(silent=True) or {}; prompt=clean(d.get('prompt'),3000); title=clean(d.get('title'),100) or 'Untitled website'; theme=d.get('theme') if d.get('theme') in themes else 'editorial'
        if len(prompt)<8:return jsonify(error='Give the studio a little more detail (at least 8 characters).'),400
        data=generate(prompt,title); pid=uuid.uuid4().hex; stamp=now()
        with db() as c:
            c.execute('INSERT INTO website_studio_projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(pid,data['title'],prompt,json.dumps(data),theme,'draft',None,1,'[]',stamp,stamp,None))
            r=c.execute('SELECT * FROM website_studio_projects WHERE id=?',(pid,)).fetchone()
        log('website_studio','Website draft created: '+data['title'])
        return jsonify(project=project(r)),201
    @app.route('/api/website-studio/projects/<pid>',methods=['GET','PATCH','DELETE'])
    def ws_project(pid):
        no=denied()
        if no:return no
        with db() as c:r=c.execute('SELECT * FROM website_studio_projects WHERE id=?',(pid,)).fetchone()
        if not r:return jsonify(error='Website project not found.'),404
        old=project(r)
        if request.method=='GET':return jsonify(project=old)
        if request.method=='DELETE':
            if old['status']=='published':return jsonify(error='Unpublish this website before deleting its project.'),409
            with db() as c:c.execute('DELETE FROM website_studio_projects WHERE id=?',(pid,))
            return jsonify(ok=True)
        d=request.get_json(silent=True) or {}; action=clean(d.get('action'),30); stamp=now(); data=old['site_data']; history=old['history']
        if action=='revise':
            prompt=clean(d.get('prompt'),3000)
            if len(prompt)<4:return jsonify(error='Describe the change you want to make.'),400
            data=generate(prompt,old['title'],data); history=(history[-19:]+[{'revision':old['revision'],'site_data':old['site_data'],'created':old['updated'],'note':'Before AI revision'}])
            with db() as c:
                c.execute('UPDATE website_studio_projects SET title=?,prompt=?,site_data=?,revision=revision+1,history=?,updated=? WHERE id=?',(data['title'],prompt,json.dumps(data),json.dumps(history),stamp,pid))
                r=c.execute('SELECT * FROM website_studio_projects WHERE id=?',(pid,)).fetchone()
            log('website_studio','Website revised: '+data['title']);return jsonify(project=project(r))
        if action=='restore':
            try:v=history[int(d.get('history_index',-1))]
            except Exception:return jsonify(error='No earlier revision is available.'),400
            history=history[-19:]+[{'revision':old['revision'],'site_data':data,'created':stamp,'note':'Before restore'}];data=v['site_data']
        elif action=='save':
            for k,n in [('title',90),('eyebrow',100),('headline',150),('subheadline',500),('primary_cta',60),('footer',220)]:
                if k in d:data[k]=clean(d[k],n)
            if isinstance(d.get('sections'),list):
                data['sections']=[{'heading':clean(s.get('heading'),100),'body':clean(s.get('body'),700),'bullets':[clean(b,120) for b in s.get('bullets',[])[:4] if clean(b,120)]} for s in d['sections'][:5] if isinstance(s,dict)]
                if len(data['sections'])<3:return jsonify(error='Keep at least three content sections.'),400
            history=history[-19:]+[{'revision':old['revision'],'site_data':old['site_data'],'created':old['updated'],'note':'Before manual edit'}]
        elif action=='publish':
            slug=slugify(d.get('slug') or old['title'])
            with db() as c:
                if c.execute('SELECT id FROM website_studio_projects WHERE slug=? AND id<>?',(slug,pid)).fetchone():slug+='-'+pid[:6]
                c.execute("UPDATE website_studio_projects SET status='published',slug=?,published_at=?,updated=? WHERE id=?",(slug,stamp,stamp,pid))
                r=c.execute('SELECT * FROM website_studio_projects WHERE id=?',(pid,)).fetchone()
            log('website_studio','Website published: '+old['title']);return jsonify(project=project(r),url='/sites/'+slug)
        elif action=='unpublish':
            with db() as c:
                c.execute("UPDATE website_studio_projects SET status='draft',slug=NULL,updated=? WHERE id=?",(stamp,pid))
                r=c.execute('SELECT * FROM website_studio_projects WHERE id=?',(pid,)).fetchone()
            return jsonify(project=project(r))
        elif action not in ('save','restore'):return jsonify(error='Unknown studio action.'),400
        with db() as c:
            c.execute('UPDATE website_studio_projects SET title=?,site_data=?,revision=revision+1,history=?,updated=? WHERE id=?',(data.get('title',old['title']),json.dumps(data),json.dumps(history),stamp,pid))
            r=c.execute('SELECT * FROM website_studio_projects WHERE id=?',(pid,)).fetchone()
        return jsonify(project=project(r))
    def e(v):
        return str(v or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;').replace("'","&#39;")
    @app.route('/sites/<slug>')
    def ws_published(slug):
        with db() as c:r=c.execute("SELECT * FROM website_studio_projects WHERE slug=? AND status='published'",(slug,)).fetchone()
        if not r:abort(404)
        p=project(r);d=p['site_data'];bg,ink,accent,muted,font=themes.get(p['theme'],themes['editorial']);sections=''
        for i,s in enumerate(d.get('sections',[])):
            bullets=''.join('<li>'+e(b)+'</li>' for b in s.get('bullets',[]))
            sections+='<section class="section"><div class="num">0'+str(i+1)+'</div><div><h2>'+e(s.get('heading'))+'</h2><p>'+e(s.get('body'))+'</p><ul>'+bullets+'</ul></div></section>'
        html='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="'+e(d.get('subheadline'))+'"><title>'+e(d.get('title'))+'</title><style>*{box-sizing:border-box}body{margin:0;background:'+bg+';color:'+ink+';font-family:'+font+';line-height:1.6}.wrap{max-width:1120px;margin:auto;padding:0 7vw}.nav{display:flex;justify-content:space-between;padding:28px 0;border-bottom:1px solid '+ink+'22;font:600 11px Arial;letter-spacing:.08em;text-transform:uppercase}.mark{display:inline-grid;place-items:center;width:27px;height:27px;background:'+accent+';margin-right:10px}.hero{padding:clamp(70px,13vw,150px) 0 95px;max-width:900px}.eyebrow,.num{font:700 11px Arial;letter-spacing:.18em;text-transform:uppercase;color:'+muted+'}h1{font-size:clamp(48px,8vw,100px);line-height:.98;letter-spacing:-.065em;margin:22px 0 28px}.hero p{font:18px/1.8 Arial;max-width:650px;color:'+muted+'}.cta{display:inline-block;margin-top:22px;padding:15px 22px;background:'+accent+';color:'+ink+';text-decoration:none;font:700 12px Arial}.section{display:grid;grid-template-columns:1fr 2fr;gap:36px;padding:54px 0;border-top:1px solid '+ink+'22}.section h2{font-size:clamp(27px,4vw,44px);line-height:1.1;margin:0 0 18px}.section p,.section li{font:16px/1.8 Arial;color:'+muted+'}footer{margin-top:70px;padding:40px 0;border-top:1px solid '+ink+'22;font:12px Arial;color:'+muted+'}@media(max-width:650px){.section{grid-template-columns:1fr;gap:14px}.hero{padding:75px 0}.wrap{padding:0 22px}}</style></head><body><div class="wrap"><nav class="nav"><span><i class="mark">R</i>'+e(d.get('title'))+'</span><span>'+e(d.get('eyebrow'))+'</span></nav><main><section class="hero"><div class="eyebrow">'+e(d.get('eyebrow'))+'</div><h1>'+e(d.get('headline'))+'</h1><p>'+e(d.get('subheadline'))+'</p><a class="cta" href="mailto:hello@reachmarkdigital.xyz">'+e(d.get('primary_cta'))+' ↗</a></section>'+sections+'</main><footer>'+e(d.get('footer'))+' · Built with Reachmark Website Studio</footer></div></body></html>'
        return Response(html,mimetype='text/html',headers={'X-Content-Type-Options':'nosniff','X-Robots-Tag':'index, follow'})
