"""Synthetic fault injection around real coordinator/storage, fully offline."""
import copy
import json
import os
import unittest
from unittest.mock import patch

import test_agent6 as original
import test_agent6_campaign32 as support
from test_agent7 import response,SAVED
from sales.agent6 import ai,schema,memory,diagnostics
from sales.agent6.coordinator import AgentCoordinator
from sales.commercial.ai_provider import ProviderError
from sales.commercial.coordinator import run_campaign
from sales.db import encode


class Recovery(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp()
        self.store,self.c,self.rs,self.w=self.base.store,self.base.c,self.base.rs,self.base.w
        self.network=patch('socket.create_connection',side_effect=AssertionError('Offline: no network'));self.network.start()
    def tearDown(self):self.network.stop();self.base.tearDown()
    def tasks(self,kind):
        with self.store.connect() as c:return [{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute('SELECT * FROM research_tasks WHERE kind=? ORDER BY id',(kind,))]
    def ledger(self):
        with self.store.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM commercial_ai_executions WHERE attempt=1')]
    def config(self,**kw):
        self.c['filters']['commercial']['ai'].update(kw)
        with self.store.connect() as c:c.execute('UPDATE campaigns SET filters=? WHERE id=?',(encode(self.c['filters']),self.c['id']))
    def page(self):
        return {'url':'https://alfa.example/careers','status':200,'checked_at':original.DATE,
            'html':'<title>Alfa Srl</title>'+''.join('<p>'+line+'</p>' for line in original.TEXT.splitlines())+
            '<p>Partita IVA: 12345678901</p><p>Sede legale: Via Roma 12, 35100 Padova (PD)</p><a href="mailto:info@alfa.example">Contatti</a>'}
    def enqueue_original(self):
        self.w.enqueue('candidate','AGENCIES',{'url':self.page()['url'],'query':'cerchiamo freelance WordPress','strategy':'synthetic'},'test-original')
        return self.rs.claim(self.c['id'],self.c['generation'])
    def stop_resume(self):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.resume(self.c['id'])
        self.w=AgentCoordinator(self.store,self.c);self.w.initialize()

    def test_partial_screen_retries_only_invalid_item_in_singleton(self):
        items=[{'url':f'https://agency{i}.example/jobs','title':'Alfa Srl','content':'WordPress project for an external development partner.'} for i in range(2)]
        with patch('sales.agent6.coordinator.acquire',return_value=items):
            self.w._execute({'id':999,'kind':'search','strategy':'AGENCIES','payload':support.query()},lambda:None)
        seen=[]
        def provider(p,cfg,check):
            seen.append(copy.deepcopy(p));out=response(p)['output']
            if not p.get('repair'):out['analyses'][0]['kind_ref']={'segment_id':'invented'};out['analyses'][0]['kind']='BUYER_DEMAND'
            return {'output':out,'usage':{}}
        with patch('sales.agent6.ai.infer',side_effect=provider):
            first=self.tasks('agent_screen')[0];self.w.execute(first,lambda:None)
            repairs=[t for t in self.tasks('agent_screen') if t['payload'].get('repair_attempt')]
            self.assertEqual(len(repairs),1);self.assertEqual(len(repairs[0]['payload']['batch']),1)
            self.w.execute(repairs[0],lambda:None)
        self.assertEqual([len(p['result_ids']) for p in seen],[2,1])
        self.assertEqual(seen[1]['evidence'][0]['url'],items[0]['url'])
        self.assertEqual(len(self.ledger()),2)
        self.assertEqual(len(self.tasks('agent_screen')),2)

    def test_repair_is_bounded_when_every_singleton_still_invalid(self):
        items=[{'url':'https://agency.example/jobs','title':'Alfa Srl','content':'WordPress project development partner.'}]
        with patch('sales.agent6.coordinator.acquire',return_value=items):self.w._execute({'id':999,'kind':'search','strategy':'AGENCIES','payload':support.query()},lambda:None)
        with patch('sales.agent6.ai.infer',return_value={'output':{},'usage':{}}):
            self.w.execute(self.tasks('agent_screen')[0],lambda:None)
            self.w.execute(self.tasks('agent_screen')[1],lambda:None)
        self.assertEqual(len(self.tasks('agent_screen')),2)
        with self.store.connect() as c:
            b=json.loads(c.execute('SELECT body FROM agent6_records').fetchone()[0])
        self.assertEqual(b['recovery_action'],'repair_exhausted');self.assertEqual(b['state'],'UNVERIFIABLE')

    def test_completed_original_inference_replays_after_stop_without_fetch_or_charge(self):
        task=self.enqueue_original();real_event=memory.event
        def stop_before_post_model_event(store,campaign,flow,kind,key,body):
            if kind=='model' and body['task']==schema.READ:
                self.rs.stop(self.c['id']);raise InterruptedError('Injected Stop after paid result persisted')
            return real_event(store,campaign,flow,kind,key,body)
        with patch('sales.agent6.coordinator.CompanyWeb.get',return_value=self.page()),patch('sales.agent6.ai.infer',side_effect=lambda p,c,g:response(p)),patch('sales.agent6.coordinator.memory.event',side_effect=stop_before_post_model_event):
            with self.assertRaises(InterruptedError):self.w.execute(task,lambda:None)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM research_documents').fetchone()[0],1)
            self.assertEqual(json.loads(c.execute('SELECT body FROM agent6_records').fetchone()[0])['workflow_state'],'VERIFICATION_PENDING')
        before=self.ledger();self.assertEqual(len(before),1)
        self.rs.paused(self.c['id']);self.c=self.rs.resume(self.c['id']);self.w=AgentCoordinator(self.store,self.c);self.w.initialize()
        task=self.rs.claim(self.c['id'],self.c['generation'])
        with patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=AssertionError('Original already saved')),patch('sales.agent6.ai.infer',side_effect=AssertionError('Inference already paid')):
            self.w.execute(task,lambda:None)
        self.assertEqual(self.ledger(),before)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT state FROM agent6_records').fetchone()[0],'VERIFIED')

    def test_original_repair_uses_same_candidate_limit_and_saved_page(self):
        self.config(max_calls_per_candidate=2)
        task=self.enqueue_original()
        with patch('sales.agent6.coordinator.CompanyWeb.get',return_value=self.page()),patch('sales.agent6.ai.infer',return_value={'output':{},'usage':{}}):self.w.execute(task,lambda:None)
        repairs=[t for t in self.tasks('candidate') if t['payload'].get('verification_repair')]
        self.assertEqual(len(repairs),1)
        with patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=AssertionError('Do not refetch')),patch('sales.agent6.ai.infer',side_effect=lambda p,c,g:response(p)):
            self.w.execute(repairs[0],lambda:None)
        ledger=self.ledger();self.assertEqual(len(ledger),2)
        self.assertEqual(len({r['candidate_id'] for r in ledger}),1)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT state FROM agent6_records').fetchone()[0],'VERIFIED')

    def test_default_candidate_limit_is_not_raised_for_repair(self):
        task=self.enqueue_original()
        with patch('sales.agent6.coordinator.CompanyWeb.get',return_value=self.page()),patch('sales.agent6.ai.infer',return_value={'output':{},'usage':{}}):self.w.execute(task,lambda:None)
        self.assertEqual(len(self.tasks('candidate')),1);self.assertEqual(len(self.ledger()),1)
        with self.store.connect() as c:
            b=json.loads(c.execute('SELECT body FROM agent6_records').fetchone()[0])
            self.assertEqual(b['recovery_action'],'candidate_limit_or_retry_policy')
            self.assertEqual(b['evidence_level'],'ORIGINAL_READ')

    def test_late_response_after_stop_keeps_usage_but_never_promotes(self):
        p,_=original.output()
        def provider(payload,cfg,check):
            self.rs.stop(self.c['id'])
            return {'output':response(payload)['output'],'usage':{'input_tokens':123,'output_tokens':45}}
        with self.assertRaises(InterruptedError):ai.call(self.store,self.c,'AGENCIES','page:late',p,lambda:None,provider)
        row=self.ledger()[0]
        self.assertEqual(row['status'],'cancelled');self.assertEqual(row['input_tokens'],123)
        self.assertIsNone(json.loads(row['body'])['output'])

    def test_timeout_repair_respects_configured_retry_zero(self):
        task=self.enqueue_original();self.config(max_calls_per_candidate=2,max_retries=0)
        with patch('sales.agent6.coordinator.CompanyWeb.get',return_value=self.page()),patch('sales.agent6.ai.infer',side_effect=TimeoutError()):self.w.execute(task,lambda:None)
        self.assertEqual(len(self.tasks('candidate')),1)

    def test_timeout_repair_when_user_configuration_allows_it(self):
        task=self.enqueue_original();self.config(max_calls_per_candidate=2,max_retries=1)
        with patch('sales.agent6.coordinator.CompanyWeb.get',return_value=self.page()),patch('sales.agent6.ai.infer',side_effect=TimeoutError()):self.w.execute(task,lambda:None)
        repair=[t for t in self.tasks('candidate') if t['payload'].get('verification_repair')][0]
        with patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=AssertionError('Saved source')),patch('sales.agent6.ai.infer',side_effect=lambda p,c,g:response(p)):self.w.execute(repair,lambda:None)
        self.assertEqual(len(self.ledger()),2)

    def test_invalid_diagnostics_redact_secrets_and_do_not_become_evidence(self):
        secret='synthetic-private-credential-12345'
        raw={'bad':'Bearer hidden-token info@example.test https://user:pass@example.test/a?token=abc#private '+secret}
        with patch.dict(os.environ,{'CUSTOMERSEARCH_AI_API_KEY':secret}):
            ai.call(self.store,self.c,'AGENCIES','batch:bad',support.screen_payload(),lambda:None,lambda p,c,g:{'output':raw,'usage':{}})
        with self.store.connect() as c:
            row=dict(c.execute('SELECT * FROM agent7_diagnostics').fetchone())
            self.assertEqual(c.execute('SELECT count(*) FROM research_documents').fetchone()[0],0)
        excerpt=row['excerpt']
        for private in (secret,'hidden-token','info@example.test','user:pass','token=abc','#private'):self.assertNotIn(private,excerpt)
        self.assertIn('https://example.test/a',excerpt)

    def test_temporary_capacity_deferral_keeps_search_and_query_reservation(self):
        self.w.enqueue('search','AGENCIES',support.query(),'deferred-search')
        task=self.tasks('search')[0]
        with patch('sales.agent6.coordinator.budget.remaining',return_value=0),patch('sales.agent6.coordinator.acquire',side_effect=AssertionError('Capacity unavailable')):
            result=self.w.execute(task,lambda:None)
        self.assertEqual(result,{'deferred_resource':'ai_screen'})
        with self.store.connect() as c:
            before=c.execute("SELECT used FROM commercial_resources WHERE engine='AGENCIES' AND resource='queries'").fetchone()[0]
            c.execute("UPDATE research_tasks SET state='budget',error='Budget operativo esaurito: ai_screen' WHERE id=?",(task['id'],))
        self.w.tick()
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT state FROM research_tasks WHERE id=?',(task['id'],)).fetchone()[0],'pending')
            self.assertEqual(c.execute("SELECT used FROM commercial_resources WHERE engine='AGENCIES' AND resource='queries'").fetchone()[0],before)
            self.assertEqual(c.execute("SELECT count(*) FROM research_tasks WHERE kind='search'").fetchone()[0],1)

    def test_replay_bypasses_exhausted_capacity_without_a_second_call(self):
        self.config(max_calls_per_engine=1)
        task=self.enqueue_original()
        with patch('sales.agent6.coordinator.CompanyWeb.get',return_value=self.page()),patch('sales.agent6.ai.infer',side_effect=lambda p,c,g:response(p)):
            self.w.execute(task,lambda:None)
        # Simulate a completed call whose task wasn't acknowledged before Stop.
        self.stop_resume();task=self.tasks('candidate')[0]
        with patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=AssertionError('Saved page')),patch('sales.agent6.ai.infer',side_effect=AssertionError('Saved inference')):
            result=self.w.execute(task,lambda:None)
        self.assertIsNone(result);self.assertEqual(len(self.ledger()),1)

    def test_resume_preserves_plan_choice_and_exploration_index(self):
        self.w.tick()
        task=next(t for t in self.tasks('agent_plan') if t['strategy']=='AGENCIES')
        chosen={**support.query('cerchiamo freelance WordPress Italia'),'selection':'exploration','memory_adjustment':0,'selection_index':3}
        memory.event(self.store,self.c,'AGENCIES','plan',str(task['id']),{'chosen':chosen,'reason':'Synthetic committed choice'})
        self.stop_resume()
        with patch('sales.agent6.ai.infer',side_effect=AssertionError('Plan already complete')):
            self.w.execute(task,lambda:None);self.w.execute(task,lambda:None)
        searches=self.tasks('search');self.assertEqual(len(searches),1)
        self.assertEqual(searches[0]['payload']['query'],chosen['query'])
        self.assertEqual(searches[0]['payload']['selection_index'],3)
        with self.store.connect() as c:
            self.assertEqual(c.execute("SELECT used FROM commercial_resources WHERE engine='AGENCIES' AND resource='queries'").fetchone()[0],1)

    def test_real_saved_noise_replans_then_completes_synthetic_original_verification(self):
        # Noise is authentic Campaign 35 material; Alfa and all model outputs
        # are synthetic. This proves orchestration, not real lead generation.
        self.c['target']=1
        with self.store.connect() as c:c.execute('UPDATE campaigns SET target=1 WHERE id=?',(self.c['id'],))
        noise=copy.deepcopy(SAVED['items'][:5]);seen_plans=[];searches=[]
        good={'url':self.page()['url'],'title':'Alfa Srl','content':original.TEXT}
        def provider(p,cfg,check):
            if p['task']==schema.PLAN:
                if p['flow']!='AGENCIES':return {'output':{'decision':'stop','queries':[],'reason':'Other synthetic flows have no proposal'},'usage':{}}
                seen_plans.append(copy.deepcopy(p))
                if p['round']==0:q='agenzia cerchiamo freelance WordPress Veneto'
                elif p['memory']['recent_queries'] and p['memory']['sources']:q='agenzia cerchiamo freelance frontend Italia'
                else:raise AssertionError('Planner must receive observed noise before changing strategy')
                return {'output':{'decision':'search','queries':[support.query(q)],'reason':'Change query after saved institutions and suppliers'},'usage':{}}
            if all(e['url']==good['url'] for e in p['evidence']):return response(p)
            analyses=[]
            for rid in p['result_ids']:
                e=next(e for e in p['evidence'] if e['result_id']==rid)
                analyses.append({'result_id':rid,'kind':'SUPPLIER_OFFER' if 'graphite.it' in e['url'] else 'EDITORIAL',
                    'kind_ref':{'segment_id':e['segments'][0]['segment_id']},'facts':[],
                    'hypothesis':'Frozen noise fixture: no concrete buyer request','missing':['request']})
            return {'output':{'analyses':analyses},'usage':{}}
        def search(store,p,check):
            searches.append(p['query']);return noise if len(searches)==1 else [good]
        with patch('sales.agent6.ai.infer',side_effect=provider),patch('sales.agent6.coordinator.acquire',side_effect=search),patch('sales.agent6.coordinator.CompanyWeb.get',return_value=self.page()) as reader:
            run_campaign(self.store,self.c,lambda:None,lambda _:None)
        self.assertEqual(len(searches),2);self.assertNotEqual(searches[0],searches[1]);self.assertEqual(len(seen_plans),2)
        self.assertEqual(reader.call_count,1)
        with self.store.connect() as c:
            promoted=[json.loads(r[0]) for r in c.execute("SELECT body FROM agent6_records WHERE state IN ('VERIFIED','POTENTIAL')")]
            self.assertEqual(len(promoted),1);self.assertEqual(promoted[0]['url'],good['url'])
            self.assertTrue(promoted[0]['identity_verified']);self.assertEqual(promoted[0]['evidence_level'],'ORIGINAL_VERIFIED')
            self.assertEqual(c.execute('SELECT count(*) FROM prospects').fetchone()[0],0)
        self.assertLessEqual(len(self.ledger()),20)

    def test_retention_and_migration_are_idempotent(self):
        with self.store.connect() as c:
            for i in range(205):diagnostics.retain(c,i,self.c['id'],schema.READ,{'invalid':'x'*9000},[])
            self.assertEqual(c.execute('SELECT count(*) FROM agent7_diagnostics').fetchone()[0],200)
            self.assertLessEqual(c.execute('SELECT max(length(excerpt)) FROM agent7_diagnostics').fetchone()[0],8000)
            c.execute("UPDATE agent7_diagnostics SET created_at='2000-01-01T00:00:00+00:00'")
            memory.migrate(c);memory.migrate(c)
            self.assertEqual(c.execute('SELECT count(*) FROM agent7_diagnostics').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM research_schema WHERE version=700').fetchone()[0],1)


if __name__=='__main__':unittest.main()
