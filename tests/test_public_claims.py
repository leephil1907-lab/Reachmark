from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_showcase_contains_no_unverified_social_proof():
    page = (ROOT / "templates" / "showcase.html").read_text(encoding="utf-8")
    forbidden = (
        "4.8/5",
        "127 reviews",
        "Sarah M.",
        "David K.",
        "proven by clients",
        "We closed 2 clinic websites",
        "Trustpilot",
    )
    for phrase in forbidden:
        assert phrase not in page


def test_showcase_keeps_concepts_explicitly_labeled():
    page = (ROOT / "templates" / "showcase.html").read_text(encoding="utf-8")
    assert "REACHMARK CONCEPT GALLERY" in page
    assert "Original design directions created to demonstrate what Reachmark can build." in page


def test_sample_sites_are_described_as_concepts_not_client_work():
    page = (ROOT / "templates" / "sample-site.html").read_text(encoding="utf-8")
    assert "fictional" in page.lower()


def test_home_leads_with_the_report_not_designer_praise():
    home = (ROOT / "templates" / "home.html").read_text(encoding="utf-8")
    app = (ROOT / "web" / "app.py").read_text(encoding="utf-8")
    home_fn = app.split("def home():", 1)[1].split("def workspace():", 1)[0]
    assert "World-class website designer" not in home_fn
    assert "8 premium" not in home_fn
    assert "no Google API" not in home_fn
    assert "Find Businesses Losing Customers Online" in home_fn
    assert "Digital Opportunity Report" in home_fn
    assert 'id="sample-report"' in home
    assert "adsense" not in home.lower()
    assert 'href="/sample-report"' in home
    assert 'x-who-design' not in home
    assert home.count('class="x-btn lime"') >= 1
    hero = home.split('<section class="x-hero">', 1)[1].split('</section>', 1)[0]
    assert hero.count('x-btn') == 1
    assert 'Get the app' not in hero
    assert 'Open Reachmark' not in hero
    assert 'id="plans-preview"' in home
    assert 'ws-leads.png' in home
    assert home.find("sample-report") < home.find("x-pipe")
    assert home.find("x-pipe") < home.find("x-concepts")
    assert home.find("x-concepts") < home.find("x-cta")
    assert home.find("x-shots") < home.find("x-concepts")


def test_reviews_page_does_not_invent_ratings():
    page = (ROOT / "templates" / "reviews.html").read_text(encoding="utf-8")
    assert "4.8/5" not in page
    assert "Trustpilot" not in page
    assert "rev.empty" in page


def test_sample_and_sending_pages_exist():
    assert (ROOT / "templates" / "sending.html").exists()
    opp = (ROOT / "web" / "opportunity.py").read_text(encoding="utf-8")
    assert "def fictional_sample_report" in opp
    assert "/sample-report" in opp
