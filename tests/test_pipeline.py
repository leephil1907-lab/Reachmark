"""The sending pipeline: controlled first batch, open/reply measurement, follow-ups.

No message ever leaves the process: SMTP is pointed at a fake host and ``smtplib``
is patched, so the suite proves the guardrails (caps, opt-out, one-send-per-business,
follow-ups that stop on a reply) without touching the network.
"""
import os
import uuid
from unittest.mock import patch, MagicMock

from tests.test_crew import CrewBase
from web import pipeline


def _lead(db, now, **over):
    """Insert a minimal lead row and return its id."""
    lid = uuid.uuid4().hex
    row = {'id': lid, 'source_key': lid, 'name': over.get('name', 'Copper Kettle Cafe'),
           'category': over.get('category', 'Cafe'), 'city': over.get('city', 'Lisbon'),
           'address': '', 'phone': '', 'email': over.get('email', 'owner@copper.test'),
           'website': over.get('website', ''), 'status': '', 'stage': over.get('stage', 'New'),
           'source': 'Google Maps', 'source_url': '', 'token': uuid.uuid4().hex,
           'created': now(), 'updated': now()}
    with db() as c:
        c.execute('INSERT INTO leads(id,source_key,name,category,city,address,phone,email,'
                  'website,status,stage,source,source_url,token,created,updated) '
                  'VALUES(:id,:source_key,:name,:category,:city,:address,:phone,:email,'
                  ':website,:status,:stage,:source,:source_url,:token,:created,:updated)', row)
    return lid


class TableTests(CrewBase):
    def test_ensure_tables_is_idempotent(self):
        pipeline.ensure_tables(self.module_db())
        pipeline.ensure_tables(self.module_db())
        with self.module_db()() as c:
            names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn('email_events', names)
        self.assertIn('pipeline_followups', names)

    def module_db(self):
        from tests.test_app import module
        return module.db


class PixelTests(CrewBase):
    def test_pixel_html_is_a_tiny_hidden_image(self):
        html = pipeline.pixel_html('https://reachmark.example', 'tok123')
        self.assertIn('https://reachmark.example/t/tok123/o.gif', html)
        self.assertIn('width="1"', html)
        self.assertIn('display:none', html)

    def test_pixel_html_empty_without_base_or_token(self):
        self.assertEqual(pipeline.pixel_html('', 'tok'), '')
        self.assertEqual(pipeline.pixel_html('https://x', ''), '')

    def test_inject_pixel_places_it_before_body_close(self):
        body = '<html><body><p>hi</p></body></html>'
        out = pipeline._inject_pixel(body, 'https://x', 'tok')
        self.assertIn('/t/tok/o.gif', out)
        self.assertLess(out.index('o.gif'), out.index('</body>'))

    def test_inject_pixel_appends_when_no_body_tag(self):
        out = pipeline._inject_pixel('<p>hi</p>', 'https://x', 'tok')
        self.assertTrue(out.endswith('o.gif" width="1" height="1" alt="" style="display:none;border:0;outline:none" />'))

    def test_track_open_records_an_event(self):
        from tests.test_app import module
        now = module.now
        lid = _lead(module.db, now)
        with module.db() as c:
            c.execute('INSERT INTO review_links(id,lead_id,token,status,created,updated) '
                      'VALUES(?,?,?,?,?,?)', (uuid.uuid4().hex, lid, 'tok-open', 'ready', now(), now()))
        self.assertTrue(pipeline.track_open(module.db, now, 'tok-open'))
        with module.db() as c:
            n = c.execute("SELECT count(*) FROM email_events WHERE kind='open' AND lead_id=?", (lid,)).fetchone()[0]
        self.assertEqual(n, 1)

    def test_track_open_unknown_token_is_false(self):
        from tests.test_app import module
        self.assertFalse(pipeline.track_open(module.db, module.now, 'nope'))


class FollowupScheduleTests(CrewBase):
    def test_schedule_is_idempotent(self):
        from tests.test_app import module
        now = module.now
        lid = _lead(module.db, now)
        link = {'id': 'link1'}
        self.assertEqual(pipeline.schedule_followups(module.db, now, {'id': lid}, link), 2)
        self.assertEqual(pipeline.schedule_followups(module.db, now, {'id': lid}, link), 0)
        with module.db() as c:
            steps = sorted(r[0] for r in c.execute('SELECT step FROM pipeline_followups WHERE lead_id=?', (lid,)))
        self.assertEqual(steps, [2, 3])


class SendBatchTests(CrewBase):
    def setUp(self):
        super().setUp()
        self.profile()
        self.env.stop()
        self.env = patch.dict(os.environ, {
            'DASHBOARD_PASSWORD': '', 'ALLOW_CREW_DEMO': '1',
            'SMTP_HOST': 'smtp.test', 'SMTP_FROM': 'studio@reachmark.test',
            'SMTP_PORT': '587', 'SMTP_SECURITY': 'starttls',
            'SMTP_USER': 'studio@reachmark.test', 'SMTP_PASSWORD': 'secret',
            'PUBLIC_BASE_URL': 'https://reachmark.example'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        super().tearDown()

    def _fake_smtp(self):
        server = MagicMock()
        server.__enter__ = MagicMock(return_value=server)
        server.__exit__ = MagicMock(return_value=False)
        return server

    def test_first_batch_sends_and_schedules_followups(self):
        from tests.test_app import module
        now = module.now
        for i in range(3):
            _lead(module.db, now, name=f'Cafe {i}', email=f'cafe{i}@copper.test')
        with patch('web.pipeline.smtplib.SMTP', return_value=self._fake_smtp()):
            result = pipeline.send_first_batch(module.db, now, None, module.settings(), limit=20)
        self.assertEqual(result['sent'], 3)
        with module.db() as c:
            sends = c.execute("SELECT count(*) FROM sends WHERE state='sent'").fetchone()[0]
            scheduled = c.execute("SELECT count(*) FROM pipeline_followups WHERE state='scheduled'").fetchone()[0]
            contacted = c.execute("SELECT count(*) FROM leads WHERE stage='Contacted'").fetchone()[0]
        self.assertEqual(sends, 3)
        self.assertEqual(scheduled, 6)  # two follow-ups per business
        self.assertEqual(contacted, 3)

    def test_batch_is_capped(self):
        from tests.test_app import module
        now = module.now
        for i in range(5):
            _lead(module.db, now, name=f'Cafe {i}', email=f'cafe{i}@copper.test')
        with patch('web.pipeline.smtplib.SMTP', return_value=self._fake_smtp()):
            result = pipeline.send_first_batch(module.db, now, None, module.settings(), limit=2)
        self.assertEqual(result['sent'], 2)
        self.assertEqual(result['cap'], pipeline.FIRST_BATCH_CAP)

    def test_no_second_send_to_the_same_business(self):
        from tests.test_app import module
        now = module.now
        _lead(module.db, now, name='Once Only', email='once@copper.test')
        with patch('web.pipeline.smtplib.SMTP', return_value=self._fake_smtp()):
            first = pipeline.send_first_batch(module.db, now, None, module.settings(), limit=20)
            second = pipeline.send_first_batch(module.db, now, None, module.settings(), limit=20)
        self.assertEqual(first['sent'], 1)
        self.assertEqual(second['sent'], 0)

    def test_suppressed_recipient_is_skipped(self):
        from tests.test_app import module
        now = module.now
        _lead(module.db, now, name='Opted Out', email='no@copper.test')
        with module.db() as c:
            c.execute('INSERT INTO suppression(email,created) VALUES(?,?)', ('no@copper.test', now()))
        with patch('web.pipeline.smtplib.SMTP', return_value=self._fake_smtp()):
            result = pipeline.send_first_batch(module.db, now, None, module.settings(), limit=20)
        self.assertEqual(result['sent'], 0)
        self.assertEqual(result['results'][0]['state'], 'skipped')

    def test_smtp_failure_is_recorded_not_raised(self):
        from tests.test_app import module
        now = module.now
        _lead(module.db, now, name='Boom', email='boom@copper.test')
        with patch('web.pipeline.smtplib.SMTP', side_effect=OSError('no route')):
            result = pipeline.send_first_batch(module.db, now, None, module.settings(), limit=20)
        self.assertEqual(result['sent'], 0)
        self.assertEqual(result['results'][0]['state'], 'failed')


class FollowupRunTests(CrewBase):
    def setUp(self):
        super().setUp()
        self.profile()
        self.env.stop()
        self.env = patch.dict(os.environ, {
            'DASHBOARD_PASSWORD': '', 'ALLOW_CREW_DEMO': '1',
            'SMTP_HOST': 'smtp.test', 'SMTP_FROM': 'studio@reachmark.test',
            'SMTP_PORT': '587', 'SMTP_SECURITY': 'starttls',
            'SMTP_USER': 'studio@reachmark.test', 'SMTP_PASSWORD': 'secret',
            'PUBLIC_BASE_URL': 'https://reachmark.example'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        super().tearDown()

    def _fake_smtp(self):
        server = MagicMock()
        server.__enter__ = MagicMock(return_value=server)
        server.__exit__ = MagicMock(return_value=False)
        return server

    def _due(self, module, lid, link_id='link1'):
        with module.db() as c:
            c.execute('INSERT INTO pipeline_followups(id,lead_id,link_id,step,state,due,created,updated) '
                      'VALUES(?,?,?,?,?,?,?,?)',
                      (uuid.uuid4().hex, lid, link_id, 2, 'scheduled', '2000-01-01T00:00:00+00:00',
                       module.now(), module.now()))

    def test_due_followup_is_sent(self):
        from tests.test_app import module
        now = module.now
        lid = _lead(module.db, now, name='Follow Me', email='follow@copper.test')
        with module.db() as c:
            c.execute('INSERT INTO review_links(id,lead_id,token,status,created,updated) '
                      'VALUES(?,?,?,?,?,?)', ('link1', lid, 'tok-fu', 'ready', now(), now()))
        self._due(module, lid)
        with patch('web.pipeline.smtplib.SMTP', return_value=self._fake_smtp()):
            result = pipeline.run_followups(module.db, now, None, module.settings(), limit=5)
        self.assertEqual(result['sent'], 1)
        with module.db() as c:
            state = c.execute('SELECT state FROM pipeline_followups WHERE lead_id=?', (lid,)).fetchone()[0]
        self.assertEqual(state, 'sent')

    def test_followup_cancelled_when_business_answered(self):
        from tests.test_app import module
        now = module.now
        lid = _lead(module.db, now, name='Answered', email='ans@copper.test')
        with module.db() as c:
            c.execute('INSERT INTO review_links(id,lead_id,token,status,created,updated) '
                      'VALUES(?,?,?,?,?,?)', ('link1', lid, 'tok-ans', 'ready', now(), now()))
            c.execute('INSERT INTO review_responses(id,link_id,lead_id,choice,note,name,email,'
                      'fingerprint,handled,rating,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (uuid.uuid4().hex, 'link1', lid, 'want', '', '', '', '', 0, None, now()))
        self._due(module, lid)
        with patch('web.pipeline.smtplib.SMTP', return_value=self._fake_smtp()):
            result = pipeline.run_followups(module.db, now, None, module.settings(), limit=5)
        self.assertEqual(result['sent'], 0)
        self.assertEqual(result['results'][0]['state'], 'cancelled')

    def test_followup_cancelled_when_suppressed(self):
        from tests.test_app import module
        now = module.now
        lid = _lead(module.db, now, name='Suppressed', email='sup@copper.test')
        with module.db() as c:
            c.execute('INSERT INTO review_links(id,lead_id,token,status,created,updated) '
                      'VALUES(?,?,?,?,?,?)', ('link1', lid, 'tok-sup', 'ready', now(), now()))
            c.execute('INSERT INTO suppression(email,created) VALUES(?,?)', ('sup@copper.test', now()))
        self._due(module, lid)
        with patch('web.pipeline.smtplib.SMTP', return_value=self._fake_smtp()):
            result = pipeline.run_followups(module.db, now, None, module.settings(), limit=5)
        self.assertEqual(result['sent'], 0)
        self.assertEqual(result['results'][0]['state'], 'cancelled')


class MetricsTests(CrewBase):
    def test_metrics_compute_rates(self):
        from tests.test_app import module
        now = module.now
        lid = _lead(module.db, now, name='Measured', email='m@copper.test')
        pipeline.record_event(module.db, now, lid, '', 'sent', 'first')
        pipeline.record_event(module.db, now, lid, '', 'open', '')
        with module.db() as c:
            c.execute('INSERT INTO review_responses(id,link_id,lead_id,choice,note,name,email,'
                      'fingerprint,handled,rating,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (uuid.uuid4().hex, 'l', lid, 'want', '', '', '', '', 0, None, now()))
        m = pipeline.pipeline_metrics(module.db)
        self.assertEqual(m['contacted'], 1)
        self.assertEqual(m['opened'], 1)
        self.assertEqual(m['replied'], 1)
        self.assertEqual(m['open_rate'], 100.0)
        self.assertEqual(m['reply_rate'], 100.0)

    def test_metrics_are_zero_safe(self):
        m = pipeline.pipeline_metrics(self.module_db())
        self.assertEqual(m['contacted'], 0)
        self.assertEqual(m['open_rate'], 0.0)

    def module_db(self):
        from tests.test_app import module
        return module.db


class RouteTests(CrewBase):
    def test_pixel_route_serves_a_gif(self):
        from tests.test_app import module
        now = module.now
        lid = _lead(module.db, now)
        with module.db() as c:
            c.execute('INSERT INTO review_links(id,lead_id,token,status,created,updated) '
                      'VALUES(?,?,?,?,?,?)', (uuid.uuid4().hex, lid, 'tok-route', 'ready', now(), now()))
        r = self.client.get('/t/tok-route/o.gif')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, 'image/gif')

    def test_pipeline_metrics_route_requires_owner_when_locked(self):
        with patch('web.pipeline.owner_locked', return_value=True):
            r = self.client.get('/api/pipeline')
        self.assertEqual(r.status_code, 403)


if __name__ == '__main__':
    import unittest
    unittest.main()
