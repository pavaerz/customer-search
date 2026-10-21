"""Offline regression for campaign 43's persisted recovery-plan failure."""
import json
import unittest
from unittest.mock import patch

import test_agent6_campaign32 as support
from sales.agent6 import memory


class RecoveryOrigin(unittest.TestCase):
    setUp = support.Campaign32Fix.setUp
    tearDown = support.Campaign32Fix.tearDown

    def test_persisted_string_origin_recovers_once_without_inference(self):
        proposal = {**support.query(), 'origin': 'deterministic_recovery_after_observed_outcomes'}
        task = {'id': 43, 'strategy': 'AZIENDE', 'kind': 'agent_plan',
                'payload': {'round': 1}}
        memory.event(self.store, self.c, 'AZIENDE', 'plan', '43',
                     {'chosen': proposal, 'queries': [proposal]})
        with patch('sales.agent6.ai.call', side_effect=AssertionError('No new inference')):
            self.w.planning(task, lambda: None)
            self.w.planning(task, lambda: None)
        with self.store.connect() as c:
            tasks = c.execute("SELECT payload FROM research_tasks WHERE kind='search'").fetchall()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(json.loads(tasks[0][0])['origin']['kind'], proposal['origin'])
            self.assertEqual(c.execute("SELECT used FROM commercial_resources WHERE resource='queries'").fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0], 0)

    def test_dict_origin_preserves_strategy_metadata(self):
        origin = {'strategy_id': 'specific-project', 'language': 'it'}
        self.w.enqueue('search', 'AZIENDE', {**support.query(), 'origin': origin}, 'dict-origin')
        with self.store.connect() as c:
            payload = json.loads(c.execute("SELECT payload FROM research_tasks WHERE kind='search'").fetchone()[0])
        self.assertEqual(payload['origin'], origin)
        self.assertEqual(payload['strategy_id'], origin['strategy_id'])

    def test_failed_planning_isolated_without_new_loop(self):
        self.w.record_failure({'kind': 'agent_plan', 'strategy': 'AZIENDE'},
                              AttributeError("'str' object has no attribute 'get'"))
        self.w.tick()
        with self.store.connect() as c:
            self.assertEqual(c.execute("SELECT state FROM commercial_engine_runs WHERE engine='AZIENDE'").fetchone()[0], 'blocked')
            flows = {r[0] for r in c.execute("SELECT strategy FROM research_tasks WHERE kind='agent_plan'")}
        self.assertNotIn('AZIENDE', flows)
        self.assertEqual(flows, {'AGENCIES', 'STARTUPS'})
