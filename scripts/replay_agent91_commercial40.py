"""Replay direction checks over frozen Campaign 40 evidence, without providers."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.agent6 import commercial_policy,completion,query_pipeline

FIXTURE=Path(__file__).resolve().parents[1]/'tests/fixtures/agent91/commercial40.json.gz'

def report():
    raw=FIXTURE.read_bytes();saved=json.loads(gzip.decompress(raw));queries=[];cases=[]
    proposals={p['proposal']['query']:p['proposal'] for p in saved['proposals']}
    for receipt in saved['queries']:
        proposal=proposals.get(receipt['query'])
        if not proposal:continue
        policy=commercial_policy.assess_query(proposal,receipt['flow'])
        if not policy['allowed']:
            queries.append({'query':receipt['query'],'flow':receipt['flow'],'observed_results':receipt['results'],
                            'policy_now':policy,'historically_executed':True})
    for record in saved['cases']:
        body=record['body']
        source=next(d for d in body['documents'] if any(f['field']=='request' and f['quote'] in d['text'] for f in body['facts']))
        cases.append({'record_id':record['id'],'url':source['url'],'historical_state':record['state'],
                      'historical_relationship':body.get('relationship_check'),
                      'request_quotes':[f['quote'] for f in body['facts'] if f['field']=='request'],
                      'current_relationship_rule':completion.relationship(source,body['facts']),
                      'original_checked_at':source.get('checked_at'),
                      'new_measurement':False})
    rows=[{**r,'campaign_id':40} for r in saved['queries'] if r['memory_id'] in (1751,1938,2094)]
    return {'mode':'offline_direction_replay_not_new_campaign','campaign_id':40,
            'fixture_sha256':hashlib.sha256(raw).hexdigest(),'queries_stopped_before_provider':queries,
            'request_cases':cases,'empty_family_evidence':rows,'empty_family_adaptation':query_pipeline.adaptation(rows),
            'new_ai_calls':0,'new_serper_calls':0,'production_writes':0,'new_opportunities':0,
            'limits':['Selected regression evidence, not a representative precision sample.',
                      'No claim that every result of a rejected query was irrelevant.',
                      'No prediction of next-campaign queries, savings or conversions.',
                      'Accredited supplier participation remains unknown, not a demonstrated web project.']}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    content=json.dumps(report(),ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(content)
    else:print(content)
