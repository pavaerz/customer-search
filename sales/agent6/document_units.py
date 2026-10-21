"""Attributed units within one acquired document; no inferred company ownership.

Only explicit repeated listing boundaries are recognized. Unrecognized pages
retain an unknown scope rather than guessed card boundaries. Offsets refer to
the untouched original text so the same URL cannot conceal cross-listing facts.
"""
import re
from sales.db import digest

OWNER = re.compile(r'(?im)^\s*(?:Azienda|Company|Employer)\s*:\s*(\S[^\n]*)$')
END = re.compile(r'(?im)^\s*(?:Candidati|Apply now|Apply for this job)\s*$')
FIELDS = {'entity', 'request', 'technical', 'contract', 'geography', 'publication', 'budget', 'scope'}


def extract(source):
    text = source.get('text', '')
    owners = list(OWNER.finditer(text))
    ends = list(END.finditer(text))
    if len(owners) < 2 or len(ends) < 2:
        return []
    units = []
    for owner in owners:
        previous = next((m for m in reversed(ends) if m.end() <= owner.start()), None)
        following = next((m for m in ends if m.start() >= owner.end()), None)
        if following is None:
            continue
        start = previous.end() if previous else 0
        end = following.end()
        # Never declare a range attributable if it still contains two owners.
        if sum(start <= o.start() < end for o in owners) != 1:
            continue
        raw = text[start:end]
        prefix=text[start:owner.start()].strip().splitlines()
        title=prefix[0].strip() if previous and prefix and 3<=len(prefix[0].strip())<=180 else None
        date = re.search(r'\b\d{2}/\d{2}/20\d{2}\b', text[owner.end():end])
        tail = text[owner.end():end].strip().splitlines()
        units.append({'id': digest(source['url']+'|'+raw), 'url': source['url'],
            'start': start, 'end': end, 'text_hash': digest(raw), 'text': raw,
            'subject': owner[1].strip(), 'subject_span': [owner.start(1), owner.end(1)],
            'title': title, 'date_quote': date[0] if date else None,
            'location_quote': tail[1] if date and len(tail) > 2 else None,
            'request_type': 'UNKNOWN', 'basis': 'explicit_owner_and_application_boundaries',
            'identity_verified': False})
    return units if len(units) >= 2 else []


def attribute(source, facts):
    units = source.get('document_units') or extract(source)
    if not units:
        return facts, [], [], []
    tagged = []
    for fact in facts:
        f = dict(fact)
        if f.get('original') and f.get('url') == source['url']:
            match = next((u for u in units if u['start'] <= f.get('document_start', -1)
                          < f.get('document_end', -1) <= u['end']), None)
            f['document_unit_id'] = match['id'] if match else None
        tagged.append(f)
    requests = [f for f in tagged if f['field'] == 'request' and f.get('original')]
    request_units = {f.get('document_unit_id') for f in requests}
    if not requests:
        return tagged, [], [], units
    issues = []
    withheld = []
    if None in request_units or len(request_units) != 1:
        issues.append('request_unit_unresolved_or_multiple')
    selected = next(iter(request_units)) if len(request_units) == 1 and None not in request_units else None
    for f in tagged:
        if f['field'] in FIELDS and f.get('original') and f.get('url') == source['url']:
            if selected is None or f.get('document_unit_id') != selected:
                withheld.append({**f, 'reason': 'different_or_unresolved_document_unit'})
    if withheld:
        issues.append('cross_unit_attribution')
    return [f for f in tagged if not any(f == {k:v for k,v in w.items() if k != 'reason'} for w in withheld)], withheld, issues, units
