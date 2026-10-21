"""Source owner, commercial subject and organization type are distinct claims."""
import re
from sales.db import domain
from sales.commercial.demand import ASK,STANDING,SELL
from sales.commercial.indexed_jobs import publisher_host
from .schema import identity_role


def engagement(facts):
    """Describe the quoted contract, never funding or the selected search flow.

    Equity can accompany a paid contract. Equity-only/cofounder roles are
    entrepreneurial opportunities; they are never valued as paid commissions.
    """
    proofs=[f for f in facts if f.get('original') and f.get('field') in ('request','contract','scope')]
    text='\n'.join(f['quote'] for f in proofs)
    def positive(pattern):
        return any(not re.search(r'(?:\bnot|\bno|\bnon|\bsenza)\s+(?:an?\s+|è\s+|un[oa]?\s+)?$',text[max(0,m.start()-25):m.start()],re.I)
            for m in re.finditer(r'\b(?:'+pattern+')',text,re.I))
    equity=positive(r'equity[ -]only|only (?:equity|shares)|solo (?:equity|quote)|(?:compenso|remunerazione).{0,30}(?:esclusivamente|soltanto).{0,15}(?:quote|equity)')
    unpaid=positive(r'unpaid\b|senza (?:compenso|retribuzione)|non retribuit|a titolo gratuito|no (?:cash|monetary) compensation')
    founder=positive(r'co[ -]?founder|cofondator|socio (?:tecnico|sviluppatore)')
    paid=positive(r'paid (?:freelance|contract|project|supplier)|(?:contratto|progetto|incarico|collaborazione) retribuit|compenso (?:fisso|concordato)|fixed[ -]price (?:contract|project)')
    conflict=(equity or unpaid) and paid
    status='CONTRADICTORY_TERMS' if conflict else 'EQUITY_ONLY' if equity else 'UNPAID' if unpaid else 'COFOUNDER_ROLE' if founder and not paid else 'PAID_CONTRACT' if paid else 'UNKNOWN'
    return {'status':status,'basis':'quoted_original_contract_terms_not_inferred_budget',
        'proofs':[{'url':f['url'],'quote':f['quote']} for f in proofs],
        'counterevidence':['unpaid_collaboration'] if status=='UNPAID' and not founder else [],
        'entrepreneurial':founder or equity,
        'needs_clarification':status=='CONTRADICTORY_TERMS'}


def inspect(source,kind,facts,identity,owner,name):
    request=[f for f in facts if f['field']=='request']
    def client_search(text):
        return bool(re.search(r'looking for (?:new )?clients|cerchiamo (?:nuovi )?clienti|seeking customers',text,re.I))
    def invitation(text):
        from .semantics import REFUSAL
        return bool((ASK.search(text) or STANDING.search(text)) and not REFUSAL.search(text) and not client_search(text))
    positive=any(invitation(f['quote']) for f in request)
    withheld=[];issues=[]
    for f in request:
        if (SELL.search(f['quote']) or client_search(f['quote'])) and not invitation(f['quote']):
            withheld.append({**f,'reason':'service_offer_is_not_client_request'})
    if withheld and kind in ('BUYER_DEMAND','AGENCY_PARTNERSHIP'):issues.append('buyer_category_conflicts_with_service_offer')
    if kind=='SUPPLIER_OFFER' and positive:issues.append('supplier_category_conflicts_with_request')
    source_role='UNKNOWN'
    if publisher_host(source['url']) or kind=='DIRECTORY':source_role='AGGREGATOR'
    elif source.get('editorial') or kind=='EDITORIAL':source_role='PUBLISHER'
    institution=identity_role(identity.get('name') or name or source.get('title',''))
    if institution in ('institution','program','territory'):source_role='INSTITUTION'
    subject_role='BUYER' if positive and kind in ('BUYER_DEMAND','AGENCY_PARTNERSHIP') and not withheld else 'SUPPLIER' if kind=='SUPPLIER_OFFER' or withheld and not positive else 'UNKNOWN'
    if source_role in ('AGGREGATOR','PUBLISHER','INSTITUTION') and not name:subject_role='UNKNOWN'
    organization={'role':'UNKNOWN','quote':None,'basis':'not_inferred_from_search_flow'}
    # Organization type requires a local self-description, not the selected flow.
    if owner and source.get('original'):
        for role,pattern in [('STARTUP',r'\b(?:we are (?:a )?|siamo (?:una )?)(?:startup|start-up)\b'),('AGENCY',r"\b(?:we are (?:a |an )?|siamo (?:una |un['’])?)(?:digital agency|web agency|agenzia(?: digitale| web)?)\b")]:
            match=re.search(pattern,source.get('text',''),re.I)
            if match:organization={'role':role,'quote':match[0],'basis':'original_self_description','url':source['url']};break
        if source_role=='UNKNOWN':source_role=organization['role'] if organization['role']!='UNKNOWN' else subject_role
    return {'source':{'role':source_role,'domain':domain(source['url']),'name':identity.get('name') if source_role in ('PUBLISHER','AGGREGATOR','INSTITUTION') else None},
        'subject':{'role':subject_role,'name':name,'identity_verified':bool(owner),'official_domain':identity.get('website') if owner else None},
        'organization':organization,'withheld':withheld,'issues':issues,'basis':'source_bound_interpretation_not_buying_probability'}


def webapp_feasibility(facts):
    """Require explicit constraints; 'AI can build it' is never feasibility."""
    proofs=[f for f in facts if f.get('original') and f['field'] in ('scope','feasibility')]
    text='\n'.join(f['quote'] for f in proofs)
    risky=re.search(r'medical records|cartelle cliniche|banking core|safety.critical|mission.critical|infrastruttura critica|24/7 SLA|PCI.DSS',text,re.I)
    facets={
        'scope':bool(re.search(r'(?:bounded|limited|single|circoscritt|limitat).{0,65}(?:workflow|process|portale|MVP|booking|prenotaz)|(?:MVP|portale).{0,65}(?:single workflow|funzioni limitate)',text,re.I)),
        'data_and_security':bool(re.search(r'no (?:payments or )?(?:sensitive|health|financial) data|nessun dato (?:sensibile|sanitario)|senza dati (?:sensibili|sanitari)',text,re.I)) and bool(re.search(r'authentication|autenticazione|access control|controllo accessi',text,re.I)),
        'integrations':bool(re.search(r'no external integrations|nessuna integrazione esterna|senza integrazioni esterne|only (?:CSV|documented API)|solo (?:CSV|API documentat)',text,re.I)),
        'maintenance':bool(re.search(r'(?:maintenance|manutenzione).{0,100}(?:agreed|included|planned|concordat|inclus|previst)',text,re.I)),
    }
    if re.search(r'(?:no|without|senza)\s+(?:authentication|autenticazione|access control)|(?:authentication|autenticazione|access control).{0,35}(?:not required|optional|non (?:richiest|previst))',text,re.I):
        facets['data_and_security']=False
    if re.search(r'(?:maintenance|manutenzione).{0,35}(?:not (?:agreed|included|planned)|non (?:concordat|inclus|previst))',text,re.I):
        facets['maintenance']=False
    return {'status':'RISKY' if risky else 'BOUNDED' if all(facets.values()) else 'UNKNOWN',
        'missing':[k for k,v in facets.items() if not v],'risk_quote':risky[0] if risky else None,
        'proofs':[{'quote':f['quote'],'url':f['url']} for f in proofs],
        'basis':'public_constraints_not_delivery_guarantee'}
