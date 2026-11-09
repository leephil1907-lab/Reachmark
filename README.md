# Reachmark Digital

**Find the leak. Win them with proof.**

Reachmark is a website review and digital build studio for Web3 founders and businesses across real estate, manufacturing, services, e-commerce and technology.

## Product architecture

- **Public website:** React 18, Vite, TypeScript, Tailwind CSS, Framer Motion, React Router, Lenis and lucide-react.
- **Application backend:** existing Flask API and account system, retained for secure sign-in, client data, admin tools, audit workflows and persistent records.
- **Database:** SQLite on a persistent Render disk for the current single-instance deployment. A PostgreSQL migration is a separate, tested project.
- **Hosting:** Render Pro (Frankfurt) using the repository Dockerfile and `render.yaml`. Railway remains a rollback source until production data and routes are verified.
- **Static option:** React's `dist/` output can be uploaded to Namecheap cPanel for the public marketing pages. The authenticated portal, admin tools and audit APIs still require the Flask backend and persistent database.

## Local development

Requirements: Python 3.11+, Node.js 20+, npm.

```bash
cp .env.example .env
npm install
npm run dev
```

Vite runs on port 5173. Run the existing Flask backend separately:

```bash
pip install -r requirements.txt
python -m flask --app web.app run --host 0.0.0.0 --port 8000
```

Production-style frontend build:

```bash
npm run typecheck
npm run build
```

Vite writes the public website to `dist/`. The production Docker image builds this directory and Flask serves the React app at `/`, `/work`, `/work/:slug`, `/services` and `/process`. Existing server-side routes such as `/signin`, `/dashboard`, `/admin`, `/api/*`, legal pages and review endpoints remain intact.

## Environment variables

### Public website (Vite)

| Variable | Purpose |
| --- | --- |
| `VITE_FORM_ENDPOINT` | HTTPS endpoint receiving the project inquiry JSON |
| `VITE_WHATSAPP_NUMBER` | WhatsApp fallback number in international digits, no plus sign |
| `VITE_TELEGRAM_URL` | Telegram contact URL fallback |
| `VITE_PLAUSIBLE_DOMAIN` | Optional Plausible domain; analytics stays disabled when blank |
| `VITE_ANALYTICS_SRC` | Optional analytics script URL |

If no form endpoint is configured, the inquiry form opens the configured WhatsApp or Telegram fallback with the inquiry details. If no fallback is configured, it displays the studio email address instead of claiming the enquiry was sent.

### Flask application (Render)

Set runtime secrets directly in Render → Reachmark → Environment. Never commit production secrets or expose them through Vite's `VITE_*` variables.

Required: `SECRET_KEY`, `OWNER_PASSWORD_HASH`, `PUBLIC_BASE_URL`, `DATABASE_PATH`.

Preserve existing production values for SMTP, OAuth, Paystack, scheduled tasks and enabled integrations. Use `/data/reachmark.sqlite3` on the attached persistent disk.

## Deploy to Render

1. Connect `leephil1907-lab/Reachmark` to the confirmed Render workspace **Ernest Achuka**.
2. Apply the reviewed `render.yaml` Blueprint for the `reachmark` Docker web service, Frankfurt region, Pro plan and persistent `/data` disk.
3. Set the required production secrets in the Render dashboard.
4. Restore a verified SQLite backup to `/data/reachmark.sqlite3` before allowing production writes.
5. Verify `/healthz`, homepage, website review, enquiry handling, sign-in, client dashboard, admin, email and scheduled jobs.
6. Add `reachmarkdigital.xyz` as the custom domain and verify TLS, canonical URLs and OAuth callback URLs.
7. Keep Railway and its volume intact until Render has passed the stability window.

Do not run multiple app instances while SQLite is the shared production database.

## Deploy the static public website to Namecheap cPanel

```bash
npm install
npm run build
```

Upload the contents of `dist/` to the document root. Configure the host to rewrite unknown public routes to `index.html` so React Router can handle `/work/*`, `/services` and `/process`. The static site alone does not provide the authenticated portal, admin tools or audit APIs.

## Design and content rules

- Liquid Glass surfaces are used selectively; text-heavy content remains high contrast.
- The hero lens, gap comparison and work cards are illustrative.
- Portfolio concepts are labelled as concepts. No fabricated client logos, testimonials, conversion lifts, speed improvements or project counts.
- Reduced-motion preferences disable non-essential animation.
- Public review remains available without account registration.
- The client portal remains protected by the existing server-side account and session controls.

## Production self-check

- [x] React/Vite project scaffold and reusable design tokens
- [x] Responsive homepage, navigation, services mega menu, lens hero, gap comparison, featured carousel and concept case studies
- [x] Light/dark theme persistence, reduced-motion support, toast notifications and scroll progress
- [x] Inquiry form with endpoint configuration, honeypot, consent and contact fallback
- [x] 404 page, social metadata, favicon, manifest, sitemap and robots policy
- [x] Flask integration for React routes and immutable Vite assets
- [ ] Automated CI build and type-check must pass before merge
- [ ] Production environment secrets and current database backup must be migrated
- [ ] Render Pro service, persistent disk and custom domain must be provisioned and verified
- [ ] Authenticated client portal UX (project timeline, project messages, file approvals, invoices and notifications) remains a separate MVP implementation step; existing server-side account routes are retained
- [ ] Real case studies and testimonials can be added only after verified project evidence is available
