#!/usr/bin/env python3
"""Regenerate the PWA assets that a perfect installability score needs.

Two things cannot be hand-written and are produced here:

1. **Maskable icon** — Android crops home-screen icons to whatever shape the launcher
   uses, so a maskable icon must keep every important pixel inside a centred 80% circle.
   The existing ``icon-512.png`` (a rounded square) would be clipped; this script paints a
   full-bleed lime canvas and puts the untouched ``icon.svg`` glyph inside the safe zone.
   The original icons are *never* modified.

2. **Manifest screenshots** — Chrome and the install prompt show them, and a manifest
   without them is judged incomplete. They are real captures of this app (public pages
   only — never the private workspace), taken with the same headless Chromium the browser
   tests use.

Usage:
    python scripts/pwa_assets.py                # both assets
    python scripts/pwa_assets.py --icons-only   # no browser needed
"""
import argparse
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, 'static')
SHOTS = os.path.join(STATIC, 'screenshots')
BRAND_LIME = (213, 242, 104)          # #d5f268
BRAND_CHARCOAL = (32, 37, 31)         # #20251f

# Declared size must equal the file's real pixels: a manifest that lies about an icon or
# screenshot size is exactly what installability checks flag.
SHOT_JOBS = [
    # (name, url path, viewport, device scale)
    ('home-narrow', '/', (390, 844), 1),
    ('home-wide', '/', (1280, 800), 1),
    ('showcase-wide', '/showcase', (1280, 800), 1),
    ('about-narrow', '/about', (390, 844), 1),
]


def _mark_only_svg():
    """The icon's mark (the forward R and its dot) without its own rounded lime tile.

    Kept as a string edit of the shipped file so the icon art itself is never redrawn by
    hand: remove the background <rect> and its corner radius, keep everything else.
    """
    import re
    with open(os.path.join(STATIC, 'icon.svg'), encoding='utf-8') as handle:
        svg = handle.read()
    return re.sub(r'<rect[^>]*/>', '', svg, count=1)


def glyph_png(size=512):
    """Rasterise the icon's mark at `size` px through headless Chromium, transparent."""
    from playwright.sync_api import sync_playwright
    import tempfile
    handle, path = tempfile.mkstemp(suffix='.svg')
    with os.fdopen(handle, 'w', encoding='utf-8') as fh:
        fh.write(_mark_only_svg())
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': size, 'height': size}, device_scale_factor=1)
        page.goto('file://' + path, wait_until='load')
        page.wait_for_timeout(250)
        data = page.screenshot(omit_background=True, clip={'x': 0, 'y': 0, 'width': size, 'height': size})
        browser.close()
    os.unlink(path)
    return data


def build_maskable(size=512, safe_ratio=0.62):
    """Full-bleed brand square with the glyph inside the maskable safe zone."""
    from PIL import Image
    canvas = Image.new('RGBA', (size, size), BRAND_LIME + (255,))
    glyph = Image.open(io.BytesIO(glyph_png(size))).convert('RGBA')
    # The SVG is a rounded lime tile: crop away its own background, keep the charcoal mark.
    bbox = glyph.getbbox()
    if bbox:
        glyph = glyph.crop(bbox)
    inner = int(size * safe_ratio)
    glyph.thumbnail((inner, inner), Image.LANCZOS)
    canvas.alpha_composite(glyph, ((size - glyph.width) // 2, (size - glyph.height) // 2))
    out = os.path.join(STATIC, f'icon-maskable-{size}.png')
    canvas.save(out, 'PNG', optimize=True)
    return out, canvas


def build_apple_touch(size=180):
    """iOS ignores the manifest icon: give Safari its own full-bleed tile."""
    from PIL import Image
    canvas = Image.new('RGBA', (size, size), BRAND_LIME + (255,))
    glyph = Image.open(io.BytesIO(glyph_png(size))).convert('RGBA')
    glyph.thumbnail((int(size * 0.72), int(size * 0.72)), Image.LANCZOS)
    bg = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    bg.alpha_composite(glyph, ((size - glyph.width) // 2, (size - glyph.height) // 2))
    canvas.alpha_composite(bg)
    out = os.path.join(STATIC, f'apple-touch-icon-{size}.png')
    canvas.save(out, 'PNG', optimize=True)
    return out, canvas


def build_screenshots():
    from playwright.sync_api import sync_playwright
    os.makedirs(SHOTS, exist_ok=True)
    sys.path.insert(0, ROOT)
    made = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, path, (width, height), scale in SHOT_JOBS:
            context = browser.new_context(viewport={'width': width, 'height': height},
                                          device_scale_factor=scale, reduced_motion='reduce')
            page = context.new_page()
            # No third-party requests: the capture must be reproducible offline.
            page.route('**/*', lambda route: route.abort()
                       if not route.request.url.startswith(('http://127.0.0.1', 'http://localhost'))
                       else route.continue_())
            page.goto(f'http://127.0.0.1:{PORT}{path}', wait_until='domcontentloaded', timeout=20000)
            page.wait_for_timeout(1500)
            out = os.path.join(SHOTS, f'{name}.png')
            page.screenshot(path=out)
            made.append((out, width, height))
            context.close()
        browser.close()
    return made


PORT = int(os.environ.get("PWA_SHOT_PORT", "8099"))
_server = None


def start_app():
    """The captures need the real app; start it on a scratch database."""
    global _server
    import tempfile, threading
    from pathlib import Path
    tmp = tempfile.mkdtemp(prefix='pwa-shots-')
    os.environ['DATABASE_PATH'] = str(Path(tmp) / 'pwa.sqlite3')
    os.environ.pop('DASHBOARD_PASSWORD', None)
    os.environ['PORT'] = str(PORT)
    sys.path.insert(0, ROOT)
    from werkzeug.serving import make_server, WSGIRequestHandler

    class Quiet(WSGIRequestHandler):
        def log_request(self, *args, **kwargs):
            pass

    import web.app as application
    _server = make_server('127.0.0.1', PORT, application.app, threaded=True, request_handler=Quiet)
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    return tmp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--icons-only', action='store_true', help='skip the browser captures')
    args = parser.parse_args()

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print('Pillow is required: pip install pillow', file=sys.stderr)
        return 1

    try:
        maskable, canvas = build_maskable(512)
        print(f'✓ {os.path.relpath(maskable, ROOT)}  {canvas.width}×{canvas.height} maskable (safe zone 62%)')
        apple, canvas = build_apple_touch(180)
        print(f'✓ {os.path.relpath(apple, ROOT)}  {canvas.width}×{canvas.height} apple-touch')
    except Exception as exc:
        print(f'✗ icons skipped: {type(exc).__name__}: {exc} — pip install playwright && python -m playwright install chromium', file=sys.stderr)
        if args.icons_only:
            return 1

    if args.icons_only:
        return 0

    tmp = start_app()
    try:
        for path, width, height in build_screenshots():
            print(f'✓ {os.path.relpath(path, ROOT)}  {width}×{height}')
    except Exception as exc:
        print(f'✗ screenshots skipped: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    finally:
        if _server:
            _server.shutdown()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
