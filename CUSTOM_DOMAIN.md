# Reachmark Custom Domain — reachmark.co

Your personal brand deserves `reachmark.co` not `sitegapreveal-production.up.railway.app`. This guide makes it top-notch.

## 1) Buy / Claim Domain (if not yet)
- Registrar: Cloudflare, Namecheap, or Google Domains — search `reachmark.co` → buy.
- If you already own it, skip to 2.

## 2) Add to Railway
1. Railway → your service `sitegapreveal` → Settings → Networking → Custom Domain
2. Add: `reachmark.co` and `www.reachmark.co`
3. Railway shows CNAME target e.g. `cname.railway.app` — copy it.

## 3) DNS (Cloudflare recommended)
In your domain DNS:

| Type | Name | Target | Proxy |
|------|------|--------|-------|
| CNAME | @ (or `reachmark.co`) | `cname.railway.app` from Railway | DNS only (grey cloud) first, then orange after verified |
| CNAME | www | `cname.railway.app` | DNS only → orange |
| TXT | @ | `v=spf1 include:_spf.mx.cloudflare.net ~all` (for email) | — |

Wait 2-5 min → Railway shows **Active** → HTTPS auto-provisions.

## 4) Tell the app its canonical URL
Railway → Variables → add:
```
PUBLIC_BASE_URL=https://reachmark.co
RELEASE_SHA=manual-reachmark-co-1
```
Redeploy. The app now:
- Uses `https://reachmark.co` for `sitemap.xml`, `robots.txt`, `canonical`, `og:image`, preview links, emails
- 301 redirects any `up.railway.app` hit to `reachmark.co` (keeps SEO juice, preserves path+query, skips `/healthz` and `/static`)

Test:
```bash
curl -i https://reachmark.co/sitemap.xml | head
curl -i https://sitegapreveal-production.up.railway.app/ | grep -i location  # should 301 to https://reachmark.co/
```

## 5) Email `hello@reachmark.co` (personal brand)
**Option A — Free (Cloudflare Email Routing):**
1. Cloudflare → Email → Email Routing → Enable → Add `hello@reachmark.co` → Destination: your Gmail
2. Cloudflare adds MX/TXT automatically. Test by sending to `hello@reachmark.co`.

**Option B — Pro (Google Workspace / Zoho):**
- Create workspace for `reachmark.co`, add Gmail MX, verify TXT. Then set Railway `SMTP_HOST`, `SMTP_FROM=hello@reachmark.co`.

Update app sender: Railway → Variables or App → Settings → Sender profile → `reply_email=hello@reachmark.co`, `agency=Reachmark`, `public_base_url=https://reachmark.co`.

## 6) Re-verify Google
After domain live:
- Search Console → Add property `https://reachmark.co` → HTML file method still works (`/googlee75a778b14224ae6.html` now served at new domain) or meta tag `ClnMo7...` — re-verify.
- Analytics `G-CPSB1EDNFE` + `GT-M6XWG99J` + GTM `GTM-M3SJZ8S7` auto-fire on new domain (no change).
- Submit sitemap: `https://reachmark.co/sitemap.xml` (12 URLs).

## 7) Final checks
- `https://reachmark.co` loads with lime `R` tight to `eachmark`, `200px`, nav glass motion
- `https://www.reachmark.co` → 301 → `https://reachmark.co` (Railway handles)
- `https://reachmark.co/robots.txt` shows `Sitemap: https://reachmark.co/sitemap.xml`
- Email test: send enquiry → reply-To is `hello@reachmark.co`

Need me to set `PUBLIC_BASE_URL` for you? Give me the exact domain you bought (e.g. `reachmark.co` or `reachmark.com`) and I’ll push the env-ready code and mark it as canonical.
