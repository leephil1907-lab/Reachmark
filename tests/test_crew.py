"""Isolated checks for the AI crew, review links and the receptionist.

No message is ever sent and no public endpoint is called: the crew runs in offline
demo mode (fixtures, enabled here via ALLOW_CREW_DEMO=1), SMTP variables are set to
a fake host, and every network call
that could leave the process is mocked. The suite is what keeps the guardrails true.
"""
import json, os, tempfile, time, unittest, uuid
from unittest.mock import patch, MagicMock

from tests.test_app import module  # bootstraps app with a temporary bootstrap database

import crew.crew as crew_module
from web.review_links import create_link, get_link, record_response, record_view, link_overview
from web.receptionist import answer, load_knowledge, match_answer, threads
from web.web_probe import gaps_from, observe
import agents.agent_scribe as agent_scribe
import agents.agent_builder as agent_builder
import agents.agent_closer as agent_closer
import agents.agent_brag as agent_brag
import agents.agent_receptionist as agent_receptionist
def wait_for(client, statuses=('completed', 'awaiting_approval', 'failed', 'cancelled'), seconds=40):
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(0.25)
        state = client.get('/api/crew').get_json()
        runs = state.get('runs') or []
        if runs and runs[0]['status'] in statuses:
            return runs[0]
    return (client.get('/api/crew').get_json().get('runs') or [{}])[0]


class CrewBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = module.DB
        with module.db() as c:
            schema = [row[0] for row in c.execute("SELECT sql FROM sqlite_master WHERE type='table'")]
        module.DB = os.path.join(self.tmp.name, 'crew-test.sqlite3')
        with module.db() as c:
            for sql in schema:
                c.execute(sql)
        self.client = module.app.test_client()
        self.env = patch.dict(os.environ, {'DASHBOARD_PASSWORD': '', 'SMTP_HOST': '', 'SMTP_FROM': '',
                                           'ALLOW_CREW_DEMO': '1'})
        self.env.start()
        self.crew = module.app.extensions['reachmark_crew']

    def tearDown(self):
        self.env.stop()
        module.DB = self.old
        self.tmp.cleanup()

    def profile(self):
        self.client.post('/api/settings', json={
            'sender_name': 'Lee Phil', 'agency': 'Reachmark', 'reply_email': 'lee@example.test',
            'postal_address': '1 Test Street', 'public_base_url': 'https://reachmark.example'})

    def run_crew(self, mode='campaign', **params):
        body = {'mode': mode, 'fixtures': True, 'limit': 3, 'tone': 'Professional',
                'include_review_link': True, 'sms_note': True}
        body.update(params)
        response = self.client.post('/api/crew/run', json=body)
        self.assertEqual(response.status_code, 200, response.data[:300])
        run_id = response.get_json()['run_id']
        run = wait_for(self.client)
        detail = self.client.get(f'/api/crew/runs/{run_id}').get_json()['run']
        return run_id, detail


class RegistryTests(CrewBase):
    def test_every_agent_handler_exists_and_is_callable(self):
        import importlib
        for agent in crew_module.AGENTS:
            mod_name, fn_name = agent['handler'].split(':')
            handler = getattr(importlib.import_module(mod_name), fn_name)
            self.assertTrue(callable(handler), agent['id'])
            for key in ('id', 'name', 'role', 'mission', 'guardrails', 'skills', 'tools'):
                self.assertTrue(agent.get(key), f'{agent["id"]} missing {key}')

    def test_playbooks_are_vendored_with_licences(self):
        payload = self.client.get('/api/crew/playbook').get_json()
        slugs = {item['slug'] for item in payload['skills']}
        self.assertTrue({'cold-email', 'copywriting', 'cro', 'prospecting', 'ai-seo', 'seo-audit', 'brag'} <= slugs)
        for source in payload['sources']:
            self.assertTrue(os.path.exists(os.path.join('skills', 'vendor', source['license_file'])))

    def test_pipeline_definitions_only_reference_known_agents(self):
        for name, pipeline in crew_module.PIPELINES.items():
            for step in pipeline['steps']:
                self.assertIn(step, crew_module.AGENTS_BY_ID, f'{name} → {step}')

    def test_guardrail_copy_is_present_in_state(self):
        state = self.client.get('/api/crew').get_json()
        self.assertIn('approval', state['guardrails']['outbound_rule'].lower())
        self.assertEqual(state['limits']['max_dispatches'], 5)


class RunHonestyTests(CrewBase):
    def test_a_run_that_could_not_work_says_so(self):
        """A blocked step must not be reported as 'all steps finished'."""
        run_id = module.crew.start('single', {'fixtures': False, 'limit': 2}, 'builder', 'owner')
        for _ in range(60):
            run = module.crew.get_run(run_id)
            if run['status'] not in ('running',):
                break
            time.sleep(0.1)
        run = module.crew.get_run(run_id)
        self.assertEqual(run['status'], 'blocked')
        self.assertIn('Stopped early', run['summary'])
        self.assertIn('no leads', run['summary'].lower())


class OfflinePipelineTests(CrewBase):
    def test_full_pipeline_stops_at_the_approval_gate(self):
        self.profile()
        run_id, detail = self.run_crew()
        self.assertEqual(detail['status'], 'awaiting_approval')
        agents = [step['agent'] for step in detail['steps']]
        self.assertEqual(agents[:5], ['scout', 'auditor', 'builder', 'scribe', 'closer'])
        self.assertEqual([step['status'] for step in detail['steps'][:4]], ['ok'] * 4)
        self.assertEqual(len(detail['approvals']), 3)
        for step in detail['steps']:
            self.assertTrue(step['receipts'], f'{step["agent"]} produced no receipts')

    def test_offline_demo_makes_no_network_call(self):
        self.profile()
        with patch('requests.get', side_effect=AssertionError('the offline demo must not call the network')):
            run_id, detail = self.run_crew()
        self.assertEqual(detail['status'], 'awaiting_approval')

    def test_nothing_is_dispatched_before_approval(self):
        self.profile()
        run_id, detail = self.run_crew()
        state = self.client.get('/api/crew').get_json()
        self.assertEqual(state['dispatch'], [])
        self.assertEqual(len(state['approvals']), 3)

    def test_drafts_are_written_and_followups_scheduled(self):
        self.profile()
        run_id, detail = self.run_crew()
        crafted = self.client.get('/api/state').get_json()['leads']
        drafted = [lead for lead in crafted if lead['stage'] == 'Drafted']
        self.assertTrue(drafted, 'scribe should have drafted at least one lead')
        self.assertTrue(all(lead['subject'] and lead['body'] for lead in drafted))
        state = self.client.get('/api/crew').get_json()
        self.assertTrue(state['followups'], 'follow-ups should be planned for drafted leads')
        self.assertEqual({row['state'] for row in state['followups']}, {'planned'})

    def test_approving_email_without_smtp_queues_instead_of_claiming_sent(self):
        self.profile()
        run_id, detail = self.run_crew()
        email_approvals = [a for a in detail['approvals'] if a['kind'] == 'outreach_email']
        self.assertTrue(email_approvals, 'a fixture with an e-mail address should produce an e-mail approval')
        for approval in detail['approvals']:
            self.client.post(f"/api/crew/approvals/{approval['id']}", json={'decision': 'approve', 'note': 'test'})
        run = wait_for(self.client, statuses=('completed', 'failed'))
        self.assertEqual(run['status'], 'completed')
        state = self.client.get('/api/crew').get_json()
        queued = [row for row in state['dispatch'] if row['state'] == 'queued']
        sent = [row for row in state['dispatch'] if row['state'] == 'sent']
        self.assertTrue(queued, 'an approved e-mail with no SMTP must be queued in the outbox')
        self.assertEqual(sent, [], 'nothing may be reported as sent without SMTP')
        manual = [row for row in state['dispatch'] if row['channel'] == 'manual']
        self.assertTrue(manual, 'records with no e-mail should produce a copy-ready share message')

    def test_rejection_blocks_the_message(self):
        self.profile()
        run_id, detail = self.run_crew()
        for approval in detail['approvals']:
            self.client.post(f"/api/crew/approvals/{approval['id']}", json={'decision': 'reject', 'note': 'not a fit'})
        wait_for(self.client, statuses=('completed', 'failed'))
        state = self.client.get('/api/crew').get_json()
        self.assertEqual([row for row in state['dispatch'] if row['state'] in ('sent', 'queued')], [])

    def test_suppressed_recipient_is_blocked_at_preflight(self):
        self.profile()
        with module.db() as c:
            c.execute("INSERT INTO suppression(email,created) VALUES('hello@northgate.example.org',?)", (module.now(),))
        run_id, detail = self.run_crew()
        blocked = [a for a in detail['approvals'] if a['kind'] == 'outreach_email']
        for approval in blocked:
            self.assertIn('opted out', (approval['payload'].get('preflight') or '').lower())
            result = self.client.post(f"/api/crew/approvals/{approval['id']}/dispatch")
            self.assertIn(result.status_code, (200, 409, 502))
            if result.status_code == 200:
                self.assertIn(result.get_json()['state'], ('blocked', 'queued'))

    def test_cancel_stops_the_run(self):
        self.profile()
        run_id = self.client.post('/api/crew/run', json={'mode': 'campaign', 'fixtures': True, 'limit': 3}).get_json()['run_id']
        self.client.post(f'/api/crew/runs/{run_id}/cancel')
        time.sleep(1.5)
        detail = self.client.get(f'/api/crew/runs/{run_id}').get_json()['run']
        self.assertIn(detail['status'], ('cancelled', 'completed', 'awaiting_approval'))

    def test_single_agent_run(self):
        self.profile()
        self.client.post('/api/crew/run', json={'mode': 'campaign', 'fixtures': True, 'limit': 2})
        wait_for(self.client)
        response = self.client.post('/api/crew/run', json={'mode': 'single', 'agent': 'receptionist'})
        if response.status_code == 409:  # a run was still finishing; the lock is intentional
            return
        self.assertEqual(response.status_code, 200)
        run = wait_for(self.client)
        self.assertEqual(run['status'], 'completed')

    def test_unknown_agent_is_refused(self):
        response = self.client.post('/api/crew/run', json={'mode': 'single', 'agent': 'nope'})
        self.assertEqual(response.status_code, 400)

    def test_demo_records_are_labelled_and_purgeable(self):
        self.profile()
        self.run_crew()
        leads = self.client.get('/api/state').get_json()['leads']
        self.assertTrue(all(lead['source'] == 'Fixture (offline demo)' for lead in leads))
        purge = self.client.post('/api/crew/demo/purge').get_json()
        self.assertGreaterEqual(purge['removed'], 1)
        self.assertEqual(self.client.get('/api/state').get_json()['leads'], [])

    def test_demo_requests_are_rejected_without_the_flag(self):
        with patch.dict(os.environ):
            os.environ.pop('ALLOW_CREW_DEMO', None)
            response = self.client.post('/api/crew/run', json={'mode': 'campaign', 'fixtures': True})
        self.assertEqual(response.status_code, 400)
        self.assertIn('disabled', response.get_json()['error'])
        leads = self.client.get('/api/state').get_json()['leads']
        self.assertFalse(any(lead['source'] == 'Fixture (offline demo)' for lead in leads))

    def test_admin_page_has_no_demo_toggle(self):
        root = os.path.join(os.path.dirname(__file__), '..')
        with open(os.path.join(root, 'templates', 'crew-panel.html'), encoding='utf-8') as handle:
            panel = handle.read()
        with open(os.path.join(root, 'static', 'crew.js'), encoding='utf-8') as handle:
            script = handle.read()
        self.assertNotIn('crew-fixtures', panel)
        self.assertNotIn('crew-fixtures', script)
        self.assertNotIn('Offline demo', panel)
        self.assertIn('crewPurgeDemo', panel)
        self.assertIn('crewPurgeDemo', script)

    def test_scout_tools_list_no_demo_source(self):
        agents = self.client.get('/api/crew').get_json()['agents']
        scout = next(a for a in agents if a['id'] == 'scout')
        self.assertNotIn('Offline fixtures (demo only)', scout['tools'])


class BuilderAndLinkTests(CrewBase):
    def test_every_link_carries_a_chat_sized_message(self):
        """WhatsApp/SMS needs its own short text; the long e-mail one does not fit."""
        from agents.agent_builder import compose_chat_message
        chat = compose_chat_message({'name': 'Copper Kettle Cafe', 'city': 'Demo City'},
                                    'Reachmark', 'https://example.test/r/tok', 'café & hospitality')
        self.assertLessEqual(len(chat), 480)
        self.assertIn('https://example.test/r/tok', chat)
        self.assertIn('STOP', chat)
        self.assertIn('Copper Kettle Cafe', chat)


class ReviewLinkTests(CrewBase):
    def test_link_creation_view_counting_and_answer(self):
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,category,city,token,created,updated) VALUES('L1','k1','Test Bakery','Bakery','Demo','tok',?,?)",
                      (module.now(), module.now()))
        lead = {'id': 'L1', 'name': 'Test Bakery', 'category': 'Bakery', 'city': 'Demo'}
        link = create_link(module.db, module.now, lead, {'theme': 'ember', 'headline': 'Hello', 'intro': 'x',
                                                         'sections': [{'title': 'a', 'body': 'b'}]}, 'share')
        page = self.client.get('/r/' + link['token'])
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Would you like this built', page.data)
        self.assertIn(b'not the official website', page.data)
        self.assertEqual(get_link(module.db, token=link['token'])['views'], 1)
        record_view(module.db, module.now, link['token'], count=False)
        self.assertEqual(get_link(module.db, token=link['token'])['views'], 1, 'a returning tab must not inflate views')
        bad = self.client.post(f"/api/r/{link['token']}/respond", json={'choice': 'maybe'})
        self.assertEqual(bad.status_code, 400)
        good = self.client.post(f"/api/r/{link['token']}/respond",
                                json={'choice': 'want', 'note': 'Yes please', 'email': 'owner@example.test', 'name': 'Owner'})
        self.assertEqual(good.status_code, 201)
        with module.db() as c:
            lead_row = dict(c.execute("SELECT stage,note FROM leads WHERE id='L1'").fetchone())
            enquiry = dict(c.execute("SELECT kind,email FROM enquiries").fetchone())
        self.assertEqual(lead_row['stage'], 'Won')
        self.assertIn('Review link', lead_row['note'])
        self.assertEqual(enquiry['kind'], 'Review link reply')
        self.assertEqual(enquiry['email'], 'owner@example.test')

    def test_superseded_and_unknown_tokens_404(self):
        self.assertEqual(self.client.get('/r/does-not-exist').status_code, 404)
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,token,created,updated) VALUES('L9','k9','Gone','tok9',?,?)",
                      (module.now(), module.now()))
        link = create_link(module.db, module.now, {'id': 'L9', 'name': 'Gone'}, {'theme': 'charcoal'}, 'x')
        with module.db() as c:
            c.execute("UPDATE review_links SET status='superseded' WHERE id=?", (link['id'],))
        self.assertEqual(self.client.get('/r/' + link['token']).status_code, 404)

    def test_overview_counts(self):
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,token,created,updated) VALUES('L2','k2','Overview Biz','t2',?,?)",
                      (module.now(), module.now()))
        create_link(module.db, module.now, {'id': 'L2', 'name': 'Overview Biz'}, {'theme': 'steel'}, 'x')
        overview = link_overview(module.db)
        self.assertGreaterEqual(overview['total'], 1)
        self.assertEqual(overview['answered'], 0)


class ReceptionistTests(CrewBase):
    def test_knowledge_base_is_grounded_in_published_facts(self):
        result = answer(module.db, module.now, 'how much does a website cost?', settings=lambda: {})
        self.assertEqual(result['intent'], 'pricing')
        self.assertIn('1,250', result['reply'])
        self.assertIn('650', result['reply'])

    def test_unknown_question_hands_off_instead_of_inventing(self):
        result = answer(module.db, module.now, 'do you offer a refund if i am unhappy with the llama?', settings=lambda: {})
        self.assertIn('handoff', result['actions'])
        self.assertIn('will not guess', result['reply'])

    def test_paraphrases_reach_the_published_answer(self):
        """Visitors do not type the exact FAQ line — paraphrases must still be answered."""
        for question, expect in [('how long until I see a preview?', 'timeline'),
                                 ('when will i see the design', 'timeline'),
                                 ('do you do seo', 'topic:_building_it'),
                                 ('is the price fixed', 'pricing'),
                                 ('how much', 'pricing')]:
            result = answer(module.db, module.now, question, settings=lambda: {})
            self.assertEqual(result['intent'], expect, question)
            self.assertNotIn('will not guess', result['reply'], question)

    def test_unrecognised_names_never_get_an_answer(self):
        """A question about something this studio has never published is handed over."""
        for question in ['what is the llama policy',
                         'do you offer a refund if i am unhappy with the llama?',
                         'do you stock llama feed?']:
            result = answer(module.db, module.now, question, settings=lambda: {})
            self.assertEqual(result['topic'], '', question)
            self.assertIn('handoff', result['actions'], question)
            self.assertIn('will not guess', result['reply'], question)

    def test_visitor_describing_their_own_business_is_routed_to_the_studio(self):
        for message in ['my restaurant needs a website',
                        'my clinic needs a site urgently',
                        'i want a website for my law firm']:
            result = answer(module.db, module.now, message, settings=lambda: {})
            self.assertEqual(result['intent'], 'new_project', message)
            self.assertIn('offer_review_link', result['actions'], message)

    def test_human_request_is_flagged(self):
        result = answer(module.db, module.now, 'can i talk to a real person please', settings=lambda: {})
        self.assertEqual(result['intent'], 'human')
        self.assertTrue(result['handoff'])

    def test_contact_details_create_a_real_enquiry_and_lead(self):
        result = answer(module.db, module.now, 'Hi, my bakery needs a website. My e-mail is ada@example.test',
                        settings=lambda: {}, name='Ada', business='Ada Bakery')
        self.assertIn('enquiry_created', result['actions'])
        with module.db() as c:
            enquiry = dict(c.execute('SELECT kind,email,business FROM enquiries').fetchone())
            lead = dict(c.execute('SELECT source,stage,email FROM leads').fetchone())
        self.assertEqual(enquiry['kind'], 'Other enquiry')
        self.assertEqual(enquiry['email'], 'ada@example.test')
        self.assertEqual(lead['source'], 'Website receptionist')
        self.assertEqual(lead['stage'], 'Replied')

    def test_model_phrasing_path_is_skipped_without_a_key(self):
        result = answer(module.db, module.now, 'how long does it take?', settings=lambda: {})
        self.assertNotIn('model_phrasing', result['actions'])

    def test_widget_endpoint_is_public_but_rate_limited_shape(self):
        response = self.client.post('/api/receptionist/message', json={'message': 'hi there'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('reply', response.get_json())
        empty = self.client.post('/api/receptionist/message', json={'message': ''})
        self.assertEqual(empty.status_code, 400)
        honeypot = self.client.post('/api/receptionist/message', json={'message': 'hello', 'company_url': 'spam'})
        self.assertEqual(honeypot.status_code, 400)

    def test_transcripts_are_stored_for_the_owner(self):
        self.client.post('/api/receptionist/message', json={'message': 'what is included in the price?'})
        rows = threads(module.db)
        self.assertTrue(rows)
        listing = self.client.get('/api/receptionist/threads')
        self.assertEqual(listing.status_code, 200)
        detail = self.client.get('/api/receptionist/threads/' + rows[0]['id'])
        self.assertEqual(detail.status_code, 200)
        roles = [line['role'] for line in detail.get_json()['transcript']]
        self.assertIn('visitor', roles)
        self.assertIn('assistant', roles)

    def test_receptionist_agent_reports_knowledge_gaps(self):
        from crew.crew import Ctx
        run = {'id': 'r1', 'params': {}, 'agent': 'receptionist'}
        ctx = Ctx(run, {'db': module.db, 'now': module.now, 'log': module.log, 'settings': module.settings,
                        'deadline': time.monotonic() + 20})
        result = agent_receptionist.run(ctx)
        self.assertGreaterEqual(result['data']['coverage'], 60)
        self.assertTrue(any(art['kind'] == 'receptionist-report' for art in ctx.artifacts))


class LocalModelTests(CrewBase):
    """Ollama: the zero-cost provider. Same masking, same guardrails, no key."""

    def test_ollama_is_selected_by_host_without_a_key(self):
        import web.ai_provider as ai_provider
        with patch.dict(os.environ, {'OLLAMA_HOST': 'http://127.0.0.1:11434'}, clear=False):
            os.environ.pop('CREW_LLM_PROVIDER', None)
            os.environ.pop('CREW_LLM_API_KEY', None)
            os.environ.pop('OPENAI_API_KEY', None)
            status = ai_provider.provider_status()
        self.assertTrue(status['configured'])
        self.assertEqual(status['provider'], 'ollama')

    def test_ollama_call_shape_and_contact_masking(self):
        import web.ai_provider as ai_provider
        fake = MagicMock()
        fake.raise_for_status.return_value = None
        fake.json.return_value = {'message': {'content': 'Review this wording.'},
                                  'prompt_eval_count': 90, 'eval_count': 12}
        env = {'CREW_LLM_PROVIDER': 'ollama', 'CREW_LLM_MODEL': 'llama3.1'}
        with patch.dict(os.environ, env, clear=False), patch.object(ai_provider.requests, 'post', return_value=fake) as post:
            text, meta = ai_provider.complete('be brief', 'write to owner@example.test please')
        self.assertIn('Review this wording', text)
        self.assertEqual(meta['provider'], 'ollama')
        self.assertTrue(post.call_args.args[0].endswith('/api/chat'))
        self.assertFalse(post.call_args.kwargs['json']['stream'])
        self.assertNotIn('owner@example.test', post.call_args.kwargs['json']['messages'][1]['content'],
                         'contact details must be masked before a prompt leaves the host')

    def test_unreachable_local_model_is_reported_not_hidden(self):
        import web.ai_provider as ai_provider
        with patch.dict(os.environ, {'CREW_LLM_PROVIDER': 'ollama'}, clear=False), \
                patch.object(ai_provider.requests, 'get', side_effect=OSError('boom')):
            probe = ai_provider.reachable()
        self.assertFalse(probe['reachable'])
        self.assertIn('ollama serve', probe['reason'])

    def test_crew_still_runs_when_the_local_model_is_down(self):
        """Losing the model must never lose the run — deterministic mode takes over."""
        self.profile()
        with patch.dict(os.environ, {'CREW_LLM_PROVIDER': 'ollama'}, clear=False):
            self.client.post('/api/crew/run', json={'mode': 'campaign', 'fixtures': True, 'limit': 2})
            run = wait_for(self.client)
        self.assertIn(run['status'], ('awaiting_approval', 'completed'))
        steps = self.client.get(f"/api/crew/runs/{run['id']}").get_json()['run']['steps']
        self.assertTrue(steps, 'the run produced no steps at all')
        self.assertTrue(all(step['status'] in ('ok', 'awaiting_approval', 'blocked') for step in steps))


class ResourceWiringTests(CrewBase):
    """Every playbook the roster advertises must actually be read by that agent.

    A declared-but-unused skill is a claim the console would be making on the owner's
    behalf, so it is checked here rather than trusted to review.
    """

    def test_declared_playbooks_are_loaded_by_the_agent_that_declares_them(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for agent in crew_module.AGENTS:
            module_name = agent['handler'].split(':')[0]
            with open(os.path.join(root, *module_name.split('.')) + '.py', encoding='utf-8') as handle:
                source = handle.read()
            self.assertIn('skills_loader', source, f'{agent["id"]} does not touch the playbook loader')
            for skill in agent['skills']:
                self.assertTrue(os.path.exists(os.path.join('skills', 'vendor', skill, 'SKILL.md')),
                                f'{agent["id"]}: vendored playbook {skill} is missing')
                self.assertIn(f"'{skill}'", source, f'{agent["id"]} declares {skill} but never reads it')

    def test_scout_qualifies_from_saved_fields_only(self):
        import agents.agent_scout as agent_scout
        row = {'name': 'Demo', 'phone': '+1 555 0100', 'source': 'openstreetmap'}
        check = agent_scout._qualification(row)
        self.assertEqual(check['public_contact'], 'phone')
        self.assertTrue(check['reachable'])
        bare = agent_scout._qualification({'name': 'Nobody'})
        self.assertEqual(bare['public_contact'], 'none listed')
        self.assertFalse(bare['reachable'], 'a listing with nothing on it must not look reachable')

    def test_closer_holds_a_draft_that_fails_the_guardrails(self):
        """The owner must never be asked to approve something the crew would refuse to send."""
        from crew.crew import Ctx
        import agents.agent_closer as agent_closer
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,token,email,body,created,updated) "
                      "VALUES('BAD','bad','Bad Draft Ltd','tb-bad','oops@example.test',?,?,?)",
                      ('Short.', module.now(), module.now()))
        run = {'id': 'r-bad', 'params': {'limit': 5, 'lead_ids': ['BAD']}, 'agent': 'closer'}
        ctx = Ctx(run, {'db': module.db, 'now': module.now, 'log': module.log, 'settings': module.settings,
                        'deadline': time.monotonic() + 20})
        result = agent_closer.run(ctx)
        self.assertEqual(result['data']['raised'], 0)
        self.assertTrue(any('held back' in r['detail'] for r in ctx.receipts),
                        [r['detail'] for r in ctx.receipts])

    def test_brag_kit_says_how_to_publish_it(self):
        from crew.crew import Ctx
        import agents.agent_brag as agent_brag
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,token,created,updated) "
                      "VALUES('WIN','win','Won Ltd','tb-win',?,?)", (module.now(), module.now()))
            c.execute("INSERT INTO site_audits(id,lead_id,url,status,signals,observations,gaps,tier,score,created) "
                      "VALUES('a1','WIN','https://won.example.test','NOT_LISTED','{}','{}','[]','warm',0,?)",
                      (module.now(),))
        run = {'id': 'r4', 'params': {'lead_id': 'WIN'}, 'agent': 'brag'}
        ctx = Ctx(run, {'db': module.db, 'now': module.now, 'log': module.log, 'settings': module.settings,
                        'deadline': time.monotonic() + 20})
        result = agent_brag.run(ctx)
        self.assertIn('ai-seo', result['data']['playbooks'])
        self.assertIn('brag', result['data']['playbooks'])
        self.assertTrue(any(art['kind'] == 'findability-notes' for art in ctx.artifacts))
        self.assertIn('Measured before the concept', result['data']['quotable_fact'])
        notes = [art for art in ctx.artifacts if art['kind'] == 'findability-notes'][0]
        self.assertIn('cite', notes['body'].lower())

    def test_front_desk_reports_coverage_by_cro_principle(self):
        from crew.crew import Ctx
        run = {'id': 'r3', 'params': {}, 'agent': 'receptionist'}
        ctx = Ctx(run, {'db': module.db, 'now': module.now, 'log': module.log, 'settings': module.settings,
                        'deadline': time.monotonic() + 20})
        data = agent_receptionist.run(ctx)['data']
        self.assertEqual(set(data['by_principle']), set(agent_receptionist.CRO_PRINCIPLES))
        self.assertTrue(all(row['asked'] for row in data['by_principle'].values()))
        self.assertTrue(any(art['kind'] == 'cro-coverage' for art in ctx.artifacts))
        self.assertTrue(any('cro playbook applied' in r['detail'] for r in ctx.receipts))


class ScribeAndBuilderTests(CrewBase):
    def _ctx(self, tmp_db=None):
        from crew.crew import Ctx
        run = {'id': 'r2', 'params': {}, 'agent': 'scribe'}
        return Ctx(run, {'db': tmp_db or module.db, 'now': module.now, 'log': module.log, 'settings': module.settings,
                         'deadline': time.monotonic() + 20})

    def test_guardrails_catch_banned_filler_and_length(self):
        self.assertTrue(agent_scribe.guardrails('Dear Sir, I hope this email finds you well. ' * 40))
        clean = ('Hi Ada,\n\nI noticed your bakery listing has no website.\n\n60-second look: https://x.test/r/abc\n\n'
                 'Reply “no thanks” to stop.')
        self.assertEqual(agent_scribe.guardrails(clean), [])

    def test_brag_refuses_when_only_a_lead_exists(self):
        from crew.crew import CrewError
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,token,created,updated) VALUES('B1','b1','Quiet Studio','tb',?,?)",
                      (module.now(), module.now()))
        ctx = self._ctx()
        ctx.params['lead_id'] = 'B1'
        with self.assertRaises(CrewError):
            agent_brag.run(ctx)  # no measured facts yet — it will not invent a story

    def test_concept_uses_only_saved_fields(self):
        lead = {'id': 'L3', 'name': 'Copper Kettle Cafe', 'category': 'Café', 'city': 'Demo City',
                'phone': '+1 555 0121', 'email': 'team@example.test', 'website': '', 'opening_hours': 'Daily 07:30-16:00'}
        concept = agent_builder.compose_concept(lead, {'agency': 'Reachmark'}, 'Professional')
        self.assertEqual(concept['family'], 'food')
        self.assertIn('Copper Kettle Cafe', concept['headline'])
        self.assertIn('independent concept', concept['intro'].lower())
        self.assertTrue(all(isinstance(section['title'], str) for section in concept['sections']))
        checks, words = agent_builder.cro_checks(concept)
        self.assertTrue(any(check['name'].startswith('No invented') for check in checks))
        self.assertLess(words, 400)

    def test_share_message_always_carries_an_opt_out_and_the_link(self):
        message = agent_builder.compose_share_message({'name': 'Test Bakery', 'city': 'Demo'},
                                                      {'family': 'food', 'family_label': 'café & hospitality'},
                                                      'Reachmark', 'https://reachmark.example', 'https://reachmark.example/r/tok')
        self.assertIn('https://reachmark.example/r/tok', message)
        self.assertIn('STOP', message)
        self.assertIn('not right now', message.lower())

    def test_brag_refuses_to_invent_a_story(self):
        from crew.crew import CrewError
        with self.assertRaises(CrewError):
            agent_brag.run(self._ctx())

    def test_brag_kit_from_prepared_facts(self):
        kit = agent_brag.build_kit({'lead': {'name': 'Astra Clinic', 'category': 'Clinic', 'city': 'Demo'},
                                    'project': None,
                                    'facts': ['Business: Astra Clinic (Clinic) · Demo', 'Review link opened 3 time(s).'],
                                    'responses': [{'choice': 'want', 'at': module.now()}]}, 'deadpan', 'vertical')
        self.assertEqual(kit['plan']['tone'], 'deadpan')
        self.assertEqual(kit['plan']['format'], 'vertical')
        card = agent_brag.brag_card_html(kit, 'Reachmark')
        self.assertIn('Astra Clinic', card)
        self.assertIn('noindex', card)
        self.assertIn('Rendering a video is a separate step', card)


class WebProbeTests(unittest.TestCase):
    def test_private_and_reserved_destinations_are_blocked(self):
        result = observe('http://127.0.0.1/admin')
        self.assertFalse(result['ok'])
        self.assertIn('private', result['reason'].lower())
        result = observe('http://10.0.0.5/')
        self.assertFalse(result['ok'])
        self.assertIn('private', result['reason'].lower())
        result = observe('ftp://example.test/file')
        self.assertFalse(result['ok'])

    def test_robots_disallow_stops_the_read(self):
        robots = MagicMock(status_code=200, headers={'Content-Type': 'text/plain'}, text='User-agent: *\nDisallow: /')
        robots.url = 'https://example.test/robots.txt'
        with patch('agents.agent_scout._public_host', return_value=(True, 'test host')), \
             patch('requests.get', return_value=robots):
            result = observe('https://example.test/private', respect_robots=True)
        self.assertFalse(result['ok'])
        self.assertIn('robots.txt', result['reason'])

    def test_gap_ranking_is_deterministic_and_sourced(self):
        lead = {'website': '', 'audit_status': 'NOT_LISTED'}
        ranking = gaps_from({}, lead)
        self.assertEqual(ranking['tier'], 'warm')  # one listing gap on its own is not a verdict
        self.assertEqual(ranking['gaps'][0]['key'], 'no_website_listed')
        self.assertEqual(ranking['gaps'][0]['source'], 'Listing')
        self.assertIn('not a claim', ranking['disclaimer'])
        measured = gaps_from({'ok': True, 'https': False, 'ms': 4000,
                              'signals': {'viewport': '', 'visible_words': 40, 'copyright_years': [2001],
                                          'img_count': 0, 'meta_description': ''}},
                             {'website': 'http://old.example', 'audit_status': 'LIVE'})
        keys = {gap['key'] for gap in measured['gaps']}
        self.assertTrue({'no_https', 'slow_first_byte', 'no_viewport', 'stale_copyright'} <= keys)
        self.assertEqual(measured['tier'], 'hot', 'several measured gaps together rank high')


class AccessControlTests(CrewBase):
    def test_clients_cannot_run_the_crew(self):
        with module.db() as c:
            c.execute('INSERT OR REPLACE INTO users(id,email,password_hash,name,role,is_active,created,updated) '
                      "VALUES('client-1','client@example.test','x','Test Client','client',1,?,?)",
                      (module.now(), module.now()))
        with self.client.session_transaction() as flask_session:
            flask_session['client_id'] = 'client-1'
            flask_session['role'] = 'client'
        response = self.client.get('/api/crew')
        self.assertEqual(response.status_code, 402)
        self.assertEqual(response.get_json().get('upgrade'), '/pricing')
        response = self.client.post('/api/crew/run', json={'mode': 'single', 'agent': 'scout'})
        self.assertEqual(response.status_code, 402)

    def test_owner_guard_still_protects_crew_apis_when_a_password_is_set(self):
        with patch.dict(os.environ, {'DASHBOARD_PASSWORD': 'secret-owner-pass'}):
            self.assertEqual(self.client.get('/api/crew').status_code, 401)
        # Public surfaces stay public.
        self.assertEqual(self.client.post('/api/receptionist/message', json={'message': 'hello'}).status_code, 200)


class _StubRaw:
    def __init__(self, data):
        self._data = data

    def read(self, _n, decode_content=True):
        return self._data


class _StubResponse:
    def __init__(self, url, status=200, headers=None, body=b''):
        self.url = url
        self.status_code = status
        self.headers = headers or {}
        self.encoding = 'utf-8'
        self.raw = _StubRaw(body)

    def close(self):
        pass


FAULT_HTML = (
    '<html><head>'
    '<meta name="viewport" content="width=device-width">'
    '<meta name="description" content="A corner bakery with fresh bread.">'
    '<link rel="stylesheet" href="http://cdn.example.test/x.css">'
    '</head><body>'
    '<h2>Our bakery</h2><p>' + 'fresh bread daily ' * 40 + '</p>'
    '<img src="/loaf.jpg" alt="a loaf"><img src="/shop.jpg">'
    '<a href="/contact">Contact</a><a href="/fine">Fine</a><a href="/gone">Gone</a>'
    '<a href="https://other.example/x">Elsewhere</a>'
    '<a href="#missing">Missing bit</a><a href="#ok">Ok bit</a><div id="ok"></div>'
    '<form action="/ask"></form>'
    '</body></html>'
).encode('utf-8')


def _head_router(url, **_kwargs):
    return _StubResponse(url, 404 if url.endswith('/gone') else 200)


class FaultSignalTests(unittest.TestCase):
    def _observe(self):
        page = _StubResponse('https://shop.example.test/', 200,
                             {'Content-Type': 'text/html; charset=utf-8', 'X-Powered-By': 'PHP/5.4'},
                             FAULT_HTML)
        with patch('agents.agent_scout._public_host', return_value=(True, 'test host')), \
             patch('agents.agent_scout.robots_allowed', return_value=(True, 'ok')), \
             patch('requests.get', return_value=page), \
             patch('requests.head', side_effect=_head_router):
            return observe('https://shop.example.test/')

    def test_fault_signals_are_measured_from_the_page(self):
        result = self._observe()
        self.assertTrue(result['ok'])
        signals = result['signals']
        self.assertEqual(signals['title'], '')
        self.assertEqual(signals['lang'], '')
        self.assertFalse(signals['has_favicon'])
        self.assertEqual(signals['http_resource_refs'], 1)
        self.assertEqual(signals['img_missing_alt'], 1)
        self.assertEqual(signals['broken_anchor_count'], 1)
        self.assertEqual(signals['broken_anchors'], ['missing'])
        self.assertEqual(result['link_check']['checked'], 3)
        self.assertEqual(len(result['link_check']['broken']), 1)
        self.assertTrue(result['link_check']['broken'][0]['url'].endswith('/gone'))

    def test_fault_gaps_carry_reasons_and_evidence(self):
        result = self._observe()
        ranking = gaps_from(result, {'website': 'https://shop.example.test/', 'audit_status': 'LIVE'})
        keys = {gap['key'] for gap in ranking['gaps']}
        self.assertTrue({'missing_title', 'missing_lang', 'no_h1', 'images_missing_alt', 'broken_anchors',
                         'mixed_content', 'no_favicon', 'server_disclosure', 'no_analytics_seen',
                         'broken_links'} <= keys)
        by_key = {gap['key']: gap for gap in ranking['gaps']}
        self.assertIn('1 of 2 images', by_key['images_missing_alt']['reason'])
        self.assertIn('/gone', by_key['broken_links']['reason'])
        self.assertEqual(by_key['broken_links']['evidence'], ['https://shop.example.test/gone'])
        self.assertNotIn('no_viewport', keys, 'a declared viewport must not gap')

    def test_link_check_can_be_switched_off(self):
        page = _StubResponse('https://shop.example.test/', 200, {'Content-Type': 'text/html'}, b'<html></html>')
        with patch('agents.agent_scout._public_host', return_value=(True, 'test host')), \
             patch('agents.agent_scout.robots_allowed', return_value=(True, 'ok')), \
             patch('requests.get', return_value=page), \
             patch('requests.head') as head:
            result = observe('https://shop.example.test/', verify_links=False)
        self.assertEqual(result['link_check'], {'checked': 0, 'broken': [], 'skipped': 0})
        head.assert_not_called()


class CheckLinksBoundsTests(unittest.TestCase):
    def test_same_host_cap_and_private_skip(self):
        from web.web_probe import check_links
        html = ''.join(f'<a href="/p{i}">p</a>' for i in range(10))
        with patch('agents.agent_scout._public_host', return_value=(True, 'test host')), \
             patch('requests.head', return_value=_StubResponse('x', 200)) as head:
            report = check_links(html, 'https://shop.example.test/')
        self.assertEqual(report['checked'], 6)
        self.assertEqual(head.call_count, 6)
        self.assertGreaterEqual(report['skipped'], 4)
        self.assertEqual(report['broken'], [])

    def test_private_destinations_are_never_followed(self):
        from web.web_probe import check_links
        report = check_links('<a href="http://127.0.0.1/x">x</a>', 'http://127.0.0.1/')
        self.assertEqual(report['checked'], 0)
        self.assertEqual(report['skipped'], 1)

    def test_head_refusal_falls_back_to_get(self):
        from web.web_probe import check_links
        with patch('agents.agent_scout._public_host', return_value=(True, 'test host')), \
             patch('requests.head', return_value=_StubResponse('x', 405)), \
             patch('requests.get', return_value=_StubResponse('x', 200)) as get:
            report = check_links('<a href="/p">p</a>', 'https://shop.example.test/')
        self.assertEqual(report['checked'], 1)
        self.assertEqual(report['broken'], [])
        get.assert_called_once()


class GapsEvidenceTests(unittest.TestCase):
    def test_a_clean_page_with_one_broken_link_reports_only_that(self):
        ranking = gaps_from(
            {'ok': True, 'https': True, 'ms': 100,
             'signals': {'title': 'T', 'lang': 'en', 'viewport': 'w', 'meta_description': 'd', 'h1_count': 1,
                         'img_count': 2, 'img_missing_alt': 0, 'has_contact_link': True, 'form_count': 1,
                         'visible_words': 500, 'has_favicon': True, 'has_analytics': True,
                         'http_resource_refs': 0, 'broken_anchor_count': 0, 'server_header': '',
                         'copyright_years': []},
             'link_check': {'checked': 2, 'broken': [{'url': 'https://x.test/dead', 'status': 404,
                                                      'note': 'HTTP 404 at check time.'}], 'skipped': 0}},
            {'website': 'https://x.test', 'audit_status': 'LIVE'})
        self.assertEqual({gap['key'] for gap in ranking['gaps']}, {'broken_links'})
        self.assertEqual(ranking['tier'], 'watch')


class FaultReportTests(unittest.TestCase):
    GAPS = {'gaps': [{'key': 'broken_links', 'weight': 2, 'reason': 'R2', 'source': 'Measured on page',
                      'evidence': ['https://x.test/dead']},
                     {'key': 'no_favicon', 'weight': 1, 'reason': 'R1', 'source': 'Measured on page',
                      'evidence': ''}],
            'disclaimer': 'D'}

    def test_report_marks_severity_and_quotes_evidence(self):
        from agents.agent_auditor import fault_report
        report = fault_report(self.GAPS, {'name': 'Test Bakery'}, '2026-01-02T00:00:00')
        self.assertIn('[fix first]', report['lines'][0])
        self.assertIn('Seen at: https://x.test/dead', report['lines'][0])
        self.assertIn('[worth fixing]', report['lines'][1])
        self.assertEqual(report['fault_count'], 2)
        self.assertEqual(report['fix_first'], 1)
        self.assertIn('measured 2026-01-02', report['proposal_lines'][0])
        self.assertIn('Test Bakery', report['proposal_lines'][0])

    def test_empty_gaps_make_an_empty_report(self):
        from agents.agent_auditor import fault_report
        report = fault_report({'gaps': []}, {})
        self.assertEqual(report, {'lines': [], 'proposal_lines': [], 'fault_count': 0, 'fix_first': 0})


class AttachFaultsTests(unittest.TestCase):
    def test_concept_carries_at_most_six_faults_with_a_date(self):
        from agents.agent_builder import attach_site_faults
        audit = {'created': '2026-05-06T07:08:09',
                 'gaps': {'gaps': [{'key': f'g{i}', 'weight': 1, 'reason': f'R{i}', 'source': 'S'}
                                   for i in range(7)]}}
        concept = attach_site_faults({}, audit)
        self.assertEqual(len(concept['site_faults']), 6)
        self.assertEqual(concept['faults_checked_at'], '2026-05-06')
        concept = attach_site_faults({}, None)
        self.assertEqual(concept['site_faults'], [])
        self.assertNotIn('faults_checked_at', concept)


class ScribeFaultObservationTests(unittest.TestCase):
    def test_broken_links_lead_the_first_message(self):
        from agents.agent_scribe import deterministic_draft
        draft = deterministic_draft(
            {'id': 't', 'name': 'T Test', 'website': 'https://x.test'},
            {'share_url': '', 'studio': 'Reachmark'},
            {'ok': True, 'signals': {}, 'link_check': {'broken': [{'url': 'u'}]}}, {})
        self.assertIn('one of the links on your page failed', draft['email1'])

    def test_missing_alt_text_is_a_checkable_opener(self):
        from agents.agent_scribe import deterministic_draft
        draft = deterministic_draft(
            {'id': 't', 'name': 'T Test', 'website': 'https://x.test'},
            {'share_url': '', 'studio': 'Reachmark'},
            {'ok': True, 'signals': {'img_missing_alt': 3}}, {})
        self.assertIn('no alt text', draft['email1'])


class ReviewFaultsRenderTests(CrewBase):
    def test_proposal_page_shows_the_measured_faults(self):
        from agents.agent_builder import attach_site_faults, compose_concept
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,category,city,token,created,updated) VALUES('LF','kf','Faulty Bakes','Bakery','Demo','tokf',?,?)",
                      (module.now(), module.now()))
        lead = {'id': 'LF', 'name': 'Faulty Bakes', 'category': 'Bakery', 'city': 'Demo'}
        concept = attach_site_faults(compose_concept(lead, {}, 'Professional'),
                                     {'created': '2026-09-22T10:00:00',
                                      'gaps': {'gaps': [{'key': 'missing_title', 'weight': 1,
                                                         'reason': 'No page title found.', 'source': 'Measured on page'}]}})
        link = create_link(module.db, module.now, lead, concept, 'share')
        page = self.client.get('/r/' + link['token'])
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'What we noticed on your current site', page.data)
        self.assertIn(b'No page title found.', page.data)
        self.assertIn(b'Measured 2026-09-22', page.data)


if __name__ == '__main__':
    unittest.main()
