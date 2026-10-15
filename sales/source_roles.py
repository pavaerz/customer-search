"""Publisher identity comes from the publisher, not incidental municipal addresses."""
import re
from .db import domain
from .extract import parse_page,nodes,types

EDITORIAL_IDENTITY=re.compile(r'\b(?:quotidiano|giornale|redazione|newsmedia)\b',re.I)
INSTITUTION_IDENTITY=re.compile(r'^(?:sito (?:ufficiale )?(?:del|della) |home\s*[-|:]\s*)?(?:comune di|regione\b|ministero\b|provincia di|camera di commercio|confindustria|confartigianato|confcommercio|assolombarda|unioncamere|unione industriali|cna\b)',re.I)


def publisher_identity(page):
    from .prospect_scope import EDITORIAL
    from .research_analysis import text_with_legal
    host=domain(page['url']);parsed=parse_page(page)
    if any(host==h or host.endswith('.'+h) for h in EDITORIAL):return True
    schema=list(nodes(parsed['doc'].schemas))
    if any(types(n)&{'NewsMediaOrganization','GovernmentOrganization'} for n in schema):return True
    # Some local newspapers declare an ordinary Organization but explicitly
    # describe their own WebSite as a territorial news service. Do not borrow
    # this description from an article about somebody else's publication.
    for node in schema:
        if 'WebSite' not in types(node) or domain(str(node.get('url') or ''))!=host:continue
        label=' '.join(str(node.get(k) or '') for k in ('name','alternateName'))
        if re.search(r'\btutte le notizie (?:di|da|su)\b|\bnotizie e cronaca\b',label,re.I):return True
    names=[str(parsed.get('name') or ''),parsed['title']]
    if any(EDITORIAL_IDENTITY.search(name) or INSTITUTION_IDENTITY.search(name.strip()) for name in names):return True
    raw=text_with_legal(page['html'])
    # Legal editorial declarations establish identity; mere membership/address does not.
    return bool(re.search(r'testata giornalistica|direttore responsabile|(?:testata|giornale|quotidiano|periodico).{0,100}(?:registrat[ao]|iscritt[ao]).{0,90}tribunale',raw,re.I))
