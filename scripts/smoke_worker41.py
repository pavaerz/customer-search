"""Real owned worker start/stop/resume, isolated DB, no outreach."""
import json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store
from sales.campaigns import CampaignManager

def main():
 with tempfile.TemporaryDirectory() as tmp:
  store=Store(Path(tmp)/'worker.sqlite3');store.init();manager=CampaignManager(store)
  campaign=manager.start({'regions':['Veneto']});time.sleep(.3)
  start=time.monotonic();paused=manager.stop(campaign['id']);first=time.monotonic()-start
  assert paused['status']=='paused' and first<5
  with store.connect() as c:before={r[0] for r in c.execute('SELECT id FROM research_tasks')}
  resumed=manager.resume(campaign['id']);assert resumed['generation']!=campaign['generation'];time.sleep(.3)
  start=time.monotonic();paused=manager.stop(campaign['id']);second=time.monotonic()-start
  assert second<5 and paused['status']=='paused'
  with store.connect() as c:
   assert before<={r[0] for r in c.execute('SELECT id FROM research_tasks')}
   assert c.execute("SELECT count(*) FROM research_tasks WHERE state IN ('pending','working')").fetchone()[0]<=48
   assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  report={'first_stop_seconds':round(first,3),'resumed_stop_seconds':round(second,3),'generation_changed':True,'task_ids_preserved':True,'database':'isolated temporary fixture','status':paused['status']}
  Path('docs/live-smoke41.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
