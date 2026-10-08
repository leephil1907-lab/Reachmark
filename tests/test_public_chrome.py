"""Public chrome: tab pill, hamburger, leak narrative, receptionist facts."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublicChromeTests(unittest.TestCase):
    def test_sample_tab_pill_does_not_stretch_across_wrapped_rows(self):
        css = (ROOT / 'static' / 'xdesign.css').read_text(encoding='utf-8')
        self.assertIn('flex-wrap:nowrap', css)
        self.assertNotIn('height:100%;width:0', css.replace(' ', ''))
        js = (ROOT / 'templates' / 'home.html').read_text(encoding='utf-8')
        self.assertIn('offsetHeight', js)
        self.assertIn('offsetTop', js)

    def test_mobile_menu_is_a_button_aligned_dropdown(self):
        css = (ROOT / 'static' / 'header.css').read_text(encoding='utf-8')
        self.assertIn('.pub-menu{', css)
        block = css.split('.pub-menu{', 1)[1].split('}', 1)[0]
        self.assertIn('position:absolute', block)
        self.assertIn('right:max(12px', block)
        self.assertNotIn('border-top:1px solid rgba(15,20,18,.06);background:rgba(255,255,255,.96);padding:8px 22px 16px', css)

    def test_plan_cards_set_their_own_ink_color(self):
        css = (ROOT / 'static' / 'xdesign.css').read_text(encoding='utf-8')
        self.assertIn('.x-plans-grid article{', css)
        self.assertIn('color:#20251f', css)
        self.assertIn('[data-theme="dark"] .x-plans-grid b{color:#f3f6f1}', css)

    def test_home_audit_renders_the_measured_narrative(self):
        home = (ROOT / 'templates' / 'home.html').read_text(encoding='utf-8')
        self.assertIn('x-audit-story', home)
        self.assertIn('j.narrative', home)

    def test_knowledge_covers_the_live_site(self):
        kb = (ROOT / 'knowledge' / 'reachmark.md').read_text(encoding='utf-8')
        for needle in (
            'https://reachmarkdigital.xyz',
            'support@reachmarkdigital.xyz',
            'https://wa.me/14473227700',
            'Free $0',
            'Starter $19',
            'Pro $59',
            'Digital Opportunity Report',
            'not a revenue forecast',
            'Ernest Micheal',
            'No phone number is published',
        ):
            self.assertIn(needle, kb)


if __name__ == '__main__':
    unittest.main()
