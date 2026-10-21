"""Italy-only opportunity geography, distinct from legal and operating locations."""
import re
from sales.extract import parse_page,nodes,types
from sales.research_evidence import owned_organizations,address_text
from sales.research_rules import REGION_CODES,region_of
from sales.db import domain
REGIONS=('Veneto','Lombardia','Piemonte','Emilia-Romagna','Liguria','Friuli-Venezia Giulia','Trentino-Alto Adige','Valle d’Aosta','Toscana','Lazio','Marche','Umbria','Abruzzo','Molise','Campania','Puglia','Basilicata','Calabria','Sicilia','Sardegna')
EXTRA={'AN':'Marche','PU':'Marche','MC':'Marche','FM':'Marche','AP':'Marche','PG':'Umbria','TR':'Umbria','AQ':'Abruzzo','PE':'Abruzzo','CH':'Abruzzo','TE':'Abruzzo','CB':'Molise','IS':'Molise','NA':'Campania','SA':'Campania','CE':'Campania','AV':'Campania','BN':'Campania','BA':'Puglia','BT':'Puglia','BR':'Puglia','FG':'Puglia','LE':'Puglia','TA':'Puglia','PZ':'Basilicata','MT':'Basilicata','CZ':'Calabria','CS':'Calabria','KR':'Calabria','RC':'Calabria','VV':'Calabria','PA':'Sicilia','CT':'Sicilia','AG':'Sicilia','CL':'Sicilia','EN':'Sicilia','ME':'Sicilia','RG':'Sicilia','SR':'Sicilia','TP':'Sicilia','CA':'Sardegna','NU':'Sardegna','OR':'Sardegna','SS':'Sardegna','SU':'Sardegna'}
CITIES={'Napoli':'Campania','Bari':'Puglia','Palermo':'Sicilia','Catania':'Sicilia','Cagliari':'Sardegna','Perugia':'Umbria','Ancona':'Marche','Pescara':'Abruzzo','Potenza':'Basilicata','Campobasso':'Molise','Catanzaro':'Calabria'}
ITALY={'it','ita','italia','italy'}
def resolve_location(text):
    import json
    from pathlib import Path
    data=json.loads(Path(__file__).with_name('italy_locations.json').read_text())
    raw=str(text or '');value=raw
    # Service markets and unrelated street names never establish an office.
    if re.search(r'serviamo|operiamo in tutta|clienti (?:in|a)|service area',value,re.I):
        return {'region':None,'city':None,'basis':'SERVICE_AREA','dataset':data['version']}
    # A region word inside a complete municipality is not a second address:
    # e.g. "33080 Fiume Veneto (PN)" belongs to Friuli-Venezia Giulia.
    # Resolve only postal address components, then retain all other locations
    # for conflict detection. Never scan arbitrary narration for town names.
    from .municipalities import resolve_quotation
    towns=[];mismatch=False
    def municipal_component(match):
        nonlocal mismatch
        place=resolve_quotation(match['town']+' ('+match['province']+')')
        if place:
            towns.append(place)
            return ' '
        if resolve_quotation(match['town']):mismatch=True
        return match[0]
    value=re.sub(r'\b\d{5}\s+(?P<town>[\wÀ-ÿ .’\'\-]{2,80}?)\s*\((?P<province>[A-Z]{2})\)',
                 municipal_component,value)
    postal=re.search(r'\b\d{5}\b',value)
    if postal:
        # Keep city/region preceding a trailing CAP; remove the street component.
        prefix=re.sub(r'\b(?:via|viale|piazza|corso|vicolo)\s+[^,;\n]*(?:[,;]|$)',' ',value[:postal.start()],flags=re.I)
        value=prefix+' '+value[postal.end():]
    else:
        # A civic number terminates the street even without a comma or CAP.
        # Preserve the following municipality/province; never use a city name
        # occurring inside the street itself (e.g. "Via Roma 12 (PD)").
        street=r'\b(?:via|viale|piazza|corso|vicolo)\s+[^,;\n]*?\s+\d+[A-Za-z]?(?:/[A-Za-z0-9]+)?(?=\s|[,;]|$)'
        value,count=re.subn(street,' ',value,flags=re.I)
        if not count:value=re.sub(r'\b(?:via|viale|piazza|corso|vicolo)\s+[^,;\n]*(?:[,;]|$)',' ',value,flags=re.I)
    matches=[(city,r) for city,r in data['cities'].items() if re.search(r'(?<!\w)'+re.escape(city)+r'(?!\w)',value,re.I)]
    matches.extend((p['city'],p['region']) for p in towns)
    matches=list(dict.fromkeys(matches))
    regions={r for _,r in matches}
    # Match province codes as delimited uppercase address components, not IT.
    codes=[v for v in re.findall(r'(?<!\w)[A-Z]{2}(?=\s*(?:[),.;]|$))',value) if v in data['provinces']]
    regions.update(data['provinces'][v] for v in codes)
    for name in REGIONS:
        if re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',value,re.I) and not re.search(re.escape(name)+r'\s+(?:Group|S\.?r\.?l|Holding)',value,re.I):regions.add(name)
    post=data['postcodes'].get(postal[0]) if postal else None
    if not regions and post:regions.add(post['region'])
    return {'region':next(iter(regions)) if len(regions)==1 and not mismatch else None,'city':matches[0][0] if len(matches)==1 else post['city'] if post and not matches else None,
            'basis':'CONFLICT' if len(regions)>1 or mismatch else 'ADDRESS_COMPONENTS' if regions else 'UNKNOWN','dataset':data['version']}

def region(text):return resolve_location(text)['region']

def owner_locations(pages,actor):
    """Attributed contact/address blocks; neither search geography nor markets."""
    from .identity import owner_html
    from sales.extract import Document
    result=[]
    for page in pages:
        from .entity_scope import profile
        if profile(page)['multi_subject']:continue
        html=owner_html(page['html']);text=Document(html).text
        scopes=re.findall(r'<footer\b[^>]*>(.*?)</footer\s*>',html,re.I|re.S)
        if re.search(r'/contatt|/contact|/chi-siamo|/azienda|/about',page['url'],re.I):scopes.append(html)
        # Some themes have a div-based footer. A bounded legal owner block
        # is acceptable only when the same actor is named in that block.
        for m in re.finditer(re.escape(str(actor or '')),text,re.I):
            if actor:scopes.append(text[m.start():m.end()+260])
        for scope in scopes:
            lines=Document(scope).text.splitlines() if '<' in scope else scope.splitlines()
            for n,line in enumerate(lines):
                if not (re.search(r'\b\d{5}\b',line) or re.search(r'\b(?:via|viale|piazza|loc\.|sede leg\.)',line,re.I)):continue
                quote=' '.join(lines[max(0,n-1):n+2])
                if re.search(r'client[ei]|progetto per|serviamo|area servita',quote,re.I):continue
                resolved=resolve_location(quote)
                if resolved['region']:
                    result.append({'text':quote,'region':resolved['region'],'url':page['url'],'actor':actor,'kind':'company','country':None,'location_role':'REGISTERED_OFFICE' if re.search(r'sede leg',quote,re.I) else 'OPERATING_OFFICE','resolution':resolved,'basis':'owner_contact_block'})
        for m in re.finditer(r'\b(?:siamo a|le nostre sedi (?:sono|si trovano) a|la nostra sede (?:è|si trova) a)\s+([^.!?\n]{3,180})',text,re.I):
            quote=m[0];resolved=resolve_location(m[1])
            if resolved['region']:result.append({'text':quote,'region':resolved['region'],'url':page['url'],'actor':actor,'kind':'company','country':None,'location_role':'OPERATING_OFFICE','resolution':resolved,'basis':'explicit_owner_location'})
    return list({(r['url'],r['text']):r for r in result}.values())

def locate(pages,identity,request_text=''):
    locations=[];countries=set();remote=False
    def add(address,url,kind,country_override=None):
        text=address_text(address) if isinstance(address,dict) else str(address or '')
        country=(address.get('addressCountry') if isinstance(address,dict) else None) or country_override
        if isinstance(country,dict):country=country.get('name')
        if country:countries.add(str(country).casefold())
        r=(region(address.get('addressRegion')) if isinstance(address,dict) else None) or region(text)
        if text:locations.append({'text':text,'region':r,'kind':kind,'url':url,'country':country,'actor':identity.get('name'),'location_role':'PROJECT_LOCATION' if kind=='opportunity' else 'REGISTERED_OFFICE' if re.search(r'sede legale|registered office',text,re.I) else 'OPERATING_OFFICE','resolution':resolve_location(text)})
    for page in pages:
        from .entity_scope import profile
        if profile(page)['multi_subject']:continue
        pp=parse_page(page)
        for org in owned_organizations(pp,domain(page['url'])):add(org.get('address'),page['url'],'company')
        job=pp.get('job') or {}
        for node in nodes(job.get('jobLocation',[])):
            if 'Place' in types(node):add(node.get('address'),page['url'],'opportunity')
        if str(job.get('jobLocationType','')).upper()=='TELECOMMUTE':
            remote=any(str(n.get('name','')).casefold() in ITALY for n in nodes(job.get('applicantLocationRequirements',[])))
    for loc in identity.get('locations',[]) or [identity.get('location')]:
        if loc:add(loc,identity.get('website'),'company',identity.get('country'))
    if identity.get('country'):countries.add(identity['country'].casefold())
    from .opportunity_view import PUBLISHERS
    if domain(identity.get('website') or '') not in PUBLISHERS:
        locations+=owner_locations([p for p in pages if domain(p['url'])==domain(identity.get('website') or '')],identity.get('name'))
    remote=remote or bool(re.search(r'(?:remoto|remote|smart working).{0,65}(?:residenti in Italia|dall.Italia|in Italia|Italy)|(?:Italia|Italy).{0,40}(?:remoto|remote)',request_text,re.I))
    from .job_activity import geo_value,GEO_NO
    # Only original request text (never query geography) establishes eligibility.
    if re.search(r'\bremote\b|remoto',request_text,re.I):
        remote=geo_value(request_text)[0]=='GEO_COMPATIBLE'
    if GEO_NO.search(request_text):remote=False
    opportunity_locations=[x for x in locations if x['kind']=='opportunity']
    considered=opportunity_locations or locations
    domestic=[x for x in considered if (x['region'] and not x['country']) or str(x['country']).casefold() in ITALY]
    foreign=bool(countries and not countries&ITALY and not domestic)
    if opportunity_locations:foreign=bool(any(x['country'] and str(x['country']).casefold() not in ITALY for x in opportunity_locations) and not domestic)
    regions=list(dict.fromkeys(x['region'] for x in domestic if x['region']))
    return {'eligible':bool(domestic or remote) and not bool(GEO_NO.search(request_text)),'regions':regions,'locations':locations,'remote_italy':remote,
            'country':'Italia' if domestic or remote else 'Estero' if foreign else None,
            'reason':'Sede o opportunità italiana documentata.' if domestic or remote else 'Italia non verificata; remoto generico non sufficiente.'}
