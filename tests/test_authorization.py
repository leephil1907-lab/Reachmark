import os
import unittest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

import web.app as module


class AuthorizationAuditTests(unittest.TestCase):
    def test_private_api_surface_requires_owner_session(self):
        private_routes = [
            ('GET', '/api/state'),
            ('POST', '/api/settings'),
            ('POST', '/api/leads'),
            ('GET', '/api/export'),
            ('POST', '/api/import'),
            ('POST', '/api/discover'),
            ('POST', '/api/jobs'),
            ('POST', '/api/jobs/not-a-real-job/cancel'),
            ('POST', '/api/leads/not-a-real-lead/audit'),
            ('POST', '/api/leads/not-a-real-lead/compose'),
            ('POST', '/api/leads/not-a-real-lead/suppress'),
            ('POST', '/api/leads/not-a-real-lead/send'),
            ('GET', '/api/quality'),
            ('GET', '/api/map/state'),
            ('POST', '/api/map/search'),
            ('GET', '/api/projects'),
            ('GET', '/api/contracts'),
            ('GET', '/api/invoices'),
            ('GET', '/api/mcp'),
            ('GET', '/api/analytics'),
            ('GET', '/api/operations/readiness'),
            ('GET', '/api/documents/invoice/not-a-real-record.pdf'),
            ('GET', '/api/snapshots'),
            ('GET', '/api/verify-config'),
            ('GET', '/api/outbox'),
            ('GET', '/api/review-links'),
            ('GET', '/api/crew'),
            ('GET', '/api/crew/playbook'),
            ('GET', '/api/receptionist/threads'),
            ('GET', '/api/admin/users'),
            ('GET', '/api/admin/payments'),
            ('GET', '/api/admin/newsletter'),
            ('GET', '/api/webhooks'),
        ]
        env = {
            'OWNER_PASSWORD_HASH': generate_password_hash('audit-owner-password'),
            'DASHBOARD_PASSWORD': '',
        }
        with patch.dict(os.environ, env, clear=False):
            client = module.app.test_client()
            for method, path in private_routes:
                response = getattr(client, method.lower())(path)
                self.assertEqual(
                    response.status_code, 401,
                    f'{method} {path} was not protected: {response.status_code}')
            self.assertEqual(client.get('/healthz').status_code, 200)
            self.assertEqual(client.get('/login').status_code, 200)


if __name__ == '__main__':
    unittest.main()
