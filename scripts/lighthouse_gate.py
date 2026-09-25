"""Fail a release candidate when Lighthouse drops below the agreed floor."""
import json,sys
path,device=sys.argv[1:]
data=json.load(open(path,encoding="utf-8"))
scores={k:round((v.get("score") or 0)*100,1) for k,v in data.get("categories",{}).items()}
floors={"performance":75,"accessibility":90,"best-practices":90,"seo":90}
failed=[f"{k}={scores.get(k,0)} < {floor}" for k,floor in floors.items() if scores.get(k,0)<floor]
print(f"Lighthouse {device}: "+", ".join(f"{k}={v}" for k,v in scores.items()))
if failed:
    print("FAIL: "+"; ".join(failed))
    raise SystemExit(1)
print("PASS: Lighthouse release floors met.")
