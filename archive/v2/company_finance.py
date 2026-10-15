"""Conservative extraction of public, reported net income; never infer from turnover."""
import re
from datetime import datetime


def valid_vat(value):
    if not re.fullmatch(r'\d{11}', value) or len(set(value)) == 1:
        return False
    total = sum(int(value[i]) for i in range(0,10,2))
    total += sum((2*int(value[i]))//10+(2*int(value[i]))%10 for i in range(1,10,2))
    return (10-total%10)%10 == int(value[-1])


def extract_vat(text):
    matches = re.findall(r'(?:partita\s+iva|p\s*\.?\s*iva|p\s*\.\s*i\s*\.)\s*[:.\-]?\s*(?:IT\s*)?(\d{11})(?!\d)',text,re.I)
    values = {value for value in matches if valid_vat(value)}
    return next(iter(values)) if len(values)==1 else ''


def reported_profit(text, vat):
    if not valid_vat(vat) or extract_vat(text) != vat:
        return []
    # Only explicit, adjacent year and euro amount for net income. No snippets or inferred dates.
    pattern = r"\butile\s+(?:netto|d[’']?esercizio|di\s+esercizio)\s*(?:dell?[’']?\s*|del\s+|anno\s+|esercizio\s+)?(20\d{2})\s*[:=\-]?\s*(?:€|euro)\s*(-?\d{1,3}(?:\.\d{3})*(?:,\d{2})?|-?\d+(?:,\d{2})?)(?![\d.,%])"
    rows=[]
    for match in re.finditer(pattern,text,re.I):
        year=int(match[1])
        if year>datetime.now().year or year<2000:
            continue
        # Skip units and percentages that would require interpreting an abbreviated figure.
        if re.match(r'\s*(?:%|milion|miliard|mila|migliaia)',text[match.end():],re.I):
            continue
        amount=float(match[2].replace('.','').replace(',','.'))
        rows.append({'year':year,'amount_eur':amount,'evidence':match[0]})
    return rows
