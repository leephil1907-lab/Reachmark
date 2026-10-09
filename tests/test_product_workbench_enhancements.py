"""Regression guards for the interactive homepage report explorer."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProductWorkbenchEnhancementTests(unittest.TestCase):
    def test_home_loads_report_explorer_assets(self):
        home = (ROOT / "templates" / "home.html").read_text(encoding="utf-8")
        self.assertIn("/static/product-workbench.css", home)
        self.assertIn("/static/product-workbench.js", home)

    def test_report_examples_are_explicitly_illustrative(self):
        script = (ROOT / "static" / "product-workbench.js").read_text(encoding="utf-8")
        self.assertIn("Illustrative examples", script)
        self.assertIn("not client results", script)
        self.assertIn("Observed signal", script)
        self.assertIn("Recommended next step", script)

    def test_ranked_opportunities_use_server_order_without_fake_scores(self):
        script = (ROOT / "static" / "product-workbench.js").read_text(encoding="utf-8")
        self.assertIn("slice(0, 3)", script)
        self.assertIn("measured gap weights", script)
        self.assertIn("No invented score or revenue estimate", script)
        self.assertNotIn("score = 99", script.lower())

    def test_receptionist_has_product_aware_quick_prompts(self):
        widget = (ROOT / "templates" / "receptionist.html").read_text(encoding="utf-8")
        script = (ROOT / "static" / "receptionist.js").read_text(encoding="utf-8")
        self.assertIn("What does Reachmark do?", widget)
        self.assertIn("How much does a website cost?", widget)
        self.assertIn("What are the steps and timing?", widget)
        self.assertIn("Can I talk to a person?", widget)
        self.assertIn("requestSubmit()", script)

    def test_homepage_uses_receptionist_instead_of_competing_whatsapp_float(self):
        home = (ROOT / "templates" / "home.html").read_text(encoding="utf-8")
        header = (ROOT / "templates" / "header-public.html").read_text(encoding="utf-8")
        widget = (ROOT / "templates" / "receptionist.html").read_text(encoding="utf-8")
        self.assertIn("{% include 'receptionist.html' %}", home)
        self.assertNotIn("_whatsapp.html", header)
        self.assertIn("rm-whatsapp-secondary", widget)
        self.assertIn("{{ whatsapp_url }}", widget)


if __name__ == "__main__":
    unittest.main()
