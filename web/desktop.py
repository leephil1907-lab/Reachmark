"""Launch Reachmark as a local application.

Same Flask app as the browser. Opens the workspace in your default browser
so operators can run it on a laptop without a public host.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    port = int(os.getenv('PORT', '8000'))
    host = os.getenv('DESKTOP_HOST', '127.0.0.1')
    path = '/workspace'
    if '--public' in argv:
        path = '/'
    os.environ.setdefault('APP_ENV', os.getenv('APP_ENV', 'development'))
    from web.app import app

    def serve():
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    url = f'http://{host}:{port}{path}'
    for _ in range(40):
        time.sleep(0.15)
        try:
            import urllib.request
            urllib.request.urlopen(url.replace(path, '/healthz'), timeout=1)
            break
        except Exception:
            continue
    webbrowser.open(url)
    print(f'Reachmark is running at {url}  — close this window to stop.')
    try:
        thread.join()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
