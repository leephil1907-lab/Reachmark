"""Design-set checks: counters, reveals, skeletons, heatmap, tour, magnets, sort, stars.

Every component is verified by its hook in the rendered page or its file on disk.
Ratings are verified end to end: form field, API, database column, crew overview.
"""
import json
import os
import re
import unittest

from tests.test_crew import CrewBase
from tests.test_app import module
from web.review_links import create_link, ensure_tables, link_overview

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def static(name):
    with open(os.path.join(ROOT, 'static', name), encoding='utf-8') as handle:
        return handle.read()


class NewFilesTests(unittest.TestCase):
    FILES = ('countup.js', 'reveal.js', 'reveal.css', 'skeleton.css',
             'heatmap.js', 'tour.js', 'tour.css', 'magnet.js')

    def test_all_component_files_exist_and_are_nontrivial(self):
        for name in self.FILES:
            body = static(name)
            self.assertGreater(len(body), 200, name)

    def test_components_respect_reduced_motion(self):
        for name in ('countup.js', 'reveal.js', 'reveal.css', 'skeleton.css', 'magnet.js'):
            self.assertIn('prefers-reduced-motion', static(name), name)

    def test_counters_and_heatmap_expose_their_entry_points(self):
        self.assertIn('window.setCount', static('countup.js'))
        self.assertIn('window.renderHeatmap', static('heatmap.js'))
        self.assertIn('startTour', static('tour.js'))


class WorkspaceHooksTests(CrewBase):
    def test_overview_counters_heatmap_tour_and_skeletons(self):
        page = self.client.get('/workspace')
        self.assertEqual(page.status_code, 200)
        body = page.data.decode('utf-8')
        self.assertEqual(body.count('data-countup'), 8, 'every metric animates')
        self.assertIn('id="activity-heatmap"', body)
        self.assertIn('id="tour-btn"', body)
        self.assertIn('/static/tour.js', body)
        self.assertIn('/static/countup.js', body)
        self.assertIn('/static/heatmap.js', body)
        self.assertIn('/static/skeleton.css', body)
        self.assertIn('/static/tour.css', body)
        self.assertGreaterEqual(body.count('class="sk"'), 4, 'skeleton placeholders')
        self.assertIn("renderHeatmap", body)

    def test_directory_columns_are_sortable(self):
        body = self.client.get('/workspace').data.decode('utf-8')
        for key in ('name', 'city', 'status', 'stage', 'contact'):
            self.assertIn(f"sortLeads('{key}')", body)
            self.assertIn(f'id="sort-{key}"', body)
        app_js = static('app.js')
        self.assertIn('function sortLeads', app_js)
        self.assertIn('leadSort', app_js)

    def test_stat_setters_use_the_animated_counter(self):
        app_js = static('app.js')
        for stat in ('stat-total', 'stat-opportunity', 'stat-sent', 'stat-replied'):
            self.assertIn(f"setC('{stat}'", app_js)
        ops_js = static('operations.js')
        for stat in ('metric-enquiries', 'metric-contracts', 'metric-runs', 'metric-views'):
            self.assertIn(f"setC('{stat}'", ops_js)
        self.assertIn('renderHeatmap', ops_js)


class PublicHooksTests(CrewBase):
    def test_receptionist_page_reveals_aurora_and_magnets(self):
        body = self.client.get('/receptionist').data.decode('utf-8')
        self.assertEqual(body.count('data-reveal'), 8)
        self.assertIn('rx-aurora', body)
        self.assertGreaterEqual(body.count('data-magnet'), 4)
        self.assertIn('/static/reveal.js', body)
        self.assertIn('/static/magnet.js', body)
        self.assertIn('/static/reveal.css', body)

    def test_enquire_and_showcase_buttons_are_magnetic(self):
        enquire = self.client.get('/enquire').data.decode('utf-8')
        self.assertIn('/static/magnet.js', enquire)
        self.assertIn('data-magnet', enquire)
        showcase = self.client.get('/showcase').data.decode('utf-8')
        self.assertIn('/static/magnet.js', showcase)
        self.assertIn('data-magnet', showcase)

    def test_review_page_reveals_aurora_magnets_and_stars(self):
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,category,city,token,created,updated) "
                      "VALUES('LD','kd','Design Cafe','Cafe','Demo','tokd',?,?)",
                      (module.now(), module.now()))
        lead = {'id': 'LD', 'name': 'Design Cafe', 'category': 'Cafe', 'city': 'Demo'}
        link = create_link(module.db, module.now, lead,
                           {'theme': 'ember', 'headline': 'Hello', 'intro': 'x',
                            'sections': [{'title': 'a', 'body': 'b'}]}, 'share')
        body = self.client.get('/r/' + link['token']).data.decode('utf-8')
        self.assertGreaterEqual(body.count('data-reveal'), 4)
        self.assertIn('<section data-reveal class="hero">', body)
        self.assertIn('<section data-reveal class="block answer" id="answer">', body)
        self.assertIn('review-aurora', body)
        self.assertIn('data-magnet', body)
        self.assertIn('class="stars-field"', body)
        self.assertIn('name="rating"', body)
        self.assertIn('/static/reveal.js', body)

    def test_about_page_references_no_new_assets(self):
        body = self.client.get('/about').data.decode('utf-8')
        for asset in ('reveal.js', 'magnet.js', 'tour.js', 'countup.js', 'heatmap.js',
                      'reveal.css', 'tour.css', 'skeleton.css', 'stars-field'):
            self.assertNotIn(asset, body, f'about must stay untouched by the design set: {asset}')


class StaticTagsResolveTests(unittest.TestCase):
    TEMPLATES = ('index.html', 'analytics-overview.html', 'receptionist-page.html',
                 'review.html', 'enquire.html', 'enquiry-form.html', 'showcase.html')

    def test_every_referenced_static_file_exists(self):
        missing = []
        for template in self.TEMPLATES:
            with open(os.path.join(ROOT, 'templates', template), encoding='utf-8') as handle:
                body = handle.read()
            for asset in set(re.findall(r'/static/([A-Za-z0-9_.-]+\.(?:js|css))', body)):
                if not os.path.isfile(os.path.join(ROOT, 'static', asset)):
                    missing.append(f'{template} -> {asset}')
        self.assertEqual(missing, [])


class RatingTests(CrewBase):
    CONCEPT = {'theme': 'ember', 'headline': 'Hello', 'intro': 'x',
               'sections': [{'title': 'a', 'body': 'b'}]}

    def _link(self, lid):
        with module.db() as c:
            c.execute("INSERT INTO leads(id,source_key,name,category,city,token,created,updated) "
                      "VALUES(?,?,?,?,?,?,?,?)",
                      (lid, 'k' + lid, 'Rated ' + lid, 'Cafe', 'Demo', 'tok' + lid,
                       module.now(), module.now()))
        lead = {'id': lid, 'name': 'Rated ' + lid, 'category': 'Cafe', 'city': 'Demo'}
        return create_link(module.db, module.now, lead, self.CONCEPT, 'share')

    def test_rating_roundtrip_to_overview(self):
        link = self._link('R1')
        response = self.client.post(f"/api/r/{link['token']}/respond",
                                    json={'choice': 'want', 'rating': 5})
        self.assertEqual(response.status_code, 201)
        with module.db() as c:
            row = dict(c.execute('SELECT rating FROM review_responses').fetchone())
        self.assertEqual(row['rating'], 5)
        overview = link_overview(module.db)
        self.assertEqual(overview['links'][0]['last_rating'], 5)

    def test_out_of_range_and_missing_ratings_stay_null(self):
        bad = self._link('R2')
        response = self.client.post(f"/api/r/{bad['token']}/respond",
                                    json={'choice': 'later', 'rating': 9})
        self.assertEqual(response.status_code, 201)
        plain = self._link('R3')
        response = self.client.post(f"/api/r/{plain['token']}/respond",
                                    json={'choice': 'later'})
        self.assertEqual(response.status_code, 201)
        with module.db() as c:
            rows = [dict(row) for row in
                    c.execute('SELECT link_id, rating FROM review_responses ORDER BY created')]
        by_link = {row['link_id']: row['rating'] for row in rows}
        self.assertIsNone(by_link[bad['id']])
        self.assertIsNone(by_link[plain['id']])
        self.assertIsNone(json.loads(json.dumps({'v': by_link[plain['id']]}))['v'])

    def test_old_database_without_rating_column_is_migrated(self):
        with module.db() as c:
            c.execute('DROP TABLE review_responses')
            c.execute('CREATE TABLE review_responses(id TEXT PRIMARY KEY, link_id TEXT, '
                      'lead_id TEXT, choice TEXT, note TEXT, name TEXT, email TEXT, '
                      'fingerprint TEXT, handled INTEGER DEFAULT 0, created TEXT)')
        ensure_tables(module.db)
        with module.db() as c:
            columns = {row[1] for row in c.execute('PRAGMA table_info(review_responses)')}
        self.assertIn('rating', columns)
