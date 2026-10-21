"""Commercial direction checks, never qualification or inferred buying intent."""
import re
from urllib.parse import urlsplit
from .schema import actor_span_valid

WEB=re.compile(r'wordpress|frontend|front.end|web\s*(?:site|app|developer|design)|sit[oi]\s*(?:web|internet)|nuovo sito|restyling sito|svilupp|e.?commerce|woocommerce|shopify|magento|react|portale|configuratore|online catalog(?:ue)?|catalogo (?:online|digitale)|software|ERP|CRM|\bPHP\b|jQuery|JavaScript|Next\.?js|\bHTML\b|\bSCSS\b|\bCSS\b|\bMVP\b',re.I)
ASK=re.compile(r'cerc\w*|richiest\w*|ricerch\w*|cerch\w*|looking for|seek\w*|need\w*|request\w*|hiring|recruit\w*|collabor\w*|partner\w*|commission\w*|fornitor\w*|tender',re.I)
EXTERNAL=re.compile(r'freelanc|partita\s*iva|p\.?\s*iva|contractor|external|estern|collabor|partner',re.I)
CHANGE=re.compile(r'nuov[oaie]\s+(?:prodott|mercat|march|line|serviz)|espansion|internazional|lancio|launch|new (?:product|market|brand|service)|rebrand|expand|distribuz|trasformazione digitale|digital transformation|migrazion|migration',re.I)
GAP=re.compile(r'gap|lacun|manca|assent|irrisolt|unresolved|inadequat|missing|verific|verify|check|confirm',re.I)
INSTITUTION=re.compile(r'unioncamere|camera di commercio|regione\s|progetti europei|enti controllati|amministrazione trasparente|fondi pubblici',re.I)
PORTFOLIO=re.compile(r'portfolio|casi studio|case stud|progetti (?:conclusi|realizzati)|completed projects',re.I)
REQUEST=re.compile(r'cerc\w*|cerch\w*|richiest\w*|ricerc\w*|looking for|seek\w*|need\w*|request\w*|hiring|recruit\w*|commission\w*|tender|collabora\w* con noi|diventa\w* partner|join (?:us|our)|\bunisciti\s+(?:al|nel)\s+(?:nostro\s+)?team\b',re.I)
TECHNICAL_COFOUNDER=re.compile(r'\b(?:technical\s+co[ -]?founder|co[ -]?founder\s+tecnic[oa]|cofondator[ei]\s+tecnic[oi]|socio\s+tecnico)\b',re.I)

def bounded_boolean_query(text):
    depth=0
    for token in re.findall(r'"[^\"]*"|\(|\)|\bOR\b',text):
        if token=='(':depth+=1
        elif token==')':
            depth-=1
            if depth<0:return False
        elif token=='OR' and depth==0:return False
    return depth==0

def positive_query(query):
    # Exclusions are not evidence of intent. Keep positive phrases only.
    return re.sub(r'(?<!\S)-(?:"[^"]*"|\S+)','',query)

def query_branches(text):
    """Expand bounded AND/OR expressions, keeping quoted phrases atomic.

    The policy must hold on each branch, not just somewhere in the query.
    A pathological expansion is rejected for replanning rather than truncated.
    """
    tokens=re.findall(r'"[^"]*"|\(|\)|[^\s()]+',text)
    position=0
    def alternatives():
        nonlocal position
        branches=conjunction()
        while position<len(tokens) and tokens[position]=='OR':
            position+=1;branches+=conjunction()
            if len(branches)>256:raise ValueError('query_boolean_expansion_too_large')
        return branches
    def conjunction():
        nonlocal position
        branches=[''];terms=0
        while position<len(tokens) and tokens[position] not in ('OR',')'):
            token=tokens[position];position+=1
            if token=='AND':continue
            if token=='(':
                part=alternatives()
                if position>=len(tokens) or tokens[position]!=')':raise ValueError('invalid_boolean_query')
                position+=1
            else:part=[token.strip('"') if not token.startswith(('site:','filetype:')) else '']
            if len(branches)*len(part)>256:raise ValueError('query_boolean_expansion_too_large')
            branches=[a+' '+b for a in branches for b in part];terms+=1
        if not terms:raise ValueError('empty_boolean_branch')
        return branches
    result=alternatives()
    if position!=len(tokens):raise ValueError('invalid_boolean_query')
    return result

def assess_query(q,flow,regions=None):
    text=positive_query(q.get('query',''));context=' '.join(str(q.get(k,'')) for k in ('objective','hypothesis','missing','success','stop_condition'))
    if not all(q.get(k) for k in ('query','objective','hypothesis','missing','success','stop_condition')):return {'allowed':False,'reason':'missing_commercial_hypothesis'}
    from .proactive import is_query,query_policy
    if is_query(q,flow):return query_policy(q,regions)
    if flow=='NEWS':
        from .news import query_policy as news_query
        return news_query(q)
    if flow in ('SOCIAL','LINKEDIN'):
        from .social import query_policy as social_query
        social=social_query(q)
        if not social['allowed']:return social
    if not bounded_boolean_query(text):return {'allowed':False,'reason':'ungrouped_or_or_unbalanced_query'}
    try:branches=query_branches(text)
    except ValueError as exc:return {'allowed':False,'reason':str(exc)}
    decisions=[assess_branch(branch,context,flow) for branch in branches]
    rejected=next((d for d in decisions if not d['allowed']),None)
    if rejected:return {**rejected,'branch_count':len(branches),'all_branches_checked':True}
    return {**decisions[0],'branch_count':len(branches),'all_branches_checked':True}

def assess_branch(text,context,flow):
    from .request_scope import query_direction
    direction=query_direction(text)
    if direction:return direction
    if PORTFOLIO.search(text):return {'allowed':False,'reason':'completed_portfolio_not_open_demand'}
    if flow=='AGENCIES' and re.search(r'web agency|digital agency|agenzi[ae] (?:web|digital)',text,re.I) and REQUEST.search(text) and EXTERNAL.search(text):
        return {'allowed':True,'intent':'external_collaboration','reason':'agency_invitation_stack_optional'}
    if re.search(r'co[ -]?founder|cofondator|socio tecnico',text,re.I) and REQUEST.search(text) and (TECHNICAL_COFOUNDER.search(text) or re.search(r'MVP|svilupp|developer|web|software|frontend|React',text,re.I)):
        return {'allowed':True,'intent':'entrepreneurial_opportunity','reason':'verify_role_and_terms_separately_from_paid_work'}
    if not WEB.search(text):return {'allowed':False,'reason':'no_digital_project_scope'}
    employment=bool(re.search(r'jobs|careers|vacanc|posizioni aperte|open positions?|lavora con noi|assunz|dipendent|employee',text,re.I))
    if (REQUEST.search(text) or employment) and EXTERNAL.search(text):return {'allowed':True,'intent':'external_collaboration','reason':'verify_requester_scope_and_currentness'}
    # Transformation/platform keywords alone also retrieve institutions and
    # suppliers. Only a specific change can justify an exploratory hypothesis.
    specific_change=re.search(r'nuov[oaie]\s+(?:prodott|mercat|march|line|serviz)|espansion|internazional|lancio|launch|new (?:product|market|brand|service)|rebrand|expand|migrazion|migration',text,re.I)
    if specific_change and GAP.search(context) and flow in ('AZIENDE','STARTUPS','NEWS'):
        return {'allowed':True,'intent':'business_signal_hypothesis','reason':'requires_company_signal_and_independent_digital_gap'}
    if employment:return {'allowed':False,'reason':'employment_without_external_collaboration'}
    if REQUEST.search(text):return {'allowed':True,'intent':'explicit_project_request','reason':'verify_actual_buyer_and_full_scope'}
    return {'allowed':False,'reason':'generic_web_topic_not_commercial_intent'}

def preflight(item):
    text=(item.get('title','')+'\n'+item.get('content',item.get('snippet','')))
    path=urlsplit(item.get('url','')).path.lower()
    # Archives can help discovery elsewhere, but they aren't one attributable
    # request/event. Do not spend an original-verification call on their titles.
    if re.search(r'/(?:tag|tags|category|categoria|categorie|archivio|archives|ricerca|search)(?:/|$)',path):
        return {'allowed':False,'reason':'collection_requires_specific_source','source_role':'COLLECTION','subject':'UNRESOLVED','actor':'UNRESOLVED'}
    if re.search(r'banche?[- ]dati.*(?:legisl|normativ)|leggi[-/]regionali|banca[-/]dati[-/]legisl',path+' '+text,re.I):
        return {'allowed':False,'reason':'legislation_not_commercial_request','source_role':'INSTITUTION','subject':'UNRESOLVED','actor':'UNRESOLVED'}
    explicit=bool(ASK.search(text) and WEB.search(text))
    signal=bool(CHANGE.search(text) and WEB.search(text))
    if explicit or signal:return {'allowed':True,'reason':'possible_commercial_evidence'}
    if INSTITUTION.search(text) or re.search(r'progetti-europei|misure-scadute|amministrazione-trasparente',path):return {'allowed':False,'reason':'institutional_without_commercial_signal'}
    if PORTFOLIO.search(text):return {'allowed':False,'reason':'completed_portfolio_without_new_request'}
    return {'allowed':True,'reason':'semantic_screening_required'}

def investigation(body,initial=False):
    if body.get('state') in ('REJECTED','VERIFIED') or body.get('suppressed'):return {'allowed':False,'reason':'conclusive_decision'}
    if body.get('relationship_check',{}).get('status')=='NONTECHNICAL_PARTNERSHIP':
        return {'allowed':False,'reason':'requested_role_not_unambiguously_technical'}
    if body.get('flow')=='NEWS':
        from .news import direction
        event=direction(body)
        if event:return event
    # A validated literal invitation may be labelled signal by the model.
    # Its field label must not prevent one original read. Never relabel the
    # evidence as a proved request or promote the candidate here.
    if initial and body.get('kind')=='AGENCY_PARTNERSHIP':
        for fact in body.get('facts',[]):
            text=fact.get('quote','')
            if fact.get('field')!='signal':continue
            invite=re.search(r'\b(?:cerchiamo|ricerchiamo|cercasi|looking for|seeking)\b[^.!?\n]{0,160}\b(?:collaborator\w*|freelanc\w*|contractor\w*)\b',text,re.I)
            excluded=re.search(r'gratuit|unpaid|volontar|non (?:cerchiamo|ricerchiamo)|no freelance|closed|chius[oa]',text,re.I)
            if invite and not excluded and WEB.search(text[max(0,invite.start()-100):invite.end()+240]):
                return {'allowed':True,'reason':'verify_cited_invitation_labelled_signal','goal':'request','evidence':text}
    requests=' '.join(f['quote'] for f in body.get('facts',[]) if f['field']=='request')
    if (initial and body.get('flow')=='AGENCIES' and body.get('kind')=='UNKNOWN'
        and body.get('source_role',{}).get('role') in ('UNKNOWN','AGENCY')
        and re.search(r'agenzia|agency|comunicazione|design',body.get('title',''),re.I)
        and re.search(r'cerchiamo collaboratori|looking for collaborators',requests,re.I)
        and body.get('relationship',{}).get('status')=='unknown'):
        return {'allowed':True,'reason':'resolve_named_agency_invitation_contract_and_scope',
                'goal':'contract','evidence':requests}
    # One original read may resolve a literal external invitation even when the
    # snippet omits the company name or technical role. It is never promotion.
    if initial and body.get('semantic_issues') and body.get('relationship',{}).get('status') in ('mixed','external_mentioned') and requests:
        return {'allowed':True,'reason':'resolve_cited_contract_contradiction','goal':'request','evidence':requests}
    if initial and body.get('kind')=='AGENCY_PARTNERSHIP' and ASK.search(requests) and EXTERNAL.search(requests):
        return {'allowed':True,'reason':'verify_external_invitation_scope_on_original','goal':'request','evidence':requests}
    if initial and body.get('kind') in ('BUYER_DEMAND','AGENCY_PARTNERSHIP') and ASK.search(requests) and WEB.search(requests):
        if body['kind']!='AGENCY_PARTNERSHIP' or EXTERNAL.search(requests):
            return {'allowed':True,'reason':'original_required_to_identify_requester','goal':'entity','evidence':requests}
    name=body.get('entity_name') or ''
    if not actor_span_valid(name,0,len(name)) or INSTITUTION.search(name):return {'allowed':False,'reason':'no_potential_buyer_identity'}
    aliases=body.get('identity_aliases',[]) if body.get('identity_verified') else []
    facts=body.get('facts',[]);entity=[f for f in facts if f['field']=='entity' and f['quote'].strip() in [name,*aliases]]
    if not entity:return {'allowed':False,'reason':'identity_not_cited'}
    requests=' '.join(f['quote'] for f in facts if f['field']=='request')
    signals=' '.join(f['quote'] for f in facts if f['field']=='signal')
    gaps=' '.join(f['quote'] for f in facts if f['field']=='digital_gap')
    kind=body.get('kind')
    partner_lead=(kind=='AGENCY_PARTNERSHIP' and body.get('identity_verified') and body.get('original')
        and ASK.search(requests) and EXTERNAL.search(requests)
        and body.get('source_role',{}).get('role') in ('AGENCY','UNKNOWN'))
    if kind in ('BUYER_DEMAND','AGENCY_PARTNERSHIP') and ASK.search(requests) and (WEB.search(requests) or partner_lead):
        if kind=='AGENCY_PARTNERSHIP' and not EXTERNAL.search(requests):return {'allowed':False,'reason':'agency_selling_not_partner_request'}
        goals=['official_domain','request','contract','technical','geography','publication','closed','contact','scope','feasibility']
    elif kind in ('COMPANY_SIGNAL','EDITORIAL') and name.casefold() in signals.casefold() and CHANGE.search(signals) and (WEB.search(signals) or gaps):
        goals=['official_domain','signal','digital_gap','existing_solution','scope','feasibility','contact']
    else:return {'allowed':False,'reason':'no_cited_commercial_reason'}
    missing=set(body.get('missing',[]))
    if kind in ('BUYER_DEMAND','AGENCY_PARTNERSHIP') and not body.get('contacts') and body.get('identity_verified'):
        missing.add('contact')
    if not body.get('identity_verified'):missing.add('official_domain')
    goal=next((g for g in goals if g in missing),None)
    if goal is None:return {'allowed':False,'reason':'no_decision_changing_check'}
    return {'allowed':True,'reason':'verify_missing_required_evidence','goal':goal,'evidence':requests or signals}


def verification_query(body,goal):
    """Search for a missing fact about this subject, not a new generic buyer.

    Only an independently verified domain can constrain the search. Query
    terms express the check, never an assertion about the company's needs.
    """
    from sales.db import domain
    name=(body.get('entity_name') or '').replace('"','')
    official=domain(body.get('official_domain') or '') if body.get('identity_verified') else ''
    prefix='site:'+official if official and goal!='official_domain' else '"'+name+'"'
    agency=body.get('kind')=='AGENCY_PARTNERSHIP'
    terms={'official_domain':'sito ufficiale contatti',
        'geography':'sede contatti' if agency else 'collaborazione remoto Italia',
        'contract':'collaborazioni freelance partita IVA',
        'publication':'("collabora con noi" OR "lavora con noi" OR careers) freelance' if agency else 'progetto sviluppo candidature data',
        'closed':'("collabora con noi" OR "lavora con noi" OR careers) candidature' if agency else 'progetto candidature aperte scadenza',
        'request':'progetto sviluppo web','technical':'sviluppo web requisiti',
        'contact':'contatti','scope':'progetto requisiti','feasibility':'progetto requisiti integrazioni',
        'signal':'nuovi prodotti espansione','digital_gap':'servizi catalogo vendita online'}
    return prefix+' '+terms.get(goal,goal)
