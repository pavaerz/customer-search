import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from sales.db import Store,encode,now
from sales.grants import profile,DEFAULT,valid_vat,official,assessment,GrantsManager,state
from sales.grants_worker import run

class GrantTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(Path(self.tmp.name)/'test.db');self.store.init()
 def seed(self):
  with self.store.connect() as c:
   ident=c.execute('INSERT INTO grant_runs(state,generation,profile,message,created_at,updated_at) VALUES (?,?,?,?,?,?)',('running','token',encode(DEFAULT),'',now(),now())).lastrowid
   c.execute("INSERT INTO grant_tasks(run_id,url,kind) VALUES (?,?,'grant')",(ident,'https://www.invitalia.it/incentivi/test'))
  return ident
 def page(self):return {'url':'https://www.invitalia.it/incentivi/test','status':200,'checked_at':now(),'html':'<title>Contributo investimenti</title><main><h1>Contributo investimenti</h1><p>Beneficiari: piccole imprese.</p><p>Scadenza: 31 dicembre 2020.</p><p>Contributo a fondo perduto del 30%.</p></main>'}
 def test_vat_and_regime(self):
  self.assertTrue(valid_vat('01114601006'));self.assertFalse(valid_vat('01114601007'))
  p=profile(self.store,{'vat':'IT01114601006'});self.assertEqual(p['tax_regime'],'unknown');self.assertEqual(p['vat'],'01114601006')
  with self.assertRaises(ValueError):profile(self.store,{'vat':'123'})
 def test_profile_validation_and_persistence(self):
  profile(self.store,{'activity':'Siti web','tax_regime':'forfettario'});self.store.init()
  self.assertEqual(profile(self.store)['tax_regime'],'forfettario')
  with self.assertRaises(ValueError):profile(self.store,{'tax_regime':'automatico'})
  with self.assertRaises(ValueError):profile(self.store,{'started_on':'2999-01-01'})
 def test_official_allowlist(self):
  self.assertTrue(official('https://www.invitalia.it/test'));self.assertFalse(official('https://invitalia.it.evil.example/test'));self.assertFalse(official('http://127.0.0.1/test'))
 def test_no_eligibility_inference(self):
  result=assessment(self.page(),DEFAULT);self.assertEqual(result['status'],'analyzing');self.assertIn('2020',result['deadlines'][0]);self.assertNotIn('eligible',result)
 def test_generic_and_procurement_not_promoted(self):
  p=self.page();p['html']='<title>Incentivi</title><p>Elenco incentivi nazionali</p>';self.assertIsNone(assessment(p,DEFAULT))
  p['html']='<title>Bandi di gara</title><p>Beneficiari: imprese</p>';self.assertIsNone(assessment(p,DEFAULT))
 def test_worker_and_crm_separation(self):
  cid=self.seed()
  with patch('sales.grants_worker.ResearchWeb.get',return_value=self.page()), patch('sales.grants_worker.GrantAnalyst.extract',return_value={'rules':[],'complete':False,'limitations':['Test senza modello']}):run(self.store.path,cid,'token')
  result=state(self.store);self.assertEqual(result['run']['state'],'completed');self.assertEqual(len(result['items']),1);self.assertEqual(self.store.company_list(),[])
 def test_stop_rejects_late_results(self):
  cid=self.seed()
  def late(*args,**kwargs):GrantsManager(self.store).stop();return self.page()
  with patch('sales.grants_worker.ResearchWeb.get',side_effect=late):run(self.store.path,cid,'token')
  self.assertEqual(state(self.store)['run']['state'],'stopped');self.assertEqual(state(self.store)['items'],[])
 def test_start_requires_profile(self):
  with self.assertRaises(ValueError):GrantsManager(self.store).start()
 def test_double_start_and_province_scope(self):
  profile(self.store,{'activity':'Siti web','province':'Treviso'})
  with patch('sales.grants.subprocess.Popen') as popen:
   popen.return_value.pid=123;popen.return_value.poll.return_value=0
   GrantsManager(self.store).start()
   with self.assertRaises(ValueError):GrantsManager(self.store).start()
  with self.store.connect() as c:
   urls=[r[0] for r in c.execute('SELECT url FROM grant_tasks')];self.assertEqual(len(urls),2);self.assertFalse(any('camcom' in u for u in urls))
