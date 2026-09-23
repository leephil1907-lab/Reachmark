"""The Brag video step: honest script, honest availability, honest route.

Nothing here needs Playwright or ffmpeg — the parts that can be checked without a browser
are the parts that decide what the ad may claim. The rendering itself is exercised by
``scripts/render_ad.py`` and reported by ``/api/crew``.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

import agents.agent_video as agent_video
import tests.test_app as test_app
from tests.test_app import module
from web.review_links import create_link

LEAD = {'id': 'L1', 'name': 'Test Bakery', 'category': 'Bakery', 'city': 'Demo City', 'phone': '+1 555 0100'}
CONCEPT = {'theme': 'ember', 'headline': 'Hello', 'intro': 'x', 'gaps': ['No website listed in the public listing'],
           'family_label': 'bakery & cafés', 'contact': {'phone': '+1 555 0100'}}


class AdScriptTests(unittest.TestCase):
    """What the ad says is limited to what the record says."""

    def script(self, views=0, gaps=None, phone='+1 555 0100', name='Test Bakery', email=''):
        lead = dict(LEAD, name=name, phone=phone, email=email)
        contact = {k: v for k, v in (('phone', phone), ('email', email)) if v}
        concept = dict(CONCEPT, gaps=gaps if gaps is not None else CONCEPT['gaps'], contact=contact)
        return agent_video.build_script(lead, concept, {'token': 't', 'views': views}, {'agency': 'Test Studio'})

    def test_only_measured_details_appear_as_facts(self):
        script = self.script()
        facts = [f for beat in script['beats'] for f in beat['facts']]
        self.assertIn('No website listed in the public listing', facts)
        for value in facts:
            self.assertTrue(value in ('No website listed in the public listing', 'Demo City',
                                      'bakery & cafés', 'No charge', 'Nothing published under their name',
                                      'Reply STOP ends contact'), f'invented fact: {value}')

    def test_a_contact_channel_is_described_from_the_record(self):
        self.assertIn('phone number', self.script()['beats'][0]['body'])
        self.assertIn('e-mail address', self.script(phone='', email='hello@example.test')['beats'][0]['body'])
        self.assertIn('nothing of their own', self.script(phone='', email='')['beats'][0]['body'])

    def test_no_gap_is_claimed_when_none_was_measured(self):
        bodies = [beat['body'] for beat in self.script(gaps=[])['beats']]
        self.assertFalse(any('because' in b for b in bodies))

    def test_the_ad_ends_on_the_one_question_with_the_disclaimer(self):
        script = self.script()
        self.assertEqual(script['beats'][-1]['title'], 'Would you like this built?')
        self.assertIn('independent concept', script['end_note'])
        self.assertIn('no reviews, prices, hours or photographs were invented', script['end_note'].lower())

    def test_view_count_is_stated_honestly_when_it_is_zero(self):
        # the full narration carries the count; the 16-second cut leaves it out
        long = lambda views: agent_video.narration(self.script(views=views), short=False)
        self.assertIn('just gone out', long(0))
        self.assertIn('opened 3 times', long(3))
        self.assertIn('opened 1 time so far', long(1))
        self.assertNotIn('opened', agent_video.narration(self.script(views=9)))

    def test_the_name_in_the_script_is_the_saved_name(self):
        script = self.script(name='Riverside Barbers')
        self.assertIn('Riverside Barbers', script['business'])
        self.assertTrue(agent_video.narration(script).startswith('Riverside Barbers.'))

    def test_short_and_long_narration_say_the_same_facts(self):
        script = self.script()
        short, long = agent_video.narration(script), agent_video.narration(script, short=False)
        self.assertLess(len(short), len(long))
        for line in (short, long):
            self.assertIn('Test Bakery', line)
            self.assertIn('Test Studio', line)

    def test_narration_is_written_beside_the_cuts_for_a_human_take(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = agent_video.write_narration(self.script(), tmp)
            self.assertTrue(os.path.exists(path))
            with open(path, encoding='utf-8') as handle:
                self.assertIn('Test Bakery', handle.read())


class AdAvailabilityTests(unittest.TestCase):
    """The crew must be able to say what this machine can and cannot do."""

    def test_availability_names_the_install_command(self):
        state = agent_video.available()
        for key in ('playwright', 'ffmpeg', 'enabled', 'install'):
            self.assertIn(key, state)
        self.assertIn('playwright install chromium', state['install'])

    def test_switched_off_is_reported_not_faked(self):
        with patch.dict(os.environ, {'CREW_VIDEO_RENDER': '0'}):
            self.assertFalse(agent_video.can_render())
            with self.assertRaises(RuntimeError) as caught:
                agent_video.render(CONCEPT, LEAD, {'token': 't'}, {}, tempfile.gettempdir())
            self.assertIn('switched off', str(caught.exception))

    def test_uninstalled_renderer_raises_with_the_exact_install_line(self):
        with patch.object(agent_video, '_playwright', lambda: False):
            with self.assertRaises(RuntimeError) as caught:
                agent_video.render(CONCEPT, LEAD, {'token': 't'}, {}, tempfile.gettempdir())
            self.assertIn('not installed', str(caught.exception))
            self.assertIn('pip install playwright', str(caught.exception))

    def test_status_line_reports_size_and_never_claims_generated_frames(self):
        line = agent_video.status_line({'cuts': {'wide': {'path': 'x.mp4', 'bytes': 2_000_000, 'seconds': 16}},
                                        'took_seconds': 42.0})
        self.assertIn('wide 16s', line)
        self.assertIn('1953 KB', line)
        self.assertIn('no frames were faked', line)
        self.assertEqual(agent_video.status_line({}), 'No cut was produced.')


class AdStageRouteTests(unittest.TestCase):
    """The recording stage is public to the token holder and says what it is."""

    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def link(self):
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,category,city,token,created,updated,phone) "
                      "VALUES('L1','k1','Test Bakery','Bakery','Demo City','tok1',?,?,'+1 555 0100')",
                      (module.now(), module.now()))
        return create_link(module.db, module.now, dict(LEAD, token='tok1'), CONCEPT, 'share')

    def test_the_stage_shows_the_real_concept_and_the_disclaimer(self):
        link = self.link()
        page = self.client.get('/ads/' + link['token'])
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'/r/' + link['token'].encode(), page.data, 'the stage must frame the real page')
        self.assertIn(b'Not the official website of Test Bakery', page.data)
        self.assertIn(b'Independent concept', page.data)
        self.assertEqual(page.headers.get('X-Robots-Tag'), 'noindex, nofollow')

    def test_a_stage_for_an_unknown_token_says_so(self):
        page = self.client.get('/ads/nothing-matches-this')
        self.assertEqual(page.status_code, 404)
        self.assertIn(b'does not exist', page.data)

    def test_the_cut_length_is_bounded(self):
        link = self.link()
        for query, expected in (('?seconds=3', 8), ('?seconds=900', 60)):
            page = self.client.get(f"/ads/{link['token']}{query}")
            self.assertEqual(page.status_code, 200)
            self.assertIn(f'var seconds = Number(qs.get(\'seconds\') || {expected})'.encode(), page.data)

    def test_portrait_cut_asks_for_the_portrait_layout(self):
        link = self.link()
        self.assertIn(b'class="tall"', self.client.get(f"/ads/{link['token']}?fmt=tall").data)
        self.assertIn(b'class="wide"', self.client.get(f"/ads/{link['token']}?fmt=wide").data)


class AdStoryTests(unittest.TestCase):
    """Sample ads may reword the acts — never the facts."""

    STORY = {'problem_body': 'Every order starts in a chat message.',
             'process_body': 'We studied the business and drafted one page.',
             'solution_title': 'The styles, the prices, the booking — one page',
             'solution_body': 'A website that fits the business.',
             'spoken': 'Test Bakery. A long sample line with Test Studio and room to spare.',
             'spoken_short': 'Test Bakery. A short sample line, Test Studio.'}

    def script(self, **kwargs):
        concept = dict(CONCEPT, story=self.STORY)
        return agent_video.build_script(LEAD, concept, {'token': 't', 'views': 0},
                                        {'agency': 'Test Studio'}, **kwargs)

    def test_story_rewords_the_acts(self):
        script = self.script()
        self.assertEqual(script['beats'][0]['body'], self.STORY['problem_body'])
        self.assertEqual(script['beats'][1]['body'], self.STORY['process_body'])
        self.assertEqual(script['beats'][2]['title'], self.STORY['solution_title'])
        self.assertEqual(script['spoken'], self.STORY['spoken'])
        self.assertEqual(agent_video.narration(script), self.STORY['spoken_short'])

    def test_story_never_adds_facts_or_moves_the_ask(self):
        script = self.script()
        facts = [f for beat in script['beats'] for f in beat['facts']]
        for value in facts:
            self.assertTrue(value in ('No website listed in the public listing', 'Demo City',
                                      'bakery & cafés', 'No charge', 'Nothing published under their name',
                                      'Reply STOP ends contact'), f'invented fact: {value}')
        self.assertEqual(script['beats'][-1]['title'], 'Would you like this built?')

    def test_beats_scale_to_the_cut_and_stay_contiguous(self):
        script = self.script(seconds=40)
        beats = script['beats']
        self.assertEqual(len(beats), 4)
        self.assertEqual(beats[0]['at'], 0.6)
        self.assertEqual(beats[-1]['until'], 36.8)
        for first, second in zip(beats, beats[1:]):
            self.assertEqual(first['until'], second['at'])

    def test_default_timing_matches_the_classic_cut(self):
        beats = agent_video.build_script(LEAD, CONCEPT, {'token': 't'}, {})['beats']
        self.assertEqual(beats[-1]['until'], 14.8)


class AdStageActsTests(unittest.TestCase):
    setUp = test_app.ProspectTests.setUp
    tearDown = test_app.ProspectTests.tearDown

    def test_stage_opens_on_the_case_and_closes_on_the_brand(self):
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,category,city,token,created,updated) "
                      "VALUES('L1','k1','Test Bakery','Bakery','Demo City','tok1',?,?)",
                      (module.now(), module.now()))
        link = create_link(module.db, module.now, dict(LEAD, token='tok1'), CONCEPT, 'share')
        body = self.client.get('/ads/' + link['token']).data.decode('utf-8')
        self.assertIn('id="case"', body)
        self.assertIn('Needs a website', body)
        self.assertIn('logo-inverse.svg', body)
        self.assertIn('No charge', body)


if __name__ == '__main__':
    unittest.main()
