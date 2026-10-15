"""Company-first acquisition. Target fit is never evidence of a buying need."""
import re
from itertools import zip_longest
from urllib.parse import urljoin, urlsplit

from .db import domain, digest
from .providers import canonical, blocked
from .extract import parse_page, nodes, types
from .research_analysis import ResearchWeb, document, identity_from, INSTITUTION
from .research_rules import ALLOWED_REGIONS, REGION_CITIES, FULL, REQUEST
from .targeting import exclusion

PROFILES = {
    'b2b': ('Produttori e piccole aziende B2B', (
        'impiantistica industriale', 'ingegneria industriale', 'lavorazioni meccaniche',
        'carpenteria metallica', 'arredamento contract', 'produzione alimentare')),
    'retail': ('Negozi e marchi propri', ('produttore abbigliamento', 'artigianato ceramica', 'produttore cosmetici', 'negozio arredamento')),
    'services': ('Servizi e professionisti', ('studio tecnico', 'servizi alle imprese', 'transfer privati', 'centro formazione')),
}
ACTIVITY = {
    'b2b': re.compile(r'impiant\w*|ingegner\w*|lavorazioni meccaniche|carpenteri\w*|contract|produci\w*|produzion\w*|fabbric\w*|manifattur\w*|costruiamo|officina', re.I),
    'retail': re.compile(r'negozi\w*|marchio|produci\w*|produzion\w*|artigian\w*|vendita|collezion\w*', re.I),
    'services': re.compile(r'studio tecnico|consulenz\w*|servizi|profession\w*|transfer|formazion\w*', re.I),
}
# Explore all segments in rotation, rather than exhausting manufacturers first.
PROFILES['all']=('Tutti i settori',tuple(s for row in zip_longest(*(p[1] for p in PROFILES.values())) for s in row if s))
ACTIVITY['all']=re.compile('|'.join('(?:'+pattern.pattern+')' for pattern in ACTIVITY.values()),re.I)
SELLER = re.compile(r'web agency|software house|sviluppatore (?:web|freelance)|realizzazione siti (?:web|internet)|sviluppo (?:siti|e.?commerce)', re.I)
DIRECTORY = re.compile(r'elenco (?:delle )?(?:aziende|imprese|espositori|associati)|catalogo espositori|aziende associate|i nostri associati|portale di riferimento per la subfornitura|database.{0,30}aziende', re.I)


LEGAL_NAME = re.compile(r'\b(?:s\.?\s*r\.?\s*l\.?|s\.?\s*n\.?\s*c\.?|s\.?\s*a\.?\s*s\.?|s\.?\s*p\.?\s*a\.?)\b',re.I)
EXCLUDED_LEGAL = re.compile(r'\bs\.?\s*p\.?\s*a\.?\b',re.I)


def directory_profiles(page):
    """Actual linked public profiles, including structured names on image-only cards."""
    parsed=parse_page(page);links=[];seen=set()
    linked={urljoin(page['url'],l['url']) for l in parsed['doc'].links if not l.get('navigation')}
    for node in nodes(parsed['doc'].schemas):
        if not types(node)&{'LocalBusiness','Organization','Corporation'}:continue
        href=node.get('url');name=node.get('name')
        if not isinstance(href,str) or not isinstance(name,str) or not 3<=len(name)<=160:continue
        href=urljoin(page['url'],href)
        if href not in linked or href==page['url'] or domain(href)!=domain(page['url']):continue
        if name.casefold() not in parsed['text'].casefold() or INSTITUTION.search(name):continue
        if href not in seen:links.append({'url':href,'name':name});seen.add(href)
    for link in parsed['doc'].links:
        href=urljoin(page['url'],link['url']);name=link['text'].strip()
        if link.get('navigation') or href==page['url'] or domain(href)!=domain(page['url']):continue
        if not re.search(r'/(?:azienda|aziende|impresa|imprese|scheda|espositore|fornitori)/[^/?]+',urlsplit(href).path,re.I):continue
        if not 3<=len(name)<=160 or not LEGAL_NAME.search(name) or re.search(r'cerca|aggiungi|registra|accedi|tutte le|categoria|^servizi$|^aziende per',name,re.I):continue
        if href not in seen:links.append({'url':href,'name':name});seen.add(href)
    return links


def directory_names(page):
    """Names must be literal in original text; plain legal-name lines work without JSON-LD."""
    parsed=parse_page(page);out=[];names=[];structured=set()
    for node in nodes(parsed['doc'].schemas):
        if types(node)&{'LocalBusiness','Organization','Corporation'} and isinstance(node.get('name'),str):names.append(node['name']);structured.add(node['name'])
    for line in parsed['text'].splitlines():
        line=line.strip()
        if 3<=len(line)<=100 and (legal:=LEGAL_NAME.search(line)) and not line[legal.end():].strip(' .,') and not re.search(r'copyright|realizzato|powered|privacy|cookie|p\.?iva|©',line,re.I):names.append(line)
    for name in dict.fromkeys(names):
        if not 3<=len(name)<=100 or INSTITUTION.search(name):continue
        match=re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',parsed['text'],re.I)
        if not match:continue
        quote='\n'.join(parsed['text'][match.start():].splitlines()[:6])[:500]
        out.append({'name':name,'quote':quote,'method':'structured' if name in structured else 'legal_line'})
    return out


def check_directory_access(web, page):
    """Public does not imply permission: respect linked restrictions as for RSS sources."""
    parsed=parse_page(page)
    if re.search(r'accesso riservato|effettua il login per|accedi per leggere', parsed['text'][:2500], re.I):
        raise ValueError('Elenco riservato: nessun accesso automatico')
    policies=[]
    for link in parsed['doc'].links:
        href=urljoin(page['url'],link['url'])
        if domain(href)==domain(page['url']) and re.search(r'termini|condizioni.*uso|terms.*use|note.legali',link['text']+' '+href,re.I):
            if href not in policies:policies.append(href)
    for href in policies[:2]:
        policy=web.get(href)
        if policy['status']!=200:raise ValueError('Condizioni dell’elenco non verificabili')
        if re.search(r'(?:vietat\w*|non (?:è )?consentit\w*|prohibit\w*).{0,140}(?:scrap\w*|automatizz\w*|automated|robot)',parse_page(policy)['text'],re.I):
            raise ValueError('L’elenco esclude la raccolta automatizzata nelle condizioni pubbliche')


def acquisition_rank(item, profile='b2b', subject=None):
    """Rank reads, never establish identity or infer need from a search snippet."""
    title=item.get('title','');url=item.get('url','');host=domain(url)
    score=(3 if ACTIVITY[profile].search(title) else 0)+(1 if re.search(r'contatti|azienda|s\.?r\.?l',title+' '+url,re.I) else 0)
    if subject:
        words=set(re.findall(r'[a-zà-ÿ0-9]{3,}',subject.casefold()))-{'srl','società','azienda','snc','sas'}
        score+=sum(3 for word in words if word in re.sub(r'[^a-zà-ÿ0-9]','',host))
        if urlsplit(url).path.strip('/') in ('','it','en'):score+=3
        if re.search(r'/fornitori/|/scheda|/business-listing|registroaziende|ufficiocamerale|\.gov\.it|\.pdf(?:$|\?)',url,re.I):score-=6
    return score


def regional_sectors(region, profile='b2b'):
    """Stable rotation: neighboring branches should not all start in one sector."""
    sectors=PROFILES[profile][1]
    offset=list(REGION_CITIES).index(region)%len(sectors) if region in REGION_CITIES else 0
    return sectors[offset:]+sectors[:offset]


def company_queries(region, profile='b2b'):
    """Find businesses, without asking Google to infer demand from digital keywords."""
    sectors = regional_sectors(region, profile)
    places = [region] + re.findall(r'La Spezia|Reggio Emilia|[A-ZÀ-Ý][a-zà-ÿ]+', REGION_CITIES[region])
    for place in places:
        for sector in sectors:
            yield f'{sector} {place} azienda contatti -agenzia -software -lavoro'


def selected_strategies(filters):
    if filters.get('groups') == ['agencies']:
        return ('partner','explicit')
    strategies=['companies','explicit']
    if 'agencies' in filters.get('groups',['direct','agencies']):strategies+=['partner']
    return tuple(strategies)



def inspect_company(store, payload, first, check):
    """Cheap identity/fit pass, including contact page; no model and no qualification."""
    from .research_analysis import CompanyWeb
    web = (CompanyWeb if payload.get('direct_channels') else ResearchWeb)(store, check)
    pages = [first]
    request_pages = [first]
    limits = []
    home_url = urljoin(first['url'], '/')
    if first['url'] != home_url:
        check()
        try:
            home = web.get(home_url)
            if home['status'] == 200 and home['url'] not in {p['url'] for p in pages}: pages.insert(0, home)
            elif home['status'] != 200: limits.append('Homepage HTTP ' + str(home['status']))
        except InterruptedError: raise
        except Exception as exc: limits.append(str(exc)[:300])
    host = domain(pages[0]['url'])
    from .organization import classify
    from .source_roles import publisher_identity
    organization=classify(pages,identity_from(pages))
    if organization['category']=='directory' or (organization['category']=='public_body' and not publisher_identity(pages[0])):
        return {'state':'rejected','reason':organization['reason'],
                'details':{'identity':identity_from(pages),'organization':organization,
                           'company_ready':False,'document':document(first,payload.get('provider','Fonte pubblica'))}}
    from .source_roles import publisher_identity
    if publisher_identity(pages[0]):
        source_doc=document(first,payload.get('provider','Fonte pubblica'))
        index=first['url']==pages[0]['url'] and not source_doc.get('published_at')
        return {'state':'needs_review','resolve':not index,'source':index,
                'reason':'Dominio editoriale verificato dalla homepage: cercare le imprese citate, non proporre l’editore.',
                'details':{'identity':{},'publisher':True,'document':source_doc,
                           'publisher_identity_url':pages[0]['url'],'company_ready':False,'organization':organization}}
    from .direct_channels import careers_page,request_excerpt,WEB,FREELANCE,collaboration_evidence,standing_partner_evidence
    from .direct_channels import careers_links
    if not careers_page(first):
        # Careers links in the site's navigation are relevant here. Follow only
        # explicitly linked pages on the official host; never invent /jobs URLs.
        links=list(dict.fromkeys(href for p in pages for href in careers_links(p)))
        for href in links[:2]:
            check()
            if href in {p['url'] for p in pages}:continue
            try:
                page=web.get(href)
                if page['status']==200 and domain(page['url'])==host:
                    pages.append(page);request_pages.append(page)
            except InterruptedError:raise
            except Exception as exc:limits.append(str(exc)[:300])
    career_indexes=[p for p in request_pages if careers_page(p) and not collaboration_evidence(p) and not standing_partner_evidence(p)]
    if career_indexes:
        # Read the actual vacancy, not a mix of contract terms from a jobs index.
        links=[]
        for index_page in career_indexes:
            for link in parse_page(index_page)['doc'].links:
                href=urljoin(index_page['url'],link['url']);label=link['text']
                if link.get('navigation') or domain(href)!=host or href in [p['url'] for p in pages]:continue
                if WEB.search(label) or (FREELANCE.search(label) and re.search(r'svilupp|design',label,re.I)):
                    links.append((0 if FREELANCE.search(label) else 1,href))
        for _,href in sorted(set(links),key=lambda x:x[0])[:2]:
            check()
            try:
                page=web.get(href)
                if page['status']==200 and domain(page['url'])==host:
                    pages.append(page);request_pages.append(page)
            except InterruptedError:raise
            except Exception as exc:limits.append(str(exc)[:300])
    contact_links = []
    for page in pages:
        for link in parse_page(page)['doc'].links:
            href = urljoin(page['url'], link['url'])
            if domain(href) == host and re.search(r'contatt|contact|chi.siamo|azienda', link['text']+' '+urlsplit(href).path, re.I):
                if href not in [p['url'] for p in pages] and href not in contact_links: contact_links.append(href)
    contact_links.sort(key=lambda href:(not bool(re.search(r'contatt|contact',urlsplit(href).path,re.I)),len(href)))
    for href in contact_links[:2]:
        check()
        try:
            page = web.get(href)
            if page['status'] == 200 and domain(page['url']) == host:
                if page['url'] not in {p['url'] for p in pages}: pages.append(page)
            else: limits.append('Pagina identità non verificabile: '+href)
        except InterruptedError: raise
        except Exception as exc: limits.append(str(exc)[:300])
    check()
    identity = identity_from(pages)
    documents = [document(p, payload.get('provider', 'Sito aziendale'), True) for p in pages]
    text = '\n'.join(d['research_text'] for d in documents)
    heading = ' '.join(parse_page(p)['title'] for p in pages)
    profile = payload.get('filters', {}).get('target', 'b2b')
    activity = ACTIVITY[profile].search(text)
    details = {'identity': identity, 'document': documents[0], 'company_documents': documents,
               'company_ready': False, 'target_profile': profile, 'limits': limits,
               'checked_at': first['checked_at'], 'budget': None, 'company_stage': 'identity',
               'next_action': 'Verificare identità e attività prima di cercare un bisogno commerciale.'}
    details['organization']=classify(pages,identity)
    reason = next((finding['reason'] for p in pages if (finding := exclusion(p))), None)
    from .research_store import ResearchStore
    reason = ResearchStore(store).suppressed(identity) or reason
    for place in store.settings()['excluded_locations']:
        if re.search(r'(?<!\w)'+re.escape(place)+r'(?!\w)', identity.get('location') or '', re.I):
            reason = 'Località esclusa: '+place
    regions = payload.get('filters', {}).get('regions') or ALLOWED_REGIONS
    if identity.get('region') and identity['region'] not in regions: reason = 'Sede fuori dal territorio selezionato.'
    if identity.get('country') and identity['country'].casefold() not in ('it', 'ita', 'italia', 'italy'): reason = 'Sede ufficiale fuori Italia.'
    # Institutional identity was already checked on the homepage above. Words
    # such as "Torino e provincia" describe an operating area, not a public body.
    # Ignore website credits: only own title or own presentation establishes a supplier.
    from .direct_channels import digital_supplier,request_excerpt,careers_page,standing_partner_evidence
    supplier = any(digital_supplier(parse_page(p)) for p in pages)
    demand = next((q for p in request_pages if (q:=request_excerpt(document(p)['research_text']))),None)
    collaboration = None;collaboration_proof=None;request_page=first
    if any(careers_page(p) for p in request_pages):
        for p in request_pages:
            collaboration_proof=(standing_partner_evidence(p) if supplier or identity['group']=='agencies' else None) or collaboration_evidence(p)
            if collaboration_proof:
                collaboration=collaboration_proof['quote'];request_page=p;break
    if supplier:identity['group']='agencies'
    if (identity['group'] == 'agencies' or supplier) and not demand and not collaboration:
        reason = 'Fornitore di servizi digitali: non è un committente per questa ricerca.'
    groups=payload.get('filters',{}).get('groups')
    if groups and identity['group'] not in groups:reason='Categoria di cliente non selezionata.'
    if reason: return {'state': 'rejected', 'reason': reason, 'details': details}
    if payload.get('subject'):
        words=lambda value:set(re.findall(r'\w{3,}',value.casefold()))-{'srl','spa','società','azienda','home'}
        expected=words(payload['subject'])
        if not expected or len(expected & words(identity['name']))/len(expected)<.75:
            return {'state':'needs_review','reason':'Il nome dell’impresa citata non coincide sufficientemente con l’identità del sito.', 'details':details}
    known_locations=bool(identity.get('regions')) and all(r in regions for r in identity['regions'])
    if identity['identity_status'] != 'verified' or (not identity.get('region') and not (collaboration and known_locations)):
        return {'state': 'unverifiable' if limits else 'needs_review', 'reason': 'Impresa da identificare: nome, sito e sede non ancora verificati insieme.', 'details': details}
    standing=bool(collaboration_proof and collaboration_proof.get('kind')=='standing_invitation')
    if collaboration and identity['contacts'] and (standing or not FULL.search(collaboration)):
        if payload.get('filters',{}).get('projects')==['website'] and not re.search(r'wordpress|front[ -]?end|web\s*design|html|css|sito\s+(?:web|aziendale)',str(collaboration_proof.get('role') or '')+' '+collaboration,re.I):
            return {'state':'needs_review','reason':'Richiesta freelance documentata, ma non riscontrata la compatibilità con siti aziendali/WordPress/frontend selezionati.','details':details}
        from datetime import datetime,timezone
        from .extract import iso_date
        request_parsed=parse_page(request_page)
        # The creation date of a multi-vacancy careers page is not the posting
        # date of its current roles. Only an attributed JobPosting dates a job.
        job={} if standing else request_parsed.get('job') or {}
        published=iso_date(job.get('datePosted')) if not request_parsed.get('multi_job') else None
        if published:
            try:
                age=(datetime.now(timezone.utc).date()-datetime.fromisoformat(published[:10]).date()).days
                if age>180 or age< -1:
                    return {'state':'needs_review','reason':'Richiesta datata: prima del contatto serve confermare che la collaborazione sia ancora aperta.','details':details}
            except ValueError:
                return {'state':'needs_review','reason':'Data della richiesta non interpretabile: verificare attualità.','details':details}
        # A verified invitation to collaborate is useful for outreach even when
        # no complete project/budget is disclosed. It never counts toward 50.
        details.update(company_ready=True,company_stage='collaboration',relationship='partner',
            collaboration={**collaboration_proof,'url':request_page['url'],'checked_at':request_page['checked_at'],
                           'published_at':published,'page_published_at':document(request_page).get('published_at'),
                           'scope':'Da concordare','budget':None},
            next_action='Presentare esperienze pertinenti alla richiesta e chiedere disponibilità, perimetro e compenso. Nessuna commessa o data di chiusura confermata.')
        if standing:
            details['next_action']='Presentarsi con portfolio e competenze pertinenti. Chiedere come entrare nella rete di collaboratori; nessun incarico aperto o compenso verificato.'
        return {'state':'promising','reason':('Agenzia disponibile a collaborazioni freelance web, dichiarate sul proprio sito. Partner da contattare; nessuna commessa aperta verificata.' if standing else 'Richiesta di collaborazione freelance riscontrata sul sito aziendale, con identità e canale di contatto verificati. Ambito e compenso da concordare.'),'details':details}
    if any(careers_page(p) for p in request_pages) and not collaboration:
        return {'state':'needs_review','reason':'Pagina di recruiting: collaborazione freelance per lo specifico ruolo web non verificata.','details':details}
    if not activity and not (identity['group']=='agencies' and demand):
        return {'state': 'needs_review', 'reason': 'Identità verificata, ma attività non riscontrata nel segmento selezionato.', 'details': details}
    from .source_identity import verified_origins
    origin,origin_limits=verified_origins(payload,identity)
    details['origin_documents']=origin
    details['limits']+=origin_limits
    from .company_investigation import plan,topic_links
    details['investigation_plan']=plan(identity,origin+details['company_documents'])
    details['investigation_links']={q['id']:topic_links(pages,[q]) for q in details['investigation_plan']}
    details.update(company_ready=True, company_stage='research', target_quote=text[max(0, activity.start()-100):activity.end()+200] if activity else demand,
                   next_action='Cercare novità, offerta e soluzioni esistenti di questa impresa; il bisogno di un nuovo sito non è ancora dimostrato.')
    # A verified business without trigger keywords is worth researching, not promoting.
    links = []
    for page in pages:
        for link in parse_page(page)['doc'].links:
            href = urljoin(page['url'], link['url'])
            label = link['text']+' '+urlsplit(href).path
            if domain(href) != host or blocked(href): continue
            if not re.search(r'news|novit|notizi|progett|serviz|prodott|mercat|settori|referenz|catalog|portale|shop|store', label, re.I): continue
            if re.search(r'privacy|cookie|login|/termini|/condizioni|/terms|\.(?:pdf|jpg|png|zip)(?:$|\?)', href, re.I): continue
            try: href = canonical(href)
            except ValueError: continue
            if href not in [p['url'] for p in pages] and href not in links: links.append(href)
    details['research_links'] = links[:8]
    return {'state': 'needs_review', 'reason': 'Impresa e attività verificate: ora cerco una ragione commerciale, non ancora un’opportunità.', 'details': details}


def research_tasks(payload, result):
    """Bounded investigation per company; public search evidence cannot confer identity."""
    d = result.get('details', {})
    if not d.get('company_ready') or d.get('collaboration') or payload.get('followup_depth', 0): return [], []
    identity = d['identity']; host = domain(identity['website'])
    from .commercial_planner import source_payload
    context = {**source_payload(payload),'strategy': 'change', 'filters': payload.get('filters', {}),
               'subject': identity['name'], 'official_link': True, 'company_host': host,
               'source_documents': d.get('origin_documents',[])+d['company_documents'],
               'evidence_url': identity['website'], 'followup_depth': 1,
               'company_key': identity.get('legal_id') or host, 'provider': 'Indagine sul sito aziendale'}
    direct_links=[u for urls in d.get('investigation_links',{}).values() for u in urls if domain(u)==host]
    candidates = [{**context, 'url': u, 'source_url': identity['website'], 'company_stage': 'evidence'} for u in dict.fromkeys(direct_links+d['research_links'])]
    # Neutral factual queries: do not presuppose that this company wants a new site.
    investigation=d.get('investigation_plan',[])
    if investigation:
        queries=[];seen=set()
        for question in investigation:
            # The announcement already supplies a direct page: read it instead
            # of paying Google to rediscover it. Keep the counterproof search.
            choices=question['queries'][1:] if d.get('investigation_links',{}).get(question['id']) else question['queries']
            for query in choices:
                if query in seen:continue
                seen.add(query)
                queries.append({**context,'query':query,'page':1,'period':'','region':identity['region'],
                                'investigation_question':question})
    else:
        queries = [{**context, 'query': f'site:{host} {terms}', 'page': 1, 'period': '', 'region': identity['region']}
                   for terms in ('novità nuovi servizi prodotti', 'settori mercati progetti', 'catalogo portale clienti shop')]
    return candidates, queries


def verification_priority(result):
    """Scheduling only, never a probability or qualification score."""
    d = result.get('details', {})
    i = d.get('identity', {})
    if d.get('publisher'): return 0
    return (4 if i.get('identity_status') == 'verified' else 0) + (2 if i.get('region') else 0) + (1 if i.get('contacts') else 0) + (1 if 'explicit' in d.get('strategies', []) else 0)


def company_verification(payload, result):
    """A real target gets one commercial investigation even without buying keywords."""
    d=result.get('details',{})
    if not d.get('company_ready') or d.get('collaboration') or payload.get('followup_depth',0):return None
    identity=d['identity'];host=domain(identity['website'])
    from .commercial_planner import source_payload
    return {**source_payload(payload),'url':payload.get('url') or identity['website'],'strategy':'companies','filters':payload.get('filters',{}),
            'company_host':host,'company_key':identity.get('legal_id') or host,
            'official_link':True,'subject':identity['name'],'source_documents':d.get('origin_documents',[])+d['company_documents'],
            'followup_depth':1,'verification_priority':verification_priority(result),
            'investigation_plan':d.get('investigation_plan',[]),
            'evidence_revision':digest('|'.join(sorted(d.get('content_hash') or d['id'] for d in d.get('origin_documents',[])))),
            'provider':'Verifica commerciale del sito aziendale'}
