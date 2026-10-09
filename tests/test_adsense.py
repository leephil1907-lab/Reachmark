"""AdSense account verification regression tests."""
import unittest

import tests.test_app as test_app

CLIENT = 'ca-pub-5678865896620902'
META = f'<meta name="google-adsense-account" content="{CLIENT}">'
LOADER = f'pagead/js/adsbygoogle.js?client={CLIENT}'
SELLER = 'google.com, pub-5678865896620902, DIRECT, f08c47fec0942fa0'


class AdSenseTests(unittest.TestCase):
    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def test_homepage_has_account_meta_and_loader_once(self):
        body = self.client.get('/').get_data(as_text=True)
        self.assertIn(META, body)
        self.assertIn(LOADER, body)
        self.assertIn('crossorigin="anonymous"', body)
        self.assertEqual(body.count('adsbygoogle.js'), 1)

    def test_ads_txt_declares_the_supplied_publisher(self):
        response = self.client.get('/ads.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response.headers.get('Content-Type', ''))
        self.assertEqual(response.get_data(as_text=True).strip(), SELLER)

    def test_content_security_policy_allows_the_ad_loader(self):
        policy = self.client.get('/').headers.get('Content-Security-Policy', '')
        self.assertIn('https://pagead2.googlesyndication.com', policy)
        self.assertIn('https://googleads.g.doubleclick.net', policy)
        self.assertIn('https://tpc.googlesyndication.com', policy)
        self.assertNotIn('\\\\', policy)


if __name__ == '__main__':
    unittest.main()
