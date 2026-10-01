"""Reachmark Digital revenue-operations APIs.

Keeps Reachmark as the source of truth across leads, outreach providers and
Google Business operations. No synthetic performance data is generated.
"""
from flask import jsonify, request, session
import os, uuid


def register_revenue_ops(app, db, now, log):
    def actor():
        if session.get('role') == 'client' and session.get('client_id'):
            return str(session['client_id'])
        if session.get('owner'):
            return 'owner'
        return None

    def owner_clause(alias=''):
        prefix = (alias + '.') if alias else ''
        return f"{prefix}owner_user_id=?"

    @app.get('/api/revenue/summary')
    def revenue_summary():
        owner = actor()
        if not owner:
            return jsonify(error='Authentication required'), 401
        with db() as c:
            lead_count = c.execute(f"SELECT count(*) n FROM leads WHERE {owner_clause()}", (owner,)).fetchone()['n']
            new_count = c.execute(f"SELECT count(*) n FROM leads WHERE {owner_clause()} AND stage='New'", (owner,)).fetchone()['n']
            replied = c.execute(f"SELECT count(*) n FROM leads WHERE {owner_clause()} AND stage='Replied'", (owner,)).fetchone()['n']
            won = c.execute(f"SELECT count(*) n FROM leads WHERE {owner_clause()} AND stage='Won'", (owner,)).fetchone()['n']
            campaigns = c.execute(f"SELECT count(*) n FROM outreach_campaigns WHERE {owner_clause()}", (owner,)).fetchone()['n']
            active = c.execute(f"SELECT count(*) n FROM outreach_campaigns WHERE {owner_clause()} AND status='active'", (owner,)).fetchone()['n']
            events = c.execute("SELECT count(*) n FROM outreach_events e JOIN outreach_campaigns c ON c.provider_campaign_id=e.provider_campaign_id AND c.provider=e.provider WHERE c.owner_user_id=?", (owner,)).fetchone()['n']
            gbp_locations = c.execute(f"SELECT count(*) n FROM google_locations WHERE {owner_clause()}", (owner,)).fetchone()['n']
            reviews = c.execute(f"SELECT count(*) n FROM google_reviews WHERE {owner_clause()}", (owner,)).fetchone()['n']
        return jsonify(leads=lead_count,new_leads=new_count,replied=replied,won=won,
                       campaigns=campaigns,active_campaigns=active,outreach_events=events,
                       google_locations=gbp_locations,google_reviews=reviews)

    @app.get('/api/revenue/conversations')
    def revenue_conversations():
        owner = actor()
        if not owner:
            return jsonify(error='Authentication required'), 401
        with db() as c:
            rows = c.execute("""SELECT l.id,l.name,l.email,l.phone,l.stage,l.updated,
                (SELECT event_type FROM outreach_events e WHERE lower(e.email)=lower(l.email)
                 ORDER BY e.created DESC LIMIT 1) AS last_event
                FROM leads l WHERE l.owner_user_id=? ORDER BY l.updated DESC LIMIT 100""", (owner,)).fetchall()
        return jsonify(conversations=[dict(r) for r in rows])

    @app.get('/api/revenue/providers')
    def revenue_providers():
        owner = actor()
        if not owner:
            return jsonify(error='Authentication required'), 401
        configured = {
            'instantly': bool(os.getenv('INSTANTLY_API_KEY','').strip()),
            'smartlead': bool(os.getenv('SMARTLEAD_API_KEY','').strip()),
            'google_business': bool(os.getenv('GOOGLE_CLIENT_ID','').strip() and os.getenv('GOOGLE_CLIENT_SECRET','').strip() and os.getenv('GOOGLE_BUSINESS_TOKEN_KEY','').strip()),
            'whatsapp': bool(os.getenv('WHATSAPP_ACCESS_TOKEN','').strip() and os.getenv('WHATSAPP_PHONE_NUMBER_ID','').strip()),
            'sms': bool(os.getenv('SMS_PROVIDER_API_KEY','').strip()),
        }
        return jsonify(providers=configured)

    @app.post('/api/revenue/workflows')
    def create_workflow():
        owner = actor()
        if not owner:
            return jsonify(error='Authentication required'), 401
        body = request.get_json(silent=True) or {}
        name = str(body.get('name') or '').strip()[:160]
        steps = body.get('steps')
        if not name or not isinstance(steps, list) or not steps:
            return jsonify(error='name and a non-empty steps array are required'), 400
        allowed = {'email','whatsapp','sms','linkedin','phone','task'}
        for step in steps:
            if not isinstance(step, dict) or step.get('channel') not in allowed:
                return jsonify(error='Unsupported workflow channel'), 400
        wid = uuid.uuid4().hex
        stamp = now()
        with db() as c:
            c.execute('INSERT INTO revenue_workflows(id,owner_user_id,name,status,created,updated) VALUES(?,?,?,?,?,?)',(wid,owner,name,'draft',stamp,stamp))
            for i,step in enumerate(steps,1):
                c.execute('INSERT INTO revenue_workflow_steps(id,workflow_id,position,channel,action,delay_minutes,requires_consent,config) VALUES(?,?,?,?,?,?,?,?)',
                          (uuid.uuid4().hex,wid,i,step['channel'],str(step.get('action') or 'send'),int(step.get('delay_minutes') or 0),1 if step.get('requires_consent') else 0,str(step)))
        log('workflow', f'Created revenue workflow {name}')
        return jsonify(id=wid,name=name,steps=steps,status='draft'),201

    @app.get('/api/revenue/workflows')
    def workflows():
        owner = actor()
        if not owner:
            return jsonify(error='Authentication required'), 401
        with db() as c:
            rows=c.execute('SELECT * FROM revenue_workflows WHERE owner_user_id=? ORDER BY updated DESC',(owner,)).fetchall()
            result=[]
            for row in rows:
                steps=c.execute('SELECT position,channel,action,delay_minutes,requires_consent,config FROM revenue_workflow_steps WHERE workflow_id=? ORDER BY position',(row['id'],)).fetchall()
                result.append({**dict(row),'steps':[dict(s) for s in steps]})
        return jsonify(workflows=result)
