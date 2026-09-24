"""Business-specific website generator: profile, brandmark, copy, theme, facts."""
from tests.test_crew import CrewBase
from web.sitegen import (BANNED, DIGIT_RE, _validate_copy, brandmark_svg,
                         build_site, business_profile, generate_copy)


class ProfileTests(CrewBase):
    def test_profile_reads_saved_fields_and_audit(self):
        lead = {'id': 'L1', 'name': 'Sunrise Bakery', 'category': 'Bakery',
                'city': 'Austin', 'address': '1 Main St', 'phone': '+1 512 555 0100',
                'email': 'hello@sunrise.test', 'opening_hours': 'Mo-Fr 07:00-15:00',
                'website': 'https://sunrise.test'}
        audit = {'status': 'LIVE', 'observations': {
            'brand': {'title': 'Sunrise Bakery — Austin', 'description': 'Fresh bread daily.',
                      'colors': ['#b3541e']},
            'signals': {'title': 'Sunrise Bakery', 'meta_description': 'Fresh bread daily.'}}}
        p = business_profile(lead, audit)
        self.assertEqual(p['name'], 'Sunrise Bakery')
        self.assertEqual(p['city'], 'Austin')
        self.assertEqual(p['audit_status'], 'LIVE')
        self.assertEqual(p['site_description'], 'Fresh bread daily.')
        self.assertEqual(p['brand']['colors'], ['#b3541e'])

    def test_profile_is_empty_safe(self):
        p = business_profile(None, None)
        self.assertEqual(p['name'], '')
        self.assertEqual(p['brand'], {})
        self.assertEqual(p['signals'], {})


class BrandmarkTests(CrewBase):
    def test_brandmark_is_a_valid_svg_with_initials(self):
        svg = brandmark_svg('Sunrise Bakery', '#b3541e')
        self.assertIn('<svg', svg)
        self.assertIn('</svg>', svg)
        self.assertIn('>SB<', svg)
        self.assertIn('#b3541e', svg)

    def test_brandmark_single_word_and_bad_colour(self):
        svg = brandmark_svg('Bakery', 'not-a-colour')
        self.assertIn('>BA<', svg)
        self.assertIn('#20251F', svg)  # falls back to the studio charcoal


class CopyTests(CrewBase):
    def test_deterministic_copy_names_the_business(self):
        p = business_profile({'name': 'Sunrise Bakery', 'category': 'Bakery',
                              'city': 'Austin'})
        copy = generate_copy(p, 'food', 'en', use_llm=False)
        self.assertEqual(copy['headline'], 'Sunrise Bakery')
        self.assertFalse(copy['generated'])
        self.assertEqual(len(copy['offers']), 3)
        self.assertTrue(copy['about'])

    def test_validate_rejects_banned_words_and_digits(self):
        p = business_profile({'name': 'Sunrise Bakery', 'category': 'Bakery'})
        good = '{"tag":"Fresh bread","about":"We bake daily.","offers":[{"t":"Bread","d":"Baked here."},{"t":"Cakes","d":"Made to order."},{"t":"Coffee","d":"Served hot."}]}'
        self.assertIsNotNone(_validate_copy(good, p, 'food', 'en'))
        bad_word = good.replace('Fresh bread', 'Award-winning bread')
        self.assertIsNone(_validate_copy(bad_word, p, 'food', 'en'))
        bad_digit = good.replace('We bake daily.', 'We bake 7 days a week.')
        self.assertIsNone(_validate_copy(bad_digit, p, 'food', 'en'))
        self.assertIsNone(_validate_copy('not json at all', p, 'food', 'en'))

    def test_banned_list_and_digit_regex(self):
        self.assertIn('award-winning', BANNED)
        self.assertTrue(DIGIT_RE.search('open 24 hours'))
        self.assertFalse(DIGIT_RE.search('open every day'))


class BuildSiteTests(CrewBase):
    def test_build_site_for_a_bakery(self):
        lead = {'id': 'L1', 'name': 'Sunrise Bakery', 'category': 'Bakery',
                'city': 'Austin', 'phone': '+1 512 555 0100'}
        site = build_site(lead, None, locale='en', use_llm=False)
        self.assertEqual(site['archetype'], 'food')
        self.assertEqual(site['theme']['colors']['accent'], '#b3541e')
        self.assertEqual(site['copy']['headline'], 'Sunrise Bakery')
        self.assertTrue(site['brandmark_generated'])
        self.assertIn('<svg', site['brandmark'])
        self.assertTrue(any('Austin' in f for f in site['facts']))
        self.assertTrue(any('+1 512 555 0100' in f for f in site['facts']))

    def test_build_site_uses_harvested_logo_when_present(self):
        lead = {'id': 'L2', 'name': 'Clinic Co', 'category': 'Dentist'}
        audit = {'observations': {'brand': {'logo': 'https://cdn.test/logo.png',
                                            'colors': ['#2a9d8f']}}}
        site = build_site(lead, audit, locale='en', use_llm=False)
        self.assertEqual(site['archetype'], 'health')
        self.assertEqual(site['theme']['logo'], 'https://cdn.test/logo.png')
        self.assertFalse(site['brandmark_generated'])
        self.assertEqual(site['brandmark'], '')

    def test_build_site_never_raises_on_empty_lead(self):
        site = build_site({}, None, locale='en', use_llm=False)
        self.assertIn('theme', site)
        self.assertIn('copy', site)
        self.assertEqual(site['archetype'], 'pro')
