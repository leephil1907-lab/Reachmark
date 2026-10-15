from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_leads_with_interactive_product_preview():
    home = (ROOT / "templates" / "home.html").read_text(encoding="utf-8")
    assert home.index('id="sample-report"') < home.index('id="try-url"')
    assert 'data-rm-preview' in home
    assert 'data-preview-select="clinic"' in home
    assert 'data-preview-select="law"' in home
    assert 'data-preview-select="cafe"' in home
    assert 'id="rm-preview-findings"' in home
    assert 'id="x-audit-form"' in home
    assert '/api/public/audit' in home
    assert 'sample website review' in home.lower()
    assert 'these examples show how a reachmark review is presented' in home.lower()
    assert 'fictional' not in home.lower()
    assert 'not measured' not in home.lower()


def test_preview_interaction_is_accessible_and_does_not_invent_metrics():
    js = (ROOT / "static" / "home-product.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "home-product.css").read_text(encoding="utf-8")
    assert "aria-pressed" in js
    assert "textContent" in js
    assert "Willow Grove Dental" in js
    assert "Northstar Family Law" in js
    assert "Harborlight Café" in js
    assert "score" not in js.lower()
    assert "@media(max-width:760px)" in css
    assert "prefers-reduced-motion:reduce" in css


def test_whatsapp_is_an_inline_secondary_receptionist_handoff():
    widget = (ROOT / "templates" / "receptionist.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "receptionist.css").read_text(encoding="utf-8")
    assert 'class="rm-whatsapp-link"' in widget
    assert '{% if whatsapp_url %}' in widget
    assert 'target="_blank" rel="noopener noreferrer"' in widget
    assert '.rm-whatsapp-link' in css
    assert 'wa-float' not in widget
