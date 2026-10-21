"""Synthetic startup discovery → original → qualification, no paid transport."""
import copy,json,unittest
from unittest.mock import patch
import test_agent7_multiflow as support
from sales.agent6.api import preview
from sales.agent6 import schema
from sales.agent6.commercial_roles import engagement
from sales.commercial.coordinator import run_campaign


class StartupCycle(unittest.TestCase):
    def setUp(self):
        self.base=support.FiveFlowCycle();self.base.setUp();self.store=self.base.store;self.rs=self.base.rs
        self.rs.stop(self.base.c['id']);self.rs.paused(self.base.c['id'])
        f=copy.deepcopy(self.base.fixture.filters);f['commercial_engines']=['STARTUPS']
        f['deep_plan_token']=preview(self.store,f)['approval_token'];self.c=self.rs.create(f)
    def tearDown(self):self.base.tearDown()
    def run_case(self,terms,constraints=True):
        b=self.base;request='We are looking for a freelance frontend developer to build our complete web app. Remote from Italy.'
        b.requests['STARTUPS']=request
        lines=['Gamma Srl','Posted 2 days ago','We are a startup.',request,terms]
        if constraints:lines.append(b.constraints)
        url=b.urls['STARTUPS'];b.pages[url]=b.page(url,'Gamma Srl',lines)
        def model(p,cfg,check):
            result=b.model(p,cfg,check)
            if p['task']==schema.READ:
                for e in p['evidence']:
                    for s in e['segments']:
                        if e['original'] and s['text'] in terms:
                            result['output']['analyses'][0]['facts'].append({'field':'contract','ref':{'segment_id':s['segment_id']}})
            return result
        with patch('socket.create_connection',side_effect=AssertionError('Offline only')),patch('sales.agent6.ai.infer',side_effect=model),patch('sales.agent6.coordinator.acquire',side_effect=b.search),patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=b.read):
            run_campaign(self.store,self.c,lambda:None,lambda _:None)
        with self.store.connect() as c:
            records=[json.loads(r[0]) for r in c.execute('SELECT body FROM agent6_records WHERE campaign_id=?',(self.c['id'],))]
        return next(r for r in records if r['original'])
    def test_bounded_paid_mvp_can_reach_worklist_without_inventing_budget(self):
        b=self.run_case('Paid freelance contract.')
        self.assertEqual(b['state'],'VERIFIED',b['reason']);self.assertEqual(b['engagement']['status'],'PAID_CONTRACT')
        self.assertEqual(b['feasibility']['status'],'BOUNDED');self.assertEqual(b['budget']['kind'],'UNKNOWN')
    def test_equity_only_is_not_a_paid_commission_even_if_model_calls_it_demand(self):
        b=self.run_case('Equity-only compensation.')
        self.assertEqual(b['state'],'POTENTIAL');self.assertEqual(b['commercial_alignment']['arrangement'],'EQUITY_ONLY_OPPORTUNITY')
    def test_unpaid_contract_is_excluded(self):
        b=self.run_case('This is an unpaid contract.')
        self.assertEqual(b['state'],'REJECTED');self.assertEqual(b['engagement']['status'],'UNPAID')
    def test_cofounder_without_payment_terms_needs_clarification(self):
        b=self.run_case('The role is a technical cofounder.')
        self.assertEqual(b['state'],'POTENTIAL');self.assertEqual(b['commercial_alignment']['arrangement'],'TECHNICAL_COFOUNDER_OPPORTUNITY')
    def test_paid_and_equity_only_conflict_is_not_silently_resolved(self):
        b=self.run_case('Paid freelance contract. Equity-only compensation.')
        self.assertEqual(b['state'],'NEEDS_REVIEW');self.assertEqual(b['engagement']['status'],'CONTRADICTORY_TERMS')
    def test_paid_contract_with_optional_equity_remains_a_contract(self):
        b=self.run_case('Paid freelance contract with optional equity. This is not equity-only.')
        self.assertEqual(b['state'],'VERIFIED',b['reason']);self.assertEqual(b['engagement']['status'],'PAID_CONTRACT')
    def test_unknown_security_and_integrations_prevent_mvp_qualification(self):
        b=self.run_case('Paid freelance contract.',constraints=False)
        self.assertEqual(b['state'],'NEEDS_REVIEW');self.assertIn('feasibility',b['missing'])
    def test_snippet_and_funding_are_not_payment_evidence(self):
        for field,original in [('signal',True),('budget',True),('contract',False)]:
            result=engagement([{'field':field,'quote':'Paid contract; equity-only funding.','original':original,'url':'https://fixture.example'}])
            self.assertEqual(result['status'],'UNKNOWN')


if __name__=='__main__':unittest.main()
