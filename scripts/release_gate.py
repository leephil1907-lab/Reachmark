import json,sys
p=sys.argv[1]
d=json.load(open(p,encoding='utf-8'))
for k,v in d.get('categories',{}).items():
    score=(v.get('score') or 0)*100
    print(k,round(score,1))
    if score < 90 and k in ('accessibility','seo'): raise SystemExit(1)
print('PASS')
