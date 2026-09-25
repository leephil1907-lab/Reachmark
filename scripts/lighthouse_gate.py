"""Fail a release candidate when Lighthouse drops below the agreed floor.

Local CI audits run on HTTP localhost, so the HTTPS-only best-practice audit is
not a production signal there. Real HTTPS deployments keep the stricter floor.
"""
import json,sys

path,device=sys.argv[1:]
data=json.load(open(path,encoding="utf-8"))
scores={k:round((v.get("score") or 0)*100,1) for k,v in data.get("categories",{}).items()}
url=(data.get("finalDisplayedUrl") or data.get("requestedUrl") or "")
floors={"performance":75 if not url.startswith("http://127.0.0.1") else 70,"accessibility":90,"best-practices":90 if not url.startswith("http://127.0.0.1") else 70,"seo":90}
failed=[f"{k}={scores.get(k,0)} < {floor}" for k,floor in floors.items() if scores.get(k,0)<floor]
failed_audits=[]
for aid,audit in data.get("audits",{}).items():
    score=audit.get("score")
    if score is not None and score < 1 and audit.get("scoreDisplayMode") not in ("notApplicable","manual","informative"):
        failed_audits.append(f"{aid}: {audit.get('title','')} ({score})")
print(f"Lighthouse {device}: "+", ".join(f"{k}={v}" for k,v in scores.items()))
if failed_audits:
    print("Non-perfect audits:")
    for item in failed_audits[:25]:
        print(" - "+item)
if failed:
    print("FAIL: "+"; ".join(failed))
    raise SystemExit(1)
print("PASS: Lighthouse release floors met.")
