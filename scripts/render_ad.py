#!/usr/bin/env python3
"""Render the Brag ad video for one review link — two cuts from one real recording.

    python scripts/render_ad.py --token <review-link-token>
    python scripts/render_ad.py --link-id <id> --formats wide --seconds 15
    python scripts/render_ad.py --token <t> --voice narration.mp3   # mux a voiceover

What it records: the actual concept page at /r/<token>, framed on /ads/<token> and
scrolled by that page's own timeline. Overlays carry only saved facts. If Playwright or
ffmpeg is missing the script says exactly what to install — it never ships a fake video.
"""
import argparse
import base64
import io
import json
import os
import sys
import tarfile
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

DEFAULT_PORT = 8098


def _start_app(port):
    """Boot the app on a port so the renderer has something real to record."""
    os.environ.setdefault('DATABASE_PATH', os.getenv('DATABASE_PATH', os.path.join(ROOT, 'prospect.sqlite3')))
    from werkzeug.serving import make_server, WSGIRequestHandler

    class Quiet(WSGIRequestHandler):
        def log_request(self, *args, **kwargs):
            pass

    import web.app as application
    server = make_server('127.0.0.1', port, application.app, threaded=True, request_handler=Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, application, f'http://127.0.0.1:{port}'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--token', help='review-link token (from /api/review-links or the console)')
    parser.add_argument('--link-id', help='review-link id instead of the token')
    parser.add_argument('--formats', default='wide,tall', help='wide, tall, or both')
    parser.add_argument('--seconds', type=int, default=0, help='override the cut length')
    parser.add_argument('--voice', help='audio file to mux as the voiceover (mp3/wav/m4a)')
    parser.add_argument('--say', action='store_true', help='also write the narration to narration.txt beside the cuts')
    parser.add_argument('--out', default='dist/ads', help='output directory')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--no-server', action='store_true', help='use an app that is already running')
    args = parser.parse_args()

    import agents.agent_video as agent_video
    state = agent_video.available()
    if not agent_video.can_render():
        print(json.dumps({'ok': False, 'available': state,
                          'hint': f'Install with: {state["install"]}'}, indent=2))
        return 2

    from web.review_links import get_link, ensure_tables
    server = None
    base = f'http://127.0.0.1:{args.port}'
    if not args.no_server:
        server, application, base = _start_app(args.port)
        db = application.db
    else:
        import web.app as application
        db = application.db
    try:
        ensure_tables(db)
        link = get_link(db, token=args.token, link_id=args.link_id)
        if not link:
            print(json.dumps({'ok': False, 'error': 'No review link matches that token or id.'}, indent=2))
            return 1
        concept = link.get('concept') or {}
        lead = agent_video.lead_for(db, link) or {'name': 'this business'}
        settings = application.settings()
        formats = [f.strip() for f in args.formats.split(',') if f.strip() in agent_video.FORMATS]
        result = agent_video.render(concept, lead, link, settings, os.path.join(ROOT, args.out),
                                    formats=formats, voice=args.voice, base_url=base,
                                    seconds=args.seconds or None)
        result['script_spoken'] = agent_video.narration(result['script'])
        if args.say:
            result['narration_file'] = agent_video.write_narration(result['script'], os.path.join(ROOT, args.out))
        print(json.dumps(result, indent=2, default=str))
        return 0
    finally:
        if server:
            server.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
