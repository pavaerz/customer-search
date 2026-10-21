"""Real C44 originals + synthetic provider contracts. No inference or network."""
import copy
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_ai_first as harness
from sales.agent6 import ai, grounding, decision
from sales.commercial.ai_tasks import request_schema
from sales.commercial.token_count import estimate, encoding
from sales.agent6 import budget, schema, FLOWS
from sales.db import encode

FIXTURE = Path(__file__).parent/'fixtures/ai_first/campaign44/originals.json.gz'


class GroundedWire(unittest.TestCase):
    def test_social_saved_queries_cover_both_requested_platforms_before_repeating(self):
        from sales.agent6.query_pipeline import social_coverage
        linkedin=harness.query('site:linkedin.com/posts Veneto "cerchiamo" "frontend freelance"')
        instagram=harness.query('site:instagram.com/p Veneto "cerchiamo" "web designer"')
        receipts=[{'query':linkedin['query'],'results':3}]
        self.assertEqual(social_coverage([linkedin,instagram],receipts),[instagram])
        self.assertEqual(social_coverage([linkedin],receipts),[])
        # Empty results still represent an actual search; provider errors don't.
        self.assertEqual(social_coverage([linkedin,instagram],[{'query':linkedin['query'],'results':0}]),[instagram])
        self.assertEqual(social_coverage([linkedin,instagram],[{'query':linkedin['query'],'results':0,'technical_error':'503'}]),[linkedin,instagram])
        receipts.append({'query':instagram['query'],'results':1})
        self.assertEqual(social_coverage([linkedin,instagram],receipts),[linkedin,instagram])

    def test_c44_tld_query_preserves_territory_and_restriction(self):
        from sales.agent6.query_pipeline import normalize
        q=normalize('site:*.it Veneto azienda produzione imballaggi sito ufficiale')
        self.assertTrue(q['allowed'])
        self.assertEqual(q['query'],'site:.it Veneto azienda produzione imballaggi sito ufficiale')
        self.assertIn('italian_tld_wildcard',q['repairs'])
        self.assertFalse(normalize('site:*.invalid/path Veneto')['allowed'])

    def test_closed_ids_do_not_mutate_shared_schema_or_free_text(self):
        p = harness.payload()
        p['links'] = [{'id':'l1', 'url':'https://alfa.example/jobs', 'label':'Lavoro'}]
        before = copy.deepcopy(decision.schema())
        wire = request_schema(p)
        allowed = wire['properties']['facts']['items']['properties']['segment_id']['enum']
        self.assertEqual(set(allowed), {s['segment_id'] for e in p['evidence'] for s in grounding.segments(e)})
        self.assertNotIn('metadata', allowed)
        self.assertNotIn('e1', allowed)
        self.assertNotIn('l1', allowed)
        self.assertEqual(wire['properties']['action']['properties']['link_id']['enum'], ['', 'l1'])
        self.assertNotIn('enum', wire['properties']['reason'])
        self.assertNotIn('enum', wire['properties']['entity_name'])
        self.assertNotIn('enum', wire['properties']['action']['properties']['query'])
        self.assertEqual(before, decision.schema())
        other = request_schema(harness.payload('Beta Srl\nCerchiamo sviluppatori freelance.'))
        self.assertNotEqual(allowed, other['properties']['facts']['items']['properties']['segment_id']['enum'])
        self.assertEqual(wire['properties']['action']['properties']['link_id']['enum'], ['', 'l1'])

    def test_local_tokenizer_no_fetch_and_injection_strings_are_plain_text(self):
        encoding.cache_clear()
        with patch('socket.create_connection',side_effect=AssertionError('Network forbidden')):
            enc = encoding()
            self.assertGreater(len(enc.encode('<|endoftext|> Testo italiano con caratteri à è ü.', disallowed_special=())), 0)
            p = harness.payload()
            value = estimate(p, {'model':'gpt-5.4-mini', 'provider':'REMOTE'})
        self.assertFalse(value['exact'])
        self.assertGreater(value['tokens'], value['text_tokens'])
        self.assertLess(value['tokens'], ai.input_bytes(p))

    def test_unknown_tokenizer_does_not_guess_a_four_character_ratio(self):
        p = harness.payload()
        e = estimate(p, {'model':'unrecognized-model', 'provider':'REMOTE'})
        self.assertEqual(e['basis'], 'conservative_utf8_bytes')
        self.assertGreater(e['tokens'], len(json.dumps(p)))


class CommercialMeaning(unittest.TestCase):
    """Hand-labelled contracts test consistency, not a live model's accuracy."""
    def test_supplier_employee_course_and_portfolio_cannot_be_positive_invitation(self):
        for intent in ('SUPPLYING_SERVICES','EMPLOYEE_ONLY','TRAINING','COMPLETED_PROJECT'):
            with self.subTest(intent=intent):
                p=harness.payload();out=harness.response(p)
                out['assessment']['intent']=intent
                with self.assertRaisesRegex(ValueError,'commercial_intent_conflict'):
                    decision.validate(out,p)
                # A coherent negative is retained, never rewritten as positive.
                out['decision']='NOT_INTERESTING'
                self.assertEqual(decision.validate(out,p)[0]['decision'],'NOT_INTERESTING')

    def test_references_to_unlisted_facts_and_cross_company_evidence_fail(self):
        p=harness.payload();out=harness.response(p)
        out['assessment']['intent_facts']=[11]
        with self.assertRaisesRegex(ValueError,'unknown_assessment_fact'):
            decision.validate(out,p)
        out=harness.response(p)
        p['evidence'][0]['unit_id']='another-employer'
        with self.assertRaisesRegex(ValueError,'cross_unit_reference'):
            decision.validate(out,p)

    def test_funding_or_old_site_alone_cannot_justify_a_rebuild(self):
        p=harness.payload();out=harness.response(p)
        out.update(relationship='PROACTIVE_OUTREACH',currentness='CURRENT_OBSERVATION')
        out['assessment'].update(intent='COMPANY_ACTIVITY',scope='FULL_PROJECT')
        with self.assertRaisesRegex(ValueError,'incomplete_proactive_evidence'):
            decision.validate(out,p)
        # Declaring a need without documenting the solution checked is still insufficient.
        request=out['facts'][1]['segment_id']
        out['facts'] += [{'field':f,'segment_id':request} for f in ('signal','digital_gap','scope')]
        with self.assertRaisesRegex(ValueError,'proactive_solution_unverified'):
            decision.validate(out,p)

    def test_documented_business_gap_can_support_proactive_not_declared_demand(self):
        text=(harness.TEXT+'\nNuova linea di macchinari configurabili per distributori esteri.'
              '\nIl configuratore attuale non supporta la nuova linea e richiede un rifacimento completo.'
              '\nIl progetto riguarda catalogo tecnico, configurazione e richieste preventivi.')
        p=harness.payload(text);out=harness.response(p)
        def fact(field,needle):
            s=next(s for e in p['evidence'] for s in grounding.segments(e) if needle in s['text'])
            return {'field':field,'segment_id':s['segment_id']}
        out['facts'] += [fact('signal','Nuova linea'),fact('digital_gap','configuratore attuale'),
                         fact('scope','progetto riguarda'),fact('existing_solution','configuratore attuale')]
        out.update(relationship='PROACTIVE_OUTREACH',currentness='CURRENT_OBSERVATION',
                   service='website',reason='Catalogo e configurazione non coprono la nuova offerta.')
        out['assessment'].update(intent='COMPANY_ACTIVITY',intent_facts=[3],scope='FULL_PROJECT',
                                 scope_facts=[5],existing_solution='CHECKED_GAP',solution_facts=[6])
        valid,_=decision.validate(out,p)
        b=decision.materialize({'url':'https://alfa.example','original':True},valid,p['evidence'],p,'AZIENDE')
        self.assertEqual(b['opportunity_type'],'OPPORTUNITA_PROATTIVA')
        self.assertEqual(b['open_paid_project'],'UNKNOWN')
        self.assertIsNone(b['budget']['amount'])
        # Evidence of an adequate solution or a small fix prevents this promotion.
        for change in ({'existing_solution':'CHECKED_ADEQUATE'},{'scope':'SMALL_TASK'}):
            changed=copy.deepcopy(out);changed['assessment'].update(change)
            with self.assertRaises(ValueError):decision.validate(changed,p)

    def test_needs_research_requires_decision_changing_question(self):
        p=harness.payload();out=harness.response(p)
        out.update(decision='NEEDS_RESEARCH')
        out['action'].update(type='STOP',question='')
        with self.assertRaisesRegex(ValueError,'missing_decisive_question'):
            decision.validate(out,p)
        out['action']['question']='Accettano candidature freelance dall’Italia?'
        self.assertEqual(decision.validate(out,p)[0]['decision'],'NEEDS_RESEARCH')

    def test_closed_request_cannot_remain_contact_ready(self):
        p=harness.payload(harness.TEXT+'\nRicerca conclusa, posizione coperta.')
        out=harness.response(p)
        s=next(s for e in p['evidence'] for s in grounding.segments(e) if 'Ricerca conclusa' in s['text'])
        out['facts'].append({'field':'closed','segment_id':s['segment_id']})
        with self.assertRaisesRegex(ValueError,'closed_opportunity'):
            decision.validate(out,p)

    def test_standing_label_does_not_override_explicit_expiry(self):
        p=harness.payload();p['dates']=[{'role':'expires_at','value':'2026-10-19'}]
        with self.assertRaisesRegex(ValueError,'expired_request'):
            decision.validate(harness.response(p),p)

    def test_equity_and_unpaid_remain_distinct_from_paid_development(self):
        for compensation,expected in [('EQUITY_ONLY','EQUITY_ONLY_OPPORTUNITY'),
                                      ('UNPAID','UNPAID_COLLABORATION'),
                                      ('MIXED','MIXED_COMPENSATION'),
                                      ('PAID','PAID_DEVELOPMENT_OPPORTUNITY'),
                                      ('UNKNOWN','FREELANCE_COLLABORATION')]:
            self.assertEqual(decision.projection({'compensation':compensation})['arrangement'],expected)

    def test_contact_attribution_regulator_commenter_and_privacy_are_not_buyer_contacts(self):
        for mailbox in ('protocollo@gpdp.it','commentatore@example.net','privacy@alfa.example'):
            with self.subTest(mailbox=mailbox):
                p=harness.payload(harness.TEXT.replace('info@alfa.example',mailbox))
                out=harness.response(harness.payload())
                out['facts']=[]
                for field,needle in [('entity','Alfa Srl'),('request','Collaboriamo'),('contact',mailbox)]:
                    s=next(s for e in p['evidence'] for s in grounding.segments(e) if needle in s['text'])
                    out['facts'].append({'field':field,'segment_id':s['segment_id']})
                valid,_=decision.validate(out,p)
                b=decision.materialize({'url':p['evidence'][0]['url'],'original':True},valid,p['evidence'],p,'AGENCIES')
                self.assertEqual(b['contacts'],[])
                self.assertTrue(b['unattributed_contacts'])
                self.assertFalse(decision.projection(b)['READY_FOR_OUTREACH'])

    def test_explicit_application_to_free_mailbox_on_owner_site_is_usable(self):
        p=harness.payload(harness.TEXT+'\nInvia il tuo portfolio e la candidatura a alfajobs@gmail.com')
        out=harness.response(p)
        s=next(s for e in p['evidence'] for s in grounding.segments(e) if s['text']=='alfajobs@gmail.com')
        out['facts'][2]={'field':'contact','segment_id':s['segment_id']}
        b=decision.materialize({'url':p['evidence'][0]['url'],'original':True},out,p['evidence'],p,'AGENCIES')
        self.assertEqual(b['contacts'][0]['value'],'alfajobs@gmail.com')
        self.assertEqual(b['contacts'][0]['attribution'],'original_application_instruction')
        # Identical text on a publisher site does not establish the buyer's channel.
        p['evidence'][0]['url']='https://publisher.example/jobs'
        b=decision.materialize({'url':p['evidence'][0]['url'],'original':True},out,p['evidence'],p,'AGENCIES')
        self.assertEqual(b['contacts'],[])


class ActualOriginalContext(unittest.TestCase):
    def setUp(self):
        self.base = harness.IntegratedPath()
        self.base.setUp()
        self.store, self.w = self.base.store, self.base.w

    def tearDown(self):
        self.base.tearDown()

    def test_planner_requests_instagram_instead_of_reusing_only_linkedin_proposals(self):
        from sales.agent6 import memory
        self.base.c['filters']['commercial_engines']=list(FLOWS)
        with self.store.connect() as c:
            c.execute('UPDATE campaigns SET filters=? WHERE id=?',(encode(self.base.c['filters']),self.base.c['id']))
        linkedin=[harness.query('site:linkedin.com/posts Veneto "cerchiamo" '+term)
                  for term in ('"frontend freelance"','"web designer freelance"','"sviluppatore WordPress"')]
        instagram=harness.query('site:instagram.com/p Veneto "cerchiamo" "sviluppatore freelance"')
        observations=[]
        def provider(p,cfg,check):
            check();observations.append(p)
            queries=linkedin if len(observations)==1 else [instagram]
            return {'output':{'decision':'search','reason':'Test offline della copertura dei canali.',
                              'queries':queries},'usage':{}}
        with patch('sales.agent6.ai.infer',side_effect=provider):
            for index in (0,1):
                self.w.enqueue('agent_plan','SOCIAL',{'round':index},'coverage-plan-'+str(index))
                with self.store.connect() as c:
                    row=c.execute('SELECT * FROM research_tasks WHERE fingerprint=?',('coverage-plan-'+str(index),)).fetchone()
                    task={**dict(row),'payload':json.loads(row['payload'])}
                self.w.planning(task,lambda:None)
                if index==0:
                    with self.store.connect() as c:
                        query=json.loads(c.execute("SELECT payload FROM research_tasks WHERE kind='search' ORDER BY id DESC").fetchone()[0])
                        c.execute("UPDATE research_tasks SET state='done'")
                    memory.event(self.store,self.base.c,'SOCIAL','query','coverage-receipt',
                                 {'query':query['query'],'results':3,'strategy':query['strategy']})
        self.assertEqual(len(observations),2,'An already covered platform should not consume every saved proposal.')
        self.assertEqual(observations[1]['channel_strategy']['platforms_to_cover'],['instagram.com'])
        self.assertNotIn('focus_platform',observations[1]['channel_strategy'])
        with self.store.connect() as c:
            queries=[json.loads(r[0])['query'] for r in c.execute("SELECT payload FROM research_tasks WHERE kind='search' ORDER BY id")]
            self.assertEqual(len(queries),2)
            self.assertIn('instagram.com',queries[-1])
            self.assertEqual(c.execute('SELECT count(*) FROM commercial_ai_executions WHERE attempt=1').fetchone()[0],2)

    def test_discovery_metrics_count_new_queue_entries_without_pdf_or_duplicates(self):
        from sales.agent6.research import search
        from sales.discovery_control import measure
        q=harness.query()
        self.w.enqueue('search','AGENCIES',q,'metrics-search')
        with self.store.connect() as c:
            row=c.execute("SELECT * FROM research_tasks WHERE fingerprint='metrics-search'").fetchone()
            task={**dict(row),'payload':json.loads(row['payload'])}
        items=[{'url':'https://alfa.example/collabora','title':'Alfa'},
               {'url':'https://alfa.example/collabora','title':'Alfa duplicata'},
               {'url':'https://alfa.example/archive.pdf','title':'Documento PDF'},
               {'url':'https://www.linkedin.com/posts/alfa-request','title':'Post indicizzato'}]
        with patch('sales.agent6.research.acquire',return_value=items),measure(self.w.rs,self.base.c,task):
            search(self.w,task,lambda:None)
        with self.store.connect() as c:
            row=c.execute('SELECT unique_urls,details FROM discovery_operations ORDER BY id DESC').fetchone()
            details=json.loads(row['details'])
            self.assertEqual(row['unique_urls'],1)
            self.assertEqual(details['duplicates'],1)
            self.assertEqual(details['excluded'],1)
            self.assertEqual(details['indexed_unverifiable'],1)
            self.assertEqual(details['outcome'],'discovery_completed')
            self.assertFalse(details['qualified'])
            self.assertEqual(c.execute("SELECT count(*) FROM research_tasks WHERE kind='candidate'").fetchone()[0],1)

    def test_c44_originals_keep_commercial_context_under_unchanged_limit(self):
        expected = {
            'polygonstudio.it':'Collaboriamo attivamente con te',
            'webbes.it':'professionisti interni e esterni',
            'lapyramid.it':'dipendenti',
            'elementdigitalimage.com':'Sanmarco Informatica',
            'ifts-ai-solutions-developer':'corso',
            'its-ai-full-stack-developer-specialist':'corso',
        }
        observations = []
        for index, item in enumerate(json.loads(gzip.decompress(FIXTURE.read_bytes()))):
            page = item['page']
            needle = next(value for key,value in expected.items() if key in page['url'])
            tag = 'objective-c44-'+str(index)
            self.w.enqueue('candidate','AGENCIES',{'url':page['url'],'title':'Originale reale',
                           'query':'collaborazione','strategy':'standing','depth':0},tag)
            with self.store.connect() as c:
                row = c.execute('SELECT * FROM research_tasks WHERE fingerprint=?',(tag,)).fetchone()
                task = {**dict(row),'payload':json.loads(row['payload'])}
            def provider(payload,cfg,check):
                check()
                text = '\n'.join(e['text'] for e in payload['evidence'])
                self.assertIn(needle.casefold(), text.casefold(), page['url'])
                self.assertLessEqual(estimate(payload,cfg)['tokens'], cfg['max_input_tokens'])
                self.assertEqual(cfg['max_input_tokens'],8192)
                observations.append((page['url'],len(text)))
                result = harness.response(harness.payload())
                result.update(decision='NOT_INTERESTING',entity_name='',subject_role='UNKNOWN',
                              relationship='UNKNOWN',currentness='UNKNOWN',facts=[],
                              assessment={'intent':'UNKNOWN','intent_facts':[],'scope':'UNKNOWN','scope_facts':[],
                                          'existing_solution':'NOT_CHECKED','solution_facts':[],
                                          'interpretation':'Solo collaudo del trasporto del contesto.','objections':[]},
                              reason='Risposta sintetica per verificare la conservazione del testo.',
                              action={'type':'STOP','query':'','link_id':'','question':''})
                return {'output':result,'usage':{'input_tokens':100,'output_tokens':100}}
            with patch('sales.agent6.research.CompanyWeb.get',return_value=page),patch(
                    'sales.agent6.ai.infer',side_effect=provider):
                self.w.execute(task,lambda:None)
        # ai.call deliberately catches provider exceptions: require every
        # provider assertion to have completed, not merely an executed worker.
        self.assertEqual(len(observations),6)

    def test_metadata_only_never_spends_a_commercial_call(self):
        p = harness.payload()
        p['evidence'][0]['origin'] = 'original_metadata'
        with patch('sales.agent6.ai.infer',side_effect=AssertionError('Must not invoke model')):
            result = ai.call(self.store,self.base.c,'AGENCIES','metadata-only',p,lambda:None)
        self.assertEqual(result['error'],'commercial_text_missing')
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM commercial_ai_executions WHERE attempt=1').fetchone()[0],0)

    def test_single_reference_repair_keeps_same_candidate_and_replays_for_free(self):
        cfg=self.base.c['filters']['commercial']['ai']
        cfg.update(max_retries=1,max_calls_per_candidate=2)
        payload=harness.payload()
        bad=harness.response(payload)
        bad['facts'][0]['segment_id']='metadata'
        with patch('sales.agent6.ai.infer',side_effect=[
                {'output':bad,'usage':{}},{'output':harness.response(payload),'usage':{}}]) as provider:
            result=ai.call(self.store,self.base.c,'AGENCIES','one-candidate',payload,lambda:None)
            self.assertEqual(result['status'],'completed')
            self.assertIsNotNone(result['repair_of'])
            self.assertEqual(provider.call_count,2)
        with patch('sales.agent6.ai.infer',side_effect=AssertionError('Resume charged again')):
            replay=ai.call(self.store,self.base.c,'AGENCIES','one-candidate',payload,lambda:None)
        self.assertTrue(replay['replayed'])
        with self.store.connect() as c:
            rows=c.execute('SELECT candidate_id FROM commercial_ai_executions WHERE attempt=1').fetchall()
        self.assertEqual(len(rows),2)
        self.assertEqual(len({r[0] for r in rows}),1)

    def test_repair_never_bypasses_candidate_limit_or_retry_disabled(self):
        payload=harness.payload();bad=harness.response(payload);bad['facts'][0]['segment_id']='e1'
        cfg=self.base.c['filters']['commercial']['ai'];cfg.update(max_retries=1,max_calls_per_candidate=1)
        with patch('sales.agent6.ai.infer',return_value={'output':bad,'usage':{}}) as provider:
            result=ai.call(self.store,self.base.c,'AGENCIES','limited',payload,lambda:None)
        self.assertEqual(result['status'],'invalid')
        self.assertEqual(provider.call_count,1)
        cfg.update(max_retries=0,max_calls_per_candidate=4)
        with patch('sales.agent6.ai.infer',return_value={'output':bad,'usage':{}}) as provider:
            result=ai.call(self.store,self.base.c,'AGENCIES','no-retries',payload,lambda:None)
        self.assertEqual(provider.call_count,1)
        self.assertEqual(result['status'],'invalid')

    def test_thirty_calls_allow_five_starts_and_five_repairs_then_twenty_originals(self):
        cfg=self.base.c['filters']['commercial']['ai']
        cfg.update(max_calls_per_campaign=30,max_calls_per_engine=6,max_estimated_cost=.75,
                   max_retries=0,max_calls_per_candidate=4)
        self.base.c['filters']['commercial_engines']=list(FLOWS)
        with self.store.connect() as c:
            c.execute('UPDATE campaigns SET filters=? WHERE id=?',
                      (encode(self.base.c['filters']),self.base.c['id']))
        def plan(p,cfg,check):
            check()
            return {'output':{'decision':'search','reason':'Offline repair probe',
                              'queries':[harness.query()]},'usage':{}}
        for round_index in (0,1):
            for flow in FLOWS:
                p={'task':schema.PLAN,'flow':flow,'round':round_index,'memory':{}}
                r=ai.call(self.store,self.base.c,flow,'plan:'+str(round_index),p,lambda:None,plan)
                self.assertEqual(r['status'],'completed',r)
        p={'task':schema.PLAN,'flow':'AZIENDE','round':2,'memory':{}}
        r=ai.call(self.store,self.base.c,'AZIENDE','plan:2',p,lambda:None,plan)
        self.assertEqual(r['status'],'budget_exhausted')
        def original(p,cfg,check):
            check()
            return {'output':harness.response(p),'usage':{}}
        for flow in FLOWS:
            for i in range(4):
                p=harness.payload();p['flow']=flow;p['prior_question']=str(i)
                r=ai.call(self.store,self.base.c,flow,'page:'+flow+str(i),p,lambda:None,original)
                self.assertEqual(r['status'],'completed',r)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM commercial_ai_executions WHERE attempt=1').fetchone()[0],30)
        self.assertEqual(budget.remaining(self.store,self.base.c,'AZIENDE',cfg,'verify'),0)
