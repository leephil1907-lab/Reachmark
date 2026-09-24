"""Builder memory: the 14 user-supplied briefs are stored versioned, matched by
trade, and applied with the business's own facts winning over placeholders."""
import unittest

import agents.agent_builder as agent_builder
from builder.memory import apply_prompt, list_prompts, load_memory, match_prompt

WEBSITE_IDS = ['illustrator-portfolio', 'developer-portfolio',
               'photographer-linkinbio', 'architecture-firm', 'smarthome-preorder',
               'course-landing', 'sports-ecommerce', 'nonprofit-donation',
               'ebook-landing', 'realestate-agency', 'support-dashboard',
               'jewelry-store']
BLUEPRINT_IDS = ['notification-service', 'file-upload-service']

# Trade-representative lead categories: each must match its own brief only.
CATEGORY_FOR = {'illustrator-portfolio': 'Illustrator',
                'developer-portfolio': 'Web Developer',
                'photographer-linkinbio': 'Wedding Photographer',
                'architecture-firm': 'Architecture Firm',
                'smarthome-preorder': 'Smart Home Devices',
                'course-landing': 'Online Course',
                'sports-ecommerce': 'Sports Equipment',
                'nonprofit-donation': 'Nonprofit',
                'ebook-landing': 'eBook',
                'realestate-agency': 'Real Estate Agency',
                'support-dashboard': 'Helpdesk Software',
                'jewelry-store': 'Jewelry Store'}

PLACEHOLDERS = ['Riley Morgan', 'Chris Anderson', 'Moments by Maya',
                'Horizon Design Studio', 'HomeHub Pro',
                'Master Digital Marketing in 30 Days', 'ProGear Athletics',
                'Clean Ocean Initiative', 'The Ultimate Guide to Remote Work',
                'Prime Properties', 'SupportMetrics', 'GemCraft']


def sample_lead(category, name='Harbor & Lark'):
    return {'id': 'LX', 'name': name, 'category': category, 'city': 'Portland',
            'phone': '+1 555 0100', 'email': 'hello@example.test'}


class StoreTests(unittest.TestCase):
    def test_version_and_count(self):
        store = load_memory()
        self.assertEqual(store['memory_version'], '1.0.0')
        self.assertEqual(len(store['prompts']), 14)

    def test_ids_unique_and_complete(self):
        ids = [p['id'] for p in load_memory()['prompts']]
        self.assertEqual(len(set(ids)), 14)
        self.assertEqual(set(ids), set(WEBSITE_IDS + BLUEPRINT_IDS))

    def test_kinds_split_twelve_websites_two_blueprints(self):
        self.assertEqual(len(list_prompts('website')), 12)
        self.assertEqual(len(list_prompts('service-blueprint')), 2)
        self.assertEqual({p['id'] for p in list_prompts('service-blueprint')},
                         set(BLUEPRINT_IDS))

    def test_website_briefs_are_build_ready(self):
        for entry in list_prompts('website'):
            with self.subTest(brief=entry['id']):
                self.assertTrue(entry['purpose'], 'purpose required')
                self.assertGreaterEqual(len(entry['features']), 3)
                self.assertTrue(entry['match'], 'match keywords required')
                self.assertIn(entry['theme_family'], agent_builder.FAMILIES)
                self.assertTrue(entry['example_name'], 'example name required')
                self.assertIn(entry['example_name'], entry['placeholders'])

    def test_raw_brief_text_preserved_for_audit(self):
        for entry in load_memory()['prompts']:
            with self.subTest(brief=entry['id']):
                self.assertIn(entry['id'].split('-')[0][:4].lower(),
                              entry['raw'].lower())
                self.assertGreater(len(entry['raw']), 100)


class MatchTests(unittest.TestCase):
    def test_each_trade_matches_its_own_brief(self):
        for brief_id, category in CATEGORY_FOR.items():
            with self.subTest(brief=brief_id):
                hit = match_prompt(category, 'Harbor & Lark')
                self.assertIsNotNone(hit, f'{category} matched nothing')
                self.assertEqual(hit['id'], brief_id)

    def test_blueprints_match_but_stay_blueprints(self):
        hit = match_prompt('Notification Service')
        self.assertIsNotNone(hit)
        self.assertEqual(hit['id'], 'notification-service')
        self.assertEqual(hit['kind'], 'service-blueprint')
        hit = match_prompt('File Upload Service')
        self.assertIsNotNone(hit)
        self.assertEqual(hit['id'], 'file-upload-service')

    def test_unmatched_trades_match_nothing(self):
        for category in ['Bakery', 'Café', 'Plumber', 'Gym', 'Golf Course',
                         'Dentist', 'Hairdresser']:
            with self.subTest(category=category):
                self.assertIsNone(match_prompt(category, 'Harbor & Lark'))

    def test_matching_is_deterministic(self):
        first = match_prompt('Real Estate Agency', 'Harbor & Lark')['id']
        second = match_prompt('Real Estate Agency', 'Harbor & Lark')['id']
        self.assertEqual(first, second)


class ComposeTests(unittest.TestCase):
    def test_brief_structure_business_facts(self):
        for brief_id, category in CATEGORY_FOR.items():
            with self.subTest(brief=brief_id):
                lead = sample_lead(category)
                concept = agent_builder.compose_concept(
                    lead, {'agency': 'Reachmark'}, 'Professional')
                mem = concept.get('memory') or {}
                self.assertTrue(mem.get('applied'))
                self.assertEqual(mem['prompt_id'], brief_id)
                self.assertEqual(mem['memory_version'], '1.0.0')
                brief = next(p for p in list_prompts() if p['id'] == brief_id)
                self.assertEqual(len(concept['sections']), len(brief['features']))
                page = ' '.join([concept['headline'], concept['intro']] +
                                [s['title'] + ' ' + s['body']
                                 for s in concept['sections']])
                for holder in PLACEHOLDERS:
                    self.assertNotIn(holder, page,
                                     f'placeholder {holder!r} leaked into {brief_id}')
                self.assertIn('Harbor & Lark', concept['intro'])
                self.assertFalse(any(ch.isdigit() for ch in concept['intro']),
                                 'memory intros stay digit-free for the CRO check')

    def test_memory_concepts_pass_every_cro_check(self):
        for brief_id, category in CATEGORY_FOR.items():
            with self.subTest(brief=brief_id):
                concept = agent_builder.compose_concept(
                    sample_lead(category), {'agency': 'Reachmark'}, 'Professional')
                checks, _words = agent_builder.cro_checks(concept)
                failed = [c['name'] for c in checks if not c['ok']]
                self.assertEqual(failed, [])

    def test_blueprints_never_produce_website_concepts(self):
        for entry in list_prompts('service-blueprint'):
            with self.assertRaises(ValueError):
                apply_prompt(entry, sample_lead('SaaS'))
        for category in ['Notification Service', 'File Upload Service']:
            concept = agent_builder.compose_concept(
                sample_lead(category), {'agency': 'Reachmark'}, 'Professional')
            self.assertFalse((concept.get('memory') or {}).get('applied'))

    def test_unmatched_trades_keep_family_treatment(self):
        concept = agent_builder.compose_concept(
            sample_lead('Bakery', 'Copper Kettle'), {'agency': 'Reachmark'},
            'Professional')
        self.assertEqual(concept['family'], 'food')
        self.assertFalse((concept.get('memory') or {}).get('applied'))
        concept = agent_builder.compose_concept(
            sample_lead('Plumber', 'Truefix'), {'agency': 'Reachmark'},
            'Professional')
        self.assertEqual(concept['family'], 'trades')

    def test_mock_data_escape_hatch_is_refused(self):
        concept = agent_builder.compose_concept(
            sample_lead('Helpdesk Software'), {'agency': 'Reachmark'},
            'Professional')
        self.assertTrue(concept['memory'].get('mock_data_refused'))
        bodies = ' '.join(s['body'] for s in concept['sections'])
        self.assertIn('figures come only from your real system', bodies)
        self.assertNotIn('mock data', bodies.lower())

    def test_apply_is_deterministic(self):
        brief = next(p for p in list_prompts() if p['id'] == 'jewelry-store')
        lead = sample_lead('Jewelry Store')
        self.assertEqual(apply_prompt(brief, lead), apply_prompt(brief, lead))


if __name__ == '__main__':
    unittest.main()
