"""Ordinal, inspectable commercial dimensions. Never a sales probability."""


def dimensions(body):
    facts=body.get('facts',[]);audit=body.get('website_audit') or {};fit=body.get('commercial_fit') or {}
    original=[f for f in facts if f.get('original') and f.get('url') and f.get('quote')]
    needs=[o for o in audit.get('observations',[]) if o.get('status')=='ISSUE' and o.get('certainty')=='MEASURED'
           or o.get('status')=='ASSESSMENT' and o.get('certainty')=='GROUNDED_ASSESSMENT']
    major=[o for o in needs if o.get('severity')=='major']
    qualified=body.get('state') in ('VERIFIED','POTENTIAL')
    refs=lambda fs:[{'url':f['url'],'quote':f['quote'],'checked_at':f.get('checked_at')} for f in fs[:3]]
    def item(value,reason,evidence=(),uncertainty=None):
        return {'value':value,'reason':reason,'evidence':list(evidence),'uncertainty':uncertainty,'sales_probability':None}
    request=[f for f in original if f.get('field')=='request']
    contact=[{'url':c['url'],'value':c['value'],'checked_at':c.get('checked_at')} for c in body.get('contacts',[]) if c.get('url') and c.get('checked_at')]
    evidence=[{'id':o['id'],'url':o['evidence']['url'],'checked_at':o['evidence'].get('checked_at')} for o in major[:5]]
    good_source=body.get('identity_verified') and body.get('original') and not body.get('semantic_issues')
    from .alignment import contacts,arrangement
    contact=contacts(body)
    actual_request=qualified and body.get('kind')=='BUYER_DEMAND' and request and arrangement(body) not in ('TECHNICAL_COFOUNDER_OPPORTUNITY','EQUITY_ONLY_OPPORTUNITY')
    return {
        'company_fit':item('SUPPORTED' if fit.get('audit_allowed') or qualified else 'NOT_COMPATIBLE' if fit.get('status')=='NOT_SUITABLE' else 'UNKNOWN',
            'Compatibilità con il servizio, non capacità di spesa.',refs([f for f in original if f.get('field') in ('business_activity','technical','scope')]),'Budget aziendale sconosciuto salvo importo dichiarato.'),
        'website_need':item('SIGNIFICANT_OBSERVATIONS' if audit.get('website_opportunity')=='REVIEW_COMPLETE_PROJECT' else 'LIMITED_OBSERVATIONS' if needs else 'UNKNOWN',
            'Rilievi tecnici e valutazioni UX/contenuti con fonti; la proposta completa richiede una motivazione commerciale separata.',evidence,
            'Audit parziale: alcune verifiche non sono state completate.' if audit and audit.get('browser_status')!='COMPLETE' else 'Nessuna intenzione di acquisto dedotta.'),
        'evidence_strength':item('CORROBORATED' if good_source and qualified else 'PARTIAL' if original or needs else 'UNKNOWN',
            'Identità, originale e coerenza delle citazioni.',refs(original),'; '.join(body.get('semantic_issues',[])) or None),
        'contactability':item('PUBLIC_CHANNEL' if contact and body.get('identity_verified') else 'UNKNOWN',
            'Canale pubblicato dalla fonte: nessun invio eseguito.',contact,'Disponibilità a collaborare e consenso non dedotti dal contatto.'),
        'freshness':item(body.get('freshness',{}).get('status','UNKNOWN'),
            'Data della richiesta distinta dalla consultazione della pagina.',refs([f for f in original if f.get('field')=='publication']),
            'La data di consultazione non dimostra che un incarico sia ancora aperto.'),
        'commercial_relevance':item('SUPPORTED' if qualified else 'TO_VERIFY' if body.get('state') in ('RELEVANT','NEEDS_REVIEW') else 'UNKNOWN',
            body.get('reason') or 'Ragione commerciale non dimostrata.',refs(request) or evidence,
            'Ipotesi da discutere con il referente, non incarico garantito.'),
        'buying_intent':item('DECLARED_REQUEST' if actual_request else 'UNKNOWN',
            'Richiesta esplicita originale verificata.' if actual_request else 'Nessuna intenzione di acquisto dimostrata.',refs(request) if actual_request else [],
            'Non equivale a un contratto o a una disponibilità di spesa verificata.')}
