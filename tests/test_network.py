"""Network (Popl-parity slice): cards, QR, events, scanning, booking, webhooks, OAuth.

External systems are never touched: OAuth provider HTTP is stubbed where
needed, and webhook delivery posts through a patched _post_json.
"""
import io
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import web.network as nw
from tests.test_app import module
from tests.test_billing import BillingBase, future


PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
       b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
       b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


class NetworkBase(BillingBase):
    def make_event(self, name='Expo 2026'):
        r = self.client.post('/api/events', json={'name': name, 'goal': 10},
                             headers=self.csrf())
        self.assertEqual(r.status_code, 201, r.data[:200])
        return r.get_json()['id']


class CardTests(NetworkBase):
    def test_card_crud_and_public_page(self):
        self.make_owner()
        r = self.client.post('/api/cards', json={'name': 'Ada Okafor', 'role': 'Founder',
                                                 'links': [{'label': 'Site', 'url': 'https://example.com'}]},
                             headers=self.csrf())
        self.assertEqual(r.status_code, 201, r.data[:200])
        body = r.get_json()
        token = body['token']
        cid = body['id']
        # Public card page + vCard work with no session.
        with self.client.session_transaction() as s:
            s.clear()
        self.assertEqual(self.client.get(f'/c/{token}').status_code, 200)
        vcf = self.client.get(f'/c/{token}.vcf')
        self.assertEqual(vcf.status_code, 200)
        self.assertIn('BEGIN:VCARD', vcf.data.decode())
        # Back as owner: update + delete.
        self.make_owner()
        r = self.client.put(f'/api/cards/{cid}', json={'name': 'Ada Okafor', 'theme': 'lime'},
                            headers=self.csrf())
        self.assertEqual(r.status_code, 200, r.data[:200])
        r = self.client.put(f'/api/cards/{cid}', json={'name': 'Ada', 'theme': 'nope'},
                            headers=self.csrf())
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.delete(f'/api/cards/{cid}', headers=self.csrf()).status_code, 200)

    def test_card_requires_name(self):
        self.make_owner()
        r = self.client.post('/api/cards', json={'name': ''}, headers=self.csrf())
        self.assertEqual(r.status_code, 400)

    def test_free_client_can_make_cards(self):
        self.make_client()
        r = self.client.post('/api/cards', json={'name': 'Client Card'}, headers=self.csrf())
        self.assertEqual(r.status_code, 201, r.data[:200])


class QrTests(NetworkBase):
    def test_qr_png_ok_and_evil_host_rejected(self):
        self.make_owner()
        r = self.client.post('/api/cards', json={'name': 'QR Guy'}, headers=self.csrf())
        token = r.get_json()['token']
        qr = self.client.get(f'/api/qr.png?u=/c/{token}')
        self.assertEqual(qr.status_code, 200)
        self.assertEqual(qr.content_type, 'image/png')
        evil = self.client.get('/api/qr.png?u=https://evil.example/x')
        self.assertEqual(evil.status_code, 400)


class EventTests(NetworkBase):
    def test_event_qualifiers_capture_and_stats(self):
        self.make_owner()
        eid = self.make_event()
        q = self.client.post(f'/api/events/{eid}/qualifiers',
                             json={'question': 'Budget?', 'kind': 'choice',
                                   'options': ['Low', 'High']}, headers=self.csrf())
        self.assertEqual(q.status_code, 201, q.data[:200])
        qid = q.get_json()['id']
        cap = self.client.post(f'/api/events/{eid}/capture',
                               json={'name': 'Ngozi Eze', 'email': 'ngozi@example.com',
                                     'answers': {qid: 'High'}}, headers=self.csrf())
        self.assertEqual(cap.status_code, 201, cap.data[:200])
        d = self.client.get(f'/api/events/{eid}').get_json()
        self.assertEqual(len(d['leads']), 1)
        self.assertTrue(d['leads'][0]['source'].startswith('Event:'))
        stats = self.client.get(f'/api/events/{eid}/stats').get_json()
        self.assertEqual(stats['captured'], 1)
        self.assertEqual(stats['stages'].get('New'), 1)
        # Invalid choice answers are skipped, not stored.
        bad = self.client.post(f'/api/events/{eid}/capture',
                               json={'name': 'Bad Guy', 'answers': {qid: 'Nope'}},
                               headers=self.csrf())
        self.assertEqual(bad.status_code, 201)

    def test_free_client_cannot_make_events(self):
        self.make_client()
        r = self.client.post('/api/events', json={'name': 'Nope'}, headers=self.csrf())
        self.assertEqual(r.status_code, 402)
        self.assertEqual(r.get_json().get('required'), 'starter')

    def test_starter_client_can_make_events(self):
        self.make_client('starter', future())
        r = self.client.post('/api/events', json={'name': 'Starter Expo'}, headers=self.csrf())
        self.assertEqual(r.status_code, 201, r.data[:200])

    def test_event_delete_removes_lead_links(self):
        self.make_owner()
        eid = self.make_event()
        self.client.post(f'/api/events/{eid}/capture', json={'name': 'Temp Lead'},
                         headers=self.csrf())
        self.assertEqual(self.client.delete(f'/api/events/{eid}', headers=self.csrf()).status_code, 200)
        with module.db() as c:
            left = c.execute('SELECT count(*) FROM event_leads WHERE event_id=?', (eid,)).fetchone()[0]
            lead = c.execute("SELECT id FROM leads WHERE name='Temp Lead'").fetchone()
        self.assertEqual(left, 0)
        self.assertIsNotNone(lead)


class ScanTests(NetworkBase):
    def test_upload_and_ai_extract_patched(self):
        self.make_owner()
        up = self.client.post('/api/scans', data={'photo': (io.BytesIO(PNG), 'card.png')},
                              headers=self.csrf())
        self.assertEqual(up.status_code, 201, up.data[:200])
        sid = up.get_json()['id']
        self.assertEqual(self.client.get(f'/api/scans/{sid}/photo').status_code, 200)

        class _FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {'message': {'content': '{"name":"Zed","email":"zed@example.com"}'}}

        with patch('web.ai_provider.resolve_provider',
                   return_value=('ollama', '', 'llava', 'http://127.0.0.1:9')), \
             patch('requests.post', return_value=_FakeResp()):
            ex = self.client.post(f'/api/scans/{sid}/extract', json={}, headers=self.csrf())
        self.assertEqual(ex.status_code, 200, ex.data[:300])
        body = ex.get_json()
        self.assertTrue(body['available'])
        self.assertEqual(body['suggestions']['name'], 'Zed')
        self.assertEqual(body['suggestions']['email'], 'zed@example.com')

    def test_upload_rejects_non_image(self):
        self.make_owner()
        up = self.client.post('/api/scans', data={'photo': (io.BytesIO(b'nope'), 'x.txt')},
                              headers=self.csrf())
        self.assertEqual(up.status_code, 400)


class BookingTests(NetworkBase):
    def test_full_booking_flow_and_double_book_guard(self):
        self.make_owner()
        monday = (datetime.now().date() + timedelta(days=(7 - datetime.now().weekday()) % 7 or 7))
        win = [{'weekday': monday.weekday(), 'start': '09:00', 'end': '10:00'}]
        r = self.client.post('/api/booking/availability', json={'windows': win}, headers=self.csrf())
        self.assertEqual(r.status_code, 200, r.data[:200])
        token = r.get_json()['book_url'].rsplit('/', 1)[-1]
        # Public: page, slots, book.
        with self.client.session_transaction() as s:
            s.clear()
        page = self.client.get(f'/book/{token}')
        self.assertEqual(page.status_code, 200)
        import re as _re
        m = _re.search(rb'data-slot="([^"]+)"', page.data)
        self.assertIsNotNone(m, 'expected open slots on the booking page')
        slot = m.group(1).decode()
        book = {'slot_start': slot, 'name': 'Adaeze Obi', 'email': 'adaeze@example.com'}
        r1 = self.client.post(f'/api/book/{token}', json=book)
        self.assertEqual(r1.status_code, 201, r1.data[:300])
        made = r1.get_json()
        bid = made['booking']['id']
        r2 = self.client.post(f'/api/book/{token}', json=book)
        self.assertEqual(r2.status_code, 409)
        ics = self.client.get(made['ics'])
        self.assertEqual(ics.status_code, 200)
        text = ics.data.decode()
        self.assertLess(text.index('BEGIN:VEVENT'), text.index('SUMMARY'))
        self.assertIn('END:VEVENT', text)
        # Owner confirms.
        self.make_owner()
        st = self.client.post(f'/api/bookings/{bid}/status', json={'status': 'confirmed'},
                              headers=self.csrf())
        self.assertEqual(st.status_code, 200)

    def test_booking_rejects_bad_fields_and_honeypot(self):
        self.make_owner()
        r = self.client.post('/api/booking/availability', json={'windows': []}, headers=self.csrf())
        token = r.get_json()['book_url'].rsplit('/', 1)[-1]
        with self.client.session_transaction() as s:
            s.clear()
        bad = self.client.post(f'/api/book/{token}', json={'slot_start': 'x', 'name': 'A', 'email': 'bad'})
        self.assertEqual(bad.status_code, 400)
        hp = self.client.post(f'/api/book/{token}', json={'slot_start': '2026-01-01T09:00', 'name': 'Spammer Man',
                                                           'email': 'spam@example.com', 'company_url': 'http://spam.example'})
        self.assertEqual(hp.status_code, 400)


class WebhookTests(NetworkBase):
    def test_webhook_crud_and_validation(self):
        self.make_owner()
        r = self.client.post('/api/webhooks', json={'url': 'https://crm.example.test/hook',
                                                    'events': ['lead.created']}, headers=self.csrf())
        self.assertEqual(r.status_code, 201, r.data[:200])
        hid = r.get_json()['id']
        self.assertEqual(len(self.client.get('/api/webhooks').get_json()['webhooks']), 1)
        bad = self.client.post('/api/webhooks', json={'url': 'http://plain.example/hook'},
                               headers=self.csrf())
        self.assertEqual(bad.status_code, 400)
        bad2 = self.client.post('/api/webhooks', json={'url': 'https://x.example/', 'events': ['nope']},
                                headers=self.csrf())
        self.assertEqual(bad2.status_code, 400)
        self.assertEqual(self.client.delete(f'/api/webhooks/{hid}', headers=self.csrf()).status_code, 200)

    def test_capture_dispatches_signed_delivery(self):
        self.make_owner()
        self.client.post('/api/webhooks', json={'url': 'https://crm.example.test/hook',
                                                'events': ['lead.created']}, headers=self.csrf())
        eid = self.make_event()
        with patch('requests.post') as post:
            r = self.client.post(f'/api/events/{eid}/capture', json={'name': 'Hook Lead'},
                                 headers=self.csrf())
            self.assertEqual(r.status_code, 201, r.data[:200])
        self.assertTrue(post.called, 'expected a signed webhook delivery')
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://crm.example.test/hook')
        self.assertIn('X-Reachmark-Signature', kwargs['headers'])
        self.assertEqual(json.loads(kwargs['data'])['event'], 'lead.created')


class FollowupTests(NetworkBase):
    def test_followup_needs_basis_and_approval(self):
        self.make_owner()
        prof = self.client.post('/api/settings', json={'sender_name': 'Ada', 'agency': 'Reachmark',
                                                        'reply_email': 'ada@example.com',
                                                        'postal_address': '1 Main St'},
                                headers=self.csrf())
        self.assertEqual(prof.status_code, 200)
        eid = self.make_event()
        cap = self.client.post(f'/api/events/{eid}/capture',
                               json={'name': 'Follow Me', 'email': 'follow@example.com'},
                               headers=self.csrf()).get_json()
        no_basis = self.client.post(f"/api/leads/{cap['lead_id']}/followup",
                                    json={'approved': True}, headers=self.csrf())
        self.assertEqual(no_basis.status_code, 400)
        no_approve = self.client.post(f"/api/leads/{cap['lead_id']}/followup",
                                      json={'basis': 'Met at Expo 2026'}, headers=self.csrf())
        self.assertEqual(no_approve.status_code, 400)
        with patch('web.crew_mail.send_email', return_value={'ok': True, 'state': 'sent'}):
            ok = self.client.post(f"/api/leads/{cap['lead_id']}/followup",
                                  json={'approved': True, 'basis': 'Met at Expo 2026'},
                                  headers=self.csrf())
        self.assertEqual(ok.status_code, 200, ok.data[:300])
        self.assertEqual(ok.get_json()['state'], 'sent')
        # Without SMTP the mail is queued honestly, never silently dropped.
        bare = self.client.post(f"/api/leads/{cap['lead_id']}/followup",
                                json={'approved': True, 'basis': 'Met at Expo 2026'},
                                headers=self.csrf())
        self.assertEqual(bare.status_code, 502)
        self.assertIn('outbox', bare.get_json()['error'])


class OAuthTests(NetworkBase):
    def test_status_lists_unconfigured_providers(self):
        r = self.client.get('/api/auth/oauth')
        self.assertEqual(r.status_code, 200)
        ids = {p['id'] for p in r.get_json()['providers']}
        self.assertEqual(ids, {'google', 'microsoft'})
        self.assertTrue(all(p['configured'] is False for p in r.get_json()['providers']))

    def test_unknown_provider_404_and_off_provider_400(self):
        self.assertEqual(self.client.get('/api/auth/oauth/github').status_code, 404)
        self.assertEqual(self.client.get('/api/auth/oauth/google').status_code, 400)

    def test_configured_start_redirects_to_provider(self):
        env = {'GOOGLE_CLIENT_ID': 'test-id', 'GOOGLE_CLIENT_SECRET': 'test-secret'}
        with patch.dict(os.environ, env):
            r = self.client.get('/api/auth/oauth/google?mode=signup')
        self.assertEqual(r.status_code, 302)
        self.assertIn('accounts.google.com', r.headers['Location'])

    def test_callback_with_bad_state_rejects(self):
        r = self.client.get('/api/auth/oauth/google/callback?state=nope&code=x')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/signin?oauth=invalid', r.headers['Location'])
