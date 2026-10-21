from scripts.analysis_archive import read_text as archived_text
"""Historical evidence assertions and separate synthetic boundaries, all offline."""
import asyncio,copy,json,unittest
from pathlib import Path
from functools import lru_cache
from scripts.replay_commercial43 import replay,load
from sales.commercial.discovery import assess
from sales.commercial.request_profile import agency_supplier_pitch
from sales.commercial.opportunity_view import site_assessment
from sales.commercial.strategies import plans
from sales.commercial.catalog import PROFILES
from sales.commercial.browser_queue import ResourceSlots
@lru_cache(None)
def validation():return replay()
class Commercial43(unittest.TestCase):
 def test_real_positive_requests_survive_full_inspection(self):
  r=validation();self.assertEqual(r['metrics']['known_positive_recognition_recall']['numerator'],2)
  for c in r['records']:
   if c['label']=='POSITIVE':
    self.assertEqual(c['trace']['DOWNLOAD'],'SAVED_ORIGINAL');self.assertTrue(c['request_recognized']);self.assertNotEqual(c['view'],'NOT_ACTIONABLE')
 def test_all_81_agency_results_in_dataset(self):
  d,_=load();self.assertEqual(sum(c['campaign']==27 and c['engine']=='AGENCIES' for c in d['cases']),81)
 def test_dataset_no_synthetic_positive_or_assumed_current_job(self):
  d,_=load();p=[c for c in d['cases'] if c['label']=='POSITIVE'];self.assertEqual(len(p),2)
  self.assertTrue(all(c['source']=='saved_original' and c['original_content_hash'] for c in p));self.assertEqual(d['positive_current_open_commissions'],0)
 def test_original_blurr_pitch_rejected_before_http(self):
  r=next(c for c in validation()['records'] if c['id']=='27-1438');self.assertEqual(r['admission'],'exclude');self.assertEqual(r['admission_reason'],'agency_supplier_not_buyer');self.assertEqual(r['saved_reads'],[])
 def test_domilea_graphalia_unknown_not_negative_demand(self):
  for ident in ('25-1112','26-1150'):
   r=next(c for c in validation()['records'] if c['id']==ident);self.assertEqual(r['admission'],'admit');self.assertEqual(r['first_limiting_stage'],'DOWNLOAD');self.assertNotIn('view',r)
 def test_dexanet_selling_not_request(self):
  r=next(c for c in validation()['records'] if c['id']=='26-1149');self.assertEqual(r['admission'],'exclude')
 def test_seller_also_recruiting_not_blanket_excluded(self):
  text='Gestiamo sviluppo e design per agenzie. Cerchiamo sviluppatori WordPress freelance per i nostri progetti.'
  self.assertFalse(agency_supplier_pitch(text));self.assertEqual(assess({'url':'https://agency.example/lavora-con-noi','title':'Collabora','content':text},'AGENCIES')['decision'],'admit')
 def test_partial_browser_does_not_create_measured_issues(self):
  v=site_assessment({'browser':{'completed':False,'findings':[{'code':'overflow','status':'UNVALIDATED'}]}},True)
  self.assertEqual(v['level'],'A_COMPANY_ONLY');self.assertFalse(v['technical_findings']);self.assertFalse(v['explicit_rebuild_request'])
 def test_measured_issue_not_rebuild_request(self):
  v=site_assessment({'browser':{'completed':True,'findings':[{'code':'overflow','status':'CONFIRMED'}]}},True)
  self.assertEqual(v['level'],'C_MEASURED_ISSUES');self.assertIsNone(v['full_rebuild_justified']);self.assertFalse(v['explicit_rebuild_request'])
 def test_unattributed_rebuild_quote_not_request(self):
  b={'verification':{'request_verified':True},'evidence':[{'kind':'request','quote':'Vogliamo rifare il sito','attribution_status':'third_party'}]};self.assertEqual(site_assessment(b,True)['level'],'A_COMPANY_ONLY')
 def test_offering_quote_retains_sentence_not_menu(self):
  from sales.commercial.target_fit import evaluate
  p={'url':'https://company.example/','status':200,'checked_at':'2026-10-18T12:00:00+00:00','html':'<title>Azienda</title><nav>Prodotti</nav><main><p>Produciamo componenti in metallo per macchine industriali.</p></main>'}
  r=evaluate({'identity_status':'verified','name':'Alfa Srl','contacts':[{}]},[p],{'eligible':True})
  self.assertEqual(r['offer_evidence'][0]['quote'],'Produciamo componenti in metallo per macchine industriali.')
 def test_short_complete_offering_is_not_discarded(self):
  from sales.commercial.target_fit import evaluate
  p={'url':'https://company.example/','status':200,'checked_at':'2026-10-18','html':'<main><p>Produciamo componenti industriali.</p></main>'}
  r=evaluate({'identity_status':'verified','name':'Alfa Srl','contacts':[{}]},[p],{'eligible':True});self.assertTrue(r['offer_evidence'])
 def test_profiles_identical_to_prephase(self):
  baseline=json.loads(archived_text('PHASE-4.2-METRICS.json'));self.assertEqual(PROFILES,baseline['profiles'])
 def test_national_social_query_does_not_change_geo_filter(self):
  p=plans('FREELANCE',['Veneto','Toscana']);social=[r for r in p if r['source']=='linkedin']
  self.assertTrue(all('Italia' in r['query'] and r['region'] in ('Veneto','Toscana') for r in social));self.assertTrue(all('national_discovery' in r['search_geography_scope'] for r in social))
  self.assertLess(len({r['query'] for r in social}),len(social)) # planner deduplicates national variants
 def test_changed_strategy_does_not_inherit_old_query_penalty(self):
  from unittest.mock import Mock
  from sales.commercial.planner import family_history
  connection=Mock();cursor=Mock();cursor.fetchall.return_value=[{'campaign_id':27,'payload':json.dumps({'family':'agency_open','query':'old query','strategy_version':'4.2'})}];connection.execute.side_effect=[cursor,[],[]]
  self.assertEqual(family_history(connection,'AGENCIES',28,'4.3'),{})
 def test_no_real_operations_in_replay(self):
  r=validation();self.assertEqual([r[k] for k in ('network_calls','ai_calls','production_writes','browser_runs')],[0]*4)

class ResourceQueue43(unittest.IsolatedAsyncioTestCase):
 async def test_queued_critical_dependencies_precede_images(self):
  slots=ResourceSlots(1);order=[]
  async def use(label,kind):
   async with slots.acquire(kind):order.append(label)
  async with slots.acquire('image'):
   images=[asyncio.create_task(use(str(i),'image')) for i in range(4)];await asyncio.sleep(0)
   critical=asyncio.create_task(use('script','script'));await asyncio.sleep(0)
  await asyncio.gather(*images,critical);self.assertEqual(order,['script','0','1','2','3']);self.assertEqual(slots.active,0)
 async def test_cancelled_waiter_releases_queue(self):
  slots=ResourceSlots(1)
  async with slots.acquire('image'):
   async def wait():
    async with slots.acquire('script'):pass
   task=asyncio.create_task(wait());await asyncio.sleep(0);task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
   self.assertEqual(slots.waiting,[])
  async with slots.acquire('image'):self.assertEqual(slots.active,1)
  self.assertEqual(slots.active,0)
