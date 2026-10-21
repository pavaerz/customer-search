"""Verified local backup, including secrets; never expose the archive through HTTP."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import zipfile
import tempfile
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]

def digest(stream):
    h=hashlib.sha256()
    for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def file_digest(path):
    with Path(path).open('rb') as stream:return digest(stream)

def private_file(path):
    """Create with restrictive permissions from the first byte."""
    return os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb')

def project_files(root):
    """Prune large environments/backups; never follow links outside the project."""
    excluded={'.venv','.runtime','node_modules','.git','__pycache__','backups'}
    for base,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if d not in excluded and not (Path(base)/d).is_symlink()]
        for name in sorted(files):
            p=Path(base)/name
            if p.is_symlink() or p.suffix in ('.sqlite3','.sqlite','.db') or name.endswith(('-wal','-shm','-journal')):continue
            if p.is_file():yield p

def verify_backup(destination):
    """Verify hashes and a real temporary restore; never overwrite live data."""
    destination=Path(destination).resolve()
    manifest=json.loads((destination/'manifest.json').read_text())
    with tempfile.TemporaryDirectory(prefix='customersearch-restore-') as tmp:
        restored=Path(tmp)
        with zipfile.ZipFile(destination/'project.zip') as z:
            expected=set(manifest['files'])-set(manifest['databases'])
            names=z.namelist()
            if len(names)!=len(set(names)) or set(names)!=expected:raise ValueError('Backup archive manifest mismatch')
            for name in names:
                p=Path(name)
                if p.is_absolute() or '..' in p.parts or '\\' in name:raise ValueError('Unsafe backup path')
                target=restored/p;target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(name) as src,private_file(target) as out:
                    h=hashlib.sha256()
                    for chunk in iter(lambda:src.read(1024*1024),b''):out.write(chunk);h.update(chunk)
                if h.hexdigest()!=manifest['files'][name]:raise ValueError('Backup checksum mismatch')
        for name,counts in manifest['databases'].items():
            if name not in ('customers.sqlite3','sales.sqlite3'):raise ValueError('Unsafe database name')
            original=destination/name
            if file_digest(original)!=manifest['files'][name]:raise ValueError('Database checksum mismatch')
            with closing(sqlite3.connect(original.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(restored/name)) as db:
                src.backup(db)
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity failure')
                for table,count in counts.items():
                    actual=db.execute('SELECT count(*) FROM "'+table.replace('"','""')+'"').fetchone()[0]
                    if actual!=count:raise ValueError('Database row count mismatch')
    return {'verified':True,'files':len(manifest['files']),'databases':len(manifest['databases'])}

def backup(root=ROOT):
    root=Path(root).resolve()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination=root/'data'/'backups'/stamp
    destination.mkdir(parents=True,mode=0o700)
    os.chmod(destination,0o700)
    manifest={'created_at':stamp,'files':{},'databases':{}}
    for filename in ('customers.sqlite3','sales.sqlite3'):
        original=root/'data'/filename
        if original.is_symlink():raise ValueError('Backup refuses a linked operational database')
        if not original.exists(): continue
        target=destination/filename
        with private_file(target):pass
        with closing(sqlite3.connect(original.as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(target)) as saved:
            source.backup(saved)
            if saved.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity failure')
            tables=[row[0] for row in saved.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            counts={name:saved.execute('SELECT count(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] for name in tables}
            # Counts describe this consistent snapshot, not the concurrently
            # changing live database after the backup finished.
            manifest['databases'][filename]=counts
        os.chmod(target,0o600)
        manifest['files'][filename]=file_digest(target)
    archive=destination/'project.zip'
    with private_file(archive) as output,zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for p in project_files(root):
            rel=p.relative_to(root)
            with p.open('rb') as src,z.open(str(rel),'w',force_zip64=True) as out:
                h=hashlib.sha256()
                for chunk in iter(lambda:src.read(1024*1024),b''):out.write(chunk);h.update(chunk)
            manifest['files'][str(rel)]=h.hexdigest()
    os.chmod(archive,0o600)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            with z.open(name) as src:
                if digest(src)!=manifest['files'][name]:raise ValueError('Backup checksum mismatch')
    with private_file(destination/'manifest.json') as f:f.write(json.dumps(manifest,indent=2).encode())
    os.chmod(destination/'manifest.json',0o600)
    return str(destination)

if __name__=='__main__': print(backup())
