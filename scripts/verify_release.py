"""Post-deploy check: HTTPS release identity and private-data access control."""
import sys,time,requests
base,sha=sys.argv[1:];base=base.rstrip('/')
if not base.startswith('https://'):raise SystemExit('Production verification requires HTTPS')
for attempt in range(18):
    try:
        r=requests.get(base+'/healthz',timeout=10);r.raise_for_status()
        if r.json().get('release')==sha:break
    except requests.RequestException:pass
    time.sleep(5)
else:raise SystemExit('Deployment failed verification: expected release never became healthy')
for path in ('/api/state','/api/analytics','/api/export','/api/projects'):
    if requests.get(base+path,timeout=10,allow_redirects=False).status_code!=401:raise SystemExit('Private access check failed: '+path)
print('Verified HTTPS health, exact release SHA and owner-only API access.')
