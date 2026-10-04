    only as a bounded fallback if the new pipeline is unavailable.
    """
    try:
        from web.global_discovery import discover
        category = {
            ('shop','car_repair'):'auto', ('shop','hairdresser'):'beauty', ('shop','bakery'):'bakery', ('shop','florist'):'florist',
            ('tourism','hotel'):'hotel', ('tourism','guest_house'):'hotel', ('leisure','fitness_centre'):'gym',
            ('shop','laundry'):'laundry', ('shop','dry_cleaning'):'laundry', ('shop','convenience'):'convenience',
            ('shop','supermarket'):'supermarket',
            ('amenity','restaurant'):'restaurant', ('amenity','cafe'):'restaurant',
            ('amenity','pharmacy'):'pharmacy', ('shop','clothes'):'clothing',
            ('shop','beauty'):'beauty', ('office','accountant'):'professional',
            ('office','lawyer'):'professional', ('office','estate_agent'):'professional',
            ('craft','plumber'):'home services', ('craft','electrician'):'home services',
            ('craft','carpenter'):'home services', ('craft','roofer'):'home services',
            ('craft','painter'):'home services', ('craft','hvac'):'home services',
            ('shop','car_repair'):'auto', ('amenity','car_wash'):'auto',
            ('amenity','dentist'):'health', ('amenity','clinic'):'health',
            ('amenity','veterinary'):'health', ('healthcare','physiotherapist'):'health',
        }.get(tuple(tag), location.split(',')[0] if isinstance(location,str) else 'business')
        from web.app import db as reachmark_db
        rows, meta = discover(location, category, limit=limit, ring=2, db=reachmark_db)
        for row in rows:
            row.setdefault('city', location)
            row.setdefault('category', category)
        return rows, place_name(location, meta.get('center'))
    except Exception:
        # Keep the established OSM-only path as a safety net when an optional provider
        # or migration is not ready. The fallback is still public-data-only.
        pass
    place=geocode(location)
    lat,lon=float(place['lat']),float(place['lon']); key,value=tag
    q=f'[out:json][timeout:40];nwr(around:15000,{lat},{lon})["{key}"="{value}"]["name"];out center tags {int(limit)};'
    from web.map_provider import query_overpass
    payload=query_overpass(q,HEADERS)
    if payload.get('remark'): raise ValueError(_t('er_115', locale_now()))
    rows=[]
    for item in payload.get('elements',[]):
        t=item.get('tags',{}); center=item.get('center',item)
        rows.append({'source_key':f"osm:{item['type']}:{item['id']}",'name':t['name'],'city':location,'address':', '.join(filter(None,[' '.join(filter(None,[t.get('addr:housenumber'),t.get('addr:street')])),t.get('addr:city'),t.get('addr:state'),t.get('addr:postcode'),t.get('addr:country')])),'phone':t.get('phone') or t.get('contact:phone',''),'email':t.get('email') or t.get('contact:email',''),'website':t.get('website') or t.get('contact:website',''),'source':'OpenStreetMap','source_url':f"https://www.openstreetmap.org/{item['type']}/{item['id']}",'latitude':center.get('lat'),'longitude':center.get('lon'),'opening_hours':t.get('opening_hours',''),'social_url':t.get('contact:facebook') or t.get('contact:instagram',''),'source_tags':t})
    return rows, place.get('display_name',location)

def place_name(location, center=None):
    return str(location)

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