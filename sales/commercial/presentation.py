"""Read-only commercial distinctions. Never rewrites official states or scores."""
def lead_type(body):
    from .entity_scope import MULTI
    discovery=body.get('discovery') or {}
    legacy_listing=bool(MULTI.search(' '.join(str(v) for v in (body.get('title',''),body.get('url',''),discovery.get('url',''),discovery.get('title','')))))
    intent=body.get('commercial_intent') or {};fit=body.get('target_fit') or {};v=body.get('verification') or {}
    if legacy_listing or body.get('classification')=='actor_unresolved' or body.get('entity_scope',{}).get('multi_subject') or body.get('source_kind') in ('aggregator','directory','multi_company_catalog') or body.get('classification')=='contradictory_request' or intent.get('contradictions'):
        kind='DATA_QUALITY_REVIEW';reason='Soggetto non attribuito: fonte multisoggetto.'
    elif fit.get('status')=='LOW_PRIORITY':kind='LOW_PRIORITY_TARGET';reason='Target di bassa priorità; non è una richiesta commerciale.'
    elif body.get('state')!='REJECTED' and (body.get('identity') or {}).get('identity_status')=='verified' and not (body.get('identity') or {}).get('identity_conflicts') and intent.get('commercial_role') not in ('SELLER','PARTNERSHIP_SELLER','AGGREGATOR','EMPLOYER') and intent.get('technical') and intent.get('buyer_evidence'):
        kind='PARTNERSHIP_PROSPECT' if body.get('classification')=='ongoing' or v.get('currentness')=='standing_invitation' else 'ACTIONABLE_LEAD'
        reason='Richiesta tecnica nelle prove; restano da verificare i requisiti indicati.'
    elif body.get('classification') in ('access_incomplete','insufficient'):kind='ACCESS_REVIEW';reason='Controllo tecnico incompleto, non controprova commerciale.'
    elif fit.get('audit_allowed') and body.get('browser',{}).get('completed') and body.get('state')=='POTENTIAL':kind='REBUILD_PROSPECT';reason='Problemi misurati e perimetro da approfondire; nessuna intenzione di acquisto dimostrata.'
    else:kind='DATA_QUALITY_REVIEW';reason='Prove commerciali o identità insufficienti.'
    return {'type':kind,'reason':reason,'official_state_unchanged':True,'priority':{'ACTIONABLE_LEAD':5,'PARTNERSHIP_PROSPECT':4,'REBUILD_PROSPECT':3,'ACCESS_REVIEW':2,'DATA_QUALITY_REVIEW':1,'LOW_PRIORITY_TARGET':0}[kind]}

def history(rows):
    """Rows sorted by revision ID; no promotion based on an older decision."""
    rows=sorted(rows,key=lambda r:r['id']);latest=rows[-1] if rows else None
    audits=[r for r in rows if r['body'].get('browser',{}).get('pages') or r['body'].get('browser',{}).get('resource_requests')]
    best=max(rows,key=lambda r:(bool(r['body'].get('browser',{}).get('completed')),len(r['body'].get('evidence',[]))+len(r['body'].get('browser',{}).get('pages',[])),r['id'])) if rows else None
    def brief(r):return {'revision_id':r['id'],'campaign_id':r.get('campaign_id'),'state':r.get('state'),'audit':r['body'].get('browser',{}),'document_ids':r['body'].get('document_ids',[]),'evidence':r['body'].get('evidence',[]),'checked_at':r['body'].get('checked_at')} if r else None
    return {'latest_decision':brief(latest),'best_available_evidence':brief(best),'latest_audit':brief(audits[-1]) if audits else None,'audit_history':[brief(r) for r in audits]}
