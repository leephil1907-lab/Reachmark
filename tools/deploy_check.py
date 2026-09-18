#!/usr/bin/env python3
"""
Reachmark deploy check — preflight for live (Reachmark parity: tools/deploy-check.mjs)
Calls /api/deploy-check and reports missing env.
Run: python tools/deploy_check.py [--url https://reachmark.co]
"""
import os, sys, json, urllib.request

def check_local_env():
    checks = []
    def add(name, ok, detail, required=False):
        checks.append((name, ok, detail, required))
    base = os.getenv('PUBLIC_BASE_URL','')
    add('PUBLIC_BASE_URL', base.startswith('https://'), base or 'Set https://reachmark.co', True)
    sk = os.getenv('SECRET_KEY','')
    add('SECRET_KEY', len(sk)>=32, f'{len(sk)} chars', os.getenv('APP_ENV')=='production')
    oph = os.getenv('OWNER_PASSWORD_HASH','')
    add('OWNER_PASSWORD_HASH', oph.startswith(('scrypt:','pbkdf2:')) if oph else False, 'Set hash', os.getenv('APP_ENV')=='production')
    dbp = os.getenv('DATABASE_PATH','')
    add('DATABASE_PATH', os.path.isabs(dbp) if dbp else False, dbp or 'Set absolute', os.getenv('APP_ENV')=='production')
    smtp = bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM'))
    add('SMTP', smtp, os.getenv('SMTP_HOST') or 'Queued to outbox', False)
    return checks

def main():
    url = sys.argv[2] if len(sys.argv)>2 and sys.argv[1]=='--url' else 'http://localhost:8000/api/deploy-check'
    print(f"Checking {url} ...")
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read().decode())
            print(f"Release: {data.get('release')}, ok: {data.get('ok')}")
            for c in data.get('checks',[]):
                mark = "✓" if c['ok'] else ("✗ required" if c['required'] else "○ optional")
                print(f"  {mark} {c['name']}: {c['detail']}")
            if not data.get('ok'):
                print("\n⚠ Some required checks failed — see above.")
                sys.exit(2)
            print("\n✓ Deploy check passed.")
    except Exception as e:
        print(f"Could not reach {url}: {e}")
        print("Falling back to local env check:")
        for name, ok, detail, req in check_local_env():
            mark = "✓" if ok else ("✗" if req else "○")
            print(f"  {mark} {name}: {detail}")

if __name__ == '__main__':
    main()
