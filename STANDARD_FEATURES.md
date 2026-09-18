# Reachmark — Reachmark-standard upgrades (added 2026-09-18)

Your premium site is **untouched** — `templates/about.html` (Founder story + pricing + dark nav + 200px tight logo + tawk 300×360) not altered. All new features are additive layers.

## 1) Auth hardening — email verification + password reset
- **Signup** now creates `email_verified=0`, generates 24h `verification_token`, sends branded email (or queues to `mail_outbox` if SMTP not set). Still logs in immediately — `needs_verification` flag returned, client sees yellow banner in workspace (`#verify-banner`) and dot in profile.
- **Login** returns `needs_verification` and `X-Needs-Verification` header if unverified, but still allows access (tests pass, no lockout surprise).
- **Verify**: `GET /verify/<token>` — validates expiry (24h), sets `email_verified=1`, shows success page with Reachmark branding. Resend via `POST /api/auth/request-verification` (throttled to 1h).
- **Forgot**: `GET /forgot` (form) → `POST /api/auth/forgot` (always 200 to avoid enumeration, 60min one-time token, branded email). `GET /reset/<token>` + `POST /api/auth/reset` (8+ chars, one-time, invalidates token).
- **Pages** styled like `auth-card` (white 22px, DM Sans/Manrope), public via `security.py` whitelist, no owner login needed.

## 2) GDPR-standard — export & close
- `GET /api/auth/export` — returns `{account, projects, invoices}` JSON for the logged-in client. Triggered via sidebar **Export my data** button (creates download `reachmark-export-*.json`).
- `POST /api/auth/close` — requires `{"confirm":"close"}`, sets `is_active=0`, clears session, logs. Client can’t log in after. Owner still retains invoices/projects for records. UI in `#client-account` box (only for `role=client`).

## 3) Snapshots & rollback — config versioning
- Table `snapshots(id, data, note, created, created_by)` — captures `settings` JSON + counts (`leads`, `enquiries`, `invoices`, `projects`, `users`).
- `POST /api/snapshots` (owner, CSRF) — creates snapshot, prunes >50.
- `GET /api/snapshots` — list.
- `POST /api/snapshots/<id>/rollback` — restores `settings` row. Logged as `snapshot`.
- Reachmark parity: publish gated by verify, rollback in one click. Tested with owner session (`DASHBOARD_PASSWORD`).

## 4) Mail outbox & 9 branded templates
- Table `mail_outbox(id, to_email, subject, body, html, created, state)` — queued when `SMTP_HOST`/`SMTP_FROM` missing or send fails. Seen at `GET /api/outbox` (owner), detail `GET /api/outbox/<id>`, resend `POST /api/outbox/<id>/resend` (uses live SMTP).
- Branded HTML helper `branded_html(title, body, cta)` — white card, Reachmark header, lime CTA (`#0f1a0a`/`#d5f268`), footer `Global`.
- `GET /api/mail-templates` — 9 templates: welcome, verify_success, reset_request, reset_done, enquiry_received, enquiry_owner, preview_shared, invoice_sent, project_update — matches Reachmark count.

## 5) Deploy check & config verifier
- `GET /api/deploy-check` — public (noindex). Returns `{ok, checks:[{name, ok, detail, required}], release}`. Checks `PUBLIC_BASE_URL` (must `https://`), `SECRET_KEY` (32+), `OWNER_PASSWORD_HASH` (scrypt/pbkdf2), `DATABASE_PATH` (absolute), `SMTP`, `GOOGLE_SITE_VERIFICATION`, `SITEMAP` (12 URLs), `LIVE_CHAT` (tawk `6aaca920...`). Local fallback via `tools/deploy_check.py`.
- `GET /api/verify-config` (owner) — refuses to ship if `agency` empty, `public_base_url` wrong, or `SAMPLES !=8`. Prevents invented figures (Reachmark assembler verifier).
- `tools/audit_responsive.py` — 50 viewports (320→1920, incl. 360), checks `viewport` meta + fixed widths without `max-width`. Current site: 0 issues.
- `tools/deploy_check.py` — calls live `/api/deploy-check` or local env.

## 6) Security hardening (Reachmark parity)
- `security.py` public list now includes `/forgot`, `/reset/*`, `/verify/*`, `/api/auth/*` (verify/forgot/reset), `/api/deploy-check`.
- `owner_guard` `allowed_prefixes` extended for `export`, `close`, `request-verification` — client CSRF still enforced on writes.
- Session `email_verified` exposed via `GET /api/auth/me` (`email_verified`, `is_active`).

## UI touches (additive only)
- `client_login.html` — added **Forgot password?** + **Resend verification** link + JS.
- `signup.html` — shows green hint “verification email sent” when `needs_verification`, resend handler.
- `index.html` (workspace, not marketing) — yellow `#verify-banner` + profile dot when `email_verified===false`; sidebar `#client-account` with Export/Close; no changes to `about.html`.

## Tests
- `python -m unittest -q` — 87 OK (unchanged).
- Integration (isolated DB): signup→verify→login→forgot→reset→export→deploy-check→snapshots→rollback→outbox→templates→verify-config→close→home still shows Founder + G-CPSB1EDNFE.
- Responsive audit: 0 issues.

## What wasn’t touched
- `templates/about.html` — Founder (grid, avatar R, Global, signature) + Pricing (3 tiers) + hero + premium.css + tawk config + SEO (ClnMo7..., G-CPSB1EDNFE, GT-M6XWG99J, GTM-M3SJZ8S7, sitemap 12) — all byte-identical.
- No demo leads, no invented metrics, no MCP, no SmartSup, real OSM+CSV, real SMTP.

## Next (optional, not required now)
- i18n 6 locales (if you want Global), separate admin process on `127.0.0.1:8787` loopback (currently same Flask but `noindex` + hidden via 5-click logo), Playwright capture of 6 real product screenshots.

To go live: set `PUBLIC_BASE_URL=https://reachmark.co`, `SECRET_KEY`, `OWNER_PASSWORD_HASH`, `DATABASE_PATH=/data/prospect.sqlite3`, `SMTP_*` — then `python tools/deploy_check.py --url https://reachmark.co/api/deploy-check`.
