"""Private per-client workspaces: one client's records stay invisible to another.

Owner and anonymous local sessions keep the full studio view; clients see
only rows stamped with their own user id.
"""
from tests.test_app import module
from tests.test_billing import BillingBase, future


class SwitchedBase(BillingBase):
    def switch_owner(self, password=None):
        import hashlib
        with self.client.session_transaction() as s:
            s.pop('client_id', None)
            s.pop('role', None)
            s['owner'] = True
            if password:
                s['revision'] = hashlib.sha256(password.encode()).hexdigest()
            s['csrf'] = 'test-csrf'
from tests.test_crew import wait_for


class IsolationTests(SwitchedBase):
    def make_named(self, cid, email, tier='starter'):
        with module.db() as c:
            c.execute('INSERT OR REPLACE INTO users(id,email,password_hash,name,role,is_active,created,updated) '
                      'VALUES(?,?,?,?,?,?,?,?)',
                      (cid, email, 'x', cid.title(), 'client', 1, module.now(), module.now()))
            c.execute('UPDATE users SET tier=?,tier_expires=? WHERE id=?', (tier, future(), cid))
        with self.client.session_transaction() as s:
            s.clear()
            s['client_id'] = cid
            s['role'] = 'client'
            s['csrf'] = 'test-csrf'

    def own_lead(self, lid, name, owner):
        with module.db() as c:
            c.execute('INSERT OR REPLACE INTO leads(id,source_key,name,stage,token,created,updated,owner_user_id) '
                      'VALUES(?,?,?,?,?,?,?,?)',
                      (lid, 'k-' + lid, name, 'New', 't-' + lid, module.now(), module.now(), owner))

    def test_lead_crud_and_export_are_private(self):
        self.make_named('ada', 'ada@example.test')
        r = self.client.post('/api/leads', json={'name': 'Ada Bakery'}, headers=self.csrf())
        self.assertEqual(r.status_code, 200)
        with module.db() as c:
            lid = c.execute("SELECT id FROM leads WHERE name='Ada Bakery'").fetchone()['id']
        self.assertIn('Ada Bakery', [l['name'] for l in self.client.get('/api/state').get_json()['leads']])
        self.make_named('bob', 'bob@example.test')
        self.assertNotIn('Ada Bakery', [l['name'] for l in self.client.get('/api/state').get_json()['leads']])
        self.assertEqual(self.client.patch(f'/api/leads/{lid}', json={'stage': 'Won'},
                                           headers=self.csrf()).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/leads/{lid}', headers=self.csrf()).status_code, 404)
        self.assertNotIn('Ada Bakery', self.client.get('/api/export').data.decode())
        # Owner still sees everything.
        self.switch_owner()
        self.assertIn('Ada Bakery', [l['name'] for l in self.client.get('/api/state').get_json()['leads']])

    def test_jobs_and_map_scans_are_private(self):
        self.own_lead('L1', 'Ada Bakery', 'ada')
        with module.db() as c:
            c.execute('INSERT INTO jobs(id,state,locations,category,progress,total,added,checked,message,created,updated,owner_user_id) '
                      "VALUES('J1','queued','[]','Bakery',0,0,0,0,'m',?,?,?)",
                      (module.now(), module.now(), 'ada'))
            c.execute('INSERT INTO map_scans(id,label,category,bounds,state,created,updated,owner_user_id) '
                      "VALUES('S1','Ada Area','Bakery','[]','queued',?,?,?)",
                      (module.now(), module.now(), 'ada'))
        self.make_named('bob', 'bob@example.test')
        state = self.client.get('/api/state').get_json()
        self.assertEqual(state['jobs'], [])
        self.assertEqual(self.client.get('/api/map/state').get_json()['scans'], [])
        # Bob's cancel does not touch Ada's job.
        self.assertEqual(self.client.post('/api/jobs/J1/cancel', headers=self.csrf()).status_code, 200)
        with module.db() as c:
            self.assertEqual(c.execute("SELECT state FROM jobs WHERE id='J1'").fetchone()['state'], 'queued')
        self.make_named('ada', 'ada@example.test')
        self.assertEqual(len(self.client.get('/api/state').get_json()['jobs']), 1)
        self.assertEqual(len(self.client.get('/api/map/state').get_json()['scans']), 1)

    def test_quality_and_analytics_are_private(self):
        self.own_lead('A1', 'Ada One', 'ada')
        self.own_lead('A2', 'Ada Two', 'ada')
        self.own_lead('O1', 'Studio One', None)
        self.own_lead('O2', 'Studio Two', None)
        with module.db() as c:
            c.execute("UPDATE leads SET phone='+10000000001' WHERE id IN ('A1','A2')")
            c.execute("UPDATE leads SET phone='+20000000002' WHERE id IN ('O1','O2')")
        self.make_named('ada', 'ada@example.test')
        pairs = self.client.get('/api/quality').get_json()['duplicates']
        self.assertEqual(len(pairs), 1)
        self.assertEqual(set([pairs[0]['first'], pairs[0]['second']]), {'A1', 'A2'})
        totals = self.client.get('/api/analytics?days=7').get_json()['totals']
        self.assertEqual(totals['leads'], 2)
        activity = self.client.get('/api/analytics?days=7').get_json()['activity']
        self.assertEqual(activity, [])

    def test_outbox_filtered_by_client_email(self):
        self.make_named('ada', 'ada@example.test', tier='pro')
        with module.db() as c:
            for oid, to in (('M1', 'ada@example.test'), ('M2', 'stranger@example.test')):
                c.execute('INSERT OR REPLACE INTO mail_outbox VALUES(?,?,?,?,?,?,?)',
                          (oid, to, 'Hi', 'body', '', module.now(), 'queued'))
        outbox = self.client.get('/api/outbox').get_json()['outbox']
        self.assertEqual([m['id'] for m in outbox], ['M1'])
        self.assertEqual(self.client.get('/api/outbox/M2').status_code, 404)

    def test_contracts_are_owner_only_for_clients(self):
        self.make_named('ada', 'ada@example.test')
        self.assertEqual(self.client.get('/api/contracts').status_code, 403)
        r = self.client.post('/api/contracts', json={'title': 'T', 'client': 'C'},
                             headers=self.csrf())
        self.assertEqual(r.status_code, 403)
        # Anonymous local sessions keep working (owner tooling, tests).
        with self.client.session_transaction() as s:
            s.clear()
        self.assertEqual(self.client.get('/api/contracts').status_code, 200)

    def test_audit_pdf_respects_lead_ownership(self):
        self.own_lead('A1', 'Ada Bakery', 'ada')
        self.own_lead('O1', 'Studio Secret', None)
        self.make_named('ada', 'ada@example.test')
        self.assertEqual(self.client.get('/api/documents/audit/A1.pdf').status_code, 200)
        self.assertEqual(self.client.get('/api/documents/audit/O1.pdf').status_code, 404)

    def test_crew_runs_are_stamped_and_private(self):
        self.make_named('ada', 'ada@example.test', tier='pro')
        r = self.client.post('/api/crew/run',
                             json={'mode': 'campaign', 'fixtures': True, 'limit': 2},
                             headers=self.csrf())
        self.assertEqual(r.status_code, 200, r.data[:300])
        run_id = r.get_json()['run_id']
        wait_for(self.client)
        detail = self.client.get(f'/api/crew/runs/{run_id}').get_json()['run']
        self.assertEqual(detail['started_by'], 'client:ada')
        self.assertEqual(detail['params'].get('owner_user_id'), 'ada')
        state = self.client.get('/api/crew').get_json()
        self.assertTrue(all(x['started_by'] == 'client:ada' for x in state['runs']))
        self.assertEqual(state['threads'], [])
        # Another client cannot see or cancel Ada's run.
        self.make_named('bob', 'bob@example.test', tier='pro')
        self.assertEqual(self.client.get(f'/api/crew/runs/{run_id}').status_code, 404)
        self.assertEqual(self.client.post(f'/api/crew/runs/{run_id}/cancel',
                                          headers=self.csrf()).status_code, 404)
        # Fixture purge is owner-only.
        self.assertEqual(self.client.post('/api/crew/demo/purge',
                                          headers=self.csrf()).status_code, 403)

    def test_review_links_follow_lead_ownership(self):
        self.own_lead('A1', 'Ada Bakery', 'ada')
        self.own_lead('O1', 'Studio Secret', None)
        with module.db() as c:
            for link_id, lead in (('RL1', 'A1'), ('RL2', 'O1')):
                c.execute('INSERT OR REPLACE INTO review_links(id,token,lead_id,created) VALUES(?,?,?,?)',
                          (link_id, 'tok-' + link_id, lead, module.now()))
        self.make_named('ada', 'ada@example.test', tier='pro')
        links = self.client.get('/api/review-links').get_json()['links']['links']
        ids = [l['id'] for l in links]
        self.assertIn('RL1', ids)
        self.assertNotIn('RL2', ids)
