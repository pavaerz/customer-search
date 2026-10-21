"""Replay saved C44 query/source admission only. No DB, AI, search or HTTP."""
import hashlib
import json
from pathlib import Path

from sales.agent6.query_pipeline import prepare
from sales.agent6.discovery_intent import source_issue

ROOT=Path(__file__).resolve().parents[1]


def run():
    source=ROOT/'CUSTOMERSEARCH-AI-FIRST-LIVE-01-METRICS.json'
    frozen=json.loads(source.read_text());queries=[]
    for task in frozen['research_tasks']:
        if task['kind']!='search':continue
        q=task['payload'];q=json.loads(q) if isinstance(q,str) else q
        allowed,error=prepare(q,task['strategy'],frozen['campaign']['filters']['regions'],ai_first=True)
        queries.append({'flow':task['strategy'],'query':q['query'],'historically_executed':task['state']=='done',
                        'admitted_now':bool(allowed),'check':error or allowed['commercial_policy']})
    query_map={(q['flow'],q['query']):q for q in queries}
    urls=[]
    for row in frozen['commercial_discovery']:
        body=row['body'];body=json.loads(body) if isinstance(body,str) else body
        issue=source_issue({**body,'url':row['url']})
        urls.append({'flow':row['engine'],'url':row['url'],'query':row['query'],
                     'historical_decision':row['decision'],'source_check':issue,
                     'parent_query_admitted_now':query_map.get((row['engine'],row['query']),{}).get('admitted_now'),
                     'commercial_decision':None})
    return {'mode':'offline_saved_query_and_url_admission','source':source.name,
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'queries':queries,'sources':urls,
            'summary':{'saved_queries':len(queries),'admitted_queries':sum(q['admitted_now'] for q in queries),
                       'queries_returned_for_replanning':sum(not q['admitted_now'] for q in queries),
                       'saved_discovery_rows':len(urls),'source_collections_excluded':sum(bool(r['source_check']) for r in urls),
                       'rows_from_rejected_queries':sum(r['parent_query_admitted_now'] is False for r in urls)},
            'paid_calls':0,'production_database_accesses':0,
            'commercial_precision':None,'commercial_recall':None,
            'limitations':['Not a rerun: replacement searches and their outcomes are unknown.',
                           'Query admission is not qualification of the returned company.',
                           'A rejected topic query may have returned a useful incidental URL; no company is blacklisted.',
                           'Original commercial AI accuracy and client acquisition remain unmeasured.']}


if __name__=='__main__':
    output=ROOT/'implementation-report/commercial-objective/discovery-replay.json'
    result=run();output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result['summary']))
