# Reachmark — Render Pro deployment

## Production target
- Render workspace: Ernest Achuka
- Service: `reachmark` (Docker web service, Pro plan)
- Region: Frankfurt
- Domain: `https://reachmarkdigital.xyz`
- Health check: `/healthz`
- Persistent SQLite path: `/data/reachmark.sqlite3`
- Backup directory: `/backups`

The Flask application remains the production backend and owns the existing account, audit, enquiry, billing and admin APIs. The React 18 + Vite + TypeScript website is built into `static/site` and served by Flask. This keeps the public site and existing authenticated product on one origin.

## Before first production deploy
1. Keep Railway running. Do not delete its service, volume or database.
2. Take a consistent SQLite backup from Railway using the existing backup procedure / SQLite online backup API. Verify the backup opens and contains the expected schema and records.
3. Create the Render service from this Blueprint and attach its persistent disk at `/data`.
4. Transfer the existing production values for `SECRET_KEY`, `OWNER_PASSWORD_HASH`, `SMTP_PASSWORD`, `CRON_SECRET`, Paystack and Google OAuth/business credentials into Render's Environment page. Do not rotate `SECRET_KEY` during migration unless intentionally invalidating active sessions.
5. Restore the verified SQLite backup to `/data/reachmark.sqlite3` before routing public traffic.
6. Confirm schema/migration version, owner sign-in, client sign-in, projects, enquiries, audit records, invoices and files.
7. Smoke-test `/healthz`, homepage, free website review (`/api/public/audit`), project enquiry (`/api/enquiries`), sign-in, dashboard, admin, email and OAuth callbacks on the Render URL.
8. Only after successful verification, point `reachmarkdigital.xyz` DNS to Render and verify TLS, canonical URL, sitemap, robots, OAuth redirect URIs and mail delivery.
9. Keep Railway intact as rollback until Render has been stable and the restored database is confirmed.

## Data and scaling
The current production database is SQLite. The Blueprint intentionally creates one web instance with a persistent disk. Do not enable multiple instances or horizontal scaling while SQLite is the shared production database. PostgreSQL is a separate future migration, not an implicit part of this hosting move.

## Frontend environment
- `VITE_FORM_ENDPOINT`: defaults to the existing same-origin `/api/enquiries` endpoint.
- `VITE_AUDIT_ENDPOINT`: defaults to `/api/public/audit`.
- `VITE_WHATSAPP_URL`: optional WhatsApp deep link used as the enquiry fallback.
- `VITE_TELEGRAM_URL`: optional Telegram link used as the secondary fallback.
- `VITE_PLAUSIBLE_DOMAIN` / `VITE_UMAMI_WEBSITE_ID`: optional privacy-friendly analytics configuration (no analytics is loaded when unset).

Vite variables are public build-time values. Never put server secrets in a `VITE_*` variable.

## Static hosting alternative
The React bundle is emitted to `static/site`. A cPanel-only static export can serve the generated bundle, but the existing audit, account, portal and admin functionality still requires the Flask backend or an explicitly configured compatible API endpoint. Do not represent the standalone static copy as including those backend features.

## Quality gates
Run `npm install --no-audit --no-fund && npm run build`, `npm run typecheck`, the full Python test suite, browser flows, and a production Docker build before merging. Lighthouse scores are targets, not claims; record actual measured results after deployment.
