"""Read-only reconstruction of acquisition paths, including pre-download rejects."""
import json
from .discovery_relevance import visit_purpose


def paths(store, cid, offset=0, limit=20):
    offset=max(0,int(offset));limit=max(1,min(100,int(limit)))
    with store.connect() as c:
        queries={r['fingerprint']:dict(r) for r in c.execute('SELECT * FROM discovery_queries WHERE campaign_id=?',(cid,))}
        candidates={r['url']:dict(r) for r in c.execute('SELECT * FROM discovery_candidates WHERE campaign_id=?',(cid,))}
        frontier=[dict(r) for r in c.execute("SELECT * FROM discovery_frontier WHERE campaign_id=? AND kind='candidate' ORDER BY id",(cid,))]
        assessments={r['id']:dict(r) for r in c.execute('SELECT id,status,entity_id FROM research_assessments WHERE campaign_id=?',(cid,))}
        events=[json.loads(r[0]) for r in c.execute("SELECT details FROM research_events WHERE campaign_id=? AND kind='acquisition_filter' ORDER BY id",(cid,))]
        errors={}
        for row in c.execute("SELECT url,message,details FROM research_events WHERE campaign_id=? AND kind='error' ORDER BY id",(cid,)):
            detail=json.loads(row['details'])
            errors[row['url']]=detail.get('access') or {'message':row['message'],'code':'legacy_unclassified'}
    rows={}
    for f in frontier:
        p=json.loads(f['payload']);url=p['url'];candidate=candidates.get(url,{})
        d=json.loads(candidate.get('details','{}'));q=queries.get(p.get('query_key') or d.get('query_key'),{})
        root=queries.get(p.get('root_query_key') or d.get('root_query_key'),{})
        source=p.get('evidence_url') or p.get('source_url') or next((x.get('url') for x in p.get('source_documents',[]) if x.get('url')),None)
        query=p.get('query') or q.get('query')
        assessment=assessments.get(candidate.get('assessment_id'),{})
        rows[(query,url)]={'url':url,'query':query,'root_query':root.get('query'),
            'page':p.get('query_page') or q.get('page'),'source_url':source,
            'subject':p.get('subject'),'purpose':d.get('visit_purpose') or visit_purpose(p),
            'classification':'Fonte editoriale' if d.get('publisher') else 'Impresa identificata' if candidate.get('identity_status')=='verified' else 'Identità da verificare',
            'state':candidate.get('state',f['state']),'reason':candidate.get('reason','In coda; nessuna verifica completata.'),
            'company':d.get('identity',{}).get('name'),'assessment_id':candidate.get('assessment_id'),
            'qualification':assessment.get('status'),'access':d.get('access') or errors.get(url),
            'visited':False if d.get('prefetch_rejection') else bool(d.get('document'))}
    for event in events:
        for item in event.get('discarded',[]):
            rows.setdefault((event.get('query'),item['url']),{'query':event.get('query'),'url':item['url'],
                'purpose':'Verificare la pertinenza del risultato prima del download.',
                'classification':'Non pertinente prima della lettura','state':'rejected',
                'reason':item['reason'],'visited':False,'qualification':None})
    items=list(rows.values())
    return {'items':items[offset:offset+limit],'total':len(items),'offset':offset,'limit':limit,
            'note':'Ricostruzione dai dati registrati. Identificazione e qualificazione sono distinte; i metadati non salvati nelle versioni precedenti restano sconosciuti.'}
