#!/bin/sh
# One-shot dev/bootstrap for sandbox turns (packages do not persist between turns).
set -e
cd "$(dirname "$0")/.."
pip install -q -r requirements.txt
pip install -q playwright
python -m playwright install chromium >/dev/null 2>&1 || python -m playwright install chromium-headless-shell
npm ci --no-audit --no-fund >/dev/null 2>&1 || npm install --no-audit --no-fund
echo "bootstrap ok"
