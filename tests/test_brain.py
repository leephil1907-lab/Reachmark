"""Brand-brain regressions: one shared source of truth for every agent.

Locks in: the brain's facts and accessors, the knowledge engine's move to
crew.business (web.receptionist re-exports the same objects), every agent
quoting the brain instead of hardcoding copy, Ctx.brand, the /api/crew brain
field, the live front-desk status, and drift guards that fail if a price or
an ethics line is ever pasted back into agent code or the page template.
"""
import json
import os
import re
import unittest

import tests.test_app as test_app
from crew import business
import crew.crew as crew_module
import agents.agent_builder as agent_builder
import agents.agent_scribe as agent_scribe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_FILES = ['agent_scout.py', 'agent_auditor.py', 'agent_builder.py', 'agent_scribe.py',
               'agent_closer.py', 'agent_receptionist.py', 'agent_brag.py', 'agent_video.py']


def source(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


class BrainFactsTests(unittest.TestCase):
    def test_version_is_pinned(self):
        self.assertRegex(business.BRAIN_VERSION, r'^\d+\.\d+\.\d+$')

    def test_tiers_match_the_published_offer(self):
        self.assertEqual(set(business.TIERS), {'starter', 'growth', 'bespoke'})
        self.assertEqual(business.TIERS['starter']['price'], 650)
        self.assertEqual(business.TIERS['growth']['price'], 1250)
        self.assertIsNone(business.TIERS['bespoke']['price'])

    def test_tier_lines_use_fixed_wording(self):
        self.assertEqual(business.tier_line('starter'), 'Starter · $650')
        self.assertEqual(business.tier_line('growth'), 'Growth · $1,250')
        self.assertEqual(business.tier_line('bespoke'), 'Bespoke · estimate')
        self.assertEqual(business.tier_line('nope'), '')

    def test_price_mention_and_contacts(self):
        self.assertIn('$650', business.price_mention())
        self.assertEqual(business.CONTACT['enquiry_path'], '/enquire')
        self.assertEqual(business.CONTACT['receptionist_path'], '/receptionist')

    def test_accessors_fall_back_instead_of_guessing(self):
        self.assertEqual(business.opt_out('sms'), business.ETHICS['opt_out_sms'])
        self.assertEqual(business.opt_out('pigeon'), business.ETHICS['opt_out_email'])
        self.assertEqual(business.facts_for('no such topic'), [])
        self.assertTrue(business.facts_for('pricing'))
        fallback = business.brand_for('no such agent')
        self.assertEqual(fallback['focus'], business.brand_for('receptionist')['focus'])
        self.assertEqual(fallback['brain'], business.BRAIN_VERSION)

    def test_brief_is_self_contained(self):
        brief = business.brief()
        for needle in ('Reachmark', business.TAGLINE, '$650', '$1,250',
                       business.ETHICS['opt_out_email'], business.VOICE['signoff']):
            self.assertIn(needle, brief)

    def test_public_is_template_safe_json(self):
        payload = json.loads(json.dumps(business.public()))
        self.assertEqual(payload['studio'], 'Reachmark')
        self.assertEqual([row['id'] for row in payload['tiers']], ['starter', 'growth', 'bespoke'])
        self.assertEqual(payload['tiers'][0]['line'], 'Starter · $650')

    def test_lifecycle_covers_start_to_review(self):
        stages = business.lifecycle()
        self.assertEqual(len(stages), 8)
        self.assertEqual(stages[0]['stage'], 'discover')
        self.assertEqual(stages[-1]['stage'], 'review')
        owners = {stage['owner'] for stage in stages}
        self.assertLessEqual(owners, set(crew_module.AGENTS_BY_ID) | {'studio'})

    def test_review_ask_is_personal_and_optional(self):
        ask = business.review_ask('Maya', 'Maya Cuts site')
        self.assertIn('Maya', ask['subject'])
        self.assertIn('Maya Cuts site', ask['body'])
        self.assertIn('only if', ask['body'].lower())


class EngineMovedTests(unittest.TestCase):
    def test_receptionist_reexports_the_brain_engine(self):
        import web.receptionist as receptionist
        self.assertIs(receptionist.load_knowledge, business.load_knowledge)
        self.assertIs(receptionist.match_answer, business.match_answer)
        self.assertIs(receptionist.detect_intent, business.detect_intent)
        self.assertEqual(receptionist.MIN_SCORE, business.MIN_SCORE)
        self.assertEqual(receptionist.KB_PATH, business.KB_PATH)

    def test_matching_still_answers_from_published_facts(self):
        topic, _question, answer, score = business.match_answer('how much does a website cost')
        self.assertIn('pricing', topic)
        self.assertGreater(score, 0)
        self.assertIn('$650', answer)


class InfusionTests(unittest.TestCase):
    def test_every_agent_quotes_the_brain(self):
        for filename in AGENT_FILES:
            body = source('agents', filename)
            self.assertIn('crew.business', body, f'{filename} does not import the brain')

    def test_context_carries_the_brand(self):
        ctx = crew_module.Ctx({'params': {}},
                              {'db': None, 'now': '', 'log': lambda *args: None,
                               'settings': lambda: {}, 'deadline': 0})
        self.assertIs(ctx.brand, business)
        self.assertEqual(ctx.brand.BRAIN_VERSION, business.BRAIN_VERSION)

    def test_share_message_quotes_the_brain_word_for_word(self):
        text = agent_builder.compose_share_message({'name': 'T'}, {}, 'Reachmark', '', 'https://x/r/abc')
        self.assertIn(business.ETHICS['opt_out_share'], text)

    def test_chat_message_quotes_the_brain_word_for_word(self):
        text = agent_builder.compose_chat_message({'name': 'T'}, 'Reachmark', 'https://x/r/abc')
        self.assertIn(business.ETHICS['chat_no_charge'], text)
        self.assertIn(business.ETHICS['opt_out_chat'], text)

    def test_drafts_carry_the_exact_opt_outs(self):
        draft = agent_scribe.deterministic_draft(
            {'id': 't', 'name': 'T Test'},
            {'share_url': 'https://x/r/abc', 'studio': 'Reachmark'}, {}, {})
        self.assertIn(business.ETHICS['opt_out_email'], draft['email1'])
        self.assertIn(business.ETHICS['opt_out_sms'], draft['sms'])


class ApiBrainTests(unittest.TestCase):
    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def test_crew_state_reports_the_brain(self):
        brain = self.client.get('/api/crew').get_json()['brain']
        self.assertEqual(brain['version'], business.BRAIN_VERSION)
        self.assertEqual(brain['tiers']['starter']['price'], 650)
        self.assertEqual(brain['tiers']['growth']['price'], 1250)
        self.assertEqual(len(brain['lifecycle']), 8)

    def test_frontdesk_status_is_live(self):
        status = self.client.get('/api/frontdesk/status').get_json()
        self.assertTrue(status['ok'])
        self.assertEqual(status['brain'], business.BRAIN_VERSION)
        self.assertGreater(status['topics'], 5)
        self.assertGreater(status['questions'], 5)
        html = self.client.get('/receptionist').get_data(as_text=True)
        self.assertIn('data-frontdesk-status', html)


class NoHardcodedFactsTests(unittest.TestCase):
    COPIES = [business.ETHICS[key] for key in (
        'opt_out_email', 'opt_out_sms', 'opt_out_share', 'opt_out_chat', 'opt_out_sms_note',
        'chat_no_charge', 'concept_intro', 'concept_disclaimer', 'contact_basis', 'suppression')]
    COPIES += ['Starter · $650', 'Growth · $1,250', '$650', '$1,250']

    def test_no_agent_pastes_brain_copy(self):
        bodies = [source('agents', name) for name in AGENT_FILES]
        bodies += [source('crew', 'crew.py'), source('crew', 'skills_loader.py')]
        names = AGENT_FILES + ['crew.py', 'skills_loader.py']
        for literal in self.COPIES:
            fragments = [part for part in re.split(r'\{[^}]*\}', literal) if len(part) >= 20]
            needle = max(fragments, key=len) if fragments else literal
            for filename, body in zip(names, bodies):
                self.assertNotIn(needle, body, f'{filename} hardcodes brain copy: {needle[:50]}')

    def test_template_renders_prices_from_the_brain(self):
        template = source('templates', 'receptionist-page.html')
        self.assertNotIn('$650', template)
        self.assertNotIn('$1,250', template)
        self.assertIn('tiers.growth', template)
        self.assertIn('brand.tiers', template)


if __name__ == '__main__':
    unittest.main()
