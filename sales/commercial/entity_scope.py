"""Conservative attribution boundaries over originals; no network or name guessing."""
import re
from sales.extract import parse_page,nodes,types
from sales.db import domain

MULTI=re.compile(r'/(?:aziende-associate|imprese-associate|schede-associati)/|catalog[ou]e?\w*\s+(?:degli\s+)?espositori|(?:elenco|lista)\s+(?:degli\s+)?espositori|exhibitor\s+(?:list|catalog)|catalogo-espositori|catalogo\s+(?:degli\s+)?autori|bibliografi[ae]|bibliograph',re.I)
LISTING=re.compile(r'(?:elenco|directory|lista)\s+(?:delle\s+|di\s+)?(?:aziende|imprese)|offerte di lavoro disponibili|tutti gli annunci',re.I)

def publication_role(title, text):
    """Explicit publisher self-description, not a customer's incidental mention.

    Shared by discovery triage and identity scope so a portal's listed firms
    cannot become its owner. No domain blacklist or interpretation of demand.
    """
    portal=r'(?:il\s+)?portale\s+(?:dell[’\']imprenditoria|delle\s+(?:piccole\s+e\s+medie\s+)?(?:industrie|imprese|aziende))\b'
    if re.search(r'(?:^|[.|–—]\s*)'+portal,title,re.I) or re.search(r'^\s*'+portal,text[:4000],re.I|re.M):
        return 'directory'
    # Paginated company search, supported by two distinct legal company labels.
    labels=set(re.findall(r'^\s*([^\n]{2,100}\bS\.?\s*r\.?\s*l\.?)\s*$',text,re.I|re.M))
    if (len(labels)>=2 and re.search(r'La ricerca ha prodotto\s+\d+\s+risultati',text[:1000],re.I)
            and re.search(r'Pagine totali:\s*\d+',text[:1000],re.I)):
        return 'multi_company_catalog'
    if (re.match(r'^\s*(?:Azienda\s+(?:USL|Unità Sanitaria Locale)|AUSL)\b',title,re.I)
            or (re.search(r'^\s*Servizio Sanitario Regionale\b',text[:1800],re.I|re.M)
                and re.search(r'^\s*Azienda Unità Sanitaria Locale\b',text[:1800],re.I|re.M))):
        return 'institution'
    return None

def profile(page):
    p=parse_page(page);title=p['title'];path=page['url'];text=p['text']
    jobs=[n for n in nodes(p['doc'].schemas) if 'JobPosting' in types(n)]
    items=[n for n in nodes(p['doc'].schemas) if 'ItemList' in types(n)]
    companies=[n for n in nodes(p['doc'].schemas) if set(types(n))&{'Organization','Corporation','LocalBusiness'}]
    external={domain(n.get('url','')) for n in companies if n.get('url') and domain(n['url'])!=domain(path)}
    employers={str((j.get('hiringOrganization') or {}).get('name') or (j.get('hiringOrganization') or {}).get('url') or '') for j in jobs if isinstance(j.get('hiringOrganization'),dict)}
    multi_jobs=len(jobs)>1 and (len(employers)!=1 or '' in employers)
    from .admission import listing_url
    publication=publication_role(title,text)
    multi=bool(publication in ('directory','multi_company_catalog') or listing_url(path) or MULTI.search(title+' '+path) or LISTING.search(title) or multi_jobs or (items and len(external)>1))
    role='MULTI_COMPANY_CATALOG' if multi else 'UNKNOWN'
    return {'page_role':role,'domain_role':'UNKNOWN','multi_subject':multi,
            'actor_status':'ACTOR_UNRESOLVED' if multi else 'UNRESOLVED',
            'publisher':domain(path),'source_url':path,
            'roles':['PUBLISHER','MENTIONED_COMPANY','EXHIBITOR','CONTACT_OWNER'] if multi else ['SOURCE_OWNER'],
            'basis':'Explicit listing structure/title; subject records must not be merged.' if multi else 'Owner must be established independently.'}

def unresolved(page,reason=None):
    scope=profile(page)
    return {'name':domain(page['url']),'website':None,'source_url':page['url'],'identity_status':'unknown',
            'contacts':[],'locations':[],'region':None,'country':None,'legal_id':None,'group':'direct',
            'basis':reason or 'ACTOR_UNRESOLVED: fonte multisoggetto, dati dei soggetti non aggregati.',
            'identity_evidence':[],'identity_conflicts':[],'domain_verification':'uncertain','entity_scope':scope,
            'attribution':{'publisher':domain(page['url']),'domain_owner':None,'client':None,'role':'ACTOR_UNRESOLVED'}}

def owner_fact(text,actor):
    """Reject an explicit third-party fact; absence of attribution is not proof."""
    if re.search(r'\b(?:client\w*|fornitor\w*|espositor\w*|partner|customer|supplier|rivenditor\w*|distributor\w*|investitor\w*|investor)\b',text,re.I):return False
    from .indexed_jobs import same_company_name
    # Named subjects may follow an intro, and may use “is/è” instead of “has”.
    subjects=re.findall(r"(?:^|[.!?]\s*|\bToday,\s*|\bOggi,\s*)(?:\d+ years on,\s*)?([A-Z][\w &.-]{1,65}?)\s+(?:e['’]|è|is|ha|conta|impiega|has|employs)(?=\s|$)",text)
    generic={'we','our company','la nostra azienda','today','oggi'}
    if any(not same_company_name(s,actor) and s.strip().casefold() not in generic for s in subjects):return False
    # Named subject before a workforce claim must agree with the known owner.
    m=re.search(r'^\s*([A-Z][\w &.-]{2,70}?)\s+(?:ha|conta|impiega|has|employs)\b',text)
    if m and actor:
        from .indexed_jobs import same_company_name
        if not same_company_name(m[1],actor) and m[1].lower() not in ('oggi','today','la nostra azienda','our company'):return False
    return True
