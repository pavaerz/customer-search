"""Read-only replay of saved originals. No database, network, browser or AI dispatch."""
import gzip,json,copy
from pathlib import Path
from sales.commercial.attribution import identity,geographic_conflicts
from sales.commercial.geography import locate
from sales.commercial.context import extract
from sales.commercial.qualification import evaluate
from sales.commercial.target_fit import evaluate as fit
from sales.commercial.entity_scope import profile
from sales.commercial.presentation import lead_type,history

def load():
    with gzip.open(Path(__file__).resolve().parents[1]/'tests/fixtures/commercial3b5/campaign22.json.gz','rt') as f:return json.load(f)
def pages_for(x,r):
    docs={d['id']:d for d in x['documents']};return [x['pages'][docs[i]['url']] for i in r['body']['document_ids'] if i in docs and docs[i]['url'] in x['pages']]
def replay():
    x=load();out=[]
    for r in sorted(x['commercial_revisions'],key=lambda r:r['id']):
        b=r['body'];pages=pages_for(x,r)
        if not pages:
            out.append({'revision':r['id'],'company':b['company'],'engine':b['engine'],'url':b['url'],'original_classification':b['classification'],'original_decision':r['state'],'replay_decision':r['state'],'scope':'NO_ORIGINAL_AVAILABLE','reason':'No saved HTML; no reconstruction.'});continue
        source=next((p for p in pages if p['url']==b['url']),pages[0])
        # Explicit multi-company source is the boundary even when homepage exists.
        pfirst=next((p for p in pages if profile(p)['multi_subject']),None)
        own=identity([pfirst] if pfirst else pages)
        geo=geographic_conflicts(locate(pages,own),extract(source),x['campaign']['filters']['regions'])
        if pfirst:
            revised={**b,'state':'UNVERIFIABLE','classification':'actor_unresolved','identity':own,'target_fit':None,'browser':{},'evidence':[],'entity_scope':profile(pfirst),'reason':'ACTOR_UNRESOLVED: no cross-company evidence.'}
        elif b['engine']=='WEBSITE_REBUILD':
            target=fit(own,pages,geo)
            revised={**b,'identity':own,'geography':geo,'target_fit':target}
            # No old measurements are retroactively made reliable by new code.
            revised.update(state='REJECTED' if target['status']=='NOT_SUITABLE' else 'NEEDS_REVIEW' if target['status']=='LOW_PRIORITY' else 'UNVERIFIABLE',reason='Target replay only; browser not re-executed, need not proven.')
        else:
            revised=evaluate(b['engine'],own,source,geo);revised['identity']=own
        out.append({'revision':r['id'],'engine':b['engine'],'company':b['company'],'url':b['url'],'original_decision':r['state'],'original_classification':b['classification'],'replay_decision':revised['state'],'replay_classification':revised.get('classification'),'identity':own,'geography':geo,'target_fit':revised.get('target_fit'),'reason':revised['reason'],'limits':revised.get('limits',[]),'commercial_intent':revised.get('commercial_intent'),'skills':revised.get('skills'),'compensation':revised.get('compensation'),'verification':revised.get('verification'),'documents':[{'url':p['url'],'checked_at':p['checked_at'],'content_hash':p.get('content_hash')} for p in pages],'lead_profile':lead_type(revised),'replayed_body':revised})
    return {'historical':{'campaign':22,'revisions':32,'opportunities':31},'replay':out,'external_calls':0,'database_writes':0,'browser_reexecuted':False,'ai_regenerated':False,'new_verified_customers':None}
if __name__=='__main__':
    result=replay();Path('implementation-report/phase-3b5-replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for r in result['replay']:print(r['revision'],r['company'],r['original_decision'],'->',r['replay_decision'],r.get('identity',{}).get('identity_status'),r.get('geography',{}).get('regions'))
