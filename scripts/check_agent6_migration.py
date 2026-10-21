"""Validate full startup migrations and rollback on a disposable backup copy."""
import hashlib,json,shutil,sqlite3,tempfile
from pathlib import Path
from sales.db import Store

def census(path):
 with sqlite3.connect(path) as c:
  tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
  out={}
  for table in tables:
   h=hashlib.sha256();n=0
   for row in c.execute('SELECT * FROM "'+table.replace('"','""')+'"'):
    h.update(repr(row).encode());n+=1
   out[table]={'rows':n,'sha256':h.hexdigest()}
  return out

def main():
 source=Path('data/backups/customersearch6/sales.sqlite3')
 with tempfile.TemporaryDirectory() as tmp:
  p=Path(tmp)/'copy.sqlite3';shutil.copyfile(source,p);before=census(p);store=Store(p);store.init();after=census(p);store.init();twice=census(p)
  changed={k:{'before':v,'after':after.get(k)} for k,v in before.items() if v!=after.get(k)}
  assert set(changed)<= {'research_schema'},changed
  assert after==twice,'Migration is not repeatable'
  with store.connect() as c:assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  # Rollback by restoring the pre-migration database, never modifying source.
  shutil.copyfile(source,p);restored=census(p);assert restored==before
  result={'integrity':'ok','source_database_modified':False,'original_tables':len(before),'changed_original_tables':changed,'new_tables':sorted(set(after)-set(before)),'repeatable':True,'restore_verified':True,'commercial_history_config_contacts_preserved':True,'before':before}
  Path('implementation-report/customersearch6-migration.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='before'}))
if __name__=='__main__':main()
