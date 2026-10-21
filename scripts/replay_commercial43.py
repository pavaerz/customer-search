"""Curated original-source replay. Never query providers, browser or production DB.

Discovery recall is not measurable offline: the recorded search output is the
input. Missing originals are UNKNOWN rather than fabricated negative outcomes.
"""
import copy,gzip,json,tempfile,sys,hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from sales.db import Store
from sales.commercial.discovery import assess
from sales.commercial.inspection import inspect
from sales.commercial.opportunity_view import build
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/commercial43'

def load():
    dataset=json.loads((FIXTURE/'dataset.json').read_text())
    snapshots={int(cid):json.loads(gzip.decompress((FIXTURE/path).read_bytes())) for cid,path in dataset['snapshots'].items()}
    return dataset,snapshots

def replay():
    dataset,snapshots=load();records=[]
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(Path(tmp)/'replay.db');store.init()
        for case in dataset['cases']:
            x=snapshots[case['campaign']];pages=x['pages'];d=case['search_result'];calls=[];missing=[]
            r=assess(d,case['engine'],d.get('origin'));rev=next((z for z in x['commercial_revisions'] if z['id']==case['revision_id']),None)
            result={'id':case['id'],'label':case['label'],'engine':case['engine'],'url':case['original_url'],'source':case['source'],'historical_decision':case['historical_decision'],'admission':r['decision'],'admission_reason':r['reason'],'trace':{'QUERY':d.get('query'),'RESULT':'SAVED_SEARCH_RESULT','ADMISSION':r['decision'],'DOWNLOAD':'NOT_ATTEMPTED','ENTITY_RESOLUTION':'NOT_EVALUATED','CLASSIFICATION':'NOT_EVALUATED','QUALIFICATION':'NOT_EVALUATED','PRESENTATION':'NOT_EVALUATED'},'first_limiting_stage':None,'known_failure':False}
            def read(url):
                calls.append(url)
                if url not in pages:missing.append(url);raise ValueError('Offline: original not saved')
                return copy.deepcopy(pages[url])
            if r['decision']=='exclude':
                result['first_limiting_stage']='ADMISSION'
                result['known_failure']=case['label']=='POSITIVE'
            elif case['original_url'] not in pages:
                result['trace']['DOWNLOAD']='ORIGINAL_NOT_SAVED';result['first_limiting_stage']='DOWNLOAD';result['limitation']='No original: access/extraction/qualification not measurable offline.'
            else:
                browser=copy.deepcopy(rev['body'].get('browser',{})) if rev else {}
                payload={**d,'url':case['original_url'],'commercial_engine':case['engine'],'allowed_regions':x['campaign']['filters']['regions']}
                original_task=next((t for t in x.get('research_tasks',[]) if t['kind']=='candidate' and t['payload'].get('url')==case['original_url']),None)
                if original_task:payload={**original_task['payload'],**payload}
                try:
                    with patch('sales.commercial.inspection.ResearchWeb.get',side_effect=read),patch('sales.commercial.browser.review',return_value=browser):
                        out=inspect(store,payload)
                    body={**out['result'],'identity':out['identity']};view=build(body,out['documents'],as_of=datetime.fromisoformat(x['snapshot_at']))
                    intent=body.get('commercial_intent') or {};request=bool(intent.get('buyer_evidence') and intent.get('technical')) or bool(body.get('partner_hint'))
                    result.update(state=body['state'],classification=body.get('classification'),view=view['status'],request_recognized=request,body=body,view_detail=view,followups=out['followups'])
                    result['trace'].update(DOWNLOAD='SAVED_ORIGINAL',ENTITY_RESOLUTION=out['identity'].get('identity_status'),CLASSIFICATION=body.get('classification'),QUALIFICATION=body['state'],PRESENTATION=view['status'])
                    if out['identity'].get('identity_status')!='verified':result['first_limiting_stage']='ENTITY_RESOLUTION'
                    elif not request and case['engine']!='WEBSITE_REBUILD':result['first_limiting_stage']='CLASSIFICATION'
                    elif view['status']=='NOT_ACTIONABLE':result['first_limiting_stage']='QUALIFICATION'
                    elif view['status']!='READY_TO_CONTACT':result['first_limiting_stage']='AVAILABILITY_OR_SCOPE_UNKNOWN'
                    result['known_failure']=case['label']=='POSITIVE' and (not request or view['status']=='NOT_ACTIONABLE')
                    if any(f.get('ats_binding') and f['url'] not in pages for f in out['followups']):
                        result['first_limiting_stage']='ATS_ORIGINAL_UNAVAILABLE'
                        result['limitation']='Official ATS link retained; no saved portal/job original to evaluate.'
                except ValueError as exc:result['trace']['DOWNLOAD']='INCOMPLETE_OFFLINE';result['first_limiting_stage']='DOWNLOAD';result['limitation']=str(exc)
            result['saved_reads']=calls;result['unavailable_originals']=missing;records.append(result)
    positives=[r for r in records if r['label']=='POSITIVE'];negatives=[r for r in records if r['label']=='NEGATIVE']
    evaluated=[r for r in records if r.get('view') and r['label']!='AMBIGUOUS'];predicted=[r for r in evaluated if r['view']!='NOT_ACTIONABLE']
    def ratio(n,d):return {'numerator':n,'denominator':d,'value':n/d if d else None,'sample_not_statistically_representative':True}
    return {'phase':'4.3','implementation':{'discovery_module':sys.modules[assess.__module__].__file__,'discovery_sha256':hashlib.sha256(Path(sys.modules[assess.__module__].__file__).read_bytes()).hexdigest()},'scope':'SAVED_SOURCE_REPLAY_NOT_LIVE_SEARCH','records':records,'labels':dict(Counter(r['label'] for r in records)),
        'metrics':{'known_positive_admission_recall':ratio(sum(r['admission']=='admit' for r in positives),len(positives)),
                   'known_positive_recognition_recall':ratio(sum(bool(r.get('request_recognized')) and r.get('view')!='NOT_ACTIONABLE' for r in positives),len(positives)),
                   'advisory_precision_on_classifiable_originals':ratio(sum(r['label']=='POSITIVE' for r in predicted),len(predicted)),
                   'negative_metadata_admitted':ratio(sum(r['admission']=='admit' for r in negatives),len(negatives)),
                   'false_negative_known_positive_ids':[r['id'] for r in positives if r['known_failure']],
                   'false_positive_on_classified_originals':[r['id'] for r in evaluated if r['label']=='NEGATIVE' and r['view']!='NOT_ACTIONABLE'],
                   'first_limiting_stages':dict(Counter(r['first_limiting_stage'] or 'NONE' for r in records)),
                   'search_recall':None,'current_open_commissions':0},
        'network_calls':0,'ai_calls':0,'production_writes':0,'browser_runs':0,
        'limits':['Two positive organizations only, previously used in development: regression set, not held-out validation.', 'Positive label means documented technical demand/partnership at acquisition, not an open paid job today.', 'Missing originals and unresolved actors are not evidence of absence.', 'Browser results are retained historical observations; offline transport is not revisited.']}
if __name__=='__main__':
    import sys
    result=replay();path=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'implementation-report/phase43-replay.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False))
