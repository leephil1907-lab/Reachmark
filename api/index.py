"""Vercel is retired: the live site runs on Railway at https://reachmarkdigital.xyz.

vercel.json turns off Git deployments and redirects every path. This tiny WSGI
app is the fallback for any deployment that still exists: it forwards each
request to the same path on the real site. It deliberately does not import the
Flask app, so no second copy of the site, database or secrets runs here.
"""
from urllib.parse import quote

CANONICAL = 'https://reachmarkdigital.xyz'


def app(environ, start_response):
    path = quote(environ.get('PATH_INFO') or '/', safe="/:@!$&'()*+,;=-._~")
    query = environ.get('QUERY_STRING')
    location = CANONICAL + path + (('?' + query) if query else '')
    start_response('301 Moved Permanently', [('Location', location), ('Content-Type', 'text/plain; charset=utf-8'),
                                             ('Cache-Control', 'public, max-age=86400')])
    return [('Moved to ' + location + '\n').encode()]


handler = app
