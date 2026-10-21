"""Offline campaign23 replay. Never visits a page or opens any database."""
import copy,gzip,json
from pathlib import Path
from collections import Counter
from sales.commercial.discovery import assess,linkedin_resolution
from sales.providers import blocked
from sales.commercial.entity_scope import profile
from sales.commercial.attribution import identity,geographic_conflicts
from sales.commercial.geography import locate
from sales.commercial.context import extract
from sales.commercial.qualification import evaluate
from sales.commercial.presentation import lead_type
from sales.commercial.ai_tasks import task_for,request_context
from sales.commercial.ai import eligibility

ROOT=Path(__file__).resolve().parents[1]
def load():
    with gzip.open(ROOT/'tests/fixtures/commercial3b6/campaign23.json.gz','rt') as f:return json.load(f)
def replay():
    x=load();discovery=[];evaluations=[]
    for r in x['commercial_discovery']:
        b=r['body'];new=assess(b,r['engine']);decision=new['decision'];reason=new['reason'];hint=None
        if decision!='exclude' and blocked(r['url']) and new['source']=='web':
            h=linkedin_resolution(b)
            if h and h['indexed_job'].get('contract_hint')=='external':decision='indexed_hint';reason='authorized_resolution_only';hint=h
            else:decision='exclude';reason='inaccessible_policy'
        discovery.append({'id':r['id'],'engine':r['engine'],'url':r['url'],'query':r['query'],'original':r['decision'],'recalculated':decision,'reason':reason,'indexed_hint':hint,'scope':'METADATA_RECALCULATED_NOT_ENQUEUED'})
    docs={d['id']:d for d in x['documents']}
    for r in x['commercial_revisions']:
        b=r['body'];revised=copy.deepcopy(b)
        # Metadata gate is separate from historical qualification. Excluded
        # URLs are not relabeled REJECTED companies in the historical record.
        trace=next((d for d in discovery if d['engine']==b['engine'] and (d['url']==b.get('discovery',{}).get('url') or d['url']==b['url'])),None)
        pages=[x['pages'][docs[i]['url']] for i in b.get('document_ids',[]) if i in docs and docs[i]['url'] in x['pages']]
        if trace and trace['recalculated']=='exclude':scope='PREFLIGHT_EXCLUDED';decision=None
        elif not pages:scope='NO_ORIGINAL_AVAILABLE';decision=None
        else:
            boundary=next((p for p in pages if profile(p)['multi_subject']),None)
            if boundary:
                revised.update(state='UNVERIFIABLE',classification='actor_unresolved',identity=identity([boundary]),entity_scope=profile(boundary));scope='ORIGINAL_RECALCULATED'
            elif b['engine']!='WEBSITE_REBUILD':
                own=identity(pages);source=next((p for p in pages if p['url']==b['url']),pages[0]);geo=geographic_conflicts(locate(pages,own),extract(source),x['campaign']['filters']['regions'])
                revised=evaluate(b['engine'],own,source,geo);revised.update(identity=own);scope='ORIGINAL_RECALCULATED'
            else:scope='HISTORICAL_AUDIT_NOT_REEXECUTED'
            decision=revised['state']
        evaluations.append({'revision':r['id'],'engine':b['engine'],'company':b['company'],'url':b['url'],'original_state':r['state'],'original_classification':b['classification'],'recalculated_state':decision,'scope':scope,'metadata_reason':trace['reason'] if trace else None,'profile':lead_type(revised),'ai_task':task_for(b['engine']),'ai_eligible':eligibility(revised),'verified_context':request_context(revised)})
    ai=[]
    for a in x['commercial_ai_executions']:
        if not a['attempt']:continue
        ai.append({'execution_id':a['id'],'engine':a['engine'],'historical_status':a['status'],'historical_error':a['body'].get('error'),'new_task':task_for(a['engine']),'new_response':None,'status':'NOT_REEXECUTED_NO_RAW_INVALID_REPLY'})
    return {'campaign':23,'source_snapshot_at':x['snapshot_at'],'fixture':x['fixture_metadata'],
        'historical':{'discovery':dict(Counter(d['decision'] for d in x['commercial_discovery'])),'revisions':len(x['commercial_revisions']),'ai_attempts':len(ai)},
        'recalculated':{'discovery':dict(Counter(d['recalculated'] for d in discovery)),
            'prior_admissions_now_excluded':sum(d['original']=='admit' and d['recalculated']=='exclude' for d in discovery),
            'new_individual_index_hints':sum(d['recalculated']=='indexed_hint' for d in discovery)},
        'discovery':discovery,'evaluations':evaluations,'ai_contract_mapping':ai,
        'external_calls':0,'database_writes':0,'browser_reexecuted':False,'ai_regenerated':False,'new_campaign':False,'real_world_improvement':None}
if __name__=='__main__':
    out=replay();(ROOT/'implementation-report/phase-3b6-replay.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'historical':out['historical'],'recalculated':out['recalculated']},indent=2))
