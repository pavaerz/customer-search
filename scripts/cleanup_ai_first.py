"""Verified retention of exported analyses. Does not touch operational data.

Requires the preflight inventory and verified backup from this implementation.
Dry-run by default; --apply archives first, verifies every member, then unlinks
only unchanged, inventoried files. No git clean, reset, environment or DB writes.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def verify(path):
    with zipfile.ZipFile(path) as z:
        m=json.loads(z.read('ARCHIVE-MANIFEST.json'))
        expected={r['path']:r['archived_sha256'] for r in m['files']}
        if len(expected)!=len(m['files']) or set(z.namelist())!=set(expected)|{'ARCHIVE-MANIFEST.json'}:
            raise ValueError('archive_members_mismatch')
        for name,checksum in expected.items():
            if Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name:
                raise ValueError('unsafe_archive_path')
            with z.open(name) as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=checksum:
                    raise ValueError('archive_checksum_mismatch')
        return m


def run(apply=False):
    folder=ROOT/'implementation-report/ai-first'
    before=json.loads((folder/'inventory-before.json').read_text())
    backup=json.loads((folder/'backup.json').read_text())
    if not backup.get('verified'):
        raise ValueError('verified_backup_required')
    db=sqlite3.connect((ROOT/'data/sales.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        if db.execute("SELECT 1 FROM campaigns WHERE status IN ('running','waiting','stopping')").fetchone():
            raise ValueError('active_campaign_preserve_files')
        latest=[dict(zip(('id','status'),row)) for row in db.execute('SELECT id,status FROM campaigns ORDER BY id DESC LIMIT 5')]
    finally:
        db.close()
    recent={r['id'] for r in latest}
    archive=ROOT/'archives/customersearch-analysis-archive.zip'
    manifest=verify(archive)
    archived={e['path']:e for e in manifest['files']}
    references='\n'.join(p.read_text(errors='replace') for base in ('tests','scripts','sales')
                         for p in (ROOT/base).rglob('*.py') if p!=Path(__file__).resolve())
    actions=[];add=[]
    for entry in before:
        rel=entry['path'];p=ROOT/rel;parts=Path(rel).parts
        if not p.is_file() or p.is_symlink():
            continue
        action='KEEP';reason=entry['reason']
        if parts[0] in ('.git','.venv','.runtime','node_modules','data','.agents','.codex'):
            continue
        if '__pycache__' in parts or p.suffix=='.pyc' or p.name=='.DS_Store':
            action='DELETE';reason='Regenerable bytecode or Finder metadata outside environments/data'
        else:
            campaign=re.search(r'CAMPAIGN-(\d+)-',p.name)
            old_export=bool(campaign and int(campaign[1]) not in recent and
                            (len(parts)==1 or parts[:2]==('reports','recent')))
            redundant=(rel in archived and rel.startswith('implementation-report/') and
                       archived[rel]['archived_sha256']==entry.get('sha256'))
            historical_output=(parts[0]=='implementation-report' and len(parts)==2 and
                               not re.search(r'campaign(?:39|40|41|42|43)\b',p.stem,re.I) and
                               p.suffix.lower() in ('.png','.log','.txt','.json','.jsonl'))
            if old_export or redundant or historical_output:
                if p.name in references or rel in references:
                    reason='Referenced by a CLI/test; keep exact compatibility input'
                elif p.suffix.lower() not in ('.md','.json','.txt','.png','.log','.jsonl'):
                    reason='Unknown artifact type: preserve'
                else:
                    raw=p.read_bytes()
                    # No credentials/session material enters an analysis archive.
                    suspicious=re.search(rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|(?i:bearer)\s+[A-Za-z0-9._-]{20,}|(?i:set-cookie:)',raw)
                    if suspicious or any(x in p.name.lower() for x in ('credential','secret','cookie','token','.env')):
                        reason='Possible sensitive material: keep in place; private rollback exists'
                    else:
                        action='ARCHIVE';reason='Older exported analysis, with verified lossless recovery'
        if action!='KEEP':
            checksum=sha(p)
            if checksum!=entry.get('sha256'):
                action='KEEP';reason='Changed since preflight; preserve local edits'
            elif action=='ARCHIVE' and rel not in archived:
                add.append((rel,p,checksum))
            elif action=='ARCHIVE' and archived[rel]['archived_sha256']!=checksum:
                action='KEEP';reason='Archive has another revision; preserve both'
        actions.append({'path':rel,'action':action,'reason':reason,'sha256':entry.get('sha256'),
                        'archive':str(archive.relative_to(ROOT)) if action=='ARCHIVE' else None})
    if apply:
        temp=archive.with_suffix('.new.zip')
        if temp.exists():
            raise ValueError('temporary_archive_already_exists')
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f,zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED) as out,zipfile.ZipFile(archive) as src:
            for name in src.namelist():
                if name=='ARCHIVE-MANIFEST.json':
                    continue
                with src.open(name) as incoming,out.open(name,'w',force_zip64=True) as dest:
                    for chunk in iter(lambda:incoming.read(1024*1024),b''):
                        dest.write(chunk)
            for rel,p,checksum in add:
                if sha(p)!=checksum:
                    raise ValueError('source_changed_during_archive')
                out.write(p,rel)
                manifest['files'].append({'path':rel,'category':'historical_campaign',
                    'original_sha256':checksum,'archived_sha256':checksum,'redacted':False,'bytes':p.stat().st_size})
            manifest['updated_at']=datetime.now(timezone.utc).isoformat()
            out.writestr('ARCHIVE-MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        verify(temp)
        os.replace(temp,archive)
        archive.with_suffix('.zip.sha256').write_text(sha(archive)+'  '+archive.name+'\n')
        for item in actions:
            if item['action'] not in ('DELETE','ARCHIVE'):
                continue
            p=ROOT/item['path']
            if sha(p)!=item['sha256']:
                raise ValueError('file_changed_before_removal')
            p.unlink()
        recent_dir=ROOT/'reports/recent'
        rows=['# Ultime cinque campagne\n','Aggiornato senza nuove campagne. Lo storico del database resta invariato.\n',
              '| Campagna | Stato | Report | Metriche |','|---|---|---|---|']
        for row in latest:
            cells=[]
            for suffix in ('REPORT.md','METRICS.json'):
                name=f'CAMPAIGN-{row["id"]}-{suffix}'
                cells.append(f'[{suffix}](../../{name})' if (ROOT/name).exists() else 'Non disponibile; nessun risultato inventato')
            rows.append(f'| {row["id"]} | {row["status"]} | '+' | '.join(cells)+' |')
        rows.append('\nAnalisi precedenti: `archives/customersearch-analysis-archive.zip`; lettura con `scripts.analysis_archive.read_text`.')
        (recent_dir/'README.md').write_text('\n'.join(rows)+'\n')
    result={'applied':apply,'latest_campaigns':latest,'archive_sha256':sha(archive),
            'private_rollback':backup['path'],'actions':actions,
            'counts':{a:sum(e['action']==a for e in actions) for a in ('KEEP','ARCHIVE','DELETE')}}
    (folder/('cleanup-actions.json' if apply else 'cleanup-preview.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result['counts']))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    run(parser.parse_args().apply)
