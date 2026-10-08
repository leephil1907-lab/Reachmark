"""Owner desk: the workspace receptionist does pipeline work, not a new agent."""
from unittest.mock import patch

from web.receptionist import FIND_RE, match_category, owner_desk
from tests.test_crew import CrewBase
from tests.test_app import module


class CategoryMapTests(CrewBase):
    def test_spoken_trades_map_to_price_book_categories(self):
        self.assertEqual(match_category('cafes'), 'Café')
        self.assertEqual(match_category('coffee shop'), 'Café')
        self.assertEqual(match_category('dentists'), 'Dentist')
        self.assertIsNone(match_category('businesses'))
        self.assertIsNone(match_category(''))

    def test_find_sentence_captures_trade_and_city(self):
        hit = FIND_RE.match('find cafes in Lagos')
        self.assertIsNotNone(hit)
        self.assertEqual(hit.group('category'), 'cafes')
        self.assertEqual(hit.group('city'), 'Lagos')


class DeskRouteTests(CrewBase):
    def _desk(self, message, **extra):
        body = {'message': message, 'desk': True}
        body.update(extra)
        return self.client.post('/api/receptionist/message', json=body)

    def test_workspace_is_a_pipeline_desk_not_an_operator_room(self):
        with self.client.session_transaction() as sess:
            sess['owner'] = True
        body = self.client.get('/workspace').data.decode()
        self.assertIn('desk-form', body)
        self.assertIn('desk-log', body)
        self.assertIn('desk.js', body)
        self.assertIn('desk-board', body)
        self.assertIn('How this workspace runs', body)
        self.assertNotIn('REVENUE OPERATIONS PLATFORM', body)
        self.assertIn('class="nav-more"', body)
        self.assertIn('chief-log', body)
        self.assertIn('oe-funnel', body)
        self.assertIn('Find businesses', body)

    def test_visitor_chat_does_not_run_discovery(self):
        with patch('web.receptionist.run_tool') as tool:
            res = self.client.post('/api/receptionist/message', json={'message': 'find cafes in Lagos'})
        self.assertEqual(res.status_code, 200)
        tool.assert_not_called()
        self.assertNotIn('discover_run', res.get_json().get('actions') or [])

    def test_desk_find_runs_existing_discovery_tool(self):
        with patch('web.receptionist.run_tool') as tool:
            tool.return_value = {'discovery': {'added': 2, 'scanned': 7}}
            res = self._desk('find cafes in Lagos')
        self.assertEqual(res.status_code, 200, res.data[:400])
        data = res.get_json()
        self.assertEqual(data['intent'], 'desk_find')
        self.assertIn('discover_run', data['actions'])
        self.assertIn('Lagos', data['reply'])
        self.assertIn('2', data['reply'])
        tool.assert_called_once()
        args = tool.call_args[0]
        self.assertEqual(args[4], 'discover_run')
        self.assertEqual(tool.call_args[0][5]['city'], 'Lagos')
        self.assertEqual(tool.call_args[0][5]['category'], 'Café')

    def test_desk_refuses_to_send_outreach(self):
        res = self._desk('send the email to them')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['intent'], 'desk_send_refused')
        self.assertIn('approve', data['reply'].lower())

    def test_whats_next_uses_saved_listings(self):
        with module.db() as c:
            c.execute(
                'INSERT INTO leads(id,source_key,name,category,city,stage,token,created,updated) '
                'VALUES(?,?,?,?,?,?,?,?,?)',
                ('d1', 'd1', 'Sunrise Bakery', 'Bakery', 'Austin', 'New', 'tok-d1',
                 module.now(), module.now()),
            )
        res = self._desk("what's next")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()['reply']
        self.assertIn('Sunrise Bakery', body)
        self.assertIn('not a forecast', body.lower())

    def test_desk_help_lists_find_not_a_new_agent(self):
        res = self._desk('help')
        self.assertIn('find cafes in Lagos', res.get_json()['reply'])
        self.assertNotIn('new agent', res.get_json()['reply'].lower())

    def test_locked_desk_needs_owner(self):
        with patch.dict('os.environ', {'DASHBOARD_PASSWORD': 'secret-owner-pass'}):
            res = self._desk('status')
        self.assertEqual(res.status_code, 403)

    def test_owner_desk_function_empty_message(self):
        out = owner_desk(module.app, module.db, module.now, module.log, '  ', None, 'hash')
        self.assertFalse(out.get('ok'))
