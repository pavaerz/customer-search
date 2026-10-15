"""Keep editorial evidence only after a name/domain/location association is checked."""
import re
from .research_rules import normalize, REGION_CITIES


def subject_context(doc,subject,quote):
    """A bare company name is not an informative passage about a business event.

    Recover a literal paragraph that names the subject, within the selected
    article body. Never borrow a neighbouring firm's event or a sidebar.
    """
    body=doc.get('research_text',doc.get('text',''))
    pattern=r'(?<!\w)'+re.escape(subject)+r'(?!\w)'
    valid=bool(re.search(pattern,quote,re.I)) and normalize(quote) in normalize(body)
    if valid and len(quote)>=80:return quote
    paragraphs=[line.strip() for line in body.splitlines() if len(line.strip())>=80 and re.search(pattern,line,re.I)]
    if paragraphs:
        from .research_strategies import SIGNAL
        return next((line for line in paragraphs if SIGNAL.search(line)),paragraphs[0])[:1200]
    return quote if valid else None


def subject_document(doc,subject,quote):
    """Retain separately grounded paragraphs naming the verified protagonist.

    Identity extraction's short quotation is a locator, not a limit on how much
    of an already-read source can be investigated. Unnamed adjacent passages and
    other companies' paragraphs are not automatically attributed to the subject.
    """
    body=doc.get('research_text',doc.get('text',''))
    if normalize(quote) not in normalize(body) or normalize(quote) not in normalize(doc.get('text','')):return None
    pattern=r'(?<!\w)'+re.escape(subject)+r'(?!\w)'
    legal=r'\b(?:[A-ZÀ-Ý][\wÀ-ÿ&.-]*[ \t]+){1,5}(?:S\.?r\.?l\.?|SRL)\b'
    if not re.search(pattern,quote,re.I):return None
    words=lambda text:set(re.findall(r'\w{2,}',normalize(text)))-{'srl','società','azienda'}
    expected=words(subject)
    selected=[]
    for line in body.splitlines():
        if not re.search(pattern,line,re.I) or normalize(line) not in normalize(doc.get('text','')):continue
        other=any(not expected or len(words(m[0])&expected)/max(1,len(words(m[0])))<.75 for m in re.finditer(legal,line))
        if other:continue
        selected.append(line.strip())
    if not any(normalize(quote) in normalize(line) for line in selected):selected.insert(0,quote)
    selected=list(dict.fromkeys(x for x in selected if x))
    return {**doc,'research_text':'\n'.join(selected),'scoped_to_subject':subject,
            'subject_passages':selected,'subject_scope_method':'Citazione di identificazione e paragrafi letterali che nominano l’impresa; nessuna attribuzione automatica dei paragrafi adiacenti.'}


def verified_origins(payload, identity):
    origin=payload.get('source_documents',[])
    subject=payload.get('subject')
    if not origin or not subject:return [],[]
    words=lambda v:set(re.findall(r'\w{3,}',normalize(v)))-{'srl','spa','società','azienda','home'}
    expected=words(subject)
    if not expected or len(words(identity.get('name',''))&expected)/len(expected)<.75:
        return [],['Collegamento fra azienda citata e dominio non verificato']
    quote=payload.get('subject_quote','')
    if not payload.get('official_link'):
        region=identity.get('region');places=[region] if region else []
        places.extend(city for city in re.findall(r'La Spezia|Reggio Emilia|[A-ZÀ-Ý][a-zà-ÿ]+',REGION_CITIES.get(region,'')) if re.search(r'\b'+re.escape(city)+r'\b',identity.get('location') or '',re.I))
        context=quote or ' '.join(d.get('research_text',d['text']) for d in origin)
        if not any(re.search(r'(?<!\w)'+re.escape(place)+r'(?!\w)',context,re.I) for place in places):
            return [],['Omonimia possibile: fonte editoriale e sede ufficiale non concordano']
    if quote:
        origin=[scoped for d in origin if (scoped:=subject_document(d,subject,quote))]
        if not origin:return [],['Citazione aziendale non riscontrata nel corpo delle fonti originali.']
    return origin,[]


def source_entities(page,doc):
    """Extract literal legal names and article subjects, retaining their observed role.

    Not a verified identity. Publishers/investors/partners are kept in diagnostics,
    never silently promoted as the protagonist. No generated URLs.
    """
    from .extract import parse_page,nodes,types
    from .research_strategies import SIGNAL
    parsed=parse_page(page);body=doc.get('research_text',doc['text']);names=[]
    for node in nodes(parsed['doc'].schemas):
        if not types(node)&{'NewsArticle','Article','BlogPosting'}:continue
        for key in ('about','mentions'):
            for entity in nodes(node.get(key,[])):
                if types(entity)&{'Organization','Corporation','LocalBusiness'} and isinstance(entity.get('name'),str):names.append(entity['name'])
    # Restrict to literal capitalised legal names, not invented proper-name recognition.
    names += [m[0].strip() for m in re.finditer(r'\b(?:[A-ZÀ-Ý][\wÀ-ÿ&.-]*[ \t]+){1,5}(?:S\.?r\.?l\.?|SRL)\b',body)]
    result=[]
    for name in dict.fromkeys(names):
        match=re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',body)
        if not match or len(name)>100:continue
        # Keep the containing sentence for event association and geography checks.
        start=max(body.rfind('\n',0,match.start()),body.rfind('. ',0,match.start()))+1
        end=body.find('\n',match.end());end=len(body) if end<0 else end
        quote=body[start:min(end,match.end()+300)].strip()
        role='COMPANY'
        if re.search(r'editore|redazione|testata',quote,re.I):role='PUBLISHER'
        elif re.search(r'(?:fondo|investitore|banca)\s+'+re.escape(name),quote,re.I):role='INVESTOR'
        elif re.search(r'(?:partner|fornitore)\s+'+re.escape(name),quote,re.I):role='PARTNER'
        elif re.search(r'(?:web agency|agenzia digitale)\s+'+re.escape(name),quote,re.I):role='AGENCY'
        elif re.search(r'^(?:Comune|Regione|Ministero|Camera di commercio)\b',name,re.I):role='PUBLIC_ENTITY'
        # The subject must participate in an observed event, not just have a footer legal name.
        if role=='COMPANY' and not SIGNAL.search(quote):continue
        result.append({'name':name,'quote':quote[:500],'role':role,'method':'Nome letterale e contesto nella fonte originale'})
    return result


def alternate_identity_query(subject,region):
    """Use the observed trading-name words when punctuation/legal suffix hurts search.

    This only changes a search query. The original full subject is still required
    by identity verification; a similarly named result is never accepted by alias.
    """
    name=re.sub(r'\b(?:s\.?\s*r\.?\s*l\.?|s\.?\s*n\.?\s*c\.?|s\.?\s*a\.?\s*s\.?)\s*$', '',subject,flags=re.I)
    name=re.sub(r'\s*&\s*C\.?\s*$','',name,flags=re.I).strip(' .,')
    return ' '.join((name,region or '', 'azienda contatti')).strip()
