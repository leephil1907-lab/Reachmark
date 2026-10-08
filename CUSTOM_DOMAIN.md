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
2. Search Console HTML tag for `https://reachmarkdigital.xyz` is on `/`:
   `zVYthfXOcAda_Sxphe3f8dYmVrRZ66cogYgTHWeaq7c`
3. Submit `https://reachmarkdigital.xyz/sitemap.xml` **after** `PUBLIC_BASE_URL` is
   the owned domain — not while the sitemap still lists `railway.app`

Analytics (`G-CPSB1EDNFE`) and GTM (`GTM-M3SJZ8S7`) fire on the new host with
no extra change.

## Email

Outbound SMTP is Gmail:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USER=reachmarkofficial@gmail.com
SMTP_FROM=reachmarkofficial@gmail.com
SUPPORT_EMAIL=reachmarkofficial@gmail.com
```

Use a Gmail App Password for `SMTP_PASSWORD`. Do not put that value in Git.
Pointing the website domain does not create `hello@reachmarkdigital.xyz`. Add
that later with Cloudflare Email Routing if you want a domain inbox.

## Google sign-up and sign-in

In Google Cloud → APIs & Services → Credentials → the OAuth client, set:

- Authorized JavaScript origins: `https://reachmarkdigital.xyz`
- Authorized redirect URIs:
  - `https://reachmarkdigital.xyz/api/auth/oauth/google/callback` (client sign-up / sign-in)
  - `https://reachmarkdigital.xyz/api/google-business/oauth/callback` (Business Profile, separate)

Railway variables (same values, no secrets here):

```
GOOGLE_OAUTH_REDIRECT_URI=https://reachmarkdigital.xyz/api/auth/oauth/google/callback
GOOGLE_BUSINESS_REDIRECT_URI=https://reachmarkdigital.xyz/api/google-business/oauth/callback
```

Leave `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` as they already are. A Railway
preview callback is ignored so Google is not sent back to `*.up.railway.app`.

## Checks

```bash
curl -sI http://reachmarkdigital.xyz/ | head
curl -s https://reachmarkdigital.xyz/healthz
curl -s https://reachmarkdigital.xyz/robots.txt
curl -s https://reachmarkdigital.xyz/sitemap.xml | head
```

Expect the sitemap and robots `Sitemap:` line to name `https://reachmarkdigital.xyz`,
not `railway.app`.
