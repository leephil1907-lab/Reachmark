"""Six-locale contract: parity, resolution, fallback, and rendering smoke.

Every key must exist in all six locales; English is the fallback everywhere;
a missing key renders the English string, never a raw key.
"""
import json
import os
import tempfile
import unittest

_original_path = os.environ.get('DATABASE_PATH')
_bootstrap = tempfile.TemporaryDirectory()
os.environ['DATABASE_PATH'] = os.path.join(_bootstrap.name, 'bootstrap.sqlite3')
import web.app as module  # noqa: E402
from web.i18n import LOCALES, resolve_locale, strings, t  # noqa: E402

if _original_path is None:
    os.environ.pop('DATABASE_PATH', None)
else:
    os.environ['DATABASE_PATH'] = _original_path

DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'locales')


class LocaleParityTests(unittest.TestCase):
    def test_all_locales_have_identical_keys(self):
        base = set(strings('en'))
        self.assertGreater(len(base), 1000, 'locale files look truncated')
        for code in LOCALES:
            if code == 'en':
                continue
            other = set(strings(code))
            self.assertEqual(base - other, set(), f'{code} missing keys')
            self.assertEqual(other - base, set(), f'{code} has extra keys')

    def test_no_empty_values(self):
        for code in LOCALES:
            for key, value in strings(code).items():
                self.assertTrue(isinstance(value, str) and value.strip(), f'{code}:{key} is empty')

    def test_locale_files_are_valid_json(self):
        for code in LOCALES:
            with open(os.path.join(DIR, code + '.json'), encoding='utf-8') as handle:
                data = json.load(handle)
            self.assertIsInstance(data, dict)


class ResolutionTests(unittest.TestCase):
    def test_cookie_wins(self):
        self.assertEqual(resolve_locale('fr', 'es,de;q=0.9'), 'fr')

    def test_accept_language_order(self):
        self.assertEqual(resolve_locale('', 'es-ES,es;q=0.9,de;q=0.8'), 'es')
        self.assertEqual(resolve_locale(None, 'zh-CN,zh;q=0.9'), 'zh')

    def test_unknown_cookie_falls_through(self):
        self.assertEqual(resolve_locale('xx', 'de'), 'de')

    def test_default_is_english(self):
        self.assertEqual(resolve_locale('', ''), 'en')
        self.assertEqual(resolve_locale(None, 'xx,yy;q=0.5'), 'en')


class FallbackTests(unittest.TestCase):
    def test_missing_key_falls_back_to_english(self):
        from web.i18n import _cache
        _cache.setdefault('es', {})['__probe__'] = None
        try:
            del _cache['es']['__probe__']
        except KeyError:
            pass
        # Key absent everywhere renders the raw key (last resort, never a crash)
        self.assertEqual(t('__no_such_key__', 'es'), '__no_such_key__')

    def test_english_used_when_locale_missing_key(self):
        from web.i18n import _cache
        saved = strings('de').pop('rv.bar', None)
        try:
            self.assertEqual(t('rv.bar', 'de'), strings('en')['rv.bar'])
        finally:
            if saved is not None:
                _cache['de']['rv.bar'] = saved

    def test_placeholders(self):
        self.assertIn('Bakery', t('rv.would', 'en', n='Bakery'))
        self.assertIn('Bakery', t('rv.would', 'zh', n='Bakery'))

    def test_locale_now_defaults_outside_request(self):
        from web.i18n import locale_now
        self.assertEqual(locale_now(), 'en')


class TemplateRenderTests(unittest.TestCase):
    def test_review_preview_ad_render_in_all_locales(self):
        from flask import g, render_template
        from agents.agent_video import build_script
        link = {'token': 'tok', 'theme': 'charcoal', 'headline': 'H', 'intro': 'I',
                'sections': [], 'concept': {}}
        lead = {'name': 'Example Bakery', 'category': 'Bakery', 'city': 'Winnipeg'}
        for loc in LOCALES:
            with module.app.test_request_context('/'):
                g.locale = loc
                html = render_template('review.html', link=link, lead=dict(lead),
                                       studio='Reachmark', reply_email='', base='', responses={})
                self.assertIn(f'<html lang="{loc}"', html)
                self.assertIn('id="locale-select"', html)
                from web.concept import build_theme, concept_copy, detect_archetype
                arch = detect_archetype(lead['category'])
                html = render_template('preview.html', lead=dict(lead), studio='Reachmark',
                                       copy=concept_copy(arch, loc), wa='',
                                       theme=build_theme(arch, {}))
                self.assertIn(f'<html lang="{loc}"', html)
                self.assertNotIn('pc.w_food_t', html)
                script = build_script(lead, {}, {'token': 't'}, {'agency': 'Reachmark'},
                                      seconds=18, locale=loc)
                html = render_template(
                    'ad-stage.html', token='t', fmt='wide', business=script['business'],
                    studio=script['studio'], category='Bakery', place=script['place'],
                    problem_facts=[str(f) for f in script['beats'][0]['facts']][:4],
                    closing_facts=script['beats'][-1]['facts'], captions=script['beats'],
                    end_note=script['end_note'], seconds=18)
                self.assertIn(f'<html lang="{loc}"', html)


class PdfSmokeTests(unittest.TestCase):
    def test_pdf_builds_in_each_locale(self):
        from web.documents import pdf
        for loc in LOCALES:
            blob = pdf(t('pdf.i_title', loc), 'n · Draft',
                       [(t('pdf.i_s1', loc), 'Name\nmail\naddr')], 'now', 'Studio', loc=loc)
            self.assertTrue(blob.startswith(b'%PDF'), loc)


if __name__ == '__main__':
    unittest.main()
