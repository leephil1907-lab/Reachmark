"""Static wiring tests for the Revenue OS workspace command center."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RevenueOSWorkspaceTests(unittest.TestCase):
    def test_workspace_exposes_revenue_os_page_and_assets(self):
        index = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        pages = (ROOT / "templates" / "operations-pages.html").read_text(encoding="utf-8")
        app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-page="revenue-os"', index)
        self.assertIn('/static/revenue-os.css', index)
        self.assertIn('/static/revenue-os.js', index)
        self.assertIn("revenue-os-panel.html", pages)
        self.assertIn('id="page-revenue-os"', (ROOT / "templates" / "revenue-os-panel.html").read_text(encoding="utf-8"))
        self.assertIn("loadRevenueOS", app_js)

    def test_command_center_reads_saved_data_and_never_auto_sends(self):
        js = (ROOT / "static" / "revenue-os.js").read_text(encoding="utf-8")
        panel = (ROOT / "templates" / "revenue-os-panel.html").read_text(encoding="utf-8")
        self.assertIn("'/api/os/command'", js)
        self.assertIn("'/api/os/metrics'", js)
        self.assertIn("'/api/os/lead/'+encodeURIComponent(id)+'/advance'", js)
        self.assertIn("Nothing will be sent", js)
        self.assertIn("does not send an email", panel)
        self.assertIn("does not add unlike currencies", panel)


if __name__ == "__main__":
    unittest.main()
