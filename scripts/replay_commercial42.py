"""Phase 4.2 replay: saved originals only; no provider, AI, browser or live DB."""
import copy,gzip,json,tempfile
from pathlib import Path
from collections import Counter
from datetime import datetime
from unittest.mock import patch
from sales.db import Store,domain
from sales.providers import blocked
from sales.commercial.indexed_jobs import resolution_continuity
from sales.commercial.discovery import assess
from sales.commercial.inspection import inspect
from sales.commercial.identity import establish
from sales.commercial.geography import locate
from sales.commercial.attribution import geographic_conflicts
from sales.commercial.context import extract
from sales.commercial.target_fit import evaluate as fit
from sales.commercial.opportunity_view import build,novelty,metrics
from sales.commercial.ai import eligibility
ROOT=Path(__file__).resolve().parents[1]
def load():
    with gzip.open(ROOT/'tests/fixtures/commercial42/campaign26.json.gz','rt') as f:return json.load(f)
def replay():
    x=load();originals=x['pages'];docs={d['id']:d for d in x['documents']};traces=[];results=[]
    prior=[]
    for folder,cid in [('commercial3b6',23),('commercial40',24),('commercial41',25)]:
        with gzip.open(ROOT/f'tests/fixtures/{folder}/campaign{cid}.json.gz','rt') as f:prior+=json.load(f)['commercial_revisions']
    for d in x['commercial_discovery']:
        recalculated=assess(d['body'],d['engine'],d['body'].get('origin'))
        origin=d['body'].get('origin',{})
        task=next((t for t in x['research_tasks'] if t['id']==origin.get('task_id')),None)
        if recalculated['decision']!='exclude' and blocked(d['url']) and recalculated.get('source')=='web':recalculated.update(decision='exclude',reason='inaccessible_policy')
        if recalculated['decision']!='exclude' and origin.get('acquisition')=='resolution' and task:
            continuity=resolution_continuity({**task['payload'],'resolution_stage':'COMPANY_DOMAIN_CANDIDATE'},d['body'])
            if continuity['status']!='SUPPORTED':recalculated.update(decision='exclude',reason=continuity['reason'])
        traces.append({'id':d['id'],'engine':d['engine'],'url':d['url'],'historical_decision':d['decision'],'historical_reason':d['body'].get('reason'),'new_decision':recalculated['decision'],'new_reason':recalculated['reason'],'admission_stage':recalculated.get('admission_stage')})
    def read(url):
        if url not in originals:raise ValueError('Offline: original not saved: '+url)
        return copy.deepcopy(originals[url])
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(Path(tmp)/'replay.db');store.init()
        for r in x['commercial_revisions']:
            b=copy.deepcopy(r['body']);owned=[copy.deepcopy(originals[docs[k]['url']]) for k in b.get('document_ids',[]) if k in docs and docs[k]['url'] in originals]
            mode='NO_NEW_ORIGINAL_AVAILABLE';limits=[];before=copy.deepcopy(b)
            admitted=assess(b.get('discovery') or {'url':b['url'],'title':b.get('title','')},b['engine'])
            if admitted['decision']=='exclude':mode='EXCLUDED_BEFORE_HTTP';limits.append(admitted['reason'])
            elif b['engine']=='WEBSITE_REBUILD' and owned:
                identity=establish(owned);geo=geographic_conflicts(locate(owned,identity),[],x['campaign']['filters']['regions']);target=fit(identity,owned,geo)
                b.update(identity=identity,company=identity['name'],geography=geo,target_fit=target)
                mode='RECALCULATED_SCREENING_ONLY';limits.append('Browser not rerun; original partial/not executed audit retained.')
            elif b['engine']!='WEBSITE_REBUILD' and b['url'] in originals and not b.get('social'):
                try:
                    with patch('sales.commercial.inspection.ResearchWeb.get',side_effect=read),patch('sales.commercial.browser.review',side_effect=AssertionError('Replay must not render')):
                        original_task=next((t for t in x['research_tasks'] if t['kind']=='candidate' and t['payload'].get('url')==b['url']),None)
                        out=inspect(store,{**(original_task['payload'] if original_task else {}),'url':b['url'],'commercial_engine':b['engine'],'allowed_regions':x['campaign']['filters']['regions']})
                    b={**out['result'],'identity':out['identity'],'document_ids':before.get('document_ids',[]),'discovery':before.get('discovery')};mode='RECALCULATED_FROM_SAVED_ORIGINALS'
                    b['offline_followups']=out['followups']
                except ValueError as exc:limits.append(str(exc));mode='INCOMPLETE_OFFLINE'
            documents=[docs[i] for i in before.get('document_ids',[]) if i in docs]
            v=build(b,documents,as_of=datetime.fromisoformat(x['snapshot_at']));v['novelty']=novelty(b,prior)
            from sales.commercial.opportunity_view import normalize
            v['subject_new']=bool(v['subject_key']) and not any(normalize((h['body'].get('identity') or {}).get('website'))==v['subject_key'] for h in prior)
            if mode=='EXCLUDED_BEFORE_HTTP':v=None
            results.append({'id':r['opportunity_id'],'revision':r['id'],'historical_state':r['state'],'historical_classification':before.get('classification'),'historical_company':before['company'],'new_state':b['state'],'new_classification':b.get('classification'),'mode':mode,'limits':limits,'body':b,'commercial_view':v,'historical_identity':{k:before.get('identity',{}).get(k) for k in ('name','identity_status','region')},'historical_geography':before.get('geography'),'ai_eligible_before':eligibility(before),'ai_eligible_after':eligibility(b)})
    useful=[r for r in results if r['commercial_view']]
    regained=[t for t in traces if t['historical_decision']=='exclude' and t['new_decision']=='admit']
    removed=[t for t in traces if t['historical_decision']=='admit' and t['new_decision']=='exclude']
    return {'scope':'OFFLINE_REPLAY_NOT_NEW_CAMPAIGN','campaign':26,'historical':dict(Counter(r['state'] for r in x['commercial_revisions'])),'new_commercial':metrics(useful),'records':results,'discovery':traces,'recovered_discovery':regained,'excluded_before_http':removed,'network_calls':0,'ai_calls':0,'browser_runs':0,'production_writes':0,'new_verified_domains':sum(r['body'].get('identity',{}).get('identity_status')=='verified' and r['historical_identity']['identity_status']!='verified' for r in results if r['mode']=='RECALCULATED_SCREENING_ONLY'),'unmeasured':['Real query yield','Live official-domain resolution','External browser reliability','Commercial conversion'],'browser_slots_saved':None,'ai_calls_avoidable_on_historical_inputs':[r['id'] for r in results if str(r['id']) in {a['candidate_id'] for a in x['commercial_ai_executions'] if a['attempt']} and not r['ai_eligible_after'][0]]}
if __name__=='__main__':
    r=replay();(ROOT/'implementation-report/phase42-replay.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k not in ('records','discovery')},ensure_ascii=False))
