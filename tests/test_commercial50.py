from scripts.analysis_archive import read_text as archived_text
"""5.0: offline strategy, budgets, memory and semantic regressions."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
from sales.db import Store,encode
from sales.research_store import ResearchStore
from sales.commercial.catalog import ENGINES,PROFILES,DEEP_PROFILE
from sales.commercial.search_strategies import catalog,plans
from sales.commercial.search_intelligence import preview,select,history
from sales.commercial.search_memory import decision
from sales.commercial.discovery import assess
from sales.commercial.coordinator import Coordinator
from sales.commercial.geography import locate
from sales.commercial.indexed_jobs import resolution_continuity
from sales.commercial.recommendations import assess as recommend
from sales.commercial.recommendation_store import listing
from scripts.replay_commercial50 import replay,load
from test_commercial44 import populate,job
NOW=datetime(2026,10,18,21,tzinfo=timezone.utc)
class Strategy50(unittest.TestCase):
 def test_all_required_distinct_strategies(self):
  ids={s['id'] for s in catalog()};self.assertEqual(len(ids),15)
  self.assertTrue({'direct_freelance','agency_collaborations','wordpress_projects','woocommerce_projects','frontend_contracts','website_creation','explicit_rebuild','startup_projects','remote_contracts','official_careers'}<=ids)
 def test_sparse_unique_bilingual_national_and_remote(self):
  ps=[p for e in ENGINES for p in plans(e,['Veneto','Toscana'])]
  self.assertEqual(len(ps),len({p['query'] for p in ps}));self.assertLess(len(ps),100)
  self.assertEqual({p['language'] for p in ps},{'it','en'});self.assertEqual({p['geography_tier'] for p in ps},{'TIER_1','TIER_2','TIER_3'})
  self.assertTrue(any(p['region']=='Italia' for p in ps));self.assertTrue(all(p['region'] in ('Veneto','Toscana') for p in ps if p['engine']=='WEBSITE_REBUILD'))
 def test_query_period_standing_vs_jobs(self):
  self.assertTrue(all(p['discovery_period']=='' for p in plans('AGENCIES',['Veneto']) if p['strategy_id']=='agency_collaborations'))
  self.assertTrue(all(p['discovery_period']=='month' for p in plans('FREELANCE',['Veneto'])))
 def test_no_old_profile_changes(self):
  baseline=json.loads(archived_text('PHASE-4.5-METRICS.json'))
  # Snapshot 4.2 also stores the same unmodified public profiles.
  self.assertEqual(PROFILES,json.loads(archived_text('PHASE-4.2-METRICS.json'))['profiles'])
 def test_rotation_and_bounded_feedback(self):
  ps=plans('FREELANCE',['Veneto']);h={'as_of':NOW.isoformat(),'queries':[],'strategies':{}}
  used=[]
  for _ in range(7):
   p,_=select(ps,used,h);self.assertIsNotNone(p);used.append(p)
  self.assertEqual(len({p['strategy_id'] for p in used}),7)
  self.assertEqual({p['geography_tier'] for p in used},{'TIER_1','TIER_2','TIER_3'})
 def test_recent_completed_query_not_repeated_but_expires(self):
  from sales.commercial.planner import query_key
  ps=plans('FREELANCE',['Veneto']);p=ps[0];h={'as_of':NOW.isoformat(),'strategies':{},'queries':[{'key':('FREELANCE',query_key(p['query']),p['discovery_period']),'state':'done','at':NOW.isoformat(),'campaign_id':29}]}
  chosen,excluded=select([p],[],h);self.assertIsNone(chosen);self.assertEqual(excluded[0]['reason'],'already_explored_within_6h')
  self.assertIsNotNone(select([p],[],h,NOW+timedelta(hours=7))[0])
 def test_real_benchmark_improves_without_losing_positives(self):
  r=replay();self.assertLess(r['new']['false_positives'],r['baseline']['false_positives']);self.assertGreaterEqual(r['new']['recall']['value'],r['baseline']['recall']['value']);self.assertFalse(r['regressions'])
 def test_historical_errors_removed(self):
  b,s=load();r=replay();rows={v['id']:v for v in r['cases']}
  for id in (912,915,916,825):self.assertEqual(rows['historical-'+str(id)]['decision'],'exclude')
  rec={j['id']:j for j in r['recommendations']};self.assertFalse(rec[915]['recommended']);self.assertFalse(rec[858]['recommended'])
 def test_social_unknown_remains_for_manual_review(self):
  r=assess({'url':'https://linkedin.com/jobs/view/wordpress-freelance-at-alfa-123456','title':'WordPress freelance at Alfa'},'FREELANCE')
  self.assertEqual(r['decision'],'admit');self.assertFalse(r['source_intelligence']['verified_original'])
 def test_remote_europe_supported_only_on_original_request(self):
  identity={'name':'Alfa','identity_status':'unknown','country':'US'}
  self.assertTrue(locate([],identity,'We are hiring a contractor remote Europe')['remote_italy'])
  self.assertFalse(locate([],identity,'We are hiring a contractor Remote US')['remote_italy'])
  self.assertFalse(locate([],identity,'Remote US only')['eligible'])
  self.assertFalse(locate([],identity,'Remote EMEA')['eligible'])
 def test_seller_with_real_separate_request_retained(self):
  self.assertEqual(assess({'url':'https://a.test/lavora-con-noi','title':'Web agency','content':'Realizziamo siti. Cerchiamo sviluppatori WordPress freelance per i nostri progetti.'},'AGENCIES')['decision'],'admit')
 def test_group_membership_blocks_audit_not_invents_size(self):
  from sales.commercial.target_fit import evaluate
  page={'url':'https://gorfar.test/','status':200,'checked_at':NOW.isoformat(),'html':'<main><p>Gor.Far., divisone di E80 Group dedicata alla carpenteria, produce componenti su misura.</p></main>'}
  r=evaluate({'name':'Gor.Far. Srl','identity_status':'verified','contacts':[{}]},[page],{'eligible':True})
  self.assertFalse(r['audit_allowed']);self.assertIn('documented_group_membership_requires_review',r['reasons']);self.assertEqual(r['size']['status'],'UNKNOWN')
 def test_client_group_not_attributed_to_owner(self):
  from sales.commercial.target_fit import evaluate
  page={'url':'https://alfa.test/','status':200,'checked_at':NOW.isoformat(),'html':'<main><p>Produciamo componenti industriali.</p><p>Il nostro cliente GorFar è una divisione di E80 Group.</p></main>'}
  r=evaluate({'name':'Alfa','identity_status':'verified','contacts':[{}]},[page],{'eligible':True})
  self.assertNotIn('documented_group_membership_requires_review',r['reasons'])

class Stored50(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.db');self.store.init()
 def tearDown(self):self.tmp.cleanup()
 def test_preview_is_read_only_and_no_inference(self):
  with self.store.connect() as c:before=c.execute('select count(*) from campaigns').fetchone()[0]
  with patch('sales.commercial.coordinator.acquire',side_effect=AssertionError('network')),patch('sales.commercial.ai.infer',side_effect=AssertionError('AI')):
   p=preview(self.store,{'commercial_engines':list(ENGINES),'regions':['Veneto'],'mode':'pilot'},NOW)
  self.assertEqual(p['planned_queries'],12);self.assertEqual(p['maximums']['max_serper_credits'],28)
  with self.store.connect() as c:self.assertEqual(c.execute('select count(*) from campaigns').fetchone()[0],before)
 def test_deep_requires_explicit_authorization_before_campaign_write(self):
  with self.assertRaisesRegex(ValueError,'Conferma'):ResearchStore(self.store).create({'commercial_engines':list(ENGINES),'mode':'deep'})
  with self.store.connect() as c:self.assertEqual(c.execute('select count(*) from campaigns').fetchone()[0],0)
  f={'commercial_engines':list(ENGINES),'mode':'deep','deep_authorized':True};p=preview(self.store,f,NOW);c=ResearchStore(self.store).create({**f,'deep_plan_token':p['approval_token']});self.assertEqual(c['filters']['work_budget'],DEEP_PROFILE)
 def test_deep_rejects_stale_budget_approval(self):
  f={'commercial_engines':list(ENGINES),'mode':'deep','regions':['Veneto']};p=preview(self.store,f,NOW)
  with self.assertRaisesRegex(ValueError,'impostazioni cambiate'):ResearchStore(self.store).create({**f,'regions':['Toscana'],'deep_authorized':True,'deep_plan_token':p['approval_token']})
 def test_new_campaign_uses_strategy_engine_and_all_pilot_queries_distinct(self):
  c=ResearchStore(self.store).create({'commercial_engines':list(ENGINES),'mode':'pilot','regions':['Veneto']});self.assertEqual(c['filters']['search_version'],'5.0')
  co=Coordinator(self.store,c);co.initialize();co.tick()
  with self.store.connect() as db:
   rows=[json.loads(r[0]) for r in db.execute("select payload from research_tasks where kind='search'")]
  self.assertEqual(len(rows),4);self.assertTrue(all(p['strategy_id'] and p['strategy_version']=='5.0' for p in rows))
 def test_known_404_backoff_and_changed_request(self):
  j=job(url='https://source.test/jobs/1',classification='access_incomplete',reason='Fonte originale HTTP 404');populate(self.store,[j]);d=j['body']['discovery']
  self.assertEqual(decision(self.store,'FREELANCE',d,NOW)['reason'],'known_404_backoff')
  self.assertIsNone(decision(self.store,'FREELANCE',{**d,'snippet':'New request React contractor'},NOW))
  self.assertIsNone(decision(self.store,'FREELANCE',d,NOW+timedelta(days=8)))
 def test_standing_same_request_does_not_block_new_url_same_company(self):
  j=job(classification='ongoing');populate(self.store,[j]);d=j['body']['discovery']
  self.assertEqual(decision(self.store,'FREELANCE',d,NOW)['reason'],'known_request_unchanged')
  self.assertIsNone(decision(self.store,'FREELANCE',{**d,'url':'https://linkedin.com/jobs/view/other-role-456'},NOW))
 def test_employment_is_separate_default(self):
  j=job('WordPress Developer','Assunzione dipendente a tempo indeterminato.');populate(self.store,[j])
  self.assertEqual(listing(self.store,{'category':'all'},NOW)['total'],0)
  self.assertEqual(listing(self.store,{'category':'all','employment':'employment'},NOW)['total'],1)
 def test_new_query_inherits_strategy_lineage(self):
  c=ResearchStore(self.store).create({'commercial_engines':['STARTUPS'],'mode':'pilot'});co=Coordinator(self.store,c)
  co.enqueue('resolve','STARTUPS',{'query':'Alfa sito ufficiale','origin':{'strategy_id':'startup_projects'}},'example')
  with self.store.connect() as db:p=json.loads(db.execute('select payload from research_tasks').fetchone()[0])
  self.assertEqual(p['strategy_id'],'startup_projects')
 def test_small_samples_never_claim_learning(self):
  h=history(self.store,NOW);self.assertEqual(h['strategies'],{});self.assertTrue(h['precision_requires_labelled_benchmark'])

class AdaptiveLearning50(unittest.TestCase):
 def test_fairness_prevents_monopoly_after_first_round(self):
  ps=plans('FREELANCE',['Veneto']);h={'as_of':NOW.isoformat(),'queries':[],
    'strategies':{'direct_freelance':{'priority_adjustment':12,'sample_sufficient':True},'frontend_contracts':{'priority_adjustment':-12,'sample_sufficient':True}}}
  used=[]
  for _ in range(24):
   p,_=select(ps,used,h);self.assertIsNotNone(p);used.append(p)
  from collections import Counter
  counts=Counter(p['strategy_id'] for p in used)
  self.assertEqual(len(counts),7);self.assertLessEqual(max(counts.values()),14)
  regions=['Veneto','Lombardia','Piemonte','Emilia-Romagna','Liguria','Friuli-Venezia Giulia','Trentino-Alto Adige','Valle d’Aosta','Toscana']
  ps=plans('WEBSITE_REBUILD',regions);used=[]
  for _ in range(24):
   p,_=select(ps,used,h);used.append(p)
  self.assertEqual({p['region'] for p in used},set(regions))
 def test_budget_denominators_cache_not_network(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=Store(Path(tmp)/'db');store.init();rs=ResearchStore(store)
   c=rs.create({'commercial_engines':['FREELANCE'],'mode':'pilot'});co=Coordinator(store,c);co.initialize();co.tick()
   with store.connect() as db:
    t=db.execute("select id from research_tasks where kind='search'").fetchone()[0]
    db.execute("update research_tasks set state='done' where id=?",(t,))
    db.execute("INSERT INTO discovery_operations(campaign_id,task_id,strategy,kind,provider,status,seconds,pages,cached_pages,unique_urls,details,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(c['id'],t,'FREELANCE','search','serper','ok',.2,0,0,0,encode({'cache_hit':True,'network_attempted':False,'credits':0}),NOW.isoformat()))
   h=history(store,NOW);m=next(iter(h['strategies'].values()))
   self.assertEqual(m['queries_executed'],1);self.assertEqual(m['query_cache_hits'],1);self.assertEqual(m['network_requests'],0);self.assertEqual(m['credits'],0);self.assertFalse(m['sample_sufficient']);self.assertEqual(m['priority_adjustment'],0)
   with store.connect() as db:
    for _ in range(2):
     db.execute("INSERT INTO discovery_operations(campaign_id,task_id,strategy,kind,provider,status,seconds,pages,cached_pages,unique_urls,details,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(c['id'],t,'FREELANCE','search','serper','ok',.2,1,0,1,encode({'network_attempted':True,'credits':1}),NOW.isoformat()))
   m=next(iter(history(store,NOW)['strategies'].values()))
   self.assertEqual(m['network_requests'],2);self.assertEqual(m['credits'],2);self.assertEqual(m['query_cache_hits'],1)

if __name__=='__main__':unittest.main()
