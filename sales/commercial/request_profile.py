"""Typed request hints; dates and publication/availability never conflated."""
import re
from datetime import date,datetime
from .intent import request_clause,request_nature
from .relevance import technical_request

def freshness(value=None,*,verified=False,text='',index_hint=False,today=None):
    today=today or date.today();parsed=None
    if value:
        for fmt in ('%Y-%m-%d','%d/%m/%Y'):
            try:parsed=datetime.strptime(str(value)[:10],fmt).date();break
            except ValueError:pass
    age=(today-parsed).days if parsed else None
    closed=bool(re.search(r'posizione chiusa|annuncio scaduto|ricerca conclusa|applications closed',text,re.I))
    open_claim=bool(re.search(r'candidature aperte|posizione aperta|applications open',text,re.I))
    return {'publication_date':parsed.isoformat() if parsed and verified else None,'date_status':'VERIFIED' if parsed and verified else 'INFERRED' if parsed else 'UNKNOWN',
      'index_date_hint':str(value) if index_hint and value else None,'date_hint':parsed.isoformat() if parsed and not verified else None,
      'availability':'CLOSED' if closed else 'OPEN_DECLARED' if open_claim and verified else 'UNVERIFIABLE',
      'priority_hint':'closed' if closed else 'recent' if age is not None and 0<=age<=60 else 'historical' if age is not None and age>180 else 'unknown',
      'limits':['Data di indicizzazione distinta da pubblicazione; apertura non verificata per semplice data recente.']}

def agency_signal(text):
    clause=request_clause(text)
    if collaboration_signal(text) and not (clause and technical_request(clause)) and not re.search(r'sviluppatori web|team tech|sviluppatori.*freelance',text,re.I):return 'B_GENERIC_EXTERNAL_COLLABORATION'
    if technical_request(text) and re.search(r'collaboriamo con|in particolare, collaboriamo|che tipo di partner cerchiamo',text,re.I) and re.search(r'sviluppatori web|team tech|sviluppatori.*freelance',text,re.I):return 'B_DECLARED_EXTERNAL_PRACTICE'
    if clause and technical_request(clause) and re.search(r'freelance|estern|partita iva|collabor',clause,re.I):return 'A_OPEN_TECHNICAL_REQUEST'
    if request_nature(text)=='GENERAL_COLLABORATION_POLICY' and technical_request(text):return 'B_DECLARED_EXTERNAL_PRACTICE'
    if re.search(r'nuove collaborazioni|collaboratore esterno|partner tecnico',text,re.I):return 'C_INDIRECT_AMBIGUOUS'
    if re.search(r'offriamo|realizziamo|servizi|sviluppo',text,re.I):return 'E_SERVICE_OFFER'
    return 'D_NO_SIGNAL'

def relationship(text):
    """Workload is not a contract. Retain both positive and conflicting clauses."""
    clauses=re.split(r'(?<=[.!?])\s+|\n+',text)
    external=[];employee=[];work=[]
    for clause in clauses:
        if re.search(r'freelance|partita\s*iva|collaborazione a progetto|project.based|external developer',clause,re.I):external.append(clause.strip())
        if re.search(r'tempo (?:indeterminato|determinato)|contratto (?:di lavoro )?(?:dipendente|subordinato)|assunzione|apprendistato|tirocinio|employee contract',clause,re.I) and not re.search(r'non (?:cerchiamo|offriamo|prevediamo)|no employment',clause,re.I):employee.append(clause.strip())
        if re.search(r'full[ -]?time|tempo pieno|part[ -]?time|orari flessibili',clause,re.I):work.append(clause.strip())
    rel='AMBIGUOUS' if external and employee else 'EXTERNAL' if external else 'EMPLOYEE' if employee else 'UNKNOWN'
    contract='UNKNOWN' if rel=='AMBIGUOUS' else 'PROJECT_BASED' if external and re.search(r'collaborazione a progetto|project.based',text,re.I) else 'FREELANCE' if external else 'EMPLOYMENT' if employee else 'UNKNOWN'
    workload='FULL_TIME' if re.search(r'full[ -]?time|tempo pieno',text,re.I) else 'PART_TIME' if re.search(r'part[ -]?time',text,re.I) else 'FLEXIBLE' if re.search(r'orari flessibili|autonomia nell.organizzazione',text,re.I) else 'UNKNOWN'
    return {'contract_type':contract,'workload':workload,'employment_relationship':rel,
            'evidence':{'external':external,'employee':employee,'workload':work},'contradictory':rel=='AMBIGUOUS'}

def collaboration_signal(text):
    # A vendor inviting freelancers to resell its services is not hiring them.
    if re.search(r'(?:proporre ai propri clienti|rivendere (?:i nostri|servizi)|referente strutturato|servizi per freelance)',text,re.I):return False
    if re.search(r'(?:effettuiamo|avviamo|valutiamo|accettiamo) collaborazioni con.{0,60}(?:freelanc|professionisti esterni)|collaboriamo con.{0,60}professionisti',text,re.I):return True
    # Recipient must be external professionals, not customers buying services.
    return bool(re.search(r'(?:collaboriamo con|cerchiamo|valutiamo|ricerchiamo|cerchiamo partner di sviluppo).{0,80}(?:freelance|professionisti.{0,30}partita iva|collaborazioni esterne|sviluppatori esterni|partner (?:tecnici|di sviluppo))',text,re.I) or re.search(r'cerchiamo partner di sviluppo',text,re.I))

def agency_supplier_pitch(text):
    """A supplier addressing agencies is not an agency commissioning work.

    Local request clauses take precedence: a seller may also be recruiting.
    Search metadata only controls admission, never proves a relationship.
    """
    clause=request_clause(text) or ''
    if clause and technical_request(clause) and re.search(r'cerchiamo|ricerchiamo|siamo alla ricerca|looking for',clause,re.I):return False
    return bool(re.search(r'(?:gestiamo|offriamo|forniamo).{0,50}(?:sviluppo|supporto|design).{0,35}per (?:le )?agenzie|(?:sei|siete) una? web agency.{0,90}(?:supporto|aiut)|(?:programmatore|sviluppatore) wordpress freelance per agenzie',text,re.I))

def startup_type(text):
    if re.search(r'co[ -]?founder|cofondator',text,re.I):return 'TECHNICAL_COFOUNDER'
    if relationship(text)['employment_relationship']=='EMPLOYEE' or re.search(r'tirocinio',text,re.I):return 'EMPLOYMENT_ROLE'
    if request_clause(text) and re.search(r'freelance|partita iva|esterno',text,re.I) and re.search(r'retribuit|compenso|pagat|paid',text,re.I):return 'PAID_FREELANCE_PROJECT'
    if request_clause(text) and re.search(r'partner tecnico|collaborazione tecnica',text,re.I):return 'TECHNICAL_PARTNERSHIP'
    return 'UNKNOWN'

def hosted_request(page):
    """A bounded JobPosting or labelled company slot, not the publisher footer."""
    from sales.extract import parse_page
    from sales.db import domain
    p=parse_page(page)
    from .context import channels
    visible=channels(page)['visible']
    text='\n'.join(u['text'] for u in visible['units'] if not u.get('excluded'))
    job=p.get('job') or {};org=job.get('hiringOrganization') or {}
    org_url=(org.get('sameAs') or org.get('url')) if isinstance(org,dict) else None
    from .opportunity_view import PUBLISHERS
    if isinstance(org_url,str) and domain(org_url)==domain(page['url']) and domain(page['url']) not in PUBLISHERS:return None
    name=org.get('name') if isinstance(org,dict) else None
    basis='JobPosting.hiringOrganization'
    if not name:
        m=re.search(r'(?:^|\n)\s*(?:Azienda|Company|Committente)\s*:\s*\n?\s*([^\n]{2,90})',text,re.I)
        if m:name=m[1].strip();basis='labelled_request_company'
    if not name and domain(page['url']) in PUBLISHERS:
        from .indexed_jobs import parse_indexed_job
        title=re.sub(r'\s*\|\s*(?:beBee|LinkedIn)\s*$','',p['title'],flags=re.I)
        hint=parse_indexed_job({'url':page['url'],'title':title})
        candidate=hint.get('company_candidate')
        # A title slot plus an exact standalone company line in the original
        # page, never the slug or a footer alone.
        if candidate and re.search(r'(?:^|\n)\s*'+re.escape(candidate)+r'\s*(?:\n|$)',text,re.I):name=candidate;basis='original_title_and_company_line'
    if not name or not (job or re.search(r'/annunci/|/jobs/|/offerta/',page['url'])):return None
    if not technical_request(text):return None
    raw_date=job.get('datePosted')
    if not raw_date:
        m=re.search(r'Data Annuncio:\s*(\d{2}/\d{2}/\d{4})',text,re.I)
        if m:raw_date=m[1]
    publisher=p['doc'].meta.get('og:site_name') or domain(page['url'])
    return {'publisher':publisher,'publisher_url':page['url'],'requesting_actor':name,'identity_verified':False,'basis':basis,
      'request_type':startup_type(text),'freshness':freshness(raw_date,verified=True,text=text),
      'relationship':relationship(text),
      'employment_full_time':bool(re.search(r'full[ -]?time|tempo pieno',text,re.I)),
      'roles':['SOURCE_PUBLISHER','REQUESTING_COMPANY'],'scope':'source_attribution_only_not_official_identity'}
