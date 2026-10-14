"""Guards against workspace JS writing to elements that no longer exist.

app.js render() runs top-to-bottom; one `$('#gone').innerHTML=` throws and
silently skips everything after it (lead directory, settings, category lists).
That happened when #outreach-list was removed from the template.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITE = re.compile(r"""\$\(\s*['"]#([\w-]+)['"]\s*\)\.(?:innerHTML|textContent|value|className)\s*=""")


def _template_ids():
    ids = set()
    for f in (ROOT / 'templates').glob('*.html'):
        ids |= set(re.findall(r'id="([\w-]+)"', f.read_text(encoding='utf-8')))
    return ids


def test_app_js_unguarded_writes_target_existing_elements():
    src = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
    ids = _template_ids() | set(re.findall(r'id=\\?["\']([\w-]+)', src))
    missing = sorted({m.group(1) for m in WRITE.finditer(src)} - ids)
    assert not missing, f'app.js writes to ids missing from templates: {missing}'
