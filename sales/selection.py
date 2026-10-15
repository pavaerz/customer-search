"""Commercial relevance shared by discovery, combinations and saved results."""
import re

GROWTH_REJECTION = 'Cambio di sede, apertura o notizia aziendale senza un progetto web da realizzare dichiarato nella fonte.'

def digital_project(text):
    # Existing websites, footer links and completed launches are not unmet needs.
    for sentence in re.split(r'[.!?;\n]+', text):
        if re.search(r'\b(?:non (?:cerchiamo|vogliamo|intendiamo)|già (?:realizzato|online|lanciato)|abbiamo (?:lanciato|realizzato))\b', sentence, re.I):
            continue
        intent = re.search(r'\b(?:cerchiamo|stiamo cercando|abbiamo bisogno|vogliamo|intendiamo|stiamo (?:progettando|pianificando)|in programma|we (?:need|are looking|plan))\b', sentence, re.I)
        work = re.search(r'\b(?:realizz\w*|svilupp\w*|rifar\w*|rifacimento|rinnov\w*|crea\w*|aprire|avviare|lanciare|build\w*|redesign)\b', sentence, re.I)
        web = re.search(r'\b(?:sito (?:web|internet|aziendale)|e-?commerce|shop online|vendita online|portale|landing page|wordpress|woocommerce|website|online store)\b', sentence, re.I)
        if intent and work and web:
            return True
    return False

def useful_evidence(e):
    return (e['kind'] in ('request', 'signal', 'measurement')
            and not e.get('metadata', {}).get('selection_rejected')
            and not (e['engine'] == 'C' and e['kind'] == 'signal' and not digital_project(e['detail'])))

def commercially_qualified(engine, evidence):
    useful = [e for e in evidence if useful_evidence(e)]
    if engine == 'C':
        return any(e['engine'] == 'C' and e['kind'] == 'signal' for e in useful)
    if engine == 'E':
        return (any(e['kind'] in ('request', 'signal') for e in useful)
                and len({e['engine'] for e in useful}) >= 2
                and len({(e['url'], ' '.join(e['detail'].lower().split())) for e in useful}) >= 2)
    return True
