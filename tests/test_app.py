"""Isolated backend checks. No messages are sent and no public APIs called."""
import unittest, tempfile, os, io, sqlite3
from unittest.mock import patch, MagicMock
_bootstrap=tempfile.TemporaryDirectory()
_original_path=os.environ.get('DATABASE_PATH')
os.environ['DATABASE_PATH']=os.path.join(_bootstrap.name,'bootstrap.sqlite3')
import web.app as module
if _original_path is None: os.environ.pop('DATABASE_PATH',None)
else: os.environ['DATABASE_PATH']=_original_path

class ProspectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.old=module.DB
        with module.db() as c: schema=[r[0] for r in c.execute("SELECT sql FROM sqlite_master WHERE type='table'")]
        module.DB=os.path.join(self.tmp.name,'test.sqlite3')
        with module.db() as c:
            for sql in schema: c.execute(sql)
        from web.services import geocode
        geocode.cache_clear()
        self.client=module.app.test_client()
        self.env=patch.dict(os.environ,{'SMTP_HOST':'smtp.example.test','SMTP_FROM':'studio@example.test','SMTP_PORT':'587','DASHBOARD_PASSWORD':''});self.env.start()
    def tearDown(self):
        self.env.stop();module.DB=self.old;self.tmp.cleanup()
    def create(self):
        self.client.post('/api/leads',json={'name':'Example Bakery','city':'Winnipeg, MB','email':'bakery@example.test'})
        return self.client.get('/api/state').json['leads'][0]
    def ready(self,l):
        self.client.post('/api/settings',json={'sender_name':'Alex','agency':'Test Studio','reply_email':'alex@example.test','postal_address':'Test address','public_base_url':'https://example.test','offer':'clear, mobile-friendly websites'})
        return self.client.post('/api/leads/'+l['id']+'/compose',json={'preview':True}).json
    def test_missing_database_directory_fails_with_a_clear_message(self):
        module.DB = os.path.join(self.tmp.name, 'no-such-dir', 'x.sqlite3')
        with self.assertRaises(RuntimeError) as ctx:
            with module.db():
                pass
        self.assertIn('DATABASE_PATH', str(ctx.exception))
        module.DB = os.path.join(self.tmp.name, 'test.sqlite3')

    def test_classification(self):
        self.assertEqual(module.classify(''),'NOT_LISTED')
        self.assertEqual(module.classify('https://www.facebook.com/example'),'SOCIAL_ONLY')
        self.assertEqual(module.classify('https://notfacebook.com'),'HAS_WEBSITE')
    def test_crud_and_dedup(self):
        l=self.create();self.create();self.assertEqual(len(self.client.get('/api/state').json['leads']),1)
        self.client.patch('/api/leads/'+l['id'],json={'stage':'Replied','note':'Verified'})
        self.assertEqual(self.client.get('/api/state').json['leads'][0]['stage'],'Replied')
    def test_import_and_export(self):
        r=self.client.post('/api/import',data={'file':(io.BytesIO(b'name,city,listed_website\nOne,Halifax,https://facebook.com/one\nOne,Halifax,https://facebook.com/one\n'),'leads.csv')})
        self.assertEqual(r.json['added'],1);self.assertEqual(r.json['skipped'],1)
        self.assertIn(b'One',self.client.get('/api/export').data)
    def test_template_and_preview(self):
        l=self.create();draft=self.ready(l)
        # The draft is now the Reachmark-branded proposal e-mail: it carries the link to
        # the finished one-page website (/r/<token>) and the single question.
        self.assertIn('Example Bakery',draft['body']);self.assertIn('/r/',draft['body']);self.assertNotIn('no website',draft['body'])
        self.assertTrue(draft.get('html'))
        self.assertEqual(self.client.get('/preview/'+l['token']).status_code,200)
    def test_review_required(self):
        l=self.create();self.ready(l)
        self.assertEqual(self.client.post('/api/leads/'+l['id']+'/send',json={}).status_code,400)
    def test_smtp_and_duplicate_guard(self):
        l=self.create();self.ready(l)
        with patch('web.app.smtplib.SMTP') as smtp:
            r=self.client.post('/api/leads/'+l['id']+'/send',json={'approved':True,'basis':True});self.assertEqual(r.status_code,200)
            smtp.return_value.__enter__.return_value.send_message.assert_called_once()
            self.assertEqual(self.client.post('/api/leads/'+l['id']+'/send',json={'approved':True,'basis':True}).status_code,409)
        self.assertEqual(self.client.get('/api/state').json['sent'],1)
    def test_optout_survives_lead_deletion(self):
        l=self.create();self.ready(l)
        with patch('web.app.smtplib.SMTP'): self.client.post('/api/leads/'+l['id']+'/send',json={'approved':True,'basis':True})
        self.client.delete('/api/leads/'+l['id']);self.assertEqual(self.client.post('/unsubscribe/'+l['token']).status_code,200)
        self.assertIn('bakery@example.test',self.client.get('/api/state').json['suppressed'])
    def test_suppression_blocks(self):
        l=self.create();self.ready(l);self.client.post('/api/leads/'+l['id']+'/suppress',json={})
        with patch('web.app.smtplib.SMTP') as smtp:
            self.assertEqual(self.client.post('/api/leads/'+l['id']+'/send',json={'approved':True,'basis':True}).status_code,400);smtp.assert_not_called()
    def test_cross_origin_block(self):
        self.assertEqual(self.client.post('/api/leads',json={'name':'bad'},headers={'Origin':'https://other.example'}).status_code,403)
    def test_discovery_mock(self):
        module.last_discovery=0
        geo=MagicMock();geo.json.return_value=[{'lat':'49.89','lon':'-97.13'}]
        osm=MagicMock();osm.json.return_value={'elements':[{'type':'node','id':123,'tags':{'name':'Example','shop':'bakery'}}]}
        with patch('web.app.requests.get',return_value=geo),patch('web.map_provider.query_overpass',return_value=osm.json.return_value):
            r=self.client.post('/api/discover',json={'city':'Winnipeg','category':'Bakery'});self.assertEqual(r.json['added'],1)
    def test_global_job_validation(self):
        self.assertEqual(self.client.post('/api/jobs',json={'locations':[],'category':'Bakery'}).status_code,400)
        self.assertEqual(self.client.post('/api/jobs',json={'locations':['Paris, France']*9,'category':'Bakery'}).status_code,400)
    def test_global_job_starts_and_persists(self):
        with patch('web.app.threading.Thread') as thread:
            response=self.client.post('/api/jobs',json={'locations':['Accra, Ghana','Lisbon, Portugal'],'category':'Bakery','check_websites':True})
            self.assertEqual(response.status_code,202)
            thread.return_value.start.assert_called_once()
        jobs=self.client.get('/api/state').json['jobs'];self.assertEqual(jobs[0]['total'],2)
        self.assertEqual(self.client.post('/api/jobs',json={'locations':['Tokyo, Japan'],'category':'Bakery'}).status_code,409)
        self.assertEqual(self.client.post('/api/jobs/'+jobs[0]['id']+'/cancel',json={}).status_code,200)
    def test_private_url_is_blocked(self):
        from web.services import audit_website
        with patch('web.services.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),patch('web.services.urllib3.HTTPSConnectionPool') as pool:
            self.assertEqual(audit_website('https://private.example')['status'],'CHECK_FAILED');pool.assert_not_called()
    def test_public_metadata(self):
        response=self.client.get('/about');self.assertIn(b'application/ld+json',response.data)
        self.assertIn(b'Reachmark',response.data)
        self.assertIn(b'logo-primary.svg',response.data)
        self.assertEqual(self.client.get('/healthz').status_code,200)
        self.assertIn(b'/preview/',self.client.get('/robots.txt').data)
        self.assertIn(b'/about',self.client.get('/robots.txt').data)
        self.assertIsNone(self.client.get('/').headers.get('X-Robots-Tag'))
        self.assertEqual(self.client.get('/workspace').headers['X-Robots-Tag'],'noindex, nofollow')
        self.assertEqual(self.client.get('/dashboard').headers['X-Robots-Tag'],'noindex, nofollow')
    def test_invalid_audit_scheme(self):
        from web.services import audit_website
        self.assertEqual(audit_website('file:///etc/passwd')['status'],'CHECK_FAILED')
    def test_dns_failure_not_called_dead(self):
        from web.services import audit_website
        import socket
        with patch('web.services.socket.getaddrinfo',side_effect=socket.gaierror()):
            self.assertEqual(audit_website('https://unresolved.example')['status'],'DNS_UNRESOLVED')
    def enquiry_data(self):
        return {'name':'Test Visitor','email':'visitor@example.test','business':'Test Studio','kind':'Website estimate','budget':'Please advise','timeline':'Flexible','message':'I would like a small website with three pages and an enquiry form.','sample':'ember-coffee','consent':True,'request_id':'abcdef1234567890abcdef1234567890'}
    def test_samples_are_public_and_not_leads(self):
        before=len(self.client.get('/api/state').json['leads'])
        self.assertEqual(self.client.get('/showcase').status_code,200)
        for slug in ['ember-coffee','stillwell-studio','forma-homes','astra-clinic','novera-law','bloom-market']:
            response=self.client.get('/showcase/'+slug);self.assertEqual(response.status_code,200);self.assertIn(b'FICTIONAL DESIGN SAMPLE',response.data)
        self.assertEqual(len(self.client.get('/api/state').json['leads']),before)
        self.assertEqual(self.client.get('/showcase/missing').status_code,404)
    def test_enquiry_persists_with_reference(self):
        r=self.client.post('/api/enquiries',json=self.enquiry_data());self.assertEqual(r.status_code,201);self.assertEqual(r.json['reference'],'ABCDEF12')
        rows=self.client.get('/api/enquiries').json['enquiries'];self.assertEqual(len(rows),1);self.assertEqual(rows[0]['sample'],'ember-coffee');self.assertEqual(rows[0]['status'],'New')
        self.assertEqual(self.client.get('/api/state').json['enquiry_count'],1)
        self.assertEqual(len(self.client.get('/api/state').json['leads']),0)
    def test_enquiry_retry_is_idempotent(self):
        self.client.post('/api/enquiries',json=self.enquiry_data());r=self.client.post('/api/enquiries',json=self.enquiry_data());self.assertEqual(r.status_code,200)
        self.assertEqual(len(self.client.get('/api/enquiries').json['enquiries']),1)
    def test_enquiry_validation_and_consent(self):
        data=self.enquiry_data();data['consent']=False;self.assertEqual(self.client.post('/api/enquiries',json=data).status_code,400)
        data['consent']=True;data['email']='not-an-email';self.assertEqual(self.client.post('/api/enquiries',json=data).status_code,400)
        data=self.enquiry_data();data['company_url']='spam';self.assertEqual(self.client.post('/api/enquiries',json=data).status_code,400)
        self.assertEqual(len(self.client.get('/api/enquiries').json['enquiries']),0)
    def test_enquiry_inbox_authentication(self):
        with patch.dict(os.environ,{'DASHBOARD_PASSWORD':'test-only-password'}):
            self.assertEqual(self.client.get('/enquire').status_code,200)
            self.assertEqual(self.client.get('/showcase').status_code,200)
            self.assertEqual(self.client.post('/api/enquiries',json=self.enquiry_data()).status_code,201)
            self.assertEqual(self.client.get('/api/enquiries').status_code,401)
            self.assertEqual(self.client.patch('/api/enquiries/abcdef1234567890abcdef1234567890',json={'status':'Answered'}).status_code,401)
    def test_enquiry_update_and_delete(self):
        self.client.post('/api/enquiries',json=self.enquiry_data());eid=self.enquiry_data()['request_id']
        self.assertEqual(self.client.patch('/api/enquiries/'+eid,json={'status':'In progress','notes':'Scope under review'}).status_code,200)
        self.assertEqual(self.client.get('/api/enquiries').json['enquiries'][0]['notes'],'Scope under review')
        self.assertEqual(self.client.delete('/api/enquiries/'+eid).status_code,200)
        self.assertEqual(self.client.get('/api/enquiries').json['enquiries'],[])
    def test_enquiry_rate_limit(self):
        for i in range(3):
            data=self.enquiry_data();data['request_id']=f'{i:032x}';self.assertEqual(self.client.post('/api/enquiries',json=data).status_code,201)
        data=self.enquiry_data();data['request_id']='e'*32;self.assertEqual(self.client.post('/api/enquiries',json=data).status_code,429)
    def test_enquiry_cross_origin_is_rejected(self):
        self.assertEqual(self.client.post('/api/enquiries',json=self.enquiry_data(),headers={'Origin':'https://elsewhere.example'}).status_code,403)
    def test_client_auth_session_sticks_after_signup_and_login(self):
        # Regression: signup/login must persist the client session (no auto-logout).
        # Pages embed their own CSRF meta token; nothing scrapes another page whose
        # Set-Cookie could race and overwrite the fresh session.
        import re
        page=self.client.get('/signup').get_data(as_text=True)
        tok=re.search(r'name="csrf-token" content="([^"]+)"',page)
        self.assertIsNotNone(tok,'signup page must embed its own CSRF token')
        r=self.client.post('/api/auth/signup',json={'name':'Client One','email':'clientone@example.test','password':'password123'},headers={'X-CSRF-Token':tok.group(1)})
        self.assertEqual(r.status_code,201)
        sc=r.headers.get('Set-Cookie','')
        self.assertIn('SameSite=Lax',sc)
        self.assertIn('HttpOnly',sc)
        self.assertEqual(self.client.get('/dashboard').status_code,200)
        me=self.client.get('/api/auth/me')
        self.assertEqual(me.status_code,200)
        self.assertEqual(me.json['role'],'client')
        self.assertEqual(me.json['email'],'clientone@example.test')
        c2=module.app.test_client()
        page2=c2.get('/signin').get_data(as_text=True)
        tok2=re.search(r'name="csrf-token" content="([^"]+)"',page2)
        self.assertIsNotNone(tok2,'signin page must embed its own CSRF token')
        r2=c2.post('/api/auth/login',json={'email':'clientone@example.test','password':'password123'},headers={'X-CSRF-Token':tok2.group(1)})
        self.assertEqual(r2.status_code,200)
        self.assertEqual(c2.get('/api/auth/me').json['role'],'client')
        self.assertEqual(c2.get('/dashboard').status_code,200)
        self.assertEqual(c2.get('/api/state').json['role'],'client')
    def test_anonymous_dashboard_goes_to_client_signin(self):
        # Anonymous/expired visitors to the client dashboard land on the client
        # sign-in, never the hidden owner login.
        from werkzeug.security import generate_password_hash
        hashed=generate_password_hash('owner-only',method='pbkdf2:sha256:1000')
        with patch.dict(os.environ,{'OWNER_PASSWORD_HASH':hashed}):
            r=self.client.get('/dashboard')
            self.assertEqual(r.status_code,302)
            self.assertEqual(r.headers['Location'],'/signin')
if __name__=='__main__':unittest.main(verbosity=2)
