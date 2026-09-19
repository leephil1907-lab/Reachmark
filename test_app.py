"""Isolated backend checks. No messages are sent and no public APIs called."""
import unittest, tempfile, os, io, sqlite3
from unittest.mock import patch, MagicMock
_bootstrap=tempfile.TemporaryDirectory()
_original_path=os.environ.get('DATABASE_PATH')
os.environ['DATABASE_PATH']=os.path.join(_bootstrap.name,'bootstrap.sqlite3')
import app as module
if _original_path is None: os.environ.pop('DATABASE_PATH',None)
else: os.environ['DATABASE_PATH']=_original_path

class ProspectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.old=module.DB
        with module.db() as c: schema=[r[0] for r in c.execute("SELECT sql FROM sqlite_master WHERE type='table'")]
        module.DB=os.path.join(self.tmp.name,'test.sqlite3')
        with module.db() as c:
            for sql in schema: c.execute(sql)
        from services import geocode
        geocode.cache_clear()
        self.client=module.app.test_client()
        self.env=patch.dict(os.environ,{'SMTP_HOST':'smtp.example.test','SMTP_FROM':'studio@example.test','SMTP_PORT':'587','DASHBOARD_PASSWORD':'','APP_ENV':'development'});self.env.start()
    def tearDown(self):
        self.env.stop();module.DB=self.old;self.tmp.cleanup()
    def create(self):
        self.client.post('/api/leads',json={'name':'Example Bakery','city':'Winnipeg, MB','email':'bakery@example.test'})
        return self.client.get('/api/state').json['leads'][0]
    def ready(self,l):
        self.client.post('/api/settings',json={'sender_name':'Alex','agency':'Test Studio','reply_email':'alex@example.test','postal_address':'Test address','public_base_url':'https://example.test','offer':'clear, mobile-friendly websites'})
        return self.client.post('/api/leads/'+l['id']+'/compose',json={'preview':True}).json
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
        self.assertIn('Example Bakery',draft['body']);self.assertIn('/preview/'+l['token'],draft['body']);self.assertNotIn('no website',draft['body'])
        self.assertEqual(self.client.get('/preview/'+l['token']).status_code,200)
    def test_review_required(self):
        l=self.create();self.ready(l)
        self.assertEqual(self.client.post('/api/leads/'+l['id']+'/send',json={}).status_code,400)
    def test_smtp_and_duplicate_guard(self):
        l=self.create();self.ready(l)
        with patch('app.smtplib.SMTP') as smtp:
            r=self.client.post('/api/leads/'+l['id']+'/send',json={'approved':True,'basis':True});self.assertEqual(r.status_code,200)
            smtp.return_value.__enter__.return_value.send_message.assert_called_once()
            self.assertEqual(self.client.post('/api/leads/'+l['id']+'/send',json={'approved':True,'basis':True}).status_code,409)
        self.assertEqual(self.client.get('/api/state').json['sent'],1)
    def test_optout_survives_lead_deletion(self):
        l=self.create();self.ready(l)
        with patch('app.smtplib.SMTP'): self.client.post('/api/leads/'+l['id']+'/send',json={'approved':True,'basis':True})
        self.client.delete('/api/leads/'+l['id']);self.assertEqual(self.client.post('/unsubscribe/'+l['token']).status_code,200)
        self.assertIn('bakery@example.test',self.client.get('/api/state').json['suppressed'])
    def test_suppression_blocks(self):
        l=self.create();self.ready(l);self.client.post('/api/leads/'+l['id']+'/suppress',json={})
        with patch('app.smtplib.SMTP') as smtp:
            self.assertEqual(self.client.post('/api/leads/'+l['id']+'/send',json={'approved':True,'basis':True}).status_code,400);smtp.assert_not_called()
    def test_cross_origin_block(self):
        self.assertEqual(self.client.post('/api/leads',json={'name':'bad'},headers={'Origin':'https://other.example'}).status_code,403)
    def test_discovery_mock(self):
        module.last_discovery=0
        geo=MagicMock();geo.json.return_value=[{'lat':'49.89','lon':'-97.13'}]
        osm=MagicMock();osm.json.return_value={'elements':[{'type':'node','id':123,'tags':{'name':'Example','shop':'bakery'}}]}
        with patch('app.requests.get',return_value=geo),patch('map_provider.query_overpass',return_value=osm.json.return_value):
            r=self.client.post('/api/discover',json={'city':'Winnipeg','category':'Bakery'});self.assertEqual(r.json['added'],1)
    def test_global_job_validation(self):
        self.assertEqual(self.client.post('/api/jobs',json={'locations':[],'category':'Bakery'}).status_code,400)
        self.assertEqual(self.client.post('/api/jobs',json={'locations':['Paris, France']*9,'category':'Bakery'}).status_code,400)
    def test_global_job_starts_and_persists(self):
        with patch('app.threading.Thread') as thread:
            response=self.client.post('/api/jobs',json={'locations':['Accra, Ghana','Lisbon, Portugal'],'category':'Bakery','check_websites':True})
            self.assertEqual(response.status_code,202)
            thread.return_value.start.assert_called_once()
        jobs=self.client.get('/api/state').json['jobs'];self.assertEqual(jobs[0]['total'],2)
        self.assertEqual(self.client.post('/api/jobs',json={'locations':['Tokyo, Japan'],'category':'Bakery'}).status_code,409)
        self.assertEqual(self.client.post('/api/jobs/'+jobs[0]['id']+'/cancel',json={}).status_code,200)
    def test_private_url_is_blocked(self):
        from services import audit_website
        with patch('services.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),patch('services.urllib3.HTTPSConnectionPool') as pool:
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
        from services import audit_website
        self.assertEqual(audit_website('file:///etc/passwd')['status'],'CHECK_FAILED')
    def test_dns_failure_not_called_dead(self):
        from services import audit_website
        import socket
        with patch('services.socket.getaddrinfo',side_effect=socket.gaierror()):
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
    # ---- PHASE 1 SECURITY REGRESSIONS ----
    def _owner_client(self, password='owner-test-pass-123'):
        from werkzeug.security import generate_password_hash
        with patch.dict(os.environ,{'OWNER_PASSWORD_HASH':generate_password_hash(password),'DASHBOARD_PASSWORD':''}):
            page=self.client.get('/login').get_data(as_text=True)
            import re
            csrf=re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
            r=self.client.post('/login',data={'password':password,'csrf_token':csrf})
            self.assertEqual(r.status_code,302)
        return self.client
    def test_unverified_client_sees_nothing_until_email_confirmed(self):
        # Victim email receives an unassigned invoice; an account created with that
        # email must see NOTHING until the mailbox is verified.
        import re as _re
        self._owner_client()
        self.client.post('/api/invoices',json={'client_name':'Victim Co','client_email':'victimco@example.test','currency':'USD','items':[{'description':'Site','quantity':1,'unit_price':500}]})
        att=module.app.test_client()
        page=att.get('/signup').get_data(as_text=True)
        tok=_re.search(r'name="csrf-token" content="([^"]+)"',page).group(1)
        r=att.post('/api/auth/signup',json={'name':'Attacker','email':'victimco@example.test','password':'password123'},headers={'X-CSRF-Token':tok})
        self.assertEqual(r.status_code,201)
        # Unverified: invoices empty, detail 404, projects empty, PDFs 404
        self.assertEqual(att.get('/api/invoices').json['invoices'],[])
        self.assertEqual(att.get('/api/projects').json['projects'],[])
        # find the invoice id via a second owner session
        c2=module.app.test_client()
        with patch.dict(os.environ,{'DASHBOARD_PASSWORD':'x'}):
            with c2.session_transaction() as s: s['owner']=True
        rows=c2.get('/api/invoices').json['invoices']
        self.assertEqual(len(rows),1)
        iid=rows[0]['id']
        self.assertEqual(att.get('/api/invoices/'+iid).status_code,404)
        self.assertEqual(att.get('/api/documents/invoice/'+iid+'.pdf').status_code,404)
        # Verify the mailbox (the /verify flow) — only then is data granted
        with module.db() as c:
            row=c.execute('SELECT verification_token FROM users WHERE lower(email)=lower(?)',('victimco@example.test',)).fetchone()
            token=row['verification_token']
        v=att.get('/verify/'+token)
        self.assertEqual(v.status_code,200)
        self.assertEqual(len(att.get('/api/invoices').json['invoices']),1)
        self.assertEqual(att.get('/api/invoices/'+iid).status_code,200)
        self.assertEqual(att.get('/api/documents/invoice/'+iid+'.pdf').status_code,200)
    def test_owner_routes_fail_closed_without_credentials(self):
        # No credentials + not explicit development => owner routes refused.
        # (APP_ENV=None removes the key for the duration of the patch.)
        saved=os.environ.pop('APP_ENV',None)
        try:
            with patch.dict(os.environ,{'OWNER_PASSWORD_HASH':'','DASHBOARD_PASSWORD':''}):
                self.assertEqual(self.client.get('/api/state').status_code,401)
                r=self.client.get('/workspace')
                self.assertEqual(r.status_code,302)
                self.assertEqual(r.headers['Location'],'/login')
                # the public site stays available
                self.assertEqual(self.client.get('/').status_code,200)
        finally:
            if saved is None:
                os.environ.pop('APP_ENV',None)
            else:
                os.environ['APP_ENV']=saved
        # explicit development keeps the open local-dev behaviour
        self.assertEqual(self.client.get('/api/state').status_code,200)
    def test_client_reviews_start_unapproved_and_owner_moderates(self):
        self._owner_client()
        # public submission
        r=self.client.post('/api/client-reviews',json={'name':'Real Visitor','business':'Café','rating':5,'text':'Beautiful work, shipped on time.'})
        self.assertEqual(r.status_code,201)
        self.assertEqual(r.json['moderation'],'pending')
        rid=r.json['id']
        # public list excludes it; /reviews page excludes it
        pub=module.app.test_client()
        self.assertEqual(pub.get('/api/client-reviews').json,[])
        self.assertNotIn('Beautiful work',pub.get('/reviews').get_data(as_text=True))
        # owner sees it pending
        rows=self.client.get('/api/client-reviews').json
        self.assertEqual([x for x in rows if x['id']==rid][0]['approved'],0)
        # client (non-owner) cannot moderate
        c2=module.app.test_client()
        page=c2.get('/signup').get_data(as_text=True)
        import re as _re
        tok=_re.search(r'name="csrf-token" content="([^"]+)"',page).group(1)
        c2.post('/api/auth/signup',json={'name':'Client','email':'moder@example.test','password':'password123'},headers={'X-CSRF-Token':tok})
        # client sessions are rejected by the owner guard (403); anonymous by the endpoint (401)
        self.assertEqual(c2.post('/api/client-reviews/'+rid+'/moderate',json={'action':'approve'}).status_code,403)
        anon=module.app.test_client()
        self.assertEqual(anon.post('/api/client-reviews/'+rid+'/moderate',json={'action':'approve'}).status_code,401)
        # owner approves -> public
        self.assertEqual(self.client.post('/api/client-reviews/'+rid+'/moderate',json={'action':'approve'}).status_code,200)
        self.assertEqual([x for x in pub.get('/api/client-reviews').json if x['id']==rid][0]['name'],'Real Visitor')
        # owner rejects -> hidden again
        self.assertEqual(self.client.post('/api/client-reviews/'+rid+'/moderate',json={'action':'reject'}).status_code,200)
        self.assertEqual(pub.get('/api/client-reviews').json,[])
        # owner deletes -> gone
        self.assertEqual(self.client.post('/api/client-reviews/'+rid+'/moderate',json={'action':'delete'}).status_code,200)
        self.assertEqual(pub.get('/api/client-reviews').json,[])
        self.assertEqual(self.client.post('/api/client-reviews/'+rid+'/moderate',json={'action':'approve'}).status_code,404)
    def test_client_review_rate_limited(self):
        for i in range(3):
            self.assertEqual(self.client.post('/api/client-reviews',json={'name':f'Visitor {i}','rating':5,'text':f'Review number {i} here.'},environ_overrides={'REMOTE_ADDR':f'10.9.8.{i}'}).status_code,201)
        # 4th from a fresh IP but same identity window is per (ip,identity); use same IP
        base={'name':'Spammer','rating':5,'text':'Spam spam spam spam.'}
        self.assertEqual(self.client.post('/api/client-reviews',json=dict(base),environ_overrides={'REMOTE_ADDR':'10.1.1.1'}).status_code,201)
        self.assertEqual(self.client.post('/api/client-reviews',json=dict(base),environ_overrides={'REMOTE_ADDR':'10.1.1.1'}).status_code,201)
        self.assertEqual(self.client.post('/api/client-reviews',json=dict(base),environ_overrides={'REMOTE_ADDR':'10.1.1.1'}).status_code,201)
        self.assertEqual(self.client.post('/api/client-reviews',json=dict(base),environ_overrides={'REMOTE_ADDR':'10.1.1.1'}).status_code,429)
    def test_signup_and_forgot_are_throttled(self):
        ip='203.0.113.7'
        for i in range(10):
            r=self.client.post('/api/auth/signup',json={'name':f'U{i}','email':f'throttle{i}@example.test','password':'password123'},environ_overrides={'REMOTE_ADDR':ip})
            self.assertEqual(r.status_code,201,i)
        self.assertEqual(self.client.post('/api/auth/signup',json={'name':'U99','email':'throttle99@example.test','password':'password123'},environ_overrides={'REMOTE_ADDR':ip}).status_code,429)
        # forgot: 3 per email per hour (generic ok response on both paths)
        self.assertEqual(self.client.post('/api/auth/forgot',json={'email':'throttle0@example.test'},environ_overrides={'REMOTE_ADDR':'203.0.113.9'}).status_code,200)
        self.assertEqual(self.client.post('/api/auth/forgot',json={'email':'throttle0@example.test'},environ_overrides={'REMOTE_ADDR':'203.0.113.9'}).status_code,200)
        self.assertEqual(self.client.post('/api/auth/forgot',json={'email':'throttle0@example.test'},environ_overrides={'REMOTE_ADDR':'203.0.113.9'}).status_code,200)
        # 4th returns the generic ok (no enumeration) but no email is queued
        self.assertEqual(self.client.post('/api/auth/forgot',json={'email':'throttle0@example.test'},environ_overrides={'REMOTE_ADDR':'203.0.113.9'}).status_code,200)
        with module.db() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM mail_outbox WHERE subject LIKE 'Reset%'").fetchone()[0],3)
    def test_captcha_hook_enforces_registered_verifier(self):
        import accounts
        def verifier(token,ip): return token=='good-token'
        accounts.register_captcha_verifier('testcap',verifier)
        try:
            with patch.dict(os.environ,{'CAPTCHA_PROVIDER':'testcap'}):
                page=self.client.get('/signup').get_data(as_text=True)
                import re as _re
                tok=_re.search(r'name="csrf-token" content="([^"]+)"',page).group(1)
                r=self.client.post('/api/auth/signup',json={'name':'C','email':'cap1@example.test','password':'password123','captcha_token':'bad'},headers={'X-CSRF-Token':tok})
                self.assertEqual(r.status_code,400)
                r=self.client.post('/api/auth/signup',json={'name':'C','email':'cap2@example.test','password':'password123','captcha_token':'good-token'},headers={'X-CSRF-Token':tok})
                self.assertEqual(r.status_code,201)
        finally:
            accounts._CAPTCHA_VERIFIERS.pop('testcap',None)
    def test_trusted_proxies_strip_untrusted_xff(self):
        # Observe the header while the request is in flight (the response's .request
        # is a snapshot, so probe it with a temporary before_request registered after
        # the stripping hook).
        from flask import request as live_request
        seen=[]
        def probe():
            seen.append(live_request.headers.get('X-Forwarded-For'))
        funcs=module.app.before_request_funcs[None]
        funcs.append(probe)  # appended last: runs after the stripping hook
        try:
            with patch.dict(os.environ,{'TRUSTED_PROXIES':'198.51.100.0/24'}):
                self.client.get('/api/state',environ_overrides={'REMOTE_ADDR':'203.0.113.50','HTTP_X_FORWARDED_FOR':'9.9.9.9'})
                self.assertIsNone(seen[-1],'untrusted peer XFF must be stripped')
                self.client.get('/api/state',environ_overrides={'REMOTE_ADDR':'198.51.100.7','HTTP_X_FORWARDED_FOR':'9.9.9.9'})
                self.assertEqual(seen[-1],'9.9.9.9','trusted proxy XFF must be kept')
        finally:
            funcs.remove(probe)
    def test_session_cookie_lifetimes_owner_12h_client_30d(self):
        import re as _re
        from email.utils import parsedate_to_datetime
        from datetime import datetime,timezone,timedelta
        # owner
        self._owner_client()
        sc=self.client.get('/api/state').headers.get('Set-Cookie','')
        m=_re.search(r'session=([^;]+);.*Expires=([^;]+);',sc)
        self.assertIsNotNone(m,'owner response should refresh session cookie')
        owner_exp=parsedate_to_datetime(m.group(2).strip())
        now=datetime.now(timezone.utc)
        self.assertTrue(timedelta(hours=10) < (owner_exp-now) < timedelta(hours=13),f'owner expiry ~12h, got {owner_exp-now}')
        # client
        c=module.app.test_client()
        page=c.get('/signup').get_data(as_text=True)
        tok=_re.search(r'name="csrf-token" content="([^"]+)"',page).group(1)
        c.post('/api/auth/signup',json={'name':'L','email':'life@example.test','password':'password123'},headers={'X-CSRF-Token':tok})
        sc2=c.get('/api/auth/me').headers.get('Set-Cookie','')
        m2=_re.search(r'session=([^;]+);.*Expires=([^;]+);',sc2)
        self.assertIsNotNone(m2)
        client_exp=parsedate_to_datetime(m2.group(2).strip())
        self.assertTrue(timedelta(days=28) < (client_exp-now) < timedelta(days=32),f'client expiry ~30d, got {client_exp-now}')
if __name__=='__main__':unittest.main(verbosity=2)
