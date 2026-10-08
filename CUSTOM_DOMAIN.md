# Custom domain — reachmarkdigital.xyz

The public site is `https://reachmarkdigital.xyz`. Railway serves it. This file is
what still has to be true after DNS is attached.

## Live today

- Apex `http://reachmarkdigital.xyz` → 301 → `https://reachmarkdigital.xyz`
- HTTPS is on (Railway certificate)
- `www.reachmarkdigital.xyz` does **not** resolve yet. Add it in Railway →
  Settings → Networking → Custom Domain, then a CNAME `www` → the Railway
  target, if you want the www host.

## Railway variable (do this even before the next git push)

Railway → the Reachmark service → Variables:

```
PUBLIC_BASE_URL=https://reachmarkdigital.xyz
```

Redeploy. That one value is what live `282916b` uses for `sitemap.xml`,
`robots.txt`, canonical tags, `og:url`, preview links, and mail. Until it is
set, those still print `https://reachmark-production.up.railway.app`.

After this repo is deployed, a Railway hostname is never treated as canonical:
sitemap and Open Graph fall back to `https://reachmarkdigital.xyz`, and
`*.up.railway.app` 301s to the owned domain (`/healthz` and `/static` excluded).

## DNS reminder

| Type | Name | Target |
|------|------|--------|
| Railway custom domain | `reachmarkdigital.xyz` | whatever Railway shows (already attached) |
| CNAME | `www` | Railway CNAME target (optional) |

Leave the record DNS-only until Railway marks the domain **Active**, then proxy
if you use Cloudflare.

## Search Console and sitemap

1. Add property `https://reachmarkdigital.xyz`
2. Verification meta `ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg` is already on `/`
   (or the `google*.html` file if you use file verification)
3. Submit `https://reachmarkdigital.xyz/sitemap.xml` **after** `PUBLIC_BASE_URL` is
   the owned domain — not while the sitemap still lists `railway.app`

Analytics (`G-CPSB1EDNFE`) and GTM (`GTM-M3SJZ8S7`) fire on the new host with
no extra change.

## Email

Outbound SMTP stays Gmail (`reachmarkofficial@gmail.com`). Pointing the website
domain does not create `hello@reachmarkdigital.xyz`. Add that later with
Cloudflare Email Routing if you want a domain inbox.

## Checks

```bash
curl -sI http://reachmarkdigital.xyz/ | head
curl -s https://reachmarkdigital.xyz/healthz
curl -s https://reachmarkdigital.xyz/robots.txt
curl -s https://reachmarkdigital.xyz/sitemap.xml | head
```

Expect the sitemap and robots `Sitemap:` line to name `https://reachmarkdigital.xyz`,
not `railway.app`.
