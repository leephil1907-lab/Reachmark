"""Google Business Profile routes are registered and fail safely.

Regression: the reply / performance / posts handlers were once pasted inside
``_actor()``, so they were never registered and anonymous calls raised NameError.
No Google API is called here.
"""
import unittest

import tests.test_app as test_app
from tests.test_app import module


class GoogleBusinessRouteTests(unittest.TestCase):
    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    ROUTES = {
        ('GET', '/api/google-business/status'),
        ('GET', '/api/google-business/connect'),
        ('GET', '/api/google-business/oauth/callback'),
        ('POST', '/api/google-business/sync'),
        ('GET', '/api/google-business/locations'),
        ('GET', '/api/google-business/reviews'),
        ('POST', '/api/google-business/reviews/reply'),
        ('GET', '/api/google-business/performance'),
        ('POST', '/api/google-business/posts'),
    }

    def test_every_route_is_registered(self):
        registered = {(method, rule.rule)
                      for rule in module.app.url_map.iter_rules()
                      for method in rule.methods
                      if rule.rule.startswith('/api/google-business/')}
        self.assertEqual(self.ROUTES - registered, set())

    def test_actor_returns_none_for_anonymous_visitors(self):
        from web.google_business import _actor
        with module.app.test_request_context('/'):
            self.assertIsNone(_actor())

    def test_anonymous_status_does_not_crash(self):
        response = self.client.get('/api/google-business/status')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json['connected'])

    def test_write_routes_validate_input_for_the_owner(self):
        with self.client.session_transaction() as session:
            session['owner'] = True
            session['csrf'] = 'test-csrf'
        headers = {'X-CSRF-Token': 'test-csrf'}
        reply = self.client.post('/api/google-business/reviews/reply', json={}, headers=headers)
        self.assertEqual(reply.status_code, 400)
        post = self.client.post('/api/google-business/posts', json={}, headers=headers)
        self.assertEqual(post.status_code, 400)
        perf = self.client.get('/api/google-business/performance')
        self.assertEqual(perf.status_code, 400)
        missing = self.client.post('/api/google-business/reviews/reply', headers=headers,
                                   json={'location_id': 'nope', 'review_id': 'r1', 'comment': 'Thanks!'})
        self.assertEqual(missing.status_code, 404)


if __name__ == '__main__':
    unittest.main()
