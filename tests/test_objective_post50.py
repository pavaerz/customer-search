"""Replay observed C50 faults offline; fixture text is not a new opportunity."""
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
import test_ai_first as harness
from sales.agent6.query_pipeline import social_query_platform
from sales.agent6 import decision

SAVED=json.loads((Path(__file__).parent/'fixtures/ai_first/campaign50/replay.json').read_text())

class SocialDispatch(unittest.TestCase):
    def setUp(self):
        self.b=harness.IntegratedPath();self.b.setUp();self.addCleanup(self.b.tearDown)
        self.task={'id':900,'strategy':'SOCIAL','payload':{'round':0}}
        self.plan={k:copy.deepcopy(SAVED['plans'][0][k]) for k in ('reason','queries')}
        # Actual wire fields, not stored derived query-policy metadata.
        self.plan['queries']=[{k:q[k] for k in harness.query()} for q in self.plan['queries']]
        self.plan['decision']='search'

    def queued(self):
        with self.b.store.connect() as c:
            return [json.loads(r[0]) for r in c.execute("SELECT payload FROM research_tasks WHERE kind='search'")]

    def test_saved_two_platform_plan_dispatches_both_with_one_call_and_resume_deduplicates(self):
        with patch('sales.agent6.ai.infer',return_value={'output':self.plan,'usage':{}}) as model:
            self.b.w.planning(self.task,lambda:None)
            self.b.w.planning(self.task,lambda:None)
        self.assertEqual(model.call_count,1)
        self.assertEqual({social_query_platform(q['query']) for q in self.queued()},
                         {'linkedin.com','instagram.com'})
        self.assertEqual(len(self.queued()),2)
        with self.b.store.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM commercial_ai_executions WHERE attempt=1").fetchone()[0],1)
            self.assertEqual(c.execute("SELECT count(*) FROM discovery_operations").fetchone()[0],0)

    def test_missing_platform_not_invented_and_duplicate_platform_not_expanded(self):
        self.plan['queries']=[self.plan['queries'][0],{**self.plan['queries'][0],'query':'site:linkedin.com/posts Veneto cerchiamo freelance WordPress'}]
        with patch('sales.agent6.ai.infer',return_value={'output':self.plan,'usage':{}}):
            self.b.w.planning(self.task,lambda:None)
        self.assertEqual(len(self.queued()),1)

    def test_stop_plan_never_becomes_search_on_replay(self):
        self.plan['decision']='stop'
        with patch('sales.agent6.ai.infer',return_value={'output':self.plan,'usage':{}}):
            self.b.w.planning(self.task,lambda:None)
            self.b.w.planning(self.task,lambda:None)
        self.assertEqual(self.queued(),[])

    def test_stop_between_two_enqueues_recovers_saved_choices_only_on_resume(self):
        enqueue=self.b.w.enqueue;counter=[]
        def interrupted(*args):
            counter.append(args)
            if len(counter)==2:raise InterruptedError('Synthetic Stop')
            return enqueue(*args)
        with patch('sales.agent6.ai.infer',return_value={'output':self.plan,'usage':{}}),patch.object(self.b.w,'enqueue',side_effect=interrupted):
            with self.assertRaises(InterruptedError):self.b.w.planning(self.task,lambda:None)
        self.assertEqual(len(self.queued()),1)
        with patch('sales.agent6.ai.infer',side_effect=AssertionError('No new paid plan')):
            self.b.w.planning(self.task,lambda:None)
        self.assertEqual(len(self.queued()),2)


class SubjectGeography(unittest.TestCase):
    def example(self):
        b=next(r['body'] for r in SAVED['records'] if r['id']==1422)
        es=copy.deepcopy(SAVED['evidence'][0])
        p={'task':decision.TASK,'unit_id':es[0]['unit_id'],'evidence':es,
           'observed_at':b['checked_at'],'dates':b['dates'],'identity':b['identity'],
           'geography_allowed':True,'region':'Lombardia','links':[],
           'subject_scope_version':1,'allowed_regions':['Veneto','Lombardia']}
        o=copy.deepcopy(b['ai_decision'])
        o['subject_geography']={'status':'OUT_OF_TARGET','region':'','fact_indices':[1],
                                 'reason':'La prova colloca Paradise Plains in Kenya.'}
        return p,o

    def test_saved_kenya_followup_is_rejected_despite_page_lombardia(self):
        p,o=self.example()
        with self.assertRaisesRegex(ValueError,'out_of_target_followup'):
            decision.validate(o,p)
        o['decision']='NOT_INTERESTING';o['action']={'type':'STOP','query':'','question':'','link_id':''}
        validated,_=decision.validate(o,p)
        body=decision.materialize({'url':'https://editor.example/article','original':True},validated,p['evidence'],p,'NEWS')
        self.assertEqual(body['state'],'REJECTED')
        self.assertIsNone(body['region'])
        self.assertEqual(body['subject_geography']['facts'][0]['field'],'geography')

    def test_country_proof_cannot_be_relabelled_as_italian_region(self):
        p,o=self.example();o['subject_geography'].update(status='IN_TARGET',region='Lombardia')
        with self.assertRaisesRegex(ValueError,'subject_region_not_supported'):decision.validate(o,p)

    def test_missing_or_wrong_geography_reference_is_not_permission_to_promote(self):
        p,o=self.example();o['subject_geography']['fact_indices']=[0]
        with self.assertRaisesRegex(ValueError,'wrong_geography_fact'):decision.validate(o,p)
        p=harness.payload();p.update(subject_scope_version=1,allowed_regions=['Veneto'])
        o=harness.response(p);o['subject_geography'].update(status='UNKNOWN',region='',fact_indices=[])
        with self.assertRaisesRegex(ValueError,'subject_geography_unverified'):decision.validate(o,p)

    def test_remote_italy_is_distinct_from_employer_location(self):
        p=harness.payload(harness.TEXT+'\nLavoro da remoto dall’Italia, collaborazione freelance.')
        p.update(subject_scope_version=1,allowed_regions=['Veneto'],geography_allowed=False)
        o=harness.response(p)
        from sales.agent6.grounding import segments
        span=next(s for s in segments(p['evidence'][0]) if 'da remoto' in s['text'])
        o['facts'].append({'field':'geography','segment_id':span['segment_id']})
        o['subject_geography']={'status':'REMOTE_ITALY','region':'','fact_indices':[len(o['facts'])-1],
                                'reason':'Collaborazione svolgibile da Italia.'}
        decision.validate(o,p)

    def test_historical_response_remains_replayable_without_new_field(self):
        p,o=self.example();p.pop('subject_scope_version');p.pop('allowed_regions');o.pop('subject_geography')
        decision.validate(o,p)

class FollowupProjection(unittest.TestCase):
    def setUp(self):
        self.rows=copy.deepcopy(SAVED['records'])
        self.tasks=copy.deepcopy(SAVED['followup_tasks'])

    def result(self):
        from sales.agent6.followups import resolutions
        return resolutions(self.rows,self.tasks)

    def test_saved_chain_concludes_two_questions_without_certifying_site(self):
        result=self.result()
        self.assertEqual(set(result),{1425,1451})
        self.assertEqual(result[1425]['paths'],[[1425,1451,1452]])
        self.assertEqual(result[1425]['terminal_records'][0]['id'],1452)
        self.assertIn('non certifica',result[1425]['limit'])
        self.assertEqual(self.rows,SAVED['records'])

    def test_unrelated_campaign_subject_domain_or_missing_provenance_never_concludes(self):
        for mutation in ('campaign','subject','domain','provenance'):
            self.setUp()
            if mutation=='campaign':self.tasks[0]['campaign_id']=9999
            if mutation=='subject':self.tasks[0]['payload']['research_parent']['entity_name']='Altra impresa'
            if mutation=='domain':self.tasks[0]['payload']['research_parent']['url']='https://news.example/'
            if mutation=='provenance':self.tasks=[]
            self.assertNotIn(1425,self.result(),mutation)

    def test_incomplete_or_positive_terminal_keeps_questions_open(self):
        for change in ({'verification_hold':True},{'technical_error':'timeout'},
                       {'original':False},{'validation_status':'MODEL_INVALID'},
                       {'decision':'INTERESTING'},{'relationship':'EXPLICIT_REQUEST'}):
            self.setUp()
            next(r['body'] for r in self.rows if r['id']==1452).update(change)
            self.assertEqual(self.result(),{},change)

    def test_worklist_projection_preserves_history_and_manual_choices(self):
        from sales.agent6 import memory,api
        from sales.agent6.worklist import listing
        b=harness.IntegratedPath();b.setUp();self.addCleanup(b.tearDown)
        ids={}
        for r in self.rows:
            ids[r['id']]=memory.save_record(b.store,b.c,r['flow'],r['body'])
        for t in self.tasks:b.rs.enqueue(b.c['id'],'candidate',t['strategy'],t['payload'])
        with b.store.connect() as c:before='\n'.join(c.iterdump())
        result=listing(b.store,{'view':'resolved'})
        self.assertEqual(result['total'],2)
        self.assertEqual(result['counts']['review'],1) # Kenya remains unchanged historical evidence.
        self.assertTrue(all(r['saved_state']=='NEEDS_REVIEW' for r in result['items']))
        dossier=api.dossier(b.store,ids[1425])
        self.assertEqual(dossier['body']['decision'],'NEEDS_RESEARCH')
        self.assertEqual(dossier['research_resolution']['status'],'FOLLOWUP_CONCLUDED')
        with b.store.connect() as c:self.assertEqual('\n'.join(c.iterdump()),before)
        memory.feedback(b.store,ids[1425],'interesting','Manual review remains authoritative')
        self.assertEqual(listing(b.store,{'view':'resolved'})['total'],1)
        self.assertIn(ids[1425],[r['id'] for r in listing(b.store,{'view':'review'})['items']])
        memory.feedback(b.store,ids[1451],'contacted','Explicit manual state')
        self.assertEqual(listing(b.store,{'view':'contacted'})['total'],1)
        self.assertEqual(listing(b.store,{'view':'resolved'})['total'],0)

class WireAndPresentation(unittest.TestCase):
    def test_schema_prompt_and_token_estimate_version_together(self):
        from sales.commercial.ai_tasks import request_schema,system_for
        from sales.commercial.token_count import estimate
        from scripts.run_objective_validation_sol import SOL_CONFIG
        old=harness.payload();new={**old,'subject_scope_version':1,'allowed_regions':['Veneto']}
        self.assertNotIn('subject_geography',request_schema(old)['properties'])
        self.assertIn('subject_geography',request_schema(new)['required'])
        self.assertIn('SELECTED subject',system_for(new['task'],new))
        self.assertNotIn('SELECTED subject',system_for(old['task'],old))
        self.assertGreater(estimate(new,SOL_CONFIG)['tokens'],estimate(old,SOL_CONFIG)['tokens'])
        self.assertNotIn('subject_geography',request_schema(old)['properties'])

    def test_followup_ui_escapes_saved_reason_and_labels(self):
        import subprocess
        code=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/worklist.js','utf8');
const start=source.indexOf('function agentFollowupResolution('),end=source.indexOf('function agentResponseChannel(',start);
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const ctx={esc,link:(u,t)=>'<a href="'+esc(u)+'">'+esc(t)+'</a>'};
vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
const html=ctx.agentFollowupResolution({label:'Concluso',limit:'Non certifica il sito',terminal_records:[{id:2,url:'https://company.example',reason:'<img src=x onerror=alert(1)>'}]},1);
assert(!html.includes('<img'));assert(html.includes('&lt;img'));assert(html.includes('data-agent8-related="2"'));
assert(html.includes('valutazione iniziale resta conservata'));assert(!html.includes('Conferma contatto'));
'''
        subprocess.run(['node','-e',code],check=True,capture_output=True,text=True)

class FollowupBranches(unittest.TestCase):
    setUp=FollowupProjection.setUp
    result=FollowupProjection.result
    def test_second_unread_branch_prevents_closing_parent(self):
        branch=copy.deepcopy(self.tasks[0]);branch['payload']['url']='https://www.termepreistoriche.it/unread'
        branch['payload']['research_parent']['link_url']=branch['payload']['url'];self.tasks.append(branch)
        self.assertNotIn(1425,self.result())
        self.assertIn(1451,self.result())
