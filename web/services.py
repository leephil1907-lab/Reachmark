"""Live public-data discovery and bounded, SSRF-resistant website checks."""
import ipaddress, socket, re, threading, time
from web.i18n import t as _t, locale_now
from functools import lru_cache
from urllib.parse import urlparse, urljoin
import requests, urllib3

SOCIAL = ('facebook.com','instagram.com','linktr.ee','linktree.com','fb.com','business.site')
geo_lock=threading.Lock()
last_geo=0.0
HEADERS={'User-Agent':'Reachmark/1.0 (interactive public business directory research)'}
def classify(url):
    if not url.strip(): return 'NOT_LISTED'
    try: host=(urlparse(url if '://' in url else 'https://'+url).hostname or '').lower()
    except ValueError: return 'HAS_WEBSITE'
    return 'SOCIAL_ONLY' if any(host==s or host.endswith('.'+s) for s in SOCIAL) else 'HAS_WEBSITE'

@lru_cache(maxsize=128)
def geocode(location):
    global last_geo
    with geo_lock:
        delay=1.1-(time.monotonic()-last_geo)
        if delay>0: time.sleep(delay)
        last_geo=time.monotonic()
        r=requests.get('https://nominatim.openstreetmap.org/search',params={'q':location,'format':'json','limit':1},headers=HEADERS,timeout=20)
        r.raise_for_status(); places=r.json()
    if not places: raise ValueError(_t('er_067', locale_now()))
    return places[0]

def _row_from_osm_tags(location, osm_type, osm_id, tags, lat, lon):
    tags = tags or {}
    name = (tags.get('name') or '').strip()
    if not name:
        return None
    return {
        'source_key': f'osm:{osm_type}:{osm_id}',
        'name': name,
        'city': location,
        'address': ', '.join(filter(None, [
            ' '.join(filter(None, [tags.get('addr:housenumber'), tags.get('addr:street')])),
            tags.get('addr:city'), tags.get('addr:state'), tags.get('addr:postcode'), tags.get('addr:country'),
        ])),
        'phone': tags.get('phone') or tags.get('contact:phone', ''),
        'email': tags.get('email') or tags.get('contact:email', ''),
        'website': tags.get('website') or tags.get('contact:website', ''),
        'source': 'OpenStreetMap',
        'source_url': f'https://www.openstreetmap.org/{osm_type}/{osm_id}',
        'latitude': lat,
        'longitude': lon,
        'opening_hours': tags.get('opening_hours', ''),
        'social_url': tags.get('contact:facebook') or tags.get('contact:instagram', ''),
        'source_tags': tags,
    }


def _discover_nominatim(location, tag, limit=25):
    """Same OpenStreetMap data via Nominatim when Overpass mirrors are down."""
    _key, value = tag
    q = f'{str(value).replace("_", " ")} in {location}'
    global last_geo
    with geo_lock:
        delay = 1.1 - (time.monotonic() - last_geo)
        if delay > 0:
            time.sleep(delay)
        last_geo = time.monotonic()
        r = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': q, 'format': 'json', 'limit': int(limit), 'addressdetails': 1, 'extratags': 1},
            headers=HEADERS, timeout=20,
        )
        r.raise_for_status()
        places = r.json()
    if not isinstance(places, list) or not places:
        raise ValueError(_t('er_096', locale_now()))
    rows = []
    for place in places:
        if place.get('class') in ('place', 'boundary', 'highway'):
            continue
        osm_type = {'node': 'node', 'way': 'way', 'relation': 'relation'}.get(place.get('osm_type'))
        osm_id = place.get('osm_id')
        if not osm_type or not osm_id:
            continue
        extra = dict(place.get('extratags') or {})
        addr = place.get('address') or {}
        name = (place.get('name') or extra.get('name') or (place.get('display_name') or '').split(',')[0]).strip()
        extra.setdefault('name', name)
        if addr.get('city') and 'addr:city' not in extra:
            extra['addr:city'] = addr.get('city') or addr.get('town') or addr.get('suburb') or ''
        if addr.get('road') and 'addr:street' not in extra:
            extra['addr:street'] = addr.get('road')
        row = _row_from_osm_tags(location, osm_type, osm_id, extra, place.get('lat'), place.get('lon'))
        if row:
            rows.append(row)
    if not rows:
        raise ValueError(_t('er_096', locale_now()))
    return rows, location


def discover_location(location, tag, limit=80):
    place = geocode(location)
    lat, lon = float(place['lat']), float(place['lon'])
    key, value = tag
    q = f'[out:json][timeout:40];nwr(around:15000,{lat},{lon})["{key}"="{value}"]["name"];out center tags {int(limit)};'
    from web.map_provider import query_overpass
    try:
        payload = query_overpass(q, HEADERS)
        if payload.get('remark'):
            raise ValueError(_t('er_115', locale_now()))
        rows = []
        for item in payload.get('elements', []):
            tags = item.get('tags', {})
            center = item.get('center', item)
            row = _row_from_osm_tags(location, item['type'], item['id'], tags, center.get('lat'), center.get('lon'))
            if row:
                rows.append(row)
        return rows, place.get('display_name', location)
    except (ValueError, requests.RequestException):
        return _discover_nominatim(location, tag, min(int(limit), 25))

def audit_website(url):
    if classify(url)!='HAS_WEBSITE': return {'status':classify(url),'reason':'Source listing has no standalone website URL. Verify independently.','http_code':None}
    current=url if '://' in url else 'https://'+url
    try:
        for redirect in range(5):
            if classify(current)=='SOCIAL_ONLY': return {'status':'SOCIAL_ONLY','reason':'Website URL redirects to a social-profile host.','http_code':None}
            p=urlparse(current)
            if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or (p.port and p.port not in (80,443)):
                return {'status':'CHECK_FAILED','reason':'Only public HTTP/HTTPS URLs on standard ports can be checked.','http_code':None}
            host=p.hostname.encode('idna').decode(); port=p.port or (443 if p.scheme=='https' else 80)
            infos=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
            ips=list(dict.fromkeys(info[4][0] for info in infos))
            if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
                return {'status':'CHECK_FAILED','reason':'Private, reserved, or mixed public/private destination blocked.','http_code':None}
            # Connect to the validated IP (not a second DNS lookup). TLS still verifies the real hostname.
            cls=urllib3.HTTPSConnectionPool if p.scheme=='https' else urllib3.HTTPConnectionPool
            kwargs={'server_hostname':host,'assert_hostname':host,'cert_reqs':'CERT_REQUIRED'} if p.scheme=='https' else {}
            pool=cls(ips[0],port=port,timeout=urllib3.Timeout(connect=5,read=7),retries=False,**kwargs)
            response=None
            try:
                target=(p.path or '/')+('?' +p.query if p.query else '')
                response=pool.urlopen('GET',target,headers={**HEADERS,'Host':host,'Accept':'text/html','Accept-Encoding':'identity'},redirect=False,preload_content=False)
                code=response.status
                if code in (301,302,303,307,308) and response.headers.get('Location'):
                    current=urljoin(current,response.headers['Location']);continue
                raw=response.read(65536,decode_content=False).decode('utf-8','replace').lower()
                if code in (401,403,429): status,reason='BLOCKED','Access restricted or rate-limited; this is not evidence of a dead website.'
                elif code>=500: status,reason='HTTP_ERROR',f'HTTP {code}: server error observed. Retry later before making a claim.'
                elif code>=400: status,reason='HTTP_ERROR',f'HTTP {code}: listed page is unavailable. The business may use another URL.'
                elif any(x in raw for x in ('this domain is for sale','buy this domain','domain has expired','website is parked')): status,reason='PARKED_SUSPECTED','Parking or domain-sale wording detected. Manual verification required.'
                elif code<300: status,reason='LIVE','The URL responded successfully. This does not assess design quality, forms, or business ownership.'
                else: status,reason='CHECK_FAILED',f'Unexpected HTTP {code}; review manually.'
                return {'status':status,'reason':reason,'http_code':code,'final_url':current}
            finally:
                if response: response.close()
                pool.close()
        return {'status':'CHECK_FAILED','reason':'Redirect limit reached.','http_code':None}
    except socket.gaierror:
        return {'status':'DNS_UNRESOLVED','reason':'DNS did not resolve during this check. Possible dead domain or temporary DNS failure; verify again.','http_code':None}
    except (urllib3.exceptions.HTTPError,TimeoutError,OSError,ValueError,UnicodeError):
        return {'status':'UNREACHABLE','reason':'Connection, TLS, or timeout failure. Not proof the website is dead.','http_code':None}
