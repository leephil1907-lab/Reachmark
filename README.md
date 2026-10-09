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

## Commercial operating system

Reachmark connects real prospect discovery, evidence-backed website opportunities, human-approved outreach, draft proposals, contracts, projects, invoices, payment confirmation, delivery, and retention tracking. Open **Revenue OS** in the workspace for the canonical funnel, next best action, opportunity segments, and the saved commercial event trail. Metrics come from persisted records; empty stages remain empty, and the dashboard does not combine unlike currencies into one total.

Operating guides:

- [Commercial Operating System](docs/COMMERCIAL_OPERATING_SYSTEM.md) — positioning, offer boundaries, workflow, and weekly scorecard.
- [Client Delivery Playbook](docs/CLIENT_DELIVERY_PLAYBOOK.md) — qualification, proposal, onboarding, delivery, handover, and data handling checklists.

## Technology

Python · Flask · React · SQLite · Leaflet · Playwright · Docker

## Browser and app

Reachmark is one product:

- **Browser** — open the site and use `/workspace`.
- **Installed app** — visit `/app` and install (Chrome/Edge/Android, or Add to Home Screen on iPhone). Same workspace, own window. There is no App Store or Play Store listing — the site *is* the app.
- **This computer** — `python -m web.desktop` starts the local server and opens the workspace. That is not a phone download.

## Preview on GitHub

Reachmark is a Flask app, so **GitHub Pages cannot host it**. The GitHub-native preview is Codespaces:

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/leephil1907-lab/Reachmark)

1. On the repo click **Code → Codespaces → Create codespace on main**, or use the badge.
2. Setup installs Python and Node, then starts the app on port **8000**.
3. GitHub opens a preview. The link looks like `https://<codespace-name>-8000.app.github.dev`.

That instance is development-only (no production secrets). Railway remains production, with Gmail SMTP and the `/data` volume.

## Development

Install dependencies, build the frontend, and run the test suite before making production changes.

```bash
pip install -r requirements.txt
npm ci && npm run build
python -m flask --app web.app run --host 0.0.0.0 --port 8000
```

## Production

Production deployment is maintained separately from development configuration. Use the provided production environment template and follow the release checks before deployment.

## Status

The project is under active development.

