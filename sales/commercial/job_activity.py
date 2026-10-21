"""Phase 4.5: source-bound job activity, independent of technical scoring.

All dates use an explicit UTC clock. Search dates never certify publication.
Evidence is additive; conflicting observations are retained, not overwritten.
"""
import re
from datetime import datetime, timezone, timedelta
from .recommendations import canonical_url
from .geography import resolve_location

MAX_JOB_AGE_DAYS=14
APPLICATION_OBSERVATION_DAYS=14
DATE_BASES={'JobPosting.datePosted','original_request','job_publication','visible_job_publication',
            'Data di pubblicazione esplicita nel testo','Data esplicita nel testo della pagina'}
CLOSED=re.compile(r'no longer accepting applications|applications (?:are )?closed|position (?:is )?filled|job (?:has )?expired|annuncio scaduto|candidature (?:sono )?chiuse|posizione (?:è )?(?:coperta|chiusa)|non (?:si )?accett(?:a|ano|iamo) più candidature',re.I)
OPEN=re.compile(r'applications (?:are )?open|(?:still|currently) accepting applications|candidature (?:sono )?aperte|posizione (?:ancora )?aperta',re.I)
NEGATION=re.compile(r'\b(?:not|never|non|mai|without)\b|unlike other jobs|other positions|altre posizioni',re.I)
GEO_NO=re.compile(r'\b(?:US|USA|United States|UK|United Kingdom)[ -]only\b|\b(?:US|United States|UK|United Kingdom) residents only\b|must (?:be based|reside|live) in (?:the )?(?:US\b|USA\b|United States|UK\b|United Kingdom)|(?:Italy|Italia|Italian residents) (?:excluded|not eligible)|(?:excluding|except|esclusa) (?:Italy|Italia)|solo residenti (?:negli Stati Uniti|nel Regno Unito)',re.I)
REMOTE=re.compile(r'\bremote\b|\bremoto\b|smart working',re.I)


def utc(value):
    if isinstance(value,datetime):d=value
    elif isinstance(value,str):
        try:d=datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:return None
    else:return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def window(value=MAX_JOB_AGE_DAYS):
    if isinstance(value,bool):raise ValueError('Finestra annunci non valida')
    try:n=int(value)
    except (ValueError,TypeError):raise ValueError('Finestra annunci non valida') from None
    if str(value)!=str(n) or not 1<=n<=90:raise ValueError('Finestra annunci: da 1 a 90 giorni')
    return n


def specific_job(body,engine):
    if engine=='WEBSITE_REBUILD':return False
    if body.get('classification') in ('general_collaboration_policy','ongoing','generic_availability') or (body.get('verification') or {}).get('currentness')=='standing_invitation':return False
    if engine=='FREELANCE':return True
    if engine=='STARTUPS' and body.get('classification') in ('cofounder','equity','paid_development','technical_collaboration'):return False
    return bool(body.get('selected_block') or re.search(r'/jobs/|/careers/|sviluppator|developer|engineer',str(body.get('url',''))+' '+str(body.get('title','')),re.I))


def observation(kind,value,url,observed_at,quote='',provenance='ORIGINAL_PAGE',**extra):
    return dict(kind=kind,value=value,url=url,observed_at=observed_at,quote=quote,
                provenance=provenance,scope='specific_job',**extra)


def text_signals(text,url,observed_at,provenance='ORIGINAL_PAGE'):
    out=[]
    # Keep sentence boundaries: footer/listing scope is excluded by the caller.
    for sentence in re.split(r'[\n.!?]+',text):
        if not sentence.strip():continue
        closed=CLOSED.search(sentence)
        # "No longer" and Italian "non ... più" are positive closure phrases.
        context=sentence[:closed.start()] if closed else ''
        if closed and not NEGATION.search(context):out.append(observation('application','CLOSED_CONFIRMED',url,observed_at,sentence.strip(),provenance))
        elif OPEN.search(sentence) and not NEGATION.search(sentence):out.append(observation('application','OPEN_CONFIRMED',url,observed_at,sentence.strip(),provenance))
        if REMOTE.search(sentence) or GEO_NO.search(sentence) or re.search(r'location|località|sede di lavoro|work location|based in|residenza|on[ -]?site|presenza obbligatoria',sentence,re.I):
            out.append(observation('geography',sentence.strip(),url,observed_at,sentence.strip(),provenance))
    return out


def collect(body):
    """Use typed publication metadata and bounded request evidence only."""
    url=body.get('url');dates=body.get('dates') or {};at=dates.get('observed_at') or body.get('checked_at')
    out=list(body.get('job_activity_evidence') or [])
    if dates.get('publication_basis') in DATE_BASES and dates.get('published_at') and not any(e.get('kind')=='publication' for e in out):
        out.append(observation('publication',dates['published_at'],url,at,str(dates['published_at']),method=dates['publication_basis']))
    if dates.get('expires_at'):
        out.append(observation('expiry',dates['expires_at'],url,at,str(dates['expires_at']),method='JobPosting.validThrough'))
    for e in body.get('evidence') or []:
        if e.get('kind')!='request' or not e.get('channel') or str(e['channel']).startswith('search'):continue
        out.extend(text_signals(e.get('quote',''),e.get('url') or url,e.get('checked_at') or at))
    d=body.get('discovery') or {}
    # Metadata can express a location/restriction, never an original date/open state.
    hint=' '.join(str(d.get(k) or '') for k in ('title','snippet','content'))
    if hint:
        out.append(observation('geography',hint,url,None,hint,'SEARCH_SNIPPET'))
    return out


def geo_value(text):
    if text.startswith('Residenza ammessa; luogo di lavoro non specificato:'):return 'GEO_UNKNOWN','Residenza ammessa non dimostra il luogo di lavoro'
    if GEO_NO.search(text):return 'GEO_INCOMPATIBLE','Richiesta esplicita incompatibile con lavoro dall’Italia'
    if re.search(r'(?:on[ -]?site|in presenza|presenza obbligatoria).{0,50}(?:London|Londra|New York|United States|USA|Berlin|Berlino|Paris|Parigi)|(?:London|Londra|New York|Berlin|Berlino|Paris|Parigi).{0,30}(?:on[ -]?site|in presenza)',text,re.I):return 'GEO_INCOMPATIBLE','Presenza obbligatoria all’estero'
    remote=bool(REMOTE.search(text))
    # A candidate-facing freedom-of-location statement differs from generic
    # remote work or a company's worldwide customer base. Restrictions win.
    anywhere=re.search(r'\b(?:lavori|lavorare|lavora) (?:da )?(?:dove vuoi|ovunque)\b|\byou can work (?:from )?anywhere\b',text,re.I)
    if remote and anywhere:
        before=text[max(0,anywhere.start()-60):anywhere.start()]
        restriction=re.search(r'\b(?:solo|only|resident[ei]|residen\w*|based in|must live|right to work|esclus\w*|except|excluding)\b',text,re.I)
        negated=re.search(r'\b(?:non|not|cannot|can.t|mai|never)\b',before,re.I)
        if not restriction and not negated:return 'GEO_COMPATIBLE','Lavoro da remoto con libertà esplicita del luogo, nessuna restrizione osservata'
    if remote and re.search(r'worldwide|anywhere in the world|da tutto il mondo',text,re.I):return 'GEO_COMPATIBLE','Remoto worldwide'
    if remote and re.search(r'\b(?:Europe|Europa|European Union|Unione Europea|EU)\b',text,re.I):return 'GEO_COMPATIBLE','Remoto Europa / UE, nessuna esclusione Italia osservata'
    if remote and re.search(r'\bEMEA\b',text,re.I):
        if re.search(r'Italy|Italia',text,re.I):return 'GEO_COMPATIBLE','Remoto EMEA con Italia esplicitamente inclusa'
        return 'GEO_UNKNOWN','EMEA: inclusione effettiva dell’Italia da verificare'
    # US office alone is not a residence restriction; Remote US is ambiguous.
    if remote and re.search(r'United States|\bUSA?\b|United Kingdom|\bUK\b',text,re.I) and not re.search(r'Italy|Italia',text,re.I):return 'GEO_UNKNOWN','Remoto con località estera: accesso dall’Italia non dimostrato'
    if re.search(r'Italy|Italia\b',text,re.I) or resolve_location(text).get('region'):
        if not re.search(r'headquarter|registered office|sede legale',text,re.I):return 'GEO_COMPATIBLE','Posizione indicata in Italia'
    return 'GEO_UNKNOWN','Compatibilità con lavoro dall’Italia da verificare'


def publication(e,now,days):
    if e.get('method')=='manual_too_old':
        observed=utc(e.get('observed_at'))
        lower=e.get('max_age_days_at_observation',14)
        return ('STALE_CONFIRMED' if observed and lower+(now-observed).total_seconds()/86400>=days else 'DATE_UNKNOWN'),None,None
    value=e.get('value');dt=utc(value)
    if e.get('relative_label'):
        seen=utc(e.get('observed_at'));label=e['relative_label']
        match=re.fullmatch(r'(\d+)\s+(days? ago|giorni? fa)',label.strip(),re.I)
        if not match or not seen or e.get('relative_meaning')!='job_publication':return 'DATE_UNKNOWN',None,None
        # Day labels are rounded. Require the entire possible age interval to fit.
        low=seen-timedelta(days=int(match[1])+1);high=seen-timedelta(days=int(match[1]))
        if seen>now:return 'FUTURE_OR_INVALID_DATE',None,None
        if now-low<=timedelta(days=days):return 'FRESH_CONFIRMED',None,{'from':low.isoformat(),'to':high.isoformat()}
        if now-high>timedelta(days=days):return 'STALE_CONFIRMED',None,{'from':low.isoformat(),'to':high.isoformat()}
        return 'DATE_UNKNOWN',None,{'from':low.isoformat(),'to':high.isoformat()}
    if not dt or dt>now:return 'FUTURE_OR_INVALID_DATE',None,None
    return ('FRESH_CONFIRMED' if now-dt<=timedelta(days=days) else 'STALE_CONFIRMED'),dt,None


def evaluate(body,engine,as_of,manual=(),max_age_days=MAX_JOB_AGE_DAYS):
    now=utc(as_of)
    if now is None:raise ValueError('Clock UTC richiesto')
    days=window(max_age_days);out={'freshness_status':'DATE_UNKNOWN','application_status':'OPEN_UNKNOWN',
      'geographic_eligibility':'GEO_UNKNOWN','category':'verify','published_at':None,'age_days':None,
      'geographic_priority':'UNKNOWN','max_job_age_days':days,'evidence':[],'conflicts':[],'reasons':[],'applicable':specific_job(body,engine)}
    if not out['applicable']:
        out.update(category='not_applicable',reasons=['Pagina di collaborazione continuativa o richiesta commerciale: filtro annunci non applicabile.']);return out
    records=collect(body)+list(manual);trusted=[]
    for e in records:
        e=dict(e);same=canonical_url(e.get('url'))==canonical_url(body.get('url'))
        # A second source needs an explicit same-job binding, not just employer name.
        if e.get('scope')!='specific_job' or not e.get('url') or (not same and not e.get('same_job_verified')):continue
        seen=utc(e.get('observed_at'))
        if seen and seen>now:continue
        out['evidence'].append(e)
        if e.get('provenance') in ('ORIGINAL_PAGE','OFFICIAL_COMPANY_PAGE','MANUAL_OBSERVATIONS'):
            trusted.append(e)
    dates=[];statuses=[];geos=[];pubs=[]
    for e in trusted:
        kind=e.get('kind');seen=utc(e.get('observed_at'));value=e.get('value')
        if kind=='publication' and (e.get('method') in DATE_BASES or e.get('method') in ('manual_publication','manual_too_old','relative_publication')):
            status,dt,interval=publication(e,now,days);dates.append(status)
            if dt:pubs.append(dt)
            if interval:out['publication_interval']=interval
        if kind=='expiry' and utc(value):
            end=utc(value)+(timedelta(days=1) if re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(value)) else timedelta(0))
            if end<now:statuses.append('CLOSED_CONFIRMED')
        if kind=='application' and value in ('CLOSED_CONFIRMED','OPEN_CONFIRMED'):
            if value=='CLOSED_CONFIRMED':statuses.append(value)
            elif seen and now-seen<=timedelta(days=APPLICATION_OBSERVATION_DAYS):statuses.append(value)
        if kind=='geography':geos.append('GEO_INCOMPATIBLE' if e.get('manual_geo_incompatible') and e.get('provenance')=='MANUAL_OBSERVATIONS' else geo_value(str(value))[0])
    # Explicit restrictions in an individual search result can prevent pointless
    # deepening, but broad/unknown geography is never an exclusion.
    for e in out['evidence']:
        if e.get('kind')=='geography' and e not in trusted:geos.append(geo_value(str(e['value']))[0])
    for dimension,values in [('publication',dates),('application',statuses),('geography',geos)]:
        known=set(values)-{'DATE_UNKNOWN','GEO_UNKNOWN'}
        if len(known)>1:out['conflicts'].append({'dimension':dimension,'values':sorted(known),'reason':'Osservazioni discordanti conservate; verifica manuale necessaria.'})
    if len(set(pubs))>1:
        out['conflicts'].append({'dimension':'publication','values':[p.isoformat() for p in sorted(set(pubs))],'reason':'Date originali discordanti.'})
    out['freshness_status']='STALE_CONFIRMED' if 'STALE_CONFIRMED' in dates else 'FUTURE_OR_INVALID_DATE' if 'FUTURE_OR_INVALID_DATE' in dates else 'FRESH_CONFIRMED' if 'FRESH_CONFIRMED' in dates else 'DATE_UNKNOWN'
    if len(set(pubs))==1:
        out['published_at']=pubs[0].isoformat();out['age_days']=(now-pubs[0]).days
    out['application_status']='CLOSED_CONFIRMED' if 'CLOSED_CONFIRMED' in statuses else 'OPEN_CONFIRMED' if 'OPEN_CONFIRMED' in statuses else 'OPEN_UNKNOWN'
    out['geographic_eligibility']='GEO_INCOMPATIBLE' if 'GEO_INCOMPATIBLE' in geos else 'GEO_COMPATIBLE' if 'GEO_COMPATIBLE' in geos else 'GEO_UNKNOWN'
    if out['geographic_eligibility']=='GEO_COMPATIBLE':
        eligible=[str(e.get('value','')) for e in out['evidence'] if e.get('kind')=='geography' and geo_value(str(e.get('value','')))[0]=='GEO_COMPATIBLE']
        high=any(not re.search(r'worldwide|EMEA',t,re.I) and (re.search(r'Italy|Italia|Unione Europea|European Union|\bEU\b',t,re.I) or resolve_location(t).get('region')) for t in eligible)
        out['geographic_priority']='HIGH' if high else 'MEDIUM'
    if out['freshness_status']=='STALE_CONFIRMED':out['reasons'].append(f'Fuori dalla finestra di {days} giorni')
    elif out['freshness_status']!='FRESH_CONFIRMED':out['reasons'].append('Data non verificata' if out['freshness_status']=='DATE_UNKNOWN' else 'Data futura o incoerente')
    if out['application_status']=='CLOSED_CONFIRMED':out['reasons'].append('Candidature chiuse')
    elif out['application_status']=='OPEN_UNKNOWN':out['reasons'].append('Apertura da verificare')
    if out['geographic_eligibility']=='GEO_INCOMPATIBLE':out['reasons'].append('Non compatibile con lavoro dall’Italia')
    elif out['geographic_eligibility']=='GEO_UNKNOWN':out['reasons'].append('Lavoro dall’Italia da verificare')
    if out['freshness_status']=='STALE_CONFIRMED' or out['application_status']=='CLOSED_CONFIRMED' or out['geographic_eligibility']=='GEO_INCOMPATIBLE':out['category']='archived'
    elif out['freshness_status']=='FRESH_CONFIRMED' and out['geographic_eligibility']=='GEO_COMPATIBLE' and not out['conflicts']:out['category']='recent'
    return out


def early_exclusion(record,engine,as_of,max_age_days=MAX_JOB_AGE_DAYS):
    body={'url':record.get('url'),'title':record.get('title'),'discovery':record,
          'job_activity_evidence':record.get('job_activity_evidence',[])}
    a=evaluate(body,engine,as_of,max_age_days=max_age_days)
    if a['category']!='archived':return None
    # Conflicting data calls for review, never an automatic network exclusion.
    if a['conflicts']:return None
    return {'reason':'job_'+('closed' if a['application_status']=='CLOSED_CONFIRMED' else 'stale' if a['freshness_status']=='STALE_CONFIRMED' else 'geo_incompatible'),'activity':a}


def extract_page(page):
    """Acquire only a single scoped position; no footer, aggregate or login text."""
    from sales.extract import parse_page
    from .context import channels,extract
    parsed=parse_page(page);blocks=extract(page);out=[];url=page['url'];at=page['checked_at']
    job_channels=[v for k,v in channels(page).items() if k.startswith('job:')]
    if len(job_channels)==1:
        job=job_channels[0]['job']
        for field,kind in (('datePosted','publication'),('validThrough','expiry')):
            if job.get(field):out.append(observation(kind,job[field],url,at,str(job[field]),method='JobPosting.'+field))
        # Eligibility requirements differ from hiringOrganization.address.
        req=job.get('applicantLocationRequirements') or []
        if isinstance(req,dict):req=[req]
        names=[str(x.get('name','')) for x in req if isinstance(x,dict)]
        if names:
            accepted=any(re.search(r'^(?:IT|Italy|Italia|EU|European Union|Europe|Europa)$',n,re.I) for n in names)
            value=(('Remote Italy' if job.get('jobLocationType')=='TELECOMMUTE' else 'Residenza ammessa; luogo di lavoro non specificato: Italia') if accepted else 'US only' if all(n in ('US','USA','United States') for n in names) else 'UK only' if all(n in ('UK','United Kingdom') for n in names) else 'Residence restricted: '+', '.join(names))
            out.append(observation('geography',value,url,at,', '.join(names),method='JobPosting.applicantLocationRequirements'))
        if job.get('jobLocation') and job.get('jobLocationType')!='TELECOMMUTE':
            loc=job['jobLocation'];loc=loc if isinstance(loc,list) else [loc]
            for place in loc:
                address=place.get('address',{}) if isinstance(place,dict) else {}
                if isinstance(address,dict):
                    country=address.get('addressCountry');country=country.get('name') if isinstance(country,dict) else country
                    value=' '.join(str(x or '') for x in (address.get('addressLocality'),country))
                    if country in ('IT','Italia','Italy'):value+=' Italia'
                    out.append(observation('geography','Location: '+value,url,at,value,method='JobPosting.jobLocation'))
        if job.get('jobLocationType')=='TELECOMMUTE' and not names:out.append(observation('geography','Remote',url,at,'TELECOMMUTE',method='JobPosting.jobLocationType'))
    if len(blocks)==1 and not blocks[0].get('segmentation_uncertain'):
        b=blocks[0]
        out.extend(text_signals(b['text'],url,at))
        if not job_channels and b['dates'].get('publication_basis') in DATE_BASES:
            out.append(observation('publication',b['dates']['published_at'],url,at,str(b['dates']['published_at']),method=b['dates']['publication_basis']))
        for label in re.findall(r'(?:posted|published|pubblicato)\s*:?\s*(\d+\s+(?:days? ago|giorni? fa))',b['text'],re.I):
            out.append(observation('publication',None,url,at,label,method='relative_publication',relative_label=label,relative_meaning='job_publication'))
    return out
