"""End-to-end Revenue OS: canonical objects, conversation intent, no invented proposals."""
import unittest

import tests.test_app as _appmod
from tests.test_app import module


class ClassifyTests(unittest.TestCase):
    def test_pricing_and_unknown(self):
        from web.revenue_os import classify_reply, ACTIONS
        intent, _ = classify_reply('How much would something like this cost?')
        self.assertEqual(intent, 'pricing')
        self.assertEqual(ACTIONS[intent], 'send_proposal')
        intent, _ = classify_reply('asdf')
        self.assertEqual(intent, 'unknown')
        intent, _ = classify_reply('unsubscribe me please')
        self.assertEqual(intent, 'unsubscribe')


class RevenueOsJourney(unittest.TestCase):
    def setUp(self):
        _appmod.ProspectTests.setUp(self)

    def tearDown(self):
        _appmod.ProspectTests.tearDown(self)

    def test_funnel_does_not_count_projects_as_proposals(self):
        r = self.client.get('/api/opportunity/funnel')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data['counts']['proposal'], 0)
        self.assertEqual(data['counts']['project'], 0)
        self.assertIn('generated_proposals', data['disclaimer'])
        ids = [s['id'] for s in data['steps']]
        self.assertEqual(ids[0], 'lead')
        self.assertIn('proposal', ids)
        self.assertIn('contract', ids)
        self.assertIn('delivered', ids)

        # A project on its own must not inflate proposals.
        with module.db() as c:
            c.execute(
                "INSERT INTO projects(id,title,stage,created,updated) VALUES(?,?,?,?,?)",
                ('proj1', 'Lone project', 'Draft', module.now(), module.now()),
            )
        data = self.client.get('/api/opportunity/funnel').get_json()
        self.assertEqual(data['counts']['project'], 1)
        self.assertEqual(data['counts']['proposal'], 0)

    def test_discover_to_reply_to_proposal(self):
        # 1. Save a lead
        r = self.client.post('/api/leads', json={
            'name': 'Sunrise Bakery', 'city': 'Lagos', 'category': 'Bakery',
            'email': 'hello@sunrise.test', 'phone': '+2348000000000',
        })
        self.assertIn(r.status_code, (200, 201))
        leads = self.client.get('/api/state').json['leads']
        self.assertTrue(leads)
        lead = leads[0]
        lid = lead['id']

        # 2. Opportunity report from stored evidence (no live fetch)
        r = self.client.post(f'/api/opportunity/lead/{lid}/run', json={'live': False})
        self.assertEqual(r.status_code, 200)
        report = r.get_json()['report']
        self.assertIn('score', report)
        self.assertTrue(report.get('token'))

        funnel = self.client.get('/api/os/funnel').get_json()['counts']
        self.assertEqual(funnel['lead'], 1)
        self.assertEqual(funnel['opportunity'], 1)
        self.assertEqual(funnel['proposal'], 0)
        self.assertEqual(funnel['conversation'], 0)

        # 3. Prototype + proposal
        r = self.client.post(f'/api/platform/lead/{lid}/prototype', json={})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json().get('url', '').startswith('/p/'))

        r = self.client.post(f'/api/platform/lead/{lid}/proposal', json={})
        self.assertEqual(r.status_code, 200)
        prop = r.get_json()
        self.assertTrue(prop['url'].startswith('/proposal/'))
        self.assertIn('Price not set', self.client.get(prop['url']).get_data(as_text=True))

        funnel = self.client.get('/api/os/funnel').get_json()['counts']
        self.assertEqual(funnel['proposal'], 1)
        self.assertEqual(funnel['project'], 0)
        self.assertEqual(funnel['contract'], 0)

        # 4. Reply → intent → suggested next action (nothing sent)
        r = self.client.post(f'/api/os/lead/{lid}/reply', json={
            'body': 'How much would something like this cost?',
        })
        self.assertEqual(r.status_code, 200)
        intel = r.get_json()
        self.assertEqual(intel['intent'], 'pricing')
        self.assertEqual(intel['suggested_action'], 'send_proposal')
        reply = (intel['suggested_response'] or '').lower()
        self.assertTrue('not put a number' in reply or 'not a quote' in reply)
        self.assertIn('Nothing was sent', intel['note'])

        funnel = self.client.get('/api/os/funnel').get_json()['counts']
        self.assertEqual(funnel['conversation'], 1)

        dossier = self.client.get(f'/api/os/lead/{lid}').get_json()
        self.assertEqual(dossier['conversation']['last_intent'], 'pricing')
        self.assertTrue(dossier['proposal']['url'].startswith('/proposal/'))
        self.assertEqual(dossier['next_action'], 'send_proposal')
        self.assertIn('neither is revenue', (dossier['ranking']['note'] or '').lower())

        # 5. Empty price book must not invent $2,400
        self.assertFalse(any(
            (p.get('amount') not in (None, '', 0))
            for p in (dossier['costs']['packages'] or [])
        ))

    def test_growth_without_delivery_stays_empty(self):
        r = self.client.post('/api/os/growth/refresh', json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['created'], 0)
        inbox = self.client.get('/api/os/growth').get_json()
        self.assertEqual(inbox['count'], 0)

    def test_one_click_advance_and_accept_without_inventing_price(self):
        self.client.post('/api/leads', json={
            'name': 'Ikeja Clinic', 'city': 'Lagos', 'category': 'Clinic',
            'email': 'hello@ikeja.test',
        })
        lid = self.client.get('/api/state').json['leads'][0]['id']
        r = self.client.post(f'/api/os/lead/{lid}/advance', json={})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('proposal', ''.join(data['steps']))
        self.assertTrue(data['proposal_url'].startswith('/proposal/'))
        self.assertFalse(data.get('sent'))

        cmd = self.client.get('/api/os/command').get_json()
        self.assertEqual(cmd['funnel']['counts']['proposal'], 1)
        self.assertEqual(cmd['money']['paid_minor_sum'], 0)
        self.assertTrue(cmd['hottest'])

        metrics = self.client.get('/api/os/metrics').get_json()
        self.assertEqual(metrics['leads'], 1)
        self.assertEqual(metrics['won'], 0)
        self.assertIsNone(metrics['avg_deal_minor'])

        r = self.client.post(f'/api/os/lead/{lid}/accept', json={'package_id': 'growth'})
        self.assertEqual(r.status_code, 200)
        acc = r.get_json()
        self.assertIsNone(acc['amount'])
        self.assertIsNone(acc['invoice_id'])
        self.assertTrue(acc['contract_id'])
        self.assertTrue(acc['project_id'])
        funnel = self.client.get('/api/os/funnel').get_json()['counts']
        self.assertEqual(funnel['contract'], 1)
        self.assertEqual(funnel['project'], 1)
        self.assertEqual(funnel['invoice'], 0)
        self.assertEqual(funnel['paid'], 0)

        thread = self.client.get(f'/api/os/lead/{lid}/thread').get_json()
        stages = [e['stage'] for e in thread['events']]
        self.assertIn('opportunity', stages)
        self.assertIn('proposal', stages)
        self.assertIn('contract', stages)
        self.assertTrue(thread['evidence'])
        self.assertIsNone((thread['commercial'] or {}).get('estimated_value'))

    def test_command_center_empty_workspace_is_zero(self):
        cmd = self.client.get('/api/os/command').get_json()
        self.assertEqual(cmd['funnel']['counts']['lead'], 0)
        self.assertEqual(cmd['happened'], [])
        self.assertEqual(cmd['attention']['replies'], [])
        self.assertEqual(cmd['money']['paid_minor_sum'], 0)

    def test_client_revenue_os_scopes_legacy_commercial_rows_by_lead_owner(self):
        # Legacy contracts/projects/invoices do not have owner_user_id; the OS
        # must scope them through their associated lead.
        with module.db() as c:
            c.execute(
                "INSERT INTO leads(id,source_key,name,category,city,created,updated,owner_user_id) "
                "VALUES(?,?,?,?,?,?,?,?)",
                ('lead-a','a','Client A','Bakery','Lagos',module.now(),module.now(),'client-a'),
            )
            c.execute(
                "INSERT INTO leads(id,source_key,name,category,city,created,updated,owner_user_id) "
                "VALUES(?,?,?,?,?,?,?,?)",
                ('lead-b','b','Client B','Bakery','Lagos',module.now(),module.now(),'client-b'),
            )
            c.execute(
                "INSERT INTO projects(id,title,lead_id,stage,created,updated) VALUES(?,?,?,?,?,?)",
                ('proj-a','A project','lead-a','Delivered',module.now(),module.now()),
            )
            c.execute(
                "INSERT INTO projects(id,title,lead_id,stage,created,updated) VALUES(?,?,?,?,?,?)",
                ('proj-b','B project','lead-b','Delivered',module.now(),module.now()),
            )
        with self.client.session_transaction() as sess:
            sess['client_id'] = 'client-a'
            sess['role'] = 'client'
        funnel = self.client.get('/api/os/funnel').get_json()['counts']
        self.assertEqual(funnel['project'], 1)
        self.assertEqual(funnel['delivered'], 1)
        self.assertEqual(self.client.get('/api/os/growth').get_json()['count'], 0)
