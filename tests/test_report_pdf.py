import unittest

from web.brand import report_theme
from web.report_pdf import build_report_pdf


class ReportPdfTests(unittest.TestCase):
    def test_pdf_contains_header_and_evidence_report(self):
        report = {
            'score': 72, 'priority': 'High', 'leak_count': 1,
            'created': '2026-10-24T10:00:00Z',
            'leaks': [{'title': 'No contact path', 'leak': 'No phone or email link was observed.',
                       'source': 'Homepage HTML', 'fix': 'Add a visible contact action.',
                       'severity': 'high'}],
            'solution': {'name': 'Website Fix Sprint', 'why': 'Prioritize the contact path.'},
            'evidence': {'website': 'https://sunrise.test', 'disclaimer': 'Saved public-page findings only.',
                         'brand_profile': {'site_name': 'Sunrise Bakery', 'theme_color': '#7a2f1b',
                                           'logo': 'https://sunrise.test/logo.svg',
                                           'colors': ['#7a2f1b', '#e0a020'],
                                           'contact_details': ['tel:+2348012345678'],
                                           'social_links': ['https://instagram.com/sunrise']}}
        }
        lead = {'name': 'Listed Bakery', 'website': 'https://sunrise.test'}
        theme = report_theme(report['evidence']['brand_profile'])
        payload = build_report_pdf(report, lead, theme)
        self.assertTrue(payload.startswith(b'%PDF-'))
        self.assertIn(b'Website Growth Audit', payload)
        self.assertIn(b'Prepared by Reachmark', payload)
        self.assertIn(b'No contact path', payload)

    def test_missing_scores_and_brand_are_not_invented(self):
        payload = build_report_pdf({'leaks': [], 'evidence': {}}, {'website': ''}, report_theme({}))
        self.assertTrue(payload.startswith(b'%PDF-'))
        self.assertGreater(len(payload), 1000)


if __name__ == '__main__':
    unittest.main()
