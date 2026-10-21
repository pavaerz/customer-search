"""Shared commercial presentation; labels never change qualification or CRM."""
import re

TYPES={'DEMANDA_ESPLICITA':'Richiesta esplicita','COLLABORAZIONE_AGENZIA':'Collaborazione con agenzia',
       'OPPORTUNITA_IMPRENDITORIALE':'Cofounder / partecipazione imprenditoriale',
       'OPPORTUNITA_PROATTIVA':'Opportunità proattiva','SEGNALE_INDIRETTO':'Segnale da verificare','NON_QUALIFICATA':'Non qualificata'}


def enrich(body):
    if body.get('decision_engine')=='ai_first_1':
        from .decision import enrich as decision_view
        return decision_view(body)
    from .completion import dossier
    body={**body,'completion_queue':dossier(body)}
    kind=body.get('kind');facts=body.get('facts',[])
    from .alignment import dimensions
    alignment=dimensions(body)
    entrepreneurial=alignment['arrangement'] in ('TECHNICAL_COFOUNDER_OPPORTUNITY','EQUITY_ONLY_OPPORTUNITY')
    request=' '.join(f.get('quote','') for f in facts if f.get('field') in ('request','contract'))
    if kind=='AGENCY_PARTNERSHIP' and body.get('original') and request and body.get('state') not in ('REJECTED','UNVERIFIABLE'):
        body={**body,'model_hypothesis':body.get('model_hypothesis',body.get('hypothesis')),
            'hypothesis':'La fonte invita collaboratori esterni. Competenze specifiche, disponibilità di incarichi, compenso e volume della collaborazione vanno confermati con l’agenzia.'}
    qualified=body.get('state') in ('VERIFIED','POTENTIAL')
    category=body.get('opportunity_type')
    if category not in TYPES:
        category='COLLABORAZIONE_AGENZIA' if kind=='AGENCY_PARTNERSHIP' and request else 'DEMANDA_ESPLICITA' if kind=='BUYER_DEMAND' and request else 'SEGNALE_INDIRETTO' if kind in ('COMPANY_SIGNAL','EDITORIAL') else 'NON_QUALIFICATA'
    if entrepreneurial:category='OPPORTUNITA_IMPRENDITORIALE'
    proactive=category=='OPPORTUNITA_PROATTIVA'
    technical=' '.join(f.get('quote','') for f in facts if f.get('field') in ('technical','scope','request'))
    service=body.get('service') or ('webapp' if re.search(r'\bMVP\b|web.?app|piattaforma|gestionale',technical,re.I) else 'ecommerce' if re.search(r'e.?commerce|woocommerce|shopify',technical,re.I) else 'website' if re.search(r'wordpress|frontend|sit[oi]|website',technical,re.I) else None)
    relation='UNKNOWN'
    from .semantics import REFUSAL
    if body.get('relationship_check',{}).get('status') in ('NONTECHNICAL_PARTNERSHIP','MIXED_INVITATIONS'):relation='UNKNOWN'
    elif kind=='EMPLOYEE_JOB':relation='EMPLOYEE_ONLY'
    elif kind=='SUPPLIER_OFFER':relation='SUPPLIER_OFFER'
    elif REFUSAL.search(request):relation='UNKNOWN'
    elif re.search(r'contratto a progetto|project contract',request,re.I):relation='PROJECT_CONTRACT'
    elif re.search(r'freelanc|partita\s*iva|contractor',request,re.I):relation='FREELANCE_COLLABORATION'
    elif re.search(r'partner|collaborator\w* estern',request,re.I):relation='EXTERNAL_PARTNER'
    elif re.search(r'candidatura spontanea|lavora con noi',body.get('title',''),re.I):relation='GENERIC_RECRUITMENT'
    audit=body.get('website_audit') or {}
    dimensions={'identity':bool(body.get('identity_verified')),'source':bool(body.get('original')),
        'problem':any(o.get('status')=='ISSUE' and o.get('certainty')=='MEASURED' for o in audit.get('observations',[])),
        'declared_demand':bool(not proactive and qualified and any(f.get('original') and f.get('field')=='request' for f in facts)),
        'currentness':bool(body.get('freshness',{}).get('status')=='RECENT'),
        'commercial_interest':'UNKNOWN'}
    from .commercial_score import dimensions as commercial_dimensions
    return {**body,'opportunity_type':category,'opportunity_type_label':TYPES[category],
        'commercial_dimensions':commercial_dimensions(body),'commercial_alignment':alignment,
        'service':service,'collaboration_type':relation,'verification_dimensions':dimensions,
        'priority':'high' if qualified else 'medium' if body.get('state') in ('RELEVANT','NEEDS_REVIEW') else 'low',
        'project_value':{'amount':body.get('budget',{}).get('amount') if not entrepreneurial and body.get('budget',{}).get('kind')=='PROJECT_BUDGET' else None,
            'basis':'declared_project_budget' if not entrepreneurial and body.get('budget',{}).get('kind')=='PROJECT_BUDGET' else 'UNKNOWN'}}
