"""Verified local backup, including secrets; never expose the archive through HTTP."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import zipfile
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]

def backup(root=ROOT):
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination=root/'data'/'backups'/stamp
    destination.mkdir(parents=True,mode=0o700)
    os.chmod(destination,0o700)
    manifest={'created_at':stamp,'files':{},'databases':{}}
    for filename in ('customers.sqlite3','sales.sqlite3'):
        original=root/'data'/filename
        if not original.exists(): continue
        target=destination/filename
        with closing(sqlite3.connect(original)) as source,closing(sqlite3.connect(target)) as saved:
            source.backup(saved)
            assert saved.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            tables=[row[0] for row in saved.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            counts={name:saved.execute('SELECT count(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] for name in tables}
            for name,n in counts.items():
                assert source.execute('SELECT count(*) FROM "'+name.replace('"','""')+'"').fetchone()[0]==n
            manifest['databases'][filename]=counts
        os.chmod(target,0o600)
        manifest['files'][filename]=hashlib.sha256(target.read_bytes()).hexdigest()
    archive=destination/'project.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in root.rglob('*'):
            rel=p.relative_to(root)
            if any(part in ('.venv','.runtime','node_modules','.git','__pycache__','backups') for part in rel.parts): continue
            if not p.is_file() or p.suffix in ('.sqlite3','.db') or p.name.endswith(('-wal','-shm','-journal')): continue
            content=p.read_bytes()
            z.writestr(str(rel),content)
            manifest['files'][str(rel)]=hashlib.sha256(content).hexdigest()
    os.chmod(archive,0o600)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name in z.namelist(): assert hashlib.sha256(z.read(name)).hexdigest()==manifest['files'][name]
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2))
    os.chmod(destination/'manifest.json',0o600)
    return str(destination)

if __name__=='__main__': print(backup())
