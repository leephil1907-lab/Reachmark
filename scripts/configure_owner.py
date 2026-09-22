"""Run locally on the VPS. Secrets are written with restrictive permissions, not printed."""
import getpass,os,re,secrets
from pathlib import Path
from werkzeug.security import generate_password_hash
path=Path('.env.production')
if path.exists():raise SystemExit('.env.production already exists. Back it up and edit deliberately; existing credentials will not be overwritten.')
domain=input('Your domain (no https://): ').strip()
if not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?',domain) or '.' not in domain:raise SystemExit('Enter a domain you own.')
password=getpass.getpass('New owner password (16+ characters): ')
if len(password)<16 or password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords must match and have at least 16 characters.')
content="APP_ENV=production\nSECRET_KEY='"+secrets.token_hex(32)+"'\nOWNER_PASSWORD_HASH='"+generate_password_hash(password)+"'\nPUBLIC_BASE_URL=https://"+domain+"\nDATABASE_PATH=/data/reachmark.sqlite3\n"
fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as f:f.write(content)
print('Wrote .env.production securely. Keep a private backup; do not commit it. Set DOMAIN in .env to '+domain)
