"""Offline advisory replay of saved originals; no campaigns or inference."""
import copy,gzip,json
from pathlib import Path
from collections import Counter
from datetime import datetime
from sales.commercial.opportunity_view import build,novelty,metrics,normalize
from sales.commercial.target_fit import evaluate as target_fit
from sales.commercial.discovery import assess
ROOT=Path(__file__).resolve().parents[1]
def load(cid):
    p=ROOT/'tests/fixtures'/({22:'commercial3b5',23:'commercial3b6',24:'commercial40'}[cid])/f'campaign{cid}.json.gz'
    with gzip.open(p,'rt') as f:return json.load(f)
def replay():
    all_data={i:load(i) for i in (22,23,24)};history=all_data[24].get('prior_revisions',[]);out=[]
    for cid,x in all_data.items():
        rs=sorted(x['commercial_revisions'],key=lambda r:r['id']);latest=list({r['opportunity_id']:r for r in rs}.values());items=[];docs={d['id']:d for d in x['documents']}
        for r in latest:
            b=copy.deepcopy(r['body']);owned=[x['pages'][docs[i]['url']] for i in b.get('document_ids',[]) if i in docs and docs[i]['url'] in x.get('pages',{})]
            original_fit=b.get('target_fit')
            if b['engine']!='WEBSITE_REBUILD' and b.get('identity',{}).get('identity_status')=='verified' and owned:
                from sales.commercial.qualification import evaluate
                source=next((p for p in owned if p['url']==b['url']),None)
                if source:
                    recalculated=evaluate(b['engine'],b['identity'],source,b['geography'])
                    recalculated.update(identity=b['identity'],document_ids=b.get('document_ids',[]),state=r['state'])
                    b=recalculated

            if b['engine']=='WEBSITE_REBUILD' and owned:
                b['target_fit']=target_fit(b.get('identity') or {},owned,b.get('geography'))
            v=build(b,[docs[i] for i in b.get('document_ids',[]) if i in docs],as_of=datetime.fromisoformat(x['snapshot_at']))
            v['novelty']=novelty(b,history)
            v['subject_new']=bool(v['subject_key']) and not any(normalize(h['body'].get('identity',{}).get('website'))==v['subject_key'] for h in history)
            items.append({'id':r['opportunity_id'],'revision':r['id'],'historical_state':r['state'],'historical_target_fit':original_fit,'recalculated_target_fit':b.get('target_fit'),'commercial_view':v,'scope':'OFFLINE_ADVISORY_PROJECTION; official state unchanged; browser/AI not rerun'})
        traces=[{'id':d['id'],'url':d['url'],'historical':d['decision'],'recalculated':assess(d['body'],d['engine'])} for d in x.get('commercial_discovery',[])]
        out.append({'campaign':cid,'historical':dict(Counter(r['state'] for r in latest)),'commercial':metrics(items),'items':items,'discovery':traces,'synthetic':False})
        history+=rs
    return {'scope':'OFFLINE_SAVED_EVIDENCE_NOT_NEW_CAMPAIGNS','campaigns':out,'network_calls':0,'ai_calls':0,'database_writes':0,'conversion_measured':False}
if __name__=='__main__':
    report=replay();(ROOT/'implementation-report/phase40-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in c.items() if k in ('campaign','historical','commercial')} for c in report['campaigns']],ensure_ascii=False))
