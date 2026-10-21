"""Bounded, source-addressable request blocks. No inference or network access.

Visible content and each JobPosting are separate evidence channels. A block
never joins two vacancies; shared invitations apply only to a careers section,
not a contract belonging to another role. Offsets address canonical source text.
"""
import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urlsplit
from sales.extract import Document, parse_page, nodes, types, iso_date
from sales.db import digest, domain

ASK = re.compile(r'\b(?:cerchiamo|cerco|cercasi|ricercasi|ricerchiamo|seleziona(?:mo)?|selezioniamo|ricerca|cerca|siamo alla ricerca|stiamo (?:anche )?cercando|looking for|we are seeking|we are hiring|profili ricercati|figure sempre ricercate|ruoli ricercati)\b', re.I)
TECH = re.compile(r'full[ -]?stack|wordpress|woocommerce|prestashop|front[ -]?end|back[ -]?end|web\s*(?:app|develop\w*|design\w*)|sviluppo web|software|sviluppator\w*|programmator\w*|MVP|\bCTO\b|piattaforma|e.?commerce|react|node\.?js|HubSpot', re.I)
EXTERNAL = re.compile(r'\bfreelanc\w*|partita\s*IVA|\bp\.?\s*iva\b|collaborator\w*\s+estern\w*|collaborazion\w*\s+estern\w*|contractor|partner\s+tecnic\w*', re.I)
STANDING = re.compile(r'accettiamo|valutiamo|siamo aperti|collaboriamo|collaborazioni continuative|entra nel nostro network|cerchiamo spesso|figure sempre ricercate|candidati come partner|diventa partner', re.I)
CAREERS = re.compile(r'/(?:lavora-con-noi|collabora-con-noi|careers?|jobs?|join-us|posizioni-aperte|offerta-lavoro|diventa-partner|entra-nel-team)(?=/|$|\s)|lavora con noi|collabora con noi|diventa partner', re.I)
EXCLUDED = re.compile(r'faq|frequently.asked|testimoni|testimonial|related|correlat|altri annunci|altre offerte|ultime posizioni|annunci simili|potrebbe interessarti|domande frequenti|cookie|consent', re.I)
EMPLOYEE = re.compile(r'tempo (?:indeterminato|determinato)|contratto (?:di lavoro )?(?:dipendente|subordinato)|apprendistato|\bstage\b|tirocinio|\bintern\b', re.I)
NEGATIVE = re.compile(r'non (?:cerchiamo|accettiamo) (?:collaborator|freelance)|no freelance|collaborazioni sospese|candidature chiuse', re.I)


class Units(HTMLParser):
    """Small HTML block stream; retains excluded text but labels its scope."""
    breaks = {'p','div','section','article','li','br','h1','h2','h3','h4','h5','h6','option','label','tr'}
    void = {'br','img','meta','link','input','hr','source','wbr','area','base','embed','param','col'}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.stack=[];self.buffer=[];self.items=[];self.heading=None;self.heading_block=None;self.serial=0
        self.feed(html);self.flush()
        offset=0
        for unit in self.items:
            unit['start']=offset;offset+=len(unit['text']);unit['end']=offset;offset+=1
        self.text='\n'.join(u['text'] for u in self.items)

    def flush(self):
        text=' '.join(''.join(self.buffer).split());self.buffer=[]
        if not text:return
        excluded=any(x[1] for x in self.stack)
        level=int(self.heading[1]) if self.heading else None
        if level:
            if self.heading_block and level<=self.heading_block:self.heading_block=None
            if EXCLUDED.search(text):self.heading_block=level
        scope=next((x[2] for x in reversed(self.stack) if x[2] is not None),None)
        self.items.append({'text':text,'heading':level,'excluded':excluded or bool(self.heading_block),'scope':scope})

    def handle_starttag(self,tag,attrs):
        if tag in self.breaks or tag in ('footer','nav','aside','script','style','header'):self.flush()
        attrs=dict(attrs);marker=' '.join(str(attrs.get(k) or '') for k in ('class','id','role'))
        skip=tag in ('footer','nav','aside','script','style','noscript','head') or bool(EXCLUDED.search(marker))
        vacancy=tag=='article' or bool(re.search(r'(?:^|[\s_-])(?:vacancy|job-card|job-posting|position-card|annuncio)(?:$|[\s_-])',marker,re.I))
        self.serial+=1
        if tag not in self.void:self.stack.append((tag,skip,self.serial if vacancy else None))
        if re.fullmatch('h[1-6]',tag):self.heading=tag

    def handle_endtag(self,tag):
        if tag in self.breaks or tag in ('footer','nav','aside','script','style','header'):self.flush()
        if tag==self.heading:self.heading=None
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:self.stack=self.stack[:i];break

    def handle_data(self,data):self.buffer.append(data)


def channels(page):
    parsed=parse_page(page);visible=Units(page['html'])
    result={'visible':{'text':visible.text,'units':visible.items,'job':None}}
    for index,job in enumerate(n for n in nodes(parsed['doc'].schemas) if 'JobPosting' in types(n)):
        # Title is its own field, not silently concatenated into the description.
        units=Units(str(job.get('description') or ''))
        result['job:'+str(index)]={'text':units.text,'units':units.items,'job':job}
    return result


def typed_dates(page, job=None):
    p=parse_page(page)
    published=iso_date((job or {}).get('datePosted'))
    origin='JobPosting.datePosted' if published else None
    if not job and (page.get('public_social') or CAREERS.search(page['url']+' '+p['title'])) and p.get('date_origin') in ('article:published_time','Data di pubblicazione esplicita nel testo','Data esplicita nel testo della pagina'):
        # Generic article metadata dates the careers page, not its several vacancies.
        if p.get('date_origin')!='article:published_time' or not re.search(r'/(?:lavora-con-noi|careers|collabora-con-noi)/?$',urlsplit(page['url']).path,re.I):
            published=p['published_at'];origin=p['date_origin']
    return {'published_at':published,'publication_basis':origin,
            'expires_at':iso_date((job or {}).get('validThrough')),
            'page_published_at':p.get('published_at'),'observed_at':page['checked_at']}


def asking(text):
    from .intent import request_clause
    return request_clause(text) is not None


def source_kind(page):
    if page.get('public_social'):return 'social_post'
    p=parse_page(page);path=urlsplit(page['url']).path.lower();host=domain(page['url'])
    intro=p['title']+' '+p['doc'].text[:1800]
    from .relevance import preflight_type
    typ,_=preflight_type({'url':page['url'],'title':p['title'],'content':p['doc'].text[:1800]})
    if typ=='EDITORIAL':return 'article'
    if typ=='INSTITUTIONAL':return 'institution'
    if host.endswith('linkedin.com'):return 'inaccessible'
    from .intent import source_intent
    intent=source_intent(page['url'],p['title'],p['doc'].text[:2200])
    from .discovery import individual_vacancy
    bounded=individual_vacancy({'url':page['url'],'title':p['title'],'content':p['doc'].text[:2200]})
    if intent=='AGGREGATOR' and (p.get('job') or bounded):return 'job_portal'
    if intent in ('DIRECTORY','EDITORIAL','AGGREGATOR'):return {'DIRECTORY':'directory','EDITORIAL':'article','AGGREGATOR':'aggregator'}[intent]
    if re.search(r'portale dell.imprenditoria|una selezione.{0,50}aziende|directory di|elenco (?:aziende|imprese)',intro,re.I) or host in ('pmilombarde.it','houzz.it','virgilio.it'):return 'directory'
    if re.search(r'camera di commercio|CCIAA|ARPA Veneto|Azienda Zero',p['title'],re.I):return 'institution'
    if re.search(r'/portfolio(?:/|$)',path):return 'portfolio'
    if re.search(r'/(?:blog|news|notizie|articoli|guide)/',path) and not CAREERS.search(path):return 'article'
    if host in ('apriamoinsieme.it','cercolavoro.com','it.clickajobs.com','careerjet.it','it.whatjobs.com'):
        return 'job_portal' if p.get('job') or bounded else 'aggregator'
    if p.get('job'):return 'job_posting'
    if CAREERS.search(path+' '+p['title']):return 'careers'
    return 'company_page'



VACANCY_START=re.compile(r'(?:ricerca|cerchiamo|ricerchiamo|seleziona)\s+(?:(?:un[oa]?|uno|una)\s+(?:esperto|sviluppator|programmator|addett|tecnic|impiegat|responsabil)|sviluppatori|programmatori)|(?:azienda|società|gruppo).{0,220}\bricerca\b',re.I)

def position_sections(page):
    """Retain all independently advertised positions, even non-web roles."""
    units=[u for u in Units(page['html']).items if not u['excluded']]
    starts=[i for i,u in enumerate(units) if VACANCY_START.search(u['text'])]
    if len(starts)<2:return []
    return [{'url':page['url'],'start':units[start]['start'],
             'end':units[(starts[n+1]-1) if n+1<len(starts) else -1]['end'],
             'heading':units[start]['text']} for n,start in enumerate(starts)]

def project_sections(page):
    """Repeated named headings delimit hosted projects, never their publisher.

    Require either repeated catalogue/detail headings or an explicit projects
    container. A heading alone is an entity hint, not verified company identity.
    """
    units=[u for u in Units(page['html']).items if not u['excluded']]
    names={}
    for u in units:
        if u['heading'] and 2<=len(u['text'])<=80 and not re.search(r'[?!]|^(?:chi |come |cosa |requisiti|servizi|contatti|posizioni|collabora|lavora|cerchiamo)',u['text'],re.I):
            names.setdefault(u['text'].casefold(),[]).append(u)
    repeated={k for k,v in names.items() if len({u['heading'] for u in v})>1}
    explicit=bool(re.search(r'(?:progetti|startup) (?:ospitati|selezionati|accelerati)|i nostri progetti', ' '.join(u['text'] for u in units if u['heading']),re.I))
    if len(repeated)<2 and not explicit:return []
    level=min((u['heading'] for k,v in names.items() for u in v if k in repeated),default=None)
    if level is None:
        container_level=min((u['heading'] for u in units if u['heading'] and re.search(r'(?:progetti|startup) (?:ospitati|selezionati|accelerati)|i nostri progetti',u['text'],re.I)),default=1)
        level=min((u['heading'] for u in units if u['heading'] and u['heading']>container_level and u['text'].casefold() in names),default=None)
    headings=[i for i,u in enumerate(units) if u['heading']==level and u['text'].casefold() in names and (explicit or u['text'].casefold() in repeated)]
    sections=[]
    for start in headings:
        first=units[start];end=next((i for i in range(start+1,len(units)) if units[i]['heading'] and units[i]['heading']<=first['heading']),len(units))
        section=units[start:end]
        if len(section)>1:sections.append({'subject':first['text'],'units':section,'start':first['start'],'end':section[-1]['end'],'subject_evidence':first})
    return sections


def extract(page):
    """Return every relevant block, with exact spans, including expired requests."""
    kind=source_kind(page)
    if kind in ('portfolio','directory','aggregator','inaccessible'):return []
    if kind in ('article','institution') and not project_sections(page):return []
    parsed=parse_page(page);sources=channels(page);blocks=[]
    jobs=[k for k in sources if k.startswith('job:')]
    for channel in jobs or ['visible']:
        src=sources[channel];job=src['job'];units=src['units'];valid=[u for u in units if not u['excluded']]
        if not valid:continue
        careers=kind in ('careers','social_post') or bool(job)
        # A heading naming a role starts a vacancy; sibling roles are not merged.
        role_label=re.compile(r'sviluppator|developer|designer|\bCTO\b|specialist|manager|copywriter|director|co-founder|programmator|wordpress expert',re.I)
        def role_unit(u):
            return len(u['text'])<120 and bool(role_label.search(u['text'])) and not ASK.search(u['text']) and not re.search(r'[.!?]|^posizione:|^contratto:|^collaborazione',u['text'],re.I)
        boundaries=[i for i,u in enumerate(valid) if role_unit(u)]
        segments=[];intro=[]
        themes=[i for i,u in enumerate(valid) if u['heading'] and re.fullmatch(r'servizi|cosa offriamo|collaborazioni|posizioni aperte|offerte di lavoro',u['text'],re.I)]
        scopes={u.get('scope') for u in valid if u.get('scope') is not None}
        request_starts=[i for i,u in enumerate(valid) if VACANCY_START.search(u['text'])]
        projects=project_sections(page) if not job else []
        if projects:
            segments=[p['units'] for p in projects]
        elif len(request_starts)>1 and not job:
            intro=valid[:request_starts[0]]
            shared=careers and any(EXTERNAL.search(u['text']) for u in intro)
            segments=[(intro if shared else [])+valid[start:(request_starts[n+1] if n+1<len(request_starts) else len(valid))] for n,start in enumerate(request_starts)]
        elif job:segments=[valid]
        elif len(scopes)>1:
            # Sibling vacancy cards cannot lend each other contracts or roles.
            first=next(i for i,u in enumerate(valid) if u.get('scope') is not None)
            intro=valid[:first]
            shared=careers and any(asking(u['text']) and EXTERNAL.search(u['text']) for u in intro)
            segments=[(intro if shared else [])+[u for u in valid if u.get('scope')==scope] for scope in sorted(scopes)]
        elif len(themes)>1:
            segments=[valid[start:(themes[n+1] if n+1<len(themes) else len(valid))] for n,start in enumerate(themes)]
        elif boundaries:
            first=boundaries[0];intro=valid[:first]
            shared=careers and any(asking(u['text']) and (EXTERNAL.search(u['text']) or STANDING.search(u['text'])) for u in intro)
            for n,start in enumerate(boundaries):
                end=boundaries[n+1] if n+1<len(boundaries) else len(valid)
                level=valid[start]['heading'] or 3
                for i in range(start+1,end):
                    if valid[i]['heading'] and valid[i]['heading']<=level and not re.search(r'cosa|chi|requisiti|offriamo|candidat|competenze|condizioni|contratto|modalità|come',valid[i]['text'],re.I):end=i;break
                segments.append((intro if shared else [])+valid[start:end])
            if not segments or not any(any(asking(u['text']) for u in s) for s in segments):segments.insert(0,intro)
        else:segments=[valid] if careers else [[u] for u in valid]
        for segment in segments:
            # No arbitrary whole-page join: a non-careers page needs a request
            # in one logical unit. JobPosting is an explicitly delimited source.
            if not segment:continue
            text='\n'.join(u['text'] for u in segment)
            title=str((job or {}).get('title') or '')
            role=title or next((u['text'] for u in segment if u not in intro and role_unit(u)),None)
            project=next((p for p in projects if p['start']==segment[0]['start']),None)
            if project:role=None
            if len(request_starts)>1 and not job and not project:
                role=re.split(r'\bricerca\b|\bcerchiamo\b|\bricerchiamo\b',next((u['text'] for u in segment if u not in intro and VACANCY_START.search(u['text'])),segment[0]['text']),flags=re.I)[-1]
            # A shared careers introduction can declare freelance availability,
            # but cannot turn a marketing vacancy into a developer position.
            body=[u for u in segment if u not in intro]
            if role and not job and not TECH.search(role):continue
            if not TECH.search(title+' '+' '.join(u['text'] for u in body)):continue
            if not (any(asking(u['text']) for u in segment) and TECH.search(text+' '+title)):continue
            if kind=='company_page' and re.search(r'\b(?:offriamo|realizziamo|vendiamo)\b',text,re.I) and not re.search(r'cerchiamo|seleziona|ricerc|partner tecnico',text,re.I):continue
            from .intent import classify_block
            intent=classify_block(text,role=role,url=page['url'],title=title,source_kind=kind)
            if intent['intent'] not in ('BUYER_INTENT','FREELANCE_OPPORTUNITY','JOB_OFFER'):continue
            # Retain relevant source units, never fabricate a joined quotation.
            proof_units=[u for u in segment if (project and u is segment[0]) or ASK.search(u['text']) or STANDING.search(u['text']) or TECH.search(u['text']) or EXTERNAL.search(u['text']) or EMPLOYEE.search(u['text']) or re.search(r'equity|quota|compenso|retribuit|sede|localit|scad|chius|offerta:|ricercat',u['text'],re.I)]
            if not proof_units:continue
            uncertain=len(text)>6000 or len([u for u in segment if re.search(r'contratto di lavoro:',u['text'],re.I)])>1
            dates=typed_dates(page,job)
            employer=(job or {}).get('hiringOrganization') or {}
            employer=employer if isinstance(employer,dict) else {}
            standing=bool(careers and STANDING.search(text) and not re.search(r'posizione chiusa|candidature chiuse',text,re.I))
            block={'id':digest(page['url']+channel+str(segment[0]['start'])+str(segment[-1]['end']))[:24],
                   'segmentation_uncertain':uncertain,'url':page['url'],'channel':channel,'start':segment[0]['start'],'end':segment[-1]['end'],
                   'publisher':domain(page['url']),'subject':project['subject'] if project else employer.get('name') or intent.get('requested_subject'),
                   'actor_role':'PROJECT' if project else 'UNKNOWN','attribution_basis':'bounded_project_heading' if project else 'request_or_schema',
                   'subject_url':employer.get('sameAs') or employer.get('url'),
                   'role':role,'commercial_intent':intent,
                   'contract':intent.get('relationship') and ('employee' if intent['relationship']=='employment' else intent['relationship']),
                   'standing':standing,'dates':dates,'source_kind':kind,'text':text,
                   'negative':bool(intent.get('negations') and not intent.get('buyer_evidence')),
                   'contradictions':intent.get('contradictions',[]),
                   'evidence':[{'url':page['url'],'quote':u['text'],'channel':channel,'start':u['start'],'end':u['end'],
                     'source_hash':digest(src['text']),'kind':'request','certainty':'fact','published_at':dates['published_at'],
                     'checked_at':page['checked_at']} for u in proof_units]}
            # Do not expose the complete section in the dossier/DB: evidence
            # spans and block coordinates are sufficient for reproducibility.
            blocks.append(block)
    return blocks


def expired(block, today=None):
    today=today or date.today();dates=block['dates']
    end=dates.get('expires_at')
    return bool((end and date.fromisoformat(end)<today) or re.search(r'annuncio scaduto|posizione chiusa|ricerca conclusa|position (?:closed|filled)|applications closed',block['text'],re.I))


def documents(page):
    """Canonical channels saved alongside legacy visible document text."""
    return {key:{'text':value['text'],'hash':digest(value['text']),'units':value['units'],**({'job':value['job']} if value.get('job') else {})} for key,value in channels(page).items()}


def followups(page):
    """Only a local recruitment context can turn a technical anchor into a role.

    A careers-like parent URL never licenses following its service navigation.
    The actual anchor context is retained for downstream trace and preflight.
    """
    from urllib.parse import urljoin
    from .intent import classify_block
    links=[];kind=source_kind(page);units=Units(page['html']).items
    for l in parse_page(page)['doc'].links:
        u=urljoin(page['url'],l['url']);path=urlsplit(u).path
        from sales.content_policy import skip_pdf
        if skip_pdf(u):continue
        from .admission import listing_url
        if listing_url(u):continue
        if u.split('#')[0]==page['url'].split('#')[0]:continue
        if domain(u)!=domain(page['url']) or urlsplit(u).scheme not in ('http','https'):continue
        anchor=l['text'].strip()
        contexts=[unit['text'] for unit in units if not unit['excluded'] and anchor and anchor in unit['text']]
        local=min(contexts,key=len) if contexts else anchor
        intent=classify_block(local,url=u)
        demand=bool(intent.get('buyer_evidence')) and not intent.get('contradictions')
        explicit=bool(re.search(r'/(?:lavora-con-noi|collabora-con-noi|careers?|jobs?|join-us|posizioni-aperte|offerta-lavoro|entra-nel-team)(?=/|$)|lavora con noi|collabora con noi|candidati|posizione aperta',path+' '+anchor,re.I))
        service=bool(re.search(r'/(?:e-commerce|web-applications|servizi|portfolio|consulenza|sviluppo-web)(?:/|[-?]|$)',path,re.I))
        role_link=kind in ('careers','aggregator','job_portal') and bool(TECH.search(anchor)) and demand
        if (explicit or role_link) and (not service or demand) and u!=page['url']:
            links.append({'url':u,'anchor':anchor,'anchor_context':local,'parent':page['url'],'source_kind':kind,
                          'commercial_role':intent['commercial_role'],'recruitment_context':bool(explicit or demand),
                          'reason':'Collegamento esplicito a candidatura/ruolo con contesto locale conservato'})
    return list({l['url']:l for l in links}.values())[:3]
