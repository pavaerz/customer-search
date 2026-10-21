"""Offline job recommendations, orthogonal to commercial qualification.

Search metadata remains metadata. No I/O, inference, state promotion or clock
hidden in scoring: callers supply the assessment date for reproducible replays.
"""
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, unquote
from .indexed_jobs import parse_indexed_job
from .opportunity_view import date_value, normalize, declared_actor
from .geography import resolve_location

VERSION='4.4'
HIGH=75
MINIMUM=40
SKILLS=(('WordPress',r'\bwordpress\b',55),('WooCommerce',r'\bwoocommerce\b',55),
 ('Frontend',r'\bfront[ -]?end\b',50),('Web Developer',r'\bweb developer\b|sviluppator\w* (?:di siti |siti )?web|sviluppo (?:di )?siti (?:web|internet)',45),
 ('JavaScript',r'\bjavascript\b',40),('HTML/CSS/SCSS',r'\b(?:html|css|scss)\b',35),
 ('E-commerce development',r'(?:svilupp\w*|develop\w*)[^.!?]{0,35}e[ -]?commerce|e[ -]?commerce (?:developer|development)',45),
 ('React',r'\breact(?:\.js)?\b',35),('Next.js',r'\bnext\.?js\b',35),('PHP',r'\bphp\b',30),
 ('API',r'\b(?:integrazion\w* api|api integration)\b',25),('UI implementation',r'\bui (?:implementation|developer)\b',30),
 ('Web performance',r'\bweb performance\b',25))
ASK=re.compile(r'\b(?:cerchiamo|cerco|ricerchiamo|selezioniamo|ricerca di|looking for|seeking|hiring|cerca|assume)\b',re.I)
OTHER=re.compile(r'\b(?:sap|salesforce|android|ios|firmware|embedded|data entry|commerciale da inserire|consulente di vendita|sales representative)\b',re.I)
EXTERNAL=re.compile(r'\b(?:freelance|partita\s+iva|collaborazion\w*\s+estern\w*|contractor|fornitor\w* estern\w*|progetto a contratto)\b',re.I)
EMPLOYEE=re.compile(r'\b(?:dipendent[ei]|tempo indeterminato|permanent employment|assunzione interna)\b',re.I)
INTERNSHIP=re.compile(r'\b(?:stage|tirocinio|internship)\b',re.I)

def safe_url(value):
    try:
        p=urlsplit(str(value or ''))
        if p.scheme not in ('https','http') or not p.hostname or p.username or p.password:return None
        if re.search(r'[\x00-\x20\\]',str(value)):return None
        return urlunsplit((p.scheme,p.netloc,p.path,p.query,''))
    except ValueError:return None

def canonical_url(value):
    p=urlsplit(safe_url(value) or '')
    host=(p.hostname or '').lower().removeprefix('www.')
    if host.endswith('.linkedin.com'):host='linkedin.com'
    job=re.search(r'/jobs/view/(?:.*-)?(\d+)/?$',p.path)
    if host=='linkedin.com' and job:return 'linkedin.com/jobs/'+job[1]
    query=[(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith(('utm_','srsltid','trk','tracking'))]
    return urlunsplit(('',host,p.path.rstrip('/'),urlencode(sorted(query)),''))

def information(value,source,url,verified=False):
    return {'value':value,'provenance':source,'url':url,'verified_on_original':verified}

def assess(item,as_of,include_inactive=False):
    b=item['body'];d=b.get('discovery') or {};identity=b.get('identity') or {};v=b.get('verification') or {}
    url=safe_url((b.get('social') or {}).get('post_url') or d.get('original_url') or b.get('url'))
    title=str(d.get('title') or b.get('title') or '').strip()
    snippet=str(d.get('snippet') or d.get('content') or '')
    base={'id':item['id'],'revision_id':item.get('selected_revision') or item.get('latest_revision'),
          'engine':item['engine'],'official_state':item['state'],'classification':b.get('classification'),
          'version':VERSION,'recommended':False,'exclusion':None,'original_url':url,'title':title,
          'compatibility_score':0,'evidence_confidence':'LOW','tier':'INSUFFICIENT','duplicate_of':None}
    def exclude(reason):
        kind='INSUFFICIENT_INFORMATION'
        if reason=='different_primary_specialism' or (reason=='negative_or_irrelevant_source' and b.get('classification') in ('irrelevant','hosted_incompatible')):kind='TECHNICAL_IRRELEVANCE'
        elif reason in ('explicitly_closed','negative_or_irrelevant_source'):kind='NEGATIVE_SOURCE_EVIDENCE'
        elif reason in ('not_specific_opportunity','no_usable_url','excluded_pdf','outbound_not_job'):kind='NOT_AN_INDIVIDUAL_JOB'
        elif reason in ('user_exclusion','explicit_geographic_restriction'):kind='EXCLUSION_PREFERENCE'
        return {**base,'exclusion':reason,'exclusion_kind':kind}
    if item['engine']=='WEBSITE_REBUILD':return exclude('outbound_not_job')
    from .source_intelligence import JUNIOR,NON_WEB
    if JUNIOR.search(title):return exclude('internship_or_junior')
    if NON_WEB.search(title):return exclude('different_primary_specialism')
    if 'HTTP 404' in str(b.get('reason','')):return exclude('source_no_longer_available')
    if item.get('manual_state') in ('discarded','contacted') or item.get('do_not_contact') or item.get('company_dismissed'):return exclude('user_exclusion')
    demand=b.get('demand_assessment') or {}
    if demand.get('excluded'):return exclude(demand['reasons'][0])
    if not url:return exclude('no_usable_url')
    p=urlsplit(url);host=p.hostname.lower();path=unquote(p.path)
    if re.search(r'\.pdf(?:$|[?#])',url,re.I) or re.search(r'\bPDF\b',title):return exclude('excluded_pdf')
    # Search/result/category pages are not a single opportunity, even if the
    # snippet contains one enticing role. No URL invented from an aggregator.
    if not path.strip('/') or re.search(r'/search|/offerte-lavoro/|/lavoro-[^/]+/?$|/profile/|/company/|/in/',path,re.I):return exclude('not_specific_opportunity')
    if b.get('classification') in ('seller','no_request','irrelevant','hosted_incompatible','target_incompatible'):return exclude('negative_or_irrelevant_source')
    now=as_of if isinstance(as_of,datetime) else date_value(as_of)
    if now is None:raise ValueError('Data di valutazione richiesta')
    expiry=date_value((b.get('dates') or {}).get('expires_at'))
    if not include_inactive and (v.get('currentness') in ('closed','expired') or (expiry and expiry<now) or re.search(r'non accetta più candidature|no longer accepting applications|posizione chiusa|position closed',snippet,re.I)):return exclude('explicitly_closed')
    is_job=bool(re.search(r'/jobs/view/|/jobs/|/job-offers/|/lavoro/ricerca_',path,re.I))
    # URL describes the primary role, useful to reject unrelated posts whose
    # snippets contain author bios or comments mentioning WordPress.
    primary=title+' '+(path.split('-activity-')[0].replace('-',' ') if '/posts/' in path else '')
    if OTHER.search(primary):return exclude('different_primary_specialism')
    proofs=[e for e in b.get('evidence',[]) if e.get('kind')=='request' and e.get('quote') and e.get('channel') and not str(e['channel']).startswith('search')]
    original=bool(proofs and b.get('document_ids') and v.get('extraction_complete'))
    # Only selected request blocks, never footer biographies or whole-page
    # keyword accumulation. Snippet attribution stays explicitly unverified.
    original_text=' '.join(e['quote'] for e in proofs) if original else ''
    ask=ASK.search(snippet)
    requested_snippet=snippet[ask.start():ask.end()+220] if ask else ''
    technical_text=title+' '+(snippet if is_job else requested_snippet)+' '+original_text
    if not is_job and not original and not ask:return exclude('no_request_context')
    if not is_job and not original and OTHER.search(requested_snippet):return exclude('different_primary_specialism')
    skills=[(name,weight) for name,pattern,weight in SKILLS if re.search(pattern,technical_text,re.I)]
    if not skills:return exclude('insufficient_technical_information')
    # Generic IT/full-stack alone is deliberately insufficient.
    points=min(65,max(w for _,w in skills)+5*(len(skills)-1))
    detail=[{'dimension':'technical','points':points,'reason':'Competenze pertinenti: '+', '.join(n for n,_ in skills)}]
    hint=parse_indexed_job({**d,'title':re.sub(r'\s+-\s+Jobs$','',title,flags=re.I),'url':url,'snippet':snippet})
    name=identity.get('name') if identity.get('identity_status')=='verified' else declared_actor(b)
    company_source='OFFICIAL_COMPANY_PAGE' if identity.get('identity_status')=='verified' else 'THIRD_PARTY_PAGE' if name else 'UNKNOWN'
    if not name and not hint.get('identity_conflict'):
        name=hint.get('company_candidate');company_source='SEARCH_TITLE' if hint.get('basis') not in ('url_slug','url_employer_slot') else 'UNKNOWN'
    if not name and re.match(r'^(?:siamo alla ricerca|cerchiamo)\b',title,re.I) and hint.get('url_hint'):
        name=hint['url_hint']['company'];company_source='UNKNOWN'
    if name and resolve_location(name).get('region') and identity.get('identity_status')!='verified':name=None
    explicit_company=re.match(r'^In (.{2,85}?) siamo alla ricerca\b',snippet,re.I) or re.match(r'^(.{2,85}?)\s+(?:cerca|is looking for|is hiring)\b',snippet,re.I)
    if not name and explicit_company and not re.match(r'we|siamo|sono|cerchiamo',explicit_company[1],re.I):
        name=explicit_company[1];company_source='SEARCH_SNIPPET'
    if not name and original and b.get('company') and b.get('company') not in (host,host.removeprefix('www.')):name=b['company'];company_source='ORIGINAL_PAGE'
    contract_snippet=snippet if is_job else snippet[max(0,ask.start()-5):ask.end()+220] if ask else ''
    contract_text=original_text if original else title+' '+contract_snippet
    # Never turn a URL slug or the word full-time into a contract declaration.
    external=bool(EXTERNAL.search(contract_text));employment=bool(EMPLOYEE.search(contract_text));intern=bool(INTERNSHIP.search(contract_text))
    if re.search(r'non (?:cerchiamo )?(?:un[oa]? )?dipendente|not an employee',contract_text,re.I):employment=False
    negated_external=bool(re.search(r'non (?:cerchiamo|accettiamo) (?:un[oa]? )?freelance|no freelancers',contract_text,re.I))
    if negated_external:external=False
    contract='AMBIGUOUS' if external and employment else 'INTERNSHIP' if intern else 'EMPLOYEE' if employment else 'EXTERNAL' if external else 'UNKNOWN'
    cp=12 if contract=='EXTERNAL' else -10 if contract=='INTERNSHIP' else 0
    if re.search(r'equity.only|senza compenso|unpaid',contract_text,re.I):contract='UNPAID_OR_EQUITY';cp=-15
    contract_labels={'EXTERNAL':'Freelance / collaborazione esterna','EMPLOYEE':'Rapporto dipendente','INTERNSHIP':'Stage / tirocinio','UNPAID_OR_EQUITY':'Senza compenso / equity','AMBIGUOUS':'Indicazioni contrattuali discordanti','UNKNOWN':'Contratto non verificato'}
    detail.append({'dimension':'relationship','points':cp,'reason':contract_labels[contract]+(' (solo titolo/snippet)' if contract!='UNKNOWN' and not original else '')})
    location_text=title+' '+requested_snippet
    remote=bool(re.search(r'\bremot[eo]|smart working',location_text,re.I)) and not re.search(r'no remote|non.*remoto',location_text,re.I)
    geo=b.get('geography') or {};regions=geo.get('regions') or []
    guessed=resolve_location(location_text)
    loc=guessed.get('city') or guessed.get('region') or (', '.join(regions) if regions else None) or hint.get('components',{}).get('LOCATION')
    gp=10 if remote or guessed.get('region')=='Veneto' or 'Veneto' in regions else 6 if (guessed.get('region') or regions) else 0
    selected=geo.get('selected_regions') or []
    known_region=guessed.get('region') or (regions[0] if len(regions)==1 else None)
    if known_region and selected and known_region not in selected and not remote:gp=-15
    if not include_inactive and re.search(r'\bUS[- ]based|US[- ]only|United States only',title+' '+path,re.I) and not re.search(r'international applicants',title,re.I):return exclude('explicit_geographic_restriction')
    detail.append({'dimension':'geography','points':gp,'reason':('Remoto dichiarato nei dati disponibili' if remote else loc or 'Località non verificata')+(' · area non preferita' if gp<0 else '')})
    dates=b.get('dates') or {};published=dates.get('published_at')
    basis=dates.get('publication_basis')
    if not published and (v.get('checks') or {}).get('temporal_basis'):published=b.get('published_at');basis='original_request'
    published_date=date_value(published) if basis and not re.search(r'index|search|snippet',str(basis),re.I) else None
    age=(now-published_date).days if published_date else None
    dp=8 if age is not None and 0<=age<=30 else 4 if age is not None and 30<age<=90 else -10 if age is not None and age>180 else 0
    detail.append({'dimension':'recency','points':dp,'reason':f'Pubblicazione documentata: {published}' if age is not None and age>=0 else 'Data non verificata'})
    confidence='HIGH' if original and identity.get('identity_status')=='verified' else 'MEDIUM' if original else 'LOW'
    detail.append({'dimension':'source','points':5 if original else 0,'reason':'Blocco della richiesta letto sulla pagina' if original else 'Solo metadati indicizzati; originale non verificato'})
    score=max(0,min(100,sum(d['points'] for d in detail)))
    missing=[]
    if not original:missing.append('Contenuto non completamente verificato. Apri l’annuncio per controllare i dettagli.')
    if b.get('classification')=='access_incomplete' and b.get('reason'):missing.append('Ultimo accesso: '+b['reason'][:400])
    if identity.get('identity_status')!='verified':missing.append('Identità aziendale non corroborata.')
    if explicit_company and name and normalize(explicit_company[1])!=normalize(name):missing.append('Il soggetto citato nello snippet ('+explicit_company[1]+') differisce da quello indicato nel titolo/URL; attribuzione da verificare.')
    if not published_date or age<0:missing.append('Data non verificata.')
    if not v.get('availability_verified'):missing.append('Disponibilità attuale non confermata.')
    if contract=='UNKNOWN' or not original:missing.append('Tipo di contratto da verificare sulla fonte originale.')
    if not loc and not remote:missing.append('Località e possibilità di lavoro remoto non verificate.')
    provenance=[information(title,'SEARCH_TITLE' if d.get('title') else 'ORIGINAL_PAGE' if original else 'UNKNOWN',url,original and not d.get('title'))]
    if snippet:provenance.append(information(snippet,'SEARCH_SNIPPET',url))
    provenance.extend(information(e['quote'],'ORIGINAL_PAGE',e['url'],True) for e in proofs[:4] if original)
    tier='HIGH' if score>=HIGH else 'MEDIUM' if score>=50 else 'LOW'
    return {**base,'recommended':score>=MINIMUM,'exclusion':None if score>=MINIMUM else 'low_compatibility',
            'compatibility_score':score,'tier':tier,'score_detail':detail,'evidence_confidence':confidence,
            'company':information(name,company_source,identity.get('website') or url,identity.get('identity_status')=='verified'),
            'location':information(('Remoto · '+loc if remote and loc else 'Remoto' if remote else loc),'ORIGINAL_PAGE' if regions and not guessed.get('region') else 'SEARCH_TITLE' if (loc and loc in title) or (remote and re.search(r'\bremot[eo]|smart working',title,re.I)) else 'SEARCH_SNIPPET' if loc or remote else 'UNKNOWN',url,bool(regions and not guessed.get('region'))),
            'source':host,'published_at':published_date.isoformat() if published_date and age>=0 else None,
            'skills':[n for n,_ in skills],'relationship':{'type':contract,'label':contract_labels[contract],'verified_on_original':original and contract!='UNKNOWN','provenance':'ORIGINAL_PAGE' if original else 'SEARCH_TITLE' if (EXTERNAL.search(title) or EMPLOYEE.search(title) or INTERNSHIP.search(title)) else 'SEARCH_SNIPPET' if contract!='UNKNOWN' else 'UNKNOWN'},
            'missing':missing,'provenance':provenance,'original_read':original,
            'canonical_url':canonical_url(url),'role_key':normalize(hint.get('role_candidate') or title),
            'request_hint_key':normalize(original_text or snippet),
            'decision_authority':'recommendation_only','assessed_at':now.isoformat()}

def rank(items,as_of,include_inactive=False):
    results=[assess(item,as_of,include_inactive) for item in items];seen={}
    for r in sorted(results,key=lambda r:(not r['recommended'],-r['compatibility_score'],r['id'])):
        if not r['recommended']:continue
        keys=[('url',r['canonical_url'])]
        company=normalize(r['company']['value'])
        if company and r['role_key'] and len(r['request_hint_key'])>=30:
            # Require matching substantive content too: one employer can have
            # several distinct projects with the same generic job title.
            keys.append(('role',company,r['role_key'],r['request_hint_key'],normalize(r['location']['value']),r['published_at']))
        match=next((seen[k] for k in keys if k in seen),None)
        if match is not None:r.update(recommended=False,duplicate_of=match,exclusion='duplicate')
        else:
            for k in keys:seen[k]=r['id']
    return sorted(results,key=lambda r:(not r['recommended'],-r['compatibility_score'],r['id']))
