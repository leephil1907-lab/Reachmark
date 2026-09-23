"""Chief — the chat-driven crew chief: parsing, skills and the console route."""
import json
from unittest.mock import patch

from agents.agent_chief import answer, parse, resolve_lead
from tests.test_crew import CrewBase
from tests.test_app import module


class ParseTests(CrewBase):
    def test_commands_and_aliases(self):
        self.assertEqual(parse('audit Sunrise Bakery'), ('audit', 'Sunrise Bakery'))
        self.assertEqual(parse('  STATUS  '), ('status', ''))
        self.assertEqual(parse('check Acme'), ('audit', 'Acme'))
        self.assertEqual(parse('preview Acme'), ('concept', 'Acme'))
        self.assertEqual(parse('hi'), ('help', ''))
        self.assertEqual(parse(''), ('', ''))

    def test_unknown_first_word_passes_through(self):
        self.assertEqual(parse('tell me a joke')[0], 'tell')


class ResolveTests(CrewBase):
    def _lead(self, lid, name):
        with module.db() as c:
            c.execute('INSERT INTO leads(id,source_key,name,category,city,stage,token,created,updated) '
                      'VALUES(?,?,?,?,?,?,?,?,?)',
                      (lid, lid, name, 'Bakery', 'Austin', 'New', f'tok-{lid}',
                       module.now(), module.now()))

    def test_exact_id_name_and_misses(self):
        self._lead('r1', 'Sunrise Bakery')
        lead, _ = resolve_lead(module.db, 'r1')
        self.assertEqual(lead['name'], 'Sunrise Bakery')
        lead, _ = resolve_lead(module.db, 'sunrise')
        self.assertEqual(lead['id'], 'r1')
        self.assertIsNone(resolve_lead(module.db, 'nope')[0])
        self.assertIsNone(resolve_lead(module.db, '')[0])

    def test_ambiguous_names_ask(self):
        self._lead('r1', 'Sunrise Bakery')
        self._lead('r2', 'Sunrise Dental')
        self.assertIsNone(resolve_lead(module.db, 'sunrise')[0])
        self.assertIn('Several match', resolve_lead(module.db, 'sunrise')[1])


class ChiefRouteTests(CrewBase):
    def _lead(self, **kw):
        row = {'id': 'c1', 'source_key': 'c1', 'name': 'Sunrise Bakery',
               'category': 'Bakery', 'city': 'Austin', 'stage': 'New',
               'token': 'ctok1', 'website': ''}
        row.update(kw)
        with module.db() as c:
            c.execute('INSERT OR REPLACE INTO leads(id,source_key,name,category,city,stage,token,website,created,updated) '
                      'VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (row['id'], row['source_key'], row['name'], row['category'],
                       row['city'], row['stage'], row['token'], row['website'],
                       module.now(), module.now()))
        return row

    def _audit(self, lead_id, brand=None, gaps=None):
        from agents.agent_auditor import ensure_tables
        ensure_tables(module.db)
        obs = {'ok': True, 'brand': brand or {}}
        with module.db() as c:
            c.execute('INSERT INTO site_audits(id,lead_id,url,status,observations,gaps,created) '
                      'VALUES(?,?,?,?,?,?,?)',
                      ('ca1', lead_id, 'https://x.test/', 'HAS_WEBSITE',
                       json.dumps(obs), json.dumps(gaps or {}), module.now()))

    def _chat(self, message):
        return self.client.post('/api/crew/chat', json={'message': message})

    def test_empty_message_rejected(self):
        self.assertEqual(self._chat('   ').status_code, 400)

    def test_help_and_status(self):
        self.assertIn('audit <name>', self._chat('help').get_json()['reply'])
        self.assertIn('businesses saved', self._chat('status').get_json()['reply'])

    def test_leads_lists_fixtures(self):
        self._lead()
        reply = self._chat('leads sunrise').get_json()['reply']
        self.assertIn('Sunrise Bakery', reply)
        self.assertIn('Bakery', reply)

    def test_unknown_business_suggests_search(self):
        reply = self._chat('brand Nope').get_json()['reply']
        self.assertIn('No saved business matches', reply)

    def test_brand_reports_harvest(self):
        lead = self._lead()
        self._audit(lead['id'], brand={'theme_color': '#7a2f1b', 'colors': ['#7a2f1b'],
                                       'logo': 'https://cdn.test/l.png', 'logo_source': 'og:logo',
                                       'images': [{'url': 'https://cdn.test/i.jpg', 'alt': 'Loaves'}],
                                       'fonts': ['Fraunces']})
        reply = self._chat('brand sunrise').get_json()['reply']
        for needle in ('#7a2f1b', 'https://cdn.test/l.png', 'Loaves', 'Fraunces'):
            self.assertIn(needle, reply)

    def test_brand_without_audit_points_to_audit(self):
        self._lead()
        self.assertIn('say “audit', self._chat('brand sunrise').get_json()['reply'])

    def test_concept_returns_link_and_theme(self):
        lead = self._lead()
        self._audit(lead['id'], brand={'theme_color': '#7a2f1b'})
        reply = self._chat('concept sunrise').get_json()['reply']
        self.assertIn('/preview/ctok1', reply)
        self.assertIn('#7a2f1b', reply)
        self.assertIn('photos 6/6', reply)

    def test_gaps_without_audit_points_to_audit(self):
        self._lead()
        self.assertIn('say “audit', self._chat('gaps sunrise').get_json()['reply'])

    def test_gaps_reports_ranking(self):
        lead = self._lead()
        self._audit(lead['id'], gaps={'gaps': [{'key': 'no_viewport', 'weight': 2,
                                                'reason': 'No viewport meta tag.',
                                                'source': 'Measured on page'}],
                                      'score': 2, 'tier': 'watch'})
        reply = self._chat('gaps sunrise').get_json()['reply']
        self.assertIn('No viewport meta tag', reply)
        self.assertIn('watch', reply)

    def test_audit_offline_for_unlisted_lead(self):
        self._lead()
        reply = self._chat('audit sunrise').get_json()['reply']
        self.assertIn('NOT_LISTED', reply)

    def test_showcase_lists_trades(self):
        reply = self._chat('showcase').get_json()['reply']
        self.assertIn('food: full (6/6 photos)', reply)
        self.assertIn('pro: planned', reply)

    def test_freeform_uses_model_then_falls_back(self):
        with patch('web.ai_provider.safe_complete', return_value=('At once, boss.', {})):
            self.assertIn('At once', self._chat('sing a song').get_json()['reply'])
        with patch('web.ai_provider.safe_complete', return_value=(None, {})):
            self.assertIn('Say “help”', self._chat('sing a song').get_json()['reply'])

    def test_chief_answers_never_raise(self):
        self.assertIsInstance(answer(module.db, module.now, 'audit'), str)

    def test_roster_lists_chief_with_working_handler(self):
        import importlib
        from crew.crew import AGENTS
        chief = next(a for a in AGENTS if a['id'] == 'chief')
        mod, fn = chief['handler'].split(':')

        class StubCtx:
            params = {'message': 'status'}
            receipts = []
            db = staticmethod(module.db)
            now = staticmethod(module.now)

            def settings(self):
                return {'public_base_url': 'https://x.test'}

            def receipt(self, kind, detail, **kw):
                self.receipts.append((kind, detail))

        out = getattr(importlib.import_module(mod), fn)(StubCtx())
        self.assertIn('businesses saved', out['reply'])

    def test_workspace_shows_chat_console(self):
        body = self.client.get('/workspace').data.decode()
        for needle in ('chief-log', 'chief-form', 'crew-chat.js', 'Talk to Chief'):
            self.assertIn(needle, body)
