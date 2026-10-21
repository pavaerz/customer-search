"""Saved campaign 23 and explicitly synthetic adversarial contracts; no network."""
import copy,gzip,json,unittest
from pathlib import Path
from unittest.mock import patch
from sales.commercial.discovery import assess,linkedin_resolution
from sales.commercial.ai_schema import validate_output,fingerprint,unknown_output
from sales.commercial.ai_tasks import AUDIT,REQUEST,unknown_audit,request_context
from sales.commercial.ai import eligibility
from sales.commercial.presentation import lead_type
from sales.commercial.entity_scope import profile
from test_commercial_engines import CommercialTestCase


def load():
    with gzip.open(Path(__file__).parent/'fixtures/commercial3b6/campaign23.json.gz','rt') as f:return json.load(f)


class Historical36(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.x=load()
    def discovery(self,fragment):return next(r for r in self.x['commercial_discovery'] if fragment in r['url'])
    def test_seven_false_paths_stopped_before_download(self):
        for host,reason in [('legavolley.it','sports_mvp_not_software'),('dtoscientifica','cms_credit_not_technical_request'),('lavoro.it/torino','generic_job_listing'),('ecomsocialmindlab','software_supplier_not_customer'),('startupeuropa','funding_information_not_request'),('teamrapidtooling','editorial_not_company'),('uciesse','non_commercial_page')]:
            with self.subTest(host=host):
                r=self.discovery(host);out=assess(r['body'],r['engine']);self.assertEqual(r['decision'],'admit');self.assertEqual(out['decision'],'exclude');self.assertEqual(out['reason'],reason)
    def test_real_technical_requests_preserved(self):
        for host in ['apiceweb','parklab']:
            r=self.discovery(host);self.assertEqual(assess(r['body'],r['engine'])['decision'],'admit')
    def test_lavoro_html_has_no_single_owner(self):
        from sales.commercial.attribution import identity
        p=self.x['pages']['https://www.lavoro.it/torino/web-developer/'];self.assertTrue(profile(p)['multi_subject']);i=identity([p]);self.assertEqual(i['identity_status'],'unknown');self.assertEqual(i['contacts'],[])
    def test_pacer_blocked_index_only_resolution(self):
        r=self.discovery('641833497982403754');v=linkedin_resolution(r['body']);self.assertEqual(v['resolution_company'],'PACER');self.assertEqual(v['indexed_job']['contract_hint'],'external');self.assertFalse(v['indexed_job']['original_request_verified']);self.assertIsNone(v['indexed_job']['published_at'])
    def test_priorities_and_ai_gate_do_not_rewrite_history(self):
        for r in self.x['commercial_revisions']:
            b=copy.deepcopy(r['body']);before=copy.deepcopy(b);p=lead_type(b)
            if r['id']==915:self.assertEqual(p['type'],'DATA_QUALITY_REVIEW');self.assertFalse(eligibility(b)[0])
            if r['id']==908:self.assertEqual(p['type'],'PARTNERSHIP_PROSPECT')
            if r['id']==907:self.assertEqual(p['type'],'ACTIONABLE_LEAD')
            if r['id']==931:self.assertEqual(p['type'],'LOW_PRIORITY_TARGET')
            self.assertEqual(b,before)
    def test_partial_browser_never_proves_rebuild(self):
        for ident in (912,918):
            b=next(r['body'] for r in self.x['commercial_revisions'] if r['id']==ident)
            self.assertFalse(b['browser']['completed']);self.assertEqual(b['browser']['findings'],[]);self.assertNotEqual(lead_type(b)['type'],'REBUILD_PROSPECT')
    def test_undated_requests_remain_unknown_in_prompt(self):
        for ident in (907,908):
            b=next(r['body'] for r in self.x['commercial_revisions'] if r['id']==ident);c=request_context(b)
            self.assertFalse(c['current_open_request_allowed'])
    def test_no_blanket_mvp_or_unknown_company_filter(self):
        for engine,title,text in [('STARTUPS','Startup Alfa','Cerchiamo sviluppatore freelance per un MVP software.'),('WEBSITE_REBUILD','Alfa manifattura','Produciamo serramenti a Padova.')]:
            self.assertEqual(assess({'url':'https://alfa.example/','title':title,'content':text},engine)['decision'],'admit')
    def test_wordpress_credit_not_contaminate_menu_but_real_vacancy_passes(self):
        self.assertEqual(assess({'url':'https://alfa.example/','title':'Un nuovo sito targato WordPress','content':'Cerchiamo sviluppatori frontend freelance per collaborazioni tecniche.'},'AGENCIES')['decision'],'admit')


class Contracts36(unittest.TestCase):
    def setUp(self):
        self.result={'engine':'WEBSITE_REBUILD','company':'Alfa Srl','identity':{'identity_status':'verified'},'browser':{'completed':False},'evidence':[]}
        self.e=[{'id':'e1','candidate_id':'1','text':'Alfa Srl produce serramenti su misura.','text_hash':fingerprint('Alfa Srl produce serramenti su misura.'),'kind':'text','roles':['identity'],'original_verified':True}]
        self.o=unknown_audit({'candidate_id':'1'});self.o.update(actor='Alfa Srl',business_facts=[{'id':'e1','quote':self.e[0]['text']}])
    def validate(self):return validate_output(self.o,'1',self.e,self.result)
    def test_audit_without_commissioned_service_valid(self):self.assertEqual(self.validate()['business_facts'],self.o['business_facts'])
    def test_audit_cannot_accept_commercial_contract(self):
        self.o=unknown_output({'candidate_id':'1','task':REQUEST})
        with self.assertRaisesRegex(ValueError,'invalid_schema'):self.validate()
    def test_invented_quote_rejected(self):
        self.o['business_facts'][0]['quote']='Vuole comprare un sito'
        with self.assertRaisesRegex(ValueError,'invented_quote'):self.validate()
    def test_invented_actor_rejected(self):
        self.o['actor']='Beta Srl'
        with self.assertRaisesRegex(ValueError,'unsupported_actor'):self.validate()
    def test_unresolved_owner_not_certified(self):
        self.result['identity']['identity_status']='unknown'
        with self.assertRaisesRegex(ValueError,'unsupported_actor'):self.validate()
    def test_unknown_owner_empty_facts_valid(self):
        self.result['identity']['identity_status']='unknown';self.o=unknown_audit({'candidate_id':'1'});self.validate()
    def test_other_company_fact_rejected(self):
        t='Beta Srl conta 50 dipendenti';self.e[0].update(text=t,text_hash=fingerprint(t));self.o.update(actor=None,business_facts=[{'id':'e1','quote':t}])
        with self.assertRaisesRegex(ValueError,'contradictory_actor'):self.validate()
    def test_index_text_not_fact(self):
        self.e[0]['kind']='indexed_text'
        with self.assertRaisesRegex(ValueError,'indexed_source'):self.validate()
    def test_partial_audit_no_indicator(self):
        self.o['technical_indicators']=copy.deepcopy(self.o['business_facts'])
        with self.assertRaisesRegex(ValueError,'unvalidated_technical'):self.validate()
    def test_completed_measured_indicator_valid(self):
        t='Overflow misurato 150 px';self.e.append({'id':'e2','candidate_id':'1','text':t,'text_hash':fingerprint(t),'kind':'measurement'})
        self.result['browser']['completed']=True;self.result['evidence']=[{'kind':'measurement','quote':t}]
        self.o['technical_indicators']=[{'id':'e2','quote':t}];self.validate()
    def test_unknown_budget_cannot_disappear(self):
        self.o['unknowns'].remove('BUDGET')
        with self.assertRaisesRegex(ValueError,'unsupported_commercial'):self.validate()
    def test_partial_state_cannot_be_known(self):
        self.o['unknowns'].remove('TECHNICAL_CONDITION')
        with self.assertRaisesRegex(ValueError,'unvalidated_technical'):self.validate()
    def test_other_candidate_and_changed_hash_rejected(self):
        for change in [{'candidate_id':'2'},{'text_hash':'changed'}]:
            with self.subTest(change=change):
                old=copy.deepcopy(self.e);self.e[0].update(change)
                with self.assertRaisesRegex(ValueError,'invalid_evidence_attribution'):self.validate()
                self.e=old
    def test_request_schema_still_rejects_audit_shape(self):
        self.result['engine']='FREELANCE'
        with self.assertRaisesRegex(ValueError,'invalid_schema'):self.validate()


class Pipeline36(CommercialTestCase):
    def setUp(self):
        super().setUp();self.c['filters']['commercial_engines']=['FREELANCE','AGENCIES','STARTUPS','WEBSITE_REBUILD']
    def test_retry_exclusion_performs_no_read_or_ai(self):
        from sales.commercial.coordinator import Coordinator
        r=next(r for r in load()['commercial_discovery'] if 'legavolley' in r['url'])
        task={'id':123,'kind':'candidate','strategy':'STARTUPS','payload':{'url':r['url'],'discovery':r['body'],'commercial_engine':'STARTUPS'}}
        with patch('sales.commercial.coordinator.inspect',side_effect=AssertionError('no read')),patch('sales.commercial.ai.infer',side_effect=AssertionError('no AI')):
            Coordinator(self.store,self.c)._execute(task,lambda:None)
        self.assertEqual(self.repo.listing()['items'],[])
    def test_blocked_hint_never_enqueues_blocked_page(self):
        from sales.commercial.coordinator import Coordinator
        r=next(r for r in load()['commercial_discovery'] if '641833497982403754' in r['url'])
        w=Coordinator(self.store,self.c)
        with patch.object(w,'enqueue',return_value=True) as q:
            w.offer('STARTUPS',r['body'],{})
        self.assertEqual(q.call_count,1);self.assertEqual(q.call_args.args[0],'resolve');self.assertEqual(q.call_args.args[2]['resolution_company'],'PACER')
    def test_audit_shadow_uses_new_contract_and_preserves_decision(self):
        from sales.commercial.ai import analyze
        r=next(r for r in load()['commercial_revisions'] if r['id']==912);b=r['body'];before=copy.deepcopy(b)
        docs=[d for d in load()['documents'] if d['id'] in b['document_ids']]
        def provider(payload,cfg,check):
            self.assertEqual(payload['task'],AUDIT);self.assertNotIn('requested_service',payload['schema']['properties'])
            return {'output':unknown_output(payload),'usage':{'input_tokens':0,'output_tokens':0},'simulated':True}
        out=analyze(self.store,self.c,'WEBSITE_REBUILD','case912',b,docs,provider=provider,config={'enabled':True,'provider':'MOCK'})
        self.assertEqual(out['status'],'completed',out);self.assertEqual(out['mode'],'shadow');self.assertEqual(out['differences'],[]);self.assertEqual(b,before)


class Transport36(unittest.TestCase):
    def test_openai_schema_and_system_follow_audit_task_offline(self):
        from test_commercial_openai import OpenAIContract
        fixture=OpenAIContract();fixture.setUp();fixture.payload['task']=AUDIT
        _,connection,_=fixture.request()
        body=json.loads(connection.request.call_args.kwargs['body'])
        props=body['response_format']['json_schema']['schema']['properties']
        self.assertIn('business_facts',props);self.assertNotIn('requested_service',props)
        self.assertIn('WEBSITE_AUDIT_CONTEXT',body['messages'][0]['content'])
        self.assertEqual(body['max_completion_tokens'],1000);self.assertEqual(body['model'],'gpt-5.4-mini')
        self.assertTrue(body['response_format']['json_schema']['strict'])
    def test_standing_invitation_does_not_prove_current_commission(self):
        from sales.commercial.ai_schema import evidence_bundle
        result={'company':'Alfa','identity':{'identity_status':'verified'},'verification':{'currentness':'standing_invitation','checks':{'temporal_basis':True}}}
        text='Alfa: cerchiamo sviluppatori WordPress freelance per collaborazioni.'
        evidence=evidence_bundle('1',[{'id':'d','url':'https://alfa.example','text':text}],result=result)
        output=unknown_output({'candidate_id':'1'});ref={'id':evidence[0]['id'],'quote':text}
        output.update(actor='Alfa',requested_service='WordPress',commercial_intent='FREELANCE_OPPORTUNITY',direction='BUYER',relationship_type='CURRENT_OPEN_REQUEST',technical_relevance=True,supporting_evidence=[ref],temporal_evidence=[ref])
        with self.assertRaisesRegex(ValueError,'unsupported_currentness'):validate_output(output,'1',evidence,result)
