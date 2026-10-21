"""Conservative Sol reservations, temporary database, no inference or transport."""
import copy
import unittest

import test_agent6_campaign32 as support
from scripts.run_objective_validation_sol import SOL_CONFIG
from sales.agent6 import FLOWS,budget
from sales.agent6.api import preview
from sales.commercial.ai import validate_config


class SolFiveFlowCapacity(unittest.TestCase):
    def test_twenty_slots_cover_five_starts_and_originals_without_raising_limits(self):
        base=support.Campaign32Fix();base.setUp()
        try:
            base.rs.stop(base.c['id']);base.rs.paused(base.c['id'])
            base.store.configure({'provider':'serper'})
            cfg=validate_config({**SOL_CONFIG,'max_calls_per_campaign':20,
                                 'max_calls_per_engine':8,'max_calls_per_candidate':2})
            filters=copy.deepcopy(base.filters)
            filters.update(agent_version='6.0',decision_engine='ai_first_1',
                           commercial_engines=list(FLOWS),commercial={'ai':cfg})
            filters['work_budget'].update(max_provider_requests=8,max_serper_credits=8,max_queries_per_engine=8)
            proposed=preview(base.store,filters)
            self.assertEqual(proposed['max_serper_requests'],40)
            filters['deep_plan_token']=proposed['approval_token']
            campaign=base.rs.create(filters)
            per_call=(cfg['max_input_tokens']*cfg['input_cost_per_million']+
                      cfg['max_output_tokens']*cfg['output_cost_per_million'])/1e6
            self.assertLessEqual(per_call*20,cfg['max_estimated_cost'])
            used=[]
            for round in range(4):
                for flow in FLOWS:
                    payload=(support.plan_payload(flow) if round==0 else
                             {'task':'COMMERCIAL_DECISION_1','evidence':[{'original':True}]})
                    ident,error,*_=budget.reserve(base.store,campaign,flow,
                        'plan:0' if round==0 else f'page:{flow}:{round}',payload,cfg,
                        f'capacity:{flow}:{round}',per_call,cfg['max_input_tokens'])
                    self.assertIsNone(error,(flow,round,error))
                    self.assertIsNotNone(ident)
                    used.append(ident)
                    with base.store.connect() as c:
                        c.execute("UPDATE commercial_ai_executions SET status='completed' WHERE id=?",(ident,))
            self.assertEqual(len(used),20)
            ident,error,*_=budget.reserve(base.store,campaign,'AGENCIES','page:extra',
                {'task':'COMMERCIAL_DECISION_1','evidence':[{'original':True}]},cfg,
                'extra',per_call,cfg['max_input_tokens'])
            self.assertIsNone(ident)
            self.assertIsNotNone(error)
            with base.store.connect() as c:
                count,total=c.execute('SELECT count(*),sum(reserved_cost) FROM commercial_ai_executions WHERE campaign_id=?',
                                      (campaign['id'],)).fetchone()
            self.assertEqual(count,20)
            self.assertAlmostEqual(total,1.6384)
            self.assertEqual(campaign['filters']['commercial']['ai'],cfg)
        finally:
            base.tearDown()
