from pathlib import Path

from web.opportunity import compose_sales_asset

ROOT = Path(__file__).resolve().parents[1]


def test_report_asset_keeps_evidence_detail_and_recommended_fix():
    lead = {"name": "Example Clinic", "website": "https://example.test"}
    report = {
        "leaks": [{
            "id": "no_form_or_booking",
            "title": "No booking path found",
            "leak": "No booking link was found in the page we read.",
            "reason": "The fetched homepage contained no form or booking link.",
            "fix": "Add a visible appointment booking link.",
            "source": "homepage HTML",
            "commercial": True,
        }],
        "solution": {"name": "Booking path", "why": "Make the next step clear."},
        "evidence": {"checked_at": "2026-10-25T01:00:00Z"},
    }

    asset = compose_sales_asset(lead, report)
    finding = asset["evidence"][0]

    assert finding["reason"] == "The fetched homepage contained no form or booking link."
    assert finding["fix"] == "Add a visible appointment booking link."
    assert finding["source"] == "homepage HTML"


def test_public_report_labels_evidence_and_recommendations_separately():
    template = (ROOT / "templates" / "opportunity-report.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "opportunity.css").read_text(encoding="utf-8")

    assert "Evidence detail" in template
    assert "Recommended fix" in template
    assert "oe-evidence" in css
    assert "oe-fix" in css
