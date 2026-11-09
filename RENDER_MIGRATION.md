# Reachmark — Render production migration

## Target
- Render web service: `reachmark`
- Runtime: Docker (the existing Flask + React application)
- Region: Frankfurt
- Production domain: `https://reachmarkdigital.xyz`
- Health check: `/healthz`
- Persistent disk: `/data` (1 GB initial allocation)
- SQLite database: `/data/reachmark.sqlite3`
- Backups: `/data/backups`

## Critical migration rules
1. Do not delete, suspend, or overwrite the Railway service or its volume during cutover.
2. Take and verify a consistent SQLite backup before migration. Use SQLite's online backup API or stop writes briefly before copying; do not copy a live database file blindly.
3. Preserve the current `SECRET_KEY`, `OWNER_PASSWORD_HASH`, `SMTP_PASSWORD`, and `CRON_SECRET` from Railway by transferring them directly into Render's Environment page. Never commit or paste them into GitHub.
4. Preserve all optional provider keys that are enabled in production (Paystack, Sentry, Google APIs/OAuth, WhatsApp, and any AI provider).
5. Restore the database to the Render disk before allowing production traffic. Confirm schema/migration version, user accounts, leads, enquiries, audit events and admin access.
6. Run a read-only smoke test on the Render URL before changing DNS. Verify `/healthz`, homepage, sign-in, dashboard, public audit, enquiry submission, email delivery, admin, and PWA assets.
7. Change DNS only after the new service is healthy and the restored database is verified. Keep Railway intact for rollback until the Render service has been stable.
8. After DNS cutover, verify HTTPS, canonical URLs, OAuth callback URLs, Search Console, sitemap, robots.txt, AdSense, and email delivery.

## Secrets
The Blueprint intentionally declares sensitive values as `sync: false`. Enter the existing production values directly in Render Dashboard → Reachmark → Environment. Do not generate a new session secret during migration unless intentionally invalidating existing sessions.

## SQLite and scaling
The application currently uses SQLite. A single Render instance with a persistent disk is the safe first migration target. Do not add multiple instances or horizontal autoscaling while SQLite is the shared production database. A later PostgreSQL migration should be a separate tested project with schema, data, and rollback plans.

## Deploy configuration
The root `render.yaml` uses the existing Dockerfile. The Docker image starts through `scripts/start.sh`, which performs production environment validation and starts Gunicorn. Render deploys from `main` after the reviewed changes are merged.

## Acceptance checklist
- [ ] Backup checksum and restore verification recorded
- [ ] Render Pro workspace and service plan confirmed
- [ ] All required secrets copied directly in Render Dashboard
- [ ] Persistent disk attached at `/data`
- [ ] Database and migration version verified
- [ ] Health check returns HTTP 200
- [ ] Login, admin, public audit, and enquiry paths verified
- [ ] SMTP and OAuth integrations verified
- [ ] Custom domain and TLS verified
- [ ] Railway retained as rollback until stability window passes
