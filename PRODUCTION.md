# Reachmark: production launch and operations

## What is ready, and what still needs activation

Implemented: studio-owner sessions, **client portal (signup/signin) with assigned-project and invoice visibility**, **branded invoice creator with line items, tax/discount and manual status tracking**, **Smartsupp Live Chat integration (lazy-loaded only when key is set, visible on About/Showcase/Enquire/Previews and workspace)**, CSRF checks, login throttling, secure production cookies, production startup validation, Docker/Caddy deployment files, persistent SQLite storage, scheduled snapshot service, verified offline restore, optional encrypted offsite copies, optional Sentry integration, CI/deployment workflows and post-deploy verification.

**Not yet activated:** a VPS, domain/DNS, public HTTPS certificates, GitHub deployment secrets/environment, external uptime/error/backup alerts, offsite storage and a dedicated map-data contract. There is no live production deployment to certify yet. Docker is not available in the development sandbox, so the actual container build/start must be checked by CI/on the target host. Local Python/browser/backup tests are not a substitute for that launch test.

Recommended starting architecture: a small VPS with roughly 2 vCPU, 2 GB RAM and 25+ GB disk, Docker Compose, Caddy and one threaded application worker. Reassess storage against lead/source-tag/backup growth. Do not run multiple app replicas: discovery workers use in-process coordination and startup recovery. For multiple users/replicas, migrate job coordination and storage first.

### Zero-budget path (your current situation)

You noted no funds right now. Do **not** purchase anything yet. Two safe options until budget is available:

1. **Run locally with secure sharing — no VPS needed.**
   ```bash
   docker compose up -d            # uses the same Compose file
   # then expose it safely for testing
   cloudflared tunnel --url http://localhost:8000
   # or: npx localtunnel --port 8000
   ```
   Keep the local SQLite file backed up with `python scripts/backup.py backup`. This is the fastest way to keep using the new client portal and invoices while you evaluate.

2. **Free-tier cloud (no card or with free credits).** When you do need a public URL without paying, these are the most practical:

   | Option | What you get free | Reachmark fit | Note |
   |---|---|---|---|
   | **Oracle Cloud Free Tier (Always Free)** | 2 ARM VMs (4 OCPU, 24 GB RAM total), 200 GB storage | Excellent — runs Docker Compose exactly as documented | Requires card for verification, no charge if you stay within Always Free. ARM works with the provided Dockerfile. |
   | **Fly.io Free allowance** | 3 shared VMs, 3 GB persistent volume, free bandwidth allowance | Good — `fly launch` + `fly volumes create` + `Dockerfile` | Add `[[services]]` for port 8000; keep one worker. |
   | **Render Free** | 750 h/month web service, 1 GB ephemeral (needs external DB for persistence) | Usable for demo only — persistence needs paid disk or external SQLite | Not recommended for real client data without a persistent disk. |
   | **Railway Hobby trial** | ~$5 free credit | Short demo only | Good for a day-long test, then needs payment. |

**Recommendation for now:** stay on **local Docker + Cloudflare Tunnel** for real client work, and claim the **Oracle Free Tier** ARM machine when you are ready for a 24/7 public deployment. It is the only free option that comfortably fits the recommended 2 vCPU/2 GB/25 GB spec without time limits.

### VPS comparison when you have ~$5–10/month

| Provider | Cheapest plan that fits Reachmark | Specs | Why consider it |
|---|---|---|---|
| **Hetzner CX22** | ~**€4.15/mo (~$4.50)** | 2 vCPU, 4 GB RAM, 40 GB SSD, 20 TB traffic | Best price-to-performance in EU; clean Docker/Caddy install (Ubuntu 24.04). |
| **Contabo Cloud VPS S** | ~**€4.50/mo** | 4 vCPU, 8 GB RAM, 50 GB SSD | More RAM for less, but older hardware reports; support slower. |
| **Hostinger KVM 1** | **~$6–7/mo** | 1 vCPU, 4 GB RAM, 50 GB NVMe, weekly backups | Includes backups/DDoS; easy panel. |
| **DigitalOcean Basic** | **$6/mo** | 1 vCPU, 1 GB RAM, 25 GB SSD | Great docs, but 1 GB is tight for Reachmark + backups; next size $18. |
| **Vultr / Linode** | **$5–6/mo** | 1 vCPU, 1 GB RAM, 25–30 GB SSD | Similar to DO; $6–12 plans are more comfortable. |

**When you move off free:** **Hetzner CX22** is the recommended starting point on a tight budget — it exceeds the minimum spec for Reachmark at the lowest price, with EU data centers closer to Nigeria than US-only hosts. If you prefer a US provider with simpler billing, use **Hostinger KVM 1** or **DigitalOcean $12/mo (2 GB)** plan. Avoid the $5/1 GB plans for production if you keep many leads and daily backups on the same disk.

All paid options still need a **domain (~$10–15/yr, e.g., Namecheap/Cloudflare Registrar)** for HTTPS. No purchase is made by this repo.

## 0. Live support chat (Smartsupp) — ready for connection

Reachmark ships with **Smartsupp Live Chat** (https://www.smartsupp.com). The widget is **disabled by default** and loaded only when you provide a key — no tracking scripts, no heavy bundle, no mock data.

**Connect in 3 minutes:**

1. Create account at https://www.smartsupp.com → **Settings → Chat widget → Chat code**. Copy the `key` value (e.g., `abcd1234...`).
2. **Option A — inside the app (fastest):** Open **Workspace → Settings → Smartsupp Live Chat key**, paste the key, **Save sender profile**. The chat appears immediately on **/about, /showcase, /enquire, /preview/** and the workspace.
3. **Option B — server env (for Docker/Oracle):** add to `.env.production` on the VPS:
   ```dotenv
   SMARTSUPP_KEY=your-key-here
   ```
   then `docker compose up -d`. Env takes precedence over the database value.

Verify: open `/about` in a private window — you should see the Smartsupp bubble. If blank, check the key at https://dashboard.smartsupp.com. Leave blank or remove `SMARTSUPP_KEY` to disable. The integration uses the official loader (`https://www.smartsuppchat.com/loader.js`) with `async` — no CSP change needed with the default headers. For strict CSP, allow `script-src https://www.smartsuppchat.com https://*.smartsupp.com`.

**Tip:** In Smartsupp Dashboard → Customize → Chat widget, set your studio name, logo (`static/logo-primary.svg`), and offline form. The widget appears on every public page once enabled — perfect for answering project enquiries live.

## 1. Accounts and network

1. Choose a VPS provider and a domain registrar. No purchases are made by these files.
2. Create an unprivileged deployment user with SSH-key access. Docker group membership grants powerful host access; restrict this account and key accordingly.
3. Install Docker Engine and Compose. Keep the host updated. Allow public TCP 80/443 (UDP 443 optional), restrict SSH, and do not publish port 8000.
4. Point the domain's A record to the VPS. Only publish AAAA if IPv6 works. Remove conflicting web servers from ports 80/443.
5. Copy this source to `/opt/reachmark`. Do not copy development `.env`, database files or backup directories through Git.

## 1.5 Oracle Cloud Free Tier — full VM + domain setup (recommended zero-budget 24/7 host)

This is the complete path to get Reachmark on **Oracle Always Free** ARM (4 OCPU, 24 GB RAM, 200 GB) — the same `compose.yaml` you already run locally.

**A. Create the Oracle VM**

1. Create account at https://cloud.oracle.com → **Sign up for Free Tier** (card is verified, no charge if you stay Always Free).
2. Console → **Compute → Instances → Create instance**
   - Name: `reachmark`
   - Image: **Canonical Ubuntu 24.04**
   - Shape: **Ampere Altra (ARM)** — `VM.Standard.A1.Flex` → **OCPU 4, RAM 24 GB** (free limit total per tenancy)
   - Add SSH key: paste your *public* key (`cat ~/.ssh/id_ed25519.pub` on your laptop)
   - VCN: create new VCN with internet gateway (default)
   - Boot volume: 50 GB (free allowance 200 GB)
3. **Open firewall:** VCN → your VCN → Security Lists → Default Security List → **Add Ingress Rules** → `0.0.0.0/0` ports **80** and **443** (TCP). Also on VM:
   ```bash
   ssh ubuntu@<public-ip>
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```

**B. Prepare the host (same as any VPS)**

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install docker.io docker-compose-plugin git -y
sudo usermod -aG docker ubuntu && newgrp docker
# Optional swap (Oracle ARM is fast enough, skip if RAM >= 12GB)
sudo mkdir -p /opt/reachmark && sudo chown ubuntu:ubuntu /opt/reachmark
git clone https://github.com/leephil1907-lab/sitegapreveal.git /opt/reachmark
cd /opt/reachmark
```

**C. Domain and DNS (required for HTTPS)**

1. Buy a domain (Namecheap / Cloudflare Registrar ~$10/yr) or use a free Cloudflare-proxied subdomain.
2. In your registrar: add **A record** `yourstudio.com → <Oracle public IP>` (and `www` if desired). Wait 2–30 min.

**D. First launch with owner password + Smartsupp**

```bash
cd /opt/reachmark
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/configure_owner.py
# prompts for: your FULL domain (e.g., reachmark.studio) + 16+ char owner password
printf 'DOMAIN=yourstudio.com\n' > .env && chmod 600 .env
# Optional live chat — paste your Smartsupp key or leave empty:
# echo 'SMARTSUPP_KEY=your-key' >> .env.production
# Optional SMTP + SENTRY add to .env.production as well (never .env)
touch .env.backup && chmod 600 .env.backup
docker compose build --build-arg RELEASE_SHA="$(git rev-parse HEAD)"
docker compose up -d
docker compose logs -f   # watch Caddy fetch LetsEncrypt cert (30–60s)
```

Visit **https://yourstudio.com/login** → sign in with owner password. No username needed.

**E. Verify + keep it alive**

- `curl -i https://yourstudio.com/healthz` → `200` and `release` SHA
- Settings → paste **Smartsupp key** → chat appears on `/about`
- Backups: `docker compose logs backup` should show `Snapshot OK`. Configure `.env.backup` later for offsite restic.
- Keep Oracle VM Always Free: don't stop for too long, keep boot volume <200 GB, stay in `A1.Flex` shape. Set email alert in Oracle → Billing → Budgets.

To update after a push: `git pull && docker compose build --build-arg RELEASE_SHA="$(git rev-parse HEAD)" && docker compose up -d`.

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
- **Projects & follow-ups** links leads, contracts, scope, draft quote, stage, next action and due date. Overdue/today reminders use UTC calendar dates and are shown in-app only. Assign a project to a client’s email and it appears in their portal; unassigned projects remain studio-only.
- **Client portal (new):** visitors sign up at `/signup` and sign in at `/signin` (client login). No invitation code is needed. Clients see **only** invoices and projects assigned to their email — they never see the lead directory, global discovery, website health, contracts, or studio settings. The owner still uses `/login` with the studio password. Share a project or invoice by entering the client’s registered email; the system links it via `client_user_id` and shows it on next client login. No payment provider is charged.
- **Invoices (new, AllScale-inspired workflow, original Reachmark design):** owner-only creation. Add 1–25 line items (description, quantity up to 2 decimals, unit price), choose currency (13 supported), tax 0–100%, discount none/percent/fixed, issue/due dates, linked project or business, notes and terms. Totals are computed locally as `(Σ qty×unit) – discount + tax`; no automatic currency conversion. Statuses: **Draft, Sent, Paid, Overdue, Cancelled** — **Paid is manual** (mark only after you confirm bank/wallet receipt). Branded PDFs (`/api/documents/invoice/<id>.pdf`) are available to the owner and to the assigned client. No e-signature, automated charging, or stablecoin payment is performed; this is a manual record, not a payment gateway.
- Audit PDFs download from business details. Draft proposal/quote and brief PDFs download from saved projects — assigned clients can also download their project’s proposal/brief PDFs. Contract-record PDFs download from Contracts. PDFs contain saved data, not invented prices, legal terms or acceptance. Review all content before sharing; a manually recorded contract stage is not an e-signature or verified payment receipt.
- No project or invoice transition sends email, executes an MCP tool, signs an agreement or charges money. Existing explicit approval gates remain. Client status changes are shown in-app only.

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
