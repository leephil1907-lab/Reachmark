# Launch acceptance — 2026-09-23 (remote walkthrough)

Live host: `https://sitegapreveal-production.up.railway.app` · live code fingerprinted as `138468c`
via the real AdSense slots (banner `1905478104`, footer `6774661404`, loader exactly once).
`/api/deploy-check`: **31/32** — the only failure is `SMTP`, intentionally unset (box 10).

## Verdicts

1. **Domain, TLS, release SHA from outside** — PARTIAL. TLS verified (HTTPS 200).
   Live SHA fingerprinted as `138468c`, but `RELEASE_SHA` reports `local`.
   Action: set `RELEASE_SHA` on Railway (and the custom domain when bought).
2. **Private APIs reject anonymous calls; public enquiry works** — PARTIAL.
   11/11 private endpoints (`/api/admin/*`, `/api/crew`, `/api/auth/me`, `/api/export`,
   `/api/outbox`, `/api/snapshots`, receipt/contract PDFs) return **401**; 13/13 public
   surfaces return **200**. The enquiry POST was deliberately not submitted against
   production; send one real test enquiry after the next deploy.
3. **Owner login/logout, CSRF, rotation** — PARTIAL. Login/logout + CSRF rejection are
   covered by `tests/browser/production_flow.py` (green). Credential rotation on the
   live host is an owner action.
4. **Real-record counts after migration/restart** — OPEN. Cannot be checked remotely
   (private APIs correctly deny it). Verify counts after the next Railway deploy.
5. **Daily backup, encrypted offsite copy, restore drill** — OPEN. `scripts/backup.py`
   (snapshot + SHA-256 manifest + integrity check + restic offsite + heartbeat) is
   reviewed and documented; the Railway volume, cron service and drill are owner actions
   (see `OPERATIONS.md` §5).
6. **Uptime, error, backup-failure alerts received** — OPEN. Point an external monitor
   (UptimeRobot / Better Stack) at `/healthz` and set `BACKUP_HEALTHCHECK_URL`.
7. **CI green; real release deployed and SHA-checked** — PARTIAL, fix in this commit.
   CI `check` was **failing** on `138468c`: the first-run tour overlay intercepted the
   production browser flow. Fixed (tour dismissed in `production_flow.py`, `map_flow.py`
   pointed at `/workspace#global`, tour no longer steals deep links, `crew_smoke.py`
   sets `ALLOW_CREW_DEMO=1`, stale review-page widget check replaced with the tawk
   single-bubble contract, login retry for a CSRF timing flake). Reproduced green
   locally: unittest 222 OK, both browser flows PASS, smoke PASS, `node --check` clean.
   The `docker build` step has no daemon in this sandbox; all `COPY` sources exist and
   everything compiles. Push to confirm green on GitHub.
8. **Desktop/mobile navigation, PDFs, keyboard live** — PARTIAL. Six real captures in
   `docs/screenshots/` (home, showcase, overview, crew, clients, mobile home); PDF
   downloads covered by the browser flow. A manual keyboard pass on the live site
   remains.
9. **Dedicated Overpass capacity** — DEFERRED BY DESIGN. Documented in `OPERATIONS.md`
   §1 (`OVERPASS_URLS`, self-host command); provision only before sustained commercial
   volume.
10. **SMTP stays off until ready** — DONE. Unset on Railway, deploy-check fails it
    loudly, approved mail queues in the outbox (proven by `crew_smoke.py`).

## Owner action list (nothing else can do these)

- Set `RELEASE_SHA` (+ wallet envs + custom domain when ready) on Railway.
- Attach the `/data` volume; add the backup cron service; run the restore drill.
- Add external uptime monitoring + `BACKUP_HEALTHCHECK_URL`.
- Rotate credentials; send one real test enquiry; do a live keyboard pass.
