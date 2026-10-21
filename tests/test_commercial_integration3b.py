"""3B application wiring, real temporary SQLite, no provider/network calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store
from sales.research_store import ResearchStore
from sales.commercial.storage import Opportunities
from sales.commercial.coordinator import Coordinator
from sales.commercial.ai_settings import read,save
from sales.commercial.ai import analyze,summary
from sales.commercial.cache_policy import inspect_cache,record_use,archive_before_refresh
from test_commercial_engines import page
from sales.commercial.inspection import inspect

class Integration3B(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=Store(Path(self.tmp.name)/'test.db');self.store.init();self.rs=ResearchStore(self.store)
 def create(self):return self.rs.create({'commercial_engines':['FREELANCE'],'mode':'pilot'})
 def test_defaults_disabled_and_no_credentials(self):
  self.assertFalse(read(self.store)['enabled'])
  with self.assertRaises(ValueError):save(self.store,{'api_key':'do-not-save'})
  with self.assertRaises(ValueError):save(self.store,{'max_calls_per_engine':-1})
  with self.store.connect() as c:self.assertNotIn('do-not-save',str(c.execute('SELECT * FROM config').fetchall()))
 def test_config_snapshot_and_resume_no_reconfiguration(self):
  first=self.create();self.assertFalse(first['filters']['commercial']['ai']['enabled'])
  save(self.store,{'enabled':True,'provider':'MOCK'})
  self.rs.stop(first['id']);self.rs.paused(first['id']);resumed=self.rs.resume(first['id'])
  self.assertFalse(resumed['filters']['commercial']['ai']['enabled'])
  self.rs.stop(first['id']);self.rs.paused(first['id']);second=self.create()
  self.assertTrue(second['filters']['commercial']['ai']['enabled'])
 def test_unknown_campaign_config_rejected_before_save(self):
  with self.assertRaises(ValueError):self.rs.create({'commercial_engines':['FREELANCE'],'commercial':{'api_key':'secret'}})
  with self.assertRaises(ValueError):self.rs.create({'commercial_engines':['FREELANCE'],'commercial':{'ai':{'timeout':0}}})
  with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM campaigns').fetchone()[0],0)
 def test_coordinator_shadow_separate_revision_and_manual_crm(self):
  save(self.store,{'enabled':True,'provider':'MOCK'});campaign=self.create()
  worker=Coordinator(self.store,campaign)
  p=page('Cerchiamo sviluppatore WordPress freelance.',date=False)
  task={'id':1,'kind':'candidate','strategy':'FREELANCE','payload':{'url':p['url'],'commercial_engine':'FREELANCE'}}
  with patch('sales.commercial.inspection.ResearchWeb.get',lambda web,url:{**p,'url':url}):worker._execute(task,lambda:None)
  repo=Opportunities(self.store);item=repo.listing()['items'][0]
  self.assertEqual(item['state'],'NEEDS_REVIEW');self.assertEqual(item['ai_assessment']['provider'],'MOCK')
  self.assertIn(item['ai_assessment']['status'],('completed','fallback'))
  self.assertEqual(repo.get(item['id'])['state'],'NEEDS_REVIEW')
  self.assertEqual(summary(self.store,campaign['id'])['calls'],1)
  repo.action(item['id'],'interesting');self.assertEqual(repo.get(item['id'])['manual_state'],'interesting')
  self.assertEqual(len(repo.get(item['id'])['revisions']),1)
 def test_disabled_pipeline_makes_no_ai_dispatch(self):
  c=self.create();p=page('Cerchiamo sviluppatore WordPress freelance.',date=False)
  with patch('sales.commercial.inspection.ResearchWeb.get',lambda web,url:{**p,'url':url}),patch('sales.commercial.ai.infer',side_effect=AssertionError('No AI')):
   Coordinator(self.store,c)._execute({'id':1,'kind':'candidate','strategy':'FREELANCE','payload':{'url':p['url'],'commercial_engine':'FREELANCE'}},lambda:None)
  self.assertEqual(summary(self.store,c['id'])['calls'],0)
 def test_migrations_repeat_preserves_history(self):
  c=self.create();p=page('Cerchiamo freelance WordPress.')
  with patch('sales.commercial.inspection.ResearchWeb.get',lambda web,url:{**p,'url':url}):r=inspect(self.store,{'url':p['url'],'commercial_engine':'FREELANCE'})
  repo=Opportunities(self.store);oid=repo.save(c,r['identity'],r['documents'],r['result']);repo.action(oid,'discard')
  before=repo.get(oid);self.store.init();after=repo.get(oid)
  self.assertEqual(before['body'],after['body']);self.assertEqual(before['revisions'],after['revisions']);self.assertEqual(after['manual_state'],'discarded')
  with self.store.connect() as conn:self.assertEqual(conn.execute('pragma integrity_check').fetchone()[0],'ok')
 def test_search_cache_ttl_usage_and_retained_versions(self):
  key='fixture';self.store.cache_set(key,{'results':[{'url':'https://a.example'}]})
  body,policy=inspect_cache(self.store,key);self.assertEqual(policy['decision'],'REUSE');record_use(self.store,key,'REUSE')
  with self.store.connect() as c:c.execute("UPDATE cache SET created_at='2020-01-01T00:00:00+00:00' WHERE key=?",(key,))
  self.assertIsNone(inspect_cache(self.store,key)[0]);self.assertEqual(inspect_cache(self.store,key)[1]['decision'],'REFRESH')
  archive_before_refresh(self.store,key);self.store.cache_set(key,{'results':[]});record_use(self.store,key,'REFRESH')
  with self.store.connect() as c:
   old=c.execute("SELECT body FROM commercial_search_cache_history WHERE cache_key=? AND acquired_at LIKE '2020%'",(key,)).fetchone()
   self.assertIn('a.example',old[0]);self.assertIsNotNone(c.execute('SELECT last_used_at FROM commercial_search_cache_usage WHERE cache_key=?',(key,)).fetchone())
 def test_embedded_not_enqueued_for_paid_resolution(self):
  c=self.create();worker=Coordinator(self.store,c)
  worker.offer('FREELANCE',{'url':'https://www.linkedin.com/jobs/view/embedded-software-engineer-at-digisourced-4377440023','title':'Embedded Software Engineer at Digisourced.','content':'Embedded AUTOSAR freelance'}, {})
  with self.store.connect() as conn:self.assertEqual(conn.execute("SELECT count(*) FROM research_tasks WHERE kind='resolve'").fetchone()[0],0)
 def test_resolution_does_not_accept_different_subject(self):
  c=self.create();worker=Coordinator(self.store,c)
  task={'id':1,'kind':'resolve','strategy':'FREELANCE','payload':{'query':'Numeraway Python jobs','resolution_company':'Numeraway','resolution_role':'Freelance esperti in Python','resolution_url':'https://linkedin.com/jobs/view/example'}}
  worker.receive(task,[{'url':'https://jobs.example/jobs/python','title':'Python developer at Elsewhere','content':'Elsewhere ricerca Python freelance'}],lambda:None,resolution=True)
  with self.store.connect() as conn:
   self.assertEqual(conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0],0)
   self.assertEqual(conn.execute('SELECT decision FROM commercial_discovery').fetchone()[0],'exclude')
 def test_serper_counter_includes_resolution_calls(self):
  from sales.db import now
  from sales.serper_provider import status
  campaign=self.create()
  with self.store.connect() as c:
   for kind,provider in [('search','serper'),('resolve','public:')]:
    c.execute('INSERT INTO discovery_operations(campaign_id,strategy,kind,provider,status,seconds,details,created_at) VALUES (?,?,?,?,?,?,?,?)',(campaign['id'],'FREELANCE',kind,provider,'ok',.1,json.dumps({'credits':1,'engines':['google via Serper']}),now()))
  self.assertEqual(self.rs.campaign(campaign['id'])['serper_requests'],2)
  with patch('sales.serper_provider.api_key',return_value=None):self.assertEqual(status(self.store,campaign['id'])['campaign_requests'],2)
