"""Bounded viewport discovery with durable per-cell progress; no world-wide scraping."""
import json, math, threading, uuid
from flask import request, jsonify
from web.services import geocode, HEADERS
from web.map_provider import query_overpass

LIMIT = 500

def grid(bounds):
    if not isinstance(bounds,list) or len(bounds)!=4 or any(type(x) not in (int,float) or not math.isfinite(x) for x in bounds):
        raise ValueError('Bounds must be four finite numbers: south, west, north, east.')
    south,west,north,east = bounds
    if not (-90<=south<north<=90 and -180<=west<=180 and -180<=east<=180) or west==east:
        raise ValueError('Invalid geographic bounds.')
    span=(east-west)%360
    # Limit angular span as well as area, including at high latitudes.
    height=(north-south)*111.32
    width=span*111.32*max(.01,math.cos(math.radians((north+south)/2)))
    if height>25 or width>25 or span>2 or north-south>1:
        raise ValueError('Zoom in: each scan must be at most 25 km wide and 25 km high (longitude span ≤2°).')
    parts=[(west,east)] if west<east else [(west,180),(-180,east)]
    cells=[]
    for w,e in parts:
        if w==e: continue
        ny=max(1,math.ceil(height/7)); nx=max(1,math.ceil((e-w)/span*width/7))
        for y in range(ny):
            for x in range(nx):
                cells.append([south+(north-south)*y/ny,w+(e-w)*x/nx,south+(north-south)*(y+1)/ny,w+(e-w)*(x+1)/nx])
    if len(cells)>20: raise ValueError('Select a smaller area (maximum 20 cells).')
    return cells

def rows_from_payload(payload, category, label):
    rows=[]
    for item in payload['elements'][:LIMIT]:
        tags=item.get('tags',{}); point=item.get('center',item)
        if not tags.get('name') or item.get('type') not in ('node','way','relation') or not isinstance(item.get('id'),int): continue
        rows.append(dict(source_key=f"osm:{item['type']}:{item['id']}",name=tags['name'],category=category,city=tags.get('addr:city') or label,
            address=', '.join(filter(None,[' '.join(filter(None,[tags.get('addr:housenumber'),tags.get('addr:street')])),tags.get('addr:city'),tags.get('addr:state'),tags.get('addr:postcode'),tags.get('addr:country')])),
            website=tags.get('website') or tags.get('contact:website',''),email=tags.get('email') or tags.get('contact:email',''),phone=tags.get('phone') or tags.get('contact:phone',''),
            source='OpenStreetMap',source_url=f"https://www.openstreetmap.org/{item['type']}/{item['id']}",latitude=point.get('lat'),longitude=point.get('lon'),opening_hours=tags.get('opening_hours',''),social_url=tags.get('contact:facebook') or tags.get('contact:instagram',''),source_tags=tags))
    return rows

def register_maps(app, db, now, add_lead, categories):
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS map_scans(id TEXT PRIMARY KEY,label TEXT,category TEXT,bounds TEXT,state TEXT,created TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS map_cells(id TEXT PRIMARY KEY,scan_id TEXT,bounds TEXT,state TEXT,found INTEGER DEFAULT 0,message TEXT DEFAULT '',updated TEXT);
        CREATE INDEX IF NOT EXISTS map_cells_scan ON map_cells(scan_id);
        CREATE TABLE IF NOT EXISTS map_geocache(query TEXT PRIMARY KEY,data TEXT,created TEXT);
        ''')
        c.execute("UPDATE map_scans SET state='interrupted' WHERE state IN ('queued','running')")
        c.execute("UPDATE map_cells SET state='pending',message='Interrupted; resume to retry this cell.' WHERE state='running'")
    worker_lock=threading.Lock()

    def run(sid):
        with worker_lock:
            try:
                with db() as c:
                    scan=dict(c.execute('SELECT * FROM map_scans WHERE id=?',(sid,)).fetchone())
                    cells=[dict(r) for r in c.execute("SELECT * FROM map_cells WHERE scan_id=? AND state='pending' ORDER BY rowid",(sid,))]
                for cell in cells:
                    with db() as c:
                        if c.execute('SELECT state FROM map_scans WHERE id=?',(sid,)).fetchone()[0]=='cancelled': return
                        c.execute("UPDATE map_scans SET state='running',updated=? WHERE id=?",(now(),sid))
                        c.execute("UPDATE map_cells SET state='running',updated=? WHERE id=?",(now(),cell['id']))
                    try:
                        key,value=categories[scan['category']]
                        box=','.join(str(x) for x in json.loads(cell['bounds']))
                        query=f'[out:json][timeout:35];nwr({box})["{key}"="{value}"]["name"];out center tags {LIMIT+1};'
                        data=query_overpass(query,HEADERS)
                        rows=rows_from_payload(data,scan['category'],scan['label'])
                        for row in rows: add_lead(row)
                        partial=bool(data.get('remark')) or len(data['elements'])>LIMIT
                        status='partial' if partial else 'checked'
                        message=('Source incomplete or listing cap reached. Zoom into this cell and scan smaller areas.' if partial else 'Selected category queried; not proof of exhaustive business coverage.')
                        found=len(rows)
                    except Exception:
                        app.logger.warning('Map cell could not complete',exc_info=True)
                        status='failed';found=0;message='Source request failed. Saved leads remain available. Wait at least one minute, then resume.'
                    with db() as c:
                        c.execute('UPDATE map_cells SET state=?,found=?,message=?,updated=? WHERE id=?',(status,found,message,now(),cell['id']))
                with db() as c:
                    statuses=[r[0] for r in c.execute('SELECT state FROM map_cells WHERE scan_id=?',(sid,))]
                    status='checked' if all(x=='checked' for x in statuses) else 'partial'
                    c.execute("UPDATE map_scans SET state=?,updated=? WHERE id=? AND state!='cancelled'",(status,now(),sid))
            except Exception:
                app.logger.exception('Map worker interrupted')
                with db() as c:
                    c.execute("UPDATE map_scans SET state='interrupted',updated=? WHERE id=? AND state!='cancelled'",(now(),sid))
                    c.execute("UPDATE map_cells SET state='pending' WHERE scan_id=? AND state='running'",(sid,))
    app.extensions['map_worker']=run

    @app.get('/api/map/state')
    def map_state():
        with db() as c:
            scans=[dict(r) for r in c.execute('SELECT * FROM map_scans ORDER BY created DESC LIMIT 50')]
            for scan in scans:
                scan['bounds']=json.loads(scan['bounds'])
                scan['cells']=[{**dict(r),'bounds':json.loads(r['bounds'])} for r in c.execute('SELECT * FROM map_cells WHERE scan_id=? ORDER BY rowid',(scan['id'],))]
        return jsonify(scans=scans,history_limit=50)

    @app.post('/api/map/search')
    def map_search():
        value=request.get_json().get('query')
        if not isinstance(value,str) or not 2<=len(value.strip())<=150: return jsonify(error='Enter a city and country, or coordinates.'),400
        value=value.strip(); cachekey=value.casefold()
        with db() as c: cached=c.execute('SELECT * FROM map_geocache WHERE query=?',(cachekey,)).fetchone()
        if cached: return jsonify(place=json.loads(cached['data']),cached=True,cached_at=cached['created'])
        try:
            place=geocode(value)
            with db() as c: c.execute('INSERT OR REPLACE INTO map_geocache VALUES(?,?,?)',(cachekey,json.dumps(place),now()))
            return jsonify(place=place,cached=False)
        except Exception:
            return jsonify(error='Place search unavailable or no match. Pan/zoom manually or enter latitude, longitude; saved records are unaffected.'),502

    @app.post('/api/map/scans')
    def map_start():
        value=request.get_json(); category=value.get('category');label=value.get('label','Selected map area')
        if not isinstance(category,str) or category not in categories or not isinstance(label,str) or not 1<=len(label.strip())<=150:
            return jsonify(error='Select a supported category and an area label (1–150 characters).'),400
        try: cells=grid(value.get('bounds'))
        except ValueError as e: return jsonify(error=str(e)),400
        sid=uuid.uuid4().hex
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT 1 FROM map_scans WHERE state IN ('queued','running')").fetchone(): return jsonify(error='Pause the active map scan before starting another.'),409
            c.execute('INSERT INTO map_scans VALUES(?,?,?,?,?,?,?)',(sid,label.strip(),category,json.dumps(value['bounds']),'queued',now(),now()))
            for cell in cells: c.execute('INSERT INTO map_cells(id,scan_id,bounds,state,updated) VALUES(?,?,?,?,?)',(uuid.uuid4().hex,sid,json.dumps(cell),'pending',now()))
        threading.Thread(target=run,args=(sid,),daemon=True).start()
        return jsonify(id=sid),202

    @app.post('/api/map/scans/<sid>/<action>')
    def map_action(sid,action):
        if action not in ('resume','cancel'): return jsonify(error='Unknown action.'),404
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            scan=c.execute('SELECT * FROM map_scans WHERE id=?',(sid,)).fetchone()
            if not scan: return jsonify(error='Scan not found.'),404
            if action=='cancel':
                c.execute("UPDATE map_scans SET state='cancelled',updated=? WHERE id=? AND state IN ('queued','running')",(now(),sid))
                return jsonify(ok=True)
            if worker_lock.locked() or c.execute("SELECT 1 FROM map_scans WHERE state IN ('queued','running')").fetchone(): return jsonify(error='Wait for the in-flight scan to stop.'),409
            todo=c.execute("SELECT 1 FROM map_cells WHERE scan_id=? AND state IN ('pending','failed','running')",(sid,)).fetchone()
            if not todo: return jsonify(error='No retryable cells. For partial/dense cells, zoom in and start a smaller scan.'),400
            c.execute("UPDATE map_cells SET state='pending' WHERE scan_id=? AND state IN ('failed','running')",(sid,))
            c.execute("UPDATE map_scans SET state='queued',updated=? WHERE id=?",(now(),sid))
        threading.Thread(target=run,args=(sid,),daemon=True).start()
        return jsonify(ok=True),202
