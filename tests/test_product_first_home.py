"""Guardrails for Reachmark's product-first public homepage."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProductFirstHomeTests(unittest.TestCase):
    def test_home_has_a_single_real_public_audit_form(self):
        home = (ROOT / "templates" / "home.html").read_text(encoding="utf-8")
        self.assertEqual(home.count('id="x-audit-form"'), 1)
        self.assertEqual(home.count('id="x-audit-url"'), 1)
        self.assertEqual(home.count('id="x-audit-out"'), 1)
        self.assertIn("fetch('/api/public/audit'", home)
        self.assertIn('href="/sample-report"', home)
        self.assertIn('href="/signup"', home)

    def test_home_loads_product_first_styles_and_has_no_old_separate_audit_section(self):
        home = (ROOT / "templates" / "home.html").read_text(encoding="utf-8")
        css = (ROOT / "static" / "product-home.css").read_text(encoding="utf-8")
        self.assertIn('/static/product-home.css', home)
        self.assertIn('class="ph-workbench"', home)
        self.assertIn('class="ph-product-card"', home)
        self.assertNotIn('id="try-url"', home)
        self.assertIn("@media(max-width:560px)", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("--rm-heading:'Manrope'", css)
        self.assertIn("--rm-body:'DM Sans'", css)
        self.assertIn("--rm-editorial:'Instrument Serif'", css)

    def test_reachmark_wordmark_is_a_boxed_r_completed_by_eachmark(self):
        home = (ROOT / "templates" / "home.html").read_text(encoding="utf-8")
        css = (ROOT / "static" / "product-home.css").read_text(encoding="utf-8")
        self.assertIn('class="ph-brand-mark" aria-hidden="true">R</span><span class="ph-brand-rest">eachmark</span>', home)
        self.assertIn(".ph-brand-mark", css)
        self.assertIn(".ph-brand-rest", css)

    def test_check_copy_does_not_overstate_findings(self):
        home = (ROOT / "templates" / "home.html").read_text(encoding="utf-8")
        css = (ROOT / "static" / "product-home.css").read_text(encoding="utf-8")
        self.assertIn("A check is not a revenue forecast", home)
        self.assertIn("inconclusive", home)
        self.assertIn("Measured observations. Not a revenue forecast.", home)


if __name__ == "__main__":
    unittest.main()
