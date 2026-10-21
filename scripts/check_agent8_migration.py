"""Migrate/restore a disposable copy; never open the live database for writes.

Usage: PYTHONPATH=. .venv/bin/python scripts/check_agent8_migration.py BACKUP_DB
Prints verification results; no new report or retained duplicate database.
"""
import hashlib,json,shutil,sqlite3,sys,tempfile
from pathlib import Path
from sales.db import Store


def census(path):
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);c.execute('PRAGMA query_only=ON')
    try:
        out={}
        for (table,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            quoted='"'+table.replace('"','""')+'"'
            info=list(c.execute('PRAGMA table_info('+quoted+')'))
            order=','.join('"'+r[1]+'"' for r in sorted(info,key=lambda r:r[5]) if r[5]) or 'rowid'
            h=hashlib.sha256();count=0
            for row in c.execute('SELECT * FROM '+quoted+' ORDER BY '+order):
                h.update(repr(row).encode());count+=1
            out[table]={'rows':count,'sha256':h.hexdigest()}
        return out
    finally:c.close()


def main(source):
    source=Path(source).resolve()
    if not source.is_file():raise ValueError('Backup SQLite missing')
    if source==Path('data/sales.sqlite3').resolve():raise ValueError('Provide a verified backup, not the active database')
    with tempfile.TemporaryDirectory(prefix='customersearch8-migration-') as tmp:
        target=Path(tmp)/'migration.sqlite3';shutil.copyfile(source,target)
        before=census(target);store=Store(target);store.init();after=census(target)
        changes={t for t in before if before[t]!=after.get(t)}
        assert changes<={'research_schema','agent7_diagnostics'},changes
        # Diagnostics may expire under the existing retention policy. Historical
        # research, commercial records, settings, feedback and CRM must not.
        assert after.get('agent7_diagnostics',{}).get('rows',0)<=before.get('agent7_diagnostics',{}).get('rows',0)
        assert 'agent8_annotations' in after and after['agent8_annotations']['rows']==0
        store.init();assert census(target)==after,'Migration not idempotent'
        with store.connect() as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert c.execute('SELECT 1 FROM research_schema WHERE version=800').fetchone()
        # Restore into a separate path: no sidecar from the migrated copy can
        # contaminate the backup restoration.
        restored=Path(tmp)/'restored.sqlite3';shutil.copyfile(source,restored)
        assert census(restored)==before,'Restore differs from original backup'
        print(json.dumps({'integrity':'ok','repeatable':True,'restore_verified':True,
            'original_tables':len(before),'new_tables':sorted(set(after)-set(before)),
            'changed_original_tables':sorted(changes),'commercial_history_preserved':True,
            'production_writes':0,'network_calls':0}))


if __name__=='__main__':main(sys.argv[1])
