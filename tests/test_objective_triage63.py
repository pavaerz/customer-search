"""C56 saved SERPs; model outputs here are synthetic, not quality measurements."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from sales.agent6 import ai, budget, schema
from sales.agent6.discovery_triage import TASK, payload, validate
from sales.db import encode
import test_ai_first as h

SAVED = json.loads((Path(__file__).parent/'fixtures/ai_first/triage63/campaign56-serps.json').read_text())
AGENCY = next(g for g in SAVED if g['flow']=='AGENCIES')


def output(p, action='HOLD', role='TEMPLATE'):
    return {'items':[{'id':i['id'], 'action':action, 'role':role,
                     'quote':i['title'], 'reason':'Synthetic routing decision for offline contracts.'}
                    for i in p['items']]}


class Contract(unittest.TestCase):
    def test_saved_paid_responses_keep_real_invitation_sources_and_operator(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/ai_first/triage63/probe-responses.json').read_text())
        seen={};errors=[]
        for row in fixture:
            clean,issues=validate(row['raw_response'],row['payload']);errors.extend(issues)
            by_id={i['id']:i for i in row['payload']['items']}
            for choice in clean['items']:seen[by_id[choice['id']]['url']]=choice['action']
        for url in ('https://www.jampaa.it/lavora-con-noi/','https://www.adviva.it/job/',
                    'https://www.marinocacciatori.it/it/',
                    'https://www.idrobasegroup.com/it/itm-italia-entra-in-idrobase-group'):
            self.assertEqual(seen[url],'READ')
        self.assertEqual(seen['https://www.developerway.it/developers-freelance'],'UNKNOWN')
        self.assertEqual(seen['https://tinyurl.com/'],'HOLD')
        self.assertEqual(seen['https://www.moduli.it/contratto-a-progetto-esempio-9076'],'HOLD')
        self.assertEqual([e['code'] for e in errors],['possible_external_network_requires_original'])

    def test_actual_templates_are_routable_without_a_company_decision(self):
        p=payload(AGENCY['items'],h.query(AGENCY['query']),'AGENCIES')
        clean,errors=validate(output(p),p)
        self.assertEqual(errors,[]);self.assertEqual(len(clean['items']),7)
        self.assertNotIn('decision',clean)

    def test_foreign_or_duplicate_identity_invalidates_envelope(self):
        p=payload(AGENCY['items'],{},'AGENCIES')
        for mutate in ('foreign','duplicate'):
            o=output(p)
            o['items'][1]['id']='not-offered' if mutate=='foreign' else o['items'][0]['id']
            with self.assertRaisesRegex(ValueError,'wrong_triage_source'):validate(o,p)

    def test_cross_source_quote_and_missing_items_do_not_lose_candidates(self):
        p=payload(AGENCY['items'],{},'AGENCIES');o=output(p)
        o['items'][0]['quote']=p['items'][2]['description']
        o['items'].pop()
        clean,errors=validate(o,p)
        self.assertEqual(len(clean['items']),len(p['items']))
        self.assertEqual(sum(x['action']=='UNKNOWN' for x in clean['items']),2)
        self.assertEqual(len(errors),2)

    def test_invitation_and_operating_company_cannot_be_held_as_such(self):
        items=[{'url':'https://agency.example/collabora','title':'Collaboratori WordPress freelance',
                'content':'Accettiamo collaboratori esterni anche per progetti futuri.'},
               {'url':'https://boats.example/','title':'Navigazione Alfa a Porto Tolle',
                'content':'Escursioni su misura per aziende e famiglie.'}]
        p=payload(items,{},'AGENCIES')
        for role in ('POSSIBLE_INVITATION','OPERATING_COMPANY','UNKNOWN'):
            clean,errors=validate(output(p,'HOLD',role),p)
            self.assertEqual([x['action'] for x in clean['items']],['UNKNOWN','UNKNOWN'])
        self.assertEqual(validate(output(p,'READ','POSSIBLE_INVITATION'),p)[1],[])

    def test_provider_contract_and_prompt_keep_metadata_unverified(self):
        from sales.commercial.ai_tasks import schema_for,system_for
        p=payload(AGENCY['items'],{},'AGENCIES')
        self.assertEqual(schema_for(TASK)['required'],['items'])
        self.assertIn('not',system_for(TASK).lower())
        self.assertIn('original',system_for(TASK))
        self.assertEqual(schema.validate_response(output(p),p),validate(output(p),p))

    def test_short_full_title_is_attributed_but_tiny_description_fragment_is_not(self):
        p=payload([{'url':'https://example.test/bandi','title':'Bandi','content':'Bandi di sostegno alle imprese.'}],{},'NEWS')
        self.assertEqual(validate(output(p,'HOLD','INFORMATIONAL'),p)[1],[])
        o=output(p);o['items'][0]['quote']='di'
        self.assertEqual(validate(o,p)[0]['items'][0]['action'],'UNKNOWN')

    def test_invited_freelance_network_is_uncertain_not_held_as_a_directory(self):
        p=payload([{'url':'https://network.example/developers','title':'Developer freelance',
                    'content':'Entra gratuitamente nel network e ricevi progetti full remote.'}],{},'AGENCIES')
        clean,errors=validate(output(p,'HOLD','COLLECTION'),p)
        self.assertEqual(clean['items'][0]['action'],'UNKNOWN')
        self.assertEqual(errors[0]['code'],'possible_external_network_requires_original')


class Integration(unittest.TestCase):
    def setUp(self):
        self.b=h.IntegratedPath();self.b.setUp();self.addCleanup(self.b.tearDown)
        self.b.c['filters']['discovery_triage_version']=1
        with self.b.store.connect() as db:
            db.execute('UPDATE campaigns SET filters=? WHERE id=?',(encode(self.b.c['filters']),self.b.c['id']))
        self.b.w.campaign=self.b.c

    def task(self, key='triage-test', query=None):
        self.b.w.enqueue('search','AGENCIES',h.query(query or AGENCY['query']),key)
        with self.b.store.connect() as db:
            row=db.execute('SELECT * FROM research_tasks WHERE fingerprint=?',(key,)).fetchone()
        return {**dict(row),'payload':json.loads(row['payload'])}

    def test_creation_persists_new_version_and_preserves_budgets_and_history(self):
        filters=copy.deepcopy(self.b.filters)
        filters.update(decision_engine='ai_first_1',discovery_triage_version=1)
        with self.b.store.connect() as db:
            before=list(map(tuple,db.execute('SELECT * FROM campaigns ORDER BY id')))
            db.execute("UPDATE campaigns SET status='paused' WHERE id=?",(self.b.c['id'],))
        created=self.b.rs.create(filters)
        self.assertEqual(created['filters']['discovery_triage_version'],1)
        self.assertEqual(created['filters']['commercial']['ai'],self.b.c['filters']['commercial']['ai'])
        with self.b.store.connect() as db:
            saved=json.loads(db.execute('SELECT filters FROM campaigns WHERE id=?',(created['id'],)).fetchone()[0])
            self.assertEqual(saved['discovery_triage_version'],1)
            self.assertEqual(json.loads(db.execute('SELECT filters FROM campaigns WHERE id=?',(self.b.c['id'],)).fetchone()[0]),self.b.c['filters'])

    def test_invalid_triage_versions_cannot_be_saved(self):
        filters={**self.b.filters,'decision_engine':'ai_first_1'}
        for version in (True,0,2,'1',None):
            with self.assertRaisesRegex(ValueError,'Versione selezione fonti'):
                self.b.rs.create({**filters,'discovery_triage_version':version})
        with self.assertRaisesRegex(ValueError,'Versione selezione fonti'):
            self.b.rs.create({**self.b.filters,'discovery_triage_version':1})

    def test_changed_triage_contract_does_not_reuse_old_cache_or_exceed_flow_limit(self):
        from sales.agent6 import discovery_triage
        p=payload(AGENCY['items'],{},'AGENCIES')
        with patch('sales.agent6.ai.infer',side_effect=lambda p,c,g:{'output':output(p),'usage':{}}) as infer:
            first=ai.call(self.b.store,self.b.c,'AGENCIES','discovery-triage:cache',p,lambda:None)
            self.assertEqual(first['status'],'completed')
            with patch.object(discovery_triage,'SYSTEM',discovery_triage.SYSTEM+' Changed contract for offline test.'):
                second=ai.call(self.b.store,self.b.c,'AGENCIES','discovery-triage:cache',p,lambda:None)
            self.assertEqual(second['status'],'budget_exhausted')
            self.assertEqual(infer.call_count,1)

    def test_actual_serp_held_one_call_replay_no_search_no_company_rejections(self):
        task=self.task()
        with patch('sales.agent6.research.acquire',return_value=AGENCY['items']) as fetch,patch(
                'sales.agent6.ai.infer',side_effect=lambda p,c,g:{'output':output(p),'usage':{}}) as infer:
            self.b.w.execute(task,lambda:None)
            with self.b.store.connect() as db:
                task['payload']=json.loads(db.execute('SELECT payload FROM research_tasks WHERE id=?',(task['id'],)).fetchone()[0])
                self.assertEqual(db.execute("SELECT count(*) FROM research_tasks WHERE kind='candidate'").fetchone()[0],0)
                self.assertEqual(db.execute('SELECT count(*) FROM agent6_records').fetchone()[0],0)
                self.assertEqual(db.execute("SELECT count(*) FROM agent6_memory WHERE kind='plan_feedback'").fetchone()[0],1)
            self.b.w.execute(task,lambda:None)
        self.assertEqual(fetch.call_count,1);self.assertEqual(infer.call_count,1)
        self.assertEqual(budget.remaining(self.b.store,self.b.c,'AGENCIES',self.b.cfg,'screen'),0)
        self.assertGreater(budget.remaining(self.b.store,self.b.c,'AGENCIES',self.b.cfg,'verify'),0)

    def test_failed_triage_falls_back_to_originals_not_negative_decisions(self):
        task=self.task()
        with patch('sales.agent6.research.acquire',return_value=AGENCY['items']),patch(
                'sales.agent6.ai.infer',return_value={'output':{'items':[{'id':'foreign'}]},'usage':{}}):
            self.b.w.execute(task,lambda:None)
        with self.b.store.connect() as db:
            self.assertGreater(db.execute("SELECT count(*) FROM research_tasks WHERE kind='candidate'").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM agent6_records WHERE state='REJECTED'").fetchone()[0],0)

    def test_read_priority_and_unknown_preserve_independent_sources(self):
        task=self.task();items=copy.deepcopy(AGENCY['items'][:3])
        items[1]={'url':'https://agency.example/jobs','title':'Sviluppatore frontend freelance',
                  'content':'Cerchiamo collaboratori per siti completi. Inviaci il portfolio.'}
        def provider(p,c,g):
            o=output(p);o['items'][1].update(action='READ',role='POSSIBLE_INVITATION')
            o['items'][2].update(action='UNKNOWN',role='UNKNOWN',quote='')
            return {'output':o,'usage':{}}
        with patch('sales.agent6.research.acquire',return_value=items),patch('sales.agent6.ai.infer',side_effect=provider):
            self.b.w.execute(task,lambda:None)
        with self.b.store.connect() as db:
            rows=[json.loads(r[0]) for r in db.execute("SELECT payload FROM research_tasks WHERE kind='candidate'")]
            self.assertEqual(len(rows),2)
            self.assertEqual(next(r for r in rows if 'agency.example' in r['url'])['discovery_priority']['value'],4)
            self.assertEqual(db.execute("SELECT count(*) FROM agent6_records WHERE state IN ('VERIFIED','POTENTIAL','REJECTED')").fetchone()[0],0)

    def test_no_capacity_does_not_add_call_or_block_original_path(self):
        self.b.cfg['max_calls_per_campaign']=1
        task=self.task()
        with patch('sales.agent6.research.acquire',return_value=AGENCY['items']),patch(
                'sales.agent6.ai.infer',side_effect=AssertionError('No funded screening')):
            self.b.w.execute(task,lambda:None)
        with self.b.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions WHERE attempt=1').fetchone()[0],0)

    def test_each_flow_keeps_first_read_with_shared_twenty_call_ceiling(self):
        flows=['AZIENDE','AGENCIES','SOCIAL','STARTUPS','NEWS']
        self.b.c['filters']['commercial_engines']=flows
        self.b.cfg.update(max_calls_per_campaign=20,max_calls_per_engine=8)
        self.b.w.engines=flows;self.b.w.initialize()
        for flow in flows:
            p=payload(AGENCY['items'],{},flow)
            result=ai.call(self.b.store,self.b.c,flow,'discovery-triage:1',p,lambda:None,
                           lambda p,c,g:{'output':output(p),'usage':{}})
            self.assertEqual(result['status'],'completed',result)
            self.assertEqual(budget.remaining(self.b.store,self.b.c,flow,self.b.cfg,'screen'),0)
            self.assertGreater(budget.remaining(self.b.store,self.b.c,flow,self.b.cfg,'verify'),0)
        with self.b.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions WHERE attempt=1').fetchone()[0],5)

    def test_stop_after_saved_batch_reuses_serper_on_resume(self):
        task=self.task()
        with patch('sales.agent6.research.acquire',return_value=AGENCY['items']) as fetch,patch(
                'sales.agent6.discovery_triage.assess',side_effect=InterruptedError('Stopped')):
            with self.assertRaises(InterruptedError):
                # Direct handler keeps the interruption observable to the test.
                from sales.agent6.research import search
                search(self.b.w,task,lambda:None)
        with self.b.store.connect() as db:
            task['payload']=json.loads(db.execute('SELECT payload FROM research_tasks WHERE id=?',(task['id'],)).fetchone()[0])
        with patch('sales.agent6.research.acquire',side_effect=AssertionError('No repeat Serper')),patch(
                'sales.agent6.ai.infer',side_effect=lambda p,c,g:{'output':output(p),'usage':{}}):
            self.b.w.execute(task,lambda:None)
        self.assertEqual(fetch.call_count,1)

    def test_held_batch_uses_saved_alternative_without_new_planning_call(self):
        from sales.agent6 import memory
        task=self.task()
        alternative=h.query('"collabora con noi" sviluppatore freelance')
        memory.event(self.b.store,self.b.c,'AGENCIES','plan','prior-plan',
                     {'queries':[h.query(AGENCY['query']),alternative]})
        with patch('sales.agent6.research.acquire',return_value=AGENCY['items']),patch(
                'sales.agent6.ai.infer',side_effect=lambda p,c,g:{'output':output(p),'usage':{}}) as infer:
            self.b.w.execute(task,lambda:None)
            with self.b.store.connect() as db:
                db.execute("UPDATE research_tasks SET state='done' WHERE id=?",(task['id'],))
            self.b.w.planning({'id':6301,'strategy':'AGENCIES','payload':{'round':1}},lambda:None)
        self.assertEqual(infer.call_count,1)
        with self.b.store.connect() as db:
            queries=[json.loads(r[0])['query'] for r in db.execute("SELECT payload FROM research_tasks WHERE kind='search'")]
            self.assertIn(alternative['query'],queries)

    def test_stopped_campaign_cannot_make_a_triage_call_or_admit_sources(self):
        task=self.task()
        with self.b.store.connect() as db:
            db.execute("UPDATE campaigns SET status='paused' WHERE id=?",(self.b.c['id'],))
        from sales.agent6.research import search
        with patch('sales.agent6.research.acquire',return_value=AGENCY['items']),patch(
                'sales.agent6.ai.infer',side_effect=AssertionError('No AI after Stop')):
            with self.assertRaises(InterruptedError):search(self.b.w,task,lambda:None)
        with self.b.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM research_tasks WHERE kind='candidate'").fetchone()[0],0)
