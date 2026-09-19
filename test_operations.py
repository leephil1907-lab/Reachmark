import os, json, tempfile, unittest, uuid
from unittest.mock import patch, MagicMock
from test_app import module
from operations import digest
from mcp_transport import MCPError, MCPClient, validate_endpoint

TOOL={'name':'summarize','description':'Test-only tool','inputSchema':{'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False}}

class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=module.DB
        with module.db() as c: schema=[r[0] for r in c.execute("SELECT sql FROM sqlite_master WHERE type='table'")]
        module.DB=os.path.join(self.tmp.name,'test.sqlite3')
        with module.db() as c:
            for sql in schema:c.execute(sql)
        self.client=module.app.test_client();self.env=patch.dict(os.environ,{'DASHBOARD_PASSWORD':'','APP_ENV':'development'});self.env.start()
    def tearDown(self):self.env.stop();module.DB=self.old;self.tmp.cleanup()
    def connector(self):
        r=self.client.post('/api/mcp/connectors',json={'name':'Unit-test service','url':'https://provider.example/mcp'});self.assertEqual(r.status_code,201)
        cid=r.json['id']
        with module.db() as c:c.execute("UPDATE mcp_connectors SET tools=?,status='Connected' WHERE id=?",(json.dumps([TOOL]),cid))
        return cid
    def run_data(self,cid):return {'request_id':uuid.uuid4().hex,'connector_id':cid,'tool_name':'summarize','arguments':{'text':'A test input'},'digest':digest(TOOL),'approved':True}
    def fake_client(self):
        f=MagicMock();f.initialize.return_value={'name':'Fixture'};f.list_tools.return_value=[TOOL];f.call.return_value={'content':[{'type':'text','text':'Fixture result'}]};f.redact.side_effect=lambda s:s;return f
    def test_empty_analytics_has_no_fake_records(self):
        a=self.client.get('/api/analytics').json
        for key in ('leads','emails_accepted','contracts','tool_runs','enquiries'):self.assertEqual(a['totals'][key],0)
        self.assertEqual(a['amounts'],[])
    def test_money_is_separate_by_currency(self):
        for currency,amount,paid in [('USD','1250.25','250.25'),('NGN','800000','100000')]:
            r=self.client.post('/api/contracts',json={'title':'Actual test agreement','client':'Test Client','currency':currency,'amount':amount,'paid':paid,'status':'Signed'});self.assertEqual(r.status_code,201)
        values={v['currency']:v for v in self.client.get('/api/analytics').json['amounts']}
        self.assertEqual(values['USD']['committed_minor'],125025);self.assertEqual(values['NGN']['committed_minor'],80000000);self.assertEqual(values['USD']['payments_minor'],25025)
        self.assertEqual(self.client.get('/api/analytics').json['totals']['contracts'],2)
    def test_contract_validation_and_unpriced(self):
        base={'title':'Unpriced agreement','client':'Client','currency':'USD','status':'Draft'}
        r=self.client.post('/api/contracts',json=base);self.assertEqual(r.status_code,201)
        self.assertIsNone(self.client.get('/api/contracts').json['contracts'][0]['amount_minor'])
        self.assertEqual(self.client.post('/api/contracts',json={**base,'paid':'10'}).status_code,400)
        self.assertEqual(self.client.post('/api/contracts',json={**base,'amount':'-3'}).status_code,400)
        self.assertEqual(self.client.post('/api/contracts',json={**base,'currency':'JPY','amount':'10.5'}).status_code,400)
    def test_contract_update_and_delete_changes_totals(self):
        data={'title':'Scope','client':'Client','currency':'USD','amount':'500','paid':'0','status':'Draft'}
        cid=self.client.post('/api/contracts',json=data).json['id'];self.client.patch('/api/contracts/'+cid,json={**data,'status':'Completed','paid':'500'})
        self.assertEqual(self.client.get('/api/analytics').json['amounts'][0]['payments_minor'],50000)
        self.client.delete('/api/contracts/'+cid);self.assertEqual(self.client.get('/api/analytics').json['totals']['contracts'],0)
    def test_private_and_credential_urls_blocked(self):
        for url in ['http://remote.example/mcp','https://127.0.0.1/mcp','https://192.168.1.4/mcp','https://name:secret@remote.example/mcp','https://remote.example/mcp?token=x']:
            with self.assertRaises(MCPError):validate_endpoint(url)
    def test_token_reference_is_not_arbitrary_env(self):
        r=self.client.post('/api/mcp/connectors',json={'name':'Wrong','url':'https://remote.example/mcp','token_env':'SMTP_PASSWORD'});self.assertEqual(r.status_code,400)
    def test_sync_discovers_real_response_not_fixed_tools(self):
        cid=self.connector();f=self.fake_client()
        with patch('operations.MCPClient',return_value=f):r=self.client.post('/api/mcp/connectors/'+cid+'/sync',json={})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['count'],1);self.assertEqual(self.client.get('/api/mcp').json['connectors'][0]['tools'][0]['name'],'summarize')
    def test_sync_failure_is_visible(self):
        cid=self.connector();f=self.fake_client();f.initialize.side_effect=MCPError('Provider unavailable')
        with patch('operations.MCPClient',return_value=f):r=self.client.post('/api/mcp/connectors/'+cid+'/sync',json={})
        self.assertEqual(r.status_code,502);self.assertEqual(self.client.get('/api/mcp').json['connectors'][0]['status'],'Connection failed')
    def test_approval_and_schema_required(self):
        cid=self.connector();data=self.run_data(cid)
        self.assertEqual(self.client.post('/api/mcp/run',json={**data,'approved':False}).status_code,400)
        self.assertEqual(self.client.post('/api/mcp/run',json={**data,'arguments':{'text':42}}).status_code,400)
        self.assertEqual(self.client.get('/api/mcp').json['runs'],[])
    def test_success_and_duplicate_protection(self):
        cid=self.connector();data=self.run_data(cid);f=self.fake_client()
        with patch('operations.MCPClient',return_value=f):
            first=self.client.post('/api/mcp/run',json=data);second=self.client.post('/api/mcp/run',json=data)
        self.assertEqual(first.json['status'],'succeeded');self.assertTrue(second.json['duplicate']);f.call.assert_called_once()
        self.assertEqual(self.client.get('/api/analytics').json['totals']['tool_runs'],1)
    def test_timeout_is_unknown_and_not_replayed(self):
        cid=self.connector();data=self.run_data(cid);f=self.fake_client();f.call.side_effect=MCPError('Connection lost')
        with patch('operations.MCPClient',return_value=f):
            result=self.client.post('/api/mcp/run',json=data);self.client.post('/api/mcp/run',json=data)
        self.assertEqual(result.json['status'],'unknown');f.call.assert_called_once()
    def test_changed_tool_is_not_executed(self):
        cid=self.connector();f=self.fake_client();f.list_tools.return_value=[{**TOOL,'description':'Different behavior'}]
        with patch('operations.MCPClient',return_value=f):r=self.client.post('/api/mcp/run',json=self.run_data(cid))
        self.assertEqual(r.json['status'],'failed');f.call.assert_not_called()
    def test_skills_are_presets_not_runs(self):
        cid=self.connector();r=self.client.post('/api/mcp/skills',json={'name':'Preset','connector_id':cid,'tool_name':'summarize','arguments':{'text':'Saved input'}})
        self.assertEqual(r.status_code,201);self.assertEqual(len(self.client.get('/api/mcp').json['skills']),1);self.assertEqual(self.client.get('/api/mcp').json['runs'],[])
    def test_mcp_and_contracts_require_dashboard_auth(self):
        with patch.dict(os.environ,{'DASHBOARD_PASSWORD':'test-password'}):
            for url in ['/api/mcp','/api/analytics','/api/contracts']:self.assertEqual(self.client.get(url).status_code,401)
    def test_page_requests_are_counted_not_visitors(self):
        self.client.get('/about');self.client.get('/about');self.client.get('/static/icon.svg').close()
        a=self.client.get('/api/analytics').json;self.assertEqual(a['page_breakdown']['Public home'],2);self.assertEqual(a['totals']['page_requests'],2)
    def test_external_json_schema_refs_blocked(self):
        cid=self.connector();tool={**TOOL,'inputSchema':{'$ref':'https://private.example/schema'}}
        with module.db() as c:c.execute('UPDATE mcp_connectors SET tools=? WHERE id=?',(json.dumps([tool]),cid))
        data={**self.run_data(cid),'digest':digest(tool)};self.assertEqual(self.client.post('/api/mcp/run',json=data).status_code,400)
    def test_streamable_http_json_and_sse(self):
        seen=[]
        def respond(method,path,body,headers,**kwargs):
            payload=json.loads(body);seen.append((payload,headers));r=MagicMock();r.status=200;r.headers={'Content-Type':'text/event-stream','Mcp-Session-Id':'unit-session'}
            if payload['method']=='notifications/initialized':r.status=202;return r
            result={'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'Test'}} if payload['method']=='initialize' else {'tools':[TOOL]}
            data=json.dumps({'jsonrpc':'2.0','id':payload['id'],'result':result}).encode()
            if payload['method']=='initialize':r.headers['Content-Type']='application/json';r.read.return_value=data
            else:r.read1.side_effect=[b'event: message\ndata: '+data+b'\n\n',b'']
            return r
        pool=MagicMock();pool.urlopen.side_effect=respond
        with patch('mcp_transport.public_ip',return_value='8.8.8.8'),patch('mcp_transport.urllib3.HTTPSConnectionPool',return_value=pool):
            c=MCPClient('https://remote.example/mcp');c.initialize();self.assertEqual(c.list_tools()[0]['name'],'summarize')
        self.assertEqual(seen[1][1]['Mcp-Session-Id'],'unit-session');self.assertEqual(seen[0][1]['Accept'],'application/json, text/event-stream')

if __name__=='__main__':unittest.main(verbosity=2)
