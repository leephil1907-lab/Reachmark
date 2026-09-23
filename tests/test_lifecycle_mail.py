"""Lifecycle e-mail: password-changed, payment-failed, expiry cron, booking mails.

SMTP is never touched: web.accounts.send_branded is patched and calls counted.
"""
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from tests.test_app import module
from tests.test_billing import BillingBase, future


class LifecycleMailTests(BillingBase):
    def test_reset_completion_sends_password_changed_mail(self):
        with module.db() as c:
            c.execute('INSERT INTO users(id,email,password_hash,name,role,is_active,created,updated,'
                      'reset_token,reset_expires) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      ('reset-u1', 'resetme@example.test', 'x', 'Reset Me', 'client', 1,
                       module.now(), module.now(), 'tok123', future()))
        with patch('web.accounts.send_branded') as sent:
            r = self.client.post('/api/auth/reset',
                                 json={'token': 'tok123', 'password': 'newpassword1'})
        self.assertEqual(r.status_code, 200, r.data[:200])
        self.assertEqual(sent.call_count, 1)
        self.assertIn('password', sent.call_args[0][1].lower())

    def _book(self):
        self.make_owner()
        monday = (datetime.now().date() + timedelta(days=(7 - datetime.now().weekday()) % 7 or 7))
        win = [{'weekday': monday.weekday(), 'start': '09:00', 'end': '10:00'}]
        token = self.client.post('/api/booking/availability', json={'windows': win},
                                 headers=self.csrf()).get_json()['book_url'].rsplit('/', 1)[-1]
        with self.client.session_transaction() as s:
            s.clear()
        import re as _re
        page = self.client.get(f'/book/{token}')
        slot = _re.search(rb'data-slot="([^"]+)"', page.data).group(1).decode()
        return token, slot

    def test_booking_sends_booker_mail_and_skips_owner_without_email(self):
        token, slot = self._book()
        with patch('web.accounts.send_branded') as sent:
            r = self.client.post(f'/api/book/{token}',
                                 json={'slot_start': slot, 'name': 'Mail Booker',
                                       'email': 'booker@example.test'})
        self.assertEqual(r.status_code, 201, r.data[:200])
        self.assertEqual(sent.call_count, 1)
        self.assertEqual(sent.call_args[0][0], 'booker@example.test')

    def test_booking_notifies_owner_when_reply_email_set(self):
        self.make_owner()
        self.client.post('/api/settings', json={'sender_name': 'Ada', 'agency': 'Reachmark',
                                                'reply_email': 'owner@example.test',
                                                'postal_address': '1 Main St'},
                         headers=self.csrf())
        token, slot = self._book()
        with patch('web.accounts.send_branded') as sent:
            r = self.client.post(f'/api/book/{token}',
                                 json={'slot_start': slot, 'name': 'Mail Booker',
                                       'email': 'booker@example.test'})
        self.assertEqual(r.status_code, 201, r.data[:200])
        self.assertEqual(sent.call_count, 2)
        recipients = {c[0][0] for c in sent.call_args_list}
        self.assertEqual(recipients, {'booker@example.test', 'owner@example.test'})

    def _mkpaid(self, uid, email, tier, expires):
        with module.db() as c:
            c.execute('INSERT OR REPLACE INTO users(id,email,password_hash,name,role,is_active,created,updated,'
                      'tier,tier_expires) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (uid, email, 'x', 'Paid User', 'client', 1,
                       module.now(), module.now(), tier, expires))

    def test_cron_rejects_missing_or_wrong_secret(self):
        self.assertEqual(self.client.post('/api/cron/expiry-warnings', json={}).status_code, 401)
        with patch.dict('os.environ', {'CRON_SECRET': 's3cret'}):
            r = self.client.post('/api/cron/expiry-warnings', json={},
                                 headers={'X-Cron-Secret': 'wrong'})
            self.assertEqual(r.status_code, 401)

    def test_cron_warns_expiring_user_once(self):
        soon = (datetime.now() + timedelta(days=2)).isoformat()
        self._mkpaid('exp-u1', 'expiring@example.test', 'starter', soon)
        with patch.dict('os.environ', {'CRON_SECRET': 's3cret'}), \
                patch('web.accounts.send_branded') as sent:
            r1 = self.client.post('/api/cron/expiry-warnings', headers={'X-Cron-Secret': 's3cret'})
            r2 = self.client.post('/api/cron/expiry-warnings', headers={'X-Cron-Secret': 's3cret'})
        self.assertEqual(r1.get_json(), {'ok': True, 'warned': 1})
        self.assertEqual(r2.get_json(), {'ok': True, 'warned': 0})
        self.assertEqual(sent.call_count, 1)
        self.assertEqual(sent.call_args[0][0], 'expiring@example.test')

    def test_cron_ignores_free_and_far_future_users(self):
        self._mkpaid('free-u1', 'free@example.test', 'free', future(30))
        self._mkpaid('far-u1', 'far@example.test', 'pro', future(30))
        with patch.dict('os.environ', {'CRON_SECRET': 's3cret'}), \
                patch('web.accounts.send_branded') as sent:
            r = self.client.post('/api/cron/expiry-warnings', headers={'X-Cron-Secret': 's3cret'})
        self.assertEqual(r.get_json(), {'ok': True, 'warned': 0})
        self.assertEqual(sent.call_count, 0)

    def test_failed_payment_sends_retry_mail(self):
        self.make_client()
        with module.db() as c:
            c.execute("INSERT INTO payments(id,user_id,email,tier,currency,amount_minor,reference,status,paid_at,created,raw) VALUES('pf1','bill-client','bill@example.test','starter','USD',2000,'rm-fail1','pending','',?,?)",
                      (module.now(), '{}'))
        event = {'event': 'charge.success',
                 'data': {'status': 'failed', 'amount': 2000, 'currency': 'USD', 'reference': 'rm-fail1'}}
        raw = json.dumps(event)
        sig = hmac.new(b'whsec-test', raw.encode(), hashlib.sha512).hexdigest()
        with patch.dict('os.environ', {'PAYSTACK_SECRET_KEY': 'whsec-test'}), \
                patch('web.accounts.send_branded') as sent:
            r = self.client.post('/api/billing/webhook', data=raw,
                                 content_type='application/json',
                                 headers={'x-paystack-signature': sig})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sent.call_count, 1)
        with module.db() as c:
            st = c.execute("SELECT status FROM payments WHERE reference='rm-fail1'").fetchone()[0]
        self.assertEqual(st, 'failed')
