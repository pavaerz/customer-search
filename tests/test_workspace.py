import json,sqlite3,tempfile,unittest
from contextlib import closing
from pathlib import Path
from sales.db import Store,encode,now
from sales.workspace import reset_results,RESULT_TABLES
from sales.research_store import ResearchStore
from sales.research_rules import qualify
from test_research import sample

class WorkspaceResetTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=Store(self.root/'sales.sqlite3');self.store.init();self.rs=ResearchStore(self.store)
  self.campaign=self.rs.create();args=sample();self.rs.save(self.campaign['id'],self.campaign['generation'],None,args[0],args[1],qualify(*args));self.rs.stop(self.campaign['id']);self.rs.paused(self.campaign['id'])
 def tearDown(self):self.temp.cleanup()
 def reset(self):return reset_results(self.store,self.root/'verified-backup')
 def test_archives_every_row_and_clears_all_visible_results(self):
  with self.store.connect() as c:before={t:[dict(r) for r in c.execute('SELECT * FROM '+t)] for t in RESULT_TABLES}
  self.reset()
  self.assertEqual(self.store.company_list(),[]);self.assertEqual(self.store.legacy(),[]);self.assertIsNone(self.rs.campaign());self.assertEqual(self.rs.opportunities()['total'],0)
  with self.store.connect() as c:
   for t,rows in before.items():
    self.assertEqual(c.execute('SELECT count(*) FROM '+t).fetchone()[0],0)
    self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM workspace_archive WHERE source_table=? ORDER BY row_number',(t,))],rows)
   self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
 def test_keeps_contacts_dismissals_exclusions_and_manual_groups(self):
  with self.store.connect() as c:
   pid=c.execute('SELECT id FROM prospects').fetchone()[0];cid=c.execute('SELECT company_id FROM prospects').fetchone()[0]
   c.execute("UPDATE prospects SET stage='contacted',notes='Conservare il contenuto della nota' WHERE id=?",(pid,))
   c.execute("INSERT INTO dismissed_companies VALUES ('deleted.example',?)",(now(),))
   c.execute("INSERT INTO target_exclusions VALUES ('excluded.example','Esclusa','https://excluded.example',?,'test')",(now(),))
  self.store.classify_contact(cid,'agencies','Scelta manuale',manual=True)
  self.reset()
  for host in ['alfa.example','deleted.example','excluded.example']:self.assertTrue(self.rs.suppressed({'website':'https://'+host}))
  with self.store.connect() as c:
   self.assertEqual(c.execute('SELECT manual FROM contact_groups WHERE company_id=?',(cid,)).fetchone()[0],1)
   notes=json.loads(c.execute("SELECT payload FROM workspace_archive WHERE source_table='prospects'").fetchone()[0])['notes'];self.assertIn('Conservare',notes)
 def test_old_mail_contact_memory_and_no_restart_reimport(self):
  payload={'domain':'old.example','status':'sent','outcome':'do_not_contact'}
  with self.store.connect() as c:c.execute('INSERT INTO legacy_records VALUES (?,?,?)',('leads',9,encode(payload)))
  old=self.root/'customers.sqlite3'
  with closing(sqlite3.connect(old)) as c,c:c.execute('CREATE TABLE leads(id INTEGER PRIMARY KEY,domain TEXT,status TEXT)');c.execute("INSERT INTO leads VALUES (9,'old.example','sent')")
  self.reset();self.store.init();self.store.migrate_legacy(old)
  self.assertEqual(self.store.legacy(),[]);self.assertTrue(self.rs.suppressed({'website':'https://old.example'}))
  with self.store.connect() as c:self.assertEqual(tuple(c.execute("SELECT prior_contacted,do_not_contact FROM companies WHERE domain='old.example'").fetchone()),(1,1))
 def test_active_campaign_blocks_reset(self):
  self.rs.resume(self.campaign['id'])
  with self.assertRaises(ValueError):self.reset()
  self.assertTrue(self.store.company_list())
 def test_new_results_work_and_second_reset_keeps_previous_archive(self):
  self.reset();campaign=self.rs.create();args=sample();self.rs.save(campaign['id'],campaign['generation'],None,args[0],args[1],qualify(*args));self.assertEqual(self.rs.opportunities()['total'],1)
  self.rs.stop(campaign['id']);self.rs.paused(campaign['id']);self.reset()
  with self.store.connect() as c:self.assertEqual(c.execute("SELECT count(DISTINCT reset_id) FROM workspace_archive WHERE source_table='prospects'").fetchone()[0],2)
 def test_unexpected_reference_rolls_back_the_reset(self):
  with self.store.connect() as c:c.execute('CREATE TABLE reference_test(id INTEGER REFERENCES prospects(id))');c.execute('INSERT INTO reference_test SELECT id FROM prospects')
  with self.assertRaises(sqlite3.IntegrityError):self.reset()
  self.assertTrue(self.store.company_list());self.assertIsNotNone(self.rs.campaign())
