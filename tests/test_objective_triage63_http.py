"""New-campaign opt-in at the real HTTP boundary; worker start is mocked."""
from unittest.mock import patch
import test_commercial44_http as base
from sales import server
import copy,json


class TriageHttp(base.RecommendationHttp44):
    def test_http_start_reaches_real_store_with_worker_only_stubbed(self):
        from test_agent6_campaign32 import FROZEN
        from sales.agent6.api import preview
        filters=copy.deepcopy(FROZEN['filters'])
        filters['commercial']['ai']['provider']='MOCK'
        for key in ('search_version','demand_version'):filters.pop(key,None)
        filters.update(deep_plan_token=preview(self.store,filters)['approval_token'],deep_authorized=True)
        with patch.object(server.CampaignManager,'launch',side_effect=lambda campaign:campaign) as launch:
            code,result=self.request('/api/campaigns',{'filters':filters,'target':50})
        self.assertEqual(code,200,result);launch.assert_called_once()
        with self.store.connect() as db:
            saved=json.loads(db.execute('SELECT filters FROM campaigns WHERE id=?',(result['id'],)).fetchone()[0])
            self.assertEqual(saved['discovery_triage_version'],1)
            self.assertEqual(saved['continuation_version'],1)
            self.assertEqual(saved['commercial']['ai']['max_calls_per_campaign'],filters['commercial']['ai']['max_calls_per_campaign'])
            db.execute("UPDATE campaigns SET status='paused' WHERE id=?",(result['id'],))

    def test_new_campaign_gets_triage_without_budget_changes(self):
        filters={'agent_version':'6.0','commercial_engines':['AGENCIES'],
                 'regions':['Veneto'],'mode':'extended','discovery_triage_version':0}
        with patch.object(server,'CampaignManager') as manager:
            manager.return_value.start.return_value={'id':999,'status':'running'}
            code,_=self.request('/api/campaigns',{'filters':filters,'target':50})
        self.assertEqual(code,200)
        forwarded=manager.return_value.start.call_args.args[0]
        self.assertEqual(forwarded,{**filters,'decision_engine':'ai_first_1','discovery_triage_version':1,'continuation_version':1})
        self.assertNotIn('commercial',forwarded)

    def test_resume_does_not_replace_historical_filters(self):
        with patch.object(server,'CampaignManager') as manager:
            manager.return_value.resume.return_value={'id':56,'status':'running'}
            code,_=self.request('/api/campaigns/56/resume',{})
        self.assertEqual(code,200)
        manager.return_value.resume.assert_called_once_with(56)
        manager.return_value.start.assert_not_called()
