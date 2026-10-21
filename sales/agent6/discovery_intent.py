"""Search-spend checks, not company qualification.

Queries express an investigation, never proof of demand. Reject known generic
topic searches before spend, return an actionable reason to the planner, and
leave source interpretation to the original-document decision path.
"""
import re
from urllib.parse import urlsplit

from .commercial_policy import positive_query,query_branches,WEB,REQUEST,TECHNICAL_COFOUNDER
from .news import EVENT

APPLICATION=re.compile(r'candidatur|application|submit.{0,30}portfolio|invia.{0,30}portfolio|'
                       r'posizioni aperte|open positions?|vacancies|'
                       r'join (?:our|us)|lavora con noi|work with us|diventa.{0,20}partner|'
                       r'(?:accett\w*|accogli\w*|welcom\w*).{0,40}(?:collaborator|freelanc|professionist|contractor)',re.I)
EXTERNAL=re.compile(r'freelanc|contractor|estern|external|partita iva|p\.?\s*iva|collaborator',re.I)
EMPLOYEE_ONLY=re.compile(r'tempo indeterminato|permanent employee|employee only|solo dipendenti',re.I)
COMPLETED=re.compile(r'progetti (?:realizzati|conclusi)|completed projects|case stud|casi studio',re.I)
DIGITAL=re.compile(WEB.pattern+r'|sit[oi]\s+complet[oi]|rifacimento\s+(?:del\s+)?sito',re.I)
COMPANY_OPENING=re.compile(r'\b(?:apre|aprono|aprirà|apriranno|ha aperto|hanno aperto|opens?|opened)\b'
                          r'(?:\s+\w+){0,3}\s+(?:spacci[oa]|showroom|sed[ei]|stabiliment[oi]|'
                          r'negozi[oa]|punt[oi]\s+vendita|stores?|offices?)\b',re.I)
PROCUREMENT=re.compile(r'\b(?:selezion\w*|ricerc\w*|cerc\w*|richiest\w*)\s+(?:di\s+)?'
                       r'(?:un\s+|una\s+|nuov[oa]\s+)?(?:fornitor\w*|preventiv\w*)\b',re.I)
# Query directions, not patterns used to qualify facts on acquired originals.
EXTERNAL_COLLABORATION=re.compile(r'\bcollaborazion[ei]\s+estern[ae]\b|\bentra\s+nel\s+nostro\s+network\b',re.I)
COMPANY_CHANGE=re.compile(r'\b(?:acquisisce|acquisiscono|ha acquisito|acquisizione di|fusione con)\b'
    r'[^.!?\n]{0,70}\b(?:aziend\w*|impres\w*|produttor\w*|stabiliment\w*|marchi\w*)\b|'
    r'\b(?:avvia|avviano|lancia|lanciano)\b(?:\s+\w+){0,3}\s+(?:servizi\w*|line[ae]|canal[ei]|marchi\w*)\b',re.I)
COLLECTION_SUBJECT=r'(?:aziende|agenzie|imprese|professionisti|campeggi|camping|hotel|startup)'
COLLECTION_METADATA=re.compile(r'\b(?:selezione\s+di|migliori|portale\s+di|trova\s+tutti\s+i)\s+'
    +COLLECTION_SUBJECT+r'\b|\btop\s+\d+\s+'+COLLECTION_SUBJECT+r'\b|\b\d+\s+'
    +COLLECTION_SUBJECT+r'\s+(?:popolari|trovati|prenotabili)\b',re.I)
# Role hints, not source bans: only the publisher's index is excluded.
EDITORIAL_HOSTS={'ansa.it','ilgazzettino.it','corriere.it','ilsole24ore.com'}
# Observed collection routes, not domain blacklists. Specific company/event or
# careers pages on these hosts still pass; these indices cannot be the buyer.
COLLECTION_ROUTES={
    'agriturismo.it':re.compile(r'^/?$'),
    'visititaly.it':re.compile(r'^/agriturismo(?:/[a-z-]+\.aspx)?$'),
    'cantine.wine':re.compile(r'^/eventi$'),
    'randstad.com':re.compile(r'^/jobs/[^/]+/s-[^/]+(?:/[^/]+)*$'),
    'englishjobs.it':re.compile(r'^/in/[^/]+/[^/]+$'),
    'michaelpage.it':re.compile(r'^/jobs/[^/]+(?:/[^/]+)?$'),
    'devjobsscanner.com':re.compile(r'^/[^/]+-jobs-in-[^/]+$'),
    'applavoro.it':re.compile(r'^/annunci-lavoro(?:-[^/]+)?$'),
    'paginegialle.it':re.compile(r'^/[a-z_-]+/[a-z]{2}/[^/]+\.html$'),
}


def assess(proposal,flow,regions):
    """Check every Boolean branch, including saved/reused plans at dispatch."""
    text=positive_query(proposal['query'])
    if proposal.get('selection')=='verification':
        # These are bounded actions issued by the decision layer (or an exact
        # manual post reference), not model-generated discovery plans.
        return {'allowed':True,'intent':'bounded_subject_verification',
                'basis':'previous_decisive_question_not_new_demand'}
    try:branches=query_branches(text)
    except ValueError as exc:return {'allowed':False,'reason':str(exc)}
    outcomes=[]
    for branch in branches:
        from .request_scope import query_direction
        direction=query_direction(branch)
        if direction:
            return {**direction,'instruction':direction.get('correction')}
        scoped_collaboration=(EXTERNAL_COLLABORATION.search(branch) and DIGITAL.search(branch)
                              and not re.search(r'\b(?:come|guida|corso|corsi)\b',branch,re.I))
        request=bool(REQUEST.search(branch) or APPLICATION.search(branch) or PROCUREMENT.search(branch)
                     or scoped_collaboration)
        if EMPLOYEE_ONLY.search(branch) and not EXTERNAL.search(branch):
            return {'allowed':False,'reason':'query_seeks_employee_only',
                    'instruction':'Search external collaboration, not exclusively permanent employment.'}
        if COMPLETED.search(branch) and not request:
            return {'allowed':False,'reason':'query_seeks_completed_projects',
                    'instruction':'Seek a new request or a current company change; completed work is not open demand.'}
        if request and (DIGITAL.search(branch) or flow=='AGENCIES'
                        or (flow=='STARTUPS' and TECHNICAL_COFOUNDER.search(branch))):
            outcomes.append('request_or_invitation_to_verify')
        elif (EVENT.search(branch) or COMPANY_OPENING.search(branch) or COMPANY_CHANGE.search(branch)) and flow in ('AZIENDE','STARTUPS','NEWS'):
            outcomes.append('company_event_not_declared_demand')
        elif proposal.get('strategy')=='official_company_sector_region' and flow in ('AZIENDE','STARTUPS'):
            from .proactive import ACTIVITY
            from .query_pipeline import sector_terms
            from sales.research_rules import region_of
            # Discovery is not an industry whitelist. An explicit official-site
            # lookup plus a concrete sector also covers operating services that
            # are absent from ACTIVITY (C48: rental of aerial platforms).
            official_lookup=re.search(r'\bsit[oi]\s+ufficial[ei]\b|\bofficial\s+website\b',branch,re.I)
            if not (ACTIVITY.search(branch) or official_lookup) or not sector_terms(branch) or region_of(branch) not in regions:
                return {'allowed':False,'reason':'query_proactive_scope_missing',
                        'instruction':'Specify an operating sector and one configured territory, then verify a business need on the official site.'}
            outcomes.append('official_company_investigation_not_declared_demand')
        else:
            return {'allowed':False,'reason':'query_commercial_direction_missing',
                    'instruction':'The query itself must seek an invitation/request or a specific company event. '
                                  'For proactive discovery use official_company_sector_region with sector and territory. '
                                  'A generic web topic, provider partnership slogan or funding is not evidence of demand.'}
    return {'allowed':True,'intents':list(dict.fromkeys(outcomes)),
            'branch_count':len(branches),'basis':'search_direction_only_originals_still_required'}


def source_issue(item, proposal=None):
    """Do not send archive pages to single-company commercial evaluation."""
    path=urlsplit(item.get('url','')).path.lower().rstrip('/')
    from .social import platform,post_url
    if platform(item.get('url','')) and not post_url(item.get('url','')):
        return {'reason':'social_profile_not_specific_request','source_role':'PROFILE',
                'instruction':'Find a specific public post or job, not a person/company profile.'}
    if re.search(r'/(?:tag|tags|category|categoria|categorie|archivio|archives|ricerca|search)(?:/|$)',path):
        return {'reason':'collection_requires_specific_source','source_role':'COLLECTION',
                'instruction':'Find a specific original request or company event, not this archive.'}
    from sales.commercial.opportunity_view import PUBLISHERS
    from sales.db import domain
    host=domain(item.get('url',''))
    # A public institution's root page is an index, not a particular company's
    # event. Its specific articles remain eligible for source investigation.
    title=item.get('title','').strip()
    if not path and re.search(r'^(?:Home\s*[-|–]\s*)?(?:unioncamere\b|regione (?:del )?|camera di commercio\b|comune di\b|gazzetta ufficiale\s*$)',title,re.I):
        return {'reason':'institutional_index_requires_specific_source','source_role':'COLLECTION',
                'instruction':'Find the specific article and named business; the institutional homepage is not a buyer.'}
    # Only discovery is routed here. A specifically requested identity/source
    # verification may legitimately read an encyclopedic or instructional page.
    if not (proposal or {}).get('selection')=='verification':
        title=item.get('title','').strip()
        invitation=bool(re.search(r'cerchiamo|cercasi|cerco|we are hiring|join our team|'
                                  r'collabora con noi|lavora con noi|candidatur',
                                  title+' '+item.get('content',item.get('snippet','')),re.I))
        category=None
        if host.endswith('wikipedia.org') and re.fullmatch(r'/wiki/(?:19|20)\d{2}',path):
            category='encyclopedic_year'
        elif re.search(r'^corso\b|^corsi\b|^tecnico specializzato\b',title,re.I) and re.search(r'/cors[oi](?:[-/]|$)',path):
            category='training_offer'
        elif re.search(r'\bbonus\b',title,re.I) and re.search(r'\bisee\b',title,re.I):
            category='personal_benefits_information'
        elif re.search(r'\bBOT\b',title) and re.search(r'\basta|emission|obbligazion',title+' '+path,re.I):
            category='sovereign_bond_information'
        elif re.search(r'/film/(?:19|20)\d{2}/?$',path):
            category='film_year_catalog'
        if category and not invitation:
            return {'reason':'discovery_source_outside_commercial_scope','source_role':category,
                    'basis':'search_metadata_routing_not_company_rejection',
                    'observed_title':title[:500],
                    'instruction':'Seek a specific company activity, event or external invitation; this result is an informational collection or offer, not that source.'}
    if host in COLLECTION_ROUTES and COLLECTION_ROUTES[host].fullmatch(path):
        return {'reason':'collection_requires_specific_source','source_role':'COLLECTION',
                'instruction':'This route lists businesses or events; seek a specific company page or request. The domain is not excluded.'}
    publisher=host in PUBLISHERS or any(host==h or host.endswith('.'+h) for h in EDITORIAL_HOSTS)
    if publisher and path in ('','/economia','/news','/notizie'):
        return {'reason':'publisher_index_requires_specific_source','source_role':'COLLECTION',
                'instruction':'The publisher homepage is not the customer; seek the specific article and named company.'}
    return None


def source_priority(item, flow, proposal):
    """Reading order only. Absence of request words never rejects a company."""
    title=item.get('title','');text=title+' '+item.get('content',item.get('snippet',''))
    path=urlsplit(item.get('url','')).path
    if proposal.get('selection')=='verification':
        return {'value':0,'basis':'bounded_or_proactive_reading'}
    if COLLECTION_METADATA.search(text):
        return {'value':-1,'basis':'indexed_business_collection_read_after_possible_official_sites',
                'effect':'reading_order_only_no_company_rejection'}
    if proposal.get('strategy')=='official_company_sector_region':
        return {'value':0,'basis':'bounded_or_proactive_reading'}
    # Metadata only changes reading order, never a company's eligibility. The
    # explicit employer label prevents treating wellness "spa" or a client in
    # a portfolio as the source owner's legal form.
    employer_spa=re.search(r'\b(?:Azienda|Employer|Hiring company)\s*:\s*[^\n.!?]{1,100}?\b(?:SPA\b|S\.[ ]*p\.[ ]*A\.)',text)
    candidate_collection=re.search(r'\b\d+\s+CV\s+trovati\b|\bprofili candidati\b',title,re.I)
    if employer_spa or candidate_collection:
        return {'value':-2,'basis':'indexed_employer_exclusion_to_verify' if employer_spa else 'candidate_profiles_not_buyer_requests',
                'effect':'reading_order_only_no_company_rejection'}
    if flow=='NEWS' and re.search(r'\bCCRL\b|\bcontratto collettivo\b|\bBollettino Ufficiale\b',title,re.I):
        return {'value':-1,'basis':'collective_or_institutional_news_read_after_company_events',
                'effect':'reading_order_only_no_company_rejection'}
    # An index can juxtapose an invitation in one listing with a technical role
    # in another. Such disconnected snippets must not earn the request bonus.
    fragments=[title]+re.split(r'\.{3,}|…|\s[·•]\s|\n',item.get('content',item.get('snippet','')))
    related=[part for part in fragments if (REQUEST.search(part) or APPLICATION.search(part))
             and (DIGITAL.search(part) or re.search(r'web agenc(?:y|ies)|developer',part,re.I))]
    invitation=bool(REQUEST.search(text) or APPLICATION.search(text))
    agency=re.search(r'\bweb agenc(?:y|ies)\b|\bagenzia\s+(?:web|digital\w*)\b',text,re.I)
    if any(EXTERNAL.search(part) for part in related):
        return {'value':3,'basis':'external_technical_invitation_read_first_not_proven_demand'}
    if invitation and agency and flow=='AGENCIES':
        return {'value':2,'basis':'digital_agency_application_original_to_verify'}
    if related:
        return {'value':2,'basis':'indexed_invitation_to_verify_not_proven_demand'}
    if flow in ('AGENCIES','SOCIAL','STARTUPS') and re.search(r'/(?:careers|jobs|lavora-con-noi|collabora-con-noi)(?:/|\.(?:php|html?)$|$)',path,re.I):
        return {'value':1,'basis':'specific_careers_source_to_verify'}
    if not invitation and re.search(r'\b(?:realizziamo|offriamo|i nostri servizi|consulenza per|guida al|come costruire)\b',text,re.I):
        return {'value':-1,'basis':'apparent_supplier_or_guide_read_after_request_sources'}
    return {'value':0,'basis':'unresolved_metadata_not_negative_evidence'}
