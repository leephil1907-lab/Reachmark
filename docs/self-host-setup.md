# Self-host setup: e-mail, social sign-in, database

Three things, in the order most owners do them. Nothing here needs a code change —
only environment variables (on Railway: the service's **Variables** tab) plus a few
fields on the workspace **Settings** page.

---

## 1. E-mail (SMTP) — makes ALL mail flow

One SMTP account drives everything: client verification e-mails, password resets,
event lead follow-ups, crew outreach, invoices. Until it is set, mail is **queued
in the outbox, never lost and never silently dropped** — the app tells you SMTP is
missing instead of pretending to send.

### Step A — get a free SMTP account (pick one)

| Provider | Free tier | Host | Port / security | Notes |
|---|---|---|---|---|
| **Brevo** (recommended) | 300 e-mails/day | `smtp-relay.brevo.com` | 587 / starttls | Sign up → SMTP & API → create key. Login is your account e-mail. |
| **SMTP2GO** | 200 e-mails/month | `mail.smtp2go.com` | 587 / starttls | Sign up → add a sending domain or verified sender. |
| **Gmail** (quick test only) | ~500/day | `smtp.gmail.com` | 587 / starttls | Needs an **App Password** (Google Account → Security → 2-Step Verification → App passwords). Mail lands in spam more often; use a real provider for production. |

### Step B — set these environment variables

```
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_SECURITY=starttls        # or: ssl (port 465)
SMTP_USER=you@yourdomain.com  # Brevo: your login e-mail. Gmail: your gmail address.
SMTP_PASSWORD=<the smtp key / app password, never your normal password>
SMTP_FROM=noreply@yourdomain.com   # must be a sender you verified at the provider
PUBLIC_BASE_URL=https://YOUR-DOMAIN   # so logos + buttons in e-mails always point at you
```

`SMTP_HOST` + `SMTP_FROM` are the minimum the app checks; without them the
workspace shows "Not connected" on the SMTP badge.
(No `PUBLIC_BASE_URL`? The app falls back to the **Public base URL** field on the
Settings page, then to the current request host.)

### Step C — fill the sender profile (workspace → Settings)

All four are **required** before any outreach/follow-up sends (the app refuses with
a message naming the missing ones):

- Sender name (e.g. `Ada Okafor`)
- Agency / studio name (e.g. `Reachmark`)
- Reply e-mail (e.g. `hello@yourdomain.com`)
- Postal address (one line is fine — legally required footer)

### Step D — verify it works

1. Open an **incognito window** → sign up a test client account → you should receive
   the verification e-mail within a minute.
2. Workspace → capture a test lead with your own e-mail → **Follow up** → it should
   report `sent` (not `queued`, not a 502).
3. If mail lands in spam: add the provider's SPF/DKIM records to your domain's DNS
   (Brevo/SMTP2GO show you the exact records; ~10 minutes, one time).

---

## 2. Google / Microsoft sign-in (OAuth)

Social buttons appear on **/signup** and **/signin** only when the matching
variables below exist — with nothing set, the pages stay clean password-only and
nothing breaks. Owner workspace sign-in (`/login`) stays password-only by design.

Your redirect URIs (register **exactly** these, `https`, no trailing slash):

```
https://YOUR-DOMAIN/api/auth/oauth/google/callback
https://YOUR-DOMAIN/api/auth/oauth/microsoft/callback
```

(For a local test: `http://localhost:5000/api/auth/oauth/google/callback` —
Google allows http only for localhost.)

### Google — ~10 minutes, free

1. [Google Cloud Console](https://console.cloud.google.com/) → new project (any name).
2. **APIs & Services → OAuth consent screen** → User type **External** → fill app
   name + support e-mail + developer contact → **Save**. (No verification needed
   while testing; add test users, or publish later.)
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID** →
   type **Web application** → under *Authorized redirect URIs* add the google
   callback URL above → **Create**.
4. Copy the **Client ID** and **Client secret** into env:

```
GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=<secret>
```

### Microsoft — ~10 minutes, free

1. [Azure Portal](https://portal.azure.com/) → **Microsoft Entra ID →
   App registrations → New registration**.
2. Name it (e.g. `Reachmark clients`), account type
   **"Accounts in any organizational directory and personal Microsoft accounts"**,
   redirect URI type **Web**, value = the microsoft callback URL above → **Register**.
3. Copy the **Application (client) ID** → `MICROSOFT_CLIENT_ID`.
4. **Certificates & secrets → New client secret** → copy the **Value** (not the ID —
   it shows once) → `MICROSOFT_CLIENT_SECRET`:

```
MICROSOFT_CLIENT_ID=<application-client-id>
MICROSOFT_CLIENT_SECRET=<secret-value>
```

### Verify

Redeploy/restart, open **/signup** in incognito: the "Continue with Google /
Microsoft" buttons appear only for providers you configured. Click one →
approve → you land on **/dashboard** with a verified client account
(`email_verified=1`, no password — password sign-in stays disabled for that
account unless you add one later).

---

## 3. Database — SQLite today, Neon Postgres possible later

**Today the app speaks SQLite only** (`prospect.sqlite3`, raw `sqlite3` module —
`?` placeholders, `INSERT OR REPLACE`, `PRAGMA busy_timeout`). There is no
Postgres driver in the codebase, so pointing it at Neon **will not work right now**.

- **Staying on SQLite is fine** for a single server: on Railway, attach a volume
  mounted at `/data` and set `DATABASE_PATH=/data/prospect.sqlite3` so data
  survives redeploys. Back up by copying the one file.
- **Neon later is possible but is real work**: a Postgres compatibility layer
  (placeholder + upsert + type translation across every query) plus a SQLite→Neon
  data migration, all kept green by the suite. Say the word and it becomes the
  next slice — estimate is a full session, not a quick toggle.

Do **not** set any `DATABASE_URL` today: nothing reads it, and the app would
silently keep using the SQLite file.

---

## 4. Subscription expiry reminders (cron)

Plans are one-off 30-day charges (no auto-renew), so the app warns paid users by
e-mail 72 hours before expiry — but something has to trigger it daily:

1. Generate a secret: `openssl rand -hex 24` (any long random string works).
2. Railway Variables → add `CRON_SECRET=<that secret>`.
3. Railway → **New → Cron Job** → schedule `0 9 * * *` (daily 09:00 UTC) →
   command:
   ```
   curl -s -X POST https://YOUR-DOMAIN/api/cron/expiry-warnings -H "X-Cron-Secret: <that secret>"
   ```
4. The endpoint replies `{"ok": true, "warned": N}`. Each user is warned **once
   per expiry** (tracked in the database), so re-runs and overlaps are harmless.
   Test it any time by running the same curl command yourself.
