"""Evidence-backed website opportunity scoring for Reachmark discovery leads."""
from __future__ import annotations
import re, socket, time, ipaddress
from urllib.parse import urlparse
import requests

SOCIAL_HOSTS={"facebook.com","instagram.com","linktr.ee","linktree.com","wa.me","whatsapp.com","tiktok.com","x.com","twitter.com"}
BUILDER_HOSTS={"wixsite.com","wix.com","blogspot.com","blogger.com","sites.google.com","wordpress.com","weebly.com","webflow.io","carrd.co","godaddysites.com"}
TIERS=("NO_SITE","SOCIAL_ONLY","FREE_BUILDER","BROKEN","WEAK","OK")
DEFAULT_TIMEOUT=8

def _host(url):
    try:return (urlparse(url if "://" in url else "https://"+url).hostname or "").lower().lstrip("www.")
    except ValueError:return ""

def _social(host): return any(host==x or host.endswith("."+x) for x in SOCIAL_HOSTS)
def _builder(host): return any(host==x or host.endswith("."+x) for x in BUILDER_HOSTS)

def _public(url):
    p=urlparse(url if "://" in url else "https://"+url)
    if p.scheme not in ("http","https") or not p.hostname:return False
    try:
        for info in socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=="https" else 80),type=socket.SOCK_STREAM):
            if not ipaddress.ip_address(info[4][0]).is_global:return False
    except (OSError,ValueError):return False
    return True

def score_website(url, timeout=DEFAULT_TIMEOUT):
    """Return tier, score and quoteable evidence. Network failures are never called proof of a dead site."""
    url=(url or "").strip()
    if not url:return {"tier":"NO_SITE","score":100,"evidence":["No website URL was supplied by the source listing."]}
    host=_host(url)
    if _social(host):return {"tier":"SOCIAL_ONLY","score":85,"evidence":[f"URL belongs to a social/contact host ({host})."]}
    if _builder(host):return {"tier":"FREE_BUILDER","score":70,"evidence":[f"URL is hosted on a common free/builder platform ({host})."]}
    if not _public(url):return {"tier":"BROKEN","score":90,"evidence":["URL failed public-host validation or DNS resolution."]}
    target=url if "://" in url else "https://"+url
    evidence=[]; score=0; started=time.monotonic()
    try:
        r=requests.get(target,headers={"User-Agent":"Reachmark/1.0 website-quality-check"},timeout=timeout,allow_redirects=True,stream=True)
        elapsed=int((time.monotonic()-started)*1000)
        code=r.status_code
        raw=r.raw.read(160000,decode_content=True) or b""
        html=raw.decode(r.encoding or "utf-8","replace")
        r.close()
    except requests.RequestException as exc:
        return {"tier":"BROKEN","score":90,"evidence":[f"Website request failed ({type(exc).__name__})."]}
    if code>=400:
        return {"tier":"BROKEN","score":90,"http_code":code,"evidence":[f"Website returned HTTP {code}."]}
    if not html.strip():
        return {"tier":"BROKEN","score":90,"http_code":code,"evidence":["Successful response contained no readable HTML."]}
    low=html.lower()
    if target.startswith("http://"):
        score+=20;evidence.append("Website is not using HTTPS.")
    else:evidence.append("HTTPS is enabled.")
    if not re.search(r'<meta[^>]+name=["\']viewport["\'][^>]+content=',low):
        score+=25;evidence.append("No mobile viewport meta tag was found.")
    else:evidence.append("Mobile viewport metadata is present.")
    title=re.search(r'<title[^>]*>(.*?)</title>',html,re.I|re.S)
    if not title or not re.sub(r'<[^>]+>','',title.group(1)).strip():
        score+=10;evidence.append("No meaningful page title was found.")
    desc=re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)',html,re.I)
    if not desc or len(desc.group(1).strip())<20:
        score+=8;evidence.append("Meta description is missing or very short.")
    if elapsed>4000:score+=20;evidence.append(f"Initial HTML response took about {elapsed} ms.")
    elif elapsed>2000:score+=10;evidence.append(f"Initial HTML response took about {elapsed} ms.")
    year=time.gmtime().tm_year
    if re.search(rf'(?:copyright|©)\s*(?:19|20)\d{{2}}',low) and str(year-3) in low:
        score+=5;evidence.append("A substantially old copyright year appears on the page.")
    obsolete=sum(bool(re.search(p,low)) for p in (r'<font\b',r'<center\b',r'<frameset\b',r'<marquee\b'))
    if obsolete:score+=10;evidence.append("Obsolete HTML markup was detected.")
    if not re.search(r'(mailto:|tel:|contact|whatsapp|facebook|instagram)',low):
        score+=8;evidence.append("No obvious contact route was found in the page HTML.")
    score=min(100,score)
    tier="WEAK" if score>=30 else "OK"
    return {"tier":tier,"score":score,"http_code":code,"final_url":str(r.url),"evidence":evidence,"ms":elapsed}

def classify_lead(website):
    return score_website(website)
