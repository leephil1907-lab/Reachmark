"""AI receptionist page regressions. Disposable databases; no external calls.

Locks in: the page renders with the brand intact, the demo/tones/industries/FAQ
sections exist, the FAQ matches the knowledge base the chat answers from, the
live widget is embedded, and no competitor brand or invented proof appears.
"""
import json
import re
import unittest

import tests.test_app as test_app
class ReceptionistPageTests(unittest.TestCase):
    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def page(self):
        response = self.client.get('/receptionist')
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_page_renders_with_brand_and_identity_intact(self):
        html = self.page()
        self.assertIn('AI Receptionist', html)
        self.assertIn('Reachmark', html)
        self.assertIn('/static/manifest.webmanifest', html)
        self.assertIn('/static/icon.svg', html)
        self.assertIn('Every chat, enquiry and booking', html)

    def test_page_has_the_demo_flow_tones_industries_and_faq(self):
        html = self.page()
        for marker in ('data-step="0"', 'data-step="3"', 'Example conversation',
                       'data-tab="0"', 'data-tab="4"', 'data-say', 'rx-faq-list',
                       'Try it live', '/about#pricing', 'Included with every Reachmark build'):
            self.assertIn(marker, html, f'missing section marker: {marker}')

    def test_demo_panels_are_labelled_as_examples(self):
        html = self.page()
        self.assertGreater(html.count('Example'), 3,
                           'demo content must be visibly labelled as an example')

    def test_widget_panel_starts_hidden(self):
        """The panel must stay shut until the visitor opens it (close must work too)."""
        from pathlib import Path
        css = (Path(__file__).parent.parent / 'static' / 'receptionist.css').read_text(encoding='utf-8')
        self.assertRegex(css, r'\.rm-panel\[hidden\]\s*\{\s*display\s*:\s*none')
        tpl = (Path(__file__).parent.parent / 'templates' / 'receptionist.html').read_text(encoding='utf-8')
        self.assertIn('id="rm-receptionist" class="rm-panel" hidden', tpl)

    def test_live_widget_is_embedded(self):
        html = self.page()
        self.assertIn('id="rm-receptionist-launch"', html)
        self.assertIn('id="rm-receptionist"', html)
        self.assertIn('/static/receptionist.js', html)
        self.assertIn('/static/receptionist-page.js', html)
        self.assertIn('/static/receptionist-page.css', html)

    def test_faq_answers_come_from_the_knowledge_base(self):
        from web.receptionist import load_knowledge
        html = self.page()
        checked = 0
        for topic in load_knowledge():
            if topic['qa']:
                self.assertIn(topic['qa'][0]['a'][:60], html,
                              f"FAQ drifted from the knowledge base on '{topic['topic']}'")
                checked += 1
        self.assertGreater(checked, 5, 'knowledge base has no questions to render')

    def test_pricing_quotes_only_published_tiers(self):
        html = self.page()
        self.assertIn('Starter · $650', html)
        self.assertIn('Growth · $1,250', html)
        self.assertIn('Bespoke', html)

    def test_no_competitor_brand_or_invented_proof(self):
        html = self.page()
        low = html.lower()
        self.assertNotIn('ringcentral', low)
        self.assertNotIn('ringex', low)
        for invented in ('$1.7M', '97%', 'customer satisfaction', 'case study',
                         '★★★★★', '4.8/5', '127 reviews'):
            self.assertNotIn(invented, html, f'invented proof leaked onto the page: {invented}')

    def test_structured_faq_matches_the_knowledge_base(self):
        from web.receptionist import load_knowledge
        html = self.page()
        blobs = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        self.assertTrue(blobs, 'no structured data on the page')
        faqs = []
        for blob in blobs:
            try:
                data = json.loads(blob)
            except ValueError:
                continue
            for item in (data if isinstance(data, list) else [data]):
                if isinstance(item, dict) and item.get('@type') == 'FAQPage':
                    faqs.extend(item.get('mainEntity') or [])
        self.assertTrue(faqs, 'FAQPage structured data missing')
        first_answers = [t['qa'][0]['a'] for t in load_knowledge() if t['qa']]
        self.assertEqual(len(faqs), len(first_answers))
        for entity, answer in zip(faqs, first_answers):
            self.assertEqual(entity['acceptedAnswer']['text'], answer)

    def test_discoverable_via_sitemap_and_robots(self):
        sitemap = self.client.get('/sitemap.xml').get_data(as_text=True)
        self.assertIn('/receptionist', sitemap)
        robots = self.client.get('/robots.txt').get_data(as_text=True)
        self.assertIn('Allow: /receptionist', robots)

    def test_static_assets_are_served(self):
        css = self.client.get('/static/receptionist-page.css')
        self.assertEqual(css.status_code, 200)
        js = self.client.get('/static/receptionist-page.js')
        self.assertEqual(js.status_code, 200)
        body = js.get_data(as_text=True)
        self.assertIn('speechSynthesis', body)
        self.assertIn('rm-receptionist-launch', body)


if __name__ == '__main__':
    unittest.main()
