"""Workspace plans (Free/Starter/Pro + Paystack) and owner-only agent tools.

Paystack is never contacted: web.billing.paystack_request is stubbed.
"""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tests.test_app import module
from tests.test_crew import CrewBase


def future(days=5):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def past(days=5):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class BillingBase(CrewBase):
    def make_client(self, tier='free', expires=None):
        with module.db() as c:
            c.execute('INSERT OR REPLACE INTO users(id,email,password_hash,name,role,is_active,created,updated) '
                      "VALUES('bill-client','bill@example.test','x','Bill Client','client',1,?,?)",
                      (module.now(), module.now()))
            c.execute('UPDATE users SET tier=?,tier_expires=? WHERE id=?',
                      (tier, expires, 'bill-client'))
        with self.client.session_transaction() as s:
            s['client_id'] = 'bill-client'
            s['role'] = 'client'
            s['csrf'] = 'test-csrf'

    def make_owner(self, password=None):
        with self.client.session_transaction() as s:
            s['owner'] = True
            if password:
                s['revision'] = hashlib.sha256(password.encode()).hexdigest()
            s['csrf'] = 'test-csrf'

    def csrf(self):
        return {'X-CSRF-Token': 'test-csrf'}


class PricingTests(BillingBase):
    def test_pricing_page_is_public(self):
        r = self.client.get('/pricing')
        self.assertEqual(r.status_code, 200)
        body = r.data.decode()
        for word in ('Starter', 'Pro', 'USD', 'NGN', 'Paystack', '30 days'):
            self.assertIn(word, body)

    def test_billing_status_for_visitors(self):
        r = self.client.get('/api/billing/status')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertFalse(data['authenticated'])
        self.assertIn('starter', data['prices'])
        self.assertIn('configured', data)

    def test_new_accounts_start_free(self):
        self.make_client()
        me = self.client.get('/api/auth/me').get_json()
        self.assertEqual(me['tier'], 'free')
        self.assertFalse(me['tier_active'])


class TierGatingTests(BillingBase):
    def test_free_client_gets_upgrade_hint_for_pro_tools(self):
        self.make_client()
        r = self.client.get('/api/crew')
        self.assertEqual(r.status_code, 402)
        self.assertEqual(r.get_json().get('upgrade'), '/pricing')
        self.assertEqual(r.get_json().get('required'), 'pro')

    def test_free_client_gets_upgrade_hint_for_starter_tools(self):
        self.make_client()
        r = self.client.post('/api/leads', json={'name': 'Nope'}, headers=self.csrf())
        self.assertEqual(r.status_code, 402)
        self.assertEqual(r.get_json().get('required'), 'starter')

    def test_owner_only_paths_stay_forbidden(self):
        self.make_client()
        r = self.client.get('/api/settings')
        self.assertEqual(r.status_code, 403)
        r = self.client.get('/api/contracts')
        self.assertEqual(r.status_code, 403)

    def test_starter_client_can_manage_leads(self):
        self.make_client('starter', future())
        r = self.client.post('/api/leads', json={'name': 'Starter Bakery'}, headers=self.csrf())
        self.assertEqual(r.status_code, 200, r.data[:200])
        self.assertEqual(r.get_json().get('added'), 1)

    def test_starter_client_cannot_send_outreach(self):
        self.make_client('starter', future())
        with module.db() as c:
            c.execute("INSERT OR REPLACE INTO leads(id,source_key,name,stage,token,created,updated) VALUES('l1','k1','X','New','t1',?,?)",
                      (module.now(), module.now()))
        r = self.client.post('/api/leads/l1/send', json={'approved': True, 'basis': 'x' * 20},
                             headers=self.csrf())
        self.assertEqual(r.status_code, 402)

    def test_expired_plan_locks_tools_again(self):
        self.make_client('pro', past())
        r = self.client.get('/api/crew')
        self.assertEqual(r.status_code, 402)

    def test_pro_client_reaches_pro_tools(self):
        self.make_client('pro', future())
        r = self.client.get('/api/crew')
        self.assertEqual(r.status_code, 200)

    def test_paid_client_sees_only_own_workspace_in_state(self):
        with module.db() as c:
            c.execute("INSERT OR REPLACE INTO leads(id,source_key,name,stage,token,created,updated,owner_user_id) VALUES('st1','stk1','State Bakery','New','stt1',?,?,'bill-client')",
                      (module.now(), module.now()))
            c.execute("INSERT OR REPLACE INTO leads(id,source_key,name,stage,token,created,updated) VALUES('st2','stk2','Studio Secret','New','stt2',?,?)",
                      (module.now(), module.now()))
        self.make_client('starter', future())
        leads = self.client.get('/api/state').get_json()['leads']
        names = [l['name'] for l in leads]
        self.assertIn('State Bakery', names)
        self.assertNotIn('Studio Secret', names)

    def test_free_client_sees_no_directory(self):
        self.make_client()
        data = self.client.get('/api/state').get_json()
        self.assertEqual(data['leads'], [])
        r = self.client.get('/api/quality')
        self.assertEqual(r.status_code, 402)

    def test_owner_bypasses_tiers_when_password_set(self):
        with patch.dict('os.environ', {'DASHBOARD_PASSWORD': 'owner-secret'}):
            self.make_owner('owner-secret')
            r = self.client.get('/api/crew')
            self.assertEqual(r.status_code, 200, r.data[:200])


class CheckoutTests(BillingBase):
    def test_anonymous_and_owner_checkout_rejected(self):
        r = self.client.post('/api/billing/checkout', json={'tier': 'pro', 'currency': 'USD'})
        self.assertEqual(r.status_code, 401)
        self.make_owner()
        r = self.client.post('/api/billing/checkout', json={'tier': 'pro', 'currency': 'USD'},
                             headers=self.csrf())
        self.assertEqual(r.status_code, 400)

    def test_checkout_needs_configured_payments(self):
        self.make_client()
        with patch.dict('os.environ', {'PAYSTACK_SECRET_KEY': ''}):
            r = self.client.post('/api/billing/checkout', json={'tier': 'pro', 'currency': 'USD'},
                                 headers=self.csrf())
        self.assertEqual(r.status_code, 503)

    def test_checkout_creates_pending_payment(self):
        self.make_client()
        fake = {'authorization_url': 'https://pay.test/abc', 'reference': 'rm-testref1'}
        with patch('web.billing.paystack_request', return_value=fake) as m, \
                patch.dict('os.environ', {'PAYSTACK_SECRET_KEY': 'sk_test_x'}):
            r = self.client.post('/api/billing/checkout', json={'tier': 'starter', 'currency': 'NGN'},
                                 headers=self.csrf())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['authorization_url'], 'https://pay.test/abc')
        args = m.call_args[0]
        self.assertEqual(args[1], '/transaction/initialize')
        self.assertEqual(args[2]['amount'], 3000000)
        self.assertEqual(args[2]['currency'], 'NGN')
        with module.db() as c:
            row = c.execute('SELECT * FROM payments WHERE reference=?', ('rm-testref1',)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['status'], 'pending')

    def test_callback_activates_plan(self):
        self.make_client()
        init = {'authorization_url': 'https://pay.test/abc', 'reference': 'rm-testref2'}
        verify = {'status': 'success', 'amount': 1900, 'currency': 'USD', 'reference': 'rm-testref2'}

        def fake(method, path, payload=None):
            return init if path == '/transaction/initialize' else verify

        with patch('web.billing.paystack_request', side_effect=fake), \
                patch.dict('os.environ', {'PAYSTACK_SECRET_KEY': 'sk_test_x'}):
            self.client.post('/api/billing/checkout', json={'tier': 'starter', 'currency': 'USD'},
                             headers=self.csrf())
            r = self.client.get('/billing/callback?reference=rm-testref2')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/dashboard?upgraded=1', r.headers['Location'])
        me = self.client.get('/api/auth/me').get_json()
        self.assertEqual(me['tier'], 'starter')
        self.assertTrue(me['tier_active'])

    def test_callback_rejects_failed_payment(self):
        self.make_client()
        init = {'authorization_url': 'https://pay.test/abc', 'reference': 'rm-testref3'}
        verify = {'status': 'failed', 'amount': 1900, 'currency': 'USD', 'reference': 'rm-testref3'}

        def fake(method, path, payload=None):
            return init if path == '/transaction/initialize' else verify

        with patch('web.billing.paystack_request', side_effect=fake), \
                patch.dict('os.environ', {'PAYSTACK_SECRET_KEY': 'sk_test_x'}):
            self.client.post('/api/billing/checkout', json={'tier': 'starter', 'currency': 'USD'},
                             headers=self.csrf())
            r = self.client.get('/billing/callback?reference=rm-testref3')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/pricing?error=payment', r.headers['Location'])
        me = self.client.get('/api/auth/me').get_json()
        self.assertEqual(me['tier'], 'free')

    def test_webhook_activates_with_valid_signature(self):
        self.make_client()
        with module.db() as c:
            c.execute("INSERT INTO payments(id,user_id,email,tier,currency,amount_minor,reference,status,paid_at,created,raw) VALUES('p1','bill-client','bill@example.test','pro','USD',5900,'rm-hook1','pending','',?,?)",
                      (module.now(), '{}'))
        event = {'event': 'charge.success',
                 'data': {'status': 'success', 'amount': 5900, 'currency': 'USD', 'reference': 'rm-hook1'}}
        raw = json.dumps(event)
        sig = hmac.new(b'whsec-test', raw.encode(), hashlib.sha512).hexdigest()
        with patch.dict('os.environ', {'PAYSTACK_SECRET_KEY': 'whsec-test'}):
            r = self.client.post('/api/billing/webhook', data=raw,
                                 content_type='application/json',
                                 headers={'x-paystack-signature': sig})
        self.assertEqual(r.status_code, 200)
        me = self.client.get('/api/auth/me').get_json()
        self.assertEqual(me['tier'], 'pro')
        # Re-delivery is harmless.
        with patch.dict('os.environ', {'PAYSTACK_SECRET_KEY': 'whsec-test'}):
            r = self.client.post('/api/billing/webhook', data=raw,
                                 content_type='application/json',
                                 headers={'x-paystack-signature': sig})
        self.assertEqual(r.status_code, 200)

    def test_webhook_rejects_bad_signature(self):
        with patch.dict('os.environ', {'PAYSTACK_SECRET_KEY': 'whsec-test'}):
            r = self.client.post('/api/billing/webhook', json={'event': 'charge.success'},
                                 headers={'x-paystack-signature': 'nope'})
        self.assertEqual(r.status_code, 401)


class AgentToolTests(BillingBase):
    def test_owner_runs_tools(self):
        self.make_owner()
        r = self.client.post('/api/receptionist/act', json={'tool': 'stats'}, headers=self.csrf())
        self.assertEqual(r.status_code, 200, r.data[:300])
        self.assertIn('leads', r.get_json()['result'])

    def test_lead_crud_through_agent(self):
        self.make_owner()
        h = self.csrf()
        r = self.client.post('/api/receptionist/act',
                             json={'tool': 'lead_create',
                                   'params': {'name': 'Agent Bakery', 'city': 'Lyon'}},
                             headers=h)
        self.assertEqual(r.status_code, 200, r.data[:300])
        lid = r.get_json()['result']['lead']['id']
        r = self.client.post('/api/receptionist/act',
                             json={'tool': 'lead_update',
                                   'params': {'id': lid, 'stage': 'Contacted'}},
                             headers=h)
        self.assertEqual(r.status_code, 200, r.data[:200])
        r = self.client.post('/api/receptionist/act', json={'tool': 'lead_get', 'params': {'id': lid}},
                             headers=h)
        self.assertEqual(r.get_json()['result']['lead']['stage'], 'Contacted')
        r = self.client.post('/api/receptionist/act',
                             json={'tool': 'lead_delete', 'params': {'id': lid}}, headers=h)
        self.assertEqual(r.status_code, 200)
        r = self.client.post('/api/receptionist/act', json={'tool': 'lead_get', 'params': {'id': lid}},
                             headers=h)
        self.assertEqual(r.status_code, 404)

    def test_unknown_tool_lists_tools(self):
        self.make_owner()
        r = self.client.post('/api/receptionist/act', json={'tool': 'nope'}, headers=self.csrf())
        self.assertEqual(r.status_code, 400)
        self.assertIn('lead_create', r.get_json()['error'])

    def test_client_cannot_run_tools_when_locked(self):
        self.make_client()
        with patch.dict('os.environ', {'DASHBOARD_PASSWORD': 'owner-secret'}):
            r = self.client.post('/api/receptionist/act', json={'tool': 'stats'}, headers=self.csrf())
        self.assertEqual(r.status_code, 403)

    def test_owner_chat_commands(self):
        self.make_owner()
        r = self.client.post('/api/receptionist/message', json={'message': '/stats'},
                             headers=self.csrf())
        self.assertEqual(r.status_code, 200, r.data[:300])
        data = r.get_json()
        self.assertEqual(data['intent'], 'owner_command')
        self.assertIn('Leads:', data['reply'])
        r = self.client.post('/api/receptionist/message', json={'message': '/help'},
                             headers=self.csrf())
        self.assertIn('/stats', r.get_json()['reply'])

    def test_public_chat_unaffected(self):
        r = self.client.post('/api/receptionist/message', json={'message': 'hello there'})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.get_json().get('intent'), 'owner_command')


import os

_BILLING_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(module.__file__)))


def _repo(path):
    with open(os.path.join(_BILLING_ROOT, path), encoding='utf-8') as f:
        return f.read()


class PeriodCheckoutTests(BillingBase):
    def _checkout(self, payload, ref):
        self.make_client()
        fake = {'authorization_url': 'https://pay.test/x', 'reference': ref}
        with patch('web.billing.paystack_request', return_value=fake) as m, \
                patch.dict('os.environ', {'PAYSTACK_SECRET_KEY': 'sk_test_x'}):
            r = self.client.post('/api/billing/checkout', json=payload, headers=self.csrf())
        return r, m

    def test_annual_checkout_charges_annual_price(self):
        r, m = self._checkout({'tier': 'starter', 'currency': 'USD', 'period': 'annual'}, 'rm-per1')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(m.call_args[0][2]['amount'], 19000)
        with module.db() as c:
            row = c.execute('SELECT period FROM payments WHERE reference=?', ('rm-per1',)).fetchone()
        self.assertEqual(row['period'], 'annual')

    def test_pro_annual_ngn_and_monthly_default(self):
        r, m = self._checkout({'tier': 'pro', 'currency': 'NGN', 'period': 'annual'}, 'rm-per2')
        self.assertEqual(m.call_args[0][2]['amount'], 90000000)
        r, m = self._checkout({'tier': 'starter', 'currency': 'USD'}, 'rm-per3')
        self.assertEqual(m.call_args[0][2]['amount'], 1900)
        with module.db() as c:
            row = c.execute('SELECT period FROM payments WHERE reference=?', ('rm-per3',)).fetchone()
        self.assertEqual(row['period'], 'monthly')

    def test_bad_period_rejected(self):
        self.make_client()
        with patch.dict('os.environ', {'PAYSTACK_SECRET_KEY': 'sk_test_x'}):
            r = self.client.post('/api/billing/checkout',
                                 json={'tier': 'starter', 'currency': 'USD', 'period': 'weekly'},
                                 headers=self.csrf())
        self.assertEqual(r.status_code, 400)


class PeriodActivationTests(BillingBase):
    def _days_granted(self, ref, amount, period):
        self.make_client()
        init = {'authorization_url': 'https://pay.test/x', 'reference': ref}
        verify = {'status': 'success', 'amount': amount, 'currency': 'USD', 'reference': ref}

        def fake(method, path, payload=None):
            return init if path == '/transaction/initialize' else verify

        with patch('web.billing.paystack_request', side_effect=fake), \
                patch.dict('os.environ', {'PAYSTACK_SECRET_KEY': 'sk_test_x'}):
            self.client.post('/api/billing/checkout',
                             json={'tier': 'starter', 'currency': 'USD', 'period': period},
                             headers=self.csrf())
            t0 = datetime.now(timezone.utc)
            r = self.client.get(f'/billing/callback?reference={ref}')
        self.assertEqual(r.status_code, 302)
        with module.db() as c:
            u = c.execute('SELECT tier_expires FROM users WHERE id=?', ('bill-client',)).fetchone()
        return (datetime.fromisoformat(u['tier_expires']) - t0).days

    def test_annual_grants_365_days(self):
        self.assertEqual(self._days_granted('rm-perA', 19000, 'annual'), 365)

    def test_monthly_grants_30_days(self):
        self.assertEqual(self._days_granted('rm-perM', 1900, 'monthly'), 30)


class PeriodStatusTests(BillingBase):
    def test_status_lists_annual_prices(self):
        data = self.client.get('/api/billing/status').get_json()
        self.assertEqual(data['prices']['starter']['usd_annual'], '$190')
        self.assertEqual(data['prices']['starter']['ngn_annual'], '₦300,000')
        self.assertEqual(data['prices']['pro']['usd_annual'], '$590')
        self.assertEqual(data['prices']['pro']['ngn_annual'], '₦900,000')


class CryptoPeriodTests(BillingBase):
    def test_crypto_options_echo_period(self):
        self.make_client()
        with patch.dict('os.environ', {'BTC_WALLET': '', 'ETH_WALLET': '',
                                       'SOL_WALLET': '', 'USDT_TRC20_WALLET': ''}, clear=False):
            r = self.client.get('/api/billing/crypto?tier=starter&period=annual')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['period'], 'annual')

    def test_crypto_bad_period_rejected(self):
        self.make_client()
        r = self.client.get('/api/billing/crypto?tier=starter&period=weekly')
        self.assertEqual(r.status_code, 400)


class PricingPeriodUITests(BillingBase):
    def test_pricing_shows_period_choice(self):
        body = self.client.get('/pricing').data.decode()
        for needle in ('Monthly', 'Annual', 'Save 17%', 'data-usd-a=', 'data-ngn-a=',
                       '>month</span>', 'crypto-period', 'dropdown.css', 'dropdown.js'):
            self.assertIn(needle, body)


class SwitcherFlagTests(BillingBase):
    def test_home_switcher_renders_six_flags(self):
        body = self.client.get('/').data.decode()
        for code in ('en', 'es', 'fr', 'de', 'pt', 'zh'):
            self.assertIn("%s:'<svg" % code, body)
        self.assertIn('id="locale-select"', body)

    def test_switcher_template_has_flags_and_fallback(self):
        s = _repo('templates/locale-switcher.html')
        self.assertGreaterEqual(s.count('<svg'), 6)
        self.assertIn('id="locale-select"', s)
        self.assertIn('setLocale', s)


class DropdownStandardTests(BillingBase):
    def test_enhancer_skips_native_and_multi(self):
        s = _repo('static/dropdown.js')
        for needle in ('data-native', 'multiple', 'aria-expanded', 'ReachmarkDropdown'):
            self.assertIn(needle, s)

    def test_select_pages_load_standard_dropdown(self):
        for page in ('index.html', 'pricing.html', 'receptionist-page.html', 'enquire.html', 'about.html'):
            s = _repo('templates/' + page)
            self.assertIn('dropdown.css', s, page)
            self.assertIn('dropdown.js', s, page)

    def test_form_selects_opt_into_standard(self):
        s = _repo('templates/enquiry-form.html')
        self.assertIn('<select', s)
        self.assertNotIn('data-native', s)
