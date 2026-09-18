"""Online SQLite snapshots and explicit offline restore. No application import."""
import argparse, hashlib, json, os, sqlite3, time, shutil, subprocess
from pathlib import Path
from contextlib import closing
import requests

def heartbeat(failed=False):
    url=os.getenv('BACKUP_HEALTHCHECK_URL','')
    if not url:return
    if not url.startswith('https://'):raise RuntimeError('Backup heartbeat requires HTTPS')
    try:
        r=requests.get(url.rstrip('/')+('/fail' if failed else ''),timeout=10);r.raise_for_status()
    except requests.RequestException:print('Backup monitor heartbeat failed; check external monitor configuration',flush=True)


def verify(path):
    with closing(sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro',uri=True)) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Snapshot integrity check failed')
        return {name:c.execute('SELECT count(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
def snapshot(source,directory,retain=14):
    source=Path(source);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if not source.is_file():raise RuntimeError('Source database does not exist')
    target=directory/(time.strftime('reachmark-%Y%m%dT%H%M%SZ-',time.gmtime())+str(time.time_ns())+'.sqlite3');tmp=target.with_suffix('.tmp')
    try:
        with closing(sqlite3.connect(f'file:{source.resolve()}?mode=ro',uri=True)) as src,closing(sqlite3.connect(tmp)) as dst:src.backup(dst);dst.commit()
        counts=verify(tmp);os.chmod(tmp,0o600);os.replace(tmp,target)
        manifest={'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'tables':counts,'created_unix':time.time()}
        target.with_suffix('.json').write_text(json.dumps(manifest,indent=2));os.chmod(target.with_suffix('.json'),0o600)
        # Optional encrypted off-host copy. Failure is visible and does not claim offsite success.
        if os.getenv('RESTIC_REPOSITORY'):
            subprocess.run(['restic','backup',str(target),str(target.with_suffix('.json')),'--tag','reachmark'],check=True,timeout=1800)
        for old in sorted(directory.glob('reachmark-*.sqlite3'),reverse=True)[retain:]:old.unlink();old.with_suffix('.json').unlink(missing_ok=True)
        (directory/'last-success').write_text(str(time.time()))
        heartbeat()
        return target
    finally:tmp.unlink(missing_ok=True)
def restore(source,target):
    source=Path(source);target=Path(target);manifest=json.loads(source.with_suffix('.json').read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest()!=manifest['sha256']:raise RuntimeError('Snapshot checksum mismatch')
    verify(source);target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():snapshot(target,target.parent/'pre-restore',retain=3)
    tmp=target.with_suffix('.restore-tmp');shutil.copyfile(source,tmp);os.chmod(tmp,0o600)
    # Operator must stop the application first: old WAL must not be replayed onto a restored DB.
    for suffix in ('-wal','-shm'):Path(str(target)+suffix).unlink(missing_ok=True)
    os.replace(tmp,target);return verify(target)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['backup','restore','loop','check']);p.add_argument('--database',default=os.getenv('DATABASE_PATH','/data/reachmark.sqlite3'));p.add_argument('--directory',default=os.getenv('BACKUP_DIR','/backups'));p.add_argument('--snapshot');p.add_argument('--confirm-app-stopped',action='store_true');a=p.parse_args()
    if a.action=='check':
        age=time.time()-float((Path(a.directory)/'last-success').read_text())
        if age>26*3600:raise SystemExit('Backup is stale')
        print('Backup age is healthy')
    elif a.action=='restore':
        if not a.confirm_app_stopped or not a.snapshot:p.error('restore requires --snapshot and --confirm-app-stopped')
        print(restore(a.snapshot,a.database))
    elif a.action=='backup':print(snapshot(a.database,a.directory))
    else:
        while True:
            try:print(snapshot(a.database,a.directory),flush=True)
            except Exception as error:print('BACKUP FAILED: '+type(error).__name__,flush=True);heartbeat(failed=True);time.sleep(300);continue
            time.sleep(24*3600)
