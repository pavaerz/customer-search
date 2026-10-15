"""Customer discovery on company domains and specific indexed freelance notices.

LinkedIn snippets are leads to investigate, never original-page evidence. We do
not fetch LinkedIn, automate a login, or convert an indexed notice into a client.
"""
import re
from urllib.parse import urlsplit,unquote,urljoin
from .db import domain

DIRECTORIES=('paginegialle.it','paginebianche.it','firmania.it','cylex-italia.it','europages.it','kompass.com','italianbusinessregister.it')
INSTITUTIONS=('confindustriavenest.it','assolombarda.it','ui.torino.it','confindustriatoscanacentroecosta.it','cnaveneto.it','venetosviluppo.it','venetoup.com')
FREELANCE=re.compile(r'\b(?:freelanc\w*|partita\s*iva|p\.?\s*iva|collaborator\w*\s+estern\w*|collaborazion\w*\s+estern\w*)\b',re.I)
WEB=re.compile(r'\b(?:wordpress|woocommerce|web\s*design\w*|front[ -]?end|sviluppator\w*\s+web|web\s+develop\w*|e[ -]?commerce|react|next\.?js|sito\s+web)\b',re.I)
REQUEST=re.compile(r'\b(?:cerco|cerchiamo|cercasi|cerca|ricerchiamo|ricerca|looking for|hiring|assumendo|selezioniamo|seleziona)\b',re.I)
EMPLOYEE=re.compile(r'\b(?:tempo (?:indeterminato|determinato)|contratto (?:di lavoro )?(?:dipendente|subordinato)|apprendistato|stage|tirocinio|no freelance|non (?:cerchiamo|si accettano) freelance)\b',re.I)
DOCUMENT_PATH=re.compile(r'\.(?:pdf|docx?|xlsx?|pptx?|odt|ods|zip|rar)(?:$|[/?&#])',re.I)
CAREERS_PATH=re.compile(r'/(?:lavora-con-noi|collabora-con-noi|careers?|jobs?|lavoro|join-us|posizioni-aperte)(?:/|$)',re.I)
GUIDE_TITLE=re.compile(r'\b(?:guida (?:per|alle?|completa)|chi [eè],? cosa fa|chi [eè] e cosa|come (?:diventare|scegliere|lavorare)|migliori (?:strumenti|app)|modello freelance)\b',re.I)


def visit_priority(item):
    """Order original recruiting pages before generic snippets; never qualify."""
    title=str(item.get('title',''));snippet=str(item.get('content') or item.get('search_snippet') or '')
    url=item.get('url','');path=unquote(urlsplit(url).path)
    careers=bool(CAREERS_PATH.search(path) or re.search(r'lavora con noi|collabora con noi|posizioni aperte',title,re.I))
    request=bool(REQUEST.search(title+' '+snippet) and WEB.search(title+' '+snippet))
    external=bool(FREELANCE.search(title+' '+snippet))
    if linkedin_notice(item):return (2,'Annuncio freelance indicizzato: identificare il committente e verificare la richiesta originale.')
    if careers:return (5+int(request)+int(external),'Pagina aziendale di recruiting: verificare ruolo web, collaborazione esterna e contatto.')
    if request and external:return (4,'Il risultato indica una richiesta web freelance: verificare chi la pubblica e le condizioni originali.')
    if GUIDE_TITLE.search(title):return (-2,'Guida informativa, senza richiesta commerciale verificata.')
    return (0,'Risultato ancora da identificare: non dimostra una richiesta di collaborazione.')


def request_excerpt(text, external=False):
    """Local evidence of a buyer's request, not unrelated words across a page.

    This is a cheap routing signal only: scope, identity, date and feasibility
    still need qualification. Return the literal original, never a generated claim.
    """
    from .research_rules import CLOSED_REQUEST,SMALL
    asking=re.compile(r'\b(?:cerchiamo|cerco|cercasi|ricerchiamo|selezioniamo|stiamo cercando|siamo alla ricerca di|we are looking for|instauriamo collaborazioni|valutiamo collaborazioni)\b',re.I)
    for m in asking.finditer(text):
        before=text[max(0,m.start()-45):m.start()]
        excerpt=text[m.start():m.start()+520].split('\n\n')[0]
        if re.search(r'\b(?:non|se|quando|chi)\s*$',before,re.I):continue
        if re.match(r'(?:cerchiamo|cerco)\s+(?:di\b|lavoro\b|clienti\b)',excerpt,re.I):continue
        if re.search(r'\b(?:come|perché|consigli per)\b.{0,25}$',before,re.I):continue
        from .extract import CLOSED
        if CLOSED_REQUEST.search(excerpt) or CLOSED.search(excerpt) or EMPLOYEE.search(excerpt) or SMALL.search(excerpt):continue
        if not WEB.search(excerpt):continue
        if external:
            pairs=[(f,w) for f in FREELANCE.finditer(excerpt) for w in WEB.finditer(excerpt)]
            if not any(max(f.start(),w.start())-min(f.end(),w.end())<=150 for f,w in pairs):continue
        provider=re.search(r'\b(?:freelanc\w*|partita\s*iva|fornitor\w*|professionist\w*|sviluppator\w*|developer|programmator\w*|web\s+design\w*|web\s+develop\w*|partner\s+(?:tecnic\w*|estern\w*))\b',excerpt,re.I)
        if provider:return excerpt.strip()
    return None


def careers_page(page):
    from .extract import parse_page
    p=parse_page(page)
    label=p['title']+' '+unquote(urlsplit(page['url']).path)
    return bool(p.get('job') or CAREERS_PATH.search(unquote(urlsplit(page['url']).path)) or re.search(r'lavora[ -]con[ -]noi|collabora[ -]con[ -]noi|careers?|/jobs?\b|posizioni[ -]aperte|cerchiamo.{0,80}(?:freelance|sviluppator|web designer)',label,re.I))


def careers_links(page):
    from .extract import parse_page
    links=[]
    for link in parse_page(page)['doc'].links:
        url=urljoin(page['url'],link['url'])
        if domain(url)!=domain(page['url']) or urlsplit(url).scheme not in ('http','https'):continue
        if DOCUMENT_PATH.search(unquote(url)):continue
        if CAREERS_PATH.search(unquote(urlsplit(url).path)) or re.fullmatch(r'\s*(?:lavora con noi|collabora con noi|jobs|careers|opportunità di lavoro|posizioni aperte)\s*',link['text'],re.I):
            if url not in links and url!=page['url']:links.append(url)
    return links


def collaboration_evidence(page):
    """Bind the contract to the same named vacancy, even on multi-job pages."""
    from .extract import parse_page,CLOSED
    from .research_analysis import document
    from .research_rules import CLOSED_REQUEST
    parsed=parse_page(page);text=document(page)['research_text'];headings=parsed['doc'].headings
    for index,h in enumerate(headings):
        if not WEB.search(h['text']) or len(h['text'])>100:continue
        start=text.find(h['text'])
        if start<0:continue
        end=len(text);level=max(2,int(h['tag'][1]))
        for nxt in headings[index+1:]:
            if nxt['text'] and int(nxt['tag'][1])<=level:
                pos=text.find(nxt['text'],start+len(h['text']))
                if pos>=0:end=pos;break
        section=text[start:end]
        quote=request_excerpt(section);external=FREELANCE.search(section)
        if not quote or not external or EMPLOYEE.search(section) or CLOSED.search(section) or CLOSED_REQUEST.search(section):continue
        return {'quote':quote,'role':h['text'],
                'contract_quote':section[max(0,section.rfind('\n',0,external.start())+1):min(len(section),section.find('\n',external.end()) if '\n' in section[external.end():] else len(section))].strip()}
    quote=request_excerpt(text,external=True)
    return {'quote':quote,'role':None,'contract_quote':None} if quote else None


def standing_partner_evidence(page):
    """Declared willingness, not a vacancy. Same original paragraph must name
    the web skill, external collaboration and invitation to apply.
    """
    from .research_analysis import document
    invitation=re.compile(r'candidatur\w*\s+spontane\w*|(?:accettiamo|valutiamo|instauriamo)\s+collaborazion\w*|siamo aperti\s+(?:a|alle)\s+collaborazion\w*',re.I)
    external=re.compile(r'freelanc\w*|collaborazion\w*\s+(?:estern\w*|(?:con|a)\s+partita\s+iva)',re.I)
    negative=re.compile(r'\b(?:non|no)\b.{0,50}(?:accett|valut|candidatur|collaborazion|freelance)|non più|candidature chiuse|collaborazioni sospese',re.I)
    for line in document(page)['research_text'].splitlines():
        if len(line)>1000 or not invitation.search(line) or not external.search(line):continue
        web=WEB.search(line)
        if not web or negative.search(line):continue
        # Do not turn conditional advice or another company's invitation into ours.
        if re.search(r'\b(?:se|quando|come|chi)\s+(?:accettiamo|valutiamo)|\b(?:offro|cerco lavoro)\b',line,re.I):continue
        return {'kind':'standing_invitation','quote':line.strip(),'role':web[0],
                'contract_quote':None,'availability':'Disponibilità dichiarata; nessuna commessa aperta verificata'}
    return None


def digital_supplier(parsed):
    from .prospecting import agency_identity
    if agency_identity(parsed):return True
    headings=' '.join(h['text'] for h in parsed['doc'].headings[:4]) if parsed.get('doc') else ''
    heading=' '.join([parsed.get('title',''),headings])
    service=re.compile(r'(?:realizzazione|creazione|sviluppo) (?:di )?siti (?:web|internet|e web\s*marketing)|sviluppo (?:web|e.?commerce)|software (?:su misura|personalizzato)|digitalizzazione (?:delle )?pmi',re.I)
    if service.search(heading):return True
    # A footer credit or a customer's case study is not the site's own offer.
    for line in parsed.get('text','')[:6000].splitlines():
        if re.search(r'website by|powered by|realizzato da|sviluppato da|credits',line,re.I):continue
        if re.search(r'\b(?:offriamo|realizziamo|sviluppiamo|siamo)\b',line,re.I) and service.search(line):return True
    return False


def linkedin_notice(item):
    url=item.get('url','');host=domain(url)
    if host!='linkedin.com' and not host.endswith('.linkedin.com'):return False
    if not re.match(r'^/(?:posts/[^/]+|feed/update/[^/]+|jobs/view/[^/]+)',urlsplit(url).path):return False
    text=str(item.get('title',''))+' '+str(item.get('content') or item.get('search_snippet') or '')
    from .research_rules import SMALL
    self_promotion=re.search(r'\b(?:cerco lavoro|cerco nuovi clienti|offro (?:servizi|sviluppo)|sono (?:un |una )?(?:web designer|freelance))\b',text,re.I)
    return bool(FREELANCE.search(text) and WEB.search(text) and REQUEST.search(text) and not EMPLOYEE.search(text) and not SMALL.search(text) and not self_promotion)


def route_exclusion(item):
    url=item.get('url','');host=domain(url)
    if DOCUMENT_PATH.search(unquote(url)):
        return 'Documento allegato escluso prima del download: cerco pagine aziendali e richieste di collaborazione.'
    from .prospect_scope import EDITORIAL
    query=item.get('query','')
    if not item.get('company_host') and not item.get('subject') and re.search(r'\b(?:elenco aziende|aziende.{0,50}associati|notizie imprese|comunicati imprese)\b',query,re.I):
        return 'Query orientata a elenchi o notizie generiche: sostituita dai canali diretti.'
    for site in re.findall(r'(?<!-)\bsite:([^\s/]+)',query,re.I):
        if any(site==h or site.endswith('.'+h) for h in DIRECTORIES+INSTITUTIONS+EDITORIAL):
            return 'Ricerca limitata a una fonte generalista o directory, fuori dai canali diretti.'
    if any(host==h or host.endswith('.'+h) for h in DIRECTORIES+INSTITUTIONS+EDITORIAL):
        return 'Fonte generalista, istituzionale o directory: ricerca concentrata su siti aziendali e richieste freelance specifiche.'
    if item.get('directory') or item.get('publisher'):
        return 'Elenco o fonte editoriale: escluso dal percorso diretto verso aziende e agenzie.'
    if re.search(r'\b(?:elenco aziende|directory (?:aziende|aziendale)|osservatorio export|rapporto congiunturale)\b',str(item.get('title','')),re.I):
        return 'Elenco o rapporto economico generale, non un committente identificato.'
    if re.search(r'aprire (?:la )?partita iva|codic[ei] ateco|come (?:diventare|aprire)|corso (?:gratuito|di formazione)',str(item.get('title','')),re.I):
        return 'Guida fiscale o formazione professionale: non una richiesta di sviluppo web.'
    if item.get('strategy') in ('explicit','partner') and GUIDE_TITLE.search(str(item.get('title',''))) and not CAREERS_PATH.search(urlsplit(url).path):
        return 'Guida su professioni o strumenti, non una richiesta aziendale: esclusa prima del download.'
    return None


def indexed_notice(payload):
    """Keep the indexed notice visible; resolve only an explicitly named employer."""
    if not linkedin_notice(payload):
        return {'state':'rejected','reason':'Risultato LinkedIn privo di una richiesta freelance web specifica, oppure lavoro dipendente.','details':{'company_ready':False}}
    title=payload.get('title','');snippet=payload.get('search_snippet','')
    # Conservative publisher/employer attribution in the result title. Unknown
    # names remain unknown; a generic skill or job title is not an employer.
    match=re.match(r'^(.{3,100}?)\s+(?:su LinkedIn\s*:|sta assumendo\b|cerca\b|ricerca\b)',title,re.I)
    subject=match[1].strip(' |–-') if match else None
    if subject and (WEB.search(subject) or REQUEST.search(subject)):subject=None
    hint={'url':payload['url'],'title':title,'snippet':snippet,'basis':'Risultato indicizzato da Google tramite Serper; annuncio originale non consultato','verified':False}
    details={'company_ready':False,'identity':{},'search_hint':hint,
             'next_action':'Verificare committente, data e richiesta su una pagina aziendale accessibile; non qualificare dallo snippet.'}
    queries=[]
    if subject:
        queries=[{'query':'"'+subject.replace('"','')+'" sito ufficiale contatti',
            'page':1,'period':'','region':payload.get('region'),'subject':subject,
            'subject_method':'Nome nel titolo indicizzato; attribuzione non verificata',
            'company_stage':'identify','search_hint':hint,'evidence_url':payload['url'],
            'root_query_key':payload.get('root_query_key') or payload.get('query_key'),
            'direct_channels':True}]
    return {'state':'needs_review','reason':'Richiesta freelance indicizzata su LinkedIn: committente e annuncio ancora da verificare; non è un’opportunità qualificata.',
            'details':details,'resolve_queries':queries}
