"""Deterministic, scoped commercial intent. No identity or contract inference.

A discovery snippet is an index hint; only an independently extracted block can
supply request evidence. Page type is derived from structure and wording, never
from a list of the regression domains.
"""
import re
from urllib.parse import unquote, urlsplit

REQUEST = re.compile(r'\b(?:cerchiamo|cerco|cercasi|ricercasi|ricerchiamo|selezioniamo|siamo alla ricerca|stiamo (?:anche )?cercando|looking for|we are seeking|we are hiring|sta assumendo|hiring|profili ricercati|figure sempre ricercate|ruoli ricercati)\b', re.I)
INVITATION = re.compile(r'\b(?:accettiamo|valutiamo|siamo aperti|collaboriamo|collaborazioni continuative|entra nel nostro network|candidati come partner|diventa partner)\b', re.I)
PEOPLE = r'(?:sviluppator\w*|programmator\w*|developer\w*|designer\w*|professionist\w*|collaborator\w*|consulent\w*|freelanc\w*|partner\w*|profil\w*|figur\w*|esperto\w*|esperta\w*|web\s+developer|front[ -]?end|back[ -]?end|CTO|co[ -]?founder)'
THIRD_PERSON = re.compile(r'\b(?:ricerca|seleziona|cerca)\s+(?:(?:un[oa]?|uno|nuovi?|nuove|dei|delle|di|un\')\s*){0,3}'+PEOPLE, re.I)
CUSTOMER = re.compile(r'\b(?:se (?:sei|stai)|sei)\s+(?:alla ricerca|cercando)|\b(?:vuoi|desideri)\s+(?:un sito|realizzare|creare|spendere)|\b(?:chiamaci|contattaci|richiedi un preventivo)\b', re.I)
SELLER = re.compile(r'\b(?:offro|offriamo|offre|offrono|realizziamo|vendiamo|progettiamo|forniamo)\b|\b(?:nostri|nostre)\s+(?:sviluppatori|professionisti|servizi)\b|\b(?:sviluppatori|professionisti)\b.{0,70}\bdisponibili\b|realizzazione siti|creazione siti|servizi di sviluppo', re.I)


# These predicates describe direction, not an isolated keyword. Offsets are in
# the supplied block; context.py attaches original document coordinates.
NEGATED = re.compile(r"\b(?:non|no)\s+(?:cerchiamo|cerco|accettiamo|collaboriamo|valutiamo)\b[^.!?;\n]*?(?=\b(?:ma|però|invece)\b|[.!?;\n]|$)", re.I)
BUYER_NEGATION = re.compile(r"fornitor|freelanc|collaborator|candidatur|partner|professionist|sviluppator", re.I)
SELLER_DIRECTION = re.compile(r"\b(?:offriamo|forniamo|proponiamo)\s+(?:i nostri |nostri |un |dei )?(?:servizi|sviluppatori|professionisti)|\b(?:affidaci|affidateci)\b|diventa (?:nostro |il nostro )?cliente|siamo (?:il|un|il tuo|il vostro) (?:partner|reparto) tecnico|(?:il|tuo|vostro) partner tecnico.{0,70}(?:serve|progetto)|perch[eé] scegliere.{0,90}partner tecnico", re.I)
GENERIC_PARTNER = re.compile(r"^(?:diventa partner|candidati come partner|entra nel nostro network)(?:[.!]?|\s+[|–—].*)$", re.I)


def clauses(text):
    for match in re.finditer(r"[^.!?;\n]+(?:[.!?;]|(?=\n|$))", text):
        value=match.group().strip()
        if value:yield {'quote':value,'start':match.start()+len(match.group())-len(match.group().lstrip()),'end':match.end()}


def request_nature(text):
    """Language of a claim, not proof it is currently open."""
    if re.search(r'\b(?:abbiamo collaborato|collaboravamo|in passato|we worked with)\b', text, re.I):return 'PAST_COLLABORATION'
    if re.search(r'\b(?:in futuro|potremmo|vorremmo|future interest)\b', text, re.I):return 'FUTURE_INTEREST'
    if re.search(r'\b(?:collaboriamo|collaboriamo anche|lavoriamo)\b.{0,100}(?:professionisti esterni|sviluppatori|freelance)|quando (?:selezioniamo|abbiamo bisogno)', text, re.I) and not re.search(r'\b(?:cerchiamo|ricerchiamo|accettiamo|candidati|invia\w* candidatura)\b',text,re.I):return 'GENERAL_COLLABORATION_POLICY'
    return 'UNKNOWN'


def request_clause(text):
    """A positive directed clause, with local rather than page-wide negation."""
    candidates=[]
    for item in clauses(text):
        sentence=item['quote']
        # Contrastive clauses are considered independently. A negative employee
        # clause must not erase a subsequent positive freelance invitation.
        for part in re.split(r'\b(?:ma|però|invece)\b',sentence,flags=re.I):
            if re.search(r'\b(?:diventa|diventiamo|diventata|diventato|divenuta|divenuto|becomes|became)\s+(?:un |una |official |certified )?partner\b|partnership (?:con|with)|partner (?:certificat[oa]|ufficiale)',part,re.I) and not REQUEST.search(part) and not re.match(r'^diventa\s+(?:un\s+)?partner\b',part.strip(),re.I):continue
            if request_nature(part) in ('PAST_COLLABORATION','FUTURE_INTEREST','GENERAL_COLLABORATION_POLICY'):continue
            if '?' in part or NEGATED.search(part) or GENERIC_PARTNER.fullmatch(part.strip()):continue
            if re.search(r'\b(?:offro|cerco lavoro|cerchiamo clienti|cerchiamo di|cerco di|cerca i fornitori|cerchiamo founder|come cercare|seleziona la categoria|scegli la categoria)\b',part,re.I):continue
            if re.search(r'\b(?:se (?:sei|stai)|sei)\s+(?:alla ricerca|cercando)',part,re.I):continue
            if SELLER_DIRECTION.search(part):continue
            if REQUEST.search(part) or THIRD_PERSON.search(part) or INVITATION.search(part):candidates.append(part.strip())
            if NEGATED.search(sentence) and re.search(r'per altri progetti\s+s[iì]',part,re.I):return part.strip()
    from .relevance import WEB_ROLE
    return next((c for c in candidates if WEB_ROLE.search(c)),candidates[0] if candidates else None)


def source_intent(url='', title='', text=''):
    """Classify evident listings/articles using URL + title/intro context."""
    path=unquote(urlsplit(url).path).lower();intro=title+' '+text[:2200]
    if re.search(r'/members/?$',path):return 'DIRECTORY'
    if re.search(r'/annunci-[^/]+/vendita/offerte-lavoro/?$',path):return 'AGGREGATOR'
    if re.search(r'\bcome finanziare (?:lo sviluppo|il tuo|un software)|come-finanziare-lo-sviluppo',title+' '+path,re.I):return 'EDITORIAL'
    if re.search(r'^(?:come|how to)\s+(?:trovare|scegliere|selezionare|assumere|find|hire|choose)\b',title.strip(),re.I) or re.search(r'/(?:come|how-to)-(?:trovare|scegliere|selezionare|assumere|find|hire|choose)-',path,re.I):return 'EDITORIAL'
    professional=r'(?:sviluppator\w*|web designer|professionist\w*|agenzi\w*|freelanc\w*)'
    ranking=bool(re.search(r'\b(?:\d+|i|le)\s+(?:migliori\s+)?'+professional, title, re.I))
    if (re.search(r'^/(?:dir|directory)/',path) and re.search(professional,intro,re.I)) or (re.search(r'^/c/[^/]+/[^/]+/',path) and ranking):return 'DIRECTORY'
    if re.search(r'\b(?:directory di|elenco di|selezione di)\s+(?:professionist|agenzi|sviluppator)|\b(?:trova|scegli|confronta)\s+(?:i\s+|un\s+)?'+professional,intro,re.I):return 'DIRECTORY'
    if ranking and re.search(r'vicino a te|ci sono \d+|preventivi|profili',intro,re.I):return 'DIRECTORY'
    if re.search(r'(?:le|i|\d+)\s+migliori\s+(?:agenzie|web agency|sviluppatori)|classifica delle agenzie',title+' '+path.replace('-',' '),re.I):return 'EDITORIAL'
    if re.search(r'pubblic(?:a|are)\s+(?:il|un|il tuo)\s+progett|inserisci\s+(?:il|un)\s+progetto',intro,re.I) and re.search(r'professionist|sviluppator|freelance',intro,re.I):return 'AGGREGATOR'
    if re.search(r'\b(?:tutti gli annunci|elenco (?:offerte|annunci)|ultime offerte di lavoro|annunci di terzi)\b',intro,re.I):return 'AGGREGATOR'
    return None


def classify_block(text, *, role=None, url='', title='', source_kind=None):
    from .context import TECH, EXTERNAL, EMPLOYEE
    listing=source_intent(url,title,text)
    clause=request_clause(text)
    from .relevance import technical_request
    technical=technical_request(text,role)
    negatives=[]
    for match in NEGATED.finditer(text):
        quote=match.group().strip()
        target='spontaneous_application' if re.search(r'candidature spontanee',quote,re.I) else 'external' if BUYER_NEGATION.search(quote) else 'employee' if re.search(r'dipendent|assunzion',quote,re.I) else 'unknown'
        negatives.append({'quote':quote,'start':match.start(),'end':match.start()+len(quote),'target':target})

    seller=[item for item in clauses(text) if SELLER_DIRECTION.search(item['quote'])]
    result={'intent':'UNKNOWN','commercial_role':'UNKNOWN','reason':'Intenzione commerciale non sufficientemente attribuibile.',
            'request_clause':clause,'role':role,'technical':technical,'buyer_evidence':[],
            'negations':negatives,'contradictions':[],'seller_evidence':seller,
            'request_nature':request_nature(text),'subject_relation':'unknown','relationship':None,'requester':None,'provider':None,'work_recipient':None,'payer':None}
    if listing:
        result.update(intent=listing,commercial_role=listing,request_nature='EDITORIAL_INFORMATION' if listing=='EDITORIAL' else 'UNKNOWN',reason='Struttura di elenco, piattaforma o articolo; editore distinto dal committente.');return result
    # A partner invitation addressed to customers is not procurement. Demand
    # needs a technical recipient or a bounded role, not technical sales copy.
    directed=bool(clause and not GENERIC_PARTNER.fullmatch(clause) and (
        TECH.search(clause) or role or re.search(r'per altri progetti\s+s[iì]',clause,re.I) or re.search(r'professionist|collaborator|figure.*ricercate|profili ricercati',clause,re.I)))
    if clause and re.search(r'copywriter|commerciale|marketing manager|addett\w* alle vendite',clause,re.I) and not TECH.search(clause):directed=False
    if directed and technical:
        positive=re.sub(NEGATED,'',text)
        employee=bool(EMPLOYEE.search(positive));external=bool(EXTERNAL.search(positive))
        partner=bool(re.search(r'partner\s+tecnic',clause,re.I))
        commercial_role='PARTNERSHIP_BUYER' if partner else 'FREELANCE_BUYER' if external and not employee else 'EMPLOYER' if employee and not external else 'BUYER'
        subject='publisher' if re.search(r'cerchiamo|ricerchiamo|selezioniamo|siamo alla ricerca|accettiamo|valutiamo|collaboriamo|siamo aperti|nostr|figure sempre ricercate|profili ricercati|ruoli ricercati',clause,re.I) else 'named_or_unknown'
        buyer=[item for item in clauses(text) if clause in item['quote']]
        named=re.match(r'^([A-ZÀ-Ý][\wÀ-ÿ &.\'-]{1,70}?)\s+(?:cerca|ricerca|seleziona)\b',clause)
        result['requested_subject']=named[1].strip() if named and not re.match(r'^(?:Siamo|Questo|La nostra|Il nostro)\b',named[1],re.I) else None
        named_claims=[(m[1].strip(),item['quote']) for item in clauses(text) if (m:=re.match(r'^([A-ZÀ-Ý][\wÀ-ÿ &.\'-]{1,70}?)\s+(?:cerca|ricerca|seleziona)\b',item['quote']))]
        candidate_addressing=[q for name,q in named_claims if re.match(r'^(?:Sei|Se sei|Ti occupi|Se ti|Tu|Voi)\b',name,re.I)]
        named_claims=[(name,q) for name,q in named_claims if not re.match(r'^(?:Siamo|Questo|La nostra|Il nostro|Sei|Se sei|Ti occupi|Se ti|Tu|Voi)\b',name,re.I)]
        result['actor_relation']='CANDIDATE_ADDRESSING' if candidate_addressing else 'INSUFFICIENT_EVIDENCE'
        result['candidate_addressing']=candidate_addressing
        subjects={name.casefold() for name,_ in named_claims}
        if result.get('requested_subject') and re.search(r'^(?:Attualmente|Siamo|Sono|Sei|Se sei|Ti occupi|Se ti|Tu|Voi|Il team|Il progetto|Per |In |La ricerca)',result['requested_subject'],re.I):result['requested_subject']=None
        if len(subjects)>1 or (named_claims and subject=='publisher'):
            result['actor_relation']='MULTIPLE_VALID_ACTORS'
            result['contradictions'].append({'relation':'MULTIPLE_VALID_ACTORS','code':'multiple_request_subjects','subjects':sorted(subjects),'quotes':[q for _,q in named_claims]})
        result.update(intent='FREELANCE_OPPORTUNITY' if external and not employee else 'JOB_OFFER' if employee and not external else 'BUYER_INTENT',
                      commercial_role=commercial_role,request_nature='CURRENT_OPEN_REQUEST',buyer_evidence=buyer,subject_relation=subject,
                      relationship='external' if external and not employee else 'employment' if employee and not external else None,
                      requester='publisher' if subject=='publisher' else None,work_recipient='external_professional' if external else None,
                      reason='Richiesta tecnica diretta nel blocco; soggetto, contratto e attualità richiedono verifica separata.')
        for neg in negatives:
            if neg['target']=='external':result['contradictions'].append({'relation':'REAL_CONTRADICTION','code':'external_request_negated','negative':neg['quote'],'positive':clause})
        if employee and external:result['contradictions'].append({'relation':'REAL_CONTRADICTION','code':'conflicting_contracts','positive':clause})
        # An invitation to sell *our* technical services and a purported buyer
        # role in the same unsplit block is unsafe, rather than a positive vote.
        if seller and re.search(r'partner',clause,re.I):result['contradictions'].append({'code':'partnership_direction_conflict','positive':clause,'negative':seller[0]['quote']})
        return result
    if seller or SELLER.search(text) or (technical and CUSTOMER.search(text)):
        partnership=bool(re.search(r'partner|reparto tecnico',text,re.I))
        result.update(intent='SELLER_INTENT',commercial_role='PARTNERSHIP_SELLER' if partnership else 'SELLER',request_nature='SERVICE_OFFER',provider='publisher',work_recipient='publisher',
                      reason='Il soggetto offre sviluppo a clienti/partner; non dimostra di affidare lavoro a un professionista.')
    elif any(n['target']=='external' for n in negatives):
        result['reason']='La fonte nega la disponibilità a incaricare collaboratori esterni.'
    return result
