# Reachmark

**Reachmark** finds businesses losing customers online, shows them exactly where the opportunity is, and helps turn that opportunity into a working solution.

## Core Features

- Business discovery and lead management
- Website intelligence and analysis
- Maps and location research
- Outreach and follow-up workflows
- Document and invoice generation
- AI-assisted business workflows
- Responsive web and PWA experience

## Technology

Python · Flask · React · SQLite · Leaflet · Playwright · Docker

## Browser and app

Reachmark is one product:

- **Browser** — customers sign up at `/signup` and land on `/dashboard`; the owner types `/admin` after the site address (it is not linked anywhere on the site).
- **Installed app** — visit `/app` and install (Chrome/Edge/Android, or Add to Home Screen on iPhone). Same workspace, own window. There is no App Store or Play Store listing — the site *is* the app.
- **This computer** — `python -m web.desktop` starts the local server and opens the workspace. That is not a phone download.

## Preview on GitHub

Reachmark is a Flask app, so **GitHub Pages cannot host it**. The GitHub-native preview is Codespaces:

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/leephil1907-lab/Reachmark)

1. On the repo click **Code → Codespaces → Create codespace on main**, or use the badge.
2. Setup installs Python and Node, then starts the app on port **8000**.
3. GitHub opens a preview. The link looks like `https://<codespace-name>-8000.app.github.dev`.

That instance is development-only (no production secrets). Render Pro in Frankfurt is the planned production target; Railway remains intact as rollback until the verified data migration and DNS cutover are complete.

## Development

Install dependencies, build the frontend, and run the test suite before making production changes.

```bash
pip install -r requirements.txt
npm ci && npm run build
python -m flask --app web.app run --host 0.0.0.0 --port 8000
```

## Public website (React/Vite)

The public Reachmark site is built with React 18, TypeScript, Vite, Framer Motion, React Router, Lenis and lucide-react. Source lives in `frontend/site`; the production bundle is emitted to `static/site` and served by the existing Flask app so existing audit, account, enquiry and admin APIs remain same-origin.

```bash
npm install --no-audit --no-fund
npm run dev:site
npm run typecheck
npm run build
```

Copy `frontend/site/.env.example` to the Vite environment file when configuring optional public endpoints. Never place server credentials in `VITE_*` variables. The free review uses `/api/public/audit`; project enquiries use `/api/enquiries` by default.

## Production

Render Pro is configured in `render.yaml`; follow `RENDER_MIGRATION.md` for database backup/restore, secret transfer, smoke tests and DNS cutover. Keep Railway running until Render is verified. The app uses SQLite on a single persistent disk-backed instance; do not scale to multiple instances until a separately tested PostgreSQL migration is completed.

## Status

The project is under active development.

