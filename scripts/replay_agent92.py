"""Frozen campaign 41 replay. No production database, browser or network."""
import argparse
import copy
import gzip
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.agent6 import qualification,commercial_view,commercial_policy,query_pipeline,learning
from sales.commercial.identity import establish
from sales.commercial.target_fit import evaluate as target_fit

FIXTURE=Path(__file__).resolve().parents[1]/'tests/fixtures/agent92/campaign41.json.gz'


def load():
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def replay(case,regions):
    before=case['record']['body'];p=case['task']['payload']
    if p.get('original_page'):
        source=copy.deepcopy(before['documents'][0]);source['allowed_regions']=regions
        identity=establish([p['original_page']])
        saved=case['ai_executions'][0]['response']
        analysis=copy.deepcopy(saved['output']['analyses'][0])
        body=qualification.evaluate(source,analysis,saved['evidence'],case['record']['flow'],identity)
        body.update(documents=before['documents'],access=before.get('access'),query=before.get('query'),strategy=before.get('strategy'))
        return commercial_view.enrich(body)
    pages=p['website_checkpoint']['pages'];identity=establish(pages)
    fit=target_fit(identity,pages,{'eligible':identity.get('region') in regions})
    # No original browser run or AI review exists for this pre-excluded site.
    # Passing triage is NOT a replayed opportunity or a completed evaluation.
    return {**copy.deepcopy(before),'commercial_fit':fit,'state':'NEEDS_REVIEW' if fit['audit_allowed'] else before['state'],
        'reason':'Preselezione recuperata; audit e bisogno commerciale ancora da dimostrare.',
        'replay_limit':'No saved browser or commercial AI review: cannot simulate qualification.'}


def report():
    fixture=load();cases=[]
    for case in fixture['cases']:
        before=case['record']['body'];after=replay(case,fixture['configuration']['regions'])
        keys=('entity_name','identity_verified','state','missing','reason','optional_unknowns','completion_queue','commercial_fit','budget','identity_link')
        cases.append({'record_id':case['record']['id'],'url':before['url'],
            'before':{k:before.get(k) for k in keys},'after':{k:after.get(k) for k in keys},
            'next_check':commercial_policy.investigation(after),
            'replay_limit':after.get('replay_limit'),
            'historical_negative_neutralized_for_learning':learning.contradicted_negative(before)})
    # Evaluate each historical attempted query against only receipts preceding
    # that attempt. This is a counterfactual policy replay, NOT actual savings.
    rejected=[];history={}
    for receipt in fixture['queries']:
        flow=receipt['flow'];earlier=history.setdefault(flow,[])
        if receipt.get('selection')!='verification':
            saturated=next((a for a in query_pipeline.adaptation(earlier)
                if a['family'] in (query_pipeline.family(receipt['query']),query_pipeline.semantic_family(receipt['query']))),None)
            balance=query_pipeline.strategy_balance(flow,earlier)
            if saturated:rejected.append({'flow':flow,'query':receipt['query'],'reason':'query_family_saturated','sample':saturated['sample']})
            elif balance['required'] and (receipt.get('strategy')=='official_company_sector_region')!=(balance['preferred']=='proactive'):
                rejected.append({'flow':flow,'query':receipt['query'],'reason':'company_strategy_balance_requires_'+balance['preferred']})
        earlier.insert(0,receipt)
    from sales.agent6 import VERSION
    return {'version':VERSION,'scope':'offline_saved_inputs_not_new_campaign','historical_campaign':41,
        'real_api_calls':0,'real_serper_requests':0,'new_campaigns':0,'production_database_writes':0,
        'before':fixture['before'],'replayed_cases':cases,'queries_rejected_counterfactually':rejected,
        'known_identity_false_negatives_recovered':sum(not c['before']['identity_verified'] and c['after']['identity_verified'] for c in cases),
        'interesting_incomplete_dossiers':sum(bool(c['after'].get('completion_queue',{}).get('promising')) for c in cases),
        'new_verified_opportunities':0,'new_potential_opportunities':0,
        'limitations':['Replay uses recorded validated AI outputs, not newly generated answers.',
            'Only two selected original cases are requalified; previous campaign fixtures cover other regressions.',
            'Blocked-query count is a policy counterfactual, not measured provider savings.',
            'No saved response for future NHW currentness follow-up; agency stack is optional in 9.2.1, availability remains unknown.',
            'Commercial conversion, weekly yield and real new planning distribution remain unmeasured.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    result=report();encoded=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(encoded+'\n')
    else:print(encoded)
