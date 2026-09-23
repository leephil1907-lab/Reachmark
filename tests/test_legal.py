"""Legal pages: public, English-authoritative, interlinked, reachable from footer/auth."""
from tests.test_crew import CrewBase


class LegalTests(CrewBase):
    PAGES = (
        ('/privacy', 'Privacy Policy'),
        ('/terms', 'Terms of Service'),
        ('/disclosure', 'Disclosures'),
    )

    def test_pages_are_public_and_english_locked(self):
        for path, title in self.PAGES:
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            body = r.data.decode()
            self.assertIn(title, body)
            self.assertIn('<html lang="en"', body)
            self.assertIn('23 September 2026', body)
            for link in ('/privacy', '/terms', '/disclosure'):
                self.assertIn(f'href="{link}"', body, f'{path} missing {link}')

    def test_home_footer_links_legal_pages(self):
        body = self.client.get('/').data.decode()
        for link in ('/privacy', '/terms', '/disclosure'):
            self.assertIn(f'href="{link}"', body)

    def test_auth_pages_link_terms_and_privacy(self):
        for path in ('/signup', '/signin'):
            body = self.client.get(path).data.decode()
            self.assertIn('href="/terms"', body, path)
            self.assertIn('href="/privacy"', body, path)

    def test_legal_pages_carry_support_bubble_but_no_ads(self):
        for path, _ in self.PAGES:
            body = self.client.get(path).data.decode()
            self.assertIn('tawk', body.lower(), f'{path} missing support bubble')
            self.assertNotIn('adsbygoogle', body, f'{path} should stay ad-free')
