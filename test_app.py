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
        self.env=patch.dict(os.environ,{'SMTP_HOST':'smtp.example.test','SMTP_FROM':'studio@example.test','SMTP_PORT':'587','DASHBOARD_PASSWORD':''});self.env.start()
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
        with patch('app.requests.get',return_value=geo),patch('app.requests.post',return_value=osm):
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
        self.assertEqual(self.client.get('/').headers['X-Robots-Tag'],'noindex, nofollow')
    def test_invalid_audit_scheme(self):
        from services import audit_website
        self.assertEqual(audit_website('file:///etc/passwd')['status'],'CHECK_FAILED')
    def test_dns_failure_not_called_dead(self):
        from services import audit_website
        import socket
        with patch('services.socket.getaddrinfo',side_effect=socket.gaierror()):
            self.assertEqual(audit_website('https://unresolved.example')['status'],'DNS_UNRESOLVED')
if __name__=='__main__':unittest.main(verbosity=2)
