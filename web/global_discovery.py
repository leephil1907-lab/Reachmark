"""Global, provider-waterfall discovery primitives used by Reachmark's Scout."""
from __future__ import annotations
import math, os, re, time, unicodedata, uuid
from typing import Iterable
import requests

try:
    from web.services import geocode
except Exception:
    geocode=None
try:
    from web.map_provider import query_overpass
except Exception:
    query_overpass=None

CATEGORY_VARIANTS={
"restaurant":["restaurant","cafe","fast food","food court","bistro"],
"bakery":["bakery","pastry shop","bread shop"],
"florist":["florist","flower shop"],
"hotel":["hotel","guest house"],
"gym":["gym","fitness centre","fitness center"],
"laundry":["laundry","dry cleaning"],
"convenience":["convenience store","convenience"],
"supermarket":["supermarket","grocery store"],
"pharmacy":["pharmacy","chemist","drugstore"],
"clothing":["clothing","fashion","boutique","apparel"],
"beauty":["beauty salon","hairdresser","barber","spa","nail salon"],
"professional":["accountant","lawyer","consultant","architect","estate agent"],
"home services":["plumber","electrician","carpenter","roofer","painter","hvac"],
"auto":["car repair","auto repair","mechanic","car wash","tyre shop"],
"health":["clinic","dentist","physiotherapist","veterinary","medical centre"],
}
REGION_PRIORITY={
"NG":["google","osm","foursquare"],"GH":["google","osm","foursquare"],"KE":["google","osm","foursquare"],
"ZA":["google","osm","foursquare"],"US":["google","foursquare","osm"],"CA":["google","foursquare","osm"],
"GB":["google","foursquare","osm"],"AU":["google","foursquare","osm"],
"FR":["google","osm","foursquare"],"DE":["google","osm","foursquare"],
"BR":["google","foursquare","osm"],"MX":["google","foursquare","osm"],
"AE":["google","foursquare","osm"],"SA":["google","foursquare","osm"],
"IN":["google","foursquare","osm"],"ID":["google","foursquare","osm"],"MY":["google","foursquare","osm"],
"PH":["google","foursquare","osm"],"TH":["google","foursquare","osm"],
}
CHAIN_TOKENS={"mcdonalds","mcdonald's","kfc","subway","starbucks","dominos","pizza hut","burger king","hilton","marriott","radisson","ikea","carrefour","walmart","tesco"}

def norm_name(value):
    value=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode().lower()
    value=re.sub(r"[^a-z0-9]+"," ",value)
    return re.sub(r"\s+"," ",value).strip()

def distance_m(a,b):
    if a.get("latitude") is None or a.get("longitude") is None or b.get("latitude") is None or b.get("longitude") is None:return 10**9
    lat1,lon1,lat2,lon2=map(float,(a["latitude"],a["longitude"],b["latitude"],b["longitude"]))
    p=math.pi/180; x=(lon2-lon1)*p*math.cos((lat1+lat2)*p/2); y=(lat2-lat1)*p
    return 6371000*math.sqrt(x*x+y*y)

def is_chain(row):
    n=norm_name(row.get("name"))
    return any(t in n for t in CHAIN_TOKENS)

def dedupe(rows,radius_m=100):
    out=[]
    for row in rows:
        name=norm_name(row.get("name"))
        if not name:continue
        duplicate=None
        for existing in out:
            if row.get("phone") and existing.get("phone") and re.sub(r"\D","",row["phone"])==re.sub(r"\D","",existing["phone"]):duplicate=existing;break
            if name==norm_name(existing.get("name")) and distance_m(row,existing)<=radius_m:duplicate=existing;break
            if distance_m(row,existing)<=radius_m and (name in norm_name(existing.get("name")) or norm_name(existing.get("name")) in name):duplicate=existing;break
        if duplicate:
            for k,v in row.items():
                if v and not duplicate.get(k):duplicate[k]=v
        else:out.append(dict(row))
    return out

def category_queries(category):
    key=norm_name(category)
    for group,variants in CATEGORY_VARIANTS.items():
        if group in key or any(v in key for v in variants):return list(dict.fromkeys([category]+variants))
    return [category]

def grid_points(lat,lon,ring=2,cell_km=3):
    dlat=cell_km/111.0; dlon=cell_km/(111.0*max(0.2,math.cos(math.radians(lat))))
    for y in range(-ring,ring+1):
        for x in range(-ring,ring+1):
            yield lat+y*dlat,lon+x*dlon

def osm_search(variant,lat,lon,radius=3000):
    if not query_overpass:return [],"unavailable"
    mapping={"restaurant":("amenity","restaurant"),"cafe":("amenity","cafe"),"pharmacy":("amenity","pharmacy"),"clothing":("shop","clothes"),"fashion":("shop","clothes"),"beauty salon":("shop","beauty"),"hairdresser":("shop","hairdresser"),"barber":("shop","hairdresser"),"spa":("shop","beauty"),"nail salon":("shop","beauty"),"plumber":("craft","plumber"),"electrician":("craft","electrician"),"carpenter":("craft","carpenter"),"roofer":("craft","roofer"),"painter":("craft","painter"),"hvac":("craft","hvac"),"car repair":("shop","car_repair"),"auto repair":("shop","car_repair"),"mechanic":("shop","car_repair"),"car wash":("amenity","car_wash"),"dentist":("amenity","dentist"),"clinic":("amenity","clinic"),"veterinary":("amenity","veterinary"),"accountant":("office","accountant"),"lawyer":("office","lawyer"),"estate agent":("office","estate_agent"),"bakery":("shop","bakery"),"pastry shop":("shop","bakery"),"bread shop":("shop","bakery"),"florist":("shop","florist"),"flower shop":("shop","florist"),"hotel":("tourism","hotel"),"guest house":("tourism","guest_house"),"gym":("leisure","fitness_centre"),"fitness centre":("leisure","fitness_centre"),"fitness center":("leisure","fitness_centre"),"laundry":("shop","laundry"),"dry cleaning":("shop","dry_cleaning"),"convenience store":("shop","convenience"),"convenience":("shop","convenience"),"supermarket":("shop","supermarket"),"grocery store":("shop","supermarket")}
    pair=mapping.get(norm_name(variant))
    if not pair:return [],"no OSM tag"
    q=f'[out:json][timeout:40];nwr(around:{int(radius)},{lat},{lon})["{pair[0]}"="{pair[1]}"]["name"];out center tags 80;'
    try:data=query_overpass(q,{"User-Agent":"Reachmark/1.0 public business discovery"})
    except Exception as exc:return [],f"request failed: {type(exc).__name__}"
    rows=[]
    for item in data.get("elements",[]):
        t=item.get("tags") or {}; center=item.get("center",item)
        rows.append({"source_key":f"osm:{item.get('type')}:{item.get('id')}","name":t.get("name",""),"address":", ".join(filter(None,[t.get("addr:street"),t.get("addr:city"),t.get("addr:state"),t.get("addr:postcode")])), "phone":t.get("phone") or t.get("contact:phone",""),"email":t.get("email") or t.get("contact:email",""),"website":t.get("website") or t.get("contact:website",""),"source":"OpenStreetMap","source_url":f"https://www.openstreetmap.org/{item.get('type')}/{item.get('id')}","latitude":center.get("lat"),"longitude":center.get("lon"),"opening_hours":t.get("opening_hours",""),"social_url":t.get("contact:facebook") or t.get("contact:instagram",""),"source_tags":{"provider":"osm",**t}})
    return rows,""

def _google_key():return os.getenv("GOOGLE_PLACES_API_KEY","").strip()
def _fsq_key():return os.getenv("FOURSQUARE_API_KEY","").strip()

def google_search(query,lat=None,lon=None,limit=20,timeout=15):
    key=_google_key()
    if not key:return [],"not configured"
    endpoint="https://places.googleapis.com/v1/places:searchText"
    mask="places.id,places.displayName,places.formattedAddress,places.internationalPhoneNumber,places.websiteUri,places.location,places.primaryTypeDisplayName,places.googleMapsUri,places.rating,places.userRatingCount,places.businessStatus"
    body={"textQuery":query,"pageSize":min(20,max(1,int(limit)))}
    if lat is not None and lon is not None:body["locationBias"]={"circle":{"center":{"latitude":lat,"longitude":lon},"radius":3000}}
    headers={"X-Goog-Api-Key":key,"X-Goog-FieldMask":mask,"Content-Type":"application/json"}
    rows=[]; token=None
    for _ in range(3):
        if token:body["pageToken"]=token
        try:r=requests.post(endpoint,json=body,headers=headers,timeout=timeout)
        except requests.RequestException as exc:return rows,f"request failed: {type(exc).__name__}"
        if r.status_code in (401,403):return rows,"key rejected"
        if r.status_code==429:return rows,"rate limited"
        if r.status_code>=400:return rows,f"HTTP {r.status_code}"
        data=r.json(); 
        for p in data.get("places") or []:
            if p.get("businessStatus") in ("CLOSED_PERMANENTLY","CLOSED_TEMPORARILY"):continue
            reviews=p.get("userRatingCount")
            if reviews is not None and int(reviews)<5:continue
            loc=p.get("location") or {};pid=p.get("id","")
            rows.append({"source_key":f"google:{pid}","name":(p.get("displayName") or {}).get("text",""),"address":p.get("formattedAddress",""),"phone":p.get("internationalPhoneNumber",""),"website":p.get("websiteUri",""),"source":"Google Maps","source_url":p.get("googleMapsUri",""),"latitude":loc.get("latitude"),"longitude":loc.get("longitude"),"source_tags":{"provider":"google","rating":p.get("rating"),"review_count":reviews,"business_status":p.get("businessStatus"),"primary_type":(p.get("primaryTypeDisplayName") or {}).get("text","")}})
        token=data.get("nextPageToken")
        if not token:break
        time.sleep(2)
    return rows,""

def foursquare_search(query,lat,lon,limit=50,timeout=15):
    key=_fsq_key()
    if not key:return [],"not configured"
    try:r=requests.get(
        "https://places-api.foursquare.com/places/search",
        headers={"Authorization":f"Bearer {key}","Accept":"application/json","X-Places-Api-Version":"2025-06-17"},
        params={"query":query,"ll":f"{lat},{lon}","radius":5000,"limit":min(50,max(1,int(limit)))},
        timeout=timeout)
    except requests.RequestException as exc:return [],f"request failed: {type(exc).__name__}"
    if r.status_code==429:return [],"rate limited"
    if r.status_code>=400:return [],f"HTTP {r.status_code}"
    rows=[]
    for p in (r.json().get("results") or []):
        stats=p.get("stats") or {}; reviews=stats.get("total_ratings") or p.get("total_ratings") or p.get("rating_count")
        if reviews is not None and int(reviews)<5:continue
        g=(p.get("geocodes") or {}).get("main") or {}
        loc=p.get("location") or {}; fsqid=p.get("fsq_place_id") or p.get("fsq_id","")
        rows.append({"source_key":f"foursquare:{fsqid}","name":p.get("name",""),"address":loc.get("formatted_address") or loc.get("address",""),"phone":p.get("tel",""),"website":p.get("website",""),"source":"Foursquare","source_url":f"https://foursquare.com/v/{fsqid}" if fsqid else "","latitude":g.get("latitude"),"longitude":g.get("longitude"),"source_tags":{"provider":"foursquare","review_count":reviews,"rating":p.get("rating")}})
    return rows,""


def _cell_key(lat,lon):
    return round(float(lat),4),round(float(lon),4)

def _cell_seen(db,location,category,provider,lat,lon):
    if not db:return False
    try:
        with db() as c:
            return c.execute("SELECT 1 FROM discovery_cells WHERE location_key=? AND category=? AND provider=? AND cell_lat=? AND cell_lon=? LIMIT 1",(location,category,provider,*_cell_key(lat,lon))).fetchone() is not None
    except Exception:return False

def _mark_cell(db,location,category,provider,lat,lon,count):
    if not db:return
    try:
        with db() as c:
            c.execute("INSERT OR REPLACE INTO discovery_cells(id,location_key,category,provider,cell_lat,cell_lon,radius_m,status,scanned_at,result_count) VALUES(?,?,?,?,?,?,?,?,datetime('now'),?)",(uuid.uuid4().hex,location,category,provider,*_cell_key(lat,lon),3000,"scanned",int(count)))
    except Exception:
        pass

def discover(location,category,limit=20,ring=2,db=None):
    if not geocode:raise RuntimeError("Geocoder unavailable")
    place=geocode(location); lat,lon=float(place["lat"]),float(place["lon"])
    country=(place.get("address") or {}).get("country_code","").upper()
    providers=REGION_PRIORITY.get(country,["google","foursquare","osm"])
    variants=category_queries(category); candidates=[]
    for glat,glon in grid_points(lat,lon,ring):
        for provider in providers:
            if _cell_seen(db,location,category,provider,glat,glon):
                continue
            before=len(candidates)
            for variant in variants:
                if provider=="google":
                    rows,_=google_search(f"{variant} in {location}",glat,glon,20)
                elif provider=="foursquare":
                    rows,_=foursquare_search(variant,glat,glon,50)
                else:
                    rows,_=osm_search(variant,glat,glon)
                candidates.extend(rows)
            _mark_cell(db,location,category,provider,glat,glon,len(candidates)-before)
        if len(candidates)>=max(limit*6,60):break
    candidates=dedupe(candidates)
    return candidates[:max(limit*6,60)],{"country":country,"providers":providers,"queries":variants,"center":{"lat":lat,"lon":lon}}

def rank(rows,site_scores=None):
    site_scores=site_scores or {}; ranked=[]
    for row in dedupe(rows):
        tags=row.setdefault("source_tags",{}); reviews=tags.get("review_count")
        if reviews is not None and int(reviews)<5:continue
        if is_chain(row):continue
        name=norm_name(row.get("name")); score=0
        tier=site_scores.get(row.get("source_key"),{}).get("tier")
        if tier=="NO_SITE":score+=50
        elif tier=="SOCIAL_ONLY":score+=42
        elif tier=="FREE_BUILDER":score+=32
        elif tier=="BROKEN":score+=45
        elif tier=="WEAK":score+=28
        elif tier=="OK":score-=20
        rating=tags.get("rating") or 0
        score+=min(20,float(rating)*4)
        score+=min(15,(int(reviews) if reviews is not None else 0)/20)
        if row.get("phone"):score+=5
        if row.get("email"):score+=8
        row["opportunity_score"]=round(score,2); row["website_tier"]=tier or ("NO_SITE" if not row.get("website") else "UNSCANNED")
        ranked.append(row)
    return sorted(ranked,key=lambda x:x["opportunity_score"],reverse=True)