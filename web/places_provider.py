"""Google Places discovery — key-gated, bounded, and honest.

This is the *second* map source the Scout can read. OpenStreetMap stays the
default because it needs no key and no billing. When the owner sets
``GOOGLE_PLACES_API_KEY`` the Scout can additionally query Google's Places API
(New) Text Search, which covers the business profiles registered on Google Maps
that OSM often misses.

Design rules, matching the rest of the crew:

* **Key-gated.** No key -> :func:`available` is ``False`` and nothing is called.
* **Bounded.** One request per (location, category), capped result count, a
  hard timeout, and a small in-process cooldown so a runaway loop cannot hammer
  the API.
* **Evidence-first.** Every row carries ``source='Google Maps'`` and a
  ``source_url`` pointing at the real Google Maps place, so the owner can check
  it. Nothing is invented; missing fields stay empty.
* **Never fatal.** Any error returns ``[]`` and a reason string; the Scout then
  falls back to OpenStreetMap.
"""

import os
import threading
import time

import requests

# Google Places API (New) — Text Search endpoint.
ENDPOINT = 'https://places.googleapis.com/v1/places:searchText'
# Only the fields we actually store. Field masks keep the response (and cost) small.
FIELD_MASK = ','.join([
    'places.id',
    'places.displayName',
    'places.formattedAddress',
    'places.internationalPhoneNumber',
    'places.websiteUri',
    'places.location',
    'places.primaryTypeDisplayName',
    'places.googleMapsUri',
    'places.regularOpeningHours.weekdayDescriptions',
    'places.rating',
    'places.userRatingCount',
])

_lock = threading.Lock()
_last_call = 0.0
MIN_INTERVAL = 1.0  # seconds between calls, process-wide


def api_key():
    """The configured Google Places key, or ``''`` when unset."""
    return (os.getenv('GOOGLE_PLACES_API_KEY') or '').strip()


def available():
    """True only when a key is configured. The Scout checks this before calling."""
    return bool(api_key())


def _cooldown():
    global _last_call
    with _lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _hours(place):
    """Flatten Google's weekday descriptions into one readable string."""
    try:
        days = place['regularOpeningHours']['weekdayDescriptions']
    except (KeyError, TypeError):
        return ''
    return '; '.join(str(d) for d in days if d)[:400]


def _row(place, location):
    """Map one Google place onto the crew's lead shape. Missing fields stay empty."""
    name = ((place.get('displayName') or {}).get('text') or '').strip()
    if not name:
        return None
    loc = place.get('location') or {}
    pid = place.get('id') or ''
    return {
        'source_key': f'google:{pid}' if pid else '',
        'name': name,
        'city': location,
        'address': (place.get('formattedAddress') or '').strip(),
        'phone': (place.get('internationalPhoneNumber') or '').strip(),
        'email': '',  # Google Places does not expose e-mail; the Scout reads the site for it.
        'website': (place.get('websiteUri') or '').strip(),
        'source': 'Google Maps',
        'source_url': (place.get('googleMapsUri') or (f'https://www.google.com/maps/place/?q=place_id:{pid}' if pid else '')),
        'latitude': loc.get('latitude'),
        'longitude': loc.get('longitude'),
        'opening_hours': _hours(place),
        'rating': place.get('rating'),
        'review_count': place.get('userRatingCount'),
        'place_id': pid,
        'social_url': '',
        'source_tags': {
            'google_place_id': pid,
            'primary_type': ((place.get('primaryTypeDisplayName') or {}).get('text') or ''),
        },
    }


def discover_places(location, category, limit=20, timeout=20):
    """Query Google Places Text Search for ``category`` in ``location``.

    Returns ``(rows, reason)``. ``rows`` is a list of lead dicts (possibly empty);
    ``reason`` is a short human string explaining an empty result, or ``''`` on
    success. Never raises.
    """
    key = api_key()
    if not key:
        return [], 'Google Places is not configured (set GOOGLE_PLACES_API_KEY).'
    if not (location or '').strip():
        return [], 'A location is required for a Google Places search.'

    query = f'{category} in {location}'.strip() if category else location.strip()
    body = {'textQuery': query, 'maxResultCount': max(1, min(int(limit or 20), 20))}
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': key,
        'X-Goog-FieldMask': FIELD_MASK,
    }
    _cooldown()
    try:
        r = requests.post(ENDPOINT, json=body, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        return [], f'Google Places request failed ({type(exc).__name__}).'
    if r.status_code in (401, 403):
        return [], 'Google Places rejected the key (401/403). Check the key and that the Places API is enabled.'
    if r.status_code == 429:
        return [], 'Google Places rate limit reached (429). Retry later.'
    if r.status_code >= 400:
        return [], f'Google Places returned HTTP {r.status_code}.'
    try:
        payload = r.json()
    except ValueError:
        return [], 'Google Places returned a non-JSON response.'
    places = payload.get('places') or []
    rows = [row for row in (_row(p, location) for p in places) if row]
    if not rows:
        return [], 'Google Places returned no named listings for that search.'
    return rows, ''


def merge_rows(*sources):
    """Merge lead rows from several sources, de-duplicating by name+city.

    Earlier sources win on conflict, but empty fields are filled from later
    duplicates so a Google row can complete an OSM row (and vice-versa). Rows
    without a name are dropped.
    """
    merged, index = [], {}
    for rows in sources:
        for row in rows or []:
            name = (row.get('name') or '').strip()
            if not name:
                continue
            key = (name.lower(), (row.get('city') or '').strip().lower())
            if key not in index:
                index[key] = len(merged)
                merged.append(dict(row))
                continue
            target = merged[index[key]]
            for field, value in row.items():
                if not value:
                    continue
                current = target.get(field)
                if isinstance(current, str):
                    if not current.strip():
                        target[field] = value
                elif not current:
                    target[field] = value
    return merged
