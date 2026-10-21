"""Post-32 regressions. Real saved evidence + clearly synthetic service doubles."""
import copy,json,tempfile,unittest,sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from sales.db import Store,encode
from sales.research_store import ResearchStore
from sales.agent6 import schema,ai,budget,memory,commercial_policy as policy
from sales.agent6.coordinator import AgentCoordinator
from sales.commercial.ai import _reserve
from test_agent6 import source,output,evaluated,TEXT,DATE

FROZEN=json.loads((Path(__file__).parent/'fixtures/agent6/campaign32/saved.json').read_text())
def query(text='azienda cerca freelance WordPress Italia'):
 return {'query':text,'strategy':'explicit collaboration','objective':'Find an identified buyer seeking a full website','hypothesis':'A current external development request can be verified on the original','missing':'Identity, original request and current contract scope','expected_source':'official careers or request page','success':'Current external WordPress request attributed to buyer','stop_condition':'No named buyer or only employee positions'}
def plan_payload(flow,round=0):return {'task':schema.PLAN,'flow':flow,'round':round,'memory':{}}
def provider(payload,cfg,check):
 check()
 if payload['task']==schema.PLAN:return {'output':{'decision':'search','reason':'Test-only explicit collaboration','queries':[query()]},'usage':{'input_tokens':20,'output_tokens':30}}
 analyses=[]
 for rid in payload['result_ids']:
  es=[e for e in payload['evidence'] if e['result_id']==rid];facts=[]
  spans={'entity':'Alfa Srl','request':'We are looking for a freelance WordPress developer to build our complete website. Remote from Italy.'}
  if payload['task']!=schema.SCREEN:spans.update(technical='WordPress developer',contract='freelance',geography='Remote from Italy.')
  for field,span in spans.items():
   e=next((e for e in es if span in e['text']),None)
   if e:
    start=e['text'].index(span);facts.append({'field':field,'ref':{'id':e['id'],'start':start,'end':start+len(span)}})
  analyses.append({'result_id':rid,'kind':'BUYER_DEMAND' if facts else 'UNKNOWN','kind_ref':facts[0]['ref'] if facts else None,'facts':facts,'hypothesis':'Synthetic test request','missing':[]})
 return {'output':{'analyses':analyses},'usage':{'input_tokens':100,'output_tokens':100}}

def screen_payload(tag='a'):
 src=source(original=False,url='https://alfa.example/'+tag)
 return {'task':schema.SCREEN,'result_ids':['r1'],'evidence':schema.bundle([{'id':'r1',**src}])}

class Campaign32Fix(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'offline.db');self.store.init();self.rs=ResearchStore(self.store)
  self.filters=copy.deepcopy(FROZEN['filters']);self.filters['commercial']['ai']['provider']='MOCK'
  self.filters.pop('search_version',None);self.filters.pop('demand_version',None)
  from sales.agent6.api import preview
  self.filters['deep_plan_token']=preview(self.store,self.filters)['approval_token'];self.filters['deep_authorized']=True
  self.c=self.rs.create(self.filters);self.w=AgentCoordinator(self.store,self.c);self.w.initialize();self.cfg=self.c['filters']['commercial']['ai']
 def tearDown(self):self.tmp.cleanup()
 def call(self,flow,key,p):return ai.call(self.store,self.c,flow,key,p,lambda:None,provider)
 def test_reproduce_old_collision_then_three_new_planners(self):
  # Reproduce original reservation contract in an independent temporary campaign.
  for index,flow in enumerate(self.filters['commercial_engines']):
   ident,error=_reserve(self.store,self.c,flow,'plan:0',self.cfg,'old'+flow,schema.PLAN,0,20)
   self.assertEqual(error,None if index==0 else 'candidate_budget')
   if ident:
    with self.store.connect() as c:c.execute("UPDATE commercial_ai_executions SET status='completed' WHERE id=?",(ident,))
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.create(self.filters)
  for flow in self.filters['commercial_engines']:self.assertEqual(self.call(flow,'plan:0',plan_payload(flow))['status'],'completed')
  with self.store.connect() as c:
   keys=[r[0] for r in c.execute('select candidate_id from commercial_ai_executions where campaign_id=? and attempt=1',(self.c['id'],))]
  self.assertEqual(len(set(keys)),3)
 def test_three_flows_enqueue_search_with_same_limits(self):
  self.w.tick()
  with self.store.connect() as c:tasks=[{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute("select * from research_tasks where kind='agent_plan'")]
  with patch('sales.agent6.ai.infer',side_effect=provider):
   for t in tasks:self.w.execute(t,lambda:None)
  with self.store.connect() as c:self.assertEqual(set(r[0] for r in c.execute("select strategy from research_tasks where kind='search'")),{'AZIENDE','AGENCIES','STARTUPS'})
 def test_stage_caps_fit_shared_and_flow_budgets(self):
  caps=[budget.allocation(self.c,self.cfg,f) for f in self.filters['commercial_engines']]
  self.assertEqual(caps,[{'plan':1,'screen':2,'verify':3,'replan':1},{'plan':1,'screen':2,'verify':3,'replan':1},{'plan':1,'screen':2,'verify':2,'replan':1}])
  self.assertEqual(sum(sum(x.values()) for x in caps),20)
  self.assertTrue(all(sum(x.values())<=8 for x in caps))
 def test_screen_can_reuse_idle_capacity_and_other_flows_still_start(self):
  self.call('AZIENDE','plan:0',plan_payload('AZIENDE'))
  for n in range(2):self.assertEqual(self.call('AZIENDE','batch:'+str(n),screen_payload(str(n)))['status'],'completed')
  self.assertEqual(self.call('AZIENDE','batch:extra',screen_payload('extra'))['status'],'completed')
  p,o=output();self.assertEqual(self.call('AZIENDE','page:alfa',p)['status'],'completed')
  for flow in ('AGENCIES','STARTUPS'):self.assertEqual(self.call(flow,'plan:0',plan_payload(flow))['status'],'completed')
  self.assertEqual(self.call('AZIENDE','plan:1',plan_payload('AZIENDE',1))['status'],'completed')
 def test_candidate_limit_across_flows_but_not_plans(self):
  p,_=output();self.assertEqual(self.call('AZIENDE','page:alfa',p)['status'],'completed')
  p['flow']='AGENCIES' # different context prevents a free cache hit
  self.assertEqual(self.call('AGENCIES','page:alfa',p)['error'],'candidate_budget')
  self.assertEqual(self.call('AGENCIES','plan:0',plan_payload('AGENCIES'))['status'],'completed')
 def test_resume_keeps_consumption(self):
  self.call('AZIENDE','plan:0',plan_payload('AZIENDE'))
  for n in range(2):self.call('AZIENDE','batch:'+str(n),screen_payload(str(n)))
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.resume(self.c['id'])
  self.assertEqual(self.call('AZIENDE','batch:extra',screen_payload('extra'))['status'],'completed')
  self.assertEqual(self.call('AZIENDE','page:alfa',output()[0])['status'],'completed')
 def test_low_budget_never_raises_limits(self):
  for total in range(10):
   cfg={**self.cfg,'max_calls_per_campaign':total,'max_calls_per_engine':2}
   caps=[budget.allocation(self.c,cfg,f) for f in self.filters['commercial_engines']]
   self.assertLessEqual(sum(sum(x.values()) for x in caps),total);self.assertTrue(all(sum(x.values())<=2 for x in caps))
 def test_cost_limit_is_part_of_fair_envelope(self):
  cfg={**self.cfg,'provider':'REMOTE','max_estimated_cost':.021288}
  self.assertLessEqual(sum(sum(budget.allocation(self.c,cfg,f).values()) for f in self.filters['commercial_engines']),2)
 def test_atomic_reservations_do_not_overspend(self):
  cfg={**self.cfg,'max_concurrent_requests':4}
  def reserve(n):return budget.reserve(self.store,self.c,'AZIENDE','batch:'+str(n),screen_payload(str(n)),cfg,'cache'+str(n),0,100)
  with ThreadPoolExecutor(max_workers=4) as pool:result=list(pool.map(reserve,range(8)))
  self.assertEqual(sum(x[0] is not None for x in result),4) # Configured concurrent maximum; stage quota is no longer a hard limit.
 def test_plan32_portfolio_blocked_before_search(self):
  old=FROZEN['plan']['chosen'];task={'id':900,'kind':'search','strategy':'AZIENDE','payload':old}
  with patch('sales.agent6.coordinator.acquire',side_effect=AssertionError('No Serper')):self.w._execute(task,lambda:None)
  with self.store.connect() as c:self.assertEqual(c.execute("select count(*) from agent6_memory where kind='query_policy'").fetchone()[0],1)
 def test_rejected_plan_can_replan_without_serper(self):
  self.w.tick()
  task={'id':901,'kind':'agent_plan','strategy':'AZIENDE','payload':{'round':0}}
  old={'decision':'search','reason':'Replay old portfolio','queries':[ {k:FROZEN['plan']['chosen'][k] for k in query()} ]}
  with patch('sales.agent6.ai.infer',return_value={'output':old,'usage':{}}):self.w.planning(task,lambda:None)
  with self.store.connect() as c:self.assertEqual(c.execute("select count(*) from research_tasks where kind='search'").fetchone()[0],0)
  self.assertTrue(memory.history(self.store,'AZIENDE')['plan_feedback'])
 def test_historical32_memory_is_visible_without_rewriting(self):
  with self.store.connect() as c:
   for m in FROZEN['memory']:c.execute('insert into agent6_memory(campaign_id,flow,kind,key,body,created_at) values (?,?,?,?,?,?)',(32,m['flow'],m['kind'],m['key'],encode(m['body']),m['created_at']))
  seen=[]
  def capture(p,*args):seen.append(copy.deepcopy(p));return provider(p,*args)
  with patch('sales.agent6.ai.infer',side_effect=capture):self.w.planning({'id':999,'strategy':'AZIENDE','payload':{'round':0}},lambda:None)
  self.assertTrue(any('portfolio' in q['query'] for q in seen[0]['memory']['recent_queries']))
  values=memory.history(self.store,'AZIENDE')['strategies'];s=next(s for s in values if s['strategy']=='official/agency portfolio discovery')
  self.assertEqual(s['queries'],2);self.assertEqual(s['priority_adjustment'],0);self.assertFalse(s['sample_sufficient'])
 def test_invalid_diagnostics_do_not_record_output_prose(self):
  p,o=output();o['analyses'][0]['facts'][0]['ref']['id']='SECRET_FAKE_NOT_A_REAL_KEY'
  r=ai.call(self.store,self.c,'AZIENDE','page:bad',p,lambda:None,lambda *a:{'output':o,'usage':{}})
  self.assertEqual(r['diagnostic']['failures'][0]['cause'],'unknown_evidence_id');self.assertNotIn('SECRET_FAKE',encode(r));self.assertIsNone(r['output'])
 def test_stop_before_dispatch_and_after_answer(self):
  self.rs.stop(self.c['id'])
  with self.assertRaises(InterruptedError):self.call('AZIENDE','plan:0',plan_payload('AZIENDE'))
 def test_no_repeat_investigation_without_new_evidence(self):
  b=evaluated(ident=False);b['missing']=['entity'];parent={'depth':0,'strategy':'specific'}
  self.w.investigate('AZIENDE',b,parent);self.w.investigate('AZIENDE',b,parent)
  with self.store.connect() as c:self.assertEqual(c.execute("select count(*) from research_tasks where kind='search'").fetchone()[0],1)
 def test_institutional_followup_never_searches(self):
  b={**evaluated(ident=False),'entity_name':'Unioncamere Piemon','kind':'UNKNOWN'}
  self.w.investigate('AZIENDE',b,{'depth':0})
  with self.store.connect() as c:self.assertEqual(c.execute('select count(*) from research_tasks').fetchone()[0],0)
 def test_original_page_runs_after_screen_envelope_exhausted(self):
  for n in range(2):self.call('AZIENDE','batch:'+str(n),screen_payload(str(n)))
  page={'url':'https://alfa.example/careers','status':200,'checked_at':DATE,'html':'<title>Alfa Srl</title>'+''.join('<p>'+x+'</p>' for x in TEXT.splitlines())+'<p>Partita IVA: 12345678901</p><p>Sede legale: Via Roma 12, 35100 Padova (PD)</p>'}
  with patch('sales.agent6.coordinator.CompanyWeb.get',return_value=page),patch('sales.agent6.ai.infer',side_effect=provider):self.w.reading({'payload':{'url':page['url'],'query':'test','strategy':'specific'},'strategy':'AZIENDE'},lambda:None)
  with self.store.connect() as c:
   r=c.execute("select body from commercial_ai_executions where json_extract(body,'$.stage')='verify'").fetchone()
   self.assertEqual(json.loads(r[0])['status'],'completed');self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok')

 def test_expired_other_campaign_is_not_rewritten(self):
  ident,_=_reserve(self.store,self.c,'AZIENDE','old',self.cfg,'oldcache',schema.PLAN,0,1)
  with self.store.connect() as c:c.execute('update commercial_ai_executions set expires_at=0 where id=?',(ident,))
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.create(self.filters)
  self.assertEqual(self.call('AZIENDE','plan:0',plan_payload('AZIENDE'))['status'],'completed')
  with self.store.connect() as c:self.assertEqual(c.execute('select status from commercial_ai_executions where id=?',(ident,)).fetchone()[0],'running')
 def test_duplicate_original_does_not_consume_another_inference(self):
  page={'url':'https://alfa.example/one','status':200,'checked_at':DATE,'html':'<title>Alfa Srl</title><p>'+TEXT+'</p>'}
  with patch('sales.agent6.coordinator.CompanyWeb.get',return_value=page),patch('sales.agent6.ai.infer',side_effect=provider):
   self.w.reading({'payload':{'url':page['url']},'strategy':'AZIENDE'},lambda:None)
   page['url']='https://alfa.example/two'
   self.w.reading({'payload':{'url':page['url']},'strategy':'AZIENDE'},lambda:None)
  with self.store.connect() as c:self.assertEqual(c.execute('select count(*) from commercial_ai_executions where attempt=1').fetchone()[0],1)

 def test_preflight_rejections_change_priority_only_after_sufficient_sample(self):
  for n in range(3):
   memory.event(self.store,self.c,'AZIENDE','query','noisy'+str(n),{'query':'noisy'+str(n),'strategy':'noisy','policy_rejections':[{'domain':'example.test','reason':'institutional_without_commercial_signal'}]})
  h=memory.history(self.store,'AZIENDE');s=next(s for s in h['strategies'] if s['strategy']=='noisy')
  self.assertTrue(s['sample_sufficient']);self.assertLess(s['priority_adjustment'],0)
  self.assertFalse(memory.seen_query(self.store,'AZIENDE','a genuinely new search'))

class Policy32(unittest.TestCase):
 def test_explicit_freelance_and_agency_partnership(self):
  for text in ('cerchiamo freelance WordPress Italia','agenzie collabora con noi frontend','startup looking for contractor web developer'):
   self.assertTrue(policy.assess_query(query(text),'AGENCIES')['allowed'])
 def test_campaign33_queries_before_dispatch(self):
  rejected=('startup "freelance" OR "agenzia" frontend OR wordpress Veneto', 'site:.it agenzia web "collaboratori esterni" WordPress frontend ecommerce', '(cerchiamo freelance WordPress')
  for text in rejected:self.assertFalse(policy.assess_query(query(text),'STARTUPS')['allowed'],text)
  allowed=('site:.it studio web "partita iva" WordPress frontend agenzia "lavora con noi"', 'startup cerca agenzia sviluppo sito web', 'cerchiamo freelance (WordPress OR frontend) Italia', 'agenzia "collabora con noi" frontend')
  for text in allowed:self.assertTrue(policy.assess_query(query(text),'AGENCIES')['allowed'],text)
 def test_all_saved_campaign33_executed_queries_rejected(self):
  saved=json.loads((Path(__file__).parent/'fixtures/agent6/campaign33/queries.json').read_text())
  self.assertEqual({q['flow'] for q in saved},{'AZIENDE','AGENCIES','STARTUPS'})
  for q in saved:self.assertFalse(policy.assess_query(q,q['flow'])['allowed'],q['query'])
 def test_queries_without_purchase_direction(self):
  for text in ('portfolio siti web Veneto','agenzia realizzazione siti web','careers WordPress developer Italia','progetti europei ecommerce','agenzia siti web -freelance -cerchiamo'):
   self.assertFalse(policy.assess_query(query(text),'AZIENDE')['allowed'],text)
 def test_new_signal_strategy_remains_hypothesis(self):
  q=query('nuovi prodotti ecommerce produttori Veneto');q['hypothesis']='Verify a digital gap against the official catalogue before proposing a project'
  r=policy.assess_query(q,'AZIENDE');self.assertTrue(r['allowed']);self.assertEqual(r['intent'],'business_signal_hypothesis')
 def test_campaign32_plan_classification(self):
  results=[policy.assess_query(q,'AZIENDE') for q in FROZEN['plan']['queries']]
  # The ERP/CRM/digital-transformation OR branches are topics, not requests.
  self.assertTrue(all(not r['allowed'] for r in results))
 def test_screen_schema_forbids_publication(self):
  p,o=output(source(original=False));p['task']=schema.SCREEN;o['analyses'][0]['facts']=o['analyses'][0]['facts'][:2]
  with self.assertRaisesRegex(ValueError,'invalid_enum'):schema.validate(o,p)
 def test_truncated_actor_and_title_fragments(self):
  for text,name in [('Unioncamere Piemonte','Unioncamere Piemon'),('Mind Design Web Agency | Studio','Mind Design Web Agency |'),('Area progetti e sviluppo del territorio','Area progetti e sviluppo del')]:
   p,o=output(source(text),fields={'entity':name})
   with self.assertRaisesRegex(ValueError,'unsupported_actor'):schema.validate(o,p)
 def test_complete_actor_still_accepted(self):
  p,o=output(source('Unioncamere Piemonte\nPagina contatti'),fields={'entity':'Unioncamere Piemonte'});schema.validate(o,p)
 def test_cross_result_diagnostic_preserves_security(self):
  p,o=output();p['evidence'][0]['result_id']='other'
  with self.assertRaises(schema.ValidationError) as cm:schema.validate(o,p)
  self.assertEqual(cm.exception.diagnostic['cause'],'cross_result_reference')
 def test_every_result_requires_an_analysis(self):
  p,o=output();p['result_ids'].append('other')
  with self.assertRaisesRegex(ValueError,'missing_result'):schema.validate(o,p)
 def test_short_ids_keep_hash_and_offset_checks(self):
  p,o=output();self.assertEqual(p['evidence'][0]['id'],'e1');p['evidence'][0]['text']='mutated'
  with self.assertRaisesRegex(ValueError,'wrong_source'):schema.validate(o,p)
 def test_bad_one_of_two_results_never_cross_attributes(self):
  p,o=output();p['result_ids'].append('2');bad=copy.deepcopy(o['analyses'][0]);bad['result_id']='2';o['analyses'].append(bad)
  with self.assertRaisesRegex(ValueError,'wrong_source'):schema.validate(o,p)
 def test_explicit_snippet_can_get_original_before_identity_resolution(self):
  b={'state':'DISCOVERED','kind':'BUYER_DEMAND','entity_name':None,'facts':[{'field':'request','quote':'We are looking for a freelance WordPress developer'}]}
  self.assertTrue(policy.investigation(b,initial=True)['allowed'])
  self.assertFalse(policy.investigation(b)['allowed'])
 def literal(self,p,o):
  o=copy.deepcopy(o)
  for a in o['analyses']:
   for ref in ([a['kind_ref']] if a['kind_ref'] else [])+[f['ref'] for f in a['facts']]:
    if 'quote' in ref:continue
    e=next(e for e in p['evidence'] if e['id']==ref['id']);quote=e['text'][ref['start']:ref['end']]
    ref.clear();ref.update(id=e['id'],quote=quote,occurrence=0)
  return o
 def test_wire_uses_canonical_segments_not_model_copied_quotes(self):
  from sales.commercial.ai_tasks import schema_for
  wire=schema_for(schema.SCREEN);ref=wire['properties']['analyses']['items']['properties']['facts']['items']['properties']['ref']
  self.assertEqual(set(ref['properties']),{'segment_id'})
  p,o=output();result=schema.validate(self.literal(p,o),p)
  self.assertEqual(result['analyses'][0]['facts'][0]['ref'],o['analyses'][0]['facts'][0]['ref'])
 def test_literal_wrong_source_still_rejected(self):
  p,o=output();o=self.literal(p,o);o['analyses'][0]['facts'][0]['ref']['id']='wrong'
  with self.assertRaisesRegex(ValueError,'wrong_source'):schema.validate(o,p)
 def test_literal_quotes_never_fuzzily_repaired(self):
  p,o=output();o=self.literal(p,o);o['analyses'][0]['facts'][0]['ref']['quote']='ALFA SRL'
  with self.assertRaisesRegex(ValueError,'quote_missing'):schema.validate(o,p)
 def test_literal_truncated_name_still_rejected(self):
  p,o=output(source('Unioncamere Piemonte'),fields={'entity':'Unioncamere Piemon'});o=self.literal(p,o)
  with self.assertRaisesRegex(ValueError,'unsupported_actor'):schema.validate(o,p)
 def test_repeated_quote_requires_valid_occurrence(self):
  p,o=output(source('Alfa Srl and Alfa Srl'),fields={'entity':'Alfa Srl'});o=self.literal(p,o)
  o['analyses'][0]['facts'][0]['ref']['occurrence']=1
  result=schema.validate(o,p);self.assertEqual(result['analyses'][0]['facts'][0]['ref']['start'],13)
  p,o=output();o=self.literal(p,o);o['analyses'][0]['facts'][0]['ref']['occurrence']=-1
  with self.assertRaisesRegex(ValueError,'occurrence_invalid'):schema.validate(o,p)

 def test_persisted_invalid_outputs_cannot_be_reconstructed(self):
  self.assertEqual(len(FROZEN['valid_outputs']),5);self.assertFalse(any(o['id'] in (458,459,462) for o in FROZEN['valid_outputs']))

if __name__=='__main__':unittest.main()
