import json,sys,os,collections
sys.path.insert(0,os.path.dirname(__file__))
from audit import CONTRAST_JS
from playwright.sync_api import sync_playwright
B='http://127.0.0.1:8000'
res={}
with sync_playwright() as p:
    b=p.chromium.launch()
    for theme in ('light','dark'):
        c=b.new_context(viewport={'width':1440,'height':900},color_scheme=theme)
        c.add_init_script(f"localStorage.setItem('rm-tour-seen','1');localStorage.setItem('reachmark-theme','{theme}')")
        pg=c.new_page(); pg.route('**/*googlesyndication*/**',lambda r:r.abort())
        pg.goto(B+'/login'); pg.fill('input[name=password]','devpass'); pg.click('button[type=submit]'); pg.wait_for_url('**/workspace'); pg.wait_for_timeout(1200)
        print(theme,'html data-theme=',pg.evaluate("document.documentElement.getAttribute('data-theme')"), 'body class=',pg.evaluate("document.body.className"))
        pages=pg.evaluate("()=>[...new Set([...document.querySelectorAll('[data-page]')].map(e=>e.dataset.page))]")
        for n in pages:
            pg.evaluate("n=>window.navigate(n)",n); pg.wait_for_timeout(900)
            iss=pg.evaluate(CONTRAST_JS)
            # inputs/selects with white bg in dark mode
            if theme=='dark':
                bright=pg.evaluate("""n=>[...document.querySelectorAll('#page-'+n+' input, #page-'+n+' select, #page-'+n+' textarea, #page-'+n+' .card, #page-'+n+' button')].filter(e=>{const r=e.getBoundingClientRect();if(!r.width)return false;const m=getComputedStyle(e).backgroundColor.match(/\\d+/g);return m&&+m[0]>225&&+m[1]>225&&+m[2]>225&&(m[3]===undefined||+m[3]>0)}).map(e=>e.tagName.toLowerCase()+'.'+(e.className||'').toString().slice(0,30))""",n)
            else: bright=[]
            res[f'{theme} {n}']={'low':iss,'white_in_dark':bright}
        c.close()
    b.close()
json.dump(res,open(os.path.join(os.path.dirname(__file__),'out','ws_contrast.json'),'w'),indent=1)
for k,v in res.items():
    ex=collections.Counter((i['tag']+'.'+i['cls'][:25]) for i in v['low']).most_common(4)
    print(f"{k:26} low={len(v['low']):3} whiteInDark={len(v['white_in_dark']):3} {ex}")
