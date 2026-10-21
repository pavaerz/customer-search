"""C45 saved queries/URLs + synthetic queue replay, never new paid work."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_ai_first as harness
from sales.agent6 import FLOWS, budget, memory, scheduling
from sales.agent6.discovery_intent import source_issue
from sales.agent6.query_pipeline import prepare
from sales.db import encode, now

SAVED=json.loads((Path(__file__).parent/'fixtures/ai_first/campaign45/discovery.json').read_text())


class QueryAndSources(unittest.TestCase):
    def test_six_real_queries_keep_terms_and_intent_but_remove_phrase_overconstraint(self):
        changed=[]
        for row in SAVED['executed_queries']:
            q={**harness.query(row['query']),**row}
            prepared,error=prepare(q,row['flow'],['Veneto'],ai_first=True)
            self.assertIsNone(error,(row['query'],error))
            self.assertEqual(prepared['query'].replace('"',''),row['query'].replace('"',''))
            if prepared['query']!=row['query']:changed.append(row['flow'])
            again,error=prepare(prepared,row['flow'],['Veneto'],ai_first=True)
            self.assertIsNone(error)
            self.assertEqual(again['query_validation'],prepared['query_validation'])
            self.assertNotIn('qualified',prepared['commercial_policy'])
        self.assertEqual(sorted(changed),['AGENCIES','AZIENDE','SOCIAL','STARTUPS'])

    def test_specific_subject_operators_exclusions_and_boolean_meaning_preserved(self):
        for text,extra in (
            ('"Alfa Srl" "collabora con noi" Veneto',{'selection':'verification'}),
            ('"Alfa Srl" "cerchiamo WordPress freelance" Veneto',{'expected_entity':'Alfa Srl'}),
            ('agenzia ("cerchiamo freelance" OR "collabora con noi") Veneto',{}),
            ('agenzia "cerchiamo freelance" Veneto -"tempo indeterminato"',{}),
        ):
            result,error=prepare({**harness.query(text),**extra},'AGENCIES',['Veneto'],ai_first=True)
            self.assertIsNone(error)
            self.assertEqual(result['query'],text)

    def test_old_campaign_queries_unchanged(self):
        q=harness.query('agenzia "cerchiamo" "sviluppatore freelance" Veneto')
        result,error=prepare(q,'AGENCIES',['Veneto'])
        self.assertIsNone(error)
        self.assertEqual(result['query'],q['query'])

    def test_real_collection_routes_filtered_without_banning_other_pages(self):
        excluded={r['id'] for r in SAVED['records'] if source_issue(r)}
        self.assertEqual(excluded,{1206,1207,1208})
        for url in ('https://www.agriturismo.it/lavora-con-noi/',
                    'https://www.visititaly.it/annunci/cerchiamo-frontend',
                    'https://www.cantine.wine/eventi/nuova-cantina',
                    'https://azienda.example/eventi'):
            self.assertIsNone(source_issue({'url':url}),url)


class FirstCycleReplay(unittest.TestCase):
    def setUp(self):
        self.base=harness.IntegratedPath();self.base.setUp()
        self.store,self.rs,self.c=self.base.store,self.base.rs,self.base.c
        self.c['filters']['commercial_engines']=list(FLOWS)
        # Real economic envelope; the provider is never invoked.
        self.cfg=copy.deepcopy(SAVED['limits'])
        self.c['filters']['commercial']['ai']=self.cfg
        with self.store.connect() as db:
            db.execute('UPDATE campaigns SET filters=? WHERE id=?',(encode(self.c['filters']),self.c['id']))
            for flow in FLOWS:
                db.execute("INSERT OR IGNORE INTO commercial_engine_runs(campaign_id,engine,state) VALUES (?,?,'running')",(self.c['id'],flow))
        self.guard=patch('socket.create_connection',side_effect=AssertionError('Offline'))
        self.guard.start()
        for flow in FLOWS:self.reserve(flow,'plan:0','plan')

    def tearDown(self):
        self.guard.stop();self.base.tearDown()

    def reserve(self,flow,key,stage='verify'):
        payload=({'task':'RESEARCH_PLAN_6','round':int(stage=='replan')} if stage in ('plan','replan') else
                 {'task':'COMMERCIAL_DECISION_1','evidence':[{'original':True}]})
        price=(self.cfg['max_input_tokens']*self.cfg['input_cost_per_million']+
               self.cfg['max_output_tokens']*self.cfg['output_cost_per_million'])/1e6
        ident,error,*_=budget.reserve(self.store,self.c,flow,key,payload,self.cfg,
                                     flow+key,price,100)
        if ident:
            with self.store.connect() as db:db.execute("UPDATE commercial_ai_executions SET status='completed' WHERE id=?",(ident,))
        self.assertIsNone(error,(flow,key,error))
        return ident

    def add(self,kind,flow,payload,key):
        self.rs.enqueue(self.c['id'],kind,flow,payload,key)
        with self.store.connect() as db:
            return db.execute('SELECT id FROM research_tasks WHERE fingerprint=?',(key,)).fetchone()[0]

    def zero(self,flow):
        row=next(q for q in SAVED['executed_queries'] if q['flow']==flow and q['results']==0)
        memory.event(self.store,self.c,flow,'query',flow,{**row,'campaign_id':45})

    def choose(self):
        with self.store.connect() as db:return scheduling.choose(db,self.c,now())

    def test_empty_flow_can_replan_before_fourteen_unread_candidates(self):
        for flow in ('AZIENDE','NEWS'):
            for i in range(7):self.add('candidate',flow,{'url':f'https://{flow.lower()}{i}.example/'},flow+str(i))
        self.zero('AGENCIES')
        pid=self.add('agent_plan','AGENCIES',{'round':1},'recover-agencies')
        with self.store.connect() as db:
            self.assertIsNone(scheduling.planning_hold(db,self.c,'AGENCIES',now()))
        selected,reason=self.choose()
        self.assertEqual(selected,pid)
        self.assertTrue(reason['first_cycle_discovery_turn'])
        self.reserve('AGENCIES','plan:1','replan')

    def test_saved_original_keeps_precedence_over_recovery(self):
        self.zero('SOCIAL')
        self.add('search','SOCIAL',{'query':'saved proposal'},'social')
        pid=self.add('candidate','NEWS',{'url':'https://original.example/',
                'original_page':{'url':'https://original.example/'}},'saved')
        self.assertEqual(self.choose()[0],pid)

    def test_last_slot_finishes_saved_original_not_a_new_search(self):
        self.cfg['max_calls_per_campaign']=6  # five initial plans already used
        self.zero('SOCIAL')
        self.add('search','SOCIAL',{'query':'saved proposal'},'social')
        pid=self.add('candidate','NEWS',{'url':'https://original.example/',
                'original_page':{'url':'https://original.example/'}},'saved')
        selected,reason=self.choose()
        self.assertEqual(selected,pid)
        self.assertEqual(reason['ai_capacity'],1)
        self.assertEqual(budget.remaining(self.store,self.c,'SOCIAL',self.cfg,'replan'),0)

    def test_concurrent_reservations_still_obey_hard_cap(self):
        from concurrent.futures import ThreadPoolExecutor
        cfg={**self.cfg,'max_calls_per_campaign':8,'max_concurrent_requests':4}
        payload={'task':'COMMERCIAL_DECISION_1','evidence':[{'original':True}]}
        def attempt(i):
            return budget.reserve(self.store,self.c,list(FLOWS)[i%5],f'page:race:{i}',
                payload,cfg,f'race:{i}',.08192,100)[0]
        with ThreadPoolExecutor(max_workers=4) as pool:result=list(pool.map(attempt,range(20)))
        self.assertLessEqual(sum(x is not None for x in result),3)
        with self.store.connect() as db:
            self.assertLessEqual(db.execute('SELECT count(*) FROM commercial_ai_executions WHERE attempt=1').fetchone()[0],8)

    def test_recovery_priority_ends_after_two_receipts(self):
        self.zero('SOCIAL')
        memory.event(self.store,self.c,'SOCIAL','query','second',{'query':'second','results':0})
        self.add('search','SOCIAL',{'query':'third'},'third')
        pid=self.add('candidate','NEWS',{'url':'https://original.example/'},'read')
        self.assertEqual(self.choose()[0],pid)

    def test_two_empty_queries_release_unused_first_cycle_slots(self):
        for flow in ('AGENCIES','SOCIAL','STARTUPS'):
            self.zero(flow)
            memory.event(self.store,self.c,flow,'query','second',{'query':'second','results':0})
        for i in range(7):
            for flow in ('AZIENDE','NEWS'):self.reserve(flow,f'page:{flow}:{i}')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions WHERE attempt=1').fetchone()[0],19)
        # Each populated flow is at its unchanged eight-call maximum.
        self.assertEqual(budget.remaining(self.store,self.c,'AZIENDE',self.cfg,'verify'),0)
        self.assertGreater(budget.remaining(self.store,self.c,'SOCIAL',self.cfg,'verify'),0)

    def test_twenty_slot_competing_queue_replay_preserves_three_empty_flows(self):
        # C45 shape, not fake results: two populated queues, three empty queries.
        for flow in ('AZIENDE','NEWS'):
            for i in range(7):self.add('candidate',flow,{'url':f'https://{flow.lower()}{i}.example/'},flow+str(i))
        for flow in ('AGENCIES','SOCIAL','STARTUPS'):
            self.zero(flow)
            self.add('search',flow,{'query':'previously generated alternative'},'recover'+flow)
        for i in range(4):
            for flow in ('AZIENDE','NEWS'):self.reserve(flow,f'page:{flow}:{i}')
        # 13 calls consumed. Queue length must not erase the other flows' starts.
        for flow in ('AGENCIES','SOCIAL','STARTUPS'):
            self.assertGreater(budget.remaining(self.store,self.c,flow,self.cfg,'verify'),0,flow)
            self.reserve(flow,f'page:recovered:{flow}:1')
            self.reserve(flow,f'page:recovered:{flow}:2')
        self.reserve('AZIENDE','page:last')
        self.assertEqual(budget.remaining(self.store,self.c,'NEWS',self.cfg,'verify'),0)
        with self.store.connect() as db:
            rows=db.execute('SELECT engine,count(*) n,sum(reserved_cost) cost FROM commercial_ai_executions WHERE attempt=1 GROUP BY engine').fetchall()
        self.assertEqual(sum(r['n'] for r in rows),20)
        self.assertLessEqual(sum(r['cost'] for r in rows),1.65)
        self.assertTrue(all(r['n']>=3 for r in rows))

    def test_coordinator_reuses_three_saved_alternatives_before_new_page_backlog(self):
        from sales.agent6.coordinator import AgentCoordinator
        for flow in FLOWS:
            tid=self.add('agent_plan',flow,{'round':0},'initial'+flow)
            self.rs.task_done(tid)
        for flow in ('AZIENDE','NEWS'):
            for i in range(7):self.add('candidate',flow,{'url':f'https://{flow.lower()}{i}.example/'},flow+str(i))
        alternatives={
            'AGENCIES':'agenzia collabora con noi frontend Lombardia',
            'SOCIAL':'site:instagram.com cerchiamo sviluppatore freelance Veneto',
            'STARTUPS':'startup cerchiamo sviluppatore freelance Veneto',
        }
        for flow,text in alternatives.items():
            self.zero(flow)
            memory.event(self.store,self.c,flow,'plan','initial'+flow,
                         {'chosen':{'query':'initial'},'queries':[harness.query(text)]})
        worker=AgentCoordinator(self.store,self.c);worker.initialize()
        seen=[]
        with patch.object(worker,'model',side_effect=AssertionError('Reuse requires no paid planning')),patch(
                'sales.agent6.research.acquire',return_value=[]) as search:
            for _ in range(6):
                worker.tick()
                task=self.rs.claim(self.c['id'],self.c['generation'])
                self.assertIn(task['kind'],('agent_plan','search'))
                self.assertIn(task['strategy'],alternatives)
                self.assertIsNone(worker.execute(task,lambda:None))
                self.rs.task_done(task['id'])
                if task['kind']=='search':seen.append(task['strategy'])
        self.assertEqual(set(seen),set(alternatives))
        self.assertEqual(search.call_count,3)
        self.assertEqual(self.rs.claim(self.c['id'],self.c['generation'])['kind'],'candidate')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions WHERE attempt=1').fetchone()[0],5)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())

    def test_real_urls_excluded_before_candidate_queue_without_negative_company_records(self):
        from sales.agent6.coordinator import AgentCoordinator
        worker=AgentCoordinator(self.store,self.c);worker.initialize()
        for flow in ('AZIENDE','NEWS'):
            row=next(q for q in SAVED['executed_queries'] if q['flow']==flow and q['results']==7)
            q={**harness.query(row['query']),**row}
            tid=self.add('search',flow,q,'replay-sources'+flow)
            task={'id':tid,'kind':'search','strategy':flow,'payload':q}
            urls=[{'url':r['url'],'title':r.get('entity') or ''} for r in SAVED['records'] if r['flow']==flow]
            with patch('sales.agent6.research.acquire',return_value=urls):
                worker.execute(task,lambda:None)
            self.rs.task_done(tid)
        with self.store.connect() as db:
            records=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
            self.assertEqual(len(records),11)
            self.assertTrue(all(r['state']=='DISCOVERED' for r in records))
            self.assertEqual(db.execute("SELECT count(*) FROM research_tasks WHERE kind='candidate'").fetchone()[0],11)
            receipts=[json.loads(r[0]) for r in db.execute("SELECT body FROM agent6_memory WHERE kind='query'")]
        self.assertEqual(sum(len(r['policy_rejections']) for r in receipts),3)

    def test_dispatch_receipt_records_actual_query_and_original_expression(self):
        from sales.agent6.coordinator import AgentCoordinator
        worker=AgentCoordinator(self.store,self.c);worker.initialize()
        text='agenzia "cerchiamo" "sviluppatore freelance" Veneto'
        q=harness.query(text);tid=self.add('search','AGENCIES',q,'old-plan')
        with patch('sales.agent6.research.acquire',return_value=[]) as search:
            worker.execute({'id':tid,'kind':'search','strategy':'AGENCIES','payload':q},lambda:None)
        sent=search.call_args.args[1]['query']
        self.assertNotEqual(sent,text)
        with self.store.connect() as db:
            receipt=json.loads(db.execute("SELECT body FROM agent6_memory WHERE kind='query'").fetchone()[0])
        self.assertEqual(receipt['query'],sent)
        self.assertEqual(receipt['query_validation']['original_query'],text)

    def test_stop_resume_preserves_turn_without_repeated_charges(self):
        self.zero('SOCIAL')
        self.add('search','SOCIAL',{'query':'saved proposal'},'social')
        self.add('candidate','NEWS',{'url':'https://original.example/'},'read')
        old=self.c['generation'];self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.assertIsNone(self.rs.claim(self.c['id'],old))
        self.c=self.rs.resume(self.c['id'])
        self.assertIsNone(self.rs.claim(self.c['id'],old))
        task=self.rs.claim(self.c['id'],self.c['generation'])
        self.assertEqual(task['strategy'],'SOCIAL')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions WHERE attempt=1').fetchone()[0],5)

