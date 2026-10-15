"""Rehearse migration and restoration on copies of the pre-change backup."""
import hashlib,json,shutil,sqlite3,tempfile,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store
from sales.research_store import migrate
ROOT=Path(__file__).resolve().parents[1]
BACKUP=ROOT/'data/backups/20261013T152552430651Z'
def snapshot(path):
 with sqlite3.connect(path) as c:
  return {r[0]:[tuple(v) for v in c.execute('SELECT * FROM "'+r[0]+'" ORDER BY rowid')] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}
def main():
 manifest=json.loads((BACKUP/'manifest.json').read_text())
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);original=BACKUP/'sales.sqlite3';target=root/'sales.sqlite3';shutil.copy2(original,target)
  assert hashlib.sha256(original.read_bytes()).hexdigest()==manifest['files']['sales.sqlite3']
  before=snapshot(target);store=Store(target);migrate(store);migrate(store);after=snapshot(target)
  assert all(after[k]==v for k,v in before.items())
  with store.connect() as c:assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  # Actually restore files and database, then verify every archived byte against the manifest.
  restored=root/'restore';restored.mkdir()
  with zipfile.ZipFile(BACKUP/'project.zip') as archive:
   for name in archive.namelist():
    p=Path(name);assert not p.is_absolute() and '..' not in p.parts
    archive.extract(name,restored)
    assert hashlib.sha256((restored/name).read_bytes()).hexdigest()==manifest['files'][name]
  shutil.copy2(original,restored/'sales.sqlite3');assert snapshot(restored/'sales.sqlite3')==before
  report={'backup':str(BACKUP.relative_to(ROOT)),'database_integrity':'ok','migration_repeated':True,'old_rows_unchanged':{k:len(v) for k,v in before.items()},'restored_archive_hashes':True,'restored_database_rows':True}
  (ROOT/'docs/migration4.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
