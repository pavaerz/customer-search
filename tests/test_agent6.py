"""Offline only: frozen real documents, local database and injected model/search."""
import copy,gzip,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store,digest,now
from sales.research_store import ResearchStore
from sales.agent6 import FLOWS,config
from sales.agent6 import schema,qualification as q,memory,ai,api
from sales.agent6.coordinator import AgentCoordinator
from sales.commercial.catalog import options,ENGINES
from sales.commercial.coordinator import run_campaign

DATE='2026-10-19T12:00:00Z'
TEXT='Alfa Srl\nPosted 2 days ago\nWe are looking for a freelance WordPress developer to build our complete website. Remote from Italy.\nBudget: €4000 fixed price\ninfo@alfa.example'
def source(text=TEXT,**kw):return {'url':'https://alfa.example/careers','title':'WordPress developer','text':text,'original':True,'checked_at':DATE,**kw}
def output(src=None,kind='BUYER_DEMAND',fields=None):
 src=src or source();ev=schema.bundle([{'id':'1',**src,'document_id':'doc'}]);facts=[]
 for field,span in (fields or {'entity':'Alfa Srl','publication':'Posted 2 days ago','request':'We are looking for a freelance WordPress developer to build our complete website. Remote from Italy.','technical':'WordPress developer','contract':'freelance','geography':'Remote from Italy.'}).items():
  e=next(e for e in ev if span in e['text']);a=e['text'].index(span);facts.append({'field':field,'ref':{'id':e['id'],'start':a,'end':a+len(span)}})
 a={'result_id':'1','kind':kind,'kind_ref':facts[0]['ref'],'facts':facts,'hypothesis':'Progetto completo da confermare con il committente','missing':[]}
 return {'task':schema.READ,'result_ids':['1'],'evidence':ev},{'analyses':[a]}
def identity():return {'identity_status':'verified','name':'Alfa Srl','website':'https://alfa.example','contacts':[{'type':'email','value':'info@alfa.example','url':'https://alfa.example/careers'}]}
def evaluated(src=None,kind='BUYER_DEMAND',ident=True,fields=None):
 p,o=output(src,kind,fields);a=schema.validate(o,p)['analyses'][0];return q.evaluate(src or source(),a,p['evidence'],'AZIENDE',identity() if ident else {})

class Contracts(unittest.TestCase):
 def test_real_cited_request_can_pass(self):self.assertEqual(evaluated()['state'],'VERIFIED')
 def test_unknown_identity_not_verified(self):self.assertEqual(evaluated(ident=False)['state'],'NEEDS_REVIEW')
 def test_remote_not_italy(self):
  s=source(TEXT.replace('Remote from Italy.','Remote work.'));fields={'entity':'Alfa Srl','request':'We are looking for a freelance WordPress developer','technical':'WordPress developer','contract':'freelance'}
  self.assertIn('geography',evaluated(s,fields=fields)['missing'])
 def test_unknown_budget_remains_unknown(self):self.assertEqual(q.money('Series A funding €5 million; our website exists.')['kind'],'UNKNOWN')
 def test_hourly_not_project_budget(self):self.assertEqual(q.money('Pay: $75 - $100 per hour')['kind'],'HOURLY')
 def test_salary_not_project_budget(self):self.assertEqual(q.money('Salary: $100000 per year')['kind'],'ANNUAL_SALARY')
 def test_small_budget_blocks(self):self.assertIn('declared_budget_insufficient_for_target',q.objective(source('Budget: $500 fixed price'))['counterevidence'])
 def test_old_job(self):self.assertIn('stale_request',q.objective(source('Posted 20 days ago'))['counterevidence'])
 def test_labelled_absolute_date(self):self.assertEqual(q.temporal('Posted on October 17, 2026',DATE,True)['published_at'],'2026-10-17')
 def test_future_date_not_recent(self):self.assertEqual(q.temporal('Posted on 2026-12-01',DATE,True)['status'],'UNKNOWN')
 def test_index_date_never_dates_request(self):self.assertEqual(q.objective(source('Posted 2 days ago',original=False))['freshness']['status'],'UNKNOWN')
 def test_minor_fixes_no_promotion(self):
  s=source(TEXT.replace('complete website','minor fixes'));fields={'entity':'Alfa Srl','request':'We are looking for a freelance WordPress developer to build our minor fixes. Remote from Italy.','technical':'WordPress developer','contract':'freelance','geography':'Remote from Italy.'}
  self.assertIn('scope',evaluated(s,fields=fields)['missing'])
 def test_publisher_not_buyer(self):
  p,o=output();self.assertEqual(q.evaluate(source(),schema.validate(o,p)['analyses'][0],p['evidence'],'AZIENDE',{**identity(),'name':'Jobboard Publishing'})['state'],'NEEDS_REVIEW')
 def test_external_collaboration_explicitly_refused(self):
  r=q.objective(source('We are looking for a WordPress developer. Permanent contract, no freelancers.'))
  self.assertIn('employee_job',r['counterevidence'])
 def test_implicit_proposal_requires_independent_originals(self):
  text='''Alfa Srl
Posted 2 days ago
Alfa Srl new product line.
Alfa Srl online catalogue is absent.
complete website
WordPress
not yet available
Remote from Italy.''' 
  src=source(text);ev=schema.bundle([{'id':'1',**src,'document_id':'official'},{'id':'1','url':'https://press.example/news','text':'Report: Alfa Srl new product line.','original':True,'document_id':'press'}])
  facts=[]
  for field,span in {'entity':'Alfa Srl','signal':'Alfa Srl new product line.','digital_gap':'Alfa Srl online catalogue is absent.','scope':'complete website','feasibility':'WordPress','existing_solution':'not yet available'}.items():
   e=next(e for e in ev if span in e['text'] and (field!='signal' or e['document_id']=='press'));start=e['text'].index(span);facts.append({'field':field,'ref':{'id':e['id'],'start':start,'end':start+len(span)}})
  a={'result_id':'1','kind':'COMPANY_SIGNAL','kind_ref':facts[0]['ref'],'facts':facts,'hypothesis':'Nuovo sito da discutere','missing':[]}
  a=schema.validate({'analyses':[a]},{'task':schema.READ,'result_ids':['1'],'evidence':ev})['analyses'][0]
  self.assertEqual(q.evaluate(src,a,ev,'NEWS',identity())['state'],'POTENTIAL')
  # Reusing the same document cannot provide a second independent signal.
  for e in ev:e['document_id']='official'
  self.assertNotIn(q.evaluate(src,a,ev,'NEWS',identity())['state'],('POTENTIAL','VERIFIED'))
 def test_unverified_ai_unknown_is_not_false(self):
  p,o=output(kind='UNKNOWN');self.assertNotEqual(q.evaluate(source(),schema.validate(o,p)['analyses'][0],p['evidence'],'AZIENDE')['state'],'REJECTED')
 def test_offset_invention(self):
  p,o=output();o['analyses'][0]['facts'][0]['ref']['end']=99999
  with self.assertRaisesRegex(ValueError,'invalid_span'):schema.validate(o,p)
 def test_wrong_actor_source(self):
  p,o=output();p['evidence'][0]['result_id']='other'
  with self.assertRaisesRegex(ValueError,'wrong_source'):schema.validate(o,p)
 def test_footer_date_is_not_publication(self):
  p,o=output();f=o['analyses'][0]['facts'][0];f['field']='publication'
  with self.assertRaisesRegex(ValueError,'temporal_role_mismatch'):schema.validate(o,p)
 def test_index_temporal_rejected(self):
  p,o=output(source(original=False))
  with self.assertRaisesRegex(ValueError,'temporal_role_mismatch'):schema.validate(o,p)
 def test_hash_mutation(self):
  p,o=output();p['evidence'][0]['text']='altered'
  with self.assertRaisesRegex(ValueError,'wrong_source'):schema.validate(o,p)
 def test_bad_budget_semantics(self):
  p,o=output();o['analyses'][0]['facts'][0]['field']='budget'
  with self.assertRaisesRegex(ValueError,'unsupported_budget'):schema.validate(o,p)
 def test_query_bounds(self):
  with self.assertRaises(ValueError):schema.validate({'decision':'search','reason':'x','queries':[]},{'task':schema.PLAN})
 def test_no_similar_jobs_links(self):
  p={'url':'https://alfa.example/jobs','html':'<a href="/apply">Apply now</a><h2>Similar jobs</h2><a href="/bad">Apply now</a>','checked_at':DATE}
  self.assertEqual([x['url'] for x in q.followup_links(p)],['/apply'])
 def test_editorial_signal_not_opportunity(self):
  s=source('Alfa Srl expands. Posted 300 days ago');p,o=output(s,'EDITORIAL',{'entity':'Alfa Srl','signal':'Alfa Srl expands.'});a=schema.validate(o,p)['analyses'][0]
  self.assertEqual(q.evaluate(s,a,p['evidence'],'NEWS',identity())['state'],'IDENTIFIED')
 def test_webapp_risk_not_promoted(self):
  s=source(TEXT.replace('complete website','complete web app'));fields={'entity':'Alfa Srl','request':'We are looking for a freelance WordPress developer to build our complete web app. Remote from Italy.','technical':'WordPress developer','contract':'freelance','geography':'Remote from Italy.'}
  self.assertIn('feasibility',evaluated(s,fields=fields)['missing'])
 def test_implicit_two_fragments_not_independent(self):
  s=source('Alfa Srl\nNew products\nNo shop');p,o=output(s,'COMPANY_SIGNAL',{'entity':'Alfa Srl','signal':'New products','digital_gap':'No shop'})
  self.assertNotIn(q.evaluate(s,schema.validate(o,p)['analyses'][0],p['evidence'],'NEWS',identity())['state'],('VERIFIED','POTENTIAL'))

class Persistence(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.db');self.store.init();self.rs=ResearchStore(self.store)
  self.filters={'agent_version':'6.0','commercial_engines':list(FLOWS),'mode':'pilot','commercial':{'ai':{'enabled':True,'provider':'MOCK'}}}
  self.c=self.rs.create(self.filters);self.w=AgentCoordinator(self.store,self.c);self.w.initialize()
 def tearDown(self):self.tmp.cleanup()
 def test_five_flows_without_changing_legacy(self):self.assertEqual(len(options(self.filters)[0]),5);self.assertEqual(len(ENGINES),4)
 def test_stop_rejects_late_record(self):
  self.rs.stop(self.c['id'])
  with self.assertRaises(InterruptedError):memory.save_record(self.store,self.c,'AZIENDE',evaluated())
 def test_stop_resume_preserves_tasks(self):
  self.w.tick();self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);new=self.rs.resume(self.c['id']);w=AgentCoordinator(self.store,new);w.initialize();w.tick()
  with self.store.connect() as c:self.assertEqual(c.execute('select count(*) from research_tasks').fetchone()[0],5)
 def test_cross_flow_dedup(self):
  a=memory.save_record(self.store,self.c,'AZIENDE',evaluated());b=memory.save_record(self.store,self.c,'AGENCIES',evaluated());self.assertEqual(a,b);self.assertEqual(api.listing(self.store,{'flow':'AGENCIES'})['total'],1)
 def test_same_company_two_roles_distinct(self):
  a=evaluated();b={**a,'url':a['url']+'/2'};self.assertNotEqual(memory.request_key(a),memory.request_key(b))
 def test_syndication_role_code(self):
  a={**evaluated(),'title':'I-CPT-11658 WordPress'};b={**a,'url':'https://other.example/job'};self.assertEqual(memory.request_key(a),memory.request_key(b))
 def test_human_feedback_persists_and_changes_next_choice(self):
  b={**evaluated(),'strategy':'best'};rid=memory.save_record(self.store,self.c,'AZIENDE',b);memory.feedback(self.store,rid,'won')
  h=memory.history(Store(self.store.path),'AZIENDE');choice=memory.choose([{'strategy':'unknown'},{'strategy':'best'}],h,0,25);self.assertEqual(choice['strategy'],'best');self.assertGreater(choice['memory_adjustment'],3)
 def test_technical_error_does_not_reduce_commercial_priority(self):
  b={**evaluated(),'state':'UNVERIFIABLE','strategy':'test','technical_error':'http403'};memory.save_record(self.store,self.c,'AZIENDE',b);h=memory.history(self.store,'AZIENDE');self.assertEqual(h['strategies'][0]['priority_adjustment'],0);self.assertEqual(h['strategies'][0]['rejected'],0)
 def test_revision_does_not_double_learning_counts(self):
  b={**evaluated(),'strategy':'test'};memory.save_record(self.store,self.c,'AZIENDE',b);memory.save_record(self.store,self.c,'AZIENDE',{**b,'reason':'new review'});self.assertEqual(memory.history(self.store,'AZIENDE')['strategies'][0]['verified'],1)
 def test_exploration_quota(self):
  h={'strategies':[],'recent_queries':[]};self.assertEqual(sum(memory.choose([{'strategy':'a'}],h,i,25)['selection']=='exploration' for i in range(100)),25)
 def test_restore_is_explicit(self):
  b=evaluated();rid=memory.save_record(self.store,self.c,'AZIENDE',b);memory.feedback(self.store,rid,'not_interesting');memory.save_record(self.store,self.c,'AZIENDE',b);self.assertEqual(api.dossier(self.store,rid)['state'],'REJECTED');memory.feedback(self.store,rid,'restore');memory.save_record(self.store,self.c,'AZIENDE',b);self.assertEqual(api.dossier(self.store,rid)['state'],'VERIFIED')
 def test_manual_removal_is_immediate_without_erasing_evaluation(self):
  rid=memory.save_record(self.store,self.c,'AZIENDE',evaluated());memory.feedback(self.store,rid,'not_interesting')
  self.assertEqual(api.listing(self.store)['total'],0);self.assertEqual(api.listing(self.store,{'include_excluded':1})['total'],1)
  self.assertEqual(api.dossier(self.store,rid)['state'],'VERIFIED');self.assertEqual(api.counts(self.store,self.c['id'])['qualified'],0)
  memory.feedback(self.store,rid,'restore');self.assertEqual(api.listing(self.store)['total'],1)
 def test_verified_domain_unifies_legal_aliases(self):
  a=evaluated();s=source(TEXT.replace('Alfa Srl','Alfa S.r.l.'));p,o=output(s,fields={'entity':'Alfa S.r.l.','request':'We are looking for a freelance WordPress developer','technical':'WordPress developer','contract':'freelance','geography':'Remote from Italy.'})
  b=q.evaluate(s,schema.validate(o,p)['analyses'][0],p['evidence'],'AGENCIES',identity());self.assertEqual(a['entity_key'],b['entity_key'])
 def test_preview_no_side_effects(self):
  with patch('sales.commercial.ai_provider.infer',side_effect=AssertionError()):r=api.preview(self.store,self.filters)
  self.assertEqual(r['max_serper_requests'],35)
 def test_plan_is_persisted(self):
  query={k:k for k in ('query','strategy','objective','hypothesis','missing','expected_source','success','stop_condition')};query['query']='agenzie cercano freelance wordpress'
  self.w.tick();task=self.rs.claim(self.c['id'],self.c['generation'])
  def fake(payload,cfg,check):return {'output':{'decision':'search','reason':'test','queries':[query]},'usage':{'input_tokens':1,'output_tokens':1}}
  with patch('sales.agent6.ai.infer',side_effect=fake):self.w.execute(task,lambda:None)
  with self.store.connect() as c:self.assertEqual(c.execute("select count(*) from research_tasks where kind='search'").fetchone()[0],1)
 def test_ai_cache_reuses_valid_spans(self):
  p,o=output();provider=lambda *args:{'output':copy.deepcopy(o),'usage':{'input_tokens':10,'output_tokens':10}}
  r=ai.call(self.store,self.c,'AZIENDE','one',copy.deepcopy(p),lambda:None,provider);self.assertEqual(r['status'],'completed')
  with patch('sales.agent6.ai.infer',side_effect=AssertionError()):r=ai.call(self.store,self.c,'AZIENDE','two',copy.deepcopy(p),lambda:None)
  self.assertTrue(r['cache_hit']);self.assertTrue(r['evidence'])
 def test_ai_stop_during_inference(self):
  p,o=output()
  def stop(*args):self.rs.stop(self.c['id']);return {'output':o,'usage':{}}
  with self.assertRaises(InterruptedError):ai.call(self.store,self.c,'AZIENDE','one',p,lambda:None,stop)
  with self.store.connect() as c:self.assertEqual(c.execute('select count(*) from agent6_cache').fetchone()[0],0)
 def test_ai_invalid_has_no_promotion(self):
  p,o=output();o['analyses'][0]['kind_ref']['end']=99999
  r=ai.call(self.store,self.c,'AZIENDE','one',p,lambda:None,lambda *args:{'output':o,'usage':{}});self.assertEqual(r['status'],'invalid');self.assertIsNone(r['output'])
 def test_run_loop_mock_stops(self):
  run_campaign(self.store,self.c,lambda:None,lambda x:None);self.assertEqual(self.rs.campaign(self.c['id'])['status'],'exhausted')
 def test_complete_research_pipeline_with_injected_services(self):
  # One source reaches VERIFIED through planner, search, document and resolver.
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
  f={**self.filters,'commercial_engines':['AZIENDE']};camp=self.rs.create(f)
  query={k:k for k in ('query','strategy','objective','hypothesis','missing','expected_source','success','stop_condition')};query['query']='alfa cerca freelance wordpress'
  page={'url':'https://alfa.example/careers','status':200,'checked_at':DATE,'html':'<title>Alfa Srl</title>'+''.join('<p>'+x+'</p>' for x in TEXT.splitlines())+'<p>Partita IVA: 12345678901</p><p>Sede legale: Via Roma 12, 35100 Padova (PD)</p><a href="mailto:info@alfa.example">info@alfa.example</a>'}
  def fake(payload,cfg,check):
   if payload['task']==schema.PLAN:
    value={'decision':'stop','reason':'No further distinct hypothesis','queries':[]} if payload['round'] else {'decision':'search','reason':'Specific need','queries':[query]}
   else:
    facts=[]
    for field,span in {'entity':'Alfa Srl','request':'We are looking for a freelance WordPress developer to build our complete website. Remote from Italy.','technical':'WordPress developer','contract':'freelance','geography':'Remote from Italy.'}.items():
     e=next((e for e in payload['evidence'] if span in e['text']),None)
     if e:
      i=e['text'].index(span);facts.append({'field':field,'ref':{'id':e['id'],'start':i,'end':i+len(span)}})
    if payload['task']==schema.SCREEN:facts=facts[:2]
    value={'analyses':[{'result_id':payload['result_ids'][0],'kind':'BUYER_DEMAND','kind_ref':facts[0]['ref'],'facts':facts,'hypothesis':'Full site project','missing':[]}]}
   return {'output':value,'usage':{'input_tokens':100,'output_tokens':100}}
  with patch('sales.agent6.ai.infer',side_effect=fake),patch('sales.agent6.coordinator.acquire',return_value=[{'url':page['url'],'title':'Alfa Srl','content':'We are looking for a freelance WordPress developer to build our complete website. Remote from Italy.'}]),patch('sales.agent6.coordinator.CompanyWeb.get',return_value=page):
   run_campaign(self.store,camp,lambda:None,lambda x:None)
  result=self.rs.campaign(camp['id']);self.assertEqual(result['qualified'],1);self.assertEqual(result['discovered'],1);self.assertEqual(result['useful_companies'],1)
  with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM prospects').fetchone()[0],0)
 def test_call_budget_stops_without_fallback_promotion(self):
  c=copy.deepcopy(self.c);c['filters']['commercial']['ai']['max_calls_per_campaign']=0
  p,o=output()
  with patch('sales.agent6.ai.infer',side_effect=AssertionError('must not call')):r=ai.call(self.store,c,'AZIENDE','test',p,lambda:None)
  self.assertEqual(r['status'],'budget_exhausted');self.assertIsNone(r['output'])
 def test_learning_between_campaigns_changes_strategy_priority(self):
  for key,good in [('broad',False),('targeted',True)]:
   for n in range(3):
    memory.event(self.store,self.c,'AZIENDE','query',key+str(n),{'query':key+str(n),'strategy':key,'results':1})
    body=evaluated() if good else evaluated(source(TEXT+'\nApplications closed'))
    memory.save_record(self.store,self.c,'AZIENDE',{**body,'strategy':key,'url':'https://alfa.example/'+key+str(n)})
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);next_campaign=self.rs.create(self.filters)
  h=memory.history(Store(self.store.path),'AZIENDE');values={x['strategy']:x['priority_adjustment'] for x in h['strategies']}
  self.assertLess(values['broad'],0);self.assertGreater(values['targeted'],0)
  self.assertEqual(memory.choose([{'strategy':'broad'},{'strategy':'targeted'}],h,0,25)['strategy'],'targeted')
  self.assertEqual(memory.choose([{'strategy':'new'},{'strategy':'targeted'}],h,3,25)['selection'],'exploration')
 def test_company_signals_merge_across_flows(self):
  b={**evaluated(),'kind':'COMPANY_SIGNAL','state':'RELEVANT'};first=memory.save_record(self.store,self.c,'NEWS',b)
  second=memory.save_record(self.store,self.c,'STARTUPS',{**b,'url':'https://alfa.example/news'})
  self.assertEqual(first,second);self.assertEqual(len(memory.shared_companies(self.store)),1)
 def test_disabled_agent_cannot_start(self):
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
  with self.assertRaises(ValueError):self.rs.create({**self.filters,'commercial':{'ai':{'enabled':False}}})
 def test_suppression_survives_new_campaign(self):
  b=evaluated();rid=memory.save_record(self.store,self.c,'AZIENDE',b);memory.feedback(self.store,rid,'not_interesting')
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);c=self.rs.create(self.filters)
  rid2=memory.save_record(self.store,c,'AGENCIES',b);self.assertEqual(api.dossier(self.store,rid2)['state'],'REJECTED')
 def test_actual_browser_schema_uses_new_contract(self):
  from sales.commercial.ai_tasks import schema_for,system_for
  self.assertEqual(schema_for(schema.PLAN),schema.wire_schema(schema.PLAN));self.assertIn('untrusted',system_for(schema.READ))
 def test_additive_migration_repeatable(self):
  before=self.c['filters'];self.store.init();self.assertEqual(self.rs.campaign(self.c['id'])['filters'],before)
 def test_pdf_not_queued(self):
  from sales.content_policy import ExcludedPDF
  with self.assertRaises(ExcludedPDF):self.w.enqueue('candidate','NEWS',{'url':'https://x.example/news.pdf'},'pdf')
 def test_equivalent_query_not_repeated(self):
  memory.event(self.store,self.c,'AZIENDE','query',memory.normalized('agenzia freelance wordpress Veneto'),{'query':'agenzia freelance wordpress Veneto'})
  self.assertTrue(memory.seen_query(self.store,'AZIENDE','Veneto wordpress freelance agenzia -filetype:pdf'))
  self.assertFalse(memory.seen_query(self.store,'AZIENDE','produttore ecommerce Veneto'))
 def test_crm_save_and_manual_outcome(self):
  rid=memory.save_record(self.store,self.c,'AZIENDE',{**evaluated(),'strategy':'crm-test'})
  first=api.save_contact(self.store,rid);pid=first['prospect_id']
  self.store.update_company(pid,{'stage':'won','contract_value':4000})
  second=api.save_contact(self.store,rid);self.assertEqual(second['prospect_id'],pid)
  h=memory.history(self.store,'AZIENDE');self.assertGreater(next(s for s in h['strategies'] if s['strategy']=='crm-test')['priority_adjustment'],3)
  from sales.research_api import annotate
  item=annotate(self.store,[self.store.company_detail(pid)])[0];self.assertEqual(item['qualification'],'agent6');self.assertEqual(item['stage'],'won')
 def test_records_after_restart(self):
  rid=memory.save_record(self.store,self.c,'NEWS',evaluated());self.assertEqual(api.dossier(Store(self.store.path),rid)['state'],'VERIFIED')

class Real31(unittest.TestCase):
 def test_frozen_cases(self):
  with gzip.open(Path(__file__).parent/'fixtures/agent6/campaign31.json.gz','rt') as f:cases={r['id']:r for r in json.load(f)}
  checks={929:'stale_request',950:'declared_budget_insufficient_for_target',1057:'stale_request',1059:'stale_request',1041:'completed_project'}
  for id,reason in checks.items():
   with self.subTest(id=id):
    r=cases[id];self.assertTrue(r['text']);self.assertIn(reason,q.objective(source(r['text'],title=r['title'],url=r['url']))['counterevidence'])
 def test_seven_named_regressions(self):
  with gzip.open(Path(__file__).parent/'fixtures/agent6/campaign31.json.gz','rt') as f:cases={r['id']:r for r in json.load(f)}
  for id,kind in [(929,'BUYER_DEMAND'),(950,'BUYER_DEMAND'),(1057,'EMPLOYEE_JOB'),(1040,'SUPPLIER_OFFER'),(1055,'EDITORIAL'),(1056,'SUPPLIER_OFFER')]:
   with self.subTest(id=id):
    r=cases[id];text=r['text'] or '\n'.join(r['snippets']) or r['title'];s=source(text,url=r['url'],title=r['title'],original=bool(r['text']))
    payload,o=output(s,kind,{'entity':text.splitlines()[0][:100]});o['analyses'][0]['facts']=[];a=schema.validate(o,payload)['analyses'][0];b=q.evaluate(s,a,payload['evidence'],'AZIENDE')
    self.assertNotIn(b['state'],('VERIFIED','POTENTIAL'))
  r=cases[1053];s=source(r['text'],url=r['url'],title=r['title']);request=next(x for x in q.core(r['text']).splitlines() if 'We are looking for an experienced freelance' in x)
  p,o=output(s,'AGENCY_PARTNERSHIP',{'entity':'AFM','request':request,'technical':'WordPress','contract':'freelance'})
  b=q.evaluate(s,schema.validate(o,p)['analyses'][0],p['evidence'],'AGENCIES')
  self.assertEqual(b['state'],'NEEDS_REVIEW');self.assertIn('geography',b['missing'])
 def test_request_stays_unknown_without_original(self):self.assertNotIn(q.evaluate(source(original=False),None,[],'LINKEDIN')['state'],('VERIFIED','POTENTIAL'))

if __name__=='__main__':unittest.main()
