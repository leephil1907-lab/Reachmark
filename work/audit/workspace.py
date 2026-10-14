"""Workspace + guided tour audit (local dev only, DASHBOARD_PASSWORD=devpass)."""
import json, os, sys
from playwright.sync_api import sync_playwright

BASE = os.getenv('BASE', 'http://127.0.0.1:8000')
OUT = os.path.join(os.path.dirname(__file__), 'out', 'ws')
os.makedirs(OUT, exist_ok=True)
THEMES = sys.argv[1:] or ['light', 'dark']


def login(page):
    page.goto(BASE + '/login')
    page.fill('input[name=password]', 'devpass')
    page.click('button[type=submit]')
    page.wait_for_url('**/workspace', timeout=15000)


def run():
    result = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for vp, (w, h) in {'desktop': (1440, 900), 'mobile': (390, 844)}.items():
            for theme in THEMES:
                ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=theme)
                ctx.add_init_script(f"try{{localStorage.setItem('reachmark-theme','{theme}');localStorage.setItem('rm-theme','{theme}')}}catch(e){{}}")
                page = ctx.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)[:220]))
                page.on('console', lambda m: m.type == 'error' and 'Content Security Policy' not in m.text and errors.append('console: ' + m.text[:220]))
                page.on('response', lambda r: r.status >= 400 and r.url.startswith(BASE) and errors.append(f'{r.status} {r.request.method} {r.url[len(BASE):][:100]}'))
                login(page)
                page.wait_for_timeout(1500)
                key = f'{vp}-{theme}'
                page.screenshot(path=f'{OUT}/{key}-landing.png')
                # nav pages
                pages = page.evaluate("()=>[...document.querySelectorAll('[data-page]')].map(e=>e.getAttribute('data-page')).filter((v,i,a)=>v&&a.indexOf(v)===i)")
                sections = page.evaluate("()=>[...document.querySelectorAll('[id^=page-]')].map(e=>e.id)")
                info = {'nav': pages, 'sections': sections, 'pages': {}}
                if vp == 'desktop':
                    for name in pages:
                        errors_before = len(errors)
                        ok = page.evaluate("n=>{if(typeof window.navigate!=='function')return 'no navigate()';window.navigate(n);return 'ok'}", name)
                        page.wait_for_timeout(700)
                        vis = page.evaluate("""n=>{const s=document.getElementById('page-'+n);if(!s)return {exists:false};
                          const r=s.getBoundingClientRect();const st=getComputedStyle(s);
                          const text=(s.innerText||'').trim();
                          return {exists:true,visible:st.display!=='none'&&r.height>40,height:Math.round(r.height),chars:text.length}}""", name)
                        page.screenshot(path=f'{OUT}/{key}-page-{name}.png')
                        info['pages'][name] = {'nav': ok, **vis, 'new_errors': errors[errors_before:]}
                # tour
                page.evaluate("()=>{try{localStorage.removeItem('rm-tour-seen')}catch(e){}}")
                has = page.evaluate("()=>typeof window.startTour")
                tour = {'startTour': has, 'steps': []}
                if has == 'function':
                    page.evaluate("()=>window.startTour()")
                    for i in range(13):
                        page.wait_for_timeout(1300)
                        st = page.evaluate("""()=>{const card=document.querySelector('.tour-card, .rm-tour-card, [class*=tour][role=dialog]');
                          const spot=document.querySelector('.tour-hole');const tgt=document.querySelector('[data-tour-active]');
                          const vr=r=>r?{x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)}:null;
                          const inView=e=>{if(!e)return false;const r=e.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth&&r.width>0};
                          return {card:!!card,cardBox:card?vr(card.getBoundingClientRect()):null,cardInView:inView(card),
                            title:card?(card.querySelector('h2,h3,strong,b')||{}).textContent:null,
                            spot:tgt?(tgt.id||tgt.className).toString().slice(0,60):null,holeOpacity:spot?getComputedStyle(spot).opacity:null,spotBox:spot?vr(spot.getBoundingClientRect()):null,spotInView:inView(spot),
                            overlap: card&&spot?(()=>{const a=card.getBoundingClientRect(),b=spot.getBoundingClientRect();return !(a.right<b.left||a.left>b.right||a.bottom<b.top||a.top>b.bottom)})():null}}""")
                        page.screenshot(path=f'{OUT}/{key}-tour-{i+1}.png')
                        tour['steps'].append(st)
                        if not st['card']:
                            break
                        nxt = page.query_selector('.tour-card [data-tour-next], .tour-card button.primary, .tour-next, [data-tour=next]')
                        if not nxt:
                            btns = page.query_selector_all('.tour-card button')
                            nxt = btns[-1] if btns else None
                        if not nxt:
                            tour['steps'].append('no next button'); break
                        try:
                            nxt.click(timeout=3000)
                        except Exception as exc:
                            tour['steps'].append('click failed: ' + str(exc)[:160]); break
                info['tour'] = tour
                info['errors'] = list(dict.fromkeys(errors))
                result[key] = info
                ctx.close()
        browser.close()
    json.dump(result, open(f'{OUT}/report.json', 'w'), indent=1)
    print(json.dumps(result, indent=1)[:12000])


if __name__ == '__main__':
    run()
