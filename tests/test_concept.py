"""Concept one-pager: archetype detection, localized copy, showroom template."""
import json
import os

import web.app as module
from tests.test_crew import CrewBase
from web.concept import ARCHETYPES, FIELDS, concept_copy, detect_archetype

LOCALES = ('en', 'es', 'fr', 'de', 'pt', 'zh')


def locale_data(code):
    base = os.path.join(os.path.dirname(module.__file__), '..', 'static', 'locales')
    with open(os.path.join(base, f'{code}.json'), encoding='utf-8') as f:
        return json.load(f)


class ArchetypeTests(CrewBase):
    def test_categories_map_to_archetypes(self):
        cases = {'Bakery': 'food', 'Restaurant': 'food', 'Hair salon': 'beauty',
                 'Tattoo studio': 'beauty', 'Dentist': 'health', 'Gym': 'health',
                 'Plumber': 'home', 'Car wash': 'home', 'Hotel': 'stay',
                 'Clothing shop': 'stay', 'Lawyer': 'pro', 'Accountant': 'pro',
                 '': 'pro', None: 'pro', 'Quantum widgetry': 'pro'}
        for cat, want in cases.items():
            self.assertEqual(detect_archetype(cat), want, cat)

    def test_all_archetypes_covered_in_all_locales(self):
        archs = list(ARCHETYPES) + ['pro']
        for code in LOCALES:
            data = locale_data(code)
            for arch in archs:
                for field in FIELDS:
                    key = f'cc.{arch}_{field}'
                    self.assertIn(key, data, f'{key} missing in {code}')
                    self.assertTrue(data[key].strip(), f'{key} empty in {code}')

    def test_copy_splits_offers_into_title_and_desc(self):
        for code in LOCALES:
            for arch in list(ARCHETYPES) + ['pro']:
                copy = concept_copy(arch, code)
                self.assertTrue(copy['tag'].strip())
                self.assertTrue(copy['about'].strip())
                self.assertEqual(len(copy['offers']), 3)
                for offer in copy['offers']:
                    self.assertTrue(offer['t'].strip(), f'{arch}/{code} offer title')
                    self.assertTrue(offer['d'].strip(), f'{arch}/{code} offer desc')

    def test_unknown_archetype_falls_back_to_pro(self):
        copy = concept_copy('nope', 'en')
        self.assertEqual(copy['archetype'], 'pro')


class PreviewPageTests(CrewBase):
    def _mklead(self, **kw):
        row = {'id': 'pv1', 'source_key': 'pv1', 'name': 'Sunrise Bakery',
               'category': 'Bakery', 'city': 'Austin', 'phone': '+1 512 555 0100',
               'email': 'hello@sunrise.test', 'address': '1 Main St',
               'stage': 'New', 'token': 'pvtoken1', 'created': module.now(),
               'updated': module.now()}
        row.update(kw)
        with module.db() as c:
            c.execute('INSERT OR REPLACE INTO leads(id,source_key,name,category,city,phone,email,address,stage,token,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                      tuple(row[k] for k in ('id', 'source_key', 'name', 'category', 'city', 'phone', 'email', 'address', 'stage', 'token', 'created', 'updated')))
        return row

    def test_preview_renders_showroom(self):
        self._mklead()
        r = self.client.get('/preview/pvtoken1')
        self.assertEqual(r.status_code, 200)
        body = r.data.decode()
        for needle in ('Sunrise Bakery', 'Austin', 'Signature menu', 'tel:+15125550100',
                       'https://wa.me/15125550100', 'mailto:hello@sunrise.test',
                       'INDEPENDENT WEBSITE CONCEPT', 'id="stars"', 'data-count="100"',
                       'sticky-cta', 'prefers-reduced-motion', 'noindex,nofollow'):
            self.assertIn(needle, body)
        self.assertNotIn('cc.food_o1', body)

    def test_preview_without_contact_falls_back_to_cta(self):
        self._mklead(id='pv2', source_key='pv2', token='pvtoken2', phone='', email='')
        body = self.client.get('/preview/pvtoken2').data.decode()
        self.assertNotIn('wa.me', body)
        self.assertIn('#contact', body)

    def test_preview_is_not_indexed(self):
        self._mklead()
        r = self.client.get('/preview/pvtoken1')
        self.assertIn('noindex', r.headers.get('X-Robots-Tag', ''))

    def test_unknown_token_404s(self):
        self.assertEqual(self.client.get('/preview/does-not-exist').status_code, 404)
