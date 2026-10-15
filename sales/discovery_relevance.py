"""Cheap routing before downloads. These decisions never qualify a company."""
import re
from urllib.parse import unquote, urlsplit
from .db import domain

LEGAL_SPA = re.compile(r'\bs\s*\.?\s*p\s*\.?\s*a\b\.?', re.I)
INSTITUTION = re.compile(r'^(?:MIMIT|MISE|MEF|INPS|INAIL|Ministero\b|Regione\b|Comune\b)', re.I)
ARCHIVE = re.compile(r'archive\.org/(?:stream|details)/|/islandora/|/datastream/|archiviostudiadriatici|\b(?:tesi di laurea|archivio storico|gazzetta del 19\d\d)\b', re.I)
UNRELATED_PDF = re.compile(r'parit[aà].{0,12}genere|politica.{0,20}uni.?pdr|processo.tributario|procedure.telematiche|scheda.contatti', re.I)
PLATFORMS={'whatsapp','whatsapp business','facebook','twitter','instagram','linkedin','telegram','youtube','pinterest','tiktok'}
PLATFORM_HOSTS=('whatsapp.com','whatsappbusiness.com','wa.me','facebook.com','fb.com','twitter.com','x.com','instagram.com','linkedin.com','t.me','telegram.me','telegram.org','youtube.com','youtu.be','pinterest.com','tiktok.com')


def utility_link(url, label=''):
    """Social/contact infrastructure is not the official domain of a prospect."""
    host=domain(url)
    return (any(host==h or host.endswith('.'+h) for h in PLATFORM_HOSTS)
            or bool(re.fullmatch(r'\s*(?:share|condividi|stampa|print|email|e-mail)(?:\s+(?:su|on)\s+\w+)?\s*',label,re.I)))


def subject_exclusion(name, documents=()):
    if name.strip().casefold() in PLATFORMS:return 'Piattaforma sociale o di messaggistica: non un’impresa cliente del segmento.'
    if LEGAL_SPA.search(name): return 'Soggetto dichiarato S.p.A.: escluso dal segmento commerciale.'
    if INSTITUTION.search(name): return 'Ente pubblico citato, non impresa committente.'
    pattern = re.escape(name)
    for doc in documents:
        body = doc.get('research_text', doc.get('text', ''))
        title = doc.get('title', '')
        if re.search(r'(?<!\w)'+pattern+r'\s+S\.?\s*p\.?\s*A\b',body,re.I):
            return 'Forma S.p.A. associata al soggetto nella fonte originale: fuori segmento.'
        for match in re.finditer(r'(?<!\w)' + pattern + r'(?!\w)', body, re.I):
            before = body[max(0, match.start()-100):match.start()]
            if re.search(r'(?:ministro|assessore|giornalista|autore)\s+(?:[\w’]+\s+){0,5}$', before, re.I):
                return 'Persona citata con ruolo istituzionale/editoriale, non azienda.'
        context = title if re.search(pattern, title, re.I) else ''
        context += '\n' + '\n'.join(line for line in body.splitlines() if re.search(pattern, line, re.I))
        if re.search(r'(?:gamma|modello|prodotto|linea di prodotti)\s+' + pattern + r'\b|' + pattern + r'\s*,\s*(?:la |una )?(?:nuova )?(?:gamma|linea|famiglia)\b', context, re.I):
            return 'Nome di una gamma/prodotto: identificare il produttore, non cercare il prodotto come impresa.'
        # Explicit size evidence near this named subject, never a guessed budget.
        if (re.search(r'(?:multinazionale|gruppo (?:mondiale|internazionale))\s+(?:\w+\s+){0,2}'+pattern+r'\b',context,re.I) or
            re.search(pattern+r'\s*,?\s*(?:è |una |uno |dei |delle |tra |i |le |realtà |industriali |più |radicate |nel |territorio |scaligero |e ){0,18}(?:multinazionale|principali gruppi (?:europei|mondiali))\b',context,re.I) or
            re.search(pattern+r'\s*(?::|investe|investirà|annuncia investimenti per)\s*\d+\s+miliardi\b',context,re.I)):
            return 'Fonte riferita a un grande gruppo; fuori dal segmento di piccole imprese.'
    return None


def preflight(item, payload):
    url = item.get('url', '')
    if payload.get('direct_channels'):
        from .direct_channels import route_exclusion,linkedin_notice
        reason=route_exclusion({**payload,**item})
        if reason:return reason
        if linkedin_notice(item):return None
    if utility_link(url):return 'Collegamento a una piattaforma sociale o di messaggistica, non dominio aziendale da investigare.'
    title = str(item.get('title', ''))
    snippet = str(item.get('content', item.get('search_snippet', '')))
    text = unquote(url) + ' ' + title + ' ' + snippet
    if ARCHIVE.search(text):
        return 'Archivio storico o biblioteca digitale: incompatibile con la ricerca commerciale corrente.'
    pdf = bool(re.search(r'\.pdf(?:$|[?#])|/datastream/[^/]+/content/', url, re.I))
    if pdf and UNRELATED_PDF.search(text):
        return 'PDF di policy, contatti o documentazione estranea al progetto: download evitato.'
    subject = payload.get('subject')
    if subject and not payload.get('company_host'):
        reason = subject_exclusion(subject, payload.get('source_documents', []))
        if reason: return reason
        if payload.get('official_link'): return None
        tokens = set(re.findall(r'\w{3,}', subject.casefold())) - {'srl', 'spa', 'società', 'azienda'}
        visible = set(re.findall(r'\w{3,}', (title + ' ' + snippet).casefold()))
        host = domain(url).replace('-', '')
        matches = sum(t in visible or t in host for t in tokens)
        # A missing snippet is unknown, not permission to invent a matching firm.
        if tokens and matches / len(tokens) < .75:
            return 'Risultato non riferibile al nome aziendale cercato; nessun download per omonimie o corrispondenze generiche.'
        if re.search(r'processo.tributario|giustizia.tributaria|normativa.ptt', text, re.I):
            return 'Omonimia con un servizio tributario, non l’impresa cercata.'
        if re.search(r'concessionari|/auto/|/veicoli/|/brand/|/rete-vendita|noleggio.a.lungo', text, re.I) and not all(t in host for t in tokens):
            return 'Rivenditore o pagina di una rete commerciale: non è il dominio del soggetto cercato.'
    return None


def visit_purpose(payload):
    if payload.get('investigation_question'):
        question = payload['investigation_question']
        return question if isinstance(question, str) else str(question.get('question') or question.get('purpose') or question.get('topic') or 'Verificare il fatto aziendale e le soluzioni già disponibili.')
    if payload.get('subject'):
        return 'Verificare identità e dominio ufficiale di ' + payload['subject'] + '; non presumere un bisogno digitale.'
    if payload.get('acquisition_reason'):return payload['acquisition_reason']
    hypothesis = payload.get('hypothesis') or {}
    return hypothesis.get('required_evidence') or 'Identificare un’impresa pertinente e verificare prove di un progetto digitale completo.'


def alternative_query(payload):
    subject=payload.get('subject')
    if not subject or payload.get('alternative_source') or not (payload.get('company_host') or payload.get('source_documents')):return None
    if subject_exclusion(subject,payload.get('source_documents',[])):return None
    result={k:v for k,v in payload.items() if k in ('subject','subject_quote','source_documents','hypothesis','root_query_key','region','filters','research_intent')}
    result.update(query='"'+subject.replace('"','')+'" azienda sito contatti -site:'+domain(payload['url']),
                  page=1,period='',company_stage='identify',alternative_source=payload['url'])
    return result
