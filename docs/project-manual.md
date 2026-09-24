# Reachmark — Find potential. Make your mark.

Global business discovery, live website checks, and reviewed website outreach.
A working Flask + SQLite app: charcoal/lime brand system, custom vector identity,
self-hosted fonts, and real server-side integrations. No Maps or model API key required.

The repo starts with an **empty** business/enquiry database — no seeded leads, fake reviews,
contact lists, credentials, or bulk mail. Tests use disposable databases and mock external
services only to avoid sending messages or hitting public endpoints.

## Run

Python 3.10+ (3.13 in production):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m web.app
```

Open http://localhost:8000 (the backend is required; never open templates directly).
To rebuild the animated menu bundle, with Node 20+: `npm ci && npm run build`.

## The AI crew — seven agents, one loop

Open **AI crew** in the workspace sidebar: find a business → prove the gap → build the
concept → ask one question → follow up when they answer → never send anything unapproved.

| Agent | Job |
|---|---|
| ★ Chief | Takes the owner's plain-word orders on the AI-crew page and delegates to the team. Reads and reports only. |
| ◎ Scout | Finds real businesses (OpenStreetMap / CSV), reads ≤3 public pages each. |
| ⌁ Auditor | Records measured website facts + a ranked list of observed gaps, each with its source. |
| ◨ Builder | Composes the concept page and issues the unguessable quick review link `/r/<token>`. |
| ✦ Scribe | Drafts the first message, two follow-ups and an SMS note from saved facts only. Drafts only. |
| ↗ Closer | Holds every outbound item for a separate human decision, then dispatches via your SMTP. |
| ☎ Receptionist | The front desk on the public pages: facts-only answers, enquiry capture, human handoff. |
| ★ Brag | Turns a won job into a launch kit (plan, brief, share copy, card, review ask, video script). |

The **review link** shows the business an independent concept built only from public facts,
then asks *“Would you like this built?”* — Yes / Not right now / I already have a website.
Answers land in the console; an e-mail reply also lands in the enquiry inbox.

Guardrails (enforced in code): nothing outbound is automatic · one message per business per
day, five dispatches per run · permanent opt-outs · no invented facts, prices or claims ·
bounded runs (14 steps, 240 s, 25 leads), one at a time, cancellable, fully audited ·
`robots.txt` honoured · live runs only (the offline demo needs `ALLOW_CREW_DEMO=1` and purges in one click).
No API key needed: every agent has a deterministic engine, and a configured model only
improves phrasing under the same guardrails (Ollama works with no key — see `.env.example`).

**One brain, no drift.** Every price, tier, timeline, opt-out line and process fact lives in
`crew/business.py` and is quoted by the agents, the API (`/api/crew` → `brain`) and the
public pages — never pasted as a copy. `tests/test_brain.py` fails the build if a literal
ever sneaks back in.

```bash
python scripts/crew_smoke.py   # offline end-to-end proof: no network, no mail
```

## What it does

- **Global finder** — 1–8 `city, country` locations or a worldwide mix; Nominatim + Overpass
  (15 km, ≤80 listings/location); background jobs, one at a time, resumable. Bounded
  discovery, never a claim of exhaustive coverage.
- **Website health** — bounded live check (64 KB, ≤5 redirects): LIVE / NOT_LISTED /
  SOCIAL_ONLY / DNS / HTTP / UNREACHABLE / BLOCKED / PARKED / FAILED. No invented scores.
- **Directory** — stages, notes, search/filters, CSV import/export (UTF-8, 5k rows), source-ID
  dedup, duplicate suggestions. Metrics come only from saved activity.
- **Composer & samples** — three deterministic tones, tailored-quote ask, no invented prices;
  per-business concept pages labelled as proposals; eight fictional showcase samples.
- **Outreach** — TLS-only SMTP, per-message approval, duplicate-send blocking, permanent
  suppression. Discovery never auto-sends.
- **Enquiries** — public form with validation, permission and rate limits; owner inbox with
  search, notes and statuses. No invented quotes or auto-replies.
- **Clients & money** — client signup/signin (clients see only their invoices/projects);
  contracts tracker; invoice creator (13 currencies, tax/discount, branded PDFs, manual Paid).
- **Trust & safety** — e-mail verification + password reset; data export + account close;
  settings snapshots + rollback; mail outbox + 9 branded templates; login throttling; CSRF.
- **Map & MCP** — Leaflet area scans (35 categories, resumable cells); Streamable-HTTP MCP
  connectors with approve-every-run; reusable skills.
- **Public site** — about, showcase, enquire, AI-receptionist page with live chat, PWA with
  honest offline behaviour, sitemap/robots/structured data. Identity, title, description and
  icons are untouched (verified by test); `templates/about.html` is byte-identical.

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

Each business has a responsive, independent concept page. It wears that business's own observed brand — the Scout harvests colours, logo, imagery and fonts from the listed page (`web/brand.py`), the audit stores the brand pack, and the Builder themes the one-pager from it (`build_theme`); businesses with no readable page fall back to their trade archetype palette, never the studio house style. The page is clearly labeled as a proposal, not the official business site. No fictional reviews, invented hours, fake booking tools, or claimed business photos. Decorative SVG artwork is labeled as concept art. Contact links use the saved phone/email. A fully bespoke client website is a separate build after agreement.

Builder memory (`builder/prompts_v1.json`, v1.0.0) holds 14 owner-supplied build briefs keyed by trade: 12 website briefs (illustrator / developer portfolio, photographer link-in-bio, architecture, smart-home pre-order, course landing, sports e-commerce, nonprofit donation, eBook landing, real estate, support dashboard, jewelry store) plus 2 backend service blueprints (notification service, file upload) that are stored but never alter website output. When a gathered lead's category matches a brief, the Builder uses that brief's exact structure — promise plus one section per core feature — while the business's own name, facts and observed brand replace every example placeholder. Brief colours are palette hints only; observed brand always wins at render. Trades with no matching brief keep the standard family treatment. The support-dashboard brief's "use mock data" line is refused: figures come only from the business's real system.

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
python -m web.app
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

The full variable list (owner login, MCP tokens, Overpass endpoints, crew providers) is documented in `.env.example`; production activation steps are in `PRODUCTION.md`.

Use port 465 and `SMTP_SECURITY=ssl` where required. No plaintext SMTP. Configure SPF/DKIM/DMARC and a verified sending identity with your provider; test delivery to your own inbox before outreach.

Publicly listed contact information is not blanket consent. Verify applicable anti-spam/privacy rules for each jurisdiction, sender identification, lawful consent/exception, and an effective opt-out process. Canadian outreach may be subject to CASL, among other laws. “Global” does not mean bypassing legal obligations, source limits, or recipient preferences.

## Production deployment

GitHub stores code; pushing this repository does **not** deploy the backend. GitHub Pages cannot run this Python application.

Use a Python host/VPS with HTTPS and persistent storage:

```bash
gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 120 web.app:app
```

Or use the included Dockerfile:

```bash
docker build -t reachmark .
docker run --env-file .env -p 8000:8000 -v sitegap-data:/data reachmark
```

- Set a strong `DASHBOARD_PASSWORD` (local/dev Basic auth, username `admin`) and generate the owner login with `scripts/configure_owner.py` (`OWNER_PASSWORD_HASH`, `/login`); use HTTPS — see `PRODUCTION.md`. Without these, the dashboard is open for local/workspace development only.
- Use one worker: jobs and public-service throttling are single-process. Do not use multiple workers/replicas without a shared queue and rate limiter.
- Persist/back up SQLite. Docker defaults to `/data/reachmark.sqlite3`. Mount the data volume with permissions for the container user.
- `/healthz` is a public minimal database health probe; `/about`, static assets, preview, unsubscribe, robots, and sitemap routes are also public.
- Preview URLs are unguessable but not access-controlled. They show saved business/contact fields, never internal notes or drafts. Do not put sensitive information into public business fields.
- Add proxy rate limiting, monitoring, backup/retention practices, your privacy notice, and stronger account/session controls before broader commercial use. This is a single-owner app, not a multi-tenant SaaS or a fully security-audited service.
- Use a hosted/self-managed OSM endpoint for sustained or higher-volume usage. Respect public Nominatim/Overpass policies.
- SMTP is not configured by source deployment; supply your own credentials. No provider delivery was tested with real credentials during development.

## Metadata and discovery

`/about` is a public indexable product page with professional title/description, canonical URL, Open Graph/Twitter tags, social-share image, SoftwareApplication structured data, app icon, and web manifest. `/robots.txt` and `/sitemap.xml` use your configured public URL. No fake reviews or ratings in structured data.

Private dashboard/API, proposal previews, and unsubscribe routes are noindex. Lead data is not SEO content. Metadata helps engines understand a deployed site; it cannot guarantee global listing or rankings. Configure a real public URL and submit the sitemap yourself after deployment. The PWA manifest plus service worker serve visited pages offline with an honest fallback page.

## Source map

- `web/app.py`: Flask, SQLite, jobs, directory, composer, SMTP, metadata endpoints
- `web/services.py`: global OSM discovery and bounded URL checks
- `web/operations.py` + `web/mcp_transport.py`: analytics, contracts, MCP connectors/skills
- `web/{accounts,portfolio,enquiries,documents,map_provider,standard,readiness,security}.py`: auth, samples, enquiries, PDF exports, area scans, composer, probes, headers
- `agents/` + `crew/`: the seven AI agents, run engine, brand brain
- `frontend/menu.jsx`: React, Framer Motion, Lucide feature menu
- `static/`: compiled JS, CSS, local fonts/licenses, app/social assets
- `templates/`: dashboard, product page, proposal, unsubscribe
- `tests/`: isolated backend checks + headless browser flows
- `scripts/`: smoke proof, backups, owner setup, release verification
- `Dockerfile`: deployable Python image

OpenStreetMap data © OpenStreetMap contributors, ODbL: https://www.openstreetmap.org/copyright. Review public usage policies before scaling. Self-hosted DM Sans and Manrope include OFL licenses. Third-party JavaScript license notices are retained in the compiled bundle.

## GitHub publishing

Repository: https://github.com/leephil1907-lab/sitegapreveal.git

GitHub requires an authenticated account with write access. Authenticate through your trusted GitHub/CLI credential flow, not by committing a token. From this repository:

```bash
git remote set-url origin https://github.com/leephil1907-lab/sitegapreveal.git
git push -u origin main
```

Do not force-push over someone else’s commits. SQLite data, `.env`, checks, and installed packages are ignored. The Docker image also excludes secrets and workspace data. No hosted deployment or SMTP connection is created by a Git push.

## Reachmark identity

**Reachmark — Find potential. Make your mark.**

Description: Discover businesses worldwide, verify website opportunities, and start meaningful conversations with personalized website proposals.

The new interface uses charcoal `#20251F`, lime `#D5F268`, warm white `#F5F5EF`, and restrained olive accents. The custom forward-R symbol includes a destination dot; the wordmark is supplied as outlined SVG so it does not rely on installed fonts.

Brand assets in `brand/`: primary/inverse SVG and transparent PNG wordmarks, SVG/PNG app symbol, and an optional asset-generation script. Production app icons, manifest and social-share image live in `static/`. Fonts retain their original OFL licenses.

The redesigned dashboard retains the same persistent database and workflows. The globe is a decorative illustration; numbers shown in workspace metrics come only from saved activity. No new business data was inserted for the visual redesign.

Name selection is a creative recommendation, not a trademark/domain availability clearance. Check the relevant registrations before commercial launch. The GitHub repository URL remains `leephil1907-lab/sitegapreveal`; the public product name is Reachmark.

## Website samples and project enquiries

### Public pages

- `/showcase`: eight clearly labelled fictional website directions.
- `/showcase/ember-coffee`: Ember & Oak, café/hospitality.
- `/showcase/stillwell-studio`: Stillwell, wellness/beauty.
- `/showcase/forma-homes`: Forma House, renovation/trades.
- `/showcase/astra-clinic`: Astra Clinic, healthcare/clinic.
- `/showcase/novera-law`: Novera Law, legal/advisory.
- `/showcase/bloom-market`: Bloom Market, boutique/retail.
- `/showcase/fintech-pulse`: Fintech Pulse, fintech/finance.
- `/showcase/getpaid`: Get Paid, SaaS/invoices.
- `/enquire`: working project estimate/question form. The `sample` query parameter preselects the design.
- `/about`: includes the design gallery and the same working enquiry form.

The existing Reachmark identity appears across the public pages, gallery and enquiry receipt. Sample names are fictional brands, not real leads, clients, reviews or completed commissions. The gallery uses actual browser screenshots of the sample pages; imagery within those pages is AI-generated concept art. No fictional sample is inserted into the business database or metrics. Preview navigation and “Ask about this design” links work; no false booking, ordering or payment tools are shown.

One shared header (`templates/header-public.html` + `static/header.css`) serves home, pricing, showcase and enquire: sticky glass bar, slim nav, locale + working theme toggle + auth controls, and a hamburger menu on mobile. Motion is dependency-free (`static/motion.css` + `static/motion.js`, React Bits / Framer Motion patterns reimplemented: split-text heroes, scroll reveals, page veil, count-ups, magnetic CTAs) with reduced-motion and no-JS fallbacks; `about.html` stays byte-identical and keeps its own premium motion. The homepage carries a live pipeline illustrator (Discover → Audit → Concept → Review link → Outreach, auto-cycling with honest demo labelling). Card and crypto prices both render from the single `TIERS` source, so they can never drift apart. AdSense loader covers `/`, `/about`, `/showcase` + all sample pages, `/enquire`, `/receptionist`, `/reviews`, `/pricing` and the workspace sidebar; `/reviews` is also in the sitemap and robots allow-list.

### Real enquiries

Visitors can send an estimate request, project question or other enquiry with their name/email, optional business, budget and timeline, message and optional sample selection. Validation and explicit contact permission are required. Successful requests are saved to SQLite and receive a reference in the browser. No quote, price, delivery date or automatic email response is invented.

The owner’s **Enquiry inbox** provides search, status filters, message details, internal notes, status updates and deletion. **Reply in email app** opens a pre-addressed email draft in the owner’s mail application; it does not automatically send mail or mark the enquiry answered. There is no email notification service or automatic inbox-to-SMTP reply flow for these requests. Check the dashboard to read new messages.

POST `/api/enquiries` is public. GET `/api/enquiries` and PATCH/DELETE `/api/enquiries/<id>` require dashboard authentication when `DASHBOARD_PASSWORD` is set. A cross-origin request check, hidden anti-bot field, length validation, retry/idempotency key and conservative database-backed hourly limits protect submissions. Basic rate limits use the socket address hash (not an untrusted forwarded header); users behind one proxy may share that limit. This is not a full CAPTCHA/spam-filter service.

Set `DASHBOARD_PASSWORD`, HTTPS, a real sender/contact profile, and appropriate privacy/retention practices before public use. The form discloses stored request details and the hashed network identifier. Add a production CAPTCHA and trusted-proxy-aware abuse controls if needed. Do not collect sensitive documents, credentials or payment details in this form. The dashboard and APIs use `Cache-Control: no-store`.

In the packaged layout these live at `web/portfolio.py`, `web/enquiries.py`, `templates/sample-site.html`, `templates/showcase.html`, `templates/enquire.html`, `templates/enquiry-form.html`, `templates/sample-cards.html`, `static/enquiry.js`, `static/inbox.js`, `static/public.css`, `static/inbox.css`, and `static/samples/`. The Dockerfile includes the packaged modules.

Validation includes isolated backend tests and a full browser submission-to-inbox flow using a disposable database. No synthetic submissions were left in the live inbox.


## MCP connectors and reusable skills

Open **MCP & skills** in the dashboard or Tools menu.

1. Add your provider's actual public HTTPS **Streamable HTTP MCP** endpoint, not its homepage or a regular REST endpoint.
2. For Bearer authentication, set a dedicated host environment variable such as `MCP_TOKEN_DESIGN`. Enter only that variable name in the connector form. Never paste secrets into tool arguments, source files, or chat.
3. Set `DASHBOARD_PASSWORD` before using an authenticated connector. Restart after environment changes.
4. Click **Test & discover tools**. The client initializes a real MCP session and requests `tools/list`; no provider tools are hardcoded into the interface.
5. Select a discovered tool, inspect its description/schema, prepare a JSON object, and explicitly approve its destination and arguments.
6. Run it once and inspect the saved result. Tool outputs are rendered as untrusted text; they never automatically execute instructions or modify leads, email counts, or contracts.
7. Save a validated tool/argument combination as a **skill**. This is a reusable preset, not code installation, an autonomous AI agent, or a model-training feature. Loading it does not run it. Adjusting a preset and saving creates a new preset; remove old ones as needed.

### Supported MCP subset and limits

- HTTPS on port 443, no-auth or server-side Bearer authentication.
- Streamable HTTP POST with JSON-RPC, JSON or SSE responses, initialization, initialized notification, session/version headers, paginated `tools/list`, and approved `tools/call`.
- Negotiated versions: `2025-06-18`, `2025-03-26`, `2025-11-25`. Not a promise of compatibility with every provider or future protocol revision.
- No OAuth account-linking flow, local/stdio commands, legacy separate SSE endpoint transport, arbitrary shell/plugin execution, resources/prompts browser, server-to-client sampling/elicitation, or asynchronous task/resumption implementation.
- A maximum of 200 discovered tools, 10 listing pages, 1 MB per MCP response, 30 KB input arguments, and 100,000 stored output characters per run.
- Network timeouts and bounded streams. Long-running providers may need a dedicated integration. One run at a time; there are no automatic retries.
- Exact endpoint redirects, query-string credentials, local/private/reserved destinations, and non-HTTPS connections are rejected. DNS results are validated, then the request is pinned to a validated address with TLS hostname verification.
- Argument validation uses the provider JSON Schema; external `$ref`, `$dynamicRef`, and `$recursiveRef` resources are blocked. Provider descriptions/annotations are not guarantees of safety.
- The tool definition is re-fetched before execution. If it changed since review, the call is blocked until re-synced/reviewed.
- Repeated requests with the same run reference do not replay an action. Known success, provider `isError`, pre-call failure, and uncertain results remain separate. An interrupted connection can leave an external action completed but unconfirmed; inspect provider logs before a new run.
- Token values are never returned to the browser, stored in the connector record, or placed in URLs. A connector stores only a dedicated environment variable name. The token is redacted from captured provider output. Arguments/results themselves are stored privately, so do not include unnecessary sensitive data.

A live compatibility check successfully initialized `https://mcp.deepwiki.com/mcp` and discovered its actual `ask_question`, `read_wiki_contents`, and `read_wiki_structure` tools. This was a handshake/discovery check, not a production connection seeded into the workspace or an AI task performed on your data. No paid AI account was connected. Public endpoint availability can change.

MCP protocol reference: https://modelcontextprotocol.io/specification/2025-03-26/basic/transports

## Contracts

**Contracts** is a manual agreement tracker. Store a project title, client/email, optional linked lead, notes, currency, value, payments received, and Draft / Sent / Signed / In progress / Completed / Cancelled stages.

Amounts are stored in integer minor units, with explicit currency precision. Blank values remain **Not priced**, not guessed revenue. USD, EUR, GBP, CAD, NGN, AUD, JPY, INR, AED, SGD, ZAR, GHS and BRL are supported. JPY uses zero decimal places; the other supported currencies use two. Recorded payments cannot exceed the contract amount. Currency changes are manual edits, not exchange conversions.

Saving a contract does **not** generate, send, sign, legally validate, or charge for an agreement. Signed dates indicate when that stage was first recorded here, not a verified electronic signature timestamp. Payment figures are manually entered, not bank-confirmed. Store the actual signed document in your appropriate document system and reference it in notes.

## Expanded overview analytics

The main Overview now queries `/api/analytics` for real database-backed breakdowns:

- Current saved businesses, website opportunities, email/phone availability, source website status, URL checks, lead stages and top locations.
- Saved email drafts, SMTP accepted messages, explicit rejections, sending state and uncertain outcomes. SMTP acceptance is not delivery; there is no fabricated open/reply rate.
- Actual project form submissions and manually maintained enquiry stages.
- Actual contract records and stages, unpriced agreements, pipeline values, committed values, and manually recorded payments **grouped by currency**. There is no summed multi-currency revenue figure.
- Recorded MCP runs and outcomes, saved connectors/skills, and discovery job states. Calls made outside Reachmark are not silently imported into these counts.
- 7/30/90-day UTC charts for saved lead creation, accepted emails, enquiries, contract creation, tool runs and server page requests.
- A journal of the latest 30 recorded workspace actions.

Most summary cards show stored totals; the page-request card and charts use the selected date range. Deleting a lead or contract removes it from its current totals and creation chart; historical SMTP/run records remain. This is not a comprehensive accounting ledger or an immutable audit service.

Page measurement starts with this deployment. It counts successful GET requests to the workspace, public home, enquiry form, sample gallery and proposal/sample pages. Refreshes, developer checks and bots may be included. It does **not** claim unique visitors or people; static/API requests and client-side tab navigation are not counted. No historical visits are invented. Proposal tokens and individual visitor identifiers are not stored in the page analytics. Dataset snapshots and metrics refresh every 30 seconds while Overview is active.

The new MCP/contract tables start empty: there are no seeded tools, contracts, runs, or payments. All UI integration-test data uses a disposable database, not the live workspace.

### Operational notes

`web/operations.py` adds the routes/storage and `web/mcp_transport.py` supplies the bounded transport. The Docker image includes the packaged modules and `jsonschema` is pinned in requirements. Use one server worker as documented for jobs/tool execution. Protect the dashboard, persisted SQLite database, and backups before adding credentials or exposing private tool output publicly.

Isolated backend tests cover MCP JSON/SSE/session handling, endpoint restrictions, schemas, approvals, changed-tool blocking, duplicate prevention, uncertain outcomes, presets, contract precision/currency totals and authentic empty-state analytics. A disposable-database browser test also covers connector discovery → saved skill → approved run → result/history → analytics, and contract creation → signed value → recorded-payment breakdown. Runtime provider availability, permissions and external actions cannot be guaranteed by tests.


## Client portal and invoices (new)

**You noted no budget for hosting right now — these features work locally today and on any VPS later. See `PRODUCTION.md` for the free-tier path.**

### Website signup and client login

- Visitors create a client account at **`/signup`** (name, email, password ≥8 characters) and sign in at **`/signin`** (also reachable via `/client-login`).
- The studio owner still uses **`/login`** with the single owner password ( `OWNER_PASSWORD_HASH` ). Client accounts are separate and do not gain lead-directory or discovery access.
- Public navigation (`/about`, `/showcase`, `/enquire`) now links to **Create account** and **Client portal** for easy discovery.
- Sessions are HTTP-only, SameSite=Strict, 8 h lifetime, CSRF-protected. Login throttling (5 failures → 15 min block) applies to both owner and client.
- `GET /api/auth/me`, `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`, and `GET /api/clients` (owner only) support the flow. The profile badge shows the signed-in client’s name/email when in portal mode.

### Privacy model: clients only see what you assign

- **Owner sees everything** — leads, discovery, health, contracts, projects, invoices, settings.
- **Clients see only** invoices and projects whose `client_email` matches their registered email (linked via `client_user_id`). No leads, no global search, no health checks.
- Assign by entering the client’s registered email when creating or editing a **Project** (new “Assign to client” field) or an **Invoice**. The server links `client_user_id` automatically if the email is already registered; otherwise the link resolves on next client login. Unassigned records remain studio-only.

### Invoice creator — original Reachmark design, AllScale-inspired workflow

Built as an **original** Reachmark billing workspace, not a copy of AllScale’s branding or payment rails. The workflow is intentionally similar — create, add items, set tax/discount, track status, download a branded PDF — but all billing is manual.

- **Owner-only creation** at **Invoices** in the workspace (also via `POST /api/invoices`). Add 1–25 line items — each needs a description (≤500 c), quantity (positive, up to 2 decimals), and unit price. Example presets (Website design + Content) are shown for new invoices.
- **Currencies:** USD, EUR, GBP, CAD, NGN, AUD, JPY (0 decimals), INR, AED, SGD, ZAR, GHS, BRL — amounts stored in integer minor units, no invented conversion.
- **Totals:** live preview in the form as `(Σ qty×unit) – discount + tax`. Discount is **none / percent (0–100%) / fixed amount** (capped at subtotal). Tax is 0–100%. `subtotal_minor`, `discount_minor`, `tax_minor`, `total_minor` are persisted.
- **Metadata:** issue/due dates (YYYY-MM-DD, due ≥ issue), linked project or business, notes and terms (≤5000 c each), status **Draft / Sent / Paid / Overdue / Cancelled**. **Paid is manual** — mark only after you verify the bank, wallet or card receipt yourself. No payment provider is charged and no stablecoin settlement occurs.
- **PDFs:** branded DejaVu PDFs at `/api/documents/invoice/<id>.pdf` — same visual system as other exports (studio header, lime rule, page numbers). The owner and the assigned client can both download; unassigned invoices are owner-only. The PDF header marks Draft clearly and the footer states this is a record, not an electronic signature, payment receipt or legal contract.
- **Client portal:** clients see a filtered invoice list (search by number/client, filter by status), view-only detail, and PDF download. They cannot create, edit or delete invoices. Projects assigned to them also allow proposal/brief PDF downloads.

Validation, disposable-DB browser checks, and the isolated backend suite cover the new flows. No test data is written to the live workspace.

### VPS and deployment — recommendation for no funds

See **`PRODUCTION.md`** (zero-budget path + $5–10 comparison). TL;DR: keep running **local Docker + Cloudflare Tunnel** for free, and claim **Oracle Cloud Free Tier (ARM)** when you want a 24/7 public host. **Hetzner CX22 (~€4.15/mo)** is the recommended cheap paid starting point when budget is available; Hostinger KVM 1 and DigitalOcean $12 plans are alternatives. No domain or hosting was purchased by this update.

## World map and durable area scans

Global finder now includes a locally shipped Leaflet map (no Google API or runtime JavaScript CDN), city/country search, direct latitude/longitude navigation, saved-lead clusters (click a count to zoom; overlapping points spread at maximum zoom), world/fit controls, mobile layout and locally remembered view. Basemap tiles come from OpenStreetMap with visible attribution and origin referrers. No prefetching, offline tile packs or tile proxy. If tiles fail, markers, cell overlays, coordinate navigation and the lead directory remain available; use **Reload basemap** to retry. Tile availability is independent of Overpass discovery.

**Scan visible area** queries one of 35 explicitly supported OSM business categories. Select a region no larger than 25 km wide/high (also ≤2° longitude). It is divided into cells approximately ≤7 km wide/high, at most 20 per scan. Dateline-crossing selections are split safely. Named OSM nodes/ways/relations are requested, including businesses with listed websites. Up to 500 listings per cell are saved, deduplicated by OSM object ID. A timeout remark or extra result sets the cell to **partial**, never checked; zoom into a dense cell and scan smaller areas. Different OSM objects may still represent the same real business and require manual review. Existing records/notes are not overwritten by a repeat discovery.

Scan and cell records persist in SQLite. **Pause** lets an in-flight cell finish saving; **Resume unfinished** retries pending/failed cells and skips checked ones. Server restart marks active scans interrupted and running cells pending. Only one map worker runs at a time. Latest 50 areas appear in the map UI; older records remain in the database. Map markers have an explicit 5,000 display limit; CSV export retains all saved leads. Missing coordinates are counted, never inferred. Map display is Web Mercator (approximately ±85°); the backend bounds validator supports geographic latitudes through ±90°. Checked means the selected category query succeeded at the recorded time—not all businesses, all categories, a whole city/country, or current/exhaustive coverage. Listing hits across cells can overlap; they are not unique-business metrics.

Read-only Overpass calls are serialized, spaced by at least two seconds, capped at 8 MB, and allow one fallback on transport/HTTP service errors. Defaults are Private.coffee and VK Maps public instances (requests share only query geometry/category, not your saved lead list). An explicit HTTP 429/406 pauses all providers for at least one minute and honors numeric Retry-After, capped at one hour; fallback does not bypass that pause. Outages leave failed cells available for manual resume. Set `OVERPASS_URLS` to one or two comma-separated approved HTTPS endpoints to switch to contracted/self-hosted capacity. Public community endpoints are not an uptime SLA or a solution for bulk global harvesting. Current instance policies: https://wiki.openstreetmap.org/wiki/Overpass_API . Never include credentials in committed endpoint configuration. There is no automatic worldwide sweep.

Place search is explicit (no autocomplete), serialized at ≥1.1 seconds, and successful map lookups are cached in SQLite. Cached lookups are labeled; enter coordinates or pan manually when geocoding is unavailable. OSM may lack names, contacts, websites or entire businesses; CSV import remains the alternative. Source gaps and connection errors do not establish that a business has no website.

Run backend regressions with `python -m unittest discover tests -q` (233 checks). Map coverage includes bounds/dateline validation, failures, caps/partial results, deduplication, resume, cancellation, authentication, persistent place cache, provider fallback and rate limits. `tests/browser/map_flow.py` (workspace QA helper) uses a disposable database and deliberately blocks external tiles to test navigation, scans, reload persistence and mobile alignment without adding production fixtures.

Deployment still requires one application worker (threaded Gunicorn as in Dockerfile), a persistent writable DATABASE_PATH, HTTPS and a strong DASHBOARD_PASSWORD before public access. SMTP and MCP credentials can be configured later. The map does not depend on either. Never run multiple app workers against these in-process discovery queues. Stop/pause discovery before redeploying. Superseded by the production upgrade: owner authentication, deployment scaffolding and document PDF downloads are now implemented. Infrastructure, monitoring accounts and actual public deployment still require activation; see PRODUCTION.md.

### Live task overview
The analytics overview now includes real map-scan/cell states and a live workspace task list for city searches, map scans and approved MCP runs. It refreshes every 30 seconds while visible and prioritizes active jobs, with up to 20 entries. It is not an autonomous agent or a record of development actions in chat. Empty counters remain zero; no activity is fabricated.

## Production upgrade validation
Run `python -m unittest discover tests -q` (233 isolated backend checks). Browser regressions: `PYTHONPATH=. python tests/browser/production_flow.py` and `PYTHONPATH=. python tests/browser/map_flow.py` (install Playwright and Chromium first). No test fixtures are written to the live database. This remains JavaScript/JSX, not a TypeScript project; npm build and JS syntax checks are used rather than claiming a nonexistent TypeScript check.

## Layout

```
web/          Flask app, metadata, documents, review links, receptionist, probes, mail
agents/       the seven crew agents (scout/auditor/builder/scribe/closer/receptionist/brag)
              + agent_video.py, the honest ad-render step behind Brag
crew/         run engine (crew.py), brand brain (business.py), playbook loader
tests/        isolated unittest suites + headless browser flows
scripts/      smoke proof, backups, owner setup, PWA assets, release verification
skills/       vendored MIT playbooks + licences (see below)
knowledge/    reachmark.md — the only facts the front desk may quote
fixtures/     offline demo records, dev-only behind ALLOW_CREW_DEMO=1
templates/ static/   pages, PWA assets, JS/CSS (no CDN at runtime)
```

## Tests

```bash
python -m unittest            # full suite, disposable databases (233 checks)
python scripts/crew_smoke.py  # offline crew proof
for f in static/*.js; do node --check "$f"; done
PYTHONPATH=. python tests/browser/production_flow.py   # needs Playwright + Chromium
PYTHONPATH=. python tests/browser/map_flow.py
```

## Attribution and provenance

The crew combines three repositories. Nothing third-party is presented as original work.

- **`marketingskills`** (Corey Haines, MIT) — six playbooks vendored **verbatim** (plugin
  `2.11.1`, commit `5b2c000`): `cold-email`, `copywriting`, `cro`, `prospecting`, `ai-seo`,
  `seo-audit`. Rules and structure only — never business facts. Licence:
  `skills/vendor/licenses/marketingskills-LICENSE.txt`.
- **`brag`** (Shunit Haviv Hakimi, MIT; commit `57ce4c9`) — `skills/brag/SKILL.md` vendored
  verbatim; the Brag agent implements its shape. Licence:
  `skills/vendor/licenses/brag-LICENSE.txt`.
- **`RevenueJob`** (the owner's own repo) — the engineering *pattern* behind
  `static/crew-orb.js` (tiered animated hero, reduced-motion path, fresh implementation).
- OpenStreetMap data © OpenStreetMap contributors (ODbL) · DM Sans/Manrope (OFL) ·
  Leaflet/MarkerCluster (licences in `static/vendor/`).

If you fork, deploy or resell: keep `skills/vendor/licenses/` intact and keep this
attribution. For MIT code that is the only condition — but it is a condition.

**Design inspiration:** the counters, reveals, skeletons, heatmap, tour, magnetic buttons
and star ratings follow patterns from the [React Bits](https://reactbits.dev) collection
and the [Made with React.js](https://madewithreactjs.com/ui-components) directory —
re-implemented here dependency-free in vanilla JS/CSS. No React code is vendored.

## Deploy & publish

See **[OPERATIONS.md](OPERATIONS.md)**: environment, Docker/HTTPS deployment, domain + DNS,
backups, monitoring, CI releases, crew operations and the publishing checklist.

See **[PRODUCTION.md](PRODUCTION.md)** for owner login, Docker/HTTPS deployment,
backup/restore, monitoring activation, CI release verification and the launch checklist
(including the zero-budget path). Production hosting/domain/alerts are not yet provisioned.
**[CUSTOM_DOMAIN.md](CUSTOM_DOMAIN.md)** covers pointing `reachmark.co` at the app;
**[STANDARD_FEATURES.md](STANDARD_FEATURES.md)** records the auth/GDPR/snapshot/outbox upgrades.

Repo: <https://github.com/leephil1907-lab/sitegapreveal.git> — pushing stores code only;
it never deploys the backend (GitHub Pages cannot run this Python app).
