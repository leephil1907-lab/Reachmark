# Reachmark: production launch and operations

## What is ready, and what still needs activation

Implemented: owner sessions, CSRF checks, login throttling, secure production cookies, production startup validation, Docker/Caddy deployment files, persistent SQLite storage, scheduled snapshot service, verified offline restore, optional encrypted offsite copies, optional Sentry integration, CI/deployment workflows and post-deploy verification.

**Not yet activated:** a VPS, domain/DNS, public HTTPS certificates, GitHub deployment secrets/environment, external uptime/error/backup alerts, offsite storage and a dedicated map-data contract. There is no live production deployment to certify yet. Docker is not available in the development sandbox, so the actual container build/start must be checked by CI/on the target host. Local Python/browser/backup tests are not a substitute for that launch test.

Recommended starting architecture: a small VPS with roughly 2 vCPU, 2 GB RAM and 25+ GB disk, Docker Compose, Caddy and one threaded application worker. Reassess storage against lead/source-tag/backup growth. Do not run multiple app replicas: discovery workers use in-process coordination and startup recovery. For multiple users/replicas, migrate job coordination and storage first.

## 1. Accounts and network

1. Choose a VPS provider and a domain registrar. No purchases are made by these files.
2. Create an unprivileged deployment user with SSH-key access. Docker group membership grants powerful host access; restrict this account and key accordingly.
3. Install Docker Engine and Compose. Keep the host updated. Allow public TCP 80/443 (UDP 443 optional), restrict SSH, and do not publish port 8000.
4. Point the domain's A record to the VPS. Only publish AAAA if IPv6 works. Remove conflicting web servers from ports 80/443.
5. Copy this source to `/opt/reachmark`. Do not copy development `.env`, database files or backup directories through Git.

## 2. Owner credentials and first launch

From `/opt/reachmark`, create configuration **on the server**, not in chat:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/configure_owner.py
# Prompts for an owned domain and a 16+ character password; writes mode-0600 .env.production.
printf 'DOMAIN=your-owned-domain.example\n' > .env
chmod 600 .env
# Optional backup credentials belong here, never in source control:
touch .env.backup && chmod 600 .env.backup
docker compose build --build-arg RELEASE_SHA="$(git rev-parse HEAD)"
docker compose up -d
```

Caddy requests/renews HTTPS certificates only when a real domain resolves correctly and ports are reachable. Visit `/login` to sign in. The owner username is not required: this is a single-owner password login. Sessions last up to eight hours, have HttpOnly/SameSite=Strict cookies and use Secure cookies in production. Writes require the session CSRF token. Five failed login attempts per trusted client address trigger a 15-minute block. This is not MFA; consider an external identity gateway with MFA for additional protection.

Production must set `APP_ENV=production`, a 32+ character `SECRET_KEY`, `OWNER_PASSWORD_HASH`, HTTPS `PUBLIC_BASE_URL`, and absolute persistent `DATABASE_PATH`. The helper creates a scrypt password hash; preserve single quotes around it in the env file so `$` separators survive dotenv parsing. Missing requirements prevent startup. `DASHBOARD_PASSWORD` Basic auth is a development compatibility feature, not the production authentication method.

Public pages: about/showcase/enquiry, health, static assets, explicitly shared token previews and unsubscribe links. Contacts, lead exports, analytics, MCP credentials/results, contracts, projects, PDF documents and operations status require owner access. Share previews intentionally: their token URLs expose the public concept. HTTPS alone is not authorization.

Keep `SECRET_KEY` and owner password recovery material in a password manager. There is no emailed password-reset flow. Rotate the hash in `.env.production` and recreate the app to reset access; credential rotation invalidates existing owner sessions. Back up configuration separately and encrypted.

## 3. Import your existing real workspace

The source ZIP intentionally does **not** contain contacts or the live database. Make a SQLite-aware snapshot, not a raw copy of an active WAL database:

```sh
python scripts/backup.py backup --database /path/to/existing/prospect.sqlite3 --directory /private/export
```

Transfer the generated `.sqlite3` and matching `.json` manifest to a private directory on the VPS over SSH. Stop writers before restoring:

```sh
docker compose stop app backup
docker compose run --rm --no-deps -v /absolute/private/export:/restore:ro app \
  python scripts/backup.py restore --snapshot /restore/EXACT-SNAPSHOT.sqlite3 --confirm-app-stopped
docker compose up -d
```

Use a directory/files readable by container UID 10001; never make private backups world-readable. Verify original lead/contract/project counts after launch. Source-seen time for legacy records is initialized from the original save timestamp, not fabricated recent verification.

## 4. Backups and restore drills

The backup service takes a snapshot immediately and then every 24 hours, retaining 14 successful local snapshots. SQLite's online backup API captures a consistent snapshot while the app runs. Every snapshot gets an integrity check, SHA-256 manifest and table counts. Files have mode 0600. Failed jobs retry after five minutes, log a clear failure and do not update successful-backup time. Docker health becomes unhealthy after 26 hours without success; Settings shows the observed backup age.

**A local volume is not disaster recovery.** Configure encrypted offsite storage before relying on production data:

```dotenv
# .env.backup — example names only; use your actual private credentials
RESTIC_REPOSITORY=s3:https://your-storage-endpoint/private-bucket
RESTIC_PASSWORD='a-strong-separate-encryption-password'
AWS_ACCESS_KEY_ID='your-key'
AWS_SECRET_ACCESS_KEY='your-secret'
BACKUP_HEALTHCHECK_URL=https://hc-ping.com/your-private-check-id
```

Initialize the repository once using the backup container (`docker compose run --rm --no-deps backup restic init`). When RESTIC_REPOSITORY is set, success is recorded only after the encrypted offsite copy succeeds. Schedule and test a sensible remote `restic forget --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune` policy separately; local retention does not prune remote snapshots. Preserve the encryption password outside the host.

The optional Healthchecks-compatible heartbeat reports success and failures. Configure its schedule as daily, with a two-hour grace period and email alerts. Test both a missed heartbeat and an explicit failure. Docker health status alone does **not** email anyone or restart unhealthy containers.

Restore only with the app and backup writer stopped. The restore command validates the manifest and database, snapshots the current destination for safety, removes obsolete WAL/SHM files and atomically replaces it. It requires `--confirm-app-stopped`; that is an operator assertion, not process detection. Never restore over a live writer. After restoring, restart, sign in, compare record counts, inspect a real lead/project and download a PDF. Test a complete offsite restore on a separate host at least monthly. Automated regression tests cover snapshot → delete → restore and reject a corrupted snapshot.

## 5. Monitoring and email alerts

Recommended: an **external uptime service such as Better Stack or UptimeRobot delivering email alerts**, independent of Reachmark SMTP. Configure HTTPS GET `/healthz`, expect HTTP 200 and `status=ok`, and test an outage/recovery. The endpoint queries SQLite and returns the deployed `release` SHA, not private data. It is a reachability/database health check, not proof that external map, email or MCP providers work.

Optional Sentry: set `SENTRY_DSN` in `.env.production`. Request/user data, breadcrumbs, local variables and exception messages are stripped from outbound error events; inspect protected server logs for full diagnosis. Test with a controlled staging error and confirm receipt. Do not add a public “crash test” endpoint. Sentry is not enabled until configured, and caught provider failures may appear as failed tasks rather than uncaught exceptions.

Monitor backup heartbeats, disk space, container restart counts and database growth in addition to HTTP uptime. Contact destination and external monitor accounts still need your setup. SMTP configuration remains independent and optional for these external alerts.

## 6. CI, GitHub pushes and verified deployments

`ci.yml` tests Python, builds the local JS bundle, runs browser regressions and builds the container on pushes/PRs. A real GitHub Actions run still needs to be observed after these files are pushed.

`deploy.yml` builds a commit-tagged GHCR image, snapshots the running database, transfers approved Compose/Caddy configuration, deploys, reloads Caddy and calls `scripts/verify_release.py`. It verifies HTTPS, the **exact expected commit SHA** and unauthenticated denial for private APIs. HTTP 200 alone does not count as a successful deployment.

Configure a protected **production** GitHub environment with required reviewers and these secrets:
- `DEPLOY_SSH_KEY`: dedicated deployment SSH private key.
- `DEPLOY_KNOWN_HOSTS`: independently verified server host-key line, not an unverified runtime ssh-keyscan.
- `DEPLOY_HOST` and `DEPLOY_USER`.
- Environment variable `PRODUCTION_URL`: your HTTPS origin.

The owner provisions `/opt/reachmark`, `.env`, `.env.production`, `.env.backup` and the initial healthy Compose stack once. The VPS must be able to pull the GHCR image: make the code-only image public or configure a read-packages credential securely on the host. No database/environment file is baked into it.

Deploy manually via **Deploy approved production release** first. For deployments after successful main-branch push CI, set repository variable `ENABLE_AUTO_DEPLOY=true`; keep environment review protection. It defaults off. Pull requests/fork workflow runs cannot trigger the privileged deploy path. Pause active discovery before approving a release; interrupted map cells are resumable but old city jobs do not automatically resume.

If verification fails, the workflow fails; it does not silently declare success or automatically restore an old database. Review logs and roll back to the last known-good image by setting the final REACHMARK_IMAGE value in `.env` and running `docker compose up -d --no-build`. Take a snapshot before data rollback. GitHub push success and production deployment success are separate events.

## 7. Lead quality, documents and workflow

- Directory filters now include location, category, email/phone availability and manual verification.
- Duplicate candidates use matching phone, email or name+city/address, capped explicitly; shared branches may match. Never auto-merge/delete.
- Source/import timestamp, automated URL-check timestamp and manual-review timestamp remain distinct.
- A manually reviewed URL-unavailable conclusion requires an evidence URL and notes. “No site found in research” is not a universal absence claim. Editing the listed website clears stale manual verification.
- **Projects & follow-ups** links leads, contracts, scope, draft quote, stage, next action and due date. Overdue/today reminders use UTC calendar dates and are shown in-app only.
- Audit PDFs download from business details. Draft proposal/quote and brief PDFs download from saved projects. Contract-record PDFs download from Contracts. PDFs contain saved data, not invented prices, legal terms or acceptance. Review all content before sharing; a manually recorded contract stage is not an e-signature or verified payment receipt.
- No project transition sends email, executes an MCP tool, signs an agreement or charges money. Existing explicit approval gates remain.

## 8. Launch acceptance checklist

- [ ] Domain, TLS and correct release SHA verified from outside the host.
- [ ] Every private API/PDF/CSV rejects an unauthenticated request; public enquiry still works.
- [ ] Owner login, logout, CSRF rejection and credential rotation tested.
- [ ] Original real-record counts verified after migration and restart.
- [ ] Daily backup, encrypted offsite copy and independent restore drill completed.
- [ ] Uptime, error and backup failure alerts received at the intended address.
- [ ] CI passed; a real release deployed and its SHA checked.
- [ ] Desktop/mobile navigation, PDFs and keyboard use reviewed on the deployed site.
- [ ] Dedicated Overpass capacity configured before sustained commercial volume.
- [ ] SMTP remains disabled until credentials, consent process and a reviewed test send are ready.
