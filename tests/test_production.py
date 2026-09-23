"""Production feature regressions. Disposable databases; no external calls."""
import os,re,tempfile,unittest,sqlite3,subprocess,sys
from pathlib import Path
from unittest.mock import patch
from tests.test_app import module
import tests.test_app as test_app
from werkzeug.security import generate_password_hash
from scripts.backup import snapshot,restore
from web.workflow import duplicates

class PWAAndManifestTests(unittest.TestCase):
    """The installable-app contract: manifest, icons, screenshots, service worker, offline."""

    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def manifest(self):
        import json
        with open(Path(__file__).parent.parent / 'static' / 'manifest.webmanifest', encoding='utf-8') as handle:
            return json.load(handle)

    def test_manifest_has_every_field_an_install_prompt_reads(self):
        manifest = self.manifest()
        for key in ('id', 'name', 'short_name', 'description', 'start_url', 'scope', 'display',
                    'theme_color', 'background_color', 'lang', 'dir', 'categories', 'icons'):
            self.assertTrue(manifest.get(key), f'manifest is missing {key}')
        self.assertEqual(manifest['id'], '/')
        self.assertEqual(manifest['scope'], '/')
        self.assertIn('standalone', manifest['display_override'])
        self.assertFalse(manifest['prefer_related_applications'],
                         'installability requires prefer_related_applications to be false')

    def test_icons_include_a_maskable_and_match_their_declared_size(self):
        from PIL import Image
        manifest = self.manifest()
        icons = manifest['icons']
        self.assertTrue(any(i.get('purpose') == 'maskable' for i in icons),
                        'Android crops icons to its own shape — a maskable icon is required')
        self.assertTrue(any(i.get('sizes') == '512x512' and i.get('purpose') != 'maskable' for i in icons))
        for icon in icons:
            path = Path(__file__).parent.parent / icon['src'].lstrip('/')
            self.assertTrue(path.exists(), f"{icon['src']} does not exist")
            if path.suffix == '.png':
                self.assertEqual(f'{Image.open(path).width}x{Image.open(path).height}', icon['sizes'],
                                 f"{icon['src']} is not the size the manifest claims")

    def test_screenshots_exist_in_both_orientations_at_their_declared_size(self):
        from PIL import Image
        manifest = self.manifest()
        shots = manifest['screenshots']
        self.assertTrue(any(s['form_factor'] == 'narrow' for s in shots))
        self.assertTrue(any(s['form_factor'] == 'wide' for s in shots))
        for shot in shots:
            path = Path(__file__).parent.parent / shot['src'].lstrip('/')
            self.assertTrue(path.exists(), f"{shot['src']} does not exist")
            self.assertEqual(f'{Image.open(path).width}x{Image.open(path).height}', shot['sizes'])

    def test_service_worker_never_caches_private_routes(self):
        source = (Path(__file__).parent.parent / 'static' / 'sw.js').read_text(encoding='utf-8')
        # The deny-list is written as regexes ('/^\/api\/crew/'), so compare unescaped.
        plain = source.replace('\\/', '/')
        for private in ('/workspace', '/dashboard', '/api/crew', '/api/state', '/api/leads', '/r/'):
            self.assertIn(private, plain, f'{private} must be on the worker deny-list')
        self.assertIn("request.mode === 'navigate'", source)
        self.assertIn('OFFLINE_URL', source)

    def test_offline_page_and_worker_are_served(self):
        self.assertEqual(self.client.get('/offline').status_code, 200)
        page = self.client.get('/offline').get_data(as_text=True)
        self.assertIn('offline', page.lower())
        worker = self.client.get('/static/sw.js')
        self.assertEqual(worker.status_code, 200)
        self.assertEqual(worker.headers.get('Service-Worker-Allowed'), '/')
        self.assertIn('no-store', worker.headers.get('Cache-Control', ''))
        manifest = self.client.get('/static/manifest.webmanifest')
        self.assertEqual(manifest.headers.get('Content-Type'), 'application/manifest+json')

    def test_deploy_check_reports_the_manifest_checklist(self):
        body = self.client.get('/api/deploy-check').json
        names = [c['name'] for c in body['checks']]
        for expected in ('MANIFEST', 'MANIFEST maskable icon', 'MANIFEST screenshots', 'SERVICE WORKER'):
            self.assertIn(expected, names)
        self.assertEqual(body['total'], len(body['checks']))
        self.assertEqual(body['passed'], len([c for c in body['checks'] if c['ok']]))
        manifest_checks = [c for c in body['checks'] if c['name'].startswith(('MANIFEST', 'ASSET', 'SERVICE', 'OFFLINE'))]
        self.assertTrue(all(c['ok'] for c in manifest_checks),
                        [c for c in manifest_checks if not c['ok']])

    def test_app_identity_is_unchanged(self):
        """The application name, description and icons belong to the owner — the crew never edits them."""
        manifest = self.manifest()
        self.assertEqual(manifest['name'], 'Reachmark \u2014 Discover Business Potential')
        self.assertEqual(manifest['short_name'], 'Reachmark')
        self.assertIn('Discover businesses worldwide', manifest['description'])
        home = self.client.get('/').get_data(as_text=True)
        self.assertIn('Reachmark \u2014 Find Potential. Make Your Mark.', home)


class ProductionTests(unittest.TestCase):
    setUp=test_app.ProspectTests.setUp
    tearDown=test_app.ProspectTests.tearDown
    def add(self,name='Temporary café',city='Test city',phone='1234567890'):
        self.client.post('/api/leads',json={'name':name,'city':city,'phone':phone})
        return self.client.get('/api/state').json['leads'][0]
    def test_login_protects_private_downloads_and_csrf(self):
        hashed=generate_password_hash('a-test-password',method='pbkdf2:sha256:1000')
        with patch.dict(os.environ,{'OWNER_PASSWORD_HASH':hashed}):
            for path in ['/api/state','/api/projects','/api/quality','/api/documents/audit/any.pdf','/api/export']:
                self.assertEqual(self.client.get(path).status_code,401)
            self.assertEqual(self.client.get('/').status_code,200)
            self.assertEqual(self.client.get('/about').status_code,200)
            self.assertEqual(self.client.get('/workspace').status_code,302)
            self.assertEqual(self.client.get('/dashboard').status_code,302)
            self.assertEqual(self.client.get('/healthz').status_code,200)
            page=self.client.get('/login').text;csrf=re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
            self.assertEqual(self.client.post('/login',data={'password':'a-test-password','csrf_token':csrf}).status_code,302)
            self.assertEqual(self.client.get('/api/state').status_code,200)
            self.assertEqual(self.client.post('/api/leads',json={'name':'Test'}).status_code,403)
            with self.client.session_transaction() as s:token=s['csrf']
            self.assertEqual(self.client.post('/api/leads',json={'name':'Test'},headers={'X-CSRF-Token':token}).status_code,200)
            self.assertEqual(self.client.post('/logout',headers={'X-CSRF-Token':token}).status_code,302)
            self.assertEqual(self.client.get('/api/state').status_code,401)
    def test_login_throttles_bad_passwords(self):
        with patch.dict(os.environ,{'OWNER_PASSWORD_HASH':generate_password_hash('test',method='pbkdf2:sha256:1000')}):
            page=self.client.get('/login').text;csrf=re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
            for i in range(5):self.client.post('/login',data={'password':'bad','csrf_token':csrf})
            self.assertEqual(self.client.post('/login',data={'password':'test','csrf_token':csrf}).status_code,429)
    def test_production_fails_closed(self):
        env={**os.environ,'APP_ENV':'production','DATABASE_PATH':str(Path(self.tmp.name)/'closed.sqlite3'),'SECRET_KEY':'','OWNER_PASSWORD_HASH':''}
        p=subprocess.run([sys.executable,'-c','import web.app'],env=env,capture_output=True,timeout=20)
        self.assertNotEqual(p.returncode,0);self.assertIn(b'Production requires',p.stderr)
    def test_manual_evidence_and_url_change(self):
        l=self.add()
        self.assertEqual(self.client.post(f"/api/leads/{l['id']}/review",json={'verification':'LISTED_URL_UNAVAILABLE'}).status_code,400)
        data={'verification':'LISTED_URL_UNAVAILABLE','note':'Manually reviewed the exact listed URL and found a missing page.','evidence_url':'https://example.test/missing'}
        self.assertEqual(self.client.post(f"/api/leads/{l['id']}/review",json=data).status_code,200)
        self.assertEqual(self.client.get('/api/state').json['leads'][0]['verification'],'LISTED_URL_UNAVAILABLE')
        self.client.patch(f"/api/leads/{l['id']}",json={'website':'https://new.example.test'})
        self.assertIsNone(self.client.get('/api/state').json['leads'][0]['verification'])
    def test_duplicate_candidates_never_merge(self):
        self.add('Fixture first');self.add('Fixture second')
        data=self.client.get('/api/quality').json
        self.assertEqual(len(data['duplicates']),1);self.assertIn('Matching phone',data['duplicates'][0]['reasons'])
        self.assertEqual(len(self.client.get('/api/state').json['leads']),2)
    def project(self):
        l=self.add();r=self.client.post('/api/projects',json={'title':'Test café website','lead_id':l['id'],'scope':'A saved scope with café & <markup>','currency':'NGN','quote':'250000.00','due_date':'2026-01-01','next_action':'Review the preview','stage':'Preview'})
        self.assertEqual(r.status_code,201,r.json);return l,r.json['id']
    def test_projects_and_pdf_exports(self):
        l,pid=self.project()
        for kind,rid in [('audit',l['id']),('proposal',pid),('brief',pid)]:
            r=self.client.get(f'/api/documents/{kind}/{rid}.pdf');self.assertEqual(r.status_code,200);self.assertEqual(r.mimetype,'application/pdf');self.assertTrue(r.data.startswith(b'%PDF'));self.assertIn('attachment',r.headers['Content-Disposition'])
        p=self.client.get('/api/projects').json['projects'][0];self.assertEqual(p['quote_minor'],25000000);self.assertEqual(p['due_date'],'2026-01-01')
        self.assertEqual(self.client.get('/api/documents/proposal/missing.pdf').status_code,404)
        self.client.delete('/api/projects/'+pid);self.assertEqual(len(self.client.get('/api/state').json['leads']),1)
    def test_contract_pdf_status(self):
        r=self.client.post('/api/contracts',json={'title':'Test scope','client':'Test client','currency':'USD','status':'Draft'})
        self.assertEqual(r.status_code,201)
        pdf=self.client.get('/api/documents/contract/'+r.json['id']+'.pdf');self.assertTrue(pdf.data.startswith(b'%PDF'))
    def test_bad_project_values(self):
        for data in ({'title':'T','due_date':'not a date'},{'title':'T','quote':'-10'},{'title':'T','currency':[]},{'title':'T','lead_id':'missing'}):self.assertEqual(self.client.post('/api/projects',json=data).status_code,400)
    def test_snapshot_and_verified_restore(self):
        l,pid=self.project();path=snapshot(module.DB,Path(self.tmp.name)/'backups')
        with module.db() as c:c.execute('DELETE FROM leads');c.execute('DELETE FROM projects')
        counts=restore(path,module.DB);self.assertEqual(counts['leads'],1);self.assertEqual(counts['projects'],1)
        self.assertEqual(self.client.get('/api/projects').json['projects'][0]['id'],pid)
        path.write_bytes(path.read_bytes()+b'corruption')
        with self.assertRaises(RuntimeError):restore(path,module.DB)
    def test_readiness_is_honest(self):
        d=self.client.get('/api/operations/readiness').json
        self.assertIn('NOT CONFIGURED',d['Owner authentication']);self.assertIn('Not connected',d['Error monitoring'])

class HomepageAndAuthBrandTests(unittest.TestCase):
    setUp=test_app.ProspectTests.setUp
    tearDown=test_app.ProspectTests.tearDown
    def test_home_is_a_slim_multipage_hub(self):
        home=self.client.get('/').get_data(as_text=True)
        self.assertIn('Reachmark \u2014 Find Potential. Make Your Mark.',home)
        for path in ('/showcase','/receptionist','/reviews','/about','/enquire','/signin','/signup'):
            self.assertIn(f'href="{path}"',home,path)
        self.assertNotIn('I hunt missing websites',home)
        about=self.client.get('/about').get_data(as_text=True)
        self.assertLess(len(home),len(about)//2)
    def test_about_and_reviews_keep_the_full_page(self):
        for path in ('/about','/reviews'):
            body=self.client.get(path).get_data(as_text=True)
            self.assertIn('I hunt missing websites',body,path)
    def test_auth_pages_use_the_visible_inverse_logo(self):
        for path in ('/signup','/signin','/login'):
            body=self.client.get(path).get_data(as_text=True)
            self.assertIn('logo-inverse.svg',body,path)
            self.assertNotIn('brightness(0) invert(1)',body,path)
    def test_client_pages_never_link_the_owner_workspace(self):
        for path in ('/signup','/signin'):
            body=self.client.get(path).get_data(as_text=True)
            self.assertNotIn('Sign in to the workspace',body,path)
            self.assertNotIn('Studio owner?',body,path)

if __name__=='__main__':unittest.main()
