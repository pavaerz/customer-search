"""Commercial target exclusions grounded in the company's own pages."""
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit
from .db import domain
from .extract import parse_page, nodes, types

SPA = re.compile(r'(?<!\w)(?:s\s*\.\s*p\s*\.\s*a\.?|societ[àa] per azioni)(?!\w)', re.I)
COMPACT_SPA = re.compile(r'(?<!\w)(?:SpA|SPA|S\.p\.a)(?!\w)')
LEGAL = re.compile(r'partita iva|p\.?\s*iva|p\.\s*iv?a|codice fiscale|capitale sociale|\bREA\b|registro imprese', re.I)
CREDIT = re.compile(r'powered by|website by|web design|design by|sviluppo\s|realizzato da|realizzazione sito|sviluppato da|sito (?:web )?(?:di|a cura di)|credits', re.I)

class VisibleText(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.parts=[]; self.skip=0
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','noscript'): self.skip+=1
        if tag in ('p','div','section','footer','li','br'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style','noscript'): self.skip=max(0,self.skip-1)
        if tag in ('p','div','section','footer','li'): self.parts.append('\n')
    def handle_data(self, text):
        if not self.skip:self.parts.append(text)
    @property
    def lines(self):return [' '.join(x.split()) for x in ''.join(self.parts).splitlines() if x.strip()]

def exclusion(page, parsed=None):
    """Return a sourced reason, never infer legal form or company size from design."""
    parsed=parsed or parse_page(page)
    host=domain(page['url']); brand=parsed.get('name') or host.split('.')[0]
    identities=[brand]; legal_names=set()
    for node in nodes(parsed['doc'].schemas):
        if types(node)&{'Organization','Corporation','LocalBusiness','ProfessionalService'} and domain(str(node.get('url') or node.get('@id') or ''))==host:
            identities.extend(str(node[k]) for k in ('legalName','name') if node.get(k))
            if node.get('legalName'):legal_names.add(str(node['legalName']))
    if parsed.get('job'):
        employer=parsed['job'].get('hiringOrganization') or {}
        if isinstance(employer,dict):identities.extend(str(employer[k]) for k in ('legalName','name') if employer.get(k))
    reason=None;code=None
    for identity in identities:
        if SPA.search(identity) or (COMPACT_SPA.search(identity) and (identity in legal_names or re.search(r'(?<!\w)SpA(?!\w)',identity))):
            # Bare SPA in a hotel/beauty brand is not evidence of its legal form.
            if not SPA.search(identity) and re.search(r'wellness|hotel|beauty|benessere|resort',identity,re.I):continue
            reason='S.p.A. esclusa dal target: '+identity;code='legal_spa';break
    visible=VisibleText(page['html']).lines
    # Require a company identity near the legal suffix; ignore customers and web credits.
    aliases=[re.sub(r'[^a-z0-9]','',v.lower()) for v in identities]
    aliases.append(re.sub(r'[^a-z0-9]','',host.split('.')[0].lower()))
    aliases=[a for a in aliases if len(a)>=3]
    # A marketing suffix can differ from the legal name (SIPA Solutions vs
    # SIPA S.p.A.). Require the literal base at the end of the company name,
    # corroborated by its domain and an own-company/legal page. Never match
    # an arbitrary substring such as SIPA inside SIPARIO.
    bases=[]
    for name in identities:
        base=re.sub(r'\s+(?:solutions|industries|group|italia|italy)$','',name,flags=re.I).strip()
        key=re.sub(r'[^a-z0-9]','',base.lower())
        if base!=name and len(key)>=4 and host.split('.')[0].startswith(key):bases.append(base)
    domain_brand=host.split('.')[0]
    domain_base=re.sub(r'(?:solutions|industries|group|italia|italy)$','',domain_brand,flags=re.I)
    if domain_base!=domain_brand and len(domain_base)>=4:bases.append(domain_base)
    if not reason:
        for n,line in enumerate(visible):
            if CREDIT.search(line) or re.search(r'client[ei]|partner|fornitor|referenze',line,re.I):continue
            match=SPA.search(line) or COMPACT_SPA.search(line)
            if not match and LEGAL.search(' '.join(visible[max(0,n-1):n+3])):
                match=re.search(r'(?<!\w)spa(?!\w)',line,re.I)
            if not match:continue
            if not SPA.search(line) and not re.search(r'(?<!\w)SpA(?!\w)',line) and not LEGAL.search(' '.join(visible[max(0,n-1):n+3])):continue
            prefix=re.sub(r'[^a-z0-9]','',line[max(0,match.start()-90):match.start()].lower())
            own_page=bool(re.search(r'/(?:[^/]+/)?(?:chi-siamo|azienda|about(?:-us)?|company|privacy|legal|contatti|contact(?:-us)?)(?:/|$)',urlsplit(page['url']).path,re.I))
            base_match=bool((own_page or LEGAL.search(' '.join(visible[max(0,n-1):n+3]))) and any(re.search(r'(?<!\w)'+re.escape(base)+r'\s*$',line[:match.start()],re.I) for base in bases))
            if any(a in prefix for a in aliases) or base_match:
                reason='S.p.A. esclusa dal target: '+line[:240];code='legal_spa';break
    if not reason:
        # These thresholds are selection rules, not a legal SME classification.
        for line in parsed['text'].splitlines():
            if re.search(r'nostr[ioe]*\s+client[ei]|client[ei]\s+(?:con|che)|per le aziende|aiutiamo|i nostri progetti|case stud',line,re.I):continue
            own=bool(re.search(r'\b(?:siamo|nostr[oaie]|abbiamo|contiamo|operiamo|disponiamo)\b',line,re.I) or brand.lower() in line.lower())
            if not own:continue
            quantities=[(int(m.group(1)),m.group(2).lower()) for m in re.finditer(r'\b(\d[\d.]*)\s+(sedi|filiali|punti vendita|negozi|showroom|dipendenti|collaboratori)\b',line.replace('.', ''),re.I)]
            if any(n >= (250 if kind in ('dipendenti','collaboratori') else 10) for n,kind in quantities) or re.search(r'\b(?:siamo (?:una? )?multinazionale|siamo (?:un )?gruppo (?:internazionale|multinazionale)|societ[àa] quotata)\b',line,re.I):
                reason='Gruppo o rete strutturata fuori target: '+line[:300];code='large_company';break
    return {'code':code,'reason':reason,'url':page['url'],'checked_at':page['checked_at']} if reason else None
