"""Offline Campaign 34 evidence. Generated counterexamples are labelled, not live outcomes."""
import copy,json,sqlite3,unittest
from pathlib import Path
from unittest.mock import patch
import test_agent6_campaign32 as support
import test_agent6 as original
from sales.agent6 import schema,ai,memory,qualification,commercial_policy,budget
from sales.commercial.coordinator import run_campaign
from sales.db import encode

SAVED=json.loads((Path(__file__).parent/'fixtures/agent6/campaign34/saved.json').read_text())

def call_fixture(ident):return copy.deepcopy(next(c for c in SAVED['calls'] if c['id']==ident))
def ref(e,text):return {'id':e['id'],'quote':text,'occurrence':0}
def analysis(e,kind,field,text):
 r=ref(e,text)
 return {'result_id':e['result_id'],'kind':kind,'kind_ref':r,'facts':[{'field':field,'ref':r}],'hypothesis':'Original required; unverified indexed evidence.','missing':['entity','technical','geography','contact','publication']}
def partial_fixture():
 """Real 487 input. Its invalid raw output was not saved; recreate one fault."""
 saved=call_fixture(487);e=saved['evidence'];p={'task':schema.SCREEN,'result_ids':[x['result_id'] for x in e],'evidence':e}
 a=[analysis(e[0],'DIRECTORY','request',e[0]['text']),analysis(e[1],'AGENCY_PARTNERSHIP','request','INVENTED CITATION FOR OFFLINE TEST'),analysis(e[2],'AGENCY_PARTNERSHIP','request',e[2]['text'])]
 return p,{'analyses':a}
def real_valid():
 saved=call_fixture(488);o=saved['output']
 for a in o['analyses']:a.pop('evidence_status',None)
 return {'task':schema.SCREEN,'result_ids':[a['result_id'] for a in o['analyses']],'evidence':saved['evidence']},o

def evaluate_real():
 p,o=real_valid();v,errors=schema.validate_response(o,p);assert not errors
 result={}
 for a in v['analyses']:
  e=next(e for e in p['evidence'] if e['result_id']==a['result_id']);item=next(x for x in SAVED['url_audit'] if x['url']==e['url'])
  source={'url':e['url'],'title':item['title'],'text':e['text'],'original':False,'checked_at':original.DATE}
  result[e['url']]=qualification.evaluate(source,a,p['evidence'],'AGENCIES')
 return result

class RecoveryContracts(unittest.TestCase):
 def test_one_bad_proposal_does_not_remove_two_good_ones(self):
  qs=[support.query(),support.query('x'*301),support.query('agenzia cerca freelance frontend')]
  v,errors=schema.validate_response({'decision':'search','reason':'Test','queries':qs},{'task':schema.PLAN})
  self.assertEqual(v['queries'],[qs[0],qs[2]]);self.assertEqual(errors[0]['code'],'query_too_long');self.assertEqual(errors[0]['query_index'],1)
 def test_plan_diagnostics_distinguish_causes(self):
  for q,code in [(support.query('x'*301),'query_too_long'),(support.query('abc'),'query_too_short'),({k:v for k,v in support.query().items() if k!='hypothesis'},'missing_required_fields'),({**support.query(),'objective':'   '},'missing_required_fields')]:
   with self.assertRaises(schema.ValidationError) as cm:schema.validate_response({'decision':'search','reason':'Test','queries':[q]},{'task':schema.PLAN})
   self.assertEqual(cm.exception.diagnostic['failures'][0]['code'],code)
 def test_empty_plan_requires_repair_not_fallback(self):
  with self.assertRaisesRegex(ValueError,'plan_no_valid_queries'):schema.validate_response({'decision':'search','reason':'No usable query','queries':[]},{'task':schema.PLAN})
 def test_three_results_two_preserved_and_e89_retained(self):
  p,o=partial_fixture();before=copy.deepcopy(o);v,errors=schema.validate_response(o,p)
  self.assertEqual(o,before);self.assertEqual(len(v['analyses']),2);self.assertEqual(errors[0]['code'],'quote_missing_or_occurrence_invalid')
  a=next(a for a in v['analyses'] if a['result_id']==p['result_ids'][2]);e=p['evidence'][2]
  b=qualification.evaluate({'url':e['url'],'text':e['text'],'original':False},a,p['evidence'],'AGENCIES')
  self.assertIn('e89.it',e['url']);self.assertTrue(commercial_policy.investigation(b,initial=True)['allowed']);self.assertNotIn(b['state'],('VERIFIED','POTENTIAL'))
 def test_source_cannot_be_borrowed_from_another_result(self):
  p,o=partial_fixture();o['analyses'][2]['facts'][0]['ref']=ref(p['evidence'][0],p['evidence'][0]['text'])
  v,errors=schema.validate_response(o,p);self.assertEqual(len(v['analyses']),1)
  self.assertEqual(next(e for e in errors if e.get('result_id')==p['result_ids'][2])['code'],'wrong_source')
 def test_duplicate_id_does_not_pick_a_winner(self):
  p,o=partial_fixture();o['analyses'][1]=copy.deepcopy(o['analyses'][0])
  v,errors=schema.validate_response(o,p);self.assertEqual(len(v['analyses']),1);self.assertIn('duplicate_result',[e['code'] for e in errors])
 def test_unknown_id_and_missing_result_do_not_poison_sibling(self):
  p,o=partial_fixture();o['analyses'][1]['result_id']='not-owned'
  v,errors=schema.validate_response(o,p);self.assertEqual(len(v['analyses']),2);self.assertIn('missing_result',[e['code'] for e in errors])
 def test_mirror_not_exclusive_employee_and_not_verified(self):
  b=evaluate_real()['https://www.mirror.it/jobs']
  self.assertEqual(b['model_kind'],'EMPLOYEE_JOB');self.assertEqual(b['kind'],'UNKNOWN');self.assertEqual(b['relationship']['status'],'mixed')
  self.assertIsNone(b['entity_name']);self.assertFalse(b['identity_verified']);self.assertEqual(b['freshness']['status'],'UNKNOWN');self.assertEqual(b['budget']['kind'],'UNKNOWN')
  self.assertNotEqual(b['state'],'REJECTED');self.assertTrue(commercial_policy.investigation(b,initial=True)['allowed'])
 def test_in_rete_rejected_for_observed_scope_not_employee(self):
  b=evaluate_real()['https://marketing.inretedigital.it/web-editor-social-media/']
  self.assertEqual(b['relationship']['status'],'external_mentioned');self.assertEqual(b['state'],'REJECTED');self.assertIn('Ambito',b['reason'])
  self.assertNotIn('EMPLOYEE_JOB',b['reason']);self.assertIsNone(b['entity_name']);self.assertTrue(b['scope_observation']['text_quote']);self.assertFalse(commercial_policy.investigation(b,initial=True)['allowed'])
 def test_generic_identities_removed_without_removing_request(self):
  p,o=real_valid();v,errors=schema.validate_response(o,p)
  self.assertFalse(errors)
  for a in v['analyses'][1:]:
   self.assertTrue(a['identity_issues']);self.assertFalse(any(f['field']=='entity' for f in a['facts']));self.assertTrue(any(f['field']=='request' for f in a['facts']))
  for text in ('Jobs','Web Editor','Careers','Web Design','Directory','Offerte di lavoro','Agenzia web'):
   self.assertFalse(schema.actor_span_valid(text,0,len(text)))
  self.assertTrue(schema.actor_span_valid('Alfa Srl',0,8))
 def test_hypothesis_alone_does_not_authorize_a_page(self):
  p,o=original.output(kind='EMPLOYEE_JOB',fields={'entity':'Alfa Srl'});o['analyses'][0]['hypothesis']='Possibly freelance'
  v,_=schema.validate_response(o,p);b=qualification.evaluate(original.source(),v['analyses'][0],p['evidence'],'AGENCIES')
  self.assertFalse(commercial_policy.investigation(b,initial=True)['allowed']);self.assertNotIn(b['state'],('VERIFIED','POTENTIAL'))
 def test_no_freelancers_is_not_positive_external_evidence(self):
  text='Alfa Srl\nWe need a developer. No freelancers. Permanent contract.'
  p,o=original.output(original.source(text),kind='EMPLOYEE_JOB',fields={'entity':'Alfa Srl','request':'No freelancers. Permanent contract.'})
  v,_=schema.validate_response(o,p);b=qualification.evaluate(original.source(text),v['analyses'][0],p['evidence'],'AGENCIES')
  self.assertFalse(b['semantic_issues']);self.assertEqual(b['state'],'REJECTED')

class RecoveryPersistence(unittest.TestCase):
 def setUp(self):
  self.base=support.Campaign32Fix();self.base.setUp();self.store=self.base.store;self.c=self.base.c;self.w=self.base.w;self.rs=self.base.rs
 def tearDown(self):self.base.tearDown()
 def test_invalid_plans_one_repair_each_and_no_queries(self):
  def fake(p,cfg,check):return {'output':{'decision':'search','reason':'Controlled invalid output','queries':[support.query('x'*301)]},'usage':{'input_tokens':1,'output_tokens':1}}
  with patch('sales.agent6.ai.infer',side_effect=fake) as infer,patch('sales.agent6.coordinator.acquire',side_effect=AssertionError('No invalid query may execute')):
   run_campaign(self.store,self.c,lambda:None,lambda _:None)
  self.assertEqual(infer.call_count,6)
  with self.store.connect() as c:
   self.assertEqual(c.execute("select count(*) from research_tasks where kind='search'").fetchone()[0],0)
   self.assertEqual(c.execute("select count(*) from commercial_engine_runs where state='blocked'").fetchone()[0],3)
   self.assertEqual(c.execute("select count(*) from agent6_memory where kind='plan_feedback'").fetchone()[0],6)
   self.assertTrue(all('query_too_long' in r[0] for r in c.execute('select error from commercial_engine_runs')))
 def test_plan_repair_reads_diagnostic_and_preserves_limits(self):
  seen=[]
  def fake(p,cfg,check):
   seen.append(p)
   return {'output':{'decision':'search','reason':'Controlled repair','queries':[support.query('x'*301) if not p['round'] else support.query()]},'usage':{'input_tokens':1,'output_tokens':1}}
  with patch('sales.agent6.ai.infer',side_effect=fake),patch('sales.agent6.coordinator.acquire',return_value=[]) as acquire:
   run_campaign(self.store,self.c,lambda:None,lambda _:None)
  self.assertEqual(len(seen),9);self.assertEqual(acquire.call_count,3) # Repaired plan, search, then an explicit stop on the already-seen query.
  self.assertTrue(all(p['memory']['plan_feedback'][0]['repair_scheduled'] for p in seen if p['round']))
  self.assertEqual(self.c['filters']['commercial']['ai']['max_calls_per_campaign'],20)
 def test_partial_call_persists_valid_output_and_failure_diagnostic(self):
  p,o=partial_fixture()
  r=ai.call(self.store,self.c,'AGENCIES','batch:partial',p,lambda:None,lambda *a:{'output':o,'usage':{'input_tokens':10,'output_tokens':10}})
  self.assertEqual(r['status'],'completed');self.assertTrue(r['partial']);self.assertEqual(len(r['output']['analyses']),2)
  self.assertNotIn('INVENTED CITATION',encode(r));self.assertEqual(r['validation_errors'][0]['result_id'],p['result_ids'][1])
  with self.store.connect() as c:self.assertEqual(c.execute('select count(*) from agent6_cache').fetchone()[0],0)
 def test_generic_identity_cleaning_survives_cache(self):
  p,o=real_valid();fake=lambda *a:{'output':o,'usage':{'input_tokens':10,'output_tokens':10}}
  first=ai.call(self.store,self.c,'AGENCIES','batch:cache',p,lambda:None,fake)
  second=ai.call(self.store,self.c,'AGENCIES','batch:cache2',p,lambda:None,lambda *a:self.fail('Cached valid response must not call'))
  self.assertTrue(second['cache_hit']);self.assertEqual(first['output'],second['output'])
 def test_contradictions_do_not_penalize_memory_after_sufficient_samples(self):
  for n in range(3):
   memory.event(self.store,self.c,'AGENCIES','query',str(n),{'query':'query'+str(n),'strategy':'mixed','results':1})
   for url,b in evaluate_real().items():
    if not b['semantic_issues']:continue
    memory.save_record(self.store,self.c,'AGENCIES',{**b,'url':url+'?sample='+str(n),'strategy':'mixed'})
  s=next(s for s in memory.history(self.store,'AGENCIES')['strategies'] if s['strategy']=='mixed')
  self.assertTrue(s['sample_sufficient']);self.assertEqual(s['priority_adjustment'],0);self.assertEqual(s['rejected'],0);self.assertEqual(s['semantic_conflicts'],6);self.assertEqual(s['scope_exclusions'],3)
 def test_explicit_verified_rejection_can_still_lower_priority(self):
  for n in range(3):
   memory.event(self.store,self.c,'AGENCIES','query',str(n),{'query':str(n),'strategy':'closed'})
   b=original.evaluated(original.source(original.TEXT+'\nApplications closed'))
   memory.save_record(self.store,self.c,'AGENCIES',{**b,'url':b['url']+str(n),'strategy':'closed'})
  s=next(s for s in memory.history(self.store,'AGENCIES')['strategies'] if s['strategy']=='closed');self.assertLess(s['priority_adjustment'],0);self.assertEqual(s['rejected'],3)
 def test_stop_discards_partial_outputs_and_cache(self):
  p,o=partial_fixture()
  def stop(*args):self.rs.stop(self.c['id']);return {'output':o,'usage':{}}
  with self.assertRaises(InterruptedError):ai.call(self.store,self.c,'AGENCIES','batch:stop',p,lambda:None,stop)
  with self.store.connect() as c:self.assertEqual(c.execute('select count(*) from agent6_cache').fetchone()[0],0)
 def test_resume_does_not_refund_partial_screen(self):
  p,o=partial_fixture()
  for n in range(2):ai.call(self.store,self.c,'AGENCIES','batch:'+str(n),p,lambda:None,lambda *a:{'output':o,'usage':{}})
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);resumed=self.rs.resume(self.c['id'])
  self.assertEqual(budget.remaining(self.store,resumed,'AGENCIES',resumed['filters']['commercial']['ai'],'screen'),6) # Two calls remain spent; idle stage capacity is reusable.
  with self.store.connect() as c:self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok')

if __name__=='__main__':unittest.main()
