"""Extract statements with their provenance; text is data, never instructions."""
import json
import re
from datetime import datetime,timezone
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit,urlunsplit
from .providers import canonical
from .db import domain
from .prospecting import direct_project_request
from .selection import digital_project, GROWTH_REJECTION

SKILLS={'WordPress':r'\bwordpress\b','WooCommerce':r'\bwoocommerce\b','React / Next.js':r'\b(?:react|next\.?js)\b','Frontend':r'\b(?:front.?end|html|css|scss|javascript|gsap|webgl)\b','UI/UX':r'\b(?:web design(?:er)?|ui/ux|user experience)\b','Sito aziendale':r'\bsit[oi] (?:web|internet|aziendal\w*)','E-commerce':r'\be-?commerce\b','Landing page':r'\blanding page\b'}
REQUEST=re.compile(r'\b(?:cerchiamo|cerco|cercasi|ricerchiamo|selezioniamo|siamo alla ricerca di|stiamo cercando|è alla ricerca di|we are looking for|we.re looking for|I am looking for|we are hiring|we are seeking|is seeking)\b',re.I)
ROLE=re.compile(r'\b(?:sviluppator\w*|web designer|web developer|front.?end|programmat\w*|realizz\w* (?:un |il |un nuovo )?sit[oi]|rifar\w* (?:il |un )?sito|wordpress|woocommerce|react|next\.?js)\b',re.I)
EXTERNAL=re.compile(r'\b(?:freelanc\w*|partita\s*iva|p\.?\s*iva|collaborazion\w* estern\w*|collaborator\w* estern\w*|contractor|contract role|a progetto)\b',re.I)
GROWTH=re.compile(r'\b(?:inauguriamo|abbiamo inaugurato|apriamo|abbiamo aperto|ha cambiato sede|ci siamo trasferiti|nuov[oaie] (?:attivit[àa]|laboratori[oa]?|sed[ei]|negozi[oa]?|punt[oi] vendita|showroom|stabiliment[oi]|line[ae] di prodotti|marchi[oa]|collezion[ei]|e-?commerce)|lanciamo|abbiamo lanciato|espansione internazionale|new (?:store|office|product line)|we (?:are launching|have opened))\b',re.I)
AGENCY=re.compile(r'\b(?:agenzia|agency|studio (?:di )?(?:comunicazione|branding|design|grafico)|software house|web agency)\b',re.I)
PARTNER=re.compile(r'\b(?:collaborazion\w*|partnership|partner tecnic\w*|fornitor\w*|nuovi servizi|nuovo progetto)\b',re.I)
CLOSED=re.compile(r'\b(?:annuncio scaduto|posizione chiusa|ricerca conclusa|position (?:closed|filled)|no longer accepting|applications closed|no freelance|non cerchiamo freelance)\b',re.I)

def web_reference(href):
    r"""Normalize HTML path separators before resolving a relative web link.

    Some sites use href="\\" for their logo. urljoin treats it as a filename,
    unlike browser navigation. Never repair ambiguous authorities or decode
    percent escapes; query strings, fragments and non-web schemes are data.
    """
    if not isinstance(href,str):return None
    try:
        p=urlsplit(href)
        if p.scheme and p.scheme not in ('http','https'):return href
        if '\\' in p.netloc:return None
        path=p.path.replace('\\','/')
        if not p.netloc and path.startswith('//'):return None
        return urlunsplit((p.scheme,p.netloc,path,p.query,p.fragment))
    except ValueError:return None


def layout_text_boundary(attrs):
    """Explicit layout containers separate labels even when their tag is span.

    Ordinary inline markup must keep spelling intact (e.g. Woo<b>Commerce</b>).
    No stylesheet fetch, inferred semantics or site-specific selector is used.
    """
    return bool(set(attrs.get('class','').split()) & {'flex','inline-flex','grid','inline-grid','block'}
                or re.search(r'(?:^|;)\s*display\s*:\s*(?:flex|inline-flex|grid|inline-grid|block)\s*(?:!important\s*)?(?:;|$)',
                             attrs.get('style',''),re.I))

VOID_TAGS={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}

class Document(HTMLParser):
    def __init__(self,html):
        super().__init__(convert_charrefs=True)
        self.parts=[];self.title='';self.headings=[];self.links=[];self.meta={};self.schemas=[];self.forms=[];self.inputs=[];self.images=[];self.times=[];self.publication_times=[]
        self.canonical=None;self.canonicals=[];self.time_attributes=[]
        self.skip=0;self.ld=False;self.raw=[];self.in_title=False;self.heading=None;self.hparts=[];self.anchor=None;self.anchor_parts=[];self.anchor_navigation=False
        self.layout_stack=[]
        self.feed(html)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        layout=layout_text_boundary(a)
        if layout:self.parts.append('\n')
        if tag not in VOID_TAGS:self.layout_stack.append((tag,layout))
        if tag=='link' and 'canonical' in a.get('rel','').lower().split():
            self.canonical=web_reference(a.get('href',''))
            self.canonicals.append(a.get('href',''))
        if tag in ('script','style','noscript','nav','footer','header'): self.skip+=1
        if tag=='script' and a.get('type')=='application/ld+json': self.ld=True;self.raw=[]
        if tag=='title': self.in_title=True
        if tag in ('h1','h2','h3'): self.heading=tag;self.hparts=[]
        if tag=='meta': self.meta[a.get('property',a.get('name','')).lower()]=a.get('content','')
        if tag=='time' and a.get('datetime'): self.times.append(a['datetime'])
        if tag=='time' and a.get('datetime'): self.time_attributes.append(a)
        if tag=='time' and a.get('datetime') and 'datePublished' in a.get('itemprop','').split():self.publication_times.append(a['datetime'])
        if tag=='a': self.anchor=web_reference(a.get('href',''));self.anchor_parts=[];self.anchor_navigation=bool(self.skip)
        if tag=='form': self.forms.append(a)
        if tag in ('input','textarea','select'): self.inputs.append(a)
        if tag=='img': self.images.append(a)
        if tag in ('p','div','section','article','li','br','h1','h2','h3','select','option','optgroup'): self.parts.append('\n')
    def handle_endtag(self,tag):
        for i in range(len(self.layout_stack)-1,-1,-1):
            if self.layout_stack[i][0]==tag:
                if any(boundary for _,boundary in self.layout_stack[i:]):self.parts.append('\n')
                del self.layout_stack[i:]
                break
        if tag=='script' and self.ld:
            try: self.schemas.append(json.loads(''.join(self.raw)))
            except ValueError: pass
            self.ld=False
        if tag in ('script','style','noscript','nav','footer','header'): self.skip=max(0,self.skip-1)
        if tag=='title': self.in_title=False
        if tag==self.heading: self.headings.append({'tag':tag,'text':' '.join(' '.join(self.hparts).split())});self.heading=None
        if tag=='a' and self.anchor is not None: self.links.append({'url':self.anchor,'text':' '.join(' '.join(self.anchor_parts).split()),'navigation':self.anchor_navigation});self.anchor=None
        if tag in ('p','div','section','article','li','h1','h2','h3','select','option','optgroup'): self.parts.append('\n')
    def handle_data(self,data):
        if self.ld:self.raw.append(data)
        if self.in_title:self.title+=data
        if self.heading:self.hparts.append(data)
        if self.anchor is not None:self.anchor_parts.append(data)
        if not self.skip and not self.in_title:self.parts.append(data)
    @property
    def text(self): return '\n'.join(' '.join(p.split()) for p in ''.join(self.parts).splitlines() if p.strip())

def nodes(value):
    if isinstance(value,dict):
        yield value
        for v in value.values(): yield from nodes(v)
    elif isinstance(value,list):
        for v in value: yield from nodes(v)
def types(node):
    t=node.get('@type',[]);return {t} if isinstance(t,str) else set(t) if isinstance(t,list) and all(isinstance(v,str) for v in t) else set()
def iso_date(value):
    if not isinstance(value,str): return None
    try:
        d=datetime.fromisoformat(value[:10]).date()
        return d.isoformat() if d<=datetime.now(timezone.utc).date() else None
    except ValueError:return None

def parse_page(page):
    d=Document(page['html']);allnodes=list(nodes(d.schemas))
    jobs=[n for n in allnodes if 'JobPosting' in types(n)]
    editorial=any(types(n)&{'Article','NewsArticle','BlogPosting'} for n in allnodes)
    job=jobs[0] if len(jobs)==1 else None
    text=Document(str(job.get('description',''))).text if job and job.get('description') else d.text
    title=str(job.get('title') or d.title) if job else d.title
    publication=None;date_origin=None
    for value,origin in [(job.get('datePosted') if job else None,'JobPosting.datePosted'),(d.meta.get('article:published_time'),'article:published_time')]+[(n.get('datePublished'),'Dati strutturati datePublished') for n in allnodes if types(n)&{'Article','BlogPosting','NewsArticle','WebPage'}]+[(d.times[0] if len(d.times)==1 else None,'Elemento time')]:
        publication=iso_date(value)
        if publication:date_origin=origin;break
    if not publication:
        months={'gennaio':1,'febbraio':2,'marzo':3,'aprile':4,'maggio':5,'giugno':6,'luglio':7,'agosto':8,'settembre':9,'ottobre':10,'novembre':11,'dicembre':12}
        visible=[]
        for day,month,year in re.findall(r'^\s*(?:Pubblicato(?: il)?\s+)?(\d{1,2})\s+('+'|'.join(months)+r')\s*,?\s*(20\d{2})\s*$',text,re.I|re.M):
            value=iso_date(f'{year}-{months[month.lower()]:02d}-{int(day):02d}')
            if value:visible.append(value)
        if len(set(visible))==1:publication=visible[0];date_origin='Data esplicita nel testo della pagina'
    if not publication:
        printed=re.search(r'\bPubblicato\s*:\s*(\d{2})[./](\d{2})[./](20\d{2})\b',text,re.I)
        if printed:
            publication=iso_date(f'{printed[3]}-{printed[2]}-{printed[1]}')
            if publication:date_origin='Data di pubblicazione esplicita nel testo'
    employer=(job.get('hiringOrganization') or {}) if job else {}
    name=employer.get('name') if isinstance(employer,dict) else None
    for n in allnodes:
        if types(n)&{'Organization','Corporation','LocalBusiness','ProfessionalService'} and domain(str(n.get('url','')))==domain(page['url']):
            name=name or n.get('name')
    # Site-name is explicitly labelled as a declared brand, not a verified legal identity.
    name=name or d.meta.get('og:site_name')
    contacts=[]
    for link in d.links:
        if link['url'].startswith('mailto:'):
            value=link['url'][7:].split('?')[0]
            if re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+',value): contacts.append({'type':'email','value':value,'url':page['url'],'checked_at':page['checked_at'],'basis':'Pubblicato sul sito; non implica consenso'})
        elif link['url'].startswith('tel:'): contacts.append({'type':'phone','value':link['url'][4:],'url':page['url'],'checked_at':page['checked_at'],'basis':'Contatto pubblico'})
    loc=None
    addresses=[n for n in allnodes if 'PostalAddress' in types(n)]
    if job and isinstance(job.get('jobLocation'),dict):
        addr=job['jobLocation'].get('address')
        if isinstance(addr,dict):addresses.insert(0,addr)
    for addr in addresses:
        parts=[addr.get(k) for k in ('addressLocality','addressRegion','addressCountry') if isinstance(addr.get(k),str)]
        if parts:loc=', '.join(dict.fromkeys(parts));break
    match=re.search(r'(?:Sede(?: di lavoro)?|Località|Location)\s*:\s*([^\n.]{2,100})',text,re.I)
    if match:loc=match.group(1).strip()
    sector='Agenzia / servizi digitali' if AGENCY.search(text[:3500]) else None
    for label,pattern in [('Retail / commercio',r'\bnegozi|punti vendita|retail\b'),('Industria / manifattura',r'\b(?:produzion\w*|industr\w*|manifattur\w*|lavorazion[ei] meccanic\w*|officin\w*|tornitur\w*|fresatur\w*|carpenteri\w*|stampaggio)'),('Ospitalità',r'\bhotel|albergo|ristorante\b'),('Servizi professionali',r'\bconsulenza|studio professionale\b')]:
        if sector is None and re.search(pattern,text[:4000],re.I):sector=label+' · inferito'
    return {'doc':d,'text':text,'title':title[:250],'name':name,'name_basis':'Identità dichiarata dalla pagina' if name else 'Dominio; identità da verificare','published_at':publication,'date_origin':date_origin,'contacts':contacts,'location':loc,'sector':sector,'job':job,'multi_job':len(jobs)>1,'editorial':editorial}

def classify(parsed,engine,url):
    text=parsed['text'];job=parsed['job'];title=parsed['title'];lines=text.splitlines()
    if re.search(r'(?:migliori|top|best)\s+(?:\d+\s+)?agenzie|trova\s+(?:un.?)?agenzia|directory di agenzie',title+' '+text[:1500],re.I):return None,'Directory di agenzie, non richiesta di un committente'
    if parsed['multi_job']:return None,'Elenco di annunci: necessario il dettaglio della singola richiesta'
    if re.search(r'\bjob board|\d+ offerte di lavoro|start your search|browse jobs|we.ve got you covered',title+' '+text[:1000],re.I):return None,'Catalogo o contenuto promozionale'
    if engine in ('A','B') and (parsed['editorial'] or re.search(r'/(?:blog|resources|guide|tutorials|articoli)/',urlsplit(url).path,re.I)) and not job:return None,'Articolo informativo, non richiesta di collaborazione'
    if CLOSED.search(text[:10000]):return None,'Richiesta chiusa o freelance esclusi'
    if job and iso_date(job.get('validThrough')) and iso_date(job.get('validThrough'))<datetime.now(timezone.utc).date().isoformat():return None,'Annuncio scaduto'
    date=parsed['published_at'];age=(datetime.now(timezone.utc).date()-datetime.fromisoformat(date).date()).days if date else None
    if age is not None and age>120:return None,'Informazione più vecchia di 120 giorni'
    request=None;scope=text[:8000]
    for line in lines:
        m=REQUEST.search(line)
        if m and ROLE.search(line[m.end():m.end()+100]) and not re.search(r'\bcer(?:co|chiamo) di\b',line,re.I) and not re.search(r'\b(?:copywriter|social media manager|come trovare|whether you|se stai cercando)\b',line,re.I):
            request=line;offset=text.find(line);scope=text[offset:offset+3500]
            # Stop at a subsequent vacancy/request instead of borrowing its skills.
            following=scope.splitlines();end=next((n for n,l in enumerate(following[1:],1) if REQUEST.search(l) or re.search(r'posizione aperta|^(?:mobile|full stack|back.?end|front.?end|wordpress) (?:developer|designer)',l,re.I)),len(following))
            scope='\n'.join(following[:end]);break
    if not request:
        request=next((line for line in lines if direct_project_request(line)),None)
        if request:
            offset=text.find(request);scope=text[offset:offset+3500]
    # Explicit application channels on company career pages also express demand,
    # even when the copy says 'collaboriamo' instead of 'cerchiamo'.
    if not request and re.search(r'lavora-con-noi|careers|/jobs|collabora',urlsplit(url).path,re.I):
        invitation=bool(re.search(r'invia (?:la tua )?candidatura|invia(?:ci)? (?:il )?(?:cv|curriculum)|apply now',text,re.I))
        professionals=bool(re.search(r'professionisti autonomi|collaboratori remoti|freelance',text,re.I))
        roles=[l for l in lines if re.search(r'^(?:\d{1,2}\s+)?(?:WordPress|Frontend|React|Next\.?js|Web) (?:developer|designer)$',l,re.I)]
        if invitation and professionals and roles:
            invitation_line=next((l for l in lines if re.search(r'professionisti autonomi|collaboratori remoti|freelance',l,re.I)), 'Invia candidatura')
            request=invitation_line+' Profili: '+'; '.join(roles[:3]);scope=text[:7000]
    if not request and job and ROLE.search(title) and EXTERNAL.search(text): request=title;scope=text[:8000]
    skills=[k for k,v in SKILLS.items() if re.search(v,scope,re.I)]
    remote=bool(re.search(r'\bremot[eoia]|telelavoro|smart working',scope,re.I))
    italian=domain(url).endswith('.it') or bool(re.search(r'\b(?:italia|italy|italiano|italiana|cerchiamo|cerco|siamo|abbiamo)\b',scope,re.I))
    if not italian and not remote:return None,'Mercato estero senza collaborazione remota esplicita'
    if re.search(r'\b(?:US only|USA only|UK only|must be based in the US)\b',scope,re.I):return None,'Vincolo geografico non compatibile'
    if engine in ('A','B'):
        path=urlsplit(url).path.lower()
        if re.search(r'/state/|/category/|/tag/|/page/\d|/lavoro-[^/]+|/offerte-lavoro/?$',path) and not job:
            return None,'Pagina di raccolta: occorre la richiesta originale del committente'
        if job:
            employer=job.get('hiringOrganization') or {}
            employer_url=employer.get('url') or employer.get('sameAs') if isinstance(employer,dict) else None
            if isinstance(employer_url,str) and domain(employer_url)!=domain(url):
                return None,'Annuncio su dominio terzo: verificare il sito originale del committente'
        if re.search(r'\b(?:portale del lavoro|agenzia per il lavoro|aggregatore|annunci di lavoro|offerte di lavoro da|job search|job aggregator)\b',text[:3000],re.I) and not job:
            return None,'Intermediario o elenco di annunci, identità aziendale non risolta'
    kind=None;statement=None;label=None
    if request and re.search(r'organico interno|tempo indeterminato|solo dipendent|full.time in sede',request,re.I) and not EXTERNAL.search(request):return None,'La richiesta riguarda personale interno; non attribuire condizioni di altre posizioni'
    if engine=='A':
        if not request or not skills:return None,'Nessuna richiesta esplicita per le competenze del profilo'
        external=bool(EXTERNAL.search(scope));direct=bool(re.search(r'\b(?:cerco|cercasi|I am looking)\b',request,re.I)) or direct_project_request(request)
        if not external and not direct and not (professionals if 'professionals' in locals() else False):return None,'Collaborazione freelance non esplicita'
        if not external and re.search(r'assunzion|tempo indeterminato|apprendistato',scope,re.I):return None,'Assunzione dipendente'
        kind='request';statement=request;label='Richiesta esplicita di sviluppo'
    elif engine=='B':
        if request and (EXTERNAL.search(scope) or re.search(r'professionisti autonomi|collaboratori remoti',scope,re.I)) and skills:kind='request';statement=request;label='Ricerca di un collaboratore esterno'
        elif AGENCY.search(text[:6000]):
            statement=next((line for line in lines if PARTNER.search(line) and re.search(r'\b(?:nuov[oaie]|cerch\w*|ricerc\w*|ampli\w*|annunc\w*|present\w*|lanci\w*)\b',line,re.I)),None)
            if statement:kind='signal';label='Segnale di collaborazione / nuovi servizi'
        if not statement:return None,'Agenzia senza segnale concreto di collaborazione o cambiamento'
    elif engine=='C':
        publisher=(parsed['name'] or '')+' '+parsed['doc'].meta.get('author','')
        if re.search(r'\b(?:redazione|quotidiano|giornale|magazine|notizie|news)\b',publisher,re.I) or any('NewsMediaOrganization' in types(n) for n in nodes(parsed['doc'].schemas)):
            return None,'Fonte editoriale: prima risolvere e verificare il sito dell’azienda citata'
        statements=[line for line in lines if GROWTH.search(line) and len(line)>30 and not re.search(r'come aprire|guida|consigli|se vuoi|potresti',line,re.I)]
        if not statements:return None,'Nessun cambiamento aziendale concreto nella pagina'
        if not date:return None,'Segnale di crescita senza data verificabile'
        # Match a first-party paragraph, rather than stopping at a generic headline.
        owned=[line for line in statements if re.search(r'\b(?:inauguriamo|abbiamo|apriamo|lanciamo|nostr[oaie])\b',line,re.I) or (parsed['name'] and len(parsed['name'])>3 and parsed['name'].lower() in line.lower())]
        if not owned:return None,'Identità del committente non collegata con certezza alla fonte'
        need=next((line for line in lines if digital_project(line)),None)
        if not need:return None,GROWTH_REJECTION
        statement=owned[0] if need==owned[0] else owned[0]+' '+need
        kind='signal';label='Progetto web dichiarato in un aggiornamento aziendale';skills=skills or ['Sito aziendale']
    if not statement:return None,'Nessun segnale pertinente'
    requirements=[]
    mandatory=re.search(r'Requisiti Obbligatori(.*?)(?:Requisiti Preferenziali|Responsabilità|Cosa offriamo|$)',scope,re.I|re.S)
    if mandatory:
        for skill in ['Vue.js','Laravel','Angular','Python','Django','Java','C#']:
            if re.search(r'(?<!\w)'+re.escape(skill)+r'(?!\w)',mandatory.group(1),re.I):requirements.append('Requisito obbligatorio da confrontare con il profilo: '+skill)
    years=re.search(r'almeno \d+ anni|\d+\+? years',scope,re.I)
    if years:requirements.append('Esperienza richiesta nella fonte: '+years.group(0)+'; esperienza del profilo da confermare')
    budget=re.search(r'(?:budget|compenso|budget range|tariffa)[^\n]{0,90}',scope,re.I)
    competition=re.search(r'(\d+)\s+(?:candidat\w*|applications|proposals|offerte)',scope,re.I)
    return {'kind':kind,'label':label,'statement':statement[:1800],'scope':scope[:7000],'skills':skills,'remote':remote,'date':date,'budget':budget.group(0) if budget else None,'competition':int(competition.group(1)) if competition else None,'requirements':requirements,'ongoing':bool(re.search(r'continuativ|ongoing|long.term',scope,re.I))},None
