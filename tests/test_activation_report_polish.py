from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_first_run_onboarding_explains_the_four_action_path():
    page = (ROOT / "templates" / "onboard.html").read_text(encoding="utf-8")
    for text in ("Discover", "Review", "Build a report", "Approve outreach", "Find businesses"):
        assert text in page
    assert "before anything is sent" in page
    assert "aria-label=\"Your first workflow\"" in page


def test_sample_report_is_clearly_presented_without_alarmist_copy():
    page = (ROOT / "templates" / "opportunity-report.html").read_text(encoding="utf-8").lower()
    assert "sample report" in page
    assert "recommended next steps" in page
    assert "fictional" not in page
    assert "not a live audit" not in page


def test_sample_report_payload_uses_a_professional_context_note():
    source = (ROOT / "web" / "opportunity.py").read_text(encoding="utf-8").lower()
    assert "sample report showing how reachmark organises findings and recommendations" in source
    assert "fictional example" not in source
