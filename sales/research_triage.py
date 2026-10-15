"""One original-page read before expensive research. No snippet can qualify a lead."""
import re
import json
from datetime import datetime,timezone
from urllib.parse import urlsplit,urljoin
from .research_analysis import ResearchWeb,document,identity_from,text_with_legal
from .extract import parse_page,nodes,types
from .targeting import exclusion
from .research_rules import FULL,REQUEST,EMPLOYEE,SMALL,region_of
from .research_strategies import SIGNAL,DIGITAL,NOISE,strategies_for
from .research_store import ResearchStore
from .db import domain

PUBLISHER=re.compile(r'testata giornalistica|direttore responsabile|confartigianato|confcommercio|confindustria|assolombarda|unioncamere|camera di commercio|unione industriali|quotidiano|giornale|redazione|comune di|regione\.',re.I)

def triage(store,payload,check):
    url=payload['url']
    if domain(url)=='linkedin.com' or domain(url).endswith('.linkedin.com'):
        from .direct_channels import indexed_notice
        return indexed_notice(payload)
    from .discovery_relevance import preflight
    reason=preflight(payload,payload)
    if reason:return {'state':'rejected','reason':reason,'details':{'prefetch_rejection':True,'company_ready':False}}
    from .prospect_scope import excluded_url
    out_of_scope=excluded_url(url)
    if out_of_scope:return {'state':'rejected','reason':out_of_scope,'details':{'acquisition_excluded':True}}
    excluded=store.target_exclusion(url) or ResearchStore(store).suppressed({'website':url})
    if excluded:return {'state':'rejected','reason':excluded['reason'] if isinstance(excluded,dict) else excluded,'details':{}}
    if NOISE.search(url):return {'state':'rejected','reason':'Pagina di servizio o archivio, non un segnale riferito a un’impresa.','details':{}}
    from .research_analysis import CompanyWeb
    page=(CompanyWeb if payload.get('direct_channels') else ResearchWeb)(store,check).get(url);check()
    if page['status']!=200:raise ValueError('Pagina originale HTTP '+str(page['status']))
    parsed=parse_page(page);doc=document(page,payload.get('provider','Fonte pubblica'));text=doc['research_text']
    from .organization import classify
    from .source_roles import publisher_identity
    organization=classify([page],identity_from([page]))
    if organization['category']=='public_body' and not publisher_identity(page):
        return {'state':'rejected','reason':organization['reason'],'details':{'organization':organization,'document':doc,'company_ready':False}}
    # Eliminate utility text preceding the article heading (e.g. procurement platform nav).
    headings=[h['text'] for h in parsed['doc'].headings if len(h['text'])>25]
    heading=next((h for h in headings if h.casefold() in parsed['title'].casefold() or parsed['title'].strip().casefold() in h.casefold()),None)
    if heading and heading in text:text=text[text.index(heading):]
    signal_text=parsed['title']+' '+text
    # A company named "Nuova Linea" is not announcing a new product line.
    if re.fullmatch(r'nuova\s+linea(?:\s+s\.?r\.?l\.?)?',str(parsed.get('name','')),re.I):signal_text=re.sub(r'nuova\s+linea','',signal_text,flags=re.I)
    matches=strategies_for(signal_text)
    from .source_roles import publisher_identity
    publisher=bool(payload.get('publisher') or publisher_identity(page))
    if publisher and payload.get('direct_channels'):
        return {'state':'rejected','reason':'Fonte editoriale o istituzionale: non estendo la ricerca alle imprese citate. Cerco siti aziendali e richieste freelance specifiche.','details':{'publisher':True,'company_ready':False}}
    if payload.get('company_host')==domain(page['url']) and not payload.get('publisher'):
        # Already verified company: incidental footer words cannot turn it into a publisher.
        publisher=False
    identity={} if publisher else identity_from([page])
    details={'identity':identity,'document':doc,'strategies':matches,'publisher':publisher,'published_at':doc.get('published_at'),'checked_at':doc['checked_at'],'budget':None,'contact_role':'Referente da verificare','source_date_basis':doc.get('date_origin'),'next_action':'Verificare identità, bisogno, soluzioni esistenti e contatto prima di proporre un progetto.'}
    details['organization']=organization
    if doc.get('access_limit'):
        details['limits']=[doc['access_limit']]
        details['next_action']='Cercare una fonte pubblica completa sullo stesso fatto; non aggirare l’accesso riservato.'
        return {'state':'unverifiable','reason':doc['access_limit'],'details':details}
    if publisher:details['identity']={};details['group']='publisher'
    else:
        finding=exclusion(page)
        if finding:return {'state':'rejected','reason':finding['reason'],'details':details}
    if not publisher and payload.get('direct_channels'):
        from .direct_channels import digital_supplier,request_excerpt,standing_partner_evidence,careers_page,careers_links
        demand=request_excerpt(text)
        standing=standing_partner_evidence(page) if careers_page(page) else None
        if digital_supplier(parsed) and not demand and not standing:
            if careers_links(page):
                from .company_research import inspect_company
                return inspect_company(store,payload,page,check)
            return {'state':'rejected','reason':'La pagina vende servizi digitali: nessuna richiesta concreta di fornitore o collaboratore nel testo originale.','details':details}
        if (demand or standing) and payload.get('strategy') in ('explicit','partner'):
            from .company_research import inspect_company
            # Check actual employer, region and contact even for JobPosting;
            # a freelance notice must not inherit the manufacturing filter.
            return inspect_company(store,payload,page,check)
    if publisher and doc.get('published_at'):
        try:
            age=(datetime.now(timezone.utc).date()-datetime.fromisoformat(doc['published_at'][:10]).date()).days
            from .source_identity import source_entities
            from .research_evidence import primary_articles
            named_link=any(not link.get('navigation') and 3<=len(link['text'].strip())<=80 and
                domain(urljoin(page['url'],link['url']))!=domain(page['url']) and
                re.sub(r'\W','',link['text'].casefold()) in domain(urljoin(page['url'],link['url'])).replace('-','')
                for link in parsed['doc'].links)
            if age>180 and (primary_articles(parsed) or source_entities(page,doc) or named_link):
                details.update(resolve_subject=True,source_historical=True)
                details['next_action']='Identificare le imprese citate e cercare prove attuali; la notizia storica non dimostra un bisogno tempestivo.'
                return {'state':'needs_review','resolve':True,'reason':'Fonte storica utilizzabile per identificare imprese; evento escluso dalle prove di attualità.','details':details}
        except ValueError:pass
    from .research_evidence import preliminary_disposition
    disposition=preliminary_disposition(page,parsed,text)
    if disposition:
        details['next_action']=disposition['next_action']
        state='rejected' if EMPLOYEE.search(text) and 'hiring' not in matches else 'needs_review'
        return {'state':state,'reason':disposition['reason'],'details':details}
    if (payload.get('company_stage') == 'identify' or payload.get('strategy') == 'companies') and not (publisher and matches and payload.get('hypothesis')):
        from .company_research import inspect_company, DIRECTORY, directory_profiles, directory_names
        directory=bool(payload.get('directory') or DIRECTORY.search(parsed['title']+' '+' '.join(h['text'] for h in parsed['doc'].headings[:3])) or len(directory_profiles(page))>=3 or len([n for n in directory_names(page) if n['method']=='structured'])>=3)
        if publisher and not directory:
            from .source_identity import source_entities
            from .research_evidence import primary_articles
            if source_entities(page,doc) or primary_articles(parsed):
                details['resolve_subject']=True
                return {'state':'needs_review','resolve':True,'reason':'Fonte con imprese da identificare; non è essa stessa un cliente.','details':details}
            return {'state':'rejected','reason':'Fonte editoriale o istituzionale, non un’impresa né un elenco aziendale pertinente.','details':details}
        if directory:
            if payload.get('direct_channels'):
                return {'state':'rejected','reason':'Directory aziendale esclusa: cerco direttamente i domini delle imprese.','details':{'publisher':True,'company_ready':False}}
            details.update(identity={}, publisher=True, directory=True, resolve_subject=True)
            return {'state':'needs_review','resolve':True,'reason':'Fonte con aziende da identificare; non è un cliente né una prova di bisogno.', 'details':details}
        if re.search(r'\b(?:wikipedia|treccani|enciclopedia|dizionario|università|dipartimento di ingegneria)\b', parsed['title'],re.I):
            return {'state':'rejected','reason':'Fonte enciclopedica o accademica, non una piccola impresa del segmento selezionato.','details':details}
        return inspect_company(store,payload,page,check)
    with store.connect() as c:
        previous=c.execute("SELECT d.details FROM discovery_candidates d JOIN commercial_outcomes o ON o.candidate_id=d.id WHERE d.url=? AND o.kind='not_relevant' ORDER BY o.id DESC LIMIT 1",(url,)).fetchone()
    if previous and json.loads(previous[0]).get('document',{}).get('content_hash')==doc['content_hash']:
        return {'state':'rejected','reason':'Segnata non pertinente: nessun cambiamento nella fonte già valutata.','details':details}
    # An article list is a discovery source, not a company. No LLM on a whole hub.
    if publisher and not doc.get('published_at') and len(parsed['doc'].links)>35 and not re.search(r'/\d{4}/|\.html$|/[^/]{45,}/?$',url):
        return {'state':'needs_review','reason':'Indice editoriale: esplorare gli articoli pertinenti, non proporre l’editore.','details':details,'source':True}
    dt=doc.get('published_at')
    if dt:
        try:
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(dt.replace('Z','+00:00')).replace(tzinfo=timezone.utc)).days
            linked_company=False
            if age>180 and publisher and payload.get('strategy')=='startup':
                # An old award notice is not automatically a company directory.
                # Require a named external website anchored in the original article.
                for link in parsed['doc'].links:
                    name=link['text'].strip();href=urljoin(page['url'],link['url'])
                    if link.get('navigation') or not 3<=len(name)<=80 or domain(href)==domain(url):continue
                    tokens=re.findall(r'[a-zà-ÿ0-9]{3,}',name.casefold())
                    if not tokens or re.search(r'cna|confindustria|facebook|instagram|linkedin|youtube|premio cambiamenti|regione|condividi',name+' '+domain(href),re.I):continue
                    if name.casefold() in text.casefold() and sum(t in domain(href) for t in tokens)/len(tokens)>=.75:linked_company=True;break
            if age>180 and publisher and payload.get('strategy')=='startup' and linked_company:
                details['directory']=True;details['resolve_subject']=True
                details['next_action']='Usare i nomi come elenco di imprese, cercando un bisogno attuale sul sito ufficiale. L’evento vecchio non qualifica.'
                return {'state':'needs_review','resolve':True,'reason':'Elenco storico di nuove imprese: identità da risolvere e segnale attuale ancora da trovare.','details':details}
            if age>180 or age< -1:return {'state':'needs_review','reason':'Data non attuale: serve un nuovo segnale datato, non basta ripubblicare la pagina.','details':details}
        except ValueError:pass
    if identity.get('region') and payload.get('filters',{}).get('regions') and identity['region'] not in payload['filters']['regions']:
        return {'state':'rejected','reason':'Indirizzo pubblico fuori dalle regioni selezionate.','details':details}
    if not text.strip():return {'state':'unverifiable','reason':'Nessun testo leggibile nella fonte originale.','details':details}
    if payload.get('company_host') and not (set(matches)-{'partner','tender'}):
        return {'state':'needs_review','reason':'Pagina aziendale letta: descrive l’attività o relazioni ordinarie, senza un evento o bisogno specifico da approfondire.','details':details}
    if not publisher and not payload.get('company_host') and payload.get('hypothesis'):
        from .company_research import inspect_company
        result=inspect_company(store,payload,page,check)
        result['details']['strategies']=matches
        return result
    if not matches:return {'state':'rejected','reason':'La pagina originale non documenta un segnale pertinente alle strategie commerciali.','details':details}
    if SMALL.search(text) and not FULL.search(text):return {'state':'rejected','reason':'Intervento limitato, non emerge un progetto completo.','details':details}
    primary=payload.get('strategy','change')
    if primary=='explicit' and EMPLOYEE.search(text) and not re.search(r'fornitor|freelance|partita iva',text,re.I):
        if 'hiring' in matches:
            details['strategies'].append('hiring');details['next_action']='Assunzione come segnale complementare; trovare un bisogno digitale indipendente.'
            return {'state':'needs_review','reason':'Offerta di lavoro dipendente, non una commessa freelance.','details':details}
        return {'state':'rejected','reason':'Offerta di lavoro dipendente, non una richiesta di fornitura.','details':details}
    if primary=='explicit' and not (REQUEST.search(text) and DIGITAL.search(text)):
        return {'state':'needs_review','reason':'Richiesta di progetto non riscontrata nel testo originale.','details':details}
    # Partnerships stay visible in a separate track. A generic supplier is not a buyer.
    if not publisher and (primary=='partner' or identity.get('group')=='agencies'):
        details['group']='agencies';details['relationship']='partner'
        if not (REQUEST.search(text) and FULL.search(text)):
            details['next_action']='Verificare un’esigenza di collaborazione concreta e complementare. Non è una commessa qualificata.'
            return {'state':'needs_review','reason':'Possibile partner: complementarità da verificare, nessun progetto commissionato dimostrato.','details':details}
    if primary=='tender':
        if re.search(r'reclutamento|profili professionali|profilo legale|assunzion',parsed['title'],re.I):
            return {'state':'rejected','reason':'Avviso di reclutamento professionale, non affidamento di un progetto digitale.','details':details}
        if not DIGITAL.search(parsed['title']+' '+text[:1800]):return {'state':'rejected','reason':'Gara senza un progetto digitale pertinente.','details':details}
        details['procurement']={'deadline':'unknown','eligibility':'unknown','requirements':'unknown','fees':'unknown'}
        details['next_action']='Verificare scadenza, requisiti, oneri e accessibilità per un professionista individuale nel capitolato.'
    if publisher and re.search(r'fondo|basket bond|bando|risorse disponibili|risorse pubbliche',parsed['title'],re.I) and not re.search(r'beneficiari\s*[:–-]|(?:assegnat|ottenut|ricevut|finanziat).{0,40}(?:srl|s\.r\.l)',text,re.I):
        return {'state':'needs_review','reason':'Notizia su uno strumento finanziario: nessuna impresa beneficiaria identificata. Non è un budget di progetto.','details':details}
    # Catalogue/email alone is not enough to spend minutes of local inference.
    if set(matches)<= {'gap','process'} and not re.search(r'configura|multilistino|personalizz|integra|nuov|ester|distributor|non (?:consente|permette)|manualment',text,re.I):
        return {'state':'needs_review','reason':'Catalogo o procedura ordinaria: manca un problema commerciale osservabile.','details':details}
    excerpts=[]
    for m in SIGNAL.finditer(text):
        excerpt=text[max(0,m.start()-100):min(len(text),m.end()+280)].strip()
        if excerpt not in excerpts:excerpts.append(excerpt)
        if len(excerpts)==4:break
    details['excerpts']=excerpts
    details['hypothesis']='Segnale da collegare a un progetto completo; non dimostra intenzione d’acquisto.'
    if publisher:
        details['resolve_subject']=True
        return {'state':'needs_review','resolve':True,'reason':'Articolo pertinente: identificare e verificare le aziende citate. L’editore non è un cliente.','details':details}
    return {'state':'promising','reason':'Segnale riscontrato nella pagina originale. '+('Occorre identificare l’impresa citata, non l’editore.' if publisher else 'Da verificare bisogno specifico, dimensione del progetto e alternative già disponibili.'),'details':details}
