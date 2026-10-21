"""Deterministic organization type, independent of identity and buying intent."""
import re
from .extract import parse_page, nodes, types
from .db import domain

PUBLIC=re.compile(r'\b(?:azienda\s+(?:unità\s+)?(?:sanitaria|ospedaliera)|unità\s+(?:locale\s+)?socio[ -]?sanitaria|(?:a[. ]?u[. ]?l[. ]?s[. ]?s|ulss|asl|ausl)\s*\d+|comune\s+di|ministero\s+(?:di|della|del))\b',re.I)
DIRECTORY=re.compile(r'\b(?:directory\s+(?:aziendal|delle aziende)|elenco\s+(?:aziende|imprese)|portale\s+(?:delle aziende|di aziende)|cerca\s+aziende)\b',re.I)
PRIVATE=re.compile(r'\b(?:s\.?\s*r\.?\s*l\.?|s\.?\s*n\.?\s*c\.?|s\.?\s*a\.?\s*s\.?|società\s+cooperativa)\b',re.I)
STARTUP=re.compile(r'\bstart[ -]?up\s+innovativa\b',re.I)


def classify(pages,identity=None):
    identity=identity or {}
    def result(category,page,quote,reason,certainty='high'):
        return {'category':category,'certainty':certainty,'source':page['url'] if page else None,
                'evidence':([{'url':page['url'],'quote':quote[:500]}] if page else []),
                'reason':reason,'identity_verified':identity.get('identity_status')=='verified',
                'service_compatibility':'to_verify','commercial_opportunity':'not_established'}
    for page in pages:
        parsed=parse_page(page)
        names=[parsed['title'],str(parsed.get('name') or '')]
        for node in nodes(parsed['doc'].schemas):
            own=domain(str(node.get('url') or ''))==domain(page['url'])
            if own and types(node)&{'GovernmentOrganization'}:
                return result('public_body',page,str(node.get('name') or parsed['title']),'Organizzazione pubblica dichiarata nei dati del sito.')
        for name in names:
            match=PUBLIC.search(str(name or ''))
            if match:return result('public_body',page,match[0],'Denominazione istituzionale sanitaria o pubblica; non è una PMI privata.')
            match=DIRECTORY.search(str(name or ''))
            if match:return result('directory',page,match[0],'Il sito si presenta come elenco di imprese, non come committente.')
    from .source_roles import publisher_identity
    from .direct_channels import digital_supplier
    for page in pages:
        parsed=parse_page(page)
        if publisher_identity(page):return result('editorial_source',page,parsed['title'],'Identità editoriale o associativa riscontrata nel sito.')
        if digital_supplier(parsed):return result('digital_agency',page,parsed['title'],'Il sito presenta servizi digitali propri; domanda di collaborazione da verificare separatamente.')
    for page in pages:
        parsed=parse_page(page)
        # Only explicit self-description; an article about a startup is not identity.
        own_text=parsed['title']+' '+str(parsed.get('name') or '')
        if STARTUP.search(own_text) and identity.get('identity_status')=='verified':
            return result('startup',page,own_text,'Startup innovativa dichiarata nell’identità del sito.')
        match=PRIVATE.search(own_text)
        if match and identity.get('identity_status')=='verified':
            return result('private_company',page,own_text,'Forma societaria privata e identità verificate; bisogno commerciale non ancora dimostrato.')
    return result('unidentified',None,'','Categoria non dimostrata dalle fonti disponibili.','unknown')


def non_buyer(classification):
    return classification['category'] in ('public_body','directory','editorial_source')
