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

- **Browser** — open the site and use `/workspace`.
- **Installed app** — visit `/app` and install (Chrome/Edge/Android, or Add to Home Screen on iPhone). Same workspace, own window.
- **This computer** — `python -m web.desktop` starts the local server and opens the workspace.

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

