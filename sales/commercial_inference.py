"""A documented business change can conflict with a declared channel condition.

Neither fact is a buying request or a defect. The relationship is an inference,
reviewed separately and kept out of the quoted evidence. Missing website content,
an email address, poor design and a catalogue alone cannot establish it.
"""
from datetime import datetime, timezone
import re

CHANNEL=re.compile(r'\bsito\b|portale|catalogo|negozio online|e.?commerce|vendit[ae]|acquist\w*|ordin[ei]|spedizion\w*',re.I)
BOUNDARY=re.compile(r'riservat\w*|esclusivamente|soltanto|unicamente|\bsolo\b|obbligator\w*|limitat\w*',re.I)
AUDIENCE=re.compile(r'rivenditor\w*|distributor\w*|operator[ei]|professionist\w*|privat[io]|consumator\w*|partita\s*iva|codice cliente|utenti registrati',re.I)
CHANGE=re.compile(r'nuov[oaie]\s+(?:marchio|brand|divisione|line[ae]|servizi\w*|mercat\w*|canal\w*)|lanci\w*|apri\w*.{0,40}(?:privati|consumatori|mercato)|espansion\w*|rete\s+(?:di\s+)?distributor\w*',re.I)
RELATIONS=('incompatible_audience','incompatible_channel','incompatible_offer')


def declared_condition(text):
    # A boundary must concern the commercial channel within the same sentence.
    # Do not borrow "solo" from an unrelated slogan in a long excerpt.
    for part in re.split(r'[.!?\n]',text):
        if not (CHANNEL.search(part) and BOUNDARY.search(part) and AUDIENCE.search(part)):continue
        # Email/Excel alone and language choices cannot justify a full project,
        # even if an otherwise well-formed model review claims that they do.
        if re.search(r'email|e-mail|excel|telefono|italiano|inglese|tedesco|francese',part,re.I):continue
        if re.search(r'recesso|restituzion|reso\b|rimbors',part,re.I):continue
        return True
    return False


def current(signal,event=False):
    try:
        if event:
            age=(datetime.now(timezone.utc).date()-datetime.fromisoformat(signal['published_at'][:10]).date()).days
            return 0<=age<=180
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(signal['checked_at'])).total_seconds()
        return 0<=age<=7*86400
    except (KeyError,TypeError,ValueError):return False


def candidates(signals):
    events=[s for s in signals if s['kind']=='event' and CHANGE.search(s['quote']) and current(s,event=True)]
    conditions=[s for s in signals if s['kind']=='condition' and s.get('official') and declared_condition(s['quote']) and current(s)]
    return events,conditions


def review_schema(events,conditions):
    fields={
        'event_id':{'type':'string','enum':['']+[s['id'] for s in events]},
        'condition_id':{'type':'string','enum':['']+[s['id'] for s in conditions]},
        'relationship':{'type':'string','enum':['not_established',*RELATIONS]},
        'reason':{'type':'string','maxLength':700},
        'full_project_reason':{'type':'string','maxLength':700},
        'small_fix_reason':{'type':'string','maxLength':700},
    }
    return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}


REVIEW_TASK=' Valuta anche inference: collega un evento recente a una condizione commerciale o di accesso realmente dichiarata nelle fonti. Una condizione non è un difetto. relationship=not_established se il pubblico, canale o offerta dell’evento è già servito, se basta un cambio di impostazioni, una pagina o traduzione, se manca la prova del collegamento o se la condizione appartiene a un altro strumento. Cita event_id e condition_id presenti anche nei support_ids della proposta e revisione. Spiega il nesso in reason, perché occorre un progetto completo in full_project_reason e perché interventi minori non bastano in small_fix_reason. Non inventare conversioni, vendite perse, volontà di acquisto o impossibilità tecniche. Una semplice procedura via email non dimostra inefficienza. Per relationship non dimostrata usa ID e motivazioni vuoti.'


def verified_inference(identity,signals,proposal,review,documents):
    """Check provenance and independent review; never promote by this check alone."""
    relation=review.get('inference')
    if not isinstance(relation,dict) or relation.get('relationship') not in RELATIONS:return None
    if review.get('status')!='supported' or review.get('existing_solution_checked') is not True or review.get('small_fix_sufficient') is not False:return None
    for field in ('reason','full_project_reason','small_fix_reason'):
        if not isinstance(relation.get(field),str) or len(relation[field].strip())<35:return None
    events,conditions=candidates(signals)
    event=next((s for s in events if s['id']==relation.get('event_id')),None)
    condition=next((s for s in conditions if s['id']==relation.get('condition_id')),None)
    if not event or not condition or event['id']==condition['id'] or event['event_key']==condition['event_key']:return None
    refs={event['id'],condition['id']}
    if not refs<=set(proposal.get('support_ids',[])) or not refs<=set(review.get('support_ids',[])):return None
    from .research_rules import normalize
    docs={d['id']:d for d in documents}
    for signal in (event,condition):
        doc=docs.get(signal['document_id'])
        if not doc or doc.get('status',200)!=200 or normalize(signal['quote']) not in normalize(doc.get('text','')):return None
        # Original company sources or explicitly scoped editorial evidence only.
        if not doc.get('official'):
            tokens=lambda value:set(re.findall(r'\w{2,}',normalize(value)))-{'srl','spa','società','azienda'}
            expected=tokens(identity.get('name',''))
            if not expected or tokens(doc.get('scoped_to_subject'))!=expected:return None
    if not docs[condition['document_id']].get('official'):return None
    return {'type':'inference','label':'Ipotesi commerciale verificata sulle fonti, non richiesta di acquisto',
            'evidence_ids':sorted(refs),**relation}
