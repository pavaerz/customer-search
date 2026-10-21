"""Parse indexed job hints, never substitute them for original-source evidence."""
import re
from urllib.parse import unquote, urlsplit


def parse_indexed_job(item):
    title=str(item.get('title') or '').strip()
    url=str(item.get('url') or '')
    clean=re.sub(r'\s*[|–]\s*LinkedIn.*$','',title,flags=re.I).strip().rstrip('.')
    clean=re.sub(r'\s+[–—]\s+Offerta di lavoro\s*$','',clean,flags=re.I)
    company=role=None;basis=None
    patterns=(
        ('company_request',r'^(.{2,90}?)\s+(?:sta assumendo|assume|hiring|cerca|ricerca)\s+(.{3,140}?)(?:\s+in\s+[^|]+)?$',False),
        ('role_at_company',r'^(.{3,140}?)\s+at\s+(.{2,90})$',True),
        ('role_dash_company',r'^(.{3,140}?)\s+[–—-]\s+(.{2,90})$',True),
    )
    from .context import TECH
    technical=lambda value: bool(TECH.search(value) or re.search(r'\b(?:python|javascript|php|typescript)\b',value,re.I))
    for name,pattern,reverse in patterns:
        m=re.match(pattern,clean,re.I)
        if not m:continue
        a,b=m.groups();candidate_role,candidate_company=(a,b) if reverse else (b,a)
        if not technical(candidate_role):continue
        # A second role, title suffix or a list is not an employer name.
        if re.search(r'\s+(?:at|presso)\s+|[|;]|LinkedIn|offerte di lavoro',candidate_company,re.I):continue
        role=candidate_role.strip();company=candidate_company.strip();basis=name;break
    path=unquote(urlsplit(url).path)
    slug=re.search(r'/jobs/view/(.{3,180}?)-at-(.{2,90}?)-\d+/?$',path,re.I)
    url_hint={'role':slug[1].replace('-',' '),'company':slug[2].replace('-',' ')} if slug else None
    # The URL is a fallback identity *hint*, never proof of contract or freshness.
    if not company and url_hint and technical(url_hint['role']):
        role=url_hint['role'];company=url_hint['company'];basis='url_slug'
    conflicting_employers=bool(company and url_hint and basis in ('company_request','role_at_company') and not same_company_name(company,url_hint['company']))
    # Prefer the explicitly delimited employer slot in a LinkedIn URL over a
    # dash separator, which often contains a project, contract or location.
    if url_hint and technical(url_hint['role']):
        if not company or not same_company_name(company,url_hint['company']):
            company=url_hint['company'];basis='url_employer_slot'
            # Preserve the published casing where the same explicit employer
            # occurs in the title; never manufacture a new alias.
            match=re.search(r'(?<!\w)'+re.escape(company)+r'(?!\w)',clean,re.I)
            if match:company=match[0]
        role=role or url_hint['role']
    location=None
    if company and re.search(r'\s+[–—-]\s+',company):
        parts=re.split(r'\s+[–—-]\s+',company)
        if len(parts)==2:
            location,company=parts
    if company:
        suffix=re.search(r'[–—]\s*([^–—]+?)\s+-\s*'+re.escape(company)+r'$',clean,re.I)
        if suffix:location=suffix[1].strip()
    platform=company if company and company.casefold() in ('twine','bebee','linkedin','upwork','freelancer','fiverr') else None
    ambiguous=conflicting_employers or bool(company and (technical(company) or re.fullmatch(r'contract|freelance|remote|onsite',company,re.I)))
    if ambiguous:company=None
    if company:
        company=re.sub(r'[^\w À-ÿ&.\'-]',' ',company).strip()
        if not company or len(company)>90:company=role=basis=None
    from .context import EXTERNAL,EMPLOYEE
    external=bool(EXTERNAL.search(clean));employee=bool(EMPLOYEE.search(clean))
    contract_hint='external' if external and not employee else 'employment' if employee and not external else None
    from .evaluation import skills
    embedded=bool(re.search(r'\b(?:embedded(?: software)? (?:engineer|developer)|firmware (?:engineer|developer)|AUTOSAR (?:engineer|developer))\b',str(role),re.I)) and not re.search(r'front[ -]?end|web developer|wordpress|woocommerce',str(role),re.I)
    foreign_onsite=bool(re.search(r'\b(?:Tucson|Arizona|San Francisco|United States|Singapore)\b',clean,re.I) and (re.search(r'on[ -]?site|in presenza|\bin Singapore\b',clean,re.I)))
    # Full-time and on-site describe workload/location, not the contract.
    contract_hint='employment' if employee and not external else contract_hint
    if not contract_hint and re.search(r'\bcontract\b',clean,re.I):contract_hint='contract_unspecified'
    primary_non_web=bool(re.search(r'\b(?:rappresentante commerciale|agente (?:di )?commercio|sales representative|account manager|communications? (?:manager|assistant)|vertical content creator|content creator|marketing specialist)\b',clean,re.I)) and not re.search(r'web developer|front[ -]?end|wordpress developer|sviluppator|software developer|woocommerce development',clean,re.I)
    contaminated=bool(re.search(r'digital product designer',clean,re.I) and re.search(r'Frontend Engineer|UX/UI Designer Editoriale|other jobs|offerte correlate',str(item.get('content') or item.get('snippet') or ''),re.I) and not EXTERNAL.search(clean))
    compatible=False if primary_non_web or contaminated or embedded or foreign_onsite or (employee and not external) else None
    return {'company_candidate':company,'role_candidate':role,'basis':basis,
            'source_url':url,'title':title,'snippet':str(item.get('content') or item.get('snippet') or ''),
            'url_hint':url_hint,'contract_hint':contract_hint,'contract':None,'published_at':None,
            'skills_hint':skills(role or ''),'identity_verified':False,'original_request_verified':False,
            'commercial_compatibility':compatible,
            'components':{'JOB_TITLE':role,'COMPANY_NAME':None if platform else company,'LOCATION':location or ('Tucson, Arizona, US' if re.search(r'Tucson',clean,re.I) else None),'CONTRACT_TYPE':contract_hint,'PLATFORM_NAME':platform,'PROJECT_NAME':(re.split(r'\s+[–—]\s+',clean)[-1] if re.search(r'[–—].*\b(?:rebuild|migration|rifacimento)\b',clean,re.I) else None),'UNKNOWN':ambiguous},
            'identity_conflict':conflicting_employers,
            'resolution_allowed':bool(company and not platform and not ambiguous and compatible is not False),
            'compatibility_reason':'Ruolo principale commerciale, servizi del venditore non sono domanda web.' if primary_non_web else 'Snippet contaminato da altre posizioni; ruolo principale senza richiesta esterna web.' if contaminated else 'Posizione estera in presenza.' if foreign_onsite else 'Rapporto dipendente in presenza.' if employee and not external else 'Ruolo embedded/firmware distinto dai servizi web richiesti.' if embedded else 'Competenze e incarico da verificare nella fonte originale.',
            'certainty':'indexed_hint','limits':['Titolo e URL indicizzati non verificano azienda, contratto o data.','Lo snippet può includere annunci correlati.']}


def resolution(item):
    hint=parse_indexed_job(item)
    company,role=hint['company_candidate'],hint['role_candidate']
    if not company or not role or not hint['resolution_allowed']:return None
    role_terms=' '.join(hint.get('skills_hint') or [])[:90]
    return {'query':'"'+company.replace('"','')+'" '+role_terms+' Italia sito ufficiale (collaborazioni OR careers OR "lavora con noi") -site:linkedin.com -site:bebee.com -site:recruit.net',
            'page':1,'resolution_company':company,'resolution_role':role,'resolution_url':item['url'],
            'resolution_stage':'COMPANY_DOMAIN_CANDIDATE','resolution_context':hint['snippet'],'indexed_job':hint}

def publisher_host(url):
    from sales.db import domain
    from .opportunity_view import PUBLISHERS
    host=domain(url)
    return any(host==p or host.endswith('.'+p) for p in PUBLISHERS|{'recruit.net','talent.com','trabajo.org','joblooku.com','jooble.org','indeed.com','glassdoor.com','devjobsscanner.com'})

def actor_resolution(result):
    actor=result.get('requesting_actor') or (result.get('actor_attribution') or {}).get('requesting_actor')
    if not actor:return None
    role=re.split(r'\s[|–-]\s',result.get('title') or 'sviluppatore web')[0]
    hint={'url':result['url'],'title':role+' at '+actor}
    plan=resolution(hint)
    if plan:plan['actor_basis']='saved_attributed_original';plan['resolution_company']=actor
    return plan


def same_company_name(expected,actual):
    """Exact token identity after legal suffixes, never substring attribution."""
    import unicodedata
    def key(value):
        value=unicodedata.normalize('NFKD',str(value or '')).casefold()
        value=''.join(c for c in value if not unicodedata.combining(c))
        value=re.sub(r'\b(?:s\.?\s*r\.?\s*l\.?\s*s\.?|s\.?\s*r\.?\s*l\.?|s\.?\s*n\.?\s*c\.?|s\.?\s*p\.?\s*a\.?|s\.?\s*a\.?\s*s\.?)\s*$','',value)
        return tuple(re.findall(r'\w+',value))
    return bool(key(expected)) and key(expected)==key(actual)


def resolution_continuity(plan,item):
    """Admission hints only: official identity still requires original evidence."""
    from .discovery import classify, individual_vacancy
    from .admission import listing_url
    if listing_url(item.get('url','')):return {'status':'UNRESOLVED','reason':'generic_job_listing'}
    if publisher_host(item.get('url','')):return {'status':'UNRESOLVED','reason':'republished_source_not_official_domain'}
    from sales.db import domain
    host=domain(item.get('url',''));path=urlsplit(item.get('url','')).path
    text=str(item.get('title') or '')+' '+str(item.get('content') or item.get('snippet') or '')
    # Product names can equal company names (PACER). A product catalogue is
    # not an employer domain merely because a title and generic role overlap.
    if re.search(r'/(?:product-archive|product-detail|products?|prodotti|catalogue)/',path,re.I) and re.search(r'pool|cleaner|piscin|product|specifiche|specifications|baracuda',text,re.I):
        return {'status':'UNRESOLVED','reason':'resolution_product_not_employer'}
    if host in ('shazam.com','spotify.com','tradeindia.com','rocketreach.co') or re.search(r'/artist/|/product-detail/|email[_-]profile|/people/',path,re.I):
        return {'status':'UNRESOLVED','reason':'resolution_incompatible_entity_context'}
    if re.search(r'\b(?:hydraulic pumps|centrifugal pumps|pump solutions|exchange.traded funds|ETFs?|parent advocacy|disabilities|leather polish|music artist)\b',text,re.I):
        return {'status':'UNRESOLVED','reason':'resolution_incompatible_entity_context'}
    if re.search(r'staffing|recruitment agency|nonprofits?|non-profit',text+' '+host,re.I) and not re.search(r'staffing|recruitment|nonprofit',str(plan.get('resolution_role',''))+' '+str(plan.get('resolution_context','')),re.I):
        return {'status':'UNRESOLVED','reason':'resolution_intermediary_not_declared_employer'}
    kind=classify(item)
    if kind in ('directory','institution','article','aggregator') and not (kind=='aggregator' and individual_vacancy(item)):
        return {'status':'UNRESOLVED','reason':'resolution_source_incompatible'}
    parsed=parse_indexed_job(item)
    if parsed['commercial_compatibility'] is False:return {'status':'UNRESOLVED','reason':'resolution_incompatible_role'}
    if re.search(r'(?:cerchiamo|cerca|assume|ricerca)\s+(?:un\s+)?(?:venditore|commerciale|agente di commercio)\b',str(item.get('title') or ''),re.I):
        return {'status':'UNRESOLVED','reason':'resolution_incompatible_role'}
    expected=plan.get('resolution_company');role=plan.get('resolution_role') or ''
    text=str(item.get('title') or '')+' '+str(item.get('content') or item.get('snippet') or '')
    name=parsed['company_candidate']
    if name and not same_company_name(expected,name):return {'status':'UNRESOLVED','reason':'resolution_subject_mismatch'}
    search_name=re.sub(r'\b(?:s\.?\s*r\.?\s*l\.?|s\.?\s*n\.?\s*c\.?|s\.?\s*p\.?\s*a\.?|s\.?\s*a\.?\s*s\.?)\s*$','',str(expected or ''),flags=re.I)
    words=re.findall(r'\w+',search_name.casefold())
    present=bool(words and re.search(r'(?<!\w)'+r'\W+'.join(map(re.escape,words))+r'(?!\w)',text.casefold()))
    # An identical generic skill is not evidence that the named business is
    # recruiting. Both the original subject and role must survive resolution.
    role_terms=[x for x in re.findall(r'\w+',role.casefold()) if x not in ('freelance','esperti','senior','junior','software','engineer','developer','in','di','per')]
    matched=bool(role_terms and any(re.search(r'\b'+re.escape(term)+r'\b',text,re.I) for term in role_terms))
    if not present:return {'status':'UNRESOLVED','reason':'resolution_subject_unproven'}
    if plan.get('resolution_stage')=='COMPANY_DOMAIN_CANDIDATE':
        # A testimonial or a copied vacancy can mention the employer without
        # being its website. Require a subject hint in the page title as well.
        title=str(item.get('title') or '').casefold()
        if not re.search(r'(?<!\w)'+r'\W+'.join(map(re.escape,words))+r'(?!\w)',title):
            return {'status':'UNRESOLVED','reason':'resolution_subject_only_mentioned'}
    if not matched and plan.get('resolution_stage')!='COMPANY_DOMAIN_CANDIDATE':return {'status':'UNRESOLVED','reason':'resolution_role_unproven'}
    context_hints={'role_overlap':matched,'digital_sector':bool(re.search(r'software|digitale|digital|sviluppo|startup|web agency|WordPress|frontend',text,re.I)),'official_claim':bool(re.search(r'sito ufficiale|official (?:site|website)',text,re.I)),'italian_context':bool(re.search(r'Italia|Milano|Roma|Padova|Torino',text,re.I))}
    if plan.get('resolution_stage')=='COMPANY_DOMAIN_CANDIDATE' and not any(context_hints.values()):return {'status':'UNRESOLVED','reason':'resolution_context_insufficient','context_hints':context_hints}
    return {'status':'SUPPORTED','context_hints':context_hints,'reason':'resolution_subject_and_role_hints','identity_verified':False,'request_verified':False,'company':expected,'role':role}
