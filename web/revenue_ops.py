"""Reachmark Digital revenue-operations APIs."""
from flask import jsonify, request, session
import os, uuid

def register_revenue_ops(app, db, now, log):
    with db() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS revenue_workflows(id TEXT PRIMARY KEY,owner_user_id TEXT NOT NULL,name TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',created TEXT NOT NULL,updated TEXT NOT NULL);CREATE TABLE IF NOT EXISTS revenue_workflow_steps(id TEXT PRIMARY KEY,workflow_id TEXT NOT NULL,position INTEGER NOT NULL,channel TEXT NOT NULL,action TEXT NOT NULL,delay_minutes INTEGER NOT NULL DEFAULT 0,requires_consent INTEGER NOT NULL DEFAULT 0,config TEXT NOT NULL,UNIQUE(workflow_id,position));CREATE INDEX IF NOT EXISTS idx_revenue_workflows_owner ON revenue_workflows(owner_user_id);CREATE INDEX IF NOT EXISTS idx_revenue_steps_workflow ON revenue_workflow_steps(workflow_id,position);""")
    def actor():
        if session.get('role') == 'client' and session.get('client_id'): return str(session['client_id'])
        if session.get('owner'): return 'owner'
        return None
    def owner_clause(): return 'owner_user_id=?'
    @app.get('/api/revenue/summary')
    def revenue_summary():
        owner=actor()
        if not owner: return jsonify(error='Authentication required'),401
        with db() as c:
            q=lambda sql:c.execute(sql,(owner,)).fetchone()['n']
            lead_count=q('SELECT count(*) n FROM leads WHERE owner_user_id=?'); new_count=q("SELECT count(*) n FROM leads WHERE owner_user_id=? AND stage='New'"); replied=q("SELECT count(*) n FROM leads WHERE owner_user_id=? AND stage='Replied'"); won=q("SELECT count(*) n FROM leads WHERE owner_user_id=? AND stage='Won'"); campaigns=q('SELECT count(*) n FROM outreach_campaigns WHERE owner_user_id=?'); active=q("SELECT count(*) n FROM outreach_campaigns WHERE owner_user_id=? AND status='active'"); gbp_locations=q('SELECT count(*) n FROM google_locations WHERE owner_user_id=?'); reviews=q('SELECT count(*) n FROM google_reviews WHERE owner_user_id=?')
            events=c.execute("SELECT count(*) n FROM outreach_events e JOIN outreach_campaigns c ON c.provider_campaign_id=e.provider_campaign_id AND c.provider=e.provider WHERE c.owner_user_id=?",(owner,)).fetchone()['n']
        return jsonify(leads=lead_count,new_leads=new_count,replied=replied,won=won,campaigns=campaigns,active_campaigns=active,outreach_events=events,google_locations=gbp_locations,google_reviews=reviews)
    @app.get('/api/revenue/conversations')
    def revenue_conversations():
        owner=actor()
        if not owner:return jsonify(error='Authentication required'),401
        with db() as c: rows=c.execute("SELECT l.id,l.name,l.email,l.phone,l.stage,l.updated,(SELECT event_type FROM outreach_events e WHERE lower(e.email)=lower(l.email) ORDER BY e.created DESC LIMIT 1) last_event FROM leads l WHERE l.owner_user_id=? ORDER BY l.updated DESC LIMIT 100",(owner,)).fetchall()
        return jsonify(conversations=[dict(r) for r in rows])
    @app.get('/api/revenue/providers')
    def revenue_providers():
        if not actor():return jsonify(error='Authentication required'),401
        return jsonify(providers={'instantly':bool(os.getenv('INSTANTLY_API_KEY','').strip()),'smartlead':bool(os.getenv('SMARTLEAD_API_KEY','').strip()),'google_business':bool(os.getenv('GOOGLE_CLIENT_ID','').strip() and os.getenv('GOOGLE_CLIENT_SECRET','').strip() and os.getenv('GOOGLE_BUSINESS_TOKEN_KEY','').strip()),'whatsapp':bool(os.getenv('WHATSAPP_ACCESS_TOKEN','').strip() and os.getenv('WHATSAPP_PHONE_NUMBER_ID','').strip()),'sms':bool(os.getenv('SMS_PROVIDER_API_KEY','').strip())})
    @app.post('/api/revenue/workflows')
    def create_workflow():
        owner=actor()
        if not owner:return jsonify(error='Authentication required'),401
        body=request.get_json(silent=True) or {}; name=str(body.get('name') or '').strip()[:160]; steps=body.get('steps')
        if not name or not isinstance(steps,list) or not steps:return jsonify(error='name and a non-empty steps array are required'),400
        allowed={'email','whatsapp','sms','linkedin','phone','task'}
        if any(not isinstance(s,dict) or s.get('channel') not in allowed for s in steps):return jsonify(error='Unsupported workflow channel'),400
        wid,stamp=uuid.uuid4().hex,now()
        with db() as c:
            c.execute('INSERT INTO revenue_workflows VALUES(?,?,?,?,?,?)',(wid,owner,name,'draft',stamp,stamp))
            for i,s in enumerate(steps,1):c.execute('INSERT INTO revenue_workflow_steps VALUES(?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,wid,i,s['channel'],str(s.get('action') or 'send'),int(s.get('delay_minutes') or 0),1 if s.get('requires_consent') else 0,str(s)))
        log('workflow',f'Created revenue workflow {name}')
        return jsonify(id=wid,name=name,steps=steps,status='draft'),201
    @app.get('/api/revenue/workflows')
    def workflows():
        owner=actor()
        if not owner:return jsonify(error='Authentication required'),401
        with db() as c:
            rows=c.execute('SELECT * FROM revenue_workflows WHERE owner_user_id=? ORDER BY updated DESC',(owner,)).fetchall(); result=[]
            for r in rows:
                ss=c.execute('SELECT position,channel,action,delay_minutes,requires_consent,config FROM revenue_workflow_steps WHERE workflow_id=? ORDER BY position',(r['id'],)).fetchall(); result.append({**dict(r),'steps':[dict(s) for s in ss]})
        return jsonify(workflows=result)
