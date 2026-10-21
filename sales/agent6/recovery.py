"""Recover investigation, never qualification, from a literal public invitation."""
import re
from . import schema, qualification

INVITATION = re.compile(
    r'\b(?:cerchiamo|ricerchiamo|cercasi|cerco|we (?:are )?(?:looking for|seeking)|'
    r'looking for|seeking)\b[^.!?\n]{0,160}\b(?:freelanc\w*|contractors?|'
    r'collaborator\w* estern\w*|partita\s*iva)\b|'
    r'\b(?:collabora con noi|diventa (?:nostro )?partner|join our freelance)\b', re.I)
SCOPE = re.compile(r'wordpress|woocommerce|frontend|front.end|web\s*(?:design|develop|app)|'
                   r'sit[oi]\s*(?:web|internet)|e.?commerce|sviluppator\w*', re.I)
COUNTER = re.compile(r'coworking|postazioni|spazio (?:ufficio|lavoro)|'
                     r'non (?:saranno|sono|verranno) (?:presi|pres[eo]) in considerazione[^.!?\n]{0,80}freelanc|'
                     r'non (?:cerchiamo|accettiamo)[^.!?\n]{0,80}freelanc|'
                     r'no freelancers|not (?:a )?freelance|no contractors|'
                     r'applications closed|posizione chiusa|no longer accepting|'
                     r'we were looking|cercavamo|case stud|portfolio', re.I)


def literal_invitation(source, flow):
    """A local matching sentence warrants one original read, not an AI fact.

    An agency mentioning collaborators, a tutorial, a negation, an old case
    study or a coworking invitation must not take this recovery path.
    """
    text = source.get('text', '')
    if COUNTER.search(text): return None
    match = INVITATION.search(text)
    if not match: return None
    # Keep attribution local; a keyword in a distant footer is insufficient.
    start = max(0, text.rfind('\n', 0, match.start()) + 1)
    end = min(len(text), match.end() + 240)
    if not SCOPE.search(text[max(start, match.start()-100):end]): return None
    e = schema.bundle([{'id': 'recovery', **source}], max(4500, len(text.encode())))
    block = next((item for item in e if match[0] in item['text']), None)
    if not block: return None
    a = block['text'].index(match[0])
    # Cite the bounded sentence/context, not model-generated text.
    b = min(len(block['text']), a + len(match[0]) + 240)
    ref = {'id': block['id'], 'start': a, 'end': b}
    output = {'analyses': [{'result_id': 'recovery',
        'kind': 'AGENCY_PARTNERSHIP' if flow=='AGENCIES' else 'BUYER_DEMAND',
        'kind_ref': ref, 'facts': [{'field': 'request', 'ref': ref}],
        'hypothesis': 'Invito letterale indicizzato: verificare originale, soggetto, ambito e attualità.',
        'missing': ['entity','technical','contract','geography','publication','contact']}]}
    valid = schema.validate(output, {'task':schema.SCREEN, 'result_ids':['recovery'], 'evidence':e})
    body = qualification.evaluate(source, valid['analyses'][0], e, flow)
    body.update(state='DISCOVERED', evidence_level='SNIPPET_ONLY',
                recovery_basis='literal_invitation_not_commercial_verification',
                reason='Invito freelance nello snippet: lettura originale necessaria.')
    return body
