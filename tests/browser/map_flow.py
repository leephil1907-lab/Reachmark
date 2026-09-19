"""Disposable browser checks, with unavailable tiles and fixture-only map records."""
import os,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server,WSGIRequestHandler
from playwright.sync_api import sync_playwright, expect
class Quiet(WSGIRequestHandler):
    def log_request(self,*a,**kw):pass
with tempfile.TemporaryDirectory() as temp:
    # Owner sign-in is required to reach the workspace (fail-closed app):
    # configure a throwaway owner credential before the app is imported.
    os.environ['DATABASE_PATH']=str(Path(temp)/'maps.sqlite3');os.environ['OWNER_PASSWORD_HASH']=generate_password_hash('map-flow-owner');os.environ.pop('DASHBOARD_PASSWORD',None)
    import app as module
    server=make_server('127.0.0.1',0,module.app,threaded=True,request_handler=Quiet)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
    try:
        with patch('maps.query_overpass',return_value={'elements':[{'type':'node','id':999,'lat':6.52,'lon':3.32,'tags':{'name':'Disposable map fixture','shop':'bakery'}}]}),sync_playwright() as p:
            b=p.chromium.launch();page=b.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
            page.route('https://tile.openstreetmap.org/**',lambda route:route.abort())
            # '/' is the public page — sign in at /login first, then open the global finder
            page.goto(base+'/login');page.locator('#password').fill('map-flow-owner');page.get_by_role('button',name='Enter workspace').click();expect(page).to_have_url(base+'/workspace')
            page.goto(base+'/workspace#global');page.locator('#world-map.leaflet-container').wait_for()
            page.locator('#map-search').fill('6.52, 3.32');page.locator('#map-search-btn').click();page.locator('#map-category').select_option('Bakery');page.locator('#map-start').click()
            expect(page.locator('#map-records')).to_contain_text('1 mapped',timeout=15000)
            assert '1 mapped' in page.locator('#map-records').inner_text()
            page.locator('[data-map-fit]').click();page.screenshot(path=str(Path(temp)/'map-desktop.png'),full_page=True)
            page.reload();page.locator('#world-map.leaflet-container').wait_for();expect(page.locator('#map-history')).to_contain_text('· checked')
            page.set_viewport_size({'width':390,'height':844});page.evaluate('worldMap.invalidateSize()');page.screenshot(path=str(Path(temp)/'map-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'mobile overflow'
            assert not errors,errors
            print('PASS: navigation, coordinate search without geocoding, scan, persisted cells, tile-outage fallback, mobile alignment, no JS errors. Disposable data only.');b.close()
    finally:server.shutdown();thread.join(timeout=5)
