# Reachmark

Find potential. Make your mark.

## Primary production architecture

Reachmark's canonical production deployment is **Docker Compose on a persistent Linux host**, fronted by **Caddy** for HTTPS.

- `app`: Reachmark Flask + Gunicorn image from GHCR.
- `caddy`: TLS termination and reverse proxy.
- `backup`: isolated daily SQLite snapshots.
- SQLite lives at `/data/reachmark.sqlite3` on the persistent `reachmark_data` volume.
- Backups live on `reachmark_backups`.
- Releases are immutable GHCR images tagged with the exact Git commit SHA.
- Production configuration lives in `.env.production`; backup configuration lives in `.env.backup`.
- Railway is not the canonical production target.

## Release gates

A production release is permitted only after:

1. Python unit/integration tests pass.
2. Playwright production flow passes on desktop and mobile.
3. Playwright map flow runs **independently** and passes.
4. Core SQLite migrations apply cleanly, including `source_seen_at`.
5. API authorization regression matrix passes.
6. Mobile/PWA audit passes.
7. Lighthouse mobile and desktop gates pass for performance, accessibility, best practices, and SEO.
8. Docker image builds successfully.
9. The deployment verifier confirms HTTPS health, exact release SHA, and private API access.

## Development

```bash
cp .env.example .env
pip install -r requirements.txt
npm ci
npm run build
python -m unittest tests.test_app tests.test_operations tests.test_maps.MapTests tests.test_production tests.test_crew tests.test_video tests.test_receptionist_page tests.test_brain tests.test_design tests.test_adsense tests.test_authorization -q
```

For production environment preparation, use `.env.production.example` and `.env.backup.example`, then populate the real files only on the deployment host.

## Live

The public URL is supplied through `PUBLIC_BASE_URL`; do not hard-code a temporary deployment host into release configuration.