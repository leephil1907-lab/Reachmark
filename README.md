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
| ◎ Scout | Finds real businesses (OpenStreetMap / CSV / offline demo), reads ≤3 public pages each. |
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
`robots.txt` honoured · an offline demo that makes no network calls and purges in one click.
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
  per-business concept pages labelled as proposals; three fictional showcase samples.
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
fixtures/     purgeable offline demo records
templates/ static/   pages, PWA assets, JS/CSS (no CDN at runtime)
```

## Tests

```bash
python -m unittest            # full suite, disposable databases (196 checks)
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

Repo: <https://github.com/leephil1907-lab/sitegapreveal.git> — pushing stores code only;
it never deploys the backend (GitHub Pages cannot run this Python app).
