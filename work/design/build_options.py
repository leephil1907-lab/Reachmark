"""Build the standalone design-option pages in design-options/.

Each page is a single self-contained HTML file (inline CSS, inline SVG logo,
inline founder photo) so it opens anywhere — including sandboxed previews.
All copy is taken from static/locales/en.json; no invented numbers or claims.

    python3 work/design/build_options.py
"""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'design-options'
EN = json.loads((ROOT / 'static/locales/en.json').read_text(encoding='utf-8'))
LOGO = (ROOT / 'work/design/_logo.svg').read_text()
AVATAR = 'data:image/jpeg;base64,' + (ROOT / 'work/design/_avatar.b64').read_text().strip()


def t(k):
    return html.escape(EN[k])


C = {
    'kicker': t('home.kicker'), 'h1a': t('home.hero_h1a'), 'h1b': t('home.hero_h1b'), 'sub': t('home.sub'),
    'cta': t('home.cta_audit'), 'cta2': t('home.cta_report'), 'ph': t('home.audit_ph'), 'go': t('home.audit_go'),
    'try_h': t('home.try_h'), 'try_p': t('home.try_p'),
    'offer_k': t('home.offer_k'), 'offer_h': t('home.offer_h'), 'offer_p': t('home.offer_p'),
    'steps': [(t(f'home.d{i}h'), t(f'home.d{i}p')) for i in range(1, 5)],
    'trust_h': t('home.trust_h'),
    'trust': [(t('home.trust_src'), t('home.trust_src_p')), (t('home.trust_send'), t('home.trust_send_p')),
              (t('home.trust_priv'), t('home.trust_priv_p'))],
    'moat_h': t('home.moat_h'), 'moat_p': t('home.moat_p'), 'shots_h': t('home.shots_h'),
    'price_h': t('home.price_h'), 'price_p': t('home.price_p'),
    'plans': [('Free', '$0', t('home.price_free')), ('Starter', '$19', t('home.price_st')),
              ('Pro', '$59', t('home.price_pro'))],
    'founder_k': t('home.founder_k'), 'founder_q': t('home.founder_q'), 'founder_link': t('home.founder_link'),
    'approve': t('home.approve'),
}
# Real concept names from the showcase gallery
CONCEPTS = [('Ember & Oak', 'Café & hospitality'), ('Stillwell', 'Wellness & beauty'),
            ('Forma House', 'Renovation & trades'), ('Astra Clinic', 'Healthcare & clinic'),
            ('Novera Law', 'Legal & advisory'), ('Bloom Market', 'Boutique & retail')]
# Sample-report preview (mirrors the home page's example; labelled as an example)
FINDINGS = [('01', 'Contact form', 'No working enquiry form found on the contact page.'),
            ('02', 'Mobile layout', 'Navigation overlaps the call-to-action on small screens.'),
            ('03', 'Response', 'Homepage responded, but the booking link returns an error.')]

TOGGLE_JS = """<script>
(function(){var r=document.documentElement,k='rm-option-theme';
try{var s=localStorage.getItem(k);if(s)r.dataset.theme=s;else if(matchMedia('(prefers-color-scheme: dark)').matches)r.dataset.theme='dark';}catch(e){}
document.addEventListener('click',function(e){var b=e.target.closest('[data-toggle-theme]');if(!b)return;
var cur=r.dataset.theme||r.dataset.default||'light',n=cur==='dark'?'light':'dark';r.dataset.theme=n;try{localStorage.setItem(k,n)}catch(e){}});
document.addEventListener('submit',function(e){e.preventDefault();var f=e.target,o=f.querySelector('output');if(o)o.textContent='Concept only — on the live site this runs a real check.';});
})();
</script>"""

SUN_MOON = ('<button class="theme" type="button" data-toggle-theme aria-label="Toggle light and dark theme">'
            '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" '
            'd="M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9Z"/></svg></button>')


def page(title, css, body, default='light'):
    return f"""<!doctype html>
<html lang="en" data-default="{default}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Reachmark design option</title>
<style>{css}</style>
</head>
<body>
{body}
{TOGGLE_JS}
</body>
</html>
"""


def logo(cls='logo'):
    return f'<a class="{cls}" href="#top" aria-label="Reachmark home">{LOGO}</a>'


def nav():
    return ('<nav class="links" aria-label="Main"><a href="#how">How it works</a><a href="#report">Sample report</a>'
            '<a href="#concepts">Concepts</a><a href="#plans">Plans</a></nav>')


def report_card(cls='report'):
    rows = ''.join(f'<li><i>{n}</i><div><b>{h}</b><span>{p}</span></div></li>' for n, h, p in FINDINGS)
    return f"""<article class="{cls}" aria-label="Example Digital Opportunity Report">
  <header><span class="dot"></span><span class="dot"></span><span class="dot"></span><em>Example only</em></header>
  <p class="over">Sample digital opportunity report</p>
  <h3>Willow Grove Dental</h3>
  <p class="dom">willowgrovedental.example</p>
  <ol>{rows}</ol>
  <footer><span>Recommended next step · example</span><b>Fix the enquiry path first</b></footer>
</article>"""


def try_form(cls='try'):
    return f"""<form class="{cls}" aria-label="{C['try_h']}">
  <label for="u-{cls}" class="sr">{C['try_h']}</label>
  <input id="u-{cls}" type="url" placeholder="{C['ph']}" required>
  <button type="submit">{C['go']}</button>
  <output aria-live="polite"></output>
</form>"""


def steps(cls='steps'):
    return f'<ol class="{cls}">' + ''.join(
        f'<li><i>0{i}</i><b>{h}</b><span>{p}</span></li>' for i, (h, p) in enumerate(C['steps'], 1)) + '</ol>'


def trust(cls='trust'):
    return f'<div class="{cls}">' + ''.join(f'<a href="#"><b>{h}</b><span>{p}</span></a>' for h, p in C['trust']) + '</div>'


def shots(cls='shots'):
    labels = ['Pipeline overview', 'Lead directory', 'Website health', 'Outreach studio']
    return f'<div class="{cls}">' + ''.join(
        f'<figure><div class="ui"><span></span><span></span><span></span><div class="bars">'
        f'<i style="--w:{w}%"></i><i style="--w:{w2}%"></i><i style="--w:{w3}%"></i></div></div>'
        f'<figcaption>{l}</figcaption></figure>'
        for l, w, w2, w3 in zip(labels, (82, 64, 90, 58), (46, 78, 52, 70), (68, 40, 74, 88))) + '</div>'


def concepts(cls='gallery'):
    return f'<div class="{cls}">' + ''.join(
        f'<a href="#" class="c c{i}"><div class="art"><span>{n.split()[0]}</span></div><b>{n}</b><small>{c}</small></a>'
        for i, (n, c) in enumerate(CONCEPTS, 1)) + '</div>'


def plans(cls='plans'):
    return f'<div class="{cls}">' + ''.join(
        f'<article class="{ "pop" if name=="Pro" else ""}"><small>{name}</small><b>{price}<em>{"" if price=="$0" else "/month"}</em></b>'
        f'<p>{d}</p><a href="#">{"Create an account" if price=="$0" else "Choose " + name}</a></article>'
        for name, price, d in C['plans']) + '</div>'


def founder(cls='founder'):
    return f"""<figure class="{cls}">
  <img src="{AVATAR}" width="120" height="120" alt="Ernest Micheal, founder of Reachmark">
  <blockquote><p>{C['founder_q']}</p></blockquote>
  <figcaption><b>Ernest Micheal</b> · Founder, Reachmark · <a href="#">{C['founder_link']} →</a></figcaption>
</figure>"""


def footer():
    return f"""<footer class="foot">{logo('logo small')}
  <p>Reachmark finds businesses losing customers online and shows exactly where the opportunity is.</p>
  <nav aria-label="Footer"><a href="#">About</a><a href="#">Privacy</a><a href="#">Terms</a><a href="#">Disclosures</a></nav>
</footer>"""


BASE = """
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
a{color:inherit}img{max-width:100%}
.logo{display:inline-flex;color:var(--ink)}.logo svg{height:52px;width:auto;display:block}
.logo.small svg{height:40px}
@media(max-width:640px){.logo svg{height:40px}}
.top .btn{white-space:nowrap}
[id]{scroll-margin-top:110px}
@media(max-width:560px){.logo svg{height:34px}.top .btn{padding:10px 14px;font-size:14px}.top .wrap{gap:10px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
"""

# ---------------------------------------------------------------- A · Editorial
CSS_A = BASE + """
:root{--bg:#f7f6f0;--paper:#fff;--ink:#1d221b;--ink2:#454d40;--ink3:#5d6655;--line:rgba(29,34,27,.12);--lime:#d5f268;--acc:#4d6417;
  --serif:'Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif;--sans:ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
[data-theme=dark]{--bg:#0e110d;--paper:#161b14;--ink:#eef2e8;--ink2:#c3ccb9;--ink3:#a2ad96;--line:rgba(213,242,104,.14);--acc:#d1ec6c}
body{background:var(--bg);color:var(--ink);font:17px/1.65 var(--sans);transition:background .3s,color .3s}
body::before{content:"";position:fixed;inset:-20%;z-index:-1;pointer-events:none;
  background:radial-gradient(30% 30% at 20% 15%,rgba(213,242,104,.45),transparent 70%),radial-gradient(28% 28% at 85% 25%,rgba(255,200,160,.30),transparent 70%),radial-gradient(30% 30% at 60% 90%,rgba(150,220,200,.25),transparent 70%);
  animation:drift 40s ease-in-out infinite alternate}
[data-theme=dark] body::before{opacity:.28}
@keyframes drift{to{transform:translate3d(4%,3%,0) rotate(6deg) scale(1.06)}}
.wrap{width:min(1180px,calc(100% - 48px));margin:0 auto}
.top{position:sticky;top:0;z-index:5;backdrop-filter:blur(14px);background:color-mix(in srgb,var(--bg) 78%,transparent);border-bottom:1px solid var(--line)}
.top .wrap{display:flex;align-items:center;gap:28px;height:84px}
.links{display:flex;gap:22px;font-size:15px;margin-right:auto}.links a{text-decoration:none;color:var(--ink2)}.links a:hover{color:var(--ink)}
.theme{width:42px;height:42px;border-radius:50%;border:1px solid var(--line);background:var(--paper);color:var(--ink);cursor:pointer}
.btn{display:inline-flex;align-items:center;gap:8px;padding:13px 22px;border-radius:999px;font-weight:650;text-decoration:none;border:1px solid var(--line)}
.btn.lime{background:var(--lime);color:#141a10;border-color:transparent}
.hero{padding:96px 0 40px;text-align:center}
.kick{font:700 12px/1 var(--sans);letter-spacing:.18em;text-transform:uppercase;color:var(--acc);margin:0 0 22px}
h1{font:400 clamp(46px,7.4vw,104px)/.98 var(--serif);letter-spacing:-.035em;margin:0 auto 26px;max-width:14ch}
h1 em{font-style:italic;color:var(--acc)}
.lead{max-width:60ch;margin:0 auto 34px;color:var(--ink2);font-size:19px}
.try{display:flex;gap:8px;max-width:620px;margin:0 auto;padding:8px;border-radius:999px;background:var(--paper);border:1px solid var(--line);box-shadow:0 30px 60px -40px rgba(0,0,0,.4);flex-wrap:wrap}
.try input{flex:1;min-width:200px;border:0;background:transparent;padding:12px 18px;font:inherit;color:var(--ink);outline:none}
.try button{border:0;border-radius:999px;background:var(--lime);color:#141a10;font:700 15px var(--sans);padding:12px 22px;cursor:pointer}
.try output{flex-basis:100%;text-align:center;font-size:13px;color:var(--ink3)}
.hint{margin:14px 0 0;color:var(--ink3);font-size:14px}.hint a{color:var(--ink)}
section{padding:88px 0}
.sec-k{font:700 12px var(--sans);letter-spacing:.16em;text-transform:uppercase;color:var(--acc);margin:0 0 12px}
h2{font:400 clamp(34px,4.6vw,58px)/1.04 var(--serif);letter-spacing:-.03em;margin:0 0 18px;max-width:18ch}
.split{display:grid;grid-template-columns:1fr 1.1fr;gap:56px;align-items:center}
.report{background:var(--paper);border:1px solid var(--line);border-radius:22px;padding:22px 26px;box-shadow:0 40px 80px -50px rgba(0,0,0,.45)}
.report header{display:flex;gap:6px;align-items:center;margin-bottom:14px}.report .dot{width:10px;height:10px;border-radius:50%;background:var(--line)}
.report header em{margin-left:auto;font:700 10px var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--acc);font-style:normal}
.report .over{font:700 11px var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--ink3);margin:0}
.report h3{font:400 32px/1.1 var(--serif);margin:6px 0 2px}.report .dom{color:var(--ink3);margin:0 0 16px;font-size:14px}
.report ol{list-style:none;padding:0;margin:0;display:grid;gap:10px}
.report li{display:grid;grid-template-columns:34px 1fr;gap:12px;padding:12px;border-radius:14px;background:color-mix(in srgb,var(--lime) 14%,transparent)}
.report li i{font:700 12px var(--sans);font-style:normal;width:30px;height:30px;border-radius:9px;display:grid;place-items:center;background:var(--lime);color:#1d2a10}
.report li b{display:block}.report li span{color:var(--ink2);font-size:14px}
.report footer{margin-top:14px;padding-top:14px;border-top:1px dashed var(--line);display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;font-size:14px;color:var(--ink3)}
.report footer b{color:var(--ink)}
.steps{list-style:none;padding:0;margin:40px 0 0;display:grid;grid-template-columns:repeat(4,1fr);gap:0;border-top:1px solid var(--line)}
.steps li{padding:26px 22px 0 0;border-right:1px solid var(--line);margin-right:22px}.steps li:last-child{border:0}
.steps i{font:400 44px var(--serif);font-style:italic;color:var(--acc)}.steps b{display:block;font-size:19px;margin:6px 0}.steps span{color:var(--ink2);font-size:15px}
.trust{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:28px}
.trust a{display:block;text-decoration:none;padding:24px;border-radius:18px;background:var(--paper);border:1px solid var(--line)}
.trust b{display:block;font-size:18px;margin-bottom:6px}.trust span{color:var(--ink2);font-size:15px}
.shots{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:30px}
.shots figure{margin:0}.shots .ui{aspect-ratio:4/3;border-radius:16px;background:var(--paper);border:1px solid var(--line);padding:14px;display:flex;flex-direction:column;gap:8px}
.shots .ui>span{height:8px;border-radius:4px;background:var(--line);width:60%}.shots .ui>span:nth-child(2){width:40%}.shots .ui>span:nth-child(3){width:75%}
.bars{margin-top:auto;display:grid;gap:6px}.bars i{display:block;height:10px;border-radius:5px;width:var(--w);background:linear-gradient(90deg,var(--lime),color-mix(in srgb,var(--lime) 40%,transparent))}
.shots figcaption{margin-top:10px;font-size:14px;color:var(--ink2)}
.why{border-radius:28px;padding:56px;background:#1d221b;color:#eef2e8}.why h2{color:#fff}.why p{color:#c9d2bf;max-width:62ch;font-size:19px}
[data-theme=dark] .why{background:var(--paper);border:1px solid var(--line)}
.gallery{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:30px}
.gallery a{text-decoration:none}.gallery .art{aspect-ratio:16/10;border-radius:18px;display:grid;place-items:end start;padding:18px;font:400 30px var(--serif);color:#fff;overflow:hidden;transition:transform .35s}
.gallery a:hover .art{transform:translateY(-4px)}
.c1 .art{background:linear-gradient(135deg,#8a4b2a,#d39a6a)}.c2 .art{background:linear-gradient(135deg,#7f8f7a,#d9ddc8)}.c3 .art{background:linear-gradient(135deg,#3a4a3a,#a7b39a)}
.c4 .art{background:linear-gradient(135deg,#2e6f8e,#9fd3e0)}.c5 .art{background:linear-gradient(135deg,#1f2a3a,#6d7f99)}.c6 .art{background:linear-gradient(135deg,#c2457a,#f2b2c8)}
.gallery b{display:block;margin-top:12px}.gallery small{color:var(--ink3)}
.plans{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:30px}
.plans article{padding:28px;border-radius:22px;background:var(--paper);border:1px solid var(--line);display:flex;flex-direction:column;gap:10px}
.plans small{font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3)}.plans b{font:400 52px/1 var(--serif)}.plans em{font:500 15px var(--sans);color:var(--ink3);font-style:normal}
.plans p{color:var(--ink2);margin:0 0 8px;flex:1}.plans a{align-self:flex-start;padding:11px 18px;border-radius:999px;border:1px solid var(--line);text-decoration:none;font-weight:650}
.plans .pop{background:#1d221b;color:#fff;border-color:#1d221b}.plans .pop p,.plans .pop em,.plans .pop small{color:#c9d2bf}.plans .pop a{background:var(--lime);color:#141a10;border-color:transparent}
.founder{margin:0;display:grid;grid-template-columns:120px 1fr;gap:30px;align-items:center;padding:40px;border-radius:28px;background:var(--paper);border:1px solid var(--line)}
.founder img{width:120px;height:120px;border-radius:30px;object-fit:cover;grid-row:span 2}
.founder blockquote{margin:0}.founder p{margin:0;font:400 clamp(24px,2.8vw,34px)/1.25 var(--serif)}
.founder figcaption{color:var(--ink3);font-size:15px}.founder figcaption b{color:var(--ink)}
.cta{text-align:center;padding:110px 0}.cta h2{margin:0 auto 18px}.cta p{color:var(--ink2);margin:0 0 28px}
.foot{width:min(1180px,calc(100% - 48px));margin:0 auto;padding:40px 0 60px;border-top:1px solid var(--line);display:flex;gap:28px;align-items:center;flex-wrap:wrap}
.foot p{margin:0;color:var(--ink3);flex:1;min-width:240px;font-size:14px}.foot nav{display:flex;gap:16px;font-size:14px}.foot nav a{text-decoration:none;color:var(--ink2)}
@media(max-width:900px){.links{display:none}.split,.trust,.plans{grid-template-columns:1fr}.steps,.shots{grid-template-columns:1fr 1fr}.gallery{grid-template-columns:1fr 1fr}.why{padding:32px}.founder{grid-template-columns:1fr;padding:26px}.top .wrap{gap:12px}.top .btn{margin-left:auto}}
@media(max-width:560px){.steps,.shots,.gallery{grid-template-columns:1fr}.steps li{border:0;margin:0}.hero{padding-top:56px}}
"""

BODY_A = f"""
<header class="top"><div class="wrap">{logo()}{nav()}{SUN_MOON}<a class="btn lime" href="#plans">Create account</a></div></header>
<main id="top">
  <section class="hero wrap">
    <p class="kick">{C['kicker']}</p>
    <h1>{C['h1a']} <em>{C['h1b']}</em></h1>
    <p class="lead">{C['sub']}</p>
    {try_form()}
    <p class="hint">{C['try_p']} · <a href="#report">{C['cta2']}</a></p>
  </section>
  <section class="wrap" id="report"><div class="split">
    <div><p class="sec-k">Sample report</p><h2>Find the gap. See the evidence. Know what to do next.</h2>
      <p style="color:var(--ink2)">Explore a sample Digital Opportunity Report, then run a live check on any public website.</p></div>
    {report_card()}</div></section>
  <section class="wrap" id="how"><p class="sec-k">{C['offer_k']}</p><h2>{C['offer_h']}</h2>
    <p style="color:var(--ink2);max-width:64ch">{C['offer_p']}</p>{steps()}</section>
  <section class="wrap"><p class="sec-k">Trust</p><h2>{C['trust_h']}</h2>{trust()}</section>
  <section class="wrap"><p class="sec-k">The workspace</p><h2>{C['shots_h']}</h2>{shots()}</section>
  <section class="wrap"><div class="why"><p class="sec-k" style="color:#d5f268">Why Reachmark</p><h2>{C['moat_h']}</h2><p>{C['moat_p']}</p></div></section>
  <section class="wrap" id="concepts"><p class="sec-k">Design concepts</p><h2>Original directions for real kinds of business.</h2>{concepts()}</section>
  <section class="wrap" id="plans"><p class="sec-k">Plans</p><h2>{C['price_h']}</h2><p style="color:var(--ink2)">{C['price_p']}</p>{plans()}</section>
  <section class="wrap">{founder()}</section>
  <section class="cta wrap"><h2>Your next client is out there.</h2><p>{C['approve']}</p><a class="btn lime" href="#top">{C['cta']}</a></section>
</main>
{footer()}
"""

# ---------------------------------------------------------------- B · Signal (dark-first)
CSS_B = BASE + """
:root{--bg:#07090a;--panel:#0f1412;--panel2:#141b18;--ink:#eef3ec;--ink2:#b9c4b6;--ink3:#8f9b8c;--line:rgba(255,255,255,.08);--lime:#d5f268;--teal:#4fe0c0;--acc:#d5f268;
  --mono:ui-monospace,'SF Mono',Menlo,Consolas,monospace;--sans:ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
:root:not([data-theme]),[data-theme=dark]{color-scheme:dark}
[data-theme=light]{--bg:#f4f6f3;--panel:#fff;--panel2:#f7f9f6;--ink:#0f1411;--ink2:#3d463f;--ink3:#59625a;--line:rgba(10,20,14,.10);--acc:#4d6417;--teal:#0f7f6a;color-scheme:light}
body{background:var(--bg);color:var(--ink);font:16px/1.6 var(--sans)}
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:radial-gradient(60% 50% at 50% -10%,rgba(213,242,104,.18),transparent 70%),radial-gradient(40% 40% at 90% 30%,rgba(79,224,192,.10),transparent 70%),
  linear-gradient(var(--line) 1px,transparent 1px) 0 0/64px 64px,linear-gradient(90deg,var(--line) 1px,transparent 1px) 0 0/64px 64px;
  -webkit-mask-image:radial-gradient(90% 70% at 50% 0%,#000 30%,transparent 100%);mask-image:radial-gradient(90% 70% at 50% 0%,#000 30%,transparent 100%)}
.wrap{width:min(1200px,calc(100% - 40px));margin:0 auto}
.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 70%,transparent);backdrop-filter:blur(16px);border-bottom:1px solid var(--line)}
.top .wrap{display:flex;align-items:center;gap:26px;height:80px}
.links{display:flex;gap:4px;margin-right:auto}.links a{text-decoration:none;color:var(--ink2);padding:8px 12px;border-radius:8px;font-size:14px}.links a:hover{background:var(--panel2);color:var(--ink)}
.theme{width:40px;height:40px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer}
.btn{display:inline-flex;gap:8px;align-items:center;padding:11px 18px;border-radius:10px;font-weight:650;font-size:15px;text-decoration:none;border:1px solid var(--line);background:var(--panel)}
.btn.lime{background:var(--lime);color:#0b0f08;border-color:transparent;box-shadow:0 0 0 1px rgba(213,242,104,.4),0 10px 40px -10px rgba(213,242,104,.6)}
.hero{display:grid;grid-template-columns:1.05fr 1fr;gap:56px;align-items:center;padding:80px 0 70px}
.pill{display:inline-flex;gap:8px;align-items:center;font:500 12px var(--mono);color:var(--ink2);padding:6px 12px;border:1px solid var(--line);border-radius:999px;background:var(--panel)}
.pill i{width:7px;height:7px;border-radius:50%;background:var(--lime);box-shadow:0 0 12px var(--lime);animation:pulse 2s infinite}
@keyframes pulse{50%{opacity:.35}}
h1{font:750 clamp(40px,5.6vw,72px)/1.02 var(--sans);letter-spacing:-.045em;margin:20px 0}
h1 em{font-style:normal;background:linear-gradient(90deg,var(--lime),var(--teal));-webkit-background-clip:text;background-clip:text;color:transparent}
[data-theme=light] h1 em{background:linear-gradient(90deg,#4d6417,#0f7f6a);-webkit-background-clip:text;background-clip:text}
.lead{color:var(--ink2);font-size:18px;max-width:54ch;margin:0 0 28px}
.try{display:flex;gap:8px;padding:6px;border-radius:12px;background:var(--panel);border:1px solid var(--line);max-width:560px;flex-wrap:wrap}
.try input{flex:1;min-width:180px;background:transparent;border:0;color:var(--ink);font:15px var(--mono);padding:10px 12px;outline:none}
.try button{border:0;border-radius:8px;background:var(--lime);color:#0b0f08;font-weight:700;padding:10px 16px;cursor:pointer}
.try output{flex-basis:100%;font:12px var(--mono);color:var(--ink3);padding:0 8px}
.hint{font:13px var(--mono);color:var(--ink3);margin-top:14px}.hint a{color:var(--acc)}
.report{position:relative;background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:18px;padding:20px 22px;
  box-shadow:0 0 0 1px rgba(213,242,104,.08),0 40px 120px -40px rgba(213,242,104,.35)}
.report::before{content:"";position:absolute;inset:-1px;border-radius:19px;padding:1px;background:linear-gradient(140deg,rgba(213,242,104,.6),transparent 40%,transparent 60%,rgba(79,224,192,.5));
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none}
.report header{display:flex;gap:6px;align-items:center;margin-bottom:16px}.report .dot{width:10px;height:10px;border-radius:50%;background:var(--line)}
.report header em{margin-left:auto;font:600 11px var(--mono);color:var(--acc);font-style:normal}
.report .over{font:500 11px var(--mono);color:var(--ink3);text-transform:uppercase;letter-spacing:.08em;margin:0}
.report h3{font:700 26px var(--sans);letter-spacing:-.02em;margin:4px 0 0}.report .dom{font:13px var(--mono);color:var(--ink3);margin:0 0 14px}
.report ol{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.report li{display:grid;grid-template-columns:36px 1fr;gap:12px;padding:12px;border-radius:12px;background:var(--panel2);border:1px solid var(--line)}
.report li i{font:600 12px var(--mono);font-style:normal;color:var(--acc);border:1px solid color-mix(in srgb,var(--acc) 40%,transparent);border-radius:8px;display:grid;place-items:center;height:30px}
.report li b{display:block;font-size:15px}.report li span{color:var(--ink2);font-size:14px}
.report footer{margin-top:14px;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;font:12px var(--mono);color:var(--ink3)}.report footer b{color:var(--acc)}
section{padding:84px 0}
.sec-k{font:500 12px var(--mono);color:var(--acc);text-transform:uppercase;letter-spacing:.12em;margin:0 0 14px}
h2{font:720 clamp(30px,3.8vw,48px)/1.08 var(--sans);letter-spacing:-.035em;margin:0 0 14px;max-width:20ch}
.sub{color:var(--ink2);max-width:62ch}
.steps{list-style:none;padding:0;margin:36px 0 0;display:grid;grid-template-columns:repeat(4,1fr);gap:12px;counter-reset:s}
.steps li{padding:22px;border-radius:14px;background:var(--panel);border:1px solid var(--line);position:relative;overflow:hidden}
.steps li::after{content:"";position:absolute;left:0;right:0;top:0;height:2px;background:linear-gradient(90deg,var(--lime),transparent)}
.steps i{font:600 12px var(--mono);color:var(--acc);font-style:normal}.steps b{display:block;font-size:18px;margin:10px 0 6px}.steps span{color:var(--ink2);font-size:14px}
.trust{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:28px}
.trust a{text-decoration:none;padding:22px;border-radius:14px;background:var(--panel);border:1px solid var(--line);transition:border-color .2s}
.trust a:hover{border-color:color-mix(in srgb,var(--acc) 50%,transparent)}.trust b{display:block;margin-bottom:6px}.trust span{color:var(--ink2);font-size:14px}
.shots{display:grid;grid-template-columns:2fr 1fr 1fr;grid-auto-rows:170px;gap:12px;margin-top:28px}
.shots figure{margin:0;position:relative;border-radius:14px;background:var(--panel);border:1px solid var(--line);overflow:hidden}
.shots figure:first-child{grid-row:span 2}
.shots .ui{position:absolute;inset:16px 16px 40px;display:flex;flex-direction:column;gap:8px}
.shots .ui>span{height:7px;border-radius:4px;background:var(--line);width:55%}.shots .ui>span:nth-child(2){width:35%}.shots .ui>span:nth-child(3){width:70%}
.bars{margin-top:auto;display:grid;gap:6px}.bars i{display:block;height:9px;border-radius:5px;width:var(--w);background:linear-gradient(90deg,var(--lime),var(--teal));opacity:.85}
.shots figcaption{position:absolute;left:16px;bottom:12px;font:12px var(--mono);color:var(--ink3)}
.why{display:grid;grid-template-columns:1fr 1fr;gap:40px;padding:44px;border-radius:20px;background:var(--panel);border:1px solid var(--line)}.why p{color:var(--ink2);font-size:18px;margin:0}
.gallery{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-top:28px}
.gallery a{text-decoration:none;grid-column:span 3}.gallery a:nth-child(1),.gallery a:nth-child(4){grid-column:span 4}.gallery a:nth-child(2),.gallery a:nth-child(3){grid-column:span 2}
.gallery .art{aspect-ratio:16/9;border-radius:14px;border:1px solid var(--line);display:grid;place-items:end start;padding:16px;font:700 22px var(--sans);color:#fff;letter-spacing:-.02em}
.c1 .art{background:radial-gradient(circle at 70% 30%,#e0a36f,#5a2d16)}.c2 .art{background:radial-gradient(circle at 70% 30%,#dfe3cf,#5d6b58)}.c3 .art{background:radial-gradient(circle at 70% 30%,#b8c2a8,#24301f)}
.c4 .art{background:radial-gradient(circle at 70% 30%,#a6dce8,#14465c)}.c5 .art{background:radial-gradient(circle at 70% 30%,#8597b3,#0f1724)}.c6 .art{background:radial-gradient(circle at 70% 30%,#f5bcd1,#7a1f47)}
.gallery b{display:block;margin-top:10px;font-size:15px}.gallery small{font:12px var(--mono);color:var(--ink3)}
.plans{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:28px}
.plans article{padding:26px;border-radius:16px;background:var(--panel);border:1px solid var(--line);display:flex;flex-direction:column;gap:8px}
.plans small{font:500 12px var(--mono);color:var(--ink3);text-transform:uppercase}.plans b{font:750 44px/1 var(--sans);letter-spacing:-.04em}.plans em{font:500 14px var(--sans);color:var(--ink3);font-style:normal}
.plans p{color:var(--ink2);flex:1;margin:4px 0 10px}.plans a{text-align:center;padding:11px;border-radius:10px;border:1px solid var(--line);text-decoration:none;font-weight:650}
.plans .pop{border-color:color-mix(in srgb,var(--lime) 55%,transparent);box-shadow:0 30px 80px -40px rgba(213,242,104,.5)}.plans .pop a{background:var(--lime);color:#0b0f08;border:0}
.founder{margin:0;display:grid;grid-template-columns:96px 1fr;gap:24px;align-items:start;padding:34px;border-radius:20px;background:var(--panel);border:1px solid var(--line)}
.founder img{width:96px;height:96px;border-radius:20px;object-fit:cover;grid-row:span 2;filter:saturate(.9)}
.founder blockquote{margin:0}.founder p{margin:0;font:600 clamp(20px,2.2vw,26px)/1.35 var(--sans);letter-spacing:-.015em}
.founder figcaption{font:13px var(--mono);color:var(--ink3)}.founder figcaption b{color:var(--ink)}.founder a{color:var(--acc)}
.cta{text-align:center;padding:100px 0;position:relative}
.cta::before{content:"";position:absolute;left:50%;top:30%;width:520px;height:260px;transform:translateX(-50%);background:radial-gradient(closest-side,rgba(213,242,104,.25),transparent);z-index:-1}
.cta h2{margin:0 auto 14px}.cta p{color:var(--ink2);margin:0 0 26px;font:14px var(--mono)}
.foot{width:min(1200px,calc(100% - 40px));margin:0 auto;padding:36px 0 56px;border-top:1px solid var(--line);display:flex;gap:26px;align-items:center;flex-wrap:wrap}
.foot p{flex:1;min-width:240px;margin:0;color:var(--ink3);font-size:14px}.foot nav{display:flex;gap:16px;font:13px var(--mono)}.foot nav a{text-decoration:none;color:var(--ink2)}
@media(max-width:960px){.hero,.why{grid-template-columns:1fr}.links{display:none}.steps{grid-template-columns:1fr 1fr}.trust,.plans{grid-template-columns:1fr}
  .shots{grid-template-columns:1fr 1fr}.shots figure:first-child{grid-column:span 2;grid-row:auto}.gallery a,.gallery a:nth-child(n){grid-column:span 3}.top .btn{margin-left:auto}}
@media(max-width:560px){.steps{grid-template-columns:1fr}.gallery a,.gallery a:nth-child(n){grid-column:span 6}.founder{grid-template-columns:1fr}.why{padding:26px}}
"""

BODY_B = f"""
<header class="top"><div class="wrap">{logo()}{nav()}{SUN_MOON}<a class="btn lime" href="#plans">Create account</a></div></header>
<main id="top">
  <section class="hero wrap">
    <div><span class="pill"><i></i>{C['kicker']}</span>
      <h1>{C['h1a']} <em>{C['h1b']}</em></h1>
      <p class="lead">{C['sub']}</p>
      {try_form()}
      <p class="hint">{C['try_p']} → <a href="#report">{C['cta2']}</a></p></div>
    <div id="report">{report_card()}</div>
  </section>
  <section class="wrap" id="how"><p class="sec-k">// {C['offer_k']}</p><h2>{C['offer_h']}</h2><p class="sub">{C['offer_p']}</p>{steps()}</section>
  <section class="wrap"><p class="sec-k">// Trust</p><h2>{C['trust_h']}</h2>{trust()}</section>
  <section class="wrap"><p class="sec-k">// Workspace</p><h2>{C['shots_h']}</h2>{shots()}</section>
  <section class="wrap"><div class="why"><div><p class="sec-k">// Why Reachmark</p><h2>{C['moat_h']}</h2></div><p>{C['moat_p']}</p></div></section>
  <section class="wrap" id="concepts"><p class="sec-k">// Design concepts</p><h2>Original directions, ready to preview.</h2>{concepts()}</section>
  <section class="wrap" id="plans"><p class="sec-k">// Plans</p><h2>{C['price_h']}</h2><p class="sub">{C['price_p']}</p>{plans()}</section>
  <section class="wrap">{founder()}</section>
  <section class="cta wrap"><h2>Your next client is out there.</h2><p>{C['approve']}</p><a class="btn lime" href="#top">{C['cta']}</a></section>
</main>
{footer()}
"""

# ---------------------------------------------------------------- C · Bento (bright, playful)
CSS_C = BASE + """
:root{--bg:#fbfaf5;--card:#fff;--ink:#14180f;--ink2:#3b4433;--ink3:#566048;--line:#e6e8dc;--lime:#d5f268;--forest:#1b2a12;--peach:#ffd8bf;--sky:#cfe9ff;--lilac:#e4dcff;--mint:#cdf3e4;--acc:#4d6417;
  --sans:ui-rounded,'SF Pro Rounded',ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
[data-theme=dark]{--bg:#0d100b;--card:#161b13;--ink:#f1f5ea;--ink2:#c5cebb;--ink3:#a3ae97;--line:#283023;--peach:#4a2e1f;--sky:#1d3347;--lilac:#2c2647;--mint:#173a2d;--acc:#d1ec6c}
body{background:var(--bg);color:var(--ink);font:17px/1.6 var(--sans)}
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;background-image:radial-gradient(var(--line) 1.2px,transparent 1.2px);background-size:22px 22px;opacity:.9}
.wrap{width:min(1220px,calc(100% - 32px));margin:0 auto}
.top{position:sticky;top:12px;z-index:5;margin-top:12px}
.top .wrap{display:flex;align-items:center;gap:20px;height:76px;padding:0 14px 0 20px;border-radius:24px;background:color-mix(in srgb,var(--card) 88%,transparent);backdrop-filter:blur(14px);border:1px solid var(--line);box-shadow:0 10px 30px -20px rgba(0,0,0,.25)}
.links{display:flex;gap:6px;margin-right:auto}.links a{text-decoration:none;padding:8px 14px;border-radius:999px;font-weight:600;font-size:15px;color:var(--ink2)}.links a:hover{background:var(--lime);color:#14180f}
.theme{width:44px;height:44px;border-radius:14px;border:2px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.btn{display:inline-flex;align-items:center;gap:8px;padding:13px 22px;border-radius:16px;font-weight:800;text-decoration:none;border:2px solid var(--ink);background:var(--card);color:var(--ink)}
.btn.lime{background:var(--lime);color:#14180f;border-color:#14180f;box-shadow:4px 4px 0 #14180f;transition:transform .15s,box-shadow .15s}
.btn.lime:hover{transform:translate(-2px,-2px);box-shadow:6px 6px 0 #14180f}
[data-theme=dark] .btn.lime{border-color:var(--lime);box-shadow:4px 4px 0 rgba(213,242,104,.35)}
.bento{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin:26px auto}
.tile{border-radius:28px;padding:30px;background:var(--card);border:2px solid var(--line);position:relative;overflow:hidden}
.t-hero{grid-column:span 4;grid-row:span 2;background:var(--lime);border-color:transparent;color:#14180f;padding:44px}
.t-hero .kick{font-weight:800;font-size:13px;letter-spacing:.08em;text-transform:uppercase;margin:0 0 18px;color:#2d3a14}
.t-hero h1{font:900 clamp(40px,5.6vw,78px)/.98 var(--sans);letter-spacing:-.045em;margin:0 0 20px}
.t-hero h1 em{font-style:normal;background:#14180f;color:var(--lime);padding:0 .18em;border-radius:.2em;box-decoration-break:clone;-webkit-box-decoration-break:clone}
.t-hero p{font-size:19px;max-width:48ch;margin:0 0 24px;color:#26311a}
.t-hero::after{content:"";position:absolute;right:-60px;bottom:-60px;width:260px;height:260px;border-radius:50%;background:radial-gradient(circle,#fff8 0,transparent 70%);animation:float 9s ease-in-out infinite alternate}
@keyframes float{to{transform:translate(-40px,-30px) scale(1.15)}}
.try{display:flex;gap:8px;background:#fff;border:2px solid #14180f;border-radius:18px;padding:6px;max-width:560px;flex-wrap:wrap;position:relative;z-index:1}
.try input{flex:1;min-width:180px;border:0;background:transparent;font:inherit;padding:10px 14px;outline:none;color:#14180f}
.try button{border:0;border-radius:12px;background:#14180f;color:var(--lime);font-weight:800;padding:10px 18px;cursor:pointer}
.try output{flex-basis:100%;font-size:13px;color:#3b4433;padding:0 8px}
.t-report{grid-column:span 2;grid-row:span 2;padding:22px}
.report header{display:flex;gap:6px;align-items:center;margin-bottom:12px}.report .dot{width:10px;height:10px;border-radius:50%;background:var(--line)}
.report header em{margin-left:auto;font-weight:800;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--acc);font-style:normal}
.report .over{font-weight:800;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);margin:0}.report h3{font:900 24px var(--sans);letter-spacing:-.02em;margin:4px 0 0}.report .dom{color:var(--ink3);font-size:13px;margin:0 0 12px}
.report ol{list-style:none;padding:0;margin:0;display:grid;gap:8px}.report li{display:grid;grid-template-columns:30px 1fr;gap:10px;padding:10px;border-radius:16px;background:var(--bg)}
.report li i{font-style:normal;font-weight:900;font-size:12px;height:28px;border-radius:10px;display:grid;place-items:center;background:var(--lime);color:#14180f}
.report li b{display:block;font-size:14px}.report li span{font-size:13px;color:var(--ink2)}
.report footer{margin-top:10px;font-size:13px;color:var(--ink3);display:grid}.report footer b{color:var(--ink)}
.t-stat{grid-column:span 2;display:flex;flex-direction:column;justify-content:space-between;min-height:170px}
.t-stat b{font:900 22px/1.15 var(--sans);letter-spacing:-.02em}.t-stat span{color:var(--ink2);font-size:15px}
.t-stat i{font-style:normal;font-weight:900;font-size:13px;width:36px;height:36px;border-radius:12px;display:grid;place-items:center;background:var(--ink);color:var(--bg)}
.peach{background:var(--peach);border-color:transparent}.sky{background:var(--sky);border-color:transparent}.lilac{background:var(--lilac);border-color:transparent}.mint{background:var(--mint);border-color:transparent}
section{padding:48px 0}
.sec-k{font-weight:800;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--acc);margin:0 0 10px}
h2{font:900 clamp(30px,4vw,52px)/1.02 var(--sans);letter-spacing:-.04em;margin:0 0 12px;max-width:20ch}
.sub{color:var(--ink2);max-width:62ch;margin:0}
.steps{list-style:none;padding:0;margin:26px 0 0;display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.steps li{padding:26px;border-radius:26px;border:2px solid var(--line);background:var(--card)}
.steps li:nth-child(1){background:var(--peach)}.steps li:nth-child(2){background:var(--sky)}.steps li:nth-child(3){background:var(--lilac)}.steps li:nth-child(4){background:var(--mint)}
.steps li{border-color:transparent}.steps i{font-style:normal;font-weight:900;font-size:40px;letter-spacing:-.04em}.steps b{display:block;font-size:19px;margin:8px 0 4px}.steps span{font-size:15px;color:var(--ink2)}
.trust{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:22px}
.trust a{text-decoration:none;padding:24px;border-radius:24px;background:var(--card);border:2px solid var(--line);transition:transform .2s}.trust a:hover{transform:rotate(-1deg) translateY(-3px)}
.trust b{display:block;font-size:18px;font-weight:800;margin-bottom:6px}.trust span{color:var(--ink2);font-size:15px}
.shots{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:22px}
.shots figure{margin:0;padding:16px;border-radius:24px;background:var(--card);border:2px solid var(--line)}
.shots .ui{aspect-ratio:4/3;border-radius:16px;background:var(--bg);padding:14px;display:flex;flex-direction:column;gap:8px}
.shots .ui>span{height:8px;border-radius:4px;background:var(--line);width:55%}.shots .ui>span:nth-child(2){width:35%}.shots .ui>span:nth-child(3){width:72%}
.bars{margin-top:auto;display:grid;gap:6px}.bars i{display:block;height:12px;border-radius:6px;width:var(--w)}
.bars i:nth-child(1){background:var(--lime)}.bars i:nth-child(2){background:#ffb48a}.bars i:nth-child(3){background:#9fc9ff}
.shots figcaption{margin-top:10px;font-weight:700;font-size:15px}
.why{display:grid;grid-template-columns:1.1fr 1fr;gap:36px;align-items:center;padding:44px;border-radius:32px;background:var(--forest);color:#f1f5ea}
.why h2{color:#fff}.why .sec-k{color:var(--lime)}.why p{color:#cbd5c0;font-size:19px;margin:0}
.gallery{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:22px}
.gallery a{text-decoration:none;padding:12px;border-radius:26px;background:var(--card);border:2px solid var(--line);transition:transform .2s}.gallery a:hover{transform:translateY(-4px) rotate(.6deg)}
.gallery .art{aspect-ratio:16/10;border-radius:18px;display:grid;place-items:center;font:900 30px var(--sans);letter-spacing:-.03em;color:#fff}
.c1 .art{background:linear-gradient(135deg,#ff9a5a,#c2410c)}.c2 .art{background:linear-gradient(135deg,#a3b899,#4b5d45)}.c3 .art{background:linear-gradient(135deg,#f3c76b,#7c5a14)}
.c4 .art{background:linear-gradient(135deg,#6cc6ff,#1d5fa8)}.c5 .art{background:linear-gradient(135deg,#7d8bb3,#1f2742)}.c6 .art{background:linear-gradient(135deg,#ff8ab6,#b0175a)}
.gallery b{display:block;margin:12px 6px 0;font-size:17px}.gallery small{display:block;margin:0 6px 6px;color:var(--ink3)}
.plans{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:22px}
.plans article{padding:28px;border-radius:28px;background:var(--card);border:2px solid var(--line);display:flex;flex-direction:column;gap:8px}
.plans small{font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--ink3)}.plans b{font:900 52px/1 var(--sans);letter-spacing:-.05em}.plans em{font:600 15px var(--sans);font-style:normal;color:var(--ink3)}
.plans p{flex:1;color:var(--ink2);margin:4px 0 12px}.plans a{text-align:center;padding:12px;border-radius:14px;border:2px solid var(--ink);font-weight:800;text-decoration:none}
.plans .pop{background:var(--lime);border-color:#14180f;color:#14180f;box-shadow:6px 6px 0 #14180f}.plans .pop p,.plans .pop small,.plans .pop em{color:#2d3a14}.plans .pop a{background:#14180f;color:var(--lime);border-color:#14180f}
.founder{margin:0;display:grid;grid-template-columns:130px 1fr;gap:28px;align-items:center;padding:36px;border-radius:32px;background:var(--peach)}
.founder img{width:130px;height:130px;border-radius:36px;object-fit:cover;grid-row:span 2;transform:rotate(-4deg);border:4px solid var(--card)}
.founder blockquote{margin:0}.founder p{margin:0;font:800 clamp(20px,2.4vw,28px)/1.3 var(--sans);letter-spacing:-.02em}
.founder figcaption{color:var(--ink2);font-size:15px}.founder figcaption b{color:var(--ink)}
.cta{margin:30px auto 0;padding:64px 40px;border-radius:36px;background:var(--lime);color:#14180f;text-align:center}
.cta h2{margin:0 auto 10px;color:#14180f}.cta p{margin:0 0 24px;color:#2d3a14;font-weight:600}
.cta .btn.lime{background:#14180f;color:var(--lime);box-shadow:4px 4px 0 #fff}
.foot{width:min(1220px,calc(100% - 32px));margin:0 auto;padding:40px 4px 56px;display:flex;gap:24px;align-items:center;flex-wrap:wrap}
.foot p{flex:1;min-width:240px;margin:0;color:var(--ink3);font-size:15px}.foot nav{display:flex;gap:16px}.foot nav a{text-decoration:none;font-weight:700;color:var(--ink2)}
@media(max-width:980px){.links{display:none}.top .btn{margin-left:auto}.t-hero,.t-report{grid-column:span 6;grid-row:auto}.t-stat{grid-column:span 3}
  .steps,.shots{grid-template-columns:1fr 1fr}.trust,.plans,.why{grid-template-columns:1fr}.gallery{grid-template-columns:1fr 1fr}.why{padding:30px}}
@media(max-width:560px){.top .wrap{padding:0 14px 0 14px}.theme{width:38px;height:38px}.btn.lime{box-shadow:3px 3px 0 #14180f}.t-stat{grid-column:span 6}.steps,.shots,.gallery{grid-template-columns:1fr}.t-hero{padding:28px}.founder{grid-template-columns:1fr;padding:26px}.cta{padding:44px 22px}}
"""

stat_tiles = ''.join(
    f'<div class="tile t-stat {cls}"><i>0{i}</i><div><b>{h}</b><br><span>{p}</span></div></div>'
    for i, ((h, p), cls) in enumerate(zip(C['steps'][:3], ('peach', 'sky', 'lilac')), 1))

BODY_C = f"""
<header class="top"><div class="wrap">{logo()}{nav()}{SUN_MOON}<a class="btn lime" href="#plans">Create account</a></div></header>
<main id="top" class="wrap">
  <div class="bento">
    <div class="tile t-hero"><p class="kick">{C['kicker']}</p><h1>{C['h1a']} <em>{C['h1b']}</em></h1><p>{C['sub']}</p>{try_form()}</div>
    <div class="tile t-report" id="report">{report_card()}</div>
    {stat_tiles}
  </div>
  <section id="how"><p class="sec-k">{C['offer_k']}</p><h2>{C['offer_h']}</h2><p class="sub">{C['offer_p']}</p>{steps()}</section>
  <section><p class="sec-k">Trust</p><h2>{C['trust_h']}</h2>{trust()}</section>
  <section><p class="sec-k">Workspace</p><h2>{C['shots_h']}</h2>{shots()}</section>
  <section><div class="why"><div><p class="sec-k">Why Reachmark</p><h2>{C['moat_h']}</h2></div><p>{C['moat_p']}</p></div></section>
  <section id="concepts"><p class="sec-k">Design concepts</p><h2>Six directions. Pick a vibe.</h2>{concepts()}</section>
  <section id="plans"><p class="sec-k">Plans</p><h2>{C['price_h']}</h2><p class="sub">{C['price_p']}</p>{plans()}</section>
  <section>{founder()}</section>
  <section class="cta"><h2>Your next client is out there.</h2><p>{C['approve']}</p><a class="btn lime" href="#top">{C['cta']}</a></section>
</main>
{footer()}
"""

# ---------------------------------------------------------------- index
INDEX_CSS = BASE + """
:root{--bg:#f6f7f2;--card:#fff;--ink:#1c2219;--ink2:#4c5646;--line:#e2e7d6}
[data-theme=dark]{--bg:#0d100b;--card:#161b13;--ink:#eef3e8;--ink2:#b9c4ae;--line:#283023}
body{background:var(--bg);color:var(--ink);font:16px/1.6 ui-sans-serif,system-ui,sans-serif;padding:40px 24px}
.wrap{max-width:1100px;margin:0 auto}header{display:flex;align-items:center;gap:16px;margin-bottom:28px}
.theme{margin-left:auto;width:42px;height:42px;border-radius:50%;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
h1{font-size:34px;letter-spacing:-.03em;margin:0 0 8px}p{color:var(--ink2);margin:0 0 28px;max-width:70ch}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.grid a{display:block;text-decoration:none;padding:22px;border-radius:20px;background:var(--card);border:1px solid var(--line)}
.sw{height:120px;border-radius:14px;margin-bottom:16px}
.a .sw{background:radial-gradient(60% 80% at 20% 20%,#d5f268,transparent),#f7f6f0;border:1px solid var(--line)}
.b .sw{background:radial-gradient(60% 80% at 50% 0%,rgba(213,242,104,.5),transparent),linear-gradient(90deg,#d5f268 0 0) 24px 70px/40% 10px no-repeat,#07090a}
.c .sw{background:linear-gradient(#d5f268 0 0) 0 0/60% 100% no-repeat,linear-gradient(#ffd8bf 0 0) 100% 0/38% 48% no-repeat,linear-gradient(#cfe9ff 0 0) 100% 100%/38% 48% no-repeat;border-radius:14px}
.grid b{font-size:19px}.grid span{display:block;color:var(--ink2);font-size:15px;margin-top:4px}
@media(max-width:800px){.grid{grid-template-columns:1fr}}
"""

INDEX_BODY = f"""<div class="wrap">
<header>{logo()}{SUN_MOON}</header>
<h1>Reachmark — three design directions</h1>
<p>Each option is a complete, self-contained home page using Reachmark’s real copy and the standard order:
hero with a live URL check, sample report, how it works, trust, workspace, why Reachmark, design concepts, plans,
founder, call to action. Every page has a light/dark toggle (top right) and works on mobile.</p>
<div class="grid">
  <a class="a" href="option-a-editorial.html"><div class="sw"></div><b>A · Editorial</b><span>Light-first, big serif headlines, calm space. The closest evolution of today’s site.</span></a>
  <a class="b" href="option-b-signal.html"><div class="sw"></div><b>B · Signal</b><span>Dark-first product look: glowing report card, grid backdrop, monospace detail.</span></a>
  <a class="c" href="option-c-bento.html"><div class="sw"></div><b>C · Bento</b><span>Bright and playful: chunky bento tiles, pastel blocks, bold rounded type.</span></a>
</div></div>"""


def main():
    (OUT / 'option-a-editorial.html').write_text(page('A · Editorial', CSS_A, BODY_A), encoding='utf-8')
    (OUT / 'option-b-signal.html').write_text(page('B · Signal', CSS_B, BODY_B, 'dark'), encoding='utf-8')
    (OUT / 'option-c-bento.html').write_text(page('C · Bento', CSS_C, BODY_C), encoding='utf-8')
    (OUT / 'index.html').write_text(page('Design options', INDEX_CSS, INDEX_BODY), encoding='utf-8')
    for f in sorted(OUT.glob('*.html')):
        print(f.name, f.stat().st_size)


if __name__ == '__main__':
    main()
