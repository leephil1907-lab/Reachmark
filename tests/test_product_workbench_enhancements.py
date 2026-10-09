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


if __name__ == "__main__":
    unittest.main()
