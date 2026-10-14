"""List the component selectors responsible for dark-mode contrast failures."""
import json,sys,os,collections
sys.path.insert(0,os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
B='http://127.0.0.1:8000'
JS=r"""
() => {
 function parse(c){const m=c.match(/rgba?\(([^)]+)\)/);if(!m)return null;const p=m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1};}
 function lum(c){const f=v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)};return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b);}
 function path(e){const parts=[];for(let n=e;n&&n!==document.body&&parts.length<3;n=n.parentElement){let s=n.tagName.toLowerCase();if(n.id)s+='#'+n.id;else if(n.classList.length)s+='.'+[...n.classList].slice(0,2).join('.');parts.unshift(s);}return parts.join(' > ');}
 const light=[],darkText=[];
 for(const el of document.querySelectorAll('body *')){
   const r=el.getBoundingClientRect(); if(r.width<30||r.height<14)continue; const s=getComputedStyle(el); if(s.display==='none'||s.visibility==='hidden')continue;
   if(el.closest('.tour-card,.adsense-sidebar,ins,iframe,svg,canvas,[aria-hidden="true"]'))continue;
   const bg=parse(s.backgroundColor); if(bg&&bg.a>0.6&&lum(bg)>0.7) light.push(path(el));
   const hasText=[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim().length>1);
   if(hasText){const fg=parse(s.color); if(fg&&lum(fg)<0.12) darkText.push(path(el)+' ['+s.color+']');}
 }
 return {light,darkText};
}"""
pages=sys.argv[1:]
out={}
with sync_playwright() as p:
    b=p.chromium.launch(); c=b.new_context(viewport={'width':1440,'height':900},color_scheme='dark')
    c.add_init_script("localStorage.setItem('rm-tour-seen','1');localStorage.setItem('reachmark-theme','dark')")
    pg=c.new_page(); pg.route('**/*googlesyndication*/**',lambda r:r.abort())
    for path in pages:
        if path.startswith('ws:'):
            if 'logged' not in out:
                pg.goto(B+'/login'); pg.fill('input[name=password]','devpass'); pg.click('button[type=submit]'); pg.wait_for_url('**/workspace'); pg.wait_for_timeout(1000); out['logged']=1
            pg.evaluate("n=>window.navigate(n)",path[3:]); pg.wait_for_timeout(900)
        else:
            pg.goto(B+path,wait_until='networkidle'); pg.wait_for_timeout(500)
            pg.evaluate("async()=>{for(let y=0;y<document.body.scrollHeight;y+=700){scrollTo(0,y);await new Promise(r=>setTimeout(r,40));}}")
        r=pg.evaluate(JS)
        out[path]={k:collections.Counter(v).most_common(40) for k,v in r.items()}
    b.close()
out.pop('logged',None)
for k,v in out.items():
    print('#####',k)
    for kind in ('light','darkText'):
        print('  --',kind)
        for sel,n in v[kind]: print('   ',n,sel)
