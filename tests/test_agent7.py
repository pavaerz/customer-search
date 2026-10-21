"""Offline system regressions; real snippets and synthetic service responses.

Network and paid services are disabled. E89's original was NOT saved in 35:
its inaccessible-original test is explicitly synthetic, never a real outcome.
The Alfa original/identity is also synthetic and exercises the full pipeline.
"""
import copy
import gzip
import html
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_agent6 as original
import test_agent6_campaign32 as support
from sales.agent6 import schema, grounding, recovery, qualification, budget, commercial_policy, FLOWS
from sales.commercial.coordinator import run_campaign

SAVED=json.loads((Path(__file__).parent/'fixtures/agent6/campaign35/saved.json').read_text())


def response(payload, kind='BUYER_DEMAND'):
    """Synthetic ID-only model, using actual canonical spans from input."""
    values=[]
    for rid in payload['result_ids']:
        anchors=[s for e in payload['evidence'] if e['result_id']==rid for s in e['segments']]
        facts=[]
        for field,contains in [('entity','Alfa Srl'),('request','We are looking for'),('technical','WordPress'),('contract','freelance'),('geography','Remote from Italy')]:
            found=next((s for s in anchors if (s['text']==contains if field=='entity' else contains in s['text'])),None)
            if found:facts.append({'field':field,'ref':{'segment_id':found['segment_id']}})
        if payload['task']==schema.SCREEN:facts=facts[:2]
        values.append({'result_id':rid,'kind':kind if facts else 'UNKNOWN','kind_ref':facts[0]['ref'] if facts else None,'facts':facts,'hypothesis':'Synthetic complete-project fixture, not a real lead','missing':[]})
    return {'output':{'analyses':values},'usage':{'input_tokens':100,'output_tokens':100}}


class Grounding(unittest.TestCase):
    def payload(self):
        p,_=original.output();p['evidence']=grounding.attach(p['evidence']);return p

    def test_ids_extract_canonical_text_and_original_offsets(self):
        p=self.payload();output=response(p)['output'];v,errors=schema.validate_response(output,p)
        self.assertEqual(errors,[])
        b=qualification.evaluate(original.source(),v['analyses'][0],p['evidence'],'AZIENDE',original.identity())
        self.assertEqual(b['state'],'VERIFIED')
        for f in b['facts']:
            self.assertEqual(f['quote'],original.TEXT[f['document_start']:f['document_end']])
        self.assertEqual(b['entity_name'],'Alfa Srl')

    def test_ids_are_stable_only_for_same_source_hash_and_block(self):
        p=self.payload();e=p['evidence'][0]
        self.assertEqual(grounding.segments(e),grounding.segments(e))
        changed={**e,'text':e['text']+' changed'}
        with self.assertRaisesRegex(ValueError,'wrong_source'):grounding.resolve({'segment_id':e['segments'][0]['segment_id']},[changed])
        with self.assertRaisesRegex(ValueError,'unknown_or_ambiguous_segment'):grounding.resolve({'segment_id':'invented'},[e])

    def test_other_result_cannot_supply_a_segment(self):
        p=self.payload();p['result_ids'].append('other')
        other=grounding.attach(schema.bundle([{'id':'other',**original.source(url='https://other.example')}]))[0]
        other['id']='e2';other['segments']=grounding.segments(other);p['evidence'].append(other)
        o=response(p)['output'];o['analyses'][0]['kind_ref']={'segment_id':other['segments'][0]['segment_id']}
        v,errors=schema.validate_response(o,p)
        self.assertEqual(len(v['analyses']),1);self.assertEqual(errors[0]['code'],'wrong_source')

    def test_forged_segment_offsets_are_not_trusted(self):
        p=self.payload();e=p['evidence'][0];ref={'segment_id':e['segments'][0]['segment_id']}
        expected=grounding.resolve(ref,p['evidence']);e['segments'][0]['start']=999
        self.assertEqual(expected,grounding.resolve(ref,p['evidence']))

    def test_unknown_segment_isolated_from_valid_sibling(self):
        p=self.payload();other=copy.deepcopy(p['evidence'][0]);other.update(id='e2',result_id='other');other['segments']=grounding.segments(other)
        p['evidence'].append(other);p['result_ids'].append('other');o=response(p)['output']
        o['analyses'][0]['facts'][0]['ref']={'segment_id':'missing'}
        v,errors=schema.validate_response(o,p)
        self.assertEqual([a['result_id'] for a in v['analyses']],['other'])
        self.assertEqual(errors[0]['code'],'unknown_or_ambiguous_segment')

    def test_provider_receives_one_copy_of_passages_and_no_mutable_offsets(self):
        p=self.payload();wire=grounding.provider_payload(p)
        self.assertIn('text',p['evidence'][0]);self.assertNotIn('text',wire['evidence'][0])
        self.assertNotIn('hash',wire['evidence'][0]);self.assertIsInstance(wire['evidence'][0]['segments'],dict)
        for e in p['evidence']:
            selected=next(w for w in wire['evidence'] if w['id']==e['id'])['segments']
            for anchor in grounding.segments(e):
                self.assertEqual(selected[anchor['segment_id']],e['text'][anchor['start']:anchor['end']])


class LiteralRecovery(unittest.TestCase):
    def test_saved_e89_is_a_reading_candidate_not_a_qualified_client(self):
        item=next(i for i in SAVED['items'] if 'e89.it' in i['url'])
        b=recovery.literal_invitation({'url':item['url'],'text':item['title']+'\n'+item['content'],'original':False},'AGENCIES')
        self.assertIsNotNone(b);self.assertEqual(b['state'],'DISCOVERED')
        self.assertFalse(b['identity_verified']);self.assertEqual(b['budget']['kind'],'UNKNOWN')
        self.assertEqual(b['evidence_level'],'SNIPPET_ONLY')

    def test_saved_noise_does_not_get_a_freelance_fallback(self):
        for item in SAVED['items']:
            if 'e89.it' in item['url']:continue
            with self.subTest(url=item['url']):
                b=recovery.literal_invitation({'url':item['url'],'text':item['title']+'\n'+item['content'],'original':False},item['flow'])
                self.assertIsNone(b)


class QueryLogic(unittest.TestCase):
    def test_each_saved_35_query_has_a_commercially_weak_branch(self):
        for q in SAVED['executed_queries']:
            proposed={**support.query(q['query']),**q}
            with self.subTest(flow=q['flow']):
                decision=commercial_policy.assess_query(proposed,q['flow'])
                self.assertFalse(decision['allowed'])
                self.assertTrue(decision['all_branches_checked'])

    def test_valid_invitations_survive_different_services_and_regions(self):
        q=support.query('(agenzia OR startup) ("cerchiamo freelance" OR "collabora con noi") (WordPress OR frontend) (Veneto OR Toscana)')
        result=commercial_policy.assess_query(q,'AGENCIES')
        self.assertTrue(result['allowed']);self.assertEqual(result['branch_count'],16)

    def test_supplier_branch_cannot_hide_behind_a_good_invitation(self):
        for query in ('agenzia ("cerchiamo freelance" OR "collaboratori esterni") WordPress',
                      'cerchiamo freelance (WordPress OR coworking)',
                      'azienda ("nuovi prodotti" OR "trasformazione digitale") ecommerce'):
            self.assertFalse(commercial_policy.assess_query(support.query(query),'AZIENDE')['allowed'])

    def test_commercial_change_is_exploratory_not_declared_demand(self):
        q=support.query('azienda nuovi prodotti ecommerce Veneto')
        q['hypothesis']='Verify an independent digital gap on the company website.'
        result=commercial_policy.assess_query(q,'AZIENDE')
        self.assertTrue(result['allowed']);self.assertEqual(result['intent'],'business_signal_hypothesis')

    def test_negative_keywords_and_domain_names_are_not_positive_intent(self):
        for query in ('agenzia wordpress -"cerchiamo freelance"','site:cerchiamo-freelance.it WordPress'):
            self.assertFalse(commercial_policy.assess_query(support.query(query),'AGENCIES')['allowed'])

    def test_pathological_boolean_expansion_is_explicitly_rejected(self):
        query='cerchiamo freelance WordPress '+' '.join(['(a OR b OR c)']*6)
        r=commercial_policy.assess_query(support.query(query),'AGENCIES')
        self.assertEqual(r['reason'],'query_boolean_expansion_too_large')


class RecoveryPipeline(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp()
        self.store,self.c,self.w,self.rs=self.base.store,self.base.c,self.base.w,self.base.rs
        self.network=patch('socket.create_connection',side_effect=AssertionError('Offline test: outbound network forbidden'))
        self.network.start()
        # Exercise the semantic-error branch deliberately. The separate 9.1
        # integration test covers bypassing an unnecessary snippet inference.
        cheap=patch('sales.agent6.completion.skip_screening',return_value=None)
        cheap.start();self.addCleanup(cheap.stop)

    def tearDown(self):
        self.network.stop();self.base.tearDown()

    def fake(self,p,cfg,check):
        if p['task']==schema.PLAN:
            return {'output':{'decision':'search' if not p['round'] else 'stop','reason':'Offline controlled plan',
                              'queries':[support.query('agenzia cerca freelance WordPress Italia')] if not p['round'] else []},'usage':{'input_tokens':10,'output_tokens':10}}
        if p['task']==schema.SCREEN:
            # Fault injection, not an authentic raw response (35 did not retain it).
            return {'output':{'analyses':[{'result_id':r,'kind':'AGENCY_PARTNERSHIP',
                'kind_ref':{'segment_id':'not-in-evidence'},'facts':[],
                'hypothesis':'Injected invalid reference','missing':[]} for r in p['result_ids']]},'usage':{'input_tokens':10,'output_tokens':10}}
        return response(p)

    def test_real_e89_bad_ai_reaches_authorized_reader_and_preserves_failure(self):
        item=next(i for i in SAVED['items'] if 'e89.it' in i['url'])
        # Synthetic access denial at the controlled reader, not an observed E89 response.
        with patch('sales.agent6.ai.infer',side_effect=self.fake),patch('sales.agent6.coordinator.acquire',return_value=[item]),patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=ValueError('HTTP 403')) as reader:
            run_campaign(self.store,self.c,lambda:None,lambda _:None)
        self.assertGreaterEqual(reader.call_count,1)
        with self.store.connect() as c:
            records=[json.loads(r[0]) for r in c.execute('select body from agent6_records')]
            self.assertTrue(records);self.assertTrue(all(b['state'] not in ('VERIFIED','POTENTIAL') for b in records))
            failed=next(b for b in records if b.get('workflow_state')=='ORIGINAL_READ_FAILED')
            self.assertTrue(failed['facts']);self.assertEqual(failed['evidence_level'],'SNIPPET_ONLY')
            self.assertEqual(c.execute('select count(*) from prospects').fetchone()[0],0)
            self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok')

    def test_e89_legacy_literal_quote_error_also_recovers(self):
        item=next(i for i in SAVED['items'] if 'e89.it' in i['url'])
        def bad_quote(p,cfg,check):
            if p['task']!=schema.SCREEN:return self.fake(p,cfg,check)
            e=p['evidence'][0]
            return {'output':{'analyses':[{'result_id':p['result_ids'][0],'kind':'AGENCY_PARTNERSHIP',
                'kind_ref':{'id':e['id'],'quote':'SYNTHETIC INVALID QUOTE','occurrence':0},
                'facts':[],'hypothesis':'Fault injection, not saved output','missing':[]}]},'usage':{}}
        q=support.query('agenzia cerca freelance WordPress Italia')
        with patch('sales.agent6.coordinator.acquire',return_value=[item]),patch('sales.agent6.ai.infer',side_effect=bad_quote):
            self.w._execute({'id':666,'kind':'search','strategy':'AGENCIES','payload':q},lambda:None)
            with self.store.connect() as c:
                r=c.execute("select * from research_tasks where kind='agent_screen'").fetchone()
            self.w._execute({**dict(r),'payload':json.loads(r['payload'])},lambda:None)
        with self.store.connect() as c:
            b=json.loads(c.execute('select body from agent6_records').fetchone()[0])
            self.assertEqual(b['workflow_state'],'ORIGINAL_READ_PENDING')
            self.assertEqual(b['validation_error']['code'],'quote_missing_or_occurrence_invalid')
            self.assertNotIn(b['state'],('VERIFIED','POTENTIAL'))

    def test_full_cycle_bad_screen_then_segment_read_produces_verified_synthetic_project(self):
        # Synthetic integration fixture proves mechanics, never commercial efficacy.
        page={'url':'https://alfa.example/careers','status':200,'checked_at':original.DATE,
              'html':'<title>Alfa Srl</title>'+''.join('<p>'+line+'</p>' for line in original.TEXT.splitlines())+
              '<p>Partita IVA: 12345678901</p><p>Sede legale: Via Roma 12, 35100 Padova (PD)</p><a href="mailto:info@alfa.example">Contatti</a>'}
        item={'url':page['url'],'title':'Alfa Srl','content':original.TEXT}
        with patch('sales.agent6.ai.infer',side_effect=self.fake),patch('sales.agent6.coordinator.acquire',return_value=[item]),patch('sales.agent6.coordinator.CompanyWeb.get',return_value=page) as reader:
            run_campaign(self.store,self.c,lambda:None,lambda _:None)
        self.assertEqual(reader.call_count,1)
        with self.store.connect() as c:
            b=json.loads(c.execute("select body from agent6_records where state='VERIFIED'").fetchone()[0])
            self.assertEqual(b['entity_name'],'Alfa Srl');self.assertEqual(b['evidence_level'],'ORIGINAL_VERIFIED')
            self.assertTrue(b['documents']);self.assertTrue(b['screening_recovery'])
            self.assertEqual(c.execute('select count(*) from prospects').fetchone()[0],0)
            self.assertLessEqual(c.execute('select count(*) from commercial_ai_executions where attempt=1').fetchone()[0],20)

    def test_pending_original_is_durable_across_stop_resume(self):
        item=next(i for i in SAVED['items'] if 'e89.it' in i['url'])
        q=support.query('agenzia cerca freelance WordPress Italia')
        task={'id':999,'kind':'search','strategy':'AGENCIES','payload':{**q,'selection':'exploitation'}}
        with patch('sales.agent6.ai.infer',side_effect=self.fake),patch('sales.agent6.coordinator.acquire',return_value=[item]):
            self.w._execute(task,lambda:None)
            with self.store.connect() as c:
                row=c.execute("select * from research_tasks where kind='agent_screen'").fetchone()
                screening={**dict(row),'payload':json.loads(row['payload'])}
            self.w._execute(screening,lambda:None)
        with self.store.connect() as c:
            b=json.loads(c.execute('select body from agent6_records').fetchone()[0]);self.assertEqual(b['workflow_state'],'ORIGINAL_READ_PENDING')
            count=c.execute('select count(*) from commercial_ai_executions where attempt=1').fetchone()[0]
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.rs.resume(self.c['id'])
        with self.store.connect() as c:
            self.assertEqual(c.execute("select count(*) from research_tasks where kind='candidate' and state='pending'").fetchone()[0],1)
            self.assertEqual(c.execute('select count(*) from commercial_ai_executions where attempt=1').fetchone()[0],count)

    def test_pending_verification_reserves_capacity_but_idle_stages_do_not(self):
        cfg=self.c['filters']['commercial']['ai']
        initial=budget.remaining(self.store,self.c,'AZIENDE',cfg,'screen')
        self.assertGreater(initial,2)
        for n in range(7):
            self.w.enqueue('candidate','AZIENDE',{'url':f'https://alfa.example/{n}'},f'candidate-{n}')
        self.assertEqual(budget.remaining(self.store,self.c,'AZIENDE',cfg,'screen'),1)
        self.assertGreater(budget.remaining(self.store,self.c,'AZIENDE',cfg,'verify'),1)
        with self.store.connect() as c:c.execute("update research_tasks set state='done' where kind='candidate'")
        self.assertEqual(budget.remaining(self.store,self.c,'AZIENDE',cfg,'screen'),initial)

    def test_global_and_flow_limits_remain_hard_after_redistribution(self):
        for flow in self.c['filters']['commercial_engines']:
            for n in range(10):
                # Distinct contexts avoid a cache hit; all are synthetic.
                p=support.plan_payload(flow,n);p['nonce']=n
                self.base.call(flow,'plan:'+str(n),p)
        with self.store.connect() as c:
            count=c.execute('select count(*) from commercial_ai_executions where attempt=1').fetchone()[0]
            self.assertEqual(count,20)
            self.assertTrue(all(r[0]<=8 for r in c.execute('select count(*) from commercial_ai_executions where attempt=1 group by engine')))
            self.assertEqual(c.execute('select count(distinct engine) from commercial_ai_executions where attempt=1').fetchone()[0],3)

    def test_saved_screening_queue_survives_stop_without_repeating_search(self):
        item=next(i for i in SAVED['items'] if 'e89.it' in i['url'])
        q=support.query('agenzia cerca freelance WordPress Italia')
        with patch('sales.agent6.coordinator.acquire',return_value=[item]) as search:
            self.w._execute({'id':555,'kind':'search','strategy':'AGENCIES','payload':{**q,'selection':'exploitation'}},lambda:None)
            self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.rs.resume(self.c['id'])
        self.assertEqual(search.call_count,1)
        with self.store.connect() as c:
            task=c.execute("select payload,state from research_tasks where kind='agent_screen'").fetchone()
            self.assertEqual(task['state'],'pending');self.assertEqual(json.loads(task['payload'])['batch'][0][0]['url'],item['url'])

    def test_all_five_flows_can_plan_and_search_with_existing_shared_maximum(self):
        from sales.agent6.api import preview
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        filters={**copy.deepcopy(self.base.filters),'commercial_engines':list(FLOWS)}
        filters['deep_plan_token']=preview(self.store,filters)['approval_token']
        campaign=self.rs.create(filters)
        def model(p,cfg,check):
            if p['task']!=schema.PLAN:self.fail('Empty search must not run screening')
            query=support.query('cerchiamo freelance WordPress '+p['flow'])
            if p['flow']=='SOCIAL':query['query']='site:linkedin.com cerchiamo freelance WordPress Italia'
            if p['flow']=='NEWS':
                query['query']='azienda nuova linea prodotti Veneto'
                query['hypothesis']='Verify the named company and related digital gap on its official site.'
            return {'output':{'decision':'search' if not p['round'] else 'stop','reason':'Five-flow synthetic test','queries':[query] if not p['round'] else []},'usage':{'input_tokens':10,'output_tokens':10}}
        with patch('sales.agent6.ai.infer',side_effect=model),patch('sales.agent6.coordinator.acquire',return_value=[]) as search:
            run_campaign(self.store,campaign,lambda:None,lambda _:None)
        self.assertEqual(search.call_count,5)
        with self.store.connect() as c:
            self.assertEqual({r[0] for r in c.execute("select strategy from research_tasks where campaign_id=? and kind='search' and state='done'",(campaign['id'],))},set(FLOWS))
            self.assertLessEqual(c.execute('select count(*) from commercial_ai_executions where campaign_id=? and attempt=1',(campaign['id'],)).fetchone()[0],20)

    def test_authentic_saved_original_reaches_reasoned_review_not_invented_verification(self):
        with gzip.open(Path(__file__).parent/'fixtures/agent6/campaign31.json.gz','rt') as f:
            saved=next(r for r in json.load(f) if r['id']==1053)
        # Authentic extracted original text, rendered as escaped paragraphs for
        # the offline reader. This is not a new fetch or the original raw HTML.
        page={'url':saved['url'],'status':200,'checked_at':original.DATE,
              'html':'<title>'+html.escape(saved['title'])+'</title>'+''.join('<p>'+html.escape(line)+'</p>' for line in saved['text'].splitlines())}
        def model(p,cfg,check):
            if p['task']!=schema.READ:return self.fake(p,cfg,check)
            anchors=[s for e in p['evidence'] for s in e['segments']]
            request=next(s for s in anchors if 'We are looking for an experienced freelance' in s['text'])
            technical=next(s for s in anchors if 'WordPress' in s['text'])
            entity=next(s for s in anchors if s['text']=='AFM')
            facts=[{'field':field,'ref':{'segment_id':value['segment_id']}} for field,value in [('entity',entity),('request',request),('technical',technical),('contract',request)]]
            return {'output':{'analyses':[{'result_id':'r1','kind':'AGENCY_PARTNERSHIP','kind_ref':{'segment_id':request['segment_id']},'facts':facts,'hypothesis':'Saved third-party request; employer identity and eligibility require verification.','missing':['entity','geography','contact']}]},'usage':{'input_tokens':100,'output_tokens':100}}
        item={'url':saved['url'],'title':saved['title'],'content':' '.join(saved['snippets'])}
        with patch('sales.agent6.ai.infer',side_effect=model),patch('sales.agent6.coordinator.acquire',return_value=[item]),patch('sales.agent6.coordinator.CompanyWeb.get',return_value=page):
            run_campaign(self.store,self.c,lambda:None,lambda _:None)
        with self.store.connect() as c:
            b=json.loads(c.execute("select body from agent6_records where json_extract(body,'$.original')=1 limit 1").fetchone()[0])
            self.assertEqual(b['state'],'NEEDS_REVIEW');self.assertEqual(b['entity_name'],'AFM')
            self.assertFalse(b['identity_verified']);self.assertIn('geography',b['missing'])
            self.assertTrue(any(f['field']=='request' and f['original'] for f in b['facts']))

