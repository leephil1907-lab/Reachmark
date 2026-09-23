"""Brand harvesting: colours, logo, images and fonts observed in page markup.

extract_brand is pure (no network) so every test runs on fixture HTML.
"""
import unittest

from web.brand import extract_brand

FIXTURE = """<!DOCTYPE html><html><head><title>Sunrise Bakery — Fresh Daily</title>
<meta name="theme-color" content="#7a2f1b">
<meta name="description" content="A neighbourhood bakery.">
<meta property="og:site_name" content="Sunrise Bakery">
<meta property="og:image" content="/img/hero.jpg">
<meta property="og:logo" content="https://cdn.test/logo.png">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:wght@600&family=DM+Sans:wght@400;700&display=swap">
<style>.hero{background:#7a2f1b;color:#fff8ef;font-family:'Fraunces',serif}.btn{background:#7a2f1b;border-color:#e8e2d5}</style>
</head><body>
<img src="/img/croissant.jpg" alt="Butter croissants" width="800">
<img src="/img/pixel.png" width="1" alt="">
<img src="https://cdn.test/oven.jpg" alt="Stone oven">
</body></html>"""


class ExtractBrandTests(unittest.TestCase):
    def test_theme_color_and_ranked_colors(self):
        brand = extract_brand(FIXTURE, 'https://sunrise.test/')
        self.assertEqual(brand['theme_color'], '#7a2f1b')
        self.assertEqual(brand['colors'][0], '#7a2f1b')
        # Near-white page colours are not brand colours.
        self.assertNotIn('#fff8ef', brand['colors'])
        self.assertNotIn('#e8e2d5', brand['colors'])

    def test_logo_prefers_declared_logo(self):
        brand = extract_brand(FIXTURE, 'https://sunrise.test/')
        self.assertEqual(brand['logo'], 'https://cdn.test/logo.png')
        self.assertEqual(brand['logo_source'], 'og:logo')

    def test_logo_falls_back_to_logoish_image(self):
        html = '<html><body><img src="/img/acme-logo.svg" alt="Acme logo"></body></html>'
        brand = extract_brand(html, 'https://acme.test/shop')
        self.assertEqual(brand['logo'], 'https://acme.test/img/acme-logo.svg')
        self.assertIn('logo', brand['logo_source'])

    def test_images_absolutized_social_first_pixel_skipped(self):
        brand = extract_brand(FIXTURE, 'https://sunrise.test/')
        urls = [img['url'] for img in brand['images']]
        self.assertEqual(urls[0], 'https://sunrise.test/img/hero.jpg')
        self.assertIn('https://sunrise.test/img/croissant.jpg', urls)
        self.assertIn('https://cdn.test/oven.jpg', urls)
        self.assertNotIn('https://sunrise.test/img/pixel.png', urls)
        self.assertLessEqual(len(urls), 6)

    def test_fonts_from_hosted_css(self):
        brand = extract_brand(FIXTURE, 'https://sunrise.test/')
        self.assertIn('Fraunces', brand['fonts'])
        self.assertIn('DM Sans', brand['fonts'])

    def test_meta_facts(self):
        brand = extract_brand(FIXTURE, 'https://sunrise.test/')
        self.assertEqual(brand['site_name'], 'Sunrise Bakery')
        self.assertIn('Sunrise Bakery', brand['title'])
        self.assertIn('neighbourhood bakery', brand['description'])

    def test_data_and_foreign_schemes_dropped(self):
        html = ('<html><head><meta property="og:image" content="data:image/png;base64,xx">'
                '<meta property="og:logo" content="ftp://x.test/l.png"></head>'
                '<body><img src="javascript:alert(1)" alt="x"></body></html>')
        brand = extract_brand(html, 'https://x.test/')
        self.assertEqual(brand['logo'], '')
        self.assertEqual(brand['images'], [])

    def test_empty_and_junk_never_crash(self):
        for html, base in (('', ''), ('not html at all', 'notaurl'),
                           ('<html><img><meta><link><style>#{', 'https://x.test/')):
            brand = extract_brand(html, base)
            self.assertEqual(brand['colors'], [])
            self.assertEqual(brand['logo'], '')
            self.assertEqual(brand['images'], [])
