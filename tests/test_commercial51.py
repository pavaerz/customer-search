"""Phase 5.1: frozen real evidence, isolated SQLite and injected providers only."""
import copy,gzip,json,tempfile,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from sales.commercial import demand
from sales.commercial.resources import Budget,BudgetExceeded,deep_review_slot
from sales.commercial.inspection import inspect
from sales.commercial.coordinator import Coordinator
from sales.db import Store
from sales.research_store import ResearchStore

AS_OF=date(2026,10,18)
def load():
 with gzip.open(Path(__file__).parent/'fixtures/commercial51/campaign30.json.gz','rt') as f:return json.load(f)
def page(text,title='Progetto WordPress',url='https://alfa.example/project',job=None):
 return {'url':url,'status':200,'checked_at':'2026-10-18T12:00:00Z','html':'<title>'+title+'</title><main><p>'+text+'</p></main>'+('<script type="application/ld+json">'+json.dumps({'@type':'JobPosting',**job})+'</script>' if job else '')}
def assess(text,**kw):return demand.assess(demand.source_from_page(page(text,**kw)),today=AS_OF)

class Demand51(unittest.TestCase):
 def test_buyer_request(self):self.assertEqual(assess('I am looking for a freelance WordPress developer for our new website.')['page_type'],'BUYER_DEMAND')
 def test_supplier(self):
  r=assess('We offer WordPress development services.');self.assertTrue(r['excluded']);self.assertEqual(r['page_type'],'SUPPLIER_OFFER');self.assertLess(r['evidence_level'],4)
 def test_completed_not_current(self):
  r=assess('We were looking for a WordPress developer. They delivered the new website.');self.assertEqual(r['page_type'],'COMPLETED_PROJECT');self.assertFalse(r['request_observed'])
 def test_supplier_with_separate_career_request(self):
  r=assess('We offer WordPress services. We are looking for a freelance WordPress developer to build our projects.');self.assertTrue(r['request_observed']);self.assertFalse(r['excluded'])
 def test_listing_overrides_embedded_job(self):
  r=assess('Results for 61 roles.',title='61 Remote React Jobs',url='https://jobs.example/jobs',job={'title':'WordPress Developer','description':'We are seeking a WordPress developer.'});self.assertEqual(r['page_type'],'JOB_AGGREGATION')
 def test_individual_job(self):
  r=assess('We are seeking a freelance WordPress developer.',title='WordPress Developer',url='https://jobs.example/job/123');self.assertEqual(r['page_type'],'INDIVIDUAL_JOB')
 def test_unknown_never_becomes_negative(self):
  r=assess('Azienda Alfa.');self.assertFalse(r['excluded']);self.assertEqual(r['page_type'],'UNKNOWN')
 def test_standing_needs_invitation(self):
  r=assess('Entra nella nostra rete: cerchiamo professionisti freelance WordPress.');self.assertEqual(r['page_type'],'STANDING_COLLABORATION');self.assertEqual(r['level'],'NEEDS_REVIEW');self.assertTrue(r['freshness']['standing_exempt'])
 def test_remote_not_worldwide(self):self.assertEqual(demand.geography('The work will be fully remote')['status'],'GEO_UNKNOWN')
 def test_emea_unknown(self):self.assertEqual(demand.geography('Fully remote EMEA')['status'],'GEO_UNKNOWN')
 def test_remote_europe(self):self.assertEqual(demand.geography('Fully remote within Europe')['status'],'GEO_COMPATIBLE_CONFIRMED')
 def test_worldwide_over_foreign_office(self):self.assertEqual(demand.geography('Our office is in Jacksonville. Work remote worldwide.')['status'],'GEO_COMPATIBLE_CONFIRMED')
 def test_us_restriction_wins(self):self.assertEqual(demand.geography('Remote worldwide. US only.')['status'],'GEO_INCOMPATIBLE_CONFIRMED')
 def test_onsite_jacksonville(self):self.assertEqual(demand.geography('This is an onsite position in Jacksonville, FL.')['status'],'GEO_INCOMPATIBLE_CONFIRMED')
 def test_foreign_address_alone_unknown(self):self.assertEqual(demand.geography('Location: US')['status'],'GEO_UNKNOWN')
 def test_unreal_not_web(self):self.assertEqual(demand.technical_fit('Software Developer','We are seeking a C++ Unreal Engine 3D developer.')['status'],'INCOMPATIBLE')
 def test_multidisciplinary_frontend_retained(self):self.assertEqual(demand.technical_fit('Software Developer','Build React frontend applications integrated with our C++ platform.')['status'],'COMPATIBLE')
 def test_react_native_alone(self):self.assertEqual(demand.technical_fit('React Native developer','iOS and Android apps')['status'],'INCOMPATIBLE')
 def test_electrical_excluded(self):self.assertEqual(demand.technical_fit('Electrical Engineer','Engineering industrial solutions')['status'],'INCOMPATIBLE')
 def test_publication_original_only(self):
  r=assess('We need a WordPress developer.',job={'title':'WordPress Developer','description':'We need a WordPress developer.','datePosted':'2026-10-07'});self.assertEqual(r['freshness']['age_days'],11);self.assertEqual(r['freshness']['priority'],'8-14')
 def test_dated_individual_job_cannot_borrow_standing_exemption(self):
  r=assess('Cerchiamo freelance WordPress per collaborazioni continuative.',job={'title':'WordPress Developer','description':'Cerchiamo freelance WordPress per collaborazioni continuative.','datePosted':'2026-09-01'})
  self.assertFalse(r['freshness']['standing_exempt']);self.assertTrue(r['excluded'])
 def test_stale_and_future(self):
  for dt,expected in [('2026-09-01','STALE_CONFIRMED'),('2026-12-01','DATE_UNKNOWN')]:
   self.assertEqual(assess('We need WordPress.',job={'description':'We need WordPress.','datePosted':dt})['freshness']['status'],expected)
 def test_snippet_never_proves_buyer(self):
  r=demand.assess({'url':'https://example.com/jobs/view/1','text':'We are seeking WordPress freelance.','original':False},today=AS_OF);self.assertEqual(r['evidence_level'],1);self.assertFalse(r['request_observed'])
 def test_publisher_not_buyer(self):
  r=assess('I am looking for a WordPress freelancer.',url='https://www.twine.net/projects/123');self.assertIsNone(r['actors']['buyer'])
 def test_named_hiring_subject_not_publisher(self):
  r=assess('We are seeking a web designer.',url='https://portal.example/job/1',job={'title':'Web designer','description':'Prout is seeking a web designer.','hiringOrganization':{'name':'Prout'}});self.assertEqual(r['actors']['buyer'],'Prout');self.assertEqual(r['actors']['buyer_status'],'ATTRIBUTED_UNVERIFIED')
 def test_verified_gate_needs_open_contact(self):
  p=page('We are seeking WordPress freelance. Remote worldwide.',job={'title':'WordPress Developer','description':'We are seeking a WordPress freelance developer. Remote worldwide.','hiringOrganization':{'name':'Alfa'},'datePosted':'2026-10-17'})
  ident={'name':'Alfa','identity_status':'verified','contacts':[]};src=demand.source_from_page(p)
  r=demand.assess(src,ident,today=AS_OF);self.assertEqual(r['level'],'POTENTIAL')
  body={'verification':{'status':'complete','request_verified':True,'currently_open':True}}
  self.assertEqual(demand.assess(src,ident,body,AS_OF)['level'],'VERIFIED')
  ident['contacts']=[{'type':'email','value':'info@alfa.example'}]
  self.assertEqual(demand.assess(src,ident,body,AS_OF)['level'],'READY_TO_CONTACT')
 def test_no_automatic_promotion(self):
  body={'state':'UNVERIFIABLE'};demand.apply(body,assess('I am looking for a WordPress freelancer.'));self.assertEqual(body['state'],'UNVERIFIABLE')
 def test_browser_not_enabled_for_semantic_ambiguity(self):self.assertFalse(assess('I am looking for a WordPress freelancer.')['browser_diagnostic']['eligible'])
 def test_prefilter_all_demand_engines(self):
  from sales.commercial.discovery import assess as discover
  for engine in ('FREELANCE','AGENCIES','STARTUPS'):
   r=discover({'url':'https://remoteonly.io/remote-react-native-jobs','title':'18 React Native Remote Jobs','content':'Companies hiring remote React Native roles','demand_version':'5.1'},engine);self.assertEqual(r['decision'],'exclude')
 def test_followups_only_specific_web_roles(self):
  from sales.commercial.discovery import followup_allowed
  result={'engine':'FREELANCE','demand_assessment':{'page_type':'JOB_AGGREGATION','excluded':True}}
  self.assertTrue(followup_allowed(result,{'url':'https://board.example/job/123','anchor':'WordPress developer','recruitment_context':True}))
  self.assertFalse(followup_allowed(result,{'url':'https://board.example/job/124','anchor':'Electrical Engineer','recruitment_context':True}))
 def test_ai_unknown_buyer_original_can_be_interpreted(self):
  from sales.commercial.commercial_gate import sufficient
  r={'url':'https://x.example','demand_assessment':assess('I am looking for a freelance WordPress developer.')}
  evidence=[{'id':'e1','url':r['url'],'kind':'text','text':'I am looking for a freelance WordPress developer to build our website.'}]
  self.assertTrue(sufficient('FREELANCE',r,evidence)['allowed'])
  evidence[0]['kind']='indexed_text';self.assertFalse(sufficient('FREELANCE',r,evidence)['allowed'])
 def test_ai_skips_conclusive_negative(self):
  from sales.commercial.ai import eligibility
  self.assertFalse(eligibility({'demand_assessment':assess('We offer WordPress services.')})[0])

class Real51(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.fixture=load();cls.docs={d['url']:d for d in cls.fixture['documents']}
 def evaluate(self,id):
  b=next(x['body'] for x in self.fixture['items'] if x['id']==id)
  return demand.assess(demand.source_from_document(self.docs[b['url']]),b.get('identity'),b,AS_OF)
 def test_all_111_frozen_and_historical_states_unchanged(self):
  before=json.dumps(self.fixture,sort_keys=True)
  for x in self.fixture['items']:
   if x['body']['url'] in self.docs:self.evaluate(x['id'])
  self.assertEqual(len(self.fixture['items']),111);self.assertEqual(before,json.dumps(self.fixture,sort_keys=True))
 def test_six_mandatory_negatives(self):
  for i in (927,965,969,973,975,998):
   with self.subTest(id=i):self.assertTrue(self.evaluate(i)['excluded'])
 def test_three_precise_leads_retained(self):
  for i in (929,931,950):
   with self.subTest(id=i):
    r=self.evaluate(i);self.assertFalse(r['excluded']);self.assertEqual(r['level'],'NEEDS_REVIEW');self.assertEqual(r['geography']['status'],'GEO_UNKNOWN')
 def test_original_date_prout(self):self.assertEqual(self.evaluate(950)['freshness']['published_at'],'2026-10-07')
 def test_entice_completed(self):self.assertEqual(self.evaluate(998)['page_type'],'COMPLETED_PROJECT')
 def test_iocos_standing(self):self.assertEqual(self.evaluate(931)['actors']['buyer'],'IOCOS');self.assertTrue(self.evaluate(931)['freshness']['standing_exempt'])
 def test_geography_dotnet_no_false_technical_rejection(self):
  r=self.evaluate(974);self.assertIn('geo_incompatible',r['reasons']);self.assertNotIn('job_incompatible',r['reasons'])
 def test_manual_unknowns_not_negative_labels(self):
  for r in self.fixture['cases']:
   if r['reference']['certainty']=='Unknown' and r['id']!=921:self.assertIsNone(r['reference']['preserve_lead'])

class Budget51(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=Store(Path(self.tmp.name)/'test.db');self.store.init();self.rs=ResearchStore(self.store)
  self.c=self.rs.create({'commercial_engines':['FREELANCE'],'regions':['Veneto'],'mode':'pilot','work_budget':{'max_candidates_per_engine':1}})
  self.worker=Coordinator(self.store,self.c);self.worker.initialize()
 def task(self,n):
  self.worker.enqueue('candidate','FREELANCE',{'url':f'https://alfa.example/{n}'},str(n));return self.rs.claim(self.c['id'],self.c['generation'])
 def budget(self,task):
  b=Budget(self.store,self.c,'FREELANCE',self.worker.budget);b.task_id=task['id'];return b
 def test_enqueue_not_deep_quota(self):
  t=self.task(1);self.assertEqual(self.budget(t).used('candidates'),0)
 def test_reserve_once_across_retry(self):
  t=self.task(1);b=self.budget(t)
  with b.task(lambda:None):deep_review_slot();deep_review_slot()
  with b.task(lambda:None):deep_review_slot()
  self.assertEqual(b.used('candidates'),1)
 def test_limit_still_enforced(self):
  t=self.task(1);b=self.budget(t)
  with b.task(lambda:None):deep_review_slot()
  self.rs.task_done(t['id']);t2=self.task(2)
  with self.budget(t2).task(lambda:None):
   with self.assertRaises(BudgetExceeded):deep_review_slot()
 def test_seller_stops_before_identity_and_slot(self):
  t=self.task(1);b=self.budget(t);p=page('We offer WordPress services.',url=t['payload']['url'])
  with b.task(lambda:None),patch('sales.commercial.inspection.ResearchWeb.get',return_value=p) as get:
   r=inspect(self.store,t['payload']);self.assertEqual(get.call_count,1);self.assertEqual(r['result']['classification'],'supplier_offer')
  self.assertEqual(b.used('candidates'),0)
 def test_real_request_consumes_one_slot(self):
  t=self.task(1);b=self.budget(t);p=page('I am looking for a WordPress freelance developer.',url=t['payload']['url'])
  with b.task(lambda:None),patch('sales.commercial.inspection.ResearchWeb.get',return_value=p):inspect(self.store,t['payload'])
  self.assertEqual(b.used('candidates'),1)
 def test_stop_blocks_new_reservations(self):
  t=self.task(1);self.rs.stop(self.c['id'])
  with self.assertRaises(InterruptedError):
   with self.budget(t).task(lambda:None):deep_review_slot()
 def test_counter_projection(self):
  self.task(1);st=self.rs.campaign(self.c['id'])['candidate_stages'];self.assertEqual(st['ADMITTED_CANDIDATES'],1);self.assertEqual(st['DEEP_REVIEW_CANDIDATES'],0)
 def test_deep_limit_message_and_tick(self):
  t=self.task(1);b=self.budget(t)
  with b.task(lambda:None):deep_review_slot()
  self.worker.tick();run=self.rs.campaign(self.c['id'])['engine_runs'][0]
  self.assertEqual(run['exhausted_resource'],'candidates');self.assertIn('approfondimenti',run['budget_reason'])
 def test_resume_does_not_charge_twice(self):
  t=self.task(1);b=self.budget(t)
  with b.task(lambda:None):deep_review_slot()
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.resume(self.c['id'])
  with self.budget(t).task(lambda:None):deep_review_slot()
  self.assertEqual(b.used('candidates'),1)
 def test_new_campaign_uses_51_same_budget(self):self.assertEqual(self.c['filters']['demand_version'],'5.1');self.assertEqual(self.worker.budget['max_candidates_per_engine'],1)


class Shadow51(unittest.TestCase):
 def test_real_pistes_mock_dispatch_without_inventing_buyer(self):
  from sales.commercial import ai
  from sales.commercial.ai_schema import unknown_output
  f=load();docs={d['url']:d for d in f['documents']}
  with tempfile.TemporaryDirectory() as td:
   st=Store(Path(td)/'test.db')
   with st.connect() as c:
    c.execute('CREATE TABLE campaigns(id INTEGER PRIMARY KEY,generation INTEGER,status TEXT)');c.execute("INSERT INTO campaigns VALUES(1,1,'running')");ai.migrate(c)
   cfg=ai.validate_config({'enabled':True,'provider':'MOCK','mode':'shadow','max_input_tokens':8192,'max_calls_per_campaign':20,'max_estimated_cost':1})
   campaign={'id':1,'generation':1,'filters':{'commercial':{'ai':cfg}}}
   called=[]
   def provider(payload,config,check):
    called.append(payload);return {'output':unknown_output(payload),'usage':{'input_tokens':100,'output_tokens':100},'reported_cost':0}
   for id in (929,931,950):
    body=copy.deepcopy(next(x['body'] for x in f['items'] if x['id']==id));doc=docs[body['url']]
    body['demand_assessment']=demand.assess(demand.source_from_document(doc),body.get('identity'),body,AS_OF)
    before=copy.deepcopy(body)
    with patch('sales.commercial.ai.infer',side_effect=AssertionError('external AI forbidden')):
     out=ai.analyze(st,campaign,body['engine'],id,body,[doc],provider=provider)
    self.assertEqual(out['status'],'completed',str((id,out.get('error'),out.get('bundle_metrics',{}).get('discard_reasons'))))
    self.assertIsNone(out['output']['actor']);self.assertEqual(before,body)
   self.assertEqual(len(called),3);self.assertEqual(ai.summary(st,1)['calls'],3)

if __name__=="__main__":unittest.main()
