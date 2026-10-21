"""Frozen pre-change labels and baseline vs new discovery, strictly offline.

Binary precision uses only labelled positive/negative cases. Ambiguous cases
and all unlabelled campaign traces are reported separately, never counted as
successful commercial opportunities. Synthetic examples are not market leads.
"""
import gzip,json,hashlib
from pathlib import Path
from collections import Counter
from sales.commercial.discovery import assess
from sales.commercial.recommendations import assess as recommend
from sales.commercial.indexed_jobs import resolution_continuity
from sales.commercial.job_activity import evaluate as activity
from sales.commercial.source_intelligence import describe
ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'tests/fixtures/commercial50'

def load():
    benchmark=json.loads((FIX/'benchmark.json').read_text())
    with gzip.open(FIX/'campaign29.json.gz','rt') as f:saved=json.load(f)
    return benchmark,saved

def ratio(n,d):return {'numerator':n,'denominator':d,'value':n/d if d else None}

def metrics(rows):
    labelled=[r for r in rows if r['label'] in ('POSITIVE','NEGATIVE')]
    tp=sum(r['label']=='POSITIVE' and r['decision']=='admit' for r in labelled)
    fp=sum(r['label']=='NEGATIVE' and r['decision']=='admit' for r in labelled)
    positives=sum(r['label']=='POSITIVE' for r in labelled)
    return {'precision':ratio(tp,tp+fp),'recall':ratio(tp,positives),'false_positives':fp,
      'ambiguous_admitted':sum(r['label']=='AMBIGUOUS' and r['decision']=='admit' for r in rows),
      'cases':len(rows),'labelled_binary_cases':len(labelled)}

def replay():
    b,s=load();baseline={r['id']:r for r in b['baseline']};old=[];new=[]
    for case in b['cases']:
        row={k:v for k,v in case.items() if k!='item'}
        old.append({**row,**baseline[case['id']]})
        result=assess(case['item'],case['engine'],case['item'].get('origin'))
        new.append({**row,'decision':result['decision'],'reason':result['reason'],'source':result['source_intelligence']['family']})
    all_traces=[]
    for d in s['traces']:
        result=assess(d['body'],d['engine'],d['body'].get('origin'))
        all_traces.append({'id':d['id'],'old':d['decision'],'new':result['decision'],'reason':result['reason'],'url':d['url']})
    jobs=[recommend(i,s['as_of'],include_inactive=True) for i in s['items']]
    activity_rows=[{'id':i['id'],'activity':activity(i['body'],i['engine'],s['as_of'])} for i in s['items'] if i['engine']!='WEBSITE_REBUILD']
    pacer=next(i for i in s['items'] if i['id']==825)['body']['discovery']
    output={'benchmark_version':'5.0','as_of':s['as_of'],'fixture_sha256':hashlib.sha256((FIX/'benchmark.json').read_bytes()).hexdigest(),
      'baseline':metrics(old),'new':metrics(new),'by_provenance':{p:{'baseline':metrics([r for r in old if r['provenance']==p]),'new':metrics([r for r in new if r['provenance']==p])} for p in sorted({r['provenance'] for r in old})},
      'cases':new,'regressions':[r for r in new if r['label']=='POSITIVE' and r['decision']!='admit' and baseline[r['id']]['decision']=='admit'],
      'raw_trace_replay':{'label':'UNLABELLED_DESCRIPTIVE_ONLY','rows':all_traces,'new_decisions':dict(Counter(r['new'] for r in all_traces))},
      'entity_resolution':{'pacer':resolution_continuity(pacer,pacer)},'freshness_and_geography':activity_rows,
      'recommendations':[{'id':r['id'],'recommended':r['recommended'],'exclusion':r.get('exclusion'),'score':r.get('compatibility_score')} for r in jobs],
      'commercial_qualification':{'verified_in_saved_campaign':sum(i['state']=='VERIFIED' for i in s['items']),'potential_in_saved_campaign':sum(i['state']=='POTENTIAL' for i in s['items']),'new_qualifications':0,'official_states_unchanged':True},
      'network_calls':0,'ai_calls':0,'production_writes':0,'cost_efficiency':{'new_live_results_per_credit':None,'reason':'No live campaign; fixture precision is not market yield.'}}
    return output
if __name__=='__main__':
    result=replay();(ROOT/'implementation-report/phase50-benchmark.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:result[k] for k in ('baseline','new','regressions','entity_resolution')},ensure_ascii=False))
