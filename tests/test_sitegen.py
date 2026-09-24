"""Business-specific website generator: profile, brandmark, copy, theme, facts."""
from tests.test_crew import CrewBase
from web.sitegen import (BANNED, DIGIT_RE, _validate_copy, brandmark_svg,
                         build_site, business_profile, generate_copy, parse_hours)


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


class HoursTests(CrewBase):
    def test_parses_a_weekday_range(self):
        rows = parse_hours('Mo-Fr 07:00-15:00')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['day'], 'Monday \u2013 Friday')
        self.assertEqual(rows[0]['time'], '07:00 \u2013 15:00')

    def test_parses_multiple_groups(self):
        rows = parse_hours('Mo,Tu,We 09:00-17:00; Sa 10:00-14:00')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['day'], 'Monday \u2013 Wednesday')
        self.assertEqual(rows[1]['day'], 'Saturday')

    def test_parses_twenty_four_seven(self):
        rows = parse_hours('24/7')
        self.assertEqual(rows, [{'day': 'Every day', 'time': 'Open 24 hours'}])

    def test_unparseable_hours_return_empty(self):
        self.assertEqual(parse_hours('by appointment'), [])
        self.assertEqual(parse_hours(''), [])


class MapTests(CrewBase):
    def test_map_uses_coordinates_when_present(self):
        site = build_site({'name': 'Cafe', 'category': 'Cafe', 'latitude': 38.71,
                           'longitude': -9.14, 'address': 'Rua do Ouro 1'}, None,
                          locale='en', use_llm=False)
        self.assertIsNotNone(site['map'])
        self.assertIn('openstreetmap.org', site['map']['embed'])
        self.assertIn('38.71', site['map']['embed'])
        self.assertEqual(site['map']['source'], 'OpenStreetMap')

    def test_map_falls_back_to_address_search(self):
        site = build_site({'name': 'Cafe', 'category': 'Cafe', 'address': '1 Main St, Austin'},
                          None, locale='en', use_llm=False)
        self.assertIsNotNone(site['map'])
        self.assertIn('google.com/maps', site['map']['embed'])
        self.assertEqual(site['map']['source'], 'Google Maps')

    def test_map_is_none_without_location(self):
        site = build_site({'name': 'Cafe', 'category': 'Cafe'}, None, locale='en', use_llm=False)
        self.assertIsNone(site['map'])


class ReviewsTests(CrewBase):
    def test_reviews_use_real_rating_and_place_id(self):
        site = build_site({'name': 'Cafe', 'category': 'Cafe', 'rating': 4.6,
                           'review_count': 128, 'place_id': 'ChIJabc'}, None,
                          locale='en', use_llm=False)
        rev = site['reviews']
        self.assertEqual(rev['rating'], 4.6)
        self.assertEqual(rev['count'], 128)
        self.assertEqual(rev['stars'], 5)
        self.assertIn('placeid=ChIJabc', rev['review_url'])

    def test_reviews_offer_a_leave_link_without_a_rating(self):
        site = build_site({'name': 'Cafe', 'category': 'Cafe', 'city': 'Austin'}, None,
                          locale='en', use_llm=False)
        self.assertIsNotNone(site['reviews'])
        self.assertIsNone(site['reviews']['rating'])
        self.assertIn('google.com/maps', site['reviews']['review_url'])

    def test_reviews_none_without_name_or_rating(self):
        site = build_site({'category': 'Cafe'}, None, locale='en', use_llm=False)
        self.assertIsNone(site['reviews'])


class FaqTests(CrewBase):
    def test_faq_always_has_contact_and_get_started(self):
        site = build_site({'name': 'Cafe', 'category': 'Cafe'}, None, locale='en', use_llm=False)
        self.assertGreaterEqual(len(site['faq']), 2)
        self.assertTrue(all(item['q'] and item['a'] for item in site['faq']))

    def test_faq_adds_location_and_hours_when_known(self):
        site = build_site({'name': 'Cafe', 'category': 'Cafe', 'city': 'Austin',
                           'opening_hours': 'Mo-Fr 07:00-15:00'}, None, locale='en', use_llm=False)
        self.assertEqual(len(site['faq']), 4)

    def test_faq_is_localized(self):
        site = build_site({'name': 'Cafe', 'category': 'Cafe'}, None, locale='es', use_llm=False)
        en = build_site({'name': 'Cafe', 'category': 'Cafe'}, None, locale='en', use_llm=False)
        self.assertNotEqual(site['faq'][0]['q'], en['faq'][0]['q'])


class JsonLdTests(CrewBase):
    def test_jsonld_is_localbusiness_with_saved_fields(self):
        site = build_site({'name': 'Sunrise Bakery', 'category': 'Bakery', 'city': 'Austin',
                           'address': '1 Main St', 'phone': '+1 512 555 0100',
                           'email': 'hi@sunrise.test', 'website': 'https://sunrise.test',
                           'latitude': 30.27, 'longitude': -97.74, 'rating': 4.8,
                           'review_count': 64, 'opening_hours': 'Mo-Fr 07:00-15:00'},
                          None, locale='en', use_llm=False)
        ld = site['jsonld']
        self.assertEqual(ld['@type'], 'LocalBusiness')
        self.assertEqual(ld['name'], 'Sunrise Bakery')
        self.assertEqual(ld['telephone'], '+1 512 555 0100')
        self.assertEqual(ld['address']['addressLocality'], 'Austin')
        self.assertEqual(ld['geo']['latitude'], 30.27)
        self.assertEqual(ld['aggregateRating']['ratingValue'], 4.8)

    def test_jsonld_omits_absent_fields(self):
        site = build_site({'name': 'Bare'}, None, locale='en', use_llm=False)
        ld = site['jsonld']
        self.assertNotIn('telephone', ld)
        self.assertNotIn('aggregateRating', ld)
        self.assertNotIn('geo', ld)
