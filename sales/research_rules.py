"""Evidence gates, not an acquisition probability. No network or LLM authority here."""
import re
from datetime import datetime,timezone
from .db import digest,domain,now

REGION_CITIES={
 'Veneto':'Padova Venezia Treviso Verona Vicenza Rovigo Belluno',
 'Lombardia':'Milano Bergamo Brescia Como Cremona Lecco Lodi Mantova Monza Pavia Sondrio Varese',
 'Piemonte':'Torino Alessandria Asti Biella Cuneo Novara Vercelli Verbania',
 'Toscana':'Firenze Arezzo Grosseto Livorno Lucca Massa Pisa Pistoia Prato Siena',
 'Emilia-Romagna':'Bologna Modena Parma Piacenza Ravenna Reggio Emilia Rimini Ferrara Forlì Cesena',
 'Liguria':'Genova Imperia Savona La Spezia',
 'Friuli-Venezia Giulia':'Trieste Udine Gorizia Pordenone',
 'Trentino-Alto Adige':'Trento Bolzano',
 'Valle d’Aosta':'Aosta', 'Lazio':'Roma Latina Frosinone Rieti Viterbo',
}
ALLOWED_REGIONS=tuple(REGION_CITIES)
PRIORITY_REGIONS=ALLOWED_REGIONS[:4]
REGION_CODES={'PD':'Veneto','VE':'Veneto','VI':'Veneto','VR':'Veneto','TV':'Veneto','BL':'Veneto','RO':'Veneto','MI':'Lombardia','BG':'Lombardia','BS':'Lombardia','CO':'Lombardia','CR':'Lombardia','LC':'Lombardia','LO':'Lombardia','MN':'Lombardia','MB':'Lombardia','PV':'Lombardia','SO':'Lombardia','VA':'Lombardia','TO':'Piemonte','AL':'Piemonte','AT':'Piemonte','BI':'Piemonte','CN':'Piemonte','NO':'Piemonte','VC':'Piemonte','VB':'Piemonte','FI':'Toscana','AR':'Toscana','GR':'Toscana','LI':'Toscana','LU':'Toscana','MS':'Toscana','PI':'Toscana','PT':'Toscana','PO':'Toscana','SI':'Toscana','BO':'Emilia-Romagna','MO':'Emilia-Romagna','PR':'Emilia-Romagna','PC':'Emilia-Romagna','RA':'Emilia-Romagna','RE':'Emilia-Romagna','RN':'Emilia-Romagna','FE':'Emilia-Romagna','FC':'Emilia-Romagna','GE':'Liguria','IM':'Liguria','SV':'Liguria','SP':'Liguria','TS':'Friuli-Venezia Giulia','UD':'Friuli-Venezia Giulia','GO':'Friuli-Venezia Giulia','PN':'Friuli-Venezia Giulia','TN':'Trentino-Alto Adige','BZ':'Trentino-Alto Adige','AO':'Valle d’Aosta','RM':'Lazio','LT':'Lazio','FR':'Lazio','RI':'Lazio','VT':'Lazio'}
from .research_strategies import STRATEGIES
MINIMUMS={'website':2000,'ecommerce':5000,'webapp':None}
SMALL=re.compile(r'correzion[ei] (?:css|bug)|piccol[oi] (?:intervent|modific)|aggiornamento (?:di )?contenuti|manutenzione ordinaria|cambio (?:di )?hosting',re.I)
FULL=re.compile(r'rifacimento (?:completo|integrale)|nuovo sito|nuov[oa] (?:e-?commerce|portale|piattaforma)|realizz\w* (?:un |il |un nuovo )?(?:sito|e-?commerce|portale)|migrazion\w*|gestionale personalizzato|svilupp\w* (?:un |una |il |la )?(?:sito|e-?commerce|portale|piattaforma|web app)',re.I)
COMPLETED=re.compile(r'(?:già|ora) (?:online|disponibile|attivo)|abbiamo (?:lanciato|realizzato)|progetto (?:concluso|completato)|fornitore (?:già )?(?:scelto|selezionato)|richiesta (?:chiusa|scaduta)',re.I)
CLOSED_REQUEST=re.compile(r'fornitore\s+(?:già\s+)?(?:scelto|selezionato)|richiesta\s+(?:chiusa|scaduta)|(?:progetto|commessa)\s+(?:conclus[oa]|completat[oa])',re.I)
EMPLOYEE=re.compile(r'tempo indeterminato|contratto (?:di lavoro|dipendente)|assunzione(?!\s+(?:al|in|di)\s+bilancio)|\bRAL\b|full.?time employee',re.I)
RISK=re.compile(r'dati (?:sanitari|biometrici)|diagnos\w*|dispositiv\w* medic\w*|trading|safety.critical|controllo industriale|mission.critical|24\s*/\s*7|PCI.DSS',re.I)
REQUEST=re.compile(r'cerchiamo|cerco|richiesta (?:di )?offerta|richiesta (?:di )?preventivo|ricerca (?:di un )?fornitore|selezione (?:di un )?fornitore|we (?:need|are looking)',re.I)

def normalize(text):return ' '.join(str(text or '').casefold().split())
def region_of(location):
    # Printed addresses often use typographic separators. Keep the original
    # evidence unchanged; normalize only the local geographic parser input.
    location=re.sub('[–—−]','-',location or '')
    text=normalize(location)
    # Street names (via Roma/Firenze) cannot establish a company's region.
    postal=list(re.finditer(r'\b\d{5}\b',text))
    if postal:text=text[postal[0].end():]
    else:text=re.sub(r'\b(?:via|viale|piazza|corso|strada)\s+[^,;\n]*?(?:\d+[a-z]?|[,;]|$)',' ',text)
    code=re.search(r'\(([A-Z]{2})\)',location or '') or re.search(r'\b([A-Z]{2})\s+\d{5}\b',location or '') or re.search(r'(?:^|[, -])([A-Z]{2})(?:\s*[, -]\s*(?:IT|Italia|Italy)\b|$)',location or '')
    if not code:
        # CAP + municipality + explicitly separated province, even when a VAT
        # label follows on the same footer line. Never infer from a street name.
        code=re.search(r'\b\d{5}\s*[-,]?\s*[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .’\'-]{1,70}?\s*[-,]\s*([A-Z]{2})(?=\s|[,.]|$)',location)
    if code:return REGION_CODES.get(code[1])
    for region,cities in REGION_CITIES.items():
        names=re.findall(r'La Spezia|Reggio Emilia|[A-ZÀ-Ý][a-zà-ÿ]+',cities)
        if normalize(region) in text or any(re.search(r'(?<!\w)'+re.escape(normalize(city))+r'(?!\w)',text) for city in names):return region
    return None

def fingerprint_signal(kind,quote):
    # Date, case, punctuation and publisher wrappers cannot create independence.
    words=re.findall(r'\w+',normalize(quote));return digest(' '.join(words))

def independent(signals):
    # Keep distinct quotations even when the documents share one origin. A
    # syndication cluster limits independence; it must not erase counterproofs
    # or complementary facts. Symmetric overlap avoids a generic short phrase
    # swallowing a longer, specific statement.
    kept=[]
    for signal in signals:
        words=set(re.findall(r'\w+',normalize(signal['quote'])))
        duplicate=False
        for old in kept:
            # One literal passage can describe an event AND the solution already
            # delivered, or a request AND its budget. Keep those distinct roles;
            # the shared event_key still prevents an independence bonus.
            if signal['kind']!=old['kind']:continue
            prev=set(re.findall(r'\w+',normalize(old['quote'])))
            overlap=len(words&prev)/max(1,len(words|prev))
            if normalize(signal['quote'])==normalize(old['quote']) or overlap>=.8:duplicate=True;break
        if not duplicate:kept.append(signal)
    return kept

def validate_signals(proposed,documents):
    docs={d['id']:d for d in documents};out=[];invalid=[]
    # Syndicated documents form one origin even when a model chooses different excerpts.
    clusters={};bags={}
    for d in documents:
        words=re.findall(r'\w+',normalize(d.get('research_text',d['text'])))
        bag={' '.join(words[n:n+5]) for n in range(max(1,len(words)-4))};bags[d['id']]=bag
        clusters[d['id']]=d['id']
        for prev in documents:
            if prev['id']==d['id']:break
            old=bags[prev['id']]
            if len(bag&old)/max(1,len(bag|old))>=.75:
                clusters[d['id']]=clusters[prev['id']];break
    duplicated={v for v in clusters.values() if list(clusters.values()).count(v)>1}
    if not isinstance(proposed,list):return [],['Risposta priva di un elenco di riscontri']
    kinds={'event','business','gap','condition','process','request','scope','counterevidence','budget','risk'}
    for raw in proposed:
        if not isinstance(raw,dict):invalid.append('Riscontro non strutturato');continue
        doc=docs.get(raw.get('document_id'));quote=raw.get('quote')
        if not doc or raw.get('kind') not in kinds or not isinstance(quote,str) or len(quote.strip())<18 or len(quote)>1500 or normalize(quote) not in normalize(doc['text']):invalid.append('Citazione non riscontrata nella fonte originale');continue
        out.append({'id':digest(doc['id']+raw['kind']+normalize(quote))[:20],'document_id':doc['id'],'kind':raw['kind'],'quote':quote.strip(),'url':doc['url'],'published_at':doc.get('published_at'),'checked_at':doc['checked_at'],'official':bool(doc.get('official')),'event_key':('syndicated:'+clusters[doc['id']] if clusters[doc['id']] in duplicated else fingerprint_signal(raw['kind'],quote))})
    from .claim_grounding import grounded_signals
    return independent(grounded_signals(out)),invalid

def qualify(identity,documents,signals,proposal,validation,*,strategy='change',limits=None,excluded=None):
    from .claim_grounding import grounded_signals
    limits=limits or [];signals=independent(grounded_signals(signals));bykind={k:[s for s in signals if s['kind']==k] for k in ('event','business','gap','process','request','scope','counterevidence','budget','risk')}
    project=proposal.get('project');selected=set(proposal.get('support_ids',[]));support=[s for s in signals if s['id'] in selected]
    official=[s for s in signals if s.get('official')]
    explicit=any(s['kind']=='request' and REQUEST.search(s['quote']) and FULL.search(s['quote']) and not EMPLOYEE.search(s['quote']) and not CLOSED_REQUEST.search(s['quote']) for s in official if s['id'] in selected)
    evidence_refs={s['id'] for s in signals}
    validation_ok=validation.get('status')=='supported' and bool(validation.get('support_ids')) and set(validation.get('support_ids',[]))<=evidence_refs
    signal_current=[]
    for s in support:
        try:
            age=(datetime.now(timezone.utc).date()-datetime.fromisoformat(s['published_at'][:10]).date()).days if s.get('published_at') else None
            current=age is not None and 0<=age<=180
            # A live process is observed now; merely reading an undated announcement doesn't date it.
            if s['kind'] in ('process','gap') and s.get('official'):
                current=0<=(datetime.now(timezone.utc)-datetime.fromisoformat(s['checked_at'])).total_seconds()<=7*86400
            if current:signal_current.append(s)
        except (ValueError,TypeError):pass
    if explicit and not any(s['kind']=='request' for s in signal_current):explicit=False
    services={'website':r'sito|web.?site|wordpress|vetrina','ecommerce':r'e.?commerce|negozio online|vendita online|woocommerce|shopify|shop','webapp':r'web.?app|portale|gestional|piattaforma|configurator|prenotazion|software|applicazion'}
    digital_fit=bool(project in services and re.search(services[project],proposal.get('proposal',''),re.I))
    concrete=bool(support and proposal.get('why') and digital_fit and validation_ok)
    distinct_support=len({s['event_key'] for s in support})
    implicit=bool(distinct_support>=2 and any(s['kind'] in ('event','business','process') for s in support) and any(s['kind'] in ('gap','process') for s in support))
    # A technical score or an email channel is not a business deficit, even if a model says so.
    gaps=[s for s in support if s['kind']=='gap']
    processes=[s for s in support if s['kind']=='process']
    technical_only=bool(gaps) and all(re.search(r'lighthouse|pagespeed|lento|lentezza|design|css|seo|font|14 px|traduzion',s['quote'],re.I) and not re.search(r'impossibil|non (?:consente|permette|gestisce|supporta)|ordini persi|errori (?:di|negli)',s['quote'],re.I) for s in gaps)
    manual_only=bool(processes) and not gaps and all(not re.search(r'errori|duplicazion|incompatibil|non (?:consente|permette|gestisce)|ricopi|molteplici|configurazion.{0,40}dipenden',s['quote'],re.I) for s in processes)
    if technical_only or manual_only:implicit=False
    from .commercial_inference import verified_inference
    inference=verified_inference(identity,signals,proposal,validation,documents)
    if inference:implicit=True
    scope=proposal.get('scope')=='full_project' and validation_ok and not all(SMALL.search(s['quote']) for s in support or [{'quote':'piccole modifiche'}])
    risks=[s['quote'] for s in signals if s['kind']=='risk' or RISK.search(s['quote'])]
    critical=[v for v in proposal.get('critical_unknowns',[]) if not re.fullmatch(r'(?:budget(?: del progetto)?|tempi? (?:di )?consegna|modalità di pagamento|prezzo|costo)',v.strip(),re.I)]
    complexity=proposal.get('feasibility')=='bounded' and not critical and not risks
    counter_resolved=validation_ok and validation.get('existing_solution_checked') is True and validation.get('small_fix_sufficient') is False
    contradictions=bykind['counterevidence']
    # Existing is not synonymous with adequate: an active website cannot by
    # itself veto a documented need for a different portal or a full rebuild.
    # The independent review must still assess adequacy and smaller alternatives.
    if any(CLOSED_REQUEST.search(s['quote']) for s in contradictions):counter_resolved=False
    budget=None;budget_evidence=None
    # Only a budget explicitly attached to this project. Never salary, turnover or the agency's client's budget.
    if proposal.get('budget_signal_id'):
        b=next((s for s in official if s['id']==proposal['budget_signal_id'] and s['kind']=='budget'),None)
        if b and re.search(r'budget|importo (?:del progetto|a base)|corrispettivo',b['quote'],re.I) and not re.search(r'fatturato|\bRAL\b|stipendio|cliente finale|del nostro cliente|finanziamento|contributo|agevolazione',b['quote'],re.I):
            match=re.search(r'(\d[\d.,]*(?:\s*(?:k|mila))?)\s*(?:€|euro|EUR)|(?:€|EUR)\s*(\d[\d.,]*(?:\s*(?:k|mila))?)',b['quote'],re.I)
            if match:
                amount=match[1] or match[2]
                multiplier=1000 if re.search(r'k|mila',amount,re.I) else 1
                amount=re.sub(r'\s*(?:k|mila)\s*','',amount,flags=re.I)
                range_match=re.search(r'(?:tra|da|fra)\s*(?:€\s*)?(\d[\d.,]*)\s*(?:e|a|[-–])\s*(?:€\s*)?\d',b['quote'],re.I)
                if range_match:amount=range_match[1];multiplier=1
                if ',' in amount:amount=amount.replace('.','').replace(',','.')
                elif '.' in amount and (amount.count('.')>1 or len(amount.rsplit('.',1)[1])==3):amount=amount.replace('.','')
                try:budget=float(amount)*multiplier;budget_evidence=b['id']
                except ValueError:pass
    minimum=MINIMUMS.get(project);economic_ok=budget is None or minimum is None or budget>=minimum
    primary_docs=[d for d in documents if d.get('official') and d.get('status',200)==200]
    checked_sections=set(proposal.get('checked_sections',[]))
    investigation=bool({'identity','offer','contact','solutions'}<=checked_sections and len(primary_docs)>=2 and not limits and validation_ok)
    gates=[]
    def gate(key,label,ok,reason,refs=None):gates.append({'key':key,'label':label,'passed':bool(ok),'reason':reason,'evidence_ids':refs or []})
    gate('identity','Identità verificata',identity.get('identity_status')=='verified','Identità e dominio collegati a dati ufficiali, non al nome nel motore.')
    gate('geography','Area geografica',identity.get('region') in ALLOWED_REGIONS,'Sede aziendale in un’area ammessa; località sconosciuta non supera il controllo.')
    gate('target','Target compatibile',not excluded,excluded or 'Nessuna esclusione identificata.')
    gate('timing','Attualità',signal_current,'Evento documentato entro 180 giorni oppure processo/lacuna attuale osservabile.',[s['id'] for s in signal_current])
    gate('need','Bisogno concreto',concrete and (explicit or implicit),'Richiesta pertinente o collegamento motivato fra almeno due riscontri distinti.',[s['id'] for s in support])
    gate('scope','Progetto completo',scope and digital_fit,'Il perimetro richiede un progetto completo; una piccola modifica non basta.')
    gate('economics','Compatibilità economica',economic_ok,'Budget non dichiarato: nessuna capacità di spesa attribuita.' if budget is None else 'Budget dichiarato confrontato con la soglia interna.',[budget_evidence] if budget_evidence else [])
    gate('counterevidence','Soluzioni e controprove',counter_resolved,'Controllati strumenti già disponibili, soluzioni esterne e alternative minori.')
    gate('feasibility','Fattibilità',complexity,'Perimetro delimitato, nessuna incognita tecnica critica irrisolta.')
    gate('contact','Canale aziendale',identity.get('contacts'),'Contatto pubblico attribuito all’azienda; non equivale a consenso.')
    gate('validation','Verifica approfondita',investigation,'Identità, offerta, contatto e soluzioni controllati; nessun controllo necessario incompleto.')
    weights=[('Qualità delle prove',20 if official and validation_ok else 0),('Concretezza del bisogno',25 if concrete and (explicit or implicit) else 0),('Tempestività',10 if signal_current else 0),('Progetto completo',15 if scope else 0),('Compatibilità economica documentata',10 if budget is not None and economic_ok else 0),('Fattibilità tecnica',10 if complexity else 0),('Accessibilità del contatto',5 if identity.get('contacts') else 0),('Riscontri indipendenti',5 if distinct_support>=2 else 0)]
    detail={name:{'points':points,'evidence_ids':[s['id'] for s in support],'reason':{'Qualità delle prove':'Citazioni controllate nelle fonti originali e revisione critica completata.','Concretezza del bisogno':'Richiesta completa o due riscontri complementari collegati a un bisogno specifico.','Tempestività':'Evento datato entro 180 giorni o processo attuale osservato.','Progetto completo':'L’ambito e le alternative minori sono stati verificati.','Compatibilità economica documentata':'Budget della commessa dichiarato e sopra la soglia interna.','Fattibilità tecnica':'Ambito delimitato, senza incognite critiche aperte.','Accessibilità del contatto':'Canale aziendale trovato in una pagina ufficiale.','Riscontri indipendenti':'Almeno due fatti distinti; ripubblicazioni escluse.'}[name] if points else ('Budget non dichiarato: zero punti.' if name=='Compatibilità economica documentata' and budget is None else 'Elemento non documentato o controllo non superato.')} for name,points in weights}
    competition=[s for s in signals if re.search(r'(?:gara|bando).{0,50}(?:apert|pubblic)|confronto (?:tra|fra) (?:più|diversi) fornitori',s['quote'],re.I)]
    penalty=5 if competition else 0
    if penalty:detail['Concorrenza documentata']={'points':-penalty,'evidence_ids':[s['id'] for s in competition],'reason':'Concorrenza elevata documentata, senza stima del numero di concorrenti.'}
    score=max(0,min(100,sum(v['points'] for v in detail.values())))
    missing=[g['label']+': '+g['reason'] for g in gates if not g['passed']]+list(limits)+proposal.get('critical_unknowns',[])
    hard_reject=bool(excluded or not economic_ok or (signals and all(SMALL.search(s['quote']) for s in signals)) or validation.get('status')=='contradicted')
    passed=all(g['passed'] for g in gates) and score>=70
    status='qualified' if passed else 'rejected' if hard_reject else 'unverifiable' if identity.get('identity_status')!='verified' or limits else 'needs_review'
    # Empty extraction alone is not a completed commercial evaluation. Only an
    # explicit no-project outcome after correlation and sufficient site coverage
    # closes this investigation; it says nothing about needs not observable here.
    no_project=bool(project=='none' and validation.get('outcome')=='no_documented_project'
                    and validation.get('status')=='insufficient' and not limits
                    and identity.get('identity_status')=='verified'
                    and {'identity','offer','contact','solutions'}<=checked_sections
                    and len({d['url'] for d in primary_docs})>=2)
    if no_project and not hard_reject:
        status='rejected'
        missing=['Nelle fonti esaminate non emerge una ragione documentata per proporre un progetto digitale completo.']
    next_action=('Verificare con il referente priorità, perimetro e budget.' if passed else
                 'Passare ad altre aziende; rivalutare questa solo con nuovi elementi commerciali significativi.' if no_project and not hard_reject else
                 'Completare i controlli mancanti prima di proporre un progetto.')
    return {'version':4,'need_inference':inference,'status':status,'score':score,'score_detail':detail,'gates':gates,'project':project,'minimum_offer':minimum,'budget':budget,'budget_evidence_id':budget_evidence,'confidence':'alta' if passed and distinct_support>=3 else 'media' if passed else 'insufficiente','why':proposal.get('why') or 'Nessun progetto completo documentato dalle fonti raccolte.','why_now':proposal.get('why_now') or 'Tempestività non dimostrata.','proposal':proposal.get('proposal') if digital_fit else 'Nessun progetto digitale completo giustificato dalle prove disponibili.','next_action':next_action,'objections':proposal.get('objections',[]),'missing':missing,'reasons':missing if not passed else ['Requisiti obbligatori superati e priorità almeno 70/100.'],'signals':signals,'document_ids':[d['id'] for d in documents],'strategy':strategy,'validated_at':now(),'validation':validation,'analysis_status':'completed' if validation.get('status') in ('supported','insufficient','contradicted') and not limits else 'incomplete'}
