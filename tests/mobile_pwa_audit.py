"""Static/runtime mobile + PWA audit used before a production release."""
import json
from pathlib import Path
from web.app import app
ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/"static"
MANIFEST=STATIC/"manifest.webmanifest"
def main():
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    required=["name","short_name","description","start_url","scope","display","theme_color","background_color","icons"]
    assert not [k for k in required if not manifest.get(k)]
    assert manifest["display"] in {"standalone","fullscreen","minimal-ui"}
    assert any(i.get("purpose")=="maskable" for i in manifest["icons"])
    for entry in manifest["icons"]+manifest.get("screenshots",[]):
        src=entry["src"]; assert (STATIC/src.removeprefix("/static/")).is_file(),src
    sw=(STATIC/"sw.js").read_text(encoding="utf-8").replace("\\/","/")
    for private in ["/workspace","/dashboard","/api/state","/api/leads","/api/projects","/api/invoices","/api/map/"]:
        assert private.rstrip("/") in sw,private
    client=app.test_client()
    for path in ["/","/about","/showcase","/enquire","/receptionist"]:
        r=client.get(path); assert r.status_code==200,(path,r.status_code)
        body=r.get_data(as_text=True); assert "name=\"viewport\"" in body or "name='viewport'" in body
    assert client.get("/static/manifest.webmanifest").status_code==200
    assert client.get("/static/sw.js").headers.get("Service-Worker-Allowed")=="/"
if __name__=="__main__": main()
