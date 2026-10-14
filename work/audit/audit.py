"""Visual + contrast audit for Reachmark (local dev only).

Usage: python work/audit/audit.py [pages...]
Writes screenshots and a JSON report to work/audit/out/.
"""
import json, os, sys
from playwright.sync_api import sync_playwright

BASE = os.getenv('BASE', 'http://127.0.0.1:8000')
OUT = os.path.join(os.path.dirname(__file__), 'out')
os.makedirs(OUT, exist_ok=True)
PAGES = sys.argv[1:] or ['/', '/about', '/pricing', '/showcase', '/reviews', '/enquire',
                         '/signin', '/signup', '/login', '/receptionist', '/sample-report', '/privacy']
VIEWPORTS = {'desktop': (1440, 900), 'mobile': (390, 844)}

CONTRAST_JS = r"""
() => {
  function parse(c){const m=c.match(/rgba?\(([^)]+)\)/);if(!m)return null;const p=m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1};}
  function lum(c){const f=v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)};return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b);}
  function blend(top,bot){const a=top.a+bot.a*(1-top.a);if(!a)return {r:255,g:255,b:255,a:0};return {r:(top.r*top.a+bot.r*bot.a*(1-top.a))/a,g:(top.g*top.a+bot.g*bot.a*(1-top.a))/a,b:(top.b*top.a+bot.b*bot.a*(1-top.a))/a,a};}
  function bgOf(el){let layers=[];let img=false;for(let e=el;e;e=e.parentElement){const s=getComputedStyle(e);if(s.backgroundImage&&s.backgroundImage!=='none'&&!/^url/.test(s.backgroundImage))img=true;const c=parse(s.backgroundColor);if(c&&c.a>0){layers.push(c);if(c.a>=1)break;}}
    let col={r:255,g:255,b:255,a:1};const rootBg=parse(getComputedStyle(document.documentElement).backgroundColor);if(rootBg&&rootBg.a>0&&!layers.some(l=>l.a>=1))col=rootBg;for(let i=layers.length-1;i>=0;i--)col=blend(layers[i],col);return {col,img};}
  const out=[];const seen=new Set();
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()){const t=walker.currentNode;const txt=t.textContent.trim();if(txt.length<2)continue;const el=t.parentElement;if(!el||seen.has(el))continue;seen.add(el);
    const s=getComputedStyle(el);if(s.visibility==='hidden'||s.display==='none'||+s.opacity===0)continue;const r=el.getBoundingClientRect();if(r.width<2||r.height<2)continue;
    if(el.closest('[hidden],[aria-hidden="true"],script,style,noscript,.rm-sr,.sr-only,.visually-hidden'))continue;
    let op=1;for(let e=el;e;e=e.parentElement){op*=+getComputedStyle(e).opacity;}if(op<0.05)continue;
    const fg=parse(s.color);if(!fg)continue;const {col,img}=bgOf(el);const f=blend({...fg,a:fg.a*Math.min(1,op)},col);
    const L1=lum(f),L2=lum(col);const ratio=(Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05);
    const big=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.6&&+s.fontWeight>=700);
    if(ratio<(big?3:4.5)){out.push({text:txt.slice(0,60),tag:el.tagName.toLowerCase(),cls:(el.className&&el.className.baseVal===undefined?el.className:'').toString().slice(0,60),ratio:Math.round(ratio*100)/100,fg:s.color,bg:`rgb(${col.r|0},${col.g|0},${col.b|0})`,gradientBehind:img,y:Math.round(r.top+scrollY)});}
  }
  return out;
}
"""

def run():
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for vp, (w, h) in VIEWPORTS.items():
            for theme in ('light', 'dark'):
                ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=theme)
                ctx.add_init_script(f"try{{localStorage.setItem('reachmark-theme','{theme}')}}catch(e){{}}")
                page = ctx.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)[:200]))
                page.on('console', lambda m: m.type == 'error' and errors.append('console: ' + m.text[:200]))
                page.on('requestfailed', lambda r: ('googlesyndication' not in r.url and 'googletagmanager' not in r.url and 'tawk' not in r.url) and errors.append('failed: ' + r.url[:120]))
                page.on('response', lambda r: r.status >= 400 and r.url.startswith(BASE) and errors.append(f'{r.status}: {r.url[:120]}'))
                for path in PAGES:
                    errors.clear()
                    try:
                        page.goto(BASE + path, wait_until='networkidle', timeout=20000)
                    except Exception as exc:
                        errors.append('goto: ' + str(exc)[:120])
                    page.wait_for_timeout(600)
                    # reveal-on-scroll content: scroll through the page so it becomes visible
                    page.evaluate("async()=>{for(let y=0;y<document.body.scrollHeight;y+=600){scrollTo(0,y);await new Promise(r=>setTimeout(r,60));}scrollTo(0,0);}")
                    page.wait_for_timeout(400)
                    issues = page.evaluate(CONTRAST_JS)
                    name = (path.strip('/') or 'home').replace('/', '_')
                    page.screenshot(path=f'{OUT}/{name}-{vp}-{theme}.png', full_page=(vp == 'desktop'))
                    logo = page.evaluate("()=>{const c=[...document.querySelectorAll('header img, .x-head img, .pub-head img, .auth-logo img, .brand img, img[alt*=Reachmark]')].map(i=>[i,i.getBoundingClientRect()]).filter(([i,r])=>r.width>0&&r.height>0&&getComputedStyle(i).visibility!=='hidden');if(!c.length)return null;c.sort((a,b)=>a[1].top-b[1].top||b[1].width-a[1].width);const [i,r]=c[0];return {w:Math.round(r.width),h:Math.round(r.height),src:i.getAttribute('src')}}")
                    report[f'{path} {vp} {theme}'] = {'low_contrast': issues, 'errors': list(dict.fromkeys(errors)), 'logo': logo}
                ctx.close()
        browser.close()
    with open(f'{OUT}/report.json', 'w') as f:
        json.dump(report, f, indent=1)
    for k, v in report.items():
        print(f"{k:38} contrast={len(v['low_contrast']):3} errors={len(v['errors'])} logo={v['logo']}")

if __name__ == '__main__':
    run()
