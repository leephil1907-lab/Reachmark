"""Static/runtime mobile + PWA audit used before a production release."""
import json
from pathlib import Path
from web.app import app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
MANIFEST = STATIC / "manifest.webmanifest"

def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    required = ["name","short_name","description","start_url","scope","display","theme_color","background_color","icons"]
    missing = [k for k in required if not manifest.get(k)]
    assert not missing, f"manifest missing: {missing}"
    assert manifest["display"] in {"standalone","fullscreen","minimal-ui"}, manifest["display"]
    assert any(i.get("purpose") == "maskable" for i in manifest["icons"]), "maskable icon missing"

    for entry in manifest["icons"] + manifest.get("screenshots", []):
        src = entry["src"]
        path = STATIC / src.removeprefix("/static/")
        assert path.is_file(), f"missing PWA asset: {src}"

    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    for private in ["/workspace","/dashboard","/api/state","/api/leads","/api/projects","/api/invoices","/api/map/"]:
        assert private in sw, f"service worker deny-list missing {private}"

    client = app.test_client()
    for path in ["/","/about","/showcase","/enquire","/receptionist"]:
        r = client.get(path)
        assert r.status_code == 200, (path, r.status_code)
        body = r.get_data(as_text=True)
        assert 'name="viewport"' in body or "name='viewport'" in body, f"viewport missing: {path}"
        assert "/static/manifest.webmanifest" in body, f"manifest link missing: {path}"
        assert "/static/pwa.js" in body, f"PWA registration missing: {path}"

    r = client.get("/static/manifest.webmanifest")
    assert r.status_code == 200 and r.mimetype == "application/manifest+json"
    r = client.get("/static/sw.js")
    assert r.status_code == 200 and r.headers.get("Service-Worker-Allowed") == "/"
    print("PASS: mobile viewport, manifest assets, maskable icon, service-worker privacy deny-list, public PWA registration.")

if __name__ == "__main__":
    main()
