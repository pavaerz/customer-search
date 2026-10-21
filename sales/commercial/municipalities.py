"""Official, offline municipality lookup for a selected geographic quotation.

Not a gazetteer scan over arbitrary prose. Full municipality names only, with
bounded address/dateline suffixes; unknown/ambiguous names remain unknown.
It establishes the place's region, never whose location it is.
"""
from functools import lru_cache
from pathlib import Path
import json
import re
import unicodedata


def normalized(value):
    return ' '.join(unicodedata.normalize('NFC',value).replace('’',"'").casefold().split())


@lru_cache(maxsize=1)
def registry():
    data=json.loads(Path(__file__).with_name('istat_municipalities.json').read_text())
    names={}
    for code,name,province,region in data['municipalities']:
        names.setdefault(normalized(name),[]).append((code,name,province,region))
    return names,data['version']


def resolve_quotation(text):
    value=' '.join(str(text or '').split()).strip()
    # No surrounding narration, client location, service territory or company
    # name is stripped to manufacture an address. Keep exact-name matching.
    match=re.fullmatch(r"(?P<name>[\wÀ-ÿ .’'\-]+?)(?:\s*\((?P<province>[A-Z]{2})\))?"
        r"(?:\s*,\s*(?P<suffix>.*))?",value)
    if not match:return None
    suffix=match['suffix'] or ''
    if suffix and not re.fullmatch(r'(?:Italia|Italy|IT|\d{1,2}\s+)?\s*'
            r'(?:(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+20\d{2})?',suffix,re.I):
        return None
    names,version=registry()
    candidates=names.get(normalized(match['name']),[])
    if match['province']:candidates=[r for r in candidates if r[2]==match['province']]
    if len(candidates)!=1:return None
    code,name,province,region=candidates[0]
    return {'region':region,'city':name,'province':province,'istat_code':code,
            'basis':'EXACT_MUNICIPALITY_QUOTATION','dataset':version}


def resolve_address_quotation(text):
    """Resolve one explicit street-number-and-town clause in a selected fact.

    Never scan unrelated article prose for arbitrary town names. This proves
    the municipality's region, not whose address it is or eligibility to work.
    Multiple different addresses remain ambiguous.
    """
    pattern = (r'\b(?:via|viale|piazza|corso|strada)\s+[^.!?;\n]{1,100}?\s+'
               r'\d{1,4}(?:[/\-]\w+)?\s*,\s*'
               r'(?:angolo\s+(?:via|viale|piazza)\s+[^,;\n.!?]{1,70},\s*)?'
               r'(?:a|in)\s+(?P<town>[\wÀ-ÿ ’\'\-]{2,80})(?=[,.;:\n!?]|$)')
    matches = list(re.finditer(pattern, str(text or ''), re.I))
    if not matches:
        return None
    resolved = [resolve_quotation(m['town']) for m in matches]
    if any(r is None for r in resolved) or len({r['istat_code'] for r in resolved}) != 1:
        return None
    return {**resolved[0], 'basis':'EXPLICIT_STREET_MUNICIPALITY_CLAUSE',
            'literal_address':matches[0][0], 'literal_municipality':matches[0]['town']}
