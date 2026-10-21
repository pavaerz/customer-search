"""Independent original-page signals, not mutually exclusive buyer labels.

A literal invitation can challenge a negative model interpretation. It cannot
establish ownership, freshness, budget or qualification by itself.
"""
import re
from sales.db import digest
from .passages import SCOPE
from .document_units import extract

ASK = re.compile(r'\b(?:cerchiamo|ricerchiamo|cercasi|cerco|siamo (?:sempre )?alla ricerca|collabora con noi|we (?:are )?(?:looking for|seeking)|looking for|seeking)\b', re.I)
EXTERNAL = re.compile(r'freelanc|collaborator|contractor|partita\s*iva|collabora con noi|partner tecnic', re.I)
NEGATIVE = re.compile(r'\b(?:non|no|not|senza)\b[^.!?\n]{0,55}(?:cerch|ricerch|freelanc|collaborator|contractor)|cercavamo|we were looking|posizione chiusa|applications closed', re.I)
SUPPLIER = re.compile(r'offriamo|nostri servizi|we (?:offer|build|provide)|servizi di|sviluppiamo', re.I)


def extract_signals(source):
    if not source.get('original'):
        return []
    text = source.get('text', '')
    ranges = source.get('allowed_ranges') or [[0, len(text)]]
    units = source.get('document_units') or extract(source)
    out = []
    for line in re.finditer(r'[^\n]+', text):
        start, end = line.span()
        allowed = next(((a,b) for a,b in ranges if a <= start and end <= b), None)
        if not allowed:
            continue
        unit = next((u for u in units if u['start'] <= start and end <= u['end']), None)
        limit = min(allowed[1], unit['end'] if unit else len(text))
        # Adjacent contract/requirements paragraph is context, never another ad.
        after = text[end:min(limit, end+400)]
        context = line[0] + after
        local_scope=SCOPE.search(line[0]) or (ASK.search(line[0]) and not SUPPLIER.search(after) and SCOPE.search(after))
        if not local_scope:continue
        kinds = []
        if SUPPLIER.search(line[0]):
            kinds.append('supplier_offer')
        if ASK.search(line[0]) and not NEGATIVE.search(context):
            kinds.append('collaboration_invitation' if EXTERNAL.search(context) else 'explicit_project_request')
        if re.search(r'\b(?:assumiamo|full.time employee|tempo indeterminato)\b', line[0], re.I) and not NEGATIVE.search(line[0]):
            kinds.append('employment_offer')
        for kind in kinds:
            out.append({'id': digest(source['url']+'|'+str(start)+'|'+kind), 'type': kind,
                'url': source['url'], 'start': start, 'end': end, 'quote': line[0],
                'context_end': end+len(after), 'context': context,
                'document_unit_id': unit['id'] if unit else None,
                'content_hash': digest(text), 'checked_at': source.get('checked_at'),
                'basis': 'literal_original_signal_not_qualification', 'original': True})
    return out


def contradictions(source, analysis, signals):
    if not analysis or analysis.get('kind') not in ('SUPPLIER_OFFER','EDITORIAL','EMPLOYEE_JOB','COMPLETED_PROJECT'):
        return []
    return [s for s in signals if s['type'] in ('collaboration_invitation','explicit_project_request')]
