# Operations — configure, deploy, back up, publish

## 1. Environment

```bash
cp .env.example .env   # fill in privately, then:
set -a; source .env; set +a
```

Never commit `.env`, databases or backups. Secrets live in the host environment, never in
chat, source or the browser (MCP connectors store only a *variable name* like
`MCP_TOKEN_DESIGN`).

| Variable | Purpose |
|---|---|
| `SMTP_HOST/PORT/SECURITY/USER/PASSWORD/FROM` | Your mail provider (TLS only: 587+starttls or 465+ssl). Until set, approved mail queues in the outbox — never *sent*. |
| `DASHBOARD_PASSWORD` | Dev/compat gate for the dashboard. Production uses the owner login below. |
| `DATABASE_PATH` | Absolute SQLite path (default: project dir; Docker: `/data/sitegap.sqlite3`; Railway: `/data/prospect.sqlite3` on an attached volume — without a volume, redeploys wipe the database). |
| `PORT` | Default `8000`. |
| `OVERPASS_URLS` | Map endpoints, ≤2 comma-separated. Default: two shared public mirrors. Dedicated capacity (required before sustained commercial volume): self-host Overpass (`docker run -p 8080:80 --ulimit nofile=65536:65536 wiktorn/overpass-api`) or a contracted endpoint, then set `OVERPASS_URLS=https://your-overpass/api/interpreter`. The app load-sheds across the list in order. |
| `CREW_LLM_PROVIDER/MODEL/API_KEY/BASE_URL/TIMEOUT/BUDGET/SEND_CONTACTS` | Optional model for phrasing only (`auto\|ollama\|openai\|anthropic\|none`). Contacts are masked by default. |
| `OLLAMA_HOST` | Local models, no key: `ollama serve && ollama pull llama3.1`. |
| `CREW_VIDEO_RENDER` | `1` lets Brag render ad cuts when Playwright+ffmpeg exist; `0` writes the brief only. |
| `SMARTSUPP_KEY` | Optional live chat (widget loads only when set). |
| `SENTRY_DSN` | Optional error monitoring (scrubbed events). |

Production additionally requires (generated **on the server**, mode-0600
`.env.production`): `APP_ENV=production`, 32+ char `SECRET_KEY`, `OWNER_PASSWORD_HASH`,
HTTPS `PUBLIC_BASE_URL`, absolute `DATABASE_PATH`. Missing requirements refuse to start.

Publicly listed contacts are not blanket consent — verify the anti-spam/privacy rules
(CASL etc.) for every jurisdiction before outreach.

## 2. Run it

```bash
python -m web.app                                  # local dev
gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 120 web.app:app
docker build -t reachmark .
docker run --env-file .env -p 8000:8000 -v sitegap-data:/data reachmark
docker compose up -d                               # app + Caddy + backups (same file locally or on a VPS)
```

One worker only: discovery, the crew lock and throttling are single-process. Persist and
back up SQLite; never run a second writer against it.

## 3. Owner access & first launch (VPS)

```bash
cd /opt/reachmark
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/configure_owner.py   # owned domain + 16+ char password → .env.production
printf 'DOMAIN=your-owned-domain.example\n' > .env && chmod 600 .env .env.production
touch .env.backup && chmod 600 .env.backup
docker compose build --build-arg RELEASE_SHA="$(git rev-parse HEAD)" && docker compose up -d
```

Sign in at `/login` (password only, 8 h sessions, 15-min block after 5 failures, no MFA —
add an identity gateway if you need it). No emailed reset: rotate the hash and recreate.

Zero budget? Run local Docker + a Cloudflare Tunnel for real work; Oracle Cloud Always Free
(ARM) is the documented free 24/7 path. When paying, Hetzner CX22 (~€4.15/mo, 2 vCPU/4 GB)
is the recommended start; avoid 1 GB plans for production.

## 4. Domain, DNS, e-mail

DNS at your registrar (Cloudflare recommended): `A @ → <VPS IP>` (+ `www` if wanted);
Caddy fetches HTTPS automatically once the name resolves. Then set
`PUBLIC_BASE_URL=https://your-domain` — sitemap, canonical URLs, previews and mail use it,
and old hosts 301 to it.

- Sending as you: Cloudflare Email Routing can forward `hello@your-domain` to your inbox
  for free; a workspace (Google/Zoho) gives you `SMTP_*` for sending.
- Update the in-app sender profile (`reply_email`, `agency`, `public_base_url`), re-verify
  Search Console on the new domain, and submit `/sitemap.xml`.

## 5. Backups & restore

Snapshots run inside the deployment (immediate + every 24 h, 14 kept, mode-0600, SHA-256
manifest + integrity check). Local copies are not disaster recovery — configure encrypted
offsite storage in `.env.backup` (`RESTIC_REPOSITORY/PASSWORD/...`, optional
`BACKUP_HEALTHCHECK_URL`), `restic init` once, and a remote prune policy.

```bash
python scripts/backup.py backup --database /path/to/live.sqlite3 --directory /private/export
docker compose stop app backup
docker compose run --rm --no-deps -v /absolute/private/export:/restore:ro app \
  python scripts/backup.py restore --snapshot /restore/EXACT-SNAPSHOT.sqlite3 --confirm-app-stopped
docker compose up -d
```

Never restore over a live writer. After restoring: restart, sign in, compare counts, open a
real record, download a PDF. Drill a full offsite restore on a separate host monthly.

Railway (current host): add a **volume mounted at `/data`**, set
`DATABASE_PATH=/data/prospect.sqlite3`, and redeploy — the app refuses to start with a
clear error if `/data` is missing, so a forgotten volume is loud, not silent. Run
backups as a second Railway cron service on the same image + volume:
`python scripts/backup.py backup` with `BACKUP_DIR=/data/backups`
(`--directory` overrides), plus `RESTIC_REPOSITORY/PASSWORD` and
`BACKUP_HEALTHCHECK_URL` for the encrypted offsite copy and failure alerts.

## 6. Monitoring

External uptime checks (Better Stack/UptimeRobot → e-mail), independent of app SMTP:
HTTPS GET `/healthz`, expect 200 + `status=ok` (+ release SHA). Also watch backup
heartbeats, disk, container restarts and DB growth. `/api/deploy-check` (public, noindex)
reports every publish-readiness item as pass/fail — the checklist in §9 is its output.

## 7. CI & verified releases

`ci.yml` (every push/PR): deps → JS build → full unittest → `node --check` all JS →
Playwright browser flows → crew smoke → Docker build. `deploy.yml` (manual first; set
`ENABLE_AUTO_DEPLOY=true` for post-CI main deploys): commit-tagged GHCR image → snapshot →
ship Compose/Caddy → deploy + Caddy reload → `verify_release.py` (HTTPS, **exact SHA**,
private APIs deny anonymous calls — 200 alone is not success).

Production environment needs: `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS` (verified, not a
runtime keyscan), `DEPLOY_HOST/USER`, `PRODUCTION_URL`. Pause discovery before a release.
On failure: fix forward or roll back via the last `REACHMARK_IMAGE` in `.env`
(`docker compose up -d --no-build`) after a snapshot — never silently.

## 8. Crew operations

Before the crew talks to businesses: complete the sender profile (name, studio, reply-to,
postal address) · configure SMTP · optionally set a model provider. Then watch the
**approval queue** — nothing outbound exists anywhere else.

| Limit | Value | Enforced in |
|---|---|---|
| Steps / wall clock / leads per run | 14 / 240 s / 25 | `crew.LIMITS` |
| Dispatches per run / per business | 5 / 1 per 24 h | `crew_mail.preflight` |
| Public-page reads per business | 3 pages, 96 KB each, robots honoured | `agent_scout` |
| Front-desk messages | 40/hour per connection | `receptionist.rate_ok` |
| Concurrency | 1 run, 1 worker, single process | `crew.Crew.lock` |

Post-deploy proof: `python scripts/crew_smoke.py`, plus an anonymous
`GET /api/crew` (expect 401). Crew tables live in the same SQLite file, so §5 covers them.
Review links are unlisted-but-public (saved business fields only); transcripts are as
sensitive as the enquiry inbox — give them a retention rule in your privacy notice.

## 9. Publishing checklist

Identity, title, description and icons are **unchanged** (md5-verified by test);
`templates/about.html` is byte-identical. `/api/deploy-check` currently reports **28/32** —
the four failures are your production secrets, empty by design in development:

| Only you can fill | How |
|---|---|
| `PUBLIC_BASE_URL` | live `https://` domain (§4) |
| `SECRET_KEY` | 32+ random chars (§1) |
| `OWNER_PASSWORD_HASH` | `python scripts/configure_owner.py` (§3) |
| `SMTP_*` | provider + verified identity (§1) |

The rest is done: manifest + installability (maskable/iOS icons, shortcuts, screenshots),
service worker with honest offline behaviour and no private data cached, robots/sitemap/
canonical/OG/Twitter/structured-data, verification meta, `noindex` on private surfaces.
Regenerate PWA art with `python scripts/pwa_assets.py` (`--icons-only` needs no browser).

Post-publish, from a machine with internet:

```bash
python scripts/verify_release.py https://your-domain <commit-sha>
python scripts/crew_smoke.py
curl -s https://your-domain/api/deploy-check | python3 -m json.tool
```

Then: Chrome/Edge install works automatically; Search Console is pre-wired (verification
meta in templates); PWABuilder/Microsoft Store/Bing are optional extras on the same
manifest.

## 10. Launch acceptance

- [ ] Domain, TLS and release SHA verified from outside the host.
- [ ] Every private API/PDF/CSV rejects anonymous calls; public enquiry still works.
- [ ] Owner login/logout, CSRF rejection and credential rotation tested.
- [ ] Real-record counts verified after migration and restart.
- [ ] Daily backup, encrypted offsite copy and independent restore drill done.
- [ ] Uptime, error and backup-failure alerts received.
- [ ] CI green; a real release deployed and its SHA checked.
- [ ] Desktop/mobile navigation, PDFs and keyboard use reviewed live.
- [ ] Dedicated Overpass capacity before sustained commercial volume.
- [ ] SMTP stays off until credentials, consent process and a test send are ready.
