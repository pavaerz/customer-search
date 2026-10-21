"""Owner identity isolated from customers, projects and credits; no network."""
import re
from html import escape
from html.parser import HTMLParser
from sales.db import domain
from sales.extract import parse_page, Document
from sales.research_analysis import identity_from
from sales.research_evidence import owned_organizations
from .indexed_jobs import same_company_name

THIRD_PARTY=re.compile(r'portfolio|testimoni|case[-_ ]?stud|client[ei]|customers?|partners?|credits|powered.by',re.I)
LEGAL_NAME=re.compile(r"^\s*([\wÀ-ÿ &’'.-]{2,90}?\s+(?:S\.?\s*r\.?\s*l\.?|S\.?\s*p\.?\s*a\.?|S\.?\s*n\.?\s*c\.?))(?=\s*(?:$|[|,·]|[-–]\s|p\.?\s*iva|partita iva))",re.I)
VAT=re.compile(r'\b(?:partita\s*iva|p\.?\s*i\.?\s*v\.?\s*a\.?(?:/C\.F\.)?|vat(?:\s*id)?)\s*[:.-]?\s*(?:IT\s*)?(\d{11})\b',re.I)

def address_name(value):return bool(re.match(r'^(?:loc\.|località|via |viale |piazza |sede |\d{5}\b)',str(value or ''),re.I))
def seo_name(value):
    text=str(value or '')
    services=re.findall(r'\b(?:realizzazione|creazione|progettazione|posizionamento|sviluppo)\s+(?:siti|web|internet|grafica|software)\b',text,re.I)
    return bool(re.search(r'\b(?:finestre|infissi|serramenti|vendita|produzione|servizi)\b.{0,65}\b(?:a|in)\s+\w+.*(?:provincia|sassuolo|spilamberto)|\|',text,re.I) or
                (len(text)>60 and ',' in text and len(services)>=2))


def metadata_brand(name,text):
    """A SEO list isn't a name. A shorter brand needs its own owner statement.

    Never shorten an arbitrary headline or legal name. Require both the exact
    metadata prefix and a visible first-person owner statement on the same page.
    """
    if not seo_name(name) or ',' not in name:
        return None
    brand=name.split(',',1)[0].strip()
    if not 3<=len(brand)<=60 or not re.fullmatch(r"[\wÀ-ÿ &’'.-]+",brand):
        return None
    match=re.search(r'\b(?:noi di|we at)\s+('+re.escape(brand)+r')(?=[\s,.!?;:]|$)',text,re.I)
    return {'name':match[1],'quote':match[0]} if match else None

class OwnerHTML(HTMLParser):
    """Remove explicit third-party containers/headed sections, retaining footer."""
    void={'br','img','meta','link','input','hr','source','wbr','area','base','embed','param','col'}
    def __init__(self,html):
        super().__init__(convert_charrefs=True);self.stack=[];self.out=[]
        self.feed(html)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);marker=' '.join(str(a.get(k,'')) for k in ('id','class','aria-label'))
        skip=bool(self.stack and self.stack[-1][1]) or bool(THIRD_PARTY.search(marker))
        if not skip:self.out.append('<'+tag+''.join(' '+k+'="'+escape(v or '',quote=True)+'"' for k,v in attrs)+'>')
        if tag not in self.void:self.stack.append((tag,skip))
    def handle_endtag(self,tag):
        if not self.stack or not self.stack[-1][1]:self.out.append('</'+tag+'>')
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:self.stack=self.stack[:i];break
    def handle_data(self,text):
        if not self.stack or not self.stack[-1][1]:
            self.out.append(text if self.stack and self.stack[-1][0] in ('script','style') else escape(text))

def owner_html(html):
    # A heading scopes third-party names until the next peer heading or footer.
    pattern=r'<h([1-6])\b[^>]*>\s*(?:i nostri |nostri |our )?(?:clienti|portfolio|testimonianze|partners?|case studies)\s*</h\1>.*?(?=<h[1-6]\b|<footer\b|$)'
    cleaned=''.join(OwnerHTML(re.sub(pattern,'',html,flags=re.I|re.S)).out)
    return re.sub(r'(?:powered by|website by|sito (?:realizzato|sviluppato) da)\s*(?:<a\b[^>]*>.*?</a>|[^<\n]*)','',cleaned,flags=re.I|re.S)

def establish(pages):
    from .entity_scope import profile,unresolved
    if profile(pages[0])['multi_subject']:return unresolved(pages[0])
    pages=[p for p in pages if not profile(p)['multi_subject']]
    cleaned=[{**p,'html':owner_html(p['html'])} for p in pages]
    result=identity_from(cleaned);host=domain(pages[0]['url']);claims=[]
    original={k:result.get(k) for k in ('name','legal_id','location','identity_status')}
    for page in cleaned:
        parsed=parse_page(page)
        for org in owned_organizations(parsed,host):
            name=org.get('legalName') or org.get('name')
            if name:
                claims.append({'name':name,'legal_id':org.get('vatID') or org.get('taxID'),'url':page['url'],'method':'owned_Organization','quote':str(name)})
                brand=metadata_brand(name,parsed['text'])
                if brand:
                    claims.append({**brand,'legal_id':None,'url':page['url'],
                                   'method':'owned_metadata_and_visible_self_identification'})
        # Footer is an owner scope, but credits and client references are not.
        footers=re.findall(r'<footer\b[^>]*>(.*?)</footer\s*>',page['html'],re.I|re.S)
        text='\n'.join(Document(x).text for x in footers)
        if re.search(r'/contatt|/contact|/legal|/privacy',page['url'],re.I):text+='\n'+Document(page['html']).text
        lines=text.splitlines()
        for i,line in enumerate(lines):
            if THIRD_PARTY.search(line):continue
            line=re.sub(r'^\s*(?:©\s*)?(?:Copyright\s*)?(?:©\s*)?(?:20\d{2}\s*)?(?:©\s*)?[|·–-]?\s*','',line,flags=re.I)
            if address_name(line) or re.match(r'^(?:Codice Etico|Modello Organizzativo|Report sostenibilit)',line,re.I):continue
            m=LEGAL_NAME.search(line) or re.match(r'^\s*([\wÀ-ÿ &’\'.-]{2,100}?\s+[sS]\.?[aA]\.?[sS]\.?(?:\s+di\s+[\wÀ-ÿ .-]{2,60})?)\s*$',line)
            if not m:m=re.match(r"^\s*([\wÀ-ÿ &’'.-]{2,85}?\s+Soc\.?\s+Coop\.?)\s*$",line,re.I)
            if not m:continue
            near=' '.join(lines[i:i+24] if re.search(r'Soc\.?\s+Coop',m[1],re.I) else lines[i:i+6]);vat=VAT.search(near)
            if not vat and re.search(r'cookie|funzionale|durata|preferenza',near,re.I):continue
            claims.append({'name':m[1].strip(),'legal_id':'IT'+vat[1] if vat else None,'url':page['url'],'method':'legal_owner_scope','quote':near[:500]})
    claims=[c for c in claims if not address_name(c['name'])]
    from .geography import owner_locations
    locations=owner_locations(cleaned,result.get('name'))
    if locations and not result.get('location'):
        result['location']=locations[0]['text'];result['locations']=[r['text'] for r in locations]
    strong=[c for c in claims if (c['legal_id'] or c['method']=='legal_owner_scope') and not seo_name(c['name'])]
    conflicts=[]
    if strong:
        chosen=strong[0]
        for c in strong[1:]:
            if not same_company_name(chosen['name'],c['name']):conflicts.append(c)
            elif c['legal_id'] and chosen['legal_id'] and re.sub(r'\D','',str(c['legal_id']))!=re.sub(r'\D','',str(chosen['legal_id'])):conflicts.append(c)
        if not conflicts:
            result['name']=chosen['name']
            ids={re.sub(r'\D','',str(c['legal_id'])) for c in strong if c['legal_id']}
            result['legal_id']='IT'+next(iter(ids)) if len(ids)==1 else None
            if not result.get('location'):
                selected_locations=owner_locations(cleaned,result['name'])
                if selected_locations:result['location']=selected_locations[0]['text'];result['locations']=[r['text'] for r in selected_locations]
            own_email=any(c['type']=='email' and domain('https://'+c['value'].split('@')[-1])==host for c in result['contacts'])
            result['identity_status']='verified' if (result['legal_id'] and (result.get('location') or own_email)) or (result.get('location') and own_email) else 'unknown'
    elif result['identity_status']=='verified':
        # Generic names extracted from body cannot borrow another subject's VAT.
        key=lambda s:re.sub(r'[^a-z0-9]','',s.lower())
        name=key(re.sub(r'\s+s\.?[rpn]\.?[lca]\.?$','',result['name'],flags=re.I))
        corroborated=any(same_company_name(result['name'],c['name']) for c in claims) or (len(name)>=3 and name in key(host.split('.')[0]))
        if not corroborated:
            result.update(identity_status='unknown',legal_id=None)
    if conflicts:
        result.update(identity_status='uncertain',legal_id=None,basis='Dati del titolare discordanti: identità da verificare, nessuna unione di soggetti.')
    if not strong and (address_name(result['name']) or seo_name(result['name'])):
        candidates=[c['name'] for c in claims if not seo_name(c['name'])]
        for page in cleaned:
            p=parse_page(page);brand=p['doc'].meta.get('og:site_name')
            if brand and not seo_name(brand) and not address_name(brand) and re.sub(r'\W','',brand).casefold() in re.sub(r'\W','',host).casefold() and re.search(re.escape(brand),p['text'],re.I):candidates.append(brand)
        names=list(dict.fromkeys(candidates))
        if len(names)==1:result['name']=names[0]
        else:result.update(name=host,identity_status='unknown',legal_id=None)
    # Resolve the owner's address with the same location rules as qualification.
    # The older extractor misses bare province codes and can include the next
    # marketing line; bounded owner blocks preserve the actual address proof.
    from .geography import resolve_location,ITALY
    locations=owner_locations(cleaned,result['name'])
    address_evidence=[{'text':a,'resolution':resolve_location(a)} for a in result.get('locations',[])]
    address_evidence+=locations
    legal_addresses=[a for a in address_evidence if re.search(r'sede legale|registered office',a['text'],re.I)]
    selected=legal_addresses or address_evidence
    regions={a['resolution']['region'] for a in selected if a['resolution']['region']}
    conflict=any(a['resolution']['basis']=='CONFLICT' for a in selected)
    domestic=not result.get('country') or result['country'].casefold() in ITALY
    result['regions']=sorted(regions) if domestic else []
    result['region']=next(iter(regions)) if domestic and len(regions)==1 and not conflict else None
    result['location_evidence']=locations
    result['identity_original']=original
    result['name_fields']={'selected_name':result['name'],'legal_name':strong[0]['name'] if strong and not conflicts else None,'page_title':parse_page(pages[0])['title'],'original_name':original['name'],'normalization':'owner_evidence_not_title_or_address'}
    result['basis']=('Nome, dati societari/indirizzo e contatti coerenti nelle pagine ufficiali.' if result['identity_status']=='verified' else 'Dati del titolare discordanti: nessuna unione di soggetti.' if conflicts else 'Identità del titolare non sufficientemente corroborata; dati mancanti restano sconosciuti.')
    for claim in claims:claim.update(actor=claim['name'],role='SOURCE_OWNER',scope='owned_organization_or_legal_scope')
    result['identity_evidence']=claims
    result['identity_conflicts']=([strong[0],*conflicts] if conflicts else [])
    result['domain_verification']='verified' if result['identity_status']=='verified' else 'uncertain'
    return result
