"""Offline dispatch regressions. Synthetic tasks are not real opportunities."""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_agent6_campaign32 as support
from sales.agent6 import budget, memory, scheduling
from sales.db import now


class CompletionFirst(unittest.TestCase):
    def setUp(self):
        self.base = support.Campaign32Fix()
        self.base.setUp()
        self.store, self.rs, self.c, self.w = (
            self.base.store, self.base.rs, self.base.c, self.base.w)
        self.network = patch('socket.create_connection', side_effect=AssertionError('Offline only'))
        self.network.start()

    def tearDown(self):
        self.network.stop()
        self.base.tearDown()

    def add(self, kind, flow, payload=None, key=None):
        self.rs.enqueue(self.c['id'], kind, flow, payload or {}, key)

    def claim(self):
        return self.rs.claim(self.c['id'], self.c['generation'])

    def candidate(self, flow='AGENCIES', key='original'):
        self.add('candidate', flow, {'url': 'https://synthetic.example/careers',
            'prior': {'facts': [{'field': 'request', 'quote': 'Cerchiamo freelance WordPress'}],
                      'missing': ['entity', 'publication']}}, key)

    def test_original_precedes_replan_search_and_screen(self):
        self.add('agent_plan', 'AZIENDE', {'round': 4})
        self.add('search', 'STARTUPS', {'query': 'synthetic'})
        self.add('agent_screen', 'AZIENDE', {'batch': []})
        self.candidate()
        task = self.claim()
        self.assertEqual((task['kind'], task['strategy']), ('candidate', 'AGENCIES'))
        with self.store.connect() as c:
            trace = json.loads(c.execute("SELECT details FROM research_events WHERE kind='agent_schedule'").fetchone()[0])
        self.assertEqual(trace['stage'], 'verify')
        self.assertEqual(trace['missing'], ['entity', 'publication'])
        self.assertIsNone(trace['sales_probability'])

    def test_query_to_resolve_existing_buyer_precedes_general_discovery(self):
        self.add('search', 'AZIENDE', {'query': 'discovery'})
        self.add('search', 'AGENCIES', {'query': 'official original', 'selection': 'verification'})
        self.assertEqual(self.claim()['strategy'], 'AGENCIES')

    def test_existing_original_holds_replanning_but_not_initial_flow(self):
        self.candidate()
        self.w.tick()
        with self.store.connect() as c:
            self.assertEqual({r[0] for r in c.execute("SELECT strategy FROM research_tasks WHERE kind='agent_plan'")}, {'AZIENDE', 'STARTUPS'})
            cfg=self.c['filters']['commercial']['ai']
            self.assertEqual(budget.available(c,self.c,'AZIENDE',cfg,'replan',[]),0)
            self.assertGreater(budget.available(c,self.c,'AZIENDE',cfg,'plan',[]),0)
        with patch.object(self.w,'model',side_effect=AssertionError('No planning inference')):
            result=self.w.planning({'id':999,'strategy':'AZIENDE','payload':{'round':1}},lambda:None)
        self.assertEqual(result, {'deferred_resource':'ai_replan'})

    def test_delayed_or_failed_original_does_not_deadlock_other_flows(self):
        self.candidate()
        with self.store.connect() as c:
            c.execute("UPDATE research_tasks SET available_at='2999-01-01' WHERE kind='candidate'")
            self.assertIsNone(scheduling.planning_hold(c,self.c,'AZIENDE',now()))
            c.execute("UPDATE research_tasks SET state='failed',available_at=? WHERE kind='candidate'",(now(),))
            self.assertIsNone(scheduling.planning_hold(c,self.c,'AZIENDE',now()))

    def test_three_unproductive_plans_stop_only_that_flow(self):
        self.add('agent_plan','AZIENDE',{'round':0})
        with self.store.connect() as c:c.execute("UPDATE research_tasks SET state='done'")
        for n in range(3):
            memory.event(self.store,self.c,'AZIENDE','plan',str(n),
                         {'chosen':None,'queries':[],'rejected_queries':[{'reason':'generic_web_topic'}]})
        self.w.tick()
        with self.store.connect() as c:
            state=c.execute("SELECT state FROM commercial_engine_runs WHERE engine='AZIENDE'").fetchone()[0]
            plans=[r[0] for r in c.execute("SELECT strategy FROM research_tasks WHERE kind='agent_plan' AND state='pending'")]
        self.assertEqual(state,'exhausted')
        self.assertEqual(set(plans),{'AGENCIES','STARTUPS'})

    def test_technical_failures_are_not_unproductive_commercial_samples(self):
        for n in range(6):
            memory.event(self.store,self.c,'AZIENDE','model',str(n),{'status':'timeout'})
        with self.store.connect() as c:self.assertIsNone(scheduling.planning_hold(c,self.c,'AZIENDE',now()))

    def test_equal_stage_rotates_flows_and_atomic_claim_never_duplicates(self):
        self.candidate('AZIENDE','a1');self.candidate('AZIENDE','a2');self.candidate('AGENCIES','b1')
        first=self.claim()
        self.assertEqual(first['strategy'],'AZIENDE')
        with ThreadPoolExecutor(max_workers=2) as pool:
            rest=list(pool.map(lambda _:self.claim(),range(2)))
        self.assertEqual(len({first['id'],*(t['id'] for t in rest)}),3)
        # Dispatch of the less-covered channel is traced before the second A.
        with self.store.connect() as c:
            order=[json.loads(r[0])['flow'] for r in c.execute("SELECT details FROM research_events WHERE kind='agent_schedule' ORDER BY id")]
        self.assertEqual(order,['AZIENDE','AGENCIES','AZIENDE'])

    def test_stop_resume_preserves_pending_original_and_generation_guard(self):
        self.candidate();old=self.c['generation']
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.assertIsNone(self.claim())
        self.c=self.rs.resume(self.c['id'])
        self.assertIsNone(self.rs.claim(self.c['id'],old))
        self.assertEqual(self.claim()['kind'],'candidate')

    def test_final_shared_slot_goes_to_original_not_replan(self):
        cfg={**self.c['filters']['commercial']['ai'],'max_calls_per_campaign':1}
        self.candidate()
        with self.store.connect() as c:
            self.assertEqual(budget.available(c,self.c,'AZIENDE',cfg,'replan',[]),0)
            self.assertEqual(budget.available(c,self.c,'AGENCIES',cfg,'verify',[]),1)

    def test_terminal_summary_does_not_leave_running_flow(self):
        self.candidate()
        with self.store.connect() as c:
            c.execute("UPDATE research_tasks SET state='budget',error='ai_verify'")
            c.execute("UPDATE commercial_engine_runs SET state='running'")
        self.w.terminal_state()
        with self.store.connect() as c:
            states=dict(c.execute('SELECT engine,state FROM commercial_engine_runs').fetchall())
        self.assertEqual(states['AGENCIES'],'budget_reached')
        self.assertNotIn('running',states.values())


if __name__=='__main__':unittest.main()
