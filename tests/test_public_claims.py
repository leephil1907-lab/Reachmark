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
