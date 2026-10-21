"""Synthetic five-flow queue/load test using campaign 41's configured maxima.

All provider responses and companies are synthetic. This measures orchestration,
not commercial success or an estimate of the next campaign's yield.
"""
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'tests')]
from test_agent7_multiflow import FiveFlowCycle
from test_agent8_proactive import browser as fixture_browser
from scripts.replay_agent92 import load
from sales.agent6 import FLOWS,schema
from sales.agent6.api import preview
from sales.commercial.coordinator import run_campaign


def simulate(flows,per_direct_flow=1):
    f=FiveFlowCycle();f.setUp()
    try:
        f.rs.stop(f.c['id']);f.rs.paused(f.c['id'])
        filters=copy.deepcopy(load()['configuration']);filters['commercial_engines']=list(flows)
        for key in ('search_version','demand_version'):filters.pop(key,None)
        filters['commercial']['ai']['provider']='MOCK'
        filters['deep_authorized']=True;filters['deep_plan_token']=preview(f.store,filters)['approval_token']
        f.c=f.rs.create(filters)
        search=f.search
        def acquire(store,payload,check):
            values=search(store,payload,check)
            flow=next((key for key,value in f.queries.items() if value==payload['query']),None)
            if flow not in ('AZIENDE','AGENCIES','STARTUPS'):return values
            expanded=[]
            for value in values:
                for n in range(per_direct_flow):
                    url=value['url']+'/'+str(n)
                    page=copy.deepcopy(f.pages[value['url']]);page['url']=url
                    page['html']+='<p>Synthetic independent request reference '+str(n)+'</p>'
                    f.pages[url]=page;expanded.append({**value,'url':url})
            return expanded
        def browser(store,pages,*a,**kw):
            result=fixture_browser(pages)
            for finding in result['findings']:finding['url']='https://epsilon.example/'
            return result
        with patch('socket.create_connection',side_effect=AssertionError('offline')),\
             patch('sales.agent6.ai.infer',side_effect=f.model),\
             patch('sales.agent6.coordinator.acquire',side_effect=acquire),\
             patch('sales.agent6.coordinator.CompanyWeb.get',side_effect=f.read),\
             patch('sales.commercial.browser.review',side_effect=browser):
            run_campaign(f.store,f.c,lambda:None,lambda _:None)
        with f.store.connect() as c:
            calls=[json.loads(r[0]) for r in c.execute('SELECT body FROM commercial_ai_executions WHERE campaign_id=? AND attempt=1',(f.c['id'],))]
            records=[json.loads(r[0]) for r in c.execute('SELECT body FROM agent6_records WHERE campaign_id=?',(f.c['id'],))]
            pending=[dict(r) for r in c.execute("SELECT kind,state,count(*) n FROM research_tasks WHERE campaign_id=? AND state NOT IN ('done','failed') GROUP BY kind,state",(f.c['id'],))]
            assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
            assert c.execute('select count(*) from prospects').fetchone()[0]==0
        purposes=Counter(r['purpose'] for r in calls)
        actual_read_flows=sorted({flow for flow,task in f.calls if task==schema.READ})
        assert actual_read_flows==sorted(flows),(flows,actual_read_flows)
        assert len(calls)<=filters['commercial']['ai']['max_calls_per_campaign']
        return {'scenario':'synthetic_not_real_leads','flows':list(flows),'direct_requests_per_flow':per_direct_flow,
            'configured_max_calls':filters['commercial']['ai']['max_calls_per_campaign'],
            'configured_max_cost_usd':filters['commercial']['ai']['max_estimated_cost'],
            'simulated_provider_calls':len(calls),'purposes':dict(purposes),
            'planning_share':(purposes['discovery_planning']+purposes['discovery_replanning'])/max(1,len(calls)),
            'original_verification_flows':actual_read_flows,'states':dict(Counter(b['state'] for b in records)),
            'remaining_tasks':pending,'api_calls_real':0,'real_opportunities':0,'production_writes':0}
    finally:f.tearDown()


def main():
    result={'combined':simulate(list(FLOWS),5),'isolated':[simulate([f]) for f in FLOWS],
        'limits':'Synthetic original availability is supplied; this is not a forecast of real candidate quality.'}
    assert result['combined']['planning_share']<.42,result['combined']
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
