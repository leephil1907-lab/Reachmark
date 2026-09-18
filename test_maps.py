"""Isolated map regressions: never call real providers or mutate the live database."""
import json, unittest
from unittest.mock import patch, MagicMock
from test_app import ProspectTests, module
from maps import grid, LIMIT
import map_provider

class MapTests(unittest.TestCase):
    setUp = ProspectTests.setUp
    tearDown = ProspectTests.tearDown
    # Inherit isolation utilities, without re-running parent test methods below.
    def start_scan(self, bounds=None):
        with patch('maps.threading.Thread'):
            response=self.client.post('/api/map/scans',json={'category':'Bakery','label':'Test area','bounds':bounds or [6.50,3.30,6.54,3.34]})
        self.assertEqual(response.status_code,202,response.json)
        return response.json['id']
    def test_grid_global_edges(self):
        self.assertTrue(grid([0,179.98,.02,-179.98]))
        for box in ([0,0,30,30],[0,0,0,1],[float('nan'),0,1,1],[False,0,1,1],[-91,0,0,1]):
            with self.assertRaises(ValueError): grid(box)
        self.assertTrue(grid([-89.99,1,-89.98,1.1]))
    def test_map_body_validation(self):
        for payload in ([],None,'text',{'category':[], 'bounds':[0,0,1,1]}):
            self.assertEqual(self.client.post('/api/map/scans',data=json.dumps(payload),content_type='application/json').status_code,400)
    def test_cell_resume_preserves_success_and_deduplicates(self):
        sid=self.start_scan([6.5,3.3,6.6,3.4]);worker=module.app.extensions['map_worker']
        payload={'elements':[{'type':'node','id':900,'lat':6.52,'lon':3.32,'tags':{'name':'Isolated map fixture','website':'https://example.test'}}]}
        with patch('maps.query_overpass',side_effect=[payload,ValueError('offline'),payload,payload]), self.assertLogs(module.app.logger,level='WARNING'): worker(sid)
        scan=self.client.get('/api/map/state').json['scans'][0]
        self.assertEqual(scan['state'],'partial');self.assertEqual(sum(c['state']=='failed' for c in scan['cells']),1)
        self.assertEqual(len(self.client.get('/api/state').json['leads']),1)
        with patch('maps.threading.Thread'): self.assertEqual(self.client.post(f'/api/map/scans/{sid}/resume',json={}).status_code,202)
        with patch('maps.query_overpass',return_value=payload) as query: worker(sid); self.assertEqual(query.call_count,1)
        self.assertEqual(self.client.get('/api/map/state').json['scans'][0]['state'],'checked')
        self.assertEqual(len(self.client.get('/api/state').json['leads']),1)
    def test_partial_never_checked(self):
        sid=self.start_scan()
        with patch('maps.query_overpass',return_value={'elements':[], 'remark':'runtime timeout'}): module.app.extensions['map_worker'](sid)
        scan=self.client.get('/api/map/state').json['scans'][0]
        self.assertEqual(scan['cells'][0]['state'],'partial')
        self.assertEqual(self.client.post(f'/api/map/scans/{sid}/resume',json={}).status_code,400)
    def test_cap_is_partial_and_existing_lead_survives(self):
        sid=self.start_scan()
        element={'type':'node','id':99,'lat':6.52,'lon':3.32,'tags':{'name':'Temporary cap fixture'}}
        with patch('maps.query_overpass',return_value={'elements':[element]*(LIMIT+1)}): module.app.extensions['map_worker'](sid)
        scan=self.client.get('/api/map/state').json['scans'][0]
        self.assertEqual(scan['cells'][0]['state'],'partial')
        self.assertEqual(scan['cells'][0]['found'],LIMIT)
        self.assertEqual(len(self.client.get('/api/state').json['leads']),1)
    def test_restart_recovers_queued_scan(self):
        import os, subprocess, sys
        sid=self.start_scan()
        with module.db() as c: c.execute("UPDATE map_cells SET state='running' WHERE scan_id=?",(sid,))
        result=subprocess.run([sys.executable,'-c','import app'],env={**os.environ,'DATABASE_PATH':module.DB},capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        scan=self.client.get('/api/map/state').json['scans'][0]
        self.assertEqual(scan['state'],'interrupted')
        self.assertTrue(all(c['state']=='pending' for c in scan['cells']))
    def test_cancel_stops_unstarted_cells(self):
        sid=self.start_scan();self.client.post(f'/api/map/scans/{sid}/cancel',json={})
        with patch('maps.query_overpass') as query: module.app.extensions['map_worker'](sid);query.assert_not_called()
        self.assertEqual(self.client.get('/api/map/state').json['scans'][0]['state'],'cancelled')
    def test_single_map_job(self):
        self.start_scan()
        self.assertEqual(self.client.post('/api/map/scans',json={'category':'Bakery','label':'Other','bounds':[6.5,3.3,6.54,3.34]}).status_code,409)
    def test_analytics_includes_actual_map_tasks(self):
        sid=self.start_scan()
        data=self.client.get('/api/analytics').json
        self.assertEqual(data['map_scan_states'],{'queued':1})
        self.assertEqual(data['tasks'][0]['id'],sid)
        self.assertEqual(data['tasks'][0]['state'],'queued')
        with patch('maps.query_overpass',return_value={'elements':[]}): module.app.extensions['map_worker'](sid)
        data=self.client.get('/api/analytics').json
        self.assertEqual(data['map_scan_states'],{'checked':1})
        self.assertEqual(data['map_cell_states'],{'checked':1})
        self.assertEqual(data['totals']['leads'],0)
    def test_place_cache(self):
        with patch('maps.geocode',return_value={'lat':'6.5','lon':'3.3','display_name':'Test place'}) as geo:
            self.assertEqual(self.client.post('/api/map/search',json={'query':'Test place'}).status_code,200)
            self.assertTrue(self.client.post('/api/map/search',json={'query':'TEST PLACE'}).json['cached']);self.assertEqual(geo.call_count,1)
    def test_map_auth(self):
        with patch.dict('os.environ',{'DASHBOARD_PASSWORD':'test'}):
            self.assertEqual(self.client.get('/api/map/state').status_code,401)
    def test_provider_fallback_and_rate_limit(self):
        response=MagicMock();response.__enter__.return_value=response;response.status_code=200;response.iter_content.return_value=[b'{"elements":[]}']
        import requests
        with patch.object(map_provider,'ENDPOINTS',['https://a.test','https://b.test']),patch.object(map_provider,'_cooldown',{}),patch.object(map_provider,'_rate_until',0),patch('map_provider.time.sleep'),patch('map_provider.requests.post',side_effect=[requests.Timeout(),response]) as post:
            self.assertEqual(map_provider.query_overpass('query',{}),{'elements':[]});self.assertEqual(post.call_count,2)
        response.status_code=429;response.headers={'Retry-After':'120'}
        with patch.object(map_provider,'ENDPOINTS',['https://a.test','https://b.test']),patch.object(map_provider,'_cooldown',{}),patch.object(map_provider,'_rate_until',0),patch('map_provider.time.sleep'),patch('map_provider.requests.post',return_value=response) as post:
            with self.assertRaises(ValueError):map_provider.query_overpass('query',{})
            self.assertEqual(post.call_count,1)

if __name__=='__main__':unittest.main()
