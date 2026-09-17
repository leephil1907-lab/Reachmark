# SiteGap Reveal

Global business discovery, live website checks, and reviewed website outreach.

A working Flask + SQLite application with a responsive dashboard, React/Framer Motion feature menu, Lucide vector icons, self-hosted fonts, and real server-side integrations. No Google Maps or language-model API key is required.

**The repository starts with an empty database. It contains no seeded businesses, simulated analytics, fake reviews, contact lists, SMTP credentials, or automatic bulk-email campaign.** Workspace data is not committed. Unit-test fixtures are isolated from runtime data; tests mock external services only to avoid sending messages or hitting public endpoints.

## Run

Python 3.10+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000. The backend is required; do not open the HTML templates directly. On Termux: `pkg install python` first.

The compiled Framer Motion bundle is included. To change/rebuild the animated frontend, use Node 20+:

```bash
npm ci
npm run build
```

## Real features

### Global finder

- Enter 1–8 **city, country** locations, one per line, or select **Choose a worldwide location mix**.
- The mix chooses search locations across six world regions. Those city names are search seeds, not fabricated business results.
- Nominatim geocodes each location globally, with cached geocoding and at least 1.1 seconds between uncached calls in one process.
- Overpass queries tagged OpenStreetMap businesses within 15 km, up to 80 listings per location. No Canadian country restriction.
- Background jobs persist progress, additions, checks, errors, and cancellation state. One job runs at a time. A restart marks an unfinished job interrupted rather than pretending it completed.
- When website checking is enabled, listed-website businesses are retained too, with up to 12 website checks per location. Remaining URLs can be checked individually. Filter results in Website health.
- Public map services can be slow or unavailable. Errors are shown, never replaced with fake results. This is bounded multi-location discovery, **not an exhaustive scan of every business on the planet**.

### Business details

Name, category, searched location, available address, phone, email, website, coordinates, listed opening hours, social link, original OSM URL, and all returned source tags. Missing fields stay missing. Public OSM coverage varies widely, particularly for trades and home-based businesses.

No software can guarantee every business’s full contact information from this source. No guessed emails, scraped private accounts, or claims that a listed address is verified. Independently verify contact details and legal outreach basis.

### Website health

A bounded live GET inspects the HTTP result and a maximum of 64 KB of response text. It follows at most five redirects and records the result and timestamp.

| Status | Meaning |
|---|---|
| NOT_LISTED | No website URL in the source. Not proof of no website. |
| SOCIAL_ONLY | Social/link-profile URL, or redirect to one. |
| LIVE | Successful HTTP response. Not proof of working forms or good design. |
| DNS_UNRESOLVED | DNS failed at check time; could be a dead domain or a temporary issue. |
| HTTP_ERROR | The listed page returned a client/server error. |
| UNREACHABLE | Connection/TLS/timeout failure. Could be local network restrictions. |
| BLOCKED | 401, 403, or 429; explicitly not classified as a dead site. |
| PARKED_SUSPECTED | Domain-sale/parking wording found; verify manually. |
| CHECK_FAILED | Unsupported URL, blocked private destination, redirects, or inconclusive result. |

Checks validate public destination IPs and connect to the validated IP while retaining TLS hostname verification. Private/reserved destinations, non-HTTP schemes, unusual ports, and mixed public/private DNS results are blocked. Checks are not a full browser audit, malware scanner, or proof that a business needs a redesign. No invented quality scores.

### Directory and metrics

SQLite persistence, manual creation, edit/delete, stage management, research/consent notes, search and filters, CSV import/export, and source-ID deduplication. Deleting a lead does not delete prior send records or sent-message opt-out mappings.

Metrics are computed from saved leads, stages, and SMTP acceptance records. Background jobs update the browser every four seconds; idle metrics refresh every 30 seconds. Replied and Won stages are manually maintained. No fabricated opens, response rates, revenue, or delivery analytics.

CSV: UTF-8, max 3 MB / 5,000 rows. Required: `name`. Optional: `category,city,address,phone,email,website`. Original `listed_website` and `city_searched` columns are also accepted. Exports include stored audit evidence and available location fields. Potential spreadsheet formulas are escaped with an apostrophe.

### Composer and previews

Three editable, deterministic tones: Professional, Warm, Concise. Uses the lead’s saved name/location and your sender profile. No language-model service or invented research claims. It asks for requirements/budget and offers a **tailored quote**, with no invented prices or unsubstantiated “cheaper than your current provider” claims.

Each business has a responsive, independent concept page. It uses a shared design template and the actual saved business information, clearly labeled as a proposal, not the official business site. No fictional reviews, invented hours, fake booking tools, or claimed business photos. Decorative SVG artwork is labeled as concept art. Contact links use the saved phone/email. A fully bespoke client website is a separate build after agreement.

Preview emails use a link to the publicly deployed concept. No screenshot attachment or automatic full-site generator. Set your real public URL in Settings before emailing links.

### SMTP outreach

A verified recipient, complete sender profile, saved message, reviewed content, and confirmed lawful contact basis are required. Send individually from the composer. **Discovery does not automatically send mail to newly found businesses.**

TLS-only SMTP, explicit confirmation, duplicate-send blocking, acceptance history, automatic sender/opt-out footer, public unsubscribe confirmation, and local suppression. Credentials stay in server environment variables.

“Configured” means SMTP host/from variables exist, not that credentials or delivery are verified. “Sent” means accepted by the SMTP server, not delivered/read. Replies are not synchronized; mark stages and process reply-based opt-outs manually using Block outreach.

Explicit SMTP rejections permit retry after correction. Uncertain connection failures are marked unknown and block blind resend; check provider logs before operator recovery. No automatic follow-ups.

## Configure sender and secrets

Complete Settings: name, studio, reply-to address, postal address, and offer description. Public preview URL must be your stable HTTPS deployment.

Set secrets through your hosting provider. Do not paste passwords into a chat or commit them. For local use, copy `.env.example` to `.env`, fill it privately, then explicitly load it:

```bash
set -a
source .env
set +a
python app.py
```

Variables:

```text
SMTP_HOST
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USER
SMTP_PASSWORD
SMTP_FROM
DASHBOARD_PASSWORD
DATABASE_PATH (optional absolute SQLite path)
PORT=8000
```

Use port 465 and `SMTP_SECURITY=ssl` where required. No plaintext SMTP. Configure SPF/DKIM/DMARC and a verified sending identity with your provider; test delivery to your own inbox before outreach.

Publicly listed contact information is not blanket consent. Verify applicable anti-spam/privacy rules for each jurisdiction, sender identification, lawful consent/exception, and an effective opt-out process. Canadian outreach may be subject to CASL, among other laws. “Global” does not mean bypassing legal obligations, source limits, or recipient preferences.

## Production deployment

GitHub stores code; pushing this repository does **not** deploy the backend. GitHub Pages cannot run this Python application.

Use a Python host/VPS with HTTPS and persistent storage:

```bash
gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 120 app:app
```

Or use the included Dockerfile:

```bash
docker build -t sitegap-reveal .
docker run --env-file .env -p 8000:8000 -v sitegap-data:/data sitegap-reveal
```

- Set a strong `DASHBOARD_PASSWORD`; Basic auth username is `admin`. Use HTTPS. Without the variable, the dashboard is open for local/workspace development only.
- Use one worker: jobs and public-service throttling are single-process. Do not use multiple workers/replicas without a shared queue and rate limiter.
- Persist/back up SQLite. Docker defaults to `/data/sitegap.sqlite3`. Mount the data volume with permissions for the container user.
- `/healthz` is a public minimal database health probe; `/about`, static assets, preview, unsubscribe, robots, and sitemap routes are also public.
- Preview URLs are unguessable but not access-controlled. They show saved business/contact fields, never internal notes or drafts. Do not put sensitive information into public business fields.
- Add proxy rate limiting, monitoring, backup/retention practices, your privacy notice, and stronger account/session controls before broader commercial use. This is a single-owner app, not a multi-tenant SaaS or a fully security-audited service.
- Use a hosted/self-managed OSM endpoint for sustained or higher-volume usage. Respect public Nominatim/Overpass policies.
- SMTP is not configured by source deployment; supply your own credentials. No provider delivery was tested with real credentials during development.

## Metadata and discovery

`/about` is a public indexable product page with professional title/description, canonical URL, Open Graph/Twitter tags, social-share image, SoftwareApplication structured data, app icon, and web manifest. `/robots.txt` and `/sitemap.xml` use your configured public URL. No fake reviews or ratings in structured data.

Private dashboard/API, proposal previews, and unsubscribe routes are noindex. Lead data is not SEO content. Metadata helps engines understand a deployed site; it cannot guarantee global listing or rankings. Configure a real public URL and submit the sitemap yourself after deployment. The manifest is app metadata, not a claim of offline support.

## Tests

```bash
python -m unittest test_app -v
npm run build
```

16 isolated tests cover CRUD, CSV, templates, mocked SMTP safety, persistent opt-outs, global job validation/start/cancel, source discovery, private-address blocking, invalid audit schemes, DNS uncertainty, metadata, and origin checks. Unit tests bootstrap temporary databases and never mutate the running workspace or send real email.

Desktop/mobile Chromium checks covered the animated feature dropdown, global finder, health list, detail evidence panel, metadata page, no horizontal overflow, and no JavaScript exceptions. Public integrations are still subject to network conditions; no claim of perfect uptime.

## Source map

- `app.py`: Flask, SQLite, jobs, directory, composer, SMTP, metadata endpoints
- `services.py`: global OSM discovery and bounded URL checks
- `frontend/menu.jsx`: React, Framer Motion, Lucide feature menu
- `static/`: compiled JS, CSS, local fonts/licenses, app/social assets
- `templates/`: dashboard, product page, proposal, unsubscribe
- `test_app.py`: isolated backend checks
- `Dockerfile`: deployable Python image

OpenStreetMap data © OpenStreetMap contributors, ODbL: https://www.openstreetmap.org/copyright. Review public usage policies before scaling. Self-hosted DM Sans and Manrope include OFL licenses. Third-party JavaScript license notices are retained in the compiled bundle.
