"""Commercial triage, not buying intent. Pure functions over acquired evidence."""
import re
from urllib.parse import urlsplit
from sales.db import domain

# Known source roles supplement structural evidence, never identify customers.
SOURCE_ROLES={
 'ufficiocamerale.it':'company_information_portal','bancomail.it':'database_provider',
 'furnishingidea.it':'sector_portal','archiproducts.com':'directory',
 'marche-manufacturing.it':'cluster','aziende.it':'directory','edilnet.it':'directory',
 'registroaziende.it':'directory','jobrapido.com':'aggregator','paginegialle.it':'directory','paginebianche.it':'directory',
}
EXCLUDED={'excluded_legal_form','multi_company_catalog','company_information_portal','database_provider','sector_portal','directory','cluster','institution','editorial','marketplace','web_agency','large_group','training_provider'}
OFFER=re.compile(r'\b(?:produciamo|produzione|prodott\w*|catalog\w*|lavorazioni|serramenti|carpenteria|CNC|packaging|impiant\w*|macchinari|servizi (?:tecnici|industriali)|su misura|manufactur\w*)\b',re.I)
MIGRATION=re.compile(r'(?:benvenuti nella nostra nuova casa digitale|(?:siamo|sono|abbiamo).{0,60}(?:trasferit|migrat).{0,100}(?:piattaforma|sito)|(?:lanciato|online|pubblicato).{0,35}(?:il nostro |il )?nuovo sito)',re.I|re.S)
# Atomic number token: never match the tail of a grouped or truncated number.
SIZE=re.compile(r'(?<![\w.,])(?P<n>\d{1,3}(?:[.,]\d{3})+|[1-9]\d{1,5})(?P<plus>\+)?(?:\s*[-–]\s*(?P<upper>\d{2,6}))?\s*(?:dipendenti|lavoratori|employees|addetti)\b',re.I)
GROUP=re.compile(r'leader mondiale|multinazionale|\bglobal (?:industrial |luxury )?group\b',re.I)


def group_evidence(text,actor=None):
    """An owner's self-description, not the size of a supplier or investor."""
    from .entity_scope import owner_fact
    out=[]
    # Preserve nearby attribution across HTML line breaks. A group keyword in
    # an isolated line is insufficient; require a named owner or first person.
    for m in GROUP.finditer(text):
        starts=[text.rfind(sep,0,m.start()) for sep in ('. ','\n\n')]
        start=max([0]+[n+2 for n in starts if n>=0])
        local=text[max(start,m.start()-240):min(len(text),m.end()+120)]
        if re.search(r'\b(?:rivenditor\w*|distributor\w*|partner|fornitor\w*|client\w*|investitor\w*|customer|supplier|investor|brand rappresentat\w*)\b',local,re.I):continue
        if not owner_fact(local,actor):continue
        named=bool(actor and re.search(re.escape(actor)+r'\s+(?:è|e[’\x27]|is|—|–|:)\s',local,re.I))
        if named or re.search(r'\b(?:siamo|we are|la nostra azienda è|our company is)\b',local,re.I):
            out.append({'kind':'owner_group_self_description','actor':actor,'quote':local.strip(),'scope':'owner'})
    return out


def excluded_legal_form(name):
    # Commercial preference: explicit S.p.A., not a wellness spa or a client mention.
    return bool(re.search(r'\bS\.\s*p\.\s*A\.?\b',str(name or ''),re.I) or re.search(r'\sSPA\s*$',str(name or '')))

def source_role(url,title='',text=''):
    host=domain(url);intro=title+' '+text[:16000];path=urlsplit(url).path
    if re.match(r'^\s*(?:corso|corsi|catalogo corsi)\b',title,re.I):return 'training_provider'
    if host=='cna.it' or host.endswith('.cna.it') or re.match(r'^\s*(?:Federazione\s|Confederazione\s|Associazione (?:industriali|artigiani|imprese))',title,re.I):return 'institution'
    from .entity_scope import MULTI,publication_role
    publication=publication_role(title,text)
    if publication:return publication
    if MULTI.search(title+' '+path):return 'multi_company_catalog'
    if re.search(r'corso.{0,60}sicurezza|sicurezza.{0,60}corso',title+' '+path,re.I):return 'editorial'
    for known,role in SOURCE_ROLES.items():
        if host==known or host.endswith('.'+known):return role
    patterns=(('database_provider',r'(?:vendita|acquist\w*|fornitura|database|liste).{0,70}(?:indirizzi email|email aziendali|database aziendali)|indirizzi-email-'),
      ('training_provider',r'ente (?:di |per la )?formazione|ente che opera nel campo della formazione|forniamo percorsi di formazione professionale|siamo un centro (?:di )?formazione|corsi, seminari, webinar|catalogo corsi|iscrizione al corso|obiettivi (?:del corso|formativi)'),
      ('company_information_portal',r'visure camerali|inserisci (?:nome societ|partita iva)|consulta partita iva'),
      ('directory',r'(?:elenco|directory|lista) (?:delle |di )?(?:aziende|imprese|rivenditori)'),
      ('cluster',r'\bcluster (?:tecnologico|manifatturiero|regionale)|distretto tecnologico'),
      ('sector_portal',r'portale (?:di settore|dedicato|dell.arredamento)'),
      ('web_agency',r'web agency|agenzia web|realizzazione siti web|sviluppo siti web'),
      ('institution',r'universit[aà]|ministero|camera di commercio'),
      ('editorial',r'quotidiano online|testata giornalistica'),
      ('marketplace',r'marketplace (?:di|per|dedicato)'))
    for role,pattern in patterns:
        if re.search(pattern,intro+' '+path,re.I):return role
    # Preserve the existing known-group rule, but only on its own branded
    # domain. A dealer/article mentioning that group cannot inherit the role.
    known_group=re.search(r'\b(?:Prada\s*Group|Gruppo Prada)\b',title,re.I)
    own_brand=host.removeprefix('www.').rsplit('.',1)[0] in ('prada','pradagroup')
    if group_evidence(text,title) or known_group and own_brand:return 'large_group'
    return 'company_candidate'

def counterevidence(text):
    facts=[]
    for m in SIZE.finditer(text):
        raw=m['n'];value=int(re.sub(r'[.,]','',raw));upper=int(m['upper']) if m['upper'] else None
        if raw.startswith('0') or (upper and upper<value):continue
        prefix=text[max(0,m.start()-18):m.start()]
        qualifier='range' if upper else 'at_least' if m['plus'] or re.search(r'oltre|over|almeno|at least',prefix,re.I) else 'approximate' if re.search(r'circa|about|approximately',prefix,re.I) else 'exact'
        facts.append({'kind':'documented_size','employees':value,'upper':upper,'qualifier':qualifier,'quote':m[0]})
    for m in MIGRATION.finditer(text):facts.append({'kind':'existing_new_platform','quote':m[0]})
    for m in re.finditer(r'(?:divisione|divisone|società controllata|parte del gruppo|subsidiary of|division of).{1,80}(?:group|gruppo|holding)\b',text,re.I):
        facts.append({'kind':'documented_group_membership','quote':m[0],'group_size':'UNKNOWN'})
    return facts

def evaluate(identity,pages,geography=None):
    from sales.extract import parse_page
    from .identity import owner_html
    from .context import channels
    from .entity_scope import profile,owner_fact
    observations=[]
    for p in pages:
        if profile(p)['multi_subject']:continue
        clean={**p,'html':owner_html(p['html'])};d=parse_page(clean);v=channels(clean)['visible']
        d['text']='\n'.join(u['text'] for u in v['units'] if not u.get('excluded')) or d['text']
        units=[u for u in v['units'] if not u.get('excluded')]
        d['fact_blocks']=[u['text'] for u in units]
        for left,right in zip(units,units[1:]):
            if left.get('scope') is not None and left.get('scope')==right.get('scope') and re.fullmatch(r'[\d.,+]+',left['text'].strip()) and re.fullmatch(r'dipendenti|lavoratori|employees|addetti',right['text'].strip(),re.I):d['fact_blocks'].append(left['text']+'\n'+right['text'])
        observations.append((p,d))
    facts=[{**f,'url':p['url'],'actor':identity.get('name'),'scope':'owner_page'} for p,d in observations for line in d['fact_blocks'] if owner_fact(line,identity.get('name')) for f in counterevidence(line)]
    facts += [{**f,'url':p['url']} for p,d in observations for f in group_evidence(d['text'],identity.get('name'))]
    roles=['multi_company_catalog'] if profile(pages[0])['multi_subject'] else [source_role(p['url'],d['title'],d['text']) for p,d in observations]
    role=next((r for r in roles if r in EXCLUDED),'company_candidate')
    if any(f['kind']=='owner_group_self_description' for f in facts):role='large_group'
    official=identity.get('identity_status')=='verified'
    if official and excluded_legal_form(identity.get('name')):role='excluded_legal_form'
    if official and role=='directory' and not any(domain(p['url']) in SOURCE_ROLES for p in pages) and re.search(r'/(?:rivenditori|dealers|partner)(?:/|$)',pages[0]['url'],re.I):role='company_candidate'
    page_roles=[]
    mapping={'directory':'EXTERNAL_DIRECTORY','multi_company_catalog':'MULTI_COMPANY_CATALOG','marketplace':'MARKETPLACE','editorial':'EDITORIAL','aggregator':'AGGREGATOR','institution':'INSTITUTION'}
    for p in pages:
        scope=profile(p)
        if not scope['multi_subject']:
            d=parse_page(p);pr=source_role(p['url'],d['title'],d['text'])
            scope.update(domain_role='OFFICIAL_COMPANY_SITE' if official else 'UNKNOWN',page_role='OFFICIAL_COMPANY_SUBPAGE' if official and pr in ('company_candidate','directory') else mapping.get(pr,'UNKNOWN'))
        page_roles.append(scope)
    # Keep a verifiable statement of the offering, not the first menu token
    # (e.g. "Prodotti"). A navigational label alone says nothing about a project.
    offer=[]
    for p,d in observations:
        candidates=[line.strip() for line in d['fact_blocks'] if OFFER.search(line) and (len(line.split())>=4 or (len(line.split())>=3 and re.search(r'\b(?:produciamo|realizziamo|progettiamo|offriamo)\b',line,re.I)))]
        if candidates:
            line=max(candidates,key=lambda s:(bool(re.search(r'produciamo|realizziamo|specializzat|ci occupiamo|progettiamo|offriamo',s,re.I)),min(len(s),500)))
            offer.append({'url':p['url'],'quote':line[:650],'checked_at':p.get('checked_at'),'scope':'business_offering_not_digital_need'})
    contacts=bool(identity.get('contacts'))
    size=next((f['employees'] for f in facts if f['kind']=='documented_size'),None)
    large=any(f.get('employees',0)>=250 for f in facts)
    migrated=any(f['kind']=='existing_new_platform' for f in facts)
    area=geography is None or geography.get('eligible',False)
    reasons=[]
    if role in EXCLUDED:reasons.append('incompatible_source:'+role)
    if large:reasons.append('documented_large_company_lower_priority')
    if any(f['kind']=='documented_group_membership' for f in facts):reasons.append('documented_group_membership_requires_review')
    if migrated:reasons.append('existing_new_platform_requires_new_need')
    if not official:reasons.append('official_domain_unverified')
    if not offer:reasons.append('offer_not_documented')
    if not contacts:reasons.append('company_contact_unknown')
    if not area:reasons.append('outside_or_unresolved_selected_area')
    allowed=not reasons
    return {'status':'SUITABLE_FOR_AUDIT' if allowed else 'LOW_PRIORITY' if large and role not in EXCLUDED else 'NOT_SUITABLE' if role in EXCLUDED or migrated else 'INSUFFICIENT_EVIDENCE',
      'audit_allowed':allowed,'source_role':role,'page_roles':page_roles,'domain_role':'OFFICIAL_COMPANY_SITE' if official else 'UNKNOWN','official_domain_verified':official,'offer_evidence':offer,'contact_available':contacts,
      'size':{'status':'DOCUMENTED' if size is not None else 'UNKNOWN','employees':size},
      'site_complexity':'UNKNOWN','budget':None,'purchase_intent':None,'counterevidence':facts,'reasons':reasons,
      'confidence':'documented_checks' if official else 'incomplete_identity','scope':'audit_priority_only_not_qualification'}

def useful_ai_text(text):
    """A complete substantive passage, not menu labels or contact fields."""
    if counterevidence(text):return True
    return len(text.split())>=12 and bool(OFFER.search(text)) and bool(re.search(r'produciamo|realizziamo|specializzat|lavorazioni|progettiamo|forniamo|manufactur',text,re.I))
