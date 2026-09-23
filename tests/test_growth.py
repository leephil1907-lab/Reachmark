"""Newsletter, crypto checkout, studio console, receipts, samples, session-aware navs.

CoinGecko is stubbed (web.crypto.coin_prices); no network is touched.
"""
import os
import re
from unittest.mock import patch

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

WALLETS = {'BTC_WALLET': 'bc1qtestwallet0000000000000000000000000',
           'ETH_WALLET': '0xTestWallet000000000000000000000000000000',
           'SOL_WALLET': 'SolTestWallet0000000000000000000000000000',
           'USDT_TRC20_WALLET': 'TTestWallet00000000000000000000000'}
RATES = {'bitcoin': 50000.0, 'ethereum': 2500.0, 'solana': 100.0, 'tether': 1.0}


class NewsletterTests(SwitchedBase):
    def test_subscribe_validates_and_welcomes(self):
        r = self.client.post('/api/newsletter', json={'email': 'not-an-email'})
        self.assertEqual(r.status_code, 400)
        r = self.client.post('/api/newsletter', json={'email': 'fan@example.test', 'source': '/pricing'})
        self.assertEqual(r.status_code, 200)
        with module.db() as c:
            row = c.execute('SELECT * FROM newsletter_subscribers WHERE email=?',
                            ('fan@example.test',)).fetchone()
            self.assertIsNotNone(row)
            mail = c.execute("SELECT subject FROM mail_outbox WHERE to_email=? "
                             "ORDER BY created DESC LIMIT 1", ('fan@example.test',)).fetchone()
        self.assertIn('studio notes', mail['subject'])
        # Resubscribing is idempotent, not an error.
        r = self.client.post('/api/newsletter', json={'email': 'fan@example.test'})
        self.assertEqual(r.status_code, 200)

    def test_newsletter_admin_is_owner_only_when_locked(self):
        self.client.post('/api/newsletter', json={'email': 'fan@example.test'})
        with patch.dict('os.environ', {'DASHBOARD_PASSWORD': 'owner-secret'}):
            self.make_client()
            r = self.client.get('/api/admin/newsletter')
            self.assertEqual(r.status_code, 403)
            self.switch_owner('owner-secret')
            r = self.client.get('/api/admin/newsletter')
            self.assertEqual(r.status_code, 200)
            self.assertTrue(any(s['email'] == 'fan@example.test' for s in r.get_json()['subscribers']))
            r = self.client.get('/api/admin/newsletter/export')
            self.assertEqual(r.status_code, 200)
            self.assertIn('text/csv', r.headers['Content-Type'])
            self.assertIn('fan@example.test', r.data.decode())


class ConsoleTests(SwitchedBase):
    def test_admin_users_and_manual_grant(self):
        self.make_client()
        with patch.dict('os.environ', {'DASHBOARD_PASSWORD': 'owner-secret'}):
            r = self.client.get('/api/admin/users')
            self.assertEqual(r.status_code, 403)
            self.switch_owner('owner-secret')
            r = self.client.get('/api/admin/users')
            self.assertEqual(r.status_code, 200)
            self.assertTrue(any(u['email'] == 'bill@example.test' for u in r.get_json()['users']))
            r = self.client.patch('/api/admin/users/bill-client',
                                  json={'tier': 'starter', 'days': 30, 'note': 'bank transfer'},
                                  headers=self.csrf())
            self.assertEqual(r.status_code, 200)
        with module.db() as c:
            u = c.execute("SELECT tier,tier_expires FROM users WHERE id='bill-client'").fetchone()
            pay = c.execute("SELECT currency,status,raw FROM payments WHERE user_id='bill-client'").fetchone()
        self.assertEqual(u['tier'], 'starter')
        self.assertTrue(u['tier_expires'] > module.now())
        self.assertEqual(pay['currency'], 'MANUAL')
        self.assertEqual(pay['status'], 'paid')
        self.assertIn('bank transfer', pay['raw'])
        # Revoke back to free and pause the account.
        self.switch_owner()
        self.client.patch('/api/admin/users/bill-client', json={'tier': 'free'}, headers=self.csrf())
        self.client.patch('/api/admin/users/bill-client', json={'is_active': False}, headers=self.csrf())
        with module.db() as c:
            u = c.execute("SELECT tier,is_active FROM users WHERE id='bill-client'").fetchone()
        self.assertEqual(u['tier'], 'free')
        self.assertEqual(u['is_active'], 0)


class CryptoTests(SwitchedBase):
    def test_anonymous_crypto_rejected(self):
        self.assertEqual(self.client.get('/api/billing/crypto?tier=starter').status_code, 401)
        r = self.client.post('/api/billing/crypto/checkout', json={'tier': 'starter', 'coin': 'BTC'})
        self.assertEqual(r.status_code, 401)

    def test_pricing_page_offers_crypto(self):
        body = self.client.get('/pricing').data.decode()
        self.assertIn('pay with crypto', body)
        self.assertIn('crypto-tier', body)

    def test_options_need_tier_and_configured_wallets(self):
        self.make_client()
        r = self.client.get('/api/billing/crypto?tier=bogus')
        self.assertEqual(r.status_code, 400)
        with patch.dict('os.environ', {k: '' for k in WALLETS}, clear=False):
            r = self.client.get('/api/billing/crypto?tier=starter')
            self.assertEqual(r.get_json()['coins'], [])

    def test_full_manual_crypto_flow(self):
        self.make_client()
        with patch.dict('os.environ', WALLETS), \
                patch('web.crypto.coin_prices', return_value=dict(RATES)):
            r = self.client.get('/api/billing/crypto?tier=starter')
            coins = r.get_json()['coins']
            self.assertEqual(len(coins), 5)
            btc = next(c for c in coins if c['coin'] == 'BTC')
            self.assertTrue(btc['qr'].startswith('data:image/png;base64,'))
            self.assertEqual(btc['usd'], 25)
            self.assertAlmostEqual(btc['coin_amount'], 25 / 50000.0, places=8)
            usdt = next(c for c in coins if c['coin'] == 'USDT_ERC20')
            self.assertEqual(usdt['address'], WALLETS['ETH_WALLET'])
            # Checkout an unconfigured coin is refused.
            r = self.client.post('/api/billing/crypto/checkout',
                                 json={'tier': 'starter', 'coin': 'DOGE'}, headers=self.csrf())
            self.assertEqual(r.status_code, 400)
            r = self.client.post('/api/billing/crypto/checkout',
                                 json={'tier': 'starter', 'coin': 'BTC'}, headers=self.csrf())
            self.assertEqual(r.status_code, 200)
            ref = r.get_json()['reference']
            self.assertTrue(r.get_json()['qr'].startswith('data:image/png;base64,'))
            # A stub hash is refused; a real-looking one queues for approval.
            r = self.client.post('/api/billing/crypto/submit',
                                 json={'reference': ref, 'tx_hash': 'short'},
                                 headers=self.csrf())
            self.assertEqual(r.status_code, 400)
            r = self.client.post('/api/billing/crypto/submit',
                                 json={'reference': ref, 'tx_hash': 'f' * 64},
                                 headers=self.csrf())
            self.assertEqual(r.status_code, 200)
            with module.db() as c:
                p = c.execute('SELECT status,tx_hash FROM payments WHERE reference=?', (ref,)).fetchone()
            self.assertEqual(p['status'], 'awaiting_approval')
            # No receipt before approval.
            self.assertEqual(self.client.get(f'/api/billing/receipt/{ref}.pdf').status_code, 400)
            # Owner approval activates the plan and unlocks the receipt.
            self.switch_owner()
            r = self.client.post(f'/api/admin/payments/{ref}/approve', headers=self.csrf())
            self.assertEqual(r.status_code, 200)
            with module.db() as c:
                u = c.execute("SELECT tier,tier_expires FROM users WHERE id='bill-client'").fetchone()
            self.assertEqual(u['tier'], 'starter')
            self.assertTrue(u['tier_expires'] > module.now())
            r = self.client.get(f'/api/billing/receipt/{ref}.pdf')
            self.assertEqual(r.status_code, 200)
            self.assertIn('application/pdf', r.headers['Content-Type'])
            self.assertTrue(r.data.startswith(b'%PDF'))
            # Rejecting a paid payment is refused.
            r = self.client.post(f'/api/admin/payments/{ref}/reject', headers=self.csrf())
            self.assertEqual(r.status_code, 400)

    def test_receipt_is_private_to_owner_and_payer(self):
        self.make_client()
        with patch.dict('os.environ', WALLETS), \
                patch('web.crypto.coin_prices', return_value=dict(RATES)):
            ref = self.client.post('/api/billing/crypto/checkout',
                                   json={'tier': 'pro', 'coin': 'SOL'},
                                   headers=self.csrf()).get_json()['reference']
            self.client.post('/api/billing/crypto/submit',
                             json={'reference': ref, 'tx_hash': 'a' * 64}, headers=self.csrf())
        self.switch_owner()
        self.client.post(f'/api/admin/payments/{ref}/approve', headers=self.csrf())
        # A different signed-in client gets 403, not the PDF.
        with module.db() as c:
            c.execute('INSERT OR REPLACE INTO users(id,email,password_hash,name,role,is_active,created,updated) '
                      "VALUES('other-client','other@example.test','x','Other','client',1,?,?)",
                      (module.now(), module.now()))
        with self.client.session_transaction() as s:
            s.clear()
            s['client_id'] = 'other-client'
            s['role'] = 'client'
            s['csrf'] = 'test-csrf'
        r = self.client.get(f'/api/billing/receipt/{ref}.pdf')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get('/api/billing/receipt/nope.pdf').status_code, 404)


class VerifyMailTests(SwitchedBase):
    def test_verify_sends_welcome_with_dashboard_link(self):
        page = self.client.get('/signup').get_data(as_text=True)
        tok = re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)
        r = self.client.post('/api/auth/signup',
                             json={'name': 'New Fan', 'email': 'newfan@example.test',
                                   'password': 'password123'},
                             headers={'X-CSRF-Token': tok})
        self.assertEqual(r.status_code, 201)
        with module.db() as c:
            token = c.execute('SELECT verification_token FROM users WHERE email=?',
                              ('newfan@example.test',)).fetchone()['verification_token']
        self.assertTrue(token)
        r = self.client.get(f'/verify/{token}')
        self.assertEqual(r.status_code, 200)
        self.assertIn('/dashboard', r.data.decode())
        with module.db() as c:
            mail = c.execute("SELECT subject,body FROM mail_outbox WHERE to_email=? "
                             "ORDER BY created DESC LIMIT 1", ('newfan@example.test',)).fetchone()
        self.assertIn('Welcome to Reachmark', mail['subject'])


class SamplesTests(SwitchedBase):
    def test_ten_samples_with_working_crypto_pages(self):
        from web.portfolio import SAMPLES
        self.assertEqual(len(SAMPLES), 10)
        for slug in ('nova-exchange', 'orbit-web3'):
            r = self.client.get(f'/showcase/{slug}')
            self.assertEqual(r.status_code, 200, slug)
        body = self.client.get('/showcase').data.decode()
        self.assertIn('Nova Exchange', body)
        self.assertIn('Orbit Studio', body)


class SessionNavTests(SwitchedBase):
    def test_nav_adapts_to_session(self):
        self.assertIn('Create account', self.client.get('/').data.decode())
        self.make_client()
        self.assertIn('/dashboard', self.client.get('/').data.decode())
        self.assertIn('/dashboard', self.client.get('/pricing').data.decode())
        with self.client.session_transaction() as s:
            s.clear()
            s['owner'] = True
        self.assertIn('/workspace', self.client.get('/').data.decode())

    def test_support_email_visible_on_public_pages(self):
        for path in ('/', '/pricing', '/showcase', '/enquire', '/receptionist'):
            self.assertIn('reachmarkofficial@gmail.com', self.client.get(path).data.decode(), path)
