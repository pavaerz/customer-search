"""Partial 3B.3 replay of frozen public evidence, no IO except fixture/report."""
import copy,gzip,json,hashlib
from pathlib import Path
from collections import Counter
from sales.commercial.discovery import assess
from sales.commercial.attribution import identity
from sales.commercial.ai import eligibility
from sales.commercial.commercial_gate import sufficient
from sales.commercial.indexed_jobs import parse_indexed_job,resolution
from sales.commercial.rebuild import browser_selection

FIXTURE=Path(__file__).resolve().parents[1]/'tests/fixtures/commercial3b3/campaign20.json.gz'
def load():
    with gzip.open(FIXTURE,'rt') as f:return json.load(f)

def replay():
    data=load();revs=data['commercial_revisions'];rows=[];identities=[];gates=[];browser=[]
    for d in data['commercial_discovery']:
        new=assess(d['body'],d['engine'],d['body'].get('origin'))
        rows.append({'id':d['id'],'engine':d['engine'],'url':d['url'],'query':d['query'],'before':d['decision'],'after':new['decision'],'reason':new['reason'],'resolution':resolution(d['body']) if '/jobs/view/' in d['url'] else None})
    for a in data['commercial_ai_executions']:
        old=next(r['body'] for r in revs if str(r['opportunity_id'])==str(a['candidate_id']))
        allowed,reason=eligibility(old);gate=sufficient(a['engine'],old,a['body']['evidence'])
        gates.append({'execution_id':a['id'],'engine':a['engine'],'before':a['status'],'new_gate':gate,'would_dispatch':allowed and gate['allowed'],'scope':'saved_trimmed_bundle_gate_only','output_revalidation':'not_reproducible_original_invalid_output_not_retained','historical_input_tokens':a['input_tokens'],'historical_output_tokens':a['output_tokens']})
    for r in revs:
        b=r['body'];old=b.get('identity',{});u=b.get('url','');docs=[d for d in data['documents'] if d['id'] in b.get('document_ids',[])]
        # Only original timestamp-matched pages already linked to this revision.
        own_url=old.get('website')
        from sales.db import domain
        pages=[data['pages'][d['url']] for d in docs if d['url'] in data['pages'] and domain(d['url'])==domain(own_url or u)]
        pages.sort(key=lambda p:len(p['url']))
        current=identity(pages) if pages and old else None
        if current:identities.append({'revision':r['id'],'url':u,'before':{k:old.get(k) for k in ('name','identity_status','legal_id')},'after':{k:current.get(k) for k in ('name','identity_status','legal_id','identity_conflicts')},'scope':'saved_original_identity_only','pages':len(pages)})
        if b['engine']=='WEBSITE_REBUILD' and b.get('screening'):
            i={**(current or old),'organization':old.get('organization',{})}
            choice=browser_selection(i,b['screening'],data['campaign']['filters']['work_budget'])
            browser.append({'revision':r['id'],'url':u,'historical_browser':b.get('browser_outcome'),'new_selection':choice,'scope':'selection_only_assuming_remaining_configured_budget','audit_executed':False})
    queries=[]
    for t in data['research_tasks']:
        if t['kind'] not in ('search','resolve'):continue
        q=t['payload']['query'];ds=[d for d in rows if d['query']==q and d['engine']==t['strategy']]
        queries.append({'engine':t['strategy'],'query':q,'state':t['state'],'appearances':len(ds),'new_exclusions':dict(Counter(d['reason'] for d in ds if d['after']=='exclude')),'sample_policy':'one_campaign_not_conversion_evidence'})
    baseline=FIXTURE.parent.parent/'commercial3b2/campaign19.json.gz'
    with gzip.open(baseline,'rt') as f:old19=json.load(f)
    def decoded(x):return json.loads(x) if isinstance(x,str) else x
    compare19=[]
    for t in old19['research_tasks']:
        if t['kind']!='search':continue
        p=decoded(t['payload']);ds=[d for d in old19['commercial_discovery'] if d['engine']==t['strategy'] and d['query']==p.get('query')]
        current=[assess(decoded(d['body']),d['engine']) for d in ds]
        compare19.append({'engine':t['strategy'],'query':p.get('query'),'state':t['state'],'historical_appearances':len(ds),'historical_admitted':sum(d['decision']=='admit' for d in ds),'current_preflight_exclusions':dict(Counter(d['reason'] for d in current if d['decision']=='exclude')),'scope':'saved_metadata_only'})
    from sales.commercial.catalog import options
    budgets={'historical_campaign20':data['campaign']['filters']['work_budget'],'new_pilot_defaults':options({'commercial_engines':['WEBSITE_REBUILD'],'mode':'pilot'})[1],'existing_campaigns_unchanged':True,'authorization':'user explicitly allowed necessary increases; no campaigns launched'}
    return {'phase':'3B.3','resources':budgets,'campaign19_query_comparison':compare19,'campaign19_fixture_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),'scope':'partial_offline_replay_not_campaign_rerun','fixture_sha256':hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        'historical':{'campaign':20,'appearances':len(rows),'evaluations':len(revs),'states':dict(Counter(r['state'] for r in revs)),'ai_calls':len(gates),'browser_audits':0},
        'new_code':{'discovery':rows,'identity':identities,'ai_gates':gates,'browser_selection':browser,'query_quality':queries,
                    'historical_admitted_now_excluded':sum(d['before']=='admit' and d['after']=='exclude' for d in rows),'saved_ai_calls_skipped':sum(not a['would_dispatch'] for a in gates)},
        'not_measured':['new_qualified_opportunities','live_AI_validity','browser_measurements','customer_conversion'],
        'external_calls':0,'historical_database_modified':False}

if __name__=='__main__':
    result=replay();Path('PHASE-3B.3-METRICS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'historical':result['historical'],'admitted_now_excluded':result['new_code']['historical_admitted_now_excluded'],'saved_ai_calls_skipped':result['new_code']['saved_ai_calls_skipped']}))
