"""Live public-data discovery and bounded, SSRF-resistant website checks."""
import ipaddress, socket, re, threading, time
from functools import lru_cache
from urllib.parse import urlparse, urljoin
import requests, urllib3

SOCIAL = ('facebook.com','instagram.com','linktr.ee','linktree.com','fb.com','business.site')
geo_lock=threading.Lock()
last_geo=0.0
HEADERS={'User-Agent':'SiteGapReveal/1.0 (interactive public business directory research)'}
def classify(url):
    if not url.strip(): return 'NOT_LISTED'
    host=(urlparse(url if '://' in url else 'https://'+url).hostname or '').lower()
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
    if not places: raise ValueError('Location not found. Include city and country.')
    return places[0]

def discover_location(location, tag, limit=80):
    place=geocode(location)
    lat,lon=float(place['lat']),float(place['lon']); key,value=tag
    q=f'[out:json][timeout:40];nwr(around:15000,{lat},{lon})["{key}"="{value}"]["name"];out center tags {int(limit)};'
    r=requests.post('https://overpass-api.de/api/interpreter',data={'data':q},headers=HEADERS,timeout=55);r.raise_for_status()
    rows=[]
    for item in r.json().get('elements',[]):
        t=item.get('tags',{}); center=item.get('center',item)
        rows.append({'source_key':f"osm:{item['type']}:{item['id']}",'name':t['name'],'city':location,'address':', '.join(filter(None,[' '.join(filter(None,[t.get('addr:housenumber'),t.get('addr:street')])),t.get('addr:city'),t.get('addr:state'),t.get('addr:postcode'),t.get('addr:country')])),'phone':t.get('phone') or t.get('contact:phone',''),'email':t.get('email') or t.get('contact:email',''),'website':t.get('website') or t.get('contact:website',''),'source':'OpenStreetMap','source_url':f"https://www.openstreetmap.org/{item['type']}/{item['id']}",'latitude':center.get('lat'),'longitude':center.get('lon'),'opening_hours':t.get('opening_hours',''),'social_url':t.get('contact:facebook') or t.get('contact:instagram',''),'source_tags':t})
    return rows, place.get('display_name',location)

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
