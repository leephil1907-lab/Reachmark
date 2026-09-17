"""MCP connections, reviewed skills, manual contracts, and source-backed analytics."""
import os, json, uuid, re, hashlib, time
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from collections import Counter, defaultdict
from flask import request, jsonify, abort, Response
from jsonschema import validators, ValidationError, SchemaError
from mcp_transport import MCPClient, MCPError, validate_endpoint

CURRENCIES={'USD':2,'EUR':2,'GBP':2,'CAD':2,'NGN':2,'AUD':2,'JPY':0,'INR':2,'AED':2,'SGD':2,'ZAR':2,'GHS':2,'BRL':2}
STAGES=['Draft','Sent','Signed','In progress','Completed','Cancelled']

def digest(tool): return hashlib.sha256(json.dumps(tool,sort_keys=True).encode()).hexdigest()
def safe_schema(schema):
    if isinstance(schema,dict):
        for key in ('$ref','$dynamicRef','$recursiveRef'):
            if key in schema and not str(schema[key]).startswith('#'): raise ValueError('External schema references are not supported.')
        for v in schema.values(): safe_schema(v)
    elif isinstance(schema,list):
        for v in schema: safe_schema(v)
def validate_args(tool,args):
    if not isinstance(args,dict): raise ValueError('Tool arguments must be a JSON object.')
    schema=tool.get('inputSchema',{'type':'object'})
    safe_schema(schema)
    try:
        cls=validators.validator_for(schema);cls.check_schema(schema);cls(schema).validate(args)
    except (ValidationError,SchemaError) as e: raise ValueError('Arguments do not match the tool schema: '+str(e.message)[:300])
    except Exception: raise ValueError('The provider schema could not be resolved safely. Review it or use a different tool.')

def money(value,currency,optional=False):
    if optional and (value is None or str(value).strip()==''): return None
    try:
        n=Decimal(str(value or '0'));factor=10**CURRENCIES[currency]
        if not n.is_finite() or n<0 or n>Decimal('1000000000000') or n*factor!=(n*factor).to_integral_value(): raise ValueError()
        return int(n*factor)
    except (InvalidOperation,ValueError): raise ValueError('Enter a non-negative amount with the correct decimal places for the currency.')

def register_operations(app,db,now,log):
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS mcp_connectors(id TEXT PRIMARY KEY,name TEXT,url TEXT,token_env TEXT,status TEXT,tools TEXT DEFAULT '[]',server TEXT DEFAULT '{}',error TEXT DEFAULT '',checked_at TEXT,created TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS mcp_skills(id TEXT PRIMARY KEY,name TEXT,description TEXT,connector_id TEXT,tool_name TEXT,arguments TEXT,created TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS mcp_runs(id TEXT PRIMARY KEY,connector_id TEXT,connector_name TEXT,tool_name TEXT,skill_id TEXT,status TEXT,arguments TEXT,result TEXT,error TEXT,duration_ms INTEGER,created TEXT,finished TEXT);
        CREATE TABLE IF NOT EXISTS contracts(id TEXT PRIMARY KEY,title TEXT,client TEXT,email TEXT,lead_id TEXT,currency TEXT,amount_minor INTEGER,paid_minor INTEGER DEFAULT 0,status TEXT,notes TEXT,signed_recorded_at TEXT,created TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS usage_events(id INTEGER PRIMARY KEY,event TEXT,page TEXT,created TEXT);
        CREATE INDEX IF NOT EXISTS usage_created ON usage_events(created);''')
        c.execute("UPDATE mcp_runs SET status='unknown',error='Server restarted during this run. Check the provider before retrying.' WHERE status='running'")
        c.execute('INSERT INTO usage_events(event,page,created) SELECT ?,?,? WHERE NOT EXISTS(SELECT 1 FROM usage_events WHERE event=?)',('measurement_started','system',now(),'measurement_started'))

    def connector(cid):
        with db() as c: r=c.execute('SELECT * FROM mcp_connectors WHERE id=?',(cid,)).fetchone()
        if not r: abort(404)
        return dict(r)
    def client_for(conn):
        token=os.getenv(conn['token_env'],'') if conn['token_env'] else ''
        if conn['token_env'] and not os.getenv('DASHBOARD_PASSWORD'): raise MCPError('Set DASHBOARD_PASSWORD before connecting an authenticated MCP service.')
        if conn['token_env'] and not token: raise MCPError('The selected server-side token variable is not configured. Add it in the host environment and restart.')
        return MCPClient(conn['url'],token)
    def clean_tools(tools):
        result=[];names=set()
        for tool in tools:
            if not isinstance(tool,dict) or not isinstance(tool.get('name'),str) or not tool['name'] or len(tool['name'])>256: raise MCPError('Server returned a malformed tool name.')
            if tool['name'] in names: continue
            names.add(tool['name'])
            result.append({k:tool[k] for k in ('name','title','description','inputSchema','annotations') if k in tool})
        return result

    @app.route('/api/mcp')
    def mcp_state():
        with db() as c:
            connectors=[dict(r) for r in c.execute('SELECT * FROM mcp_connectors ORDER BY created DESC')]
            skills=[dict(r) for r in c.execute('SELECT * FROM mcp_skills ORDER BY created DESC')]
            runs=[dict(r) for r in c.execute('SELECT id,connector_id,connector_name,tool_name,skill_id,status,error,duration_ms,created,finished FROM mcp_runs ORDER BY created DESC LIMIT 50')]
        for con in connectors:
            con['tools']=json.loads(con['tools']);con['server']=json.loads(con['server']);con['token_ready']=bool(os.getenv(con['token_env'])) if con['token_env'] else True
            for tool in con['tools']: tool['digest']=digest(tool)
        for skill in skills: skill['arguments']=json.loads(skill['arguments'])
        return jsonify(connectors=connectors,skills=skills,runs=runs)

    @app.route('/api/mcp/connectors',methods=['POST'])
    def add_connector():
        v=request.get_json(silent=True) or {};name=str(v.get('name','')).strip();url=str(v.get('url','')).strip();env=str(v.get('token_env','')).strip()
        try: validate_endpoint(url)
        except MCPError as e:return jsonify(error=str(e)),400
        if not name or len(name)>100 or len(url)>1500 or (env and not re.fullmatch(r'MCP_TOKEN_[A-Z0-9_]{1,80}',env)): return jsonify(error='Provide a name and, optionally, a dedicated environment variable such as MCP_TOKEN_DESIGN. Never enter a token itself.'),400
        cid=uuid.uuid4().hex
        with db() as c: c.execute('INSERT INTO mcp_connectors(id,name,url,token_env,status,created,updated) VALUES(?,?,?,?,?,?,?)',(cid,name,url,env,'Not tested',now(),now()))
        log('connector','MCP connector added: '+name);return jsonify(id=cid),201

    @app.route('/api/mcp/connectors/<cid>',methods=['DELETE'])
    def remove_connector(cid):
        connector(cid)
        with db() as c:
            if c.execute("SELECT 1 FROM mcp_runs WHERE connector_id=? AND status='running'",(cid,)).fetchone(): return jsonify(error='Wait for this connector’s active run to finish.'),409
            c.execute('DELETE FROM mcp_connectors WHERE id=?',(cid,));c.execute('DELETE FROM mcp_skills WHERE connector_id=?',(cid,))
        return jsonify(ok=True)

    @app.route('/api/mcp/connectors/<cid>/sync',methods=['POST'])
    def sync_connector(cid):
        conn=connector(cid)
        try:
            client=client_for(conn);server=client.initialize();tools=clean_tools(client.list_tools());tools_json=client.redact(json.dumps(tools));server_json=client.redact(json.dumps(server))
            with db() as c: c.execute("UPDATE mcp_connectors SET tools=?,server=?,status='Connected',error='',checked_at=?,updated=? WHERE id=?",(tools_json,server_json,now(),now(),cid))
            log('connector',f'MCP discovery completed: {conn["name"]} · {len(tools)} tools')
            return jsonify(ok=True,count=len(tools))
        except MCPError as e:
            with db() as c: c.execute("UPDATE mcp_connectors SET status='Connection failed',error=?,checked_at=?,updated=? WHERE id=?",(str(e)[:600],now(),now(),cid))
            return jsonify(error=str(e)),502

    @app.route('/api/mcp/skills',methods=['POST'])
    def save_skill():
        v=request.get_json(silent=True) or {};conn=connector(v.get('connector_id',''));name=str(v.get('name','')).strip();description=str(v.get('description','')).strip();tool_name=v.get('tool_name');args=v.get('arguments',{})
        tool=next((t for t in json.loads(conn['tools']) if t['name']==tool_name),None)
        if not name or len(name)>100 or len(description)>1000 or not tool: return jsonify(error='Choose a discovered tool and give the skill a short name.'),400
        try:
            if len(json.dumps(args))>30000: raise ValueError('Skill arguments exceed 30 KB.')
            validate_args(tool,args)
        except ValueError as e: return jsonify(error=str(e)),400
        sid=uuid.uuid4().hex
        with db() as c: c.execute('INSERT INTO mcp_skills VALUES(?,?,?,?,?,?,?,?)',(sid,name,description,conn['id'],tool_name,json.dumps(args),now(),now()))
        log('skill','Reusable tool preset saved: '+name);return jsonify(id=sid),201

    @app.route('/api/mcp/skills/<sid>',methods=['DELETE'])
    def delete_skill(sid):
        with db() as c: c.execute('DELETE FROM mcp_skills WHERE id=?',(sid,))
        return jsonify(ok=True)

    @app.route('/api/mcp/runs/<rid>')
    def run_detail(rid):
        with db() as c: r=c.execute('SELECT * FROM mcp_runs WHERE id=?',(rid,)).fetchone()
        if not r: abort(404)
        return jsonify(dict(r))

    @app.route('/api/mcp/run',methods=['POST'])
    def run_tool():
        v=request.get_json(silent=True) or {};rid=v.get('request_id','');args=v.get('arguments');conn=connector(v.get('connector_id',''));tool_name=v.get('tool_name')
        if not re.fullmatch(r'[a-f0-9]{32}',str(rid)) or v.get('approved') is not True: return jsonify(error='Review the destination, tool, and arguments, and explicitly approve this run.'),400
        tool=next((t for t in json.loads(conn['tools']) if t['name']==tool_name),None)
        if not tool or v.get('digest')!=digest(tool): return jsonify(error='The tool selection changed. Sync the connector and review the tool again.'),409
        try:
            if len(json.dumps(args))>30000: raise ValueError('Arguments exceed 30 KB.')
            validate_args(tool,args);client=client_for(conn)
        except (ValueError,MCPError) as e:return jsonify(error=str(e)),400
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM mcp_runs WHERE id=?',(rid,)).fetchone()
            if old:return jsonify(id=rid,status=old['status'],duplicate=True),200
            if c.execute("SELECT 1 FROM mcp_runs WHERE status='running'").fetchone(): return jsonify(error='A tool is already running. Wait before starting another.'),409
            c.execute('INSERT INTO mcp_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(rid,conn['id'],conn['name'],tool_name,v.get('skill_id',''),'running',client.redact(json.dumps(args)),'','',0,now(),None))
        started=time.monotonic();calling=False;status='failed';result_text='';error=''
        try:
            client.initialize();fresh=clean_tools(client.list_tools());current=next((t for t in fresh if t['name']==tool_name),None)
            if not current or digest(current)!=digest(tool): raise MCPError('The provider changed this tool since your review. Sync and approve its new definition before running.')
            calling=True;result=client.call(tool_name,args)
            if not isinstance(result,dict): raise MCPError('The tool returned an invalid result.')
            status='tool_error' if result.get('isError') else 'succeeded'
            result_text=client.redact(json.dumps(result,ensure_ascii=False))
            if len(result_text)>100000: result_text=result_text[:100000]+'\n[Output truncated at 100,000 characters]'
        except MCPError as e: status='unknown' if calling else 'failed';error=str(e)
        except Exception: status='unknown' if calling else 'failed';error='The run could not be confirmed. Check the provider before retrying.'
        duration=round((time.monotonic()-started)*1000)
        with db() as c: c.execute('UPDATE mcp_runs SET status=?,result=?,error=?,duration_ms=?,finished=? WHERE id=?',(status,result_text,error,duration,now(),rid))
        log('mcp_run',f'MCP tool {tool_name}: {status}')
        return jsonify(id=rid,status=status,error=error),200

    @app.route('/api/contracts',methods=['GET','POST'])
    def contracts():
        if request.method=='GET':
            with db() as c: rows=[dict(r) for r in c.execute('SELECT * FROM contracts ORDER BY created DESC')]
            return jsonify(contracts=rows,currencies=CURRENCIES,stages=STAGES)
        return write_contract(None)

    def write_contract(cid):
        v=request.get_json(silent=True) or {};currency=v.get('currency','USD');status=v.get('status','Draft');title=str(v.get('title','')).strip();client=str(v.get('client','')).strip();email=str(v.get('email','')).strip();notes=str(v.get('notes','')).strip();lead_id=str(v.get('lead_id','')).strip()
        if currency not in CURRENCIES or status not in STAGES or not title or not client or len(title)>180 or len(client)>180 or len(notes)>5000: return jsonify(error='Provide a title, client, supported currency, and valid contract stage.'),400
        if email and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',email): return jsonify(error='Enter a valid client email.'),400
        try:
            amount=money(v.get('amount'),currency,optional=True);paid=money(v.get('paid'),currency)
            if paid and (amount is None or paid>amount): raise ValueError('Recorded payments cannot exceed the stated contract value. Set the contract value first.')
        except ValueError as e: return jsonify(error=str(e)),400
        stamp=now()
        with db() as c:
            if lead_id and not c.execute('SELECT 1 FROM leads WHERE id=?',(lead_id,)).fetchone(): return jsonify(error='The linked lead no longer exists.'),400
            previous=c.execute('SELECT * FROM contracts WHERE id=?',(cid,)).fetchone() if cid else None
            if cid and not previous: abort(404)
            signed=previous['signed_recorded_at'] if previous else None
            if status in ('Signed','In progress','Completed') and not signed: signed=stamp
            cid=cid or uuid.uuid4().hex
            c.execute('INSERT OR REPLACE INTO contracts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(cid,title,client,email,lead_id,currency,amount,paid,status,notes,signed,previous['created'] if previous else stamp,stamp))
        log('contract',f'Contract recorded: {title} · {status}')
        return jsonify(id=cid),200 if previous else 201

    @app.route('/api/contracts/<cid>',methods=['PATCH','DELETE'])
    def contract_detail(cid):
        if request.method=='PATCH': return write_contract(cid)
        with db() as c: c.execute('DELETE FROM contracts WHERE id=?',(cid,))
        log('contract','A contract record was deleted');return jsonify(ok=True)

    @app.after_request
    def measure_pages(response):
        path=request.path
        if request.method=='GET' and response.status_code==200 and (path in ('/','/about','/enquire','/showcase') or path.startswith(('/showcase/','/preview/'))):
            # Count requests, not unique people. Keep preview tokens out of analytics.
            page='Business proposal' if path.startswith('/preview/') else 'Sample preview' if path.startswith('/showcase/') else {'/':'Workspace','/about':'Public home','/enquire':'Enquiry form','/showcase':'Sample gallery'}[path]
            with db() as c: c.execute('INSERT INTO usage_events(event,page,created) VALUES(?,?,?)',('page_request',page,now()))
        return response

    @app.route('/api/analytics')
    def analytics():
        days=request.args.get('days','30')
        if days not in ('7','30','90'): return jsonify(error='Choose 7, 30 or 90 days.'),400
        days=int(days);end=datetime.now(timezone.utc).date();start=end-timedelta(days=days-1);cutoff=start.isoformat()
        with db() as c:
            leads=[dict(r) for r in c.execute('SELECT city,status,audit_status,email,phone,stage,created,checked_at FROM leads')]
            sends=[dict(r) for r in c.execute('SELECT state,created FROM sends')]
            enquiries=[dict(r) for r in c.execute('SELECT status,created FROM enquiries')]
            contracts=[dict(r) for r in c.execute('SELECT status,currency,amount_minor,paid_minor,created,signed_recorded_at FROM contracts')]
            runs=[dict(r) for r in c.execute('SELECT status,duration_ms,created FROM mcp_runs')]
            jobs=[dict(r) for r in c.execute('SELECT id,category,state,added,checked,progress,total,message,created,updated FROM jobs')]
            map_scans=[dict(r) for r in c.execute("SELECT s.*,count(c.id) total,sum(CASE WHEN c.state='checked' THEN 1 ELSE 0 END) checked FROM map_scans s LEFT JOIN map_cells c ON c.scan_id=s.id GROUP BY s.id")]
            map_cells=[dict(r) for r in c.execute('SELECT state,count(*) count FROM map_cells GROUP BY state')]
            recent_runs=[dict(r) for r in c.execute('SELECT id,connector_name,tool_name,status,created,finished FROM mcp_runs ORDER BY created DESC LIMIT 20')]
            pages=[dict(r) for r in c.execute("SELECT page,created FROM usage_events WHERE event='page_request' AND created>=?",(cutoff,))]
            started=c.execute("SELECT MIN(created) FROM usage_events WHERE event='measurement_started'").fetchone()[0]
            drafts=c.execute("SELECT count(*) FROM leads WHERE trim(body)!=''").fetchone()[0]
            connectors=c.execute('SELECT count(*) FROM mcp_connectors').fetchone()[0];skills=c.execute('SELECT count(*) FROM mcp_skills').fetchone()[0]
            activity=[dict(r) for r in c.execute('SELECT kind,message,created FROM activity ORDER BY id DESC LIMIT 30')]
        def counts(rows,key):return dict(Counter(r[key] or 'Not checked' for r in rows))
        timeline=[]
        for i in range(days):
            day=(start+timedelta(days=i)).isoformat()
            timeline.append({'date':day,'leads':sum(r['created'][:10]==day for r in leads),'emails':sum(r['created'][:10]==day and r['state']=='sent' for r in sends),'enquiries':sum(r['created'][:10]==day for r in enquiries),'contracts':sum(r['created'][:10]==day for r in contracts),'tool_runs':sum(r['created'][:10]==day for r in runs),'page_requests':sum(r['created'][:10]==day for r in pages)})
        tasks=[{'id':j['id'],'kind':'City discovery','title':j['category'],'state':j['state'],'detail':f"{j['progress']}/{j['total']} locations processed · {j['added']} saved · {j['checked']} URL checks",'updated':j['updated'],'page':'global'} for j in jobs]
        tasks += [{'id':s['id'],'kind':'Map scan','title':s['label']+' · '+s['category'],'state':s['state'],'detail':f"{s['checked']}/{s['total']} cells checked; partial cells are not complete",'updated':s['updated'],'page':'global'} for s in map_scans]
        tasks += [{'id':r['id'],'kind':'Approved MCP run','title':r['connector_name']+' · '+r['tool_name'],'state':r['status'],'detail':'Provider result and evidence available in MCP run history.','updated':r['finished'] or r['created'],'page':'integrations'} for r in recent_runs]
        tasks=sorted(tasks,key=lambda t:(t['state'] in ('running','queued'),t['updated']),reverse=True)[:20]
        amounts={}
        for r in contracts:
            currency=r['currency'];v=amounts.setdefault(currency,{'currency':currency,'decimals':CURRENCIES[currency],'pipeline_minor':0,'committed_minor':0,'payments_minor':0,'unpriced':0})
            if r['amount_minor'] is None: v['unpriced']+=1
            elif r['status'] in ('Draft','Sent'):v['pipeline_minor']+=r['amount_minor']
            elif r['status'] in ('Signed','In progress','Completed'):v['committed_minor']+=r['amount_minor']
            v['payments_minor']+=r['paid_minor'] or 0
        opportunities=sum((l['status'] in ('NOT_LISTED','SOCIAL_ONLY') or l['audit_status'] in ('DNS_UNRESOLVED','HTTP_ERROR','PARKED_SUSPECTED','UNREACHABLE','SOCIAL_ONLY')) and l['stage']!='Not a fit' for l in leads)
        return jsonify(generated_at=now(),days=days,tracking_started=started,totals={'leads':len(leads),'opportunities':opportunities,'email_available':sum(bool(l['email']) for l in leads),'phone_available':sum(bool(l['phone']) for l in leads),'emails_accepted':sum(s['state']=='sent' for s in sends),'drafts_saved':drafts,'enquiries':len(enquiries),'contracts':len(contracts),'active_contracts':sum(r['status'] in ('Signed','In progress') for r in contracts),'tool_runs':len(runs),'connectors':connectors,'skills':skills,'page_requests':len(pages)},lead_stages=counts(leads,'stage'),website_statuses=counts(leads,'status'),audits=counts(leads,'audit_status'),email_states=counts(sends,'state'),enquiry_stages=counts(enquiries,'status'),contract_stages=counts(contracts,'status'),run_states=counts(runs,'status'),job_states=counts(jobs,'state'),map_scan_states=counts(map_scans,'state'),map_cell_states={r['state']:r['count'] for r in map_cells},tasks=tasks,locations=dict(Counter(l['city'] or 'Not listed' for l in leads).most_common(10)),page_breakdown=counts(pages,'page'),amounts=list(amounts.values()),timeline=timeline,activity=activity)
