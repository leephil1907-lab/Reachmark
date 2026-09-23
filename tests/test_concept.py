"""Concept one-pager: archetype detection, localized copy, showroom template."""
import json
import os

import web.app as module
from tests.test_crew import CrewBase
from web.concept import ARCHETYPES, FIELDS, concept_copy, detect_archetype, build_theme

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


class ThemeTests(CrewBase):
    def test_food_trade_palette_is_not_studio_lime(self):
        theme = build_theme('food', {})
        self.assertEqual(theme['colors']['accent'], '#b3541e')
        self.assertEqual(theme['colors']['bg'], '#faf4e9')
        self.assertIn('hero-oven.jpg', theme['showcase']['hero'])
        self.assertNotIn('#d5f268', ' '.join(v for v in theme['colors'].values()
                                             if isinstance(v, str)))
        self.assertEqual(theme['archetype'], 'food')
        self.assertEqual(theme['widget_key'], 'pc.w_food_t')

    def test_observed_brand_colour_overrides_trade_palette(self):
        theme = build_theme('food', {'theme_color': '#7a2f1b', 'colors': ['#7a2f1b']})
        self.assertEqual(theme['colors']['accent'], '#7a2f1b')
        self.assertEqual(theme['colors']['accent_source'], 'observed on page')
        self.assertTrue(theme['has_brand'])

    def test_white_theme_color_falls_back_to_trade(self):
        theme = build_theme('health', {'theme_color': '#ffffff'})
        self.assertEqual(theme['colors']['accent'], '#63d6c3')

    def test_accent_ink_stays_readable(self):
        light = build_theme('pro', {'colors': ['#f5e9c8']})['colors']['accent_ink']
        dark = build_theme('pro', {'colors': ['#123a5e']})['colors']['accent_ink']
        self.assertEqual(light, '#201405')
        self.assertEqual(dark, '#fff8ef')

    def test_serif_fonts_flip_display_vibe(self):
        theme = build_theme('home', {'fonts': ['Fraunces']})
        self.assertEqual(theme['colors']['vibe'], 'serif')

    def test_unknown_archetype_and_junk_urls_are_safe(self):
        theme = build_theme('nope', {'logo': 'javascript:alert(1)',
                                     'images': [{'url': 'ftp://x/y.png', 'alt': ''}]})
        self.assertEqual(theme['archetype'], 'pro')
        self.assertEqual(theme['logo'], '')
        self.assertEqual(theme['images'], [])


class PreviewBrandTests(CrewBase):
    def _mklead(self, **kw):
        row = {'id': 'pvb1', 'source_key': 'pvb1', 'name': 'Sunrise Bakery',
               'category': 'Bakery', 'city': 'Austin', 'phone': '+1 512 555 0100',
               'email': 'hello@sunrise.test', 'address': '1 Main St',
               'stage': 'New', 'token': 'pvtoken1', 'created': module.now(),
               'updated': module.now()}
        row.update(kw)
        with module.db() as c:
            c.execute('INSERT OR REPLACE INTO leads(id,source_key,name,category,city,phone,email,address,stage,token,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                      tuple(row[k] for k in ('id', 'source_key', 'name', 'category', 'city', 'phone', 'email', 'address', 'stage', 'token', 'created', 'updated')))
        return row

    def _audit_with_brand(self, lead_id, brand):
        from agents.agent_auditor import ensure_tables
        ensure_tables(module.db)
        with module.db() as c:
            c.execute('INSERT INTO site_audits(id,lead_id,url,status,observations,created) VALUES(?,?,?,?,?,?)',
                      ('a1', lead_id, 'https://x.test/', 'HAS_WEBSITE',
                       json.dumps({'ok': True, 'brand': brand}), module.now()))

    def test_preview_wears_observed_brand(self):
        lead = self._mklead()
        self._audit_with_brand(lead['id'], {
            'theme_color': '#7a2f1b', 'colors': ['#7a2f1b'],
            'logo': 'https://cdn.test/logo.png', 'logo_source': 'og:logo',
            'images': [{'url': 'https://cdn.test/hero.jpg', 'alt': 'Fresh loaves'}],
            'fonts': []})
        body = self.client.get('/preview/pvtoken1').data.decode()
        for needle in ('--accent:#7a2f1b', 'https://cdn.test/logo.png',
                       'https://cdn.test/hero.jpg', 'id="gallery"', 'Order ahead',
                       'Plays well with', 'WhatsApp', 'Live demo', 'Get directions',
                       'id="lightbox"', 'id="w-form"', 'vibe-serif'):
            self.assertIn(needle, body)

    def test_preview_without_brand_uses_trade_palette(self):
        self._mklead()
        body = self.client.get('/preview/pvtoken1').data.decode()
        self.assertIn('--accent:#b3541e', body)
        self.assertNotIn('id="gallery"', body)
        self.assertIn('Order ahead', body)
        for needle in ('Fresh from the oven', 'pays for itself',
                       '/static/concept/food/hero-oven.jpg', 'hero-split',
                       'Concept photography', 'Be found first'):
            self.assertIn(needle, body)
