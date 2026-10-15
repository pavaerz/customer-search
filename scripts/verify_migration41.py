"""Rehearse the additive migration and backup restore without touching production."""
import hashlib,json,sqlite3,sys,tempfile,zipfile,shutil,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store
from sales.research_store import migrate
ROOT=Path(__file__).resolve().parents[1]
BACKUP=ROOT/'data/backups/20261013T181253135811Z'
def rows(db):
 with sqlite3.connect(db) as c:
  return {name:[list(r) for r in c.execute('SELECT * FROM "'+name+'"')] for name, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--backup',type=Path,default=BACKUP);parser.add_argument('--output',type=Path,default=ROOT/'docs/migration41.json');args=parser.parse_args();backup=args.backup.resolve()
 manifest=json.loads((backup/'manifest.json').read_text());before=rows(backup/'sales.sqlite3')
 with tempfile.TemporaryDirectory() as tmp:
  dest=Path(tmp);db=dest/'sales.sqlite3';shutil.copy2(backup/'sales.sqlite3',db);store=Store(db);migrate(store);migrate(store);after=rows(db)
  for table,data in before.items():
   if table in ('research_sources','research_schema'):
    assert all(r in after[table] for r in data),table
   else:assert data==after[table],table
  with store.connect() as c:
   assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not c.execute('PRAGMA foreign_key_check').fetchall()
  with zipfile.ZipFile(backup/'project.zip') as archive:
   assert archive.testzip() is None
   for entry in archive.namelist():assert hashlib.sha256(archive.read(entry)).hexdigest()==manifest['files'][entry]
  restored=dest/'restored.sqlite3';shutil.copy2(backup/'sales.sqlite3',restored)
  assert hashlib.sha256(restored.read_bytes()).hexdigest()==manifest['files']['sales.sqlite3'];assert rows(restored)==before
 report={'backup':str(backup.relative_to(ROOT)),'migration_runs':2,'existing_tables_preserved':{name:len(v) for name,v in before.items()},'integrity_check':'ok','foreign_key_check':[],'archive_hashes_verified':True,'restore_identical':True}
 args.output.write_text(json.dumps(report,indent=2));print(json.dumps({'migration_runs':2,'integrity_check':'ok','restore_identical':True}))
if __name__=='__main__':main()
