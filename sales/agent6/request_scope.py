"""Direction of a cited invitation; never infer the client's purchasing intent."""
import re

INVITE=r'(?:cerchiamo|cerco|cerca|cercasi|ricerchiamo|looking for|seeking|we need)'
TECHNICAL_ROLE=re.compile(r'\b'+INVITE+r'\s+(?:(?:un[oa]?|uno|dei|nuovi|a|an|external|freelance)\s+){0,3}'
    r'(?:sviluppator\w*|programmator\w*|web\s+(?:designer|developer)|front.?end\s+developer|'
    r'WordPress\s+developer|partner\s+tecnic\w*)\b',re.I)
NONTECHNICAL=(
    ('commercial_sales',r'\b(?:soci[oa]|partner)\s+commercial\w*|\bagent[ei]\s+di\s+commercio\b|\bcommunity builder\w*'),
    ('franchise_store',r'\bfranchisee\w*|\baffiliat\w*\s+(?:commercial\w*|franchising)|\baprir\w*\b[^.!?\n]{0,90}\b(?:store|negozio|punto vendita)\b'),
    ('hospitality_partner',r'\bpartner\b[^.!?\n]{0,140}\b(?:accoglienza|ospitalità|strutture ricettive)\b'),
)

def nontechnical_request(quote):
    """Only the literal requested role, not a nearby service or another ad.

    A developer hired to work on a franchise/hotel/sales platform is still a
    technical request. Unspecified or regulated supplier roles stay unknown.
    """
    if not re.search(r'\b'+INVITE+r'\b',quote,re.I):return None
    if TECHNICAL_ROLE.search(quote):return None
    return next((reason for reason,pattern in NONTECHNICAL if re.search(pattern,quote,re.I)),None)

def query_direction(text):
    """Reject demonstrated ambiguity before spending a search request.

    Branch input contains only positive terms. Technology used by a shop is
    not the role of its partner, and a quote form belongs to a supplier.
    """
    buyer=bool(re.search(r'\b(?:cerch\w*|cerc\w*|ricerch\w*|looking for|seek\w*)\b',text,re.I))
    if re.search(r'\b(?:richiesta(?: di)?|richiedi|richiedere)\s+(?:un\s+)?preventivo\b',text,re.I) and not buyer:
        return {'allowed':False,'reason':'supplier_quote_form_not_buyer_request',
                'correction':'Search a buyer explicitly looking for a developer or supplier; a request-a-quote form is a supplier offer.'}
    if re.search(r'\bpartner\b',text,re.I) and not re.search(r'svilupp|programmator|developer|frontend|front.end|web design|partner\s+(?:tecnic|tecnolog)|technical\s+partner|freelanc|contractor',text,re.I):
        return {'allowed':False,'reason':'partner_role_not_technically_scoped',
                'correction':'Specify an external technical role or development activity; WordPress/ecommerce alone also match franchising and sales partners.'}
    return None
