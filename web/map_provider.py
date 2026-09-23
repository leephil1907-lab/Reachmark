"""Serialized, bounded read-only Overpass access. Never retry writes or claim completeness."""
import os, threading, time
from web.i18n import t as _t, locale_now
import requests

# Commercial/high-volume deployments should configure a contracted or self-hosted instance.
ENDPOINTS = [x.strip() for x in os.getenv('OVERPASS_URLS', 'https://overpass.private.coffee/api/interpreter,https://maps.mail.ru/osm/tools/overpass/api/interpreter').split(',') if x.strip()][:2]
_lock = threading.Lock()
_cooldown = {}
_last = 0.0
_rate_until = 0.0

def query_overpass(query, headers):
    global _last, _rate_until
    with _lock:
        if _rate_until > time.monotonic():
            raise ValueError(_t('er_072', locale_now()))
        error = 'Map data providers are temporarily unavailable. Saved progress is retained; retry later.'
        for endpoint in ENDPOINTS:
            if _cooldown.get(endpoint, 0) > time.monotonic():
                continue
            time.sleep(max(0, 2 - (time.monotonic() - _last)))
            try:
                _last = time.monotonic()
                # A bounded request and response; at most one fallback per read-only query.
                with requests.post(endpoint, data={'data': query}, headers=headers, timeout=(8, 50), stream=True) as r:
                    if r.status_code in (429, 406):
                        try: delay = min(3600, max(60, int(r.headers.get('Retry-After', '60'))))
                        except ValueError: delay = 60
                        _cooldown[endpoint] = time.monotonic() + delay
                        _rate_until = _cooldown[endpoint]
                        # Do not route around an explicit rate limit.
                        raise ValueError(_t('er_071', locale_now()))
                    r.raise_for_status()
                    data = bytearray()
                    for chunk in r.iter_content(65536):
                        data.extend(chunk)
                        if len(data) > 8 * 1024 * 1024:
                            raise ValueError(_t('er_073', locale_now()))
                    import json
                    payload = json.loads(data)
                    if not isinstance(payload, dict) or not isinstance(payload.get('elements'), list):
                        raise ValueError(_t('er_056', locale_now()))
                    return payload
            except requests.RequestException:
                _cooldown[endpoint] = time.monotonic() + 60
        raise ValueError(error)
