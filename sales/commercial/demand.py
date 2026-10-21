"""5.1 source-bound demand checks. Pure functions: no fetching or AI authority.

Page role, buyer identity and commercial readiness are separate claims. A
negative page role does not classify every business mentioned on that page.
"""
import re
from datetime import date
from urllib.parse import urlsplit

VERSION = '5.1'
NON_DEMAND = {'SUPPLIER_OFFER', 'COMPLETED_PROJECT', 'JOB_AGGREGATION', 'EDITORIAL_CONTENT', 'DIRECTORY'}
WEB = re.compile(r'wordpress|woocommerce|javascript|jquery|\bphp\b|html|css|scss|react(?!\s+native)|next\.?js|front[ -]?end|web\s*(?:design|develop|app)|\bMVP\b|sit[oi]\s+(?:web|aziendal)|e[ -]?commerce', re.I)
WRONG = re.compile(r'\belectrical engineer|\baccount executive|\b(?:unreal|unity)\b|C\+\+|\b3D\b|\bSAP\b|data engineer|cyber\s?security|security (?:infrastructure|engineer)|sales engineer|social media manager|content creator|graphic designer|\bSRE\b|DataOps|MLOps|\btirocin|\binternship\b', re.I)
ASK = re.compile(r'\b(?:I am looking for|we (?:are )?(?:looking for|seeking|hiring|need)|is seeking|cerchiamo|cerco|cercasi|ricerchiamo|siamo alla ricerca)\b', re.I)
SELL = re.compile(r'\b(?:we (?:offer|provide|build)|our (?:services|developers)|offriamo|realizziamo|i offer)\b', re.I)
STANDING = re.compile(r'entra nella nostra rete|entra nel nostro network|collaborazioni continuative|accettiamo collaborazion|siamo aperti.{0,40}collaborazion|join our (?:freelance|partner) network', re.I)
LIST_TITLE = re.compile(r'\b(?:\d[\d,]*\s+(?:remote\s+)?[^|\n]{0,65}jobs|jobs in |jobs worldwide|jobs with |remote .{0,55}jobs|developer jobs|engineering jobs|technology jobs|freelance and remote .{0,40}jobs|results for .{0,50}jobs)\b', re.I)
REASONS = {'SUPPLIER_OFFER':'supplier_offer','COMPLETED_PROJECT':'completed_project','JOB_AGGREGATION':'aggregate_listing','EDITORIAL_CONTENT':'no_buyer_demand','DIRECTORY':'no_buyer_demand'}


def technical_fit(title, text):
    """Primary requested responsibilities, not global site technology keywords."""
    significant = bool(re.search(r'(?:build|develop|implement|design|svilupp|realizz|gestir).{0,90}(?:frontend|front-end|React(?! Native)|WordPress|Next.js|web interface)', text, re.I))
    wrong = WRONG.search(title) or WRONG.search(text[:1600])
    mobile = re.search(r'react native|mobile developer|iOS|Android', title+' '+text[:700], re.I)
    if (wrong or mobile) and not significant:
        return {'status':'INCOMPATIBLE','reason':'job_incompatible','quote':(wrong or mobile)[0]}
    if WEB.search(title+' '+text):
        return {'status':'COMPATIBLE','reason':'verified_web_component','quote':WEB.search(title+' '+text)[0]}
    return {'status':'UNKNOWN','reason':'technical_scope_unknown','quote':None}


def geography(text):
    # Restriction sentences take precedence over a broad remote slogan.
    restriction = re.search(r'(?:US|United States|UK|United Kingdom|Canada|India|Portugal|Germany)[ -]only|(?:must (?:be|reside)|residents? (?:of|in)|based in|required to be).{0,35}(?:United States|USA|US\b|UK\b|Canada|India|Portugal|Germany)', text, re.I)
    if restriction:return {'status':'GEO_INCOMPATIBLE_CONFIRMED','mode':'country_restricted','quote':restriction[0]}
    worldwide=re.search(r'(?:remote|work).{0,35}(?:worldwide|anywhere|everywhere)|(?:worldwide|anywhere).{0,30}remote',text,re.I)
    if worldwide:return {'status':'GEO_COMPATIBLE_CONFIRMED','mode':'remote_worldwide','quote':worldwide[0]}
    europe=re.search(r'remote.{0,30}(?:within Europe|in Europe|from Italy|Italy|Italia|European Union|\bEU\b)|(?:Europe|Italy|Italia|European Union).{0,15}remote',text,re.I)
    if europe:return {'status':'GEO_COMPATIBLE_CONFIRMED','mode':'remote_europe_or_italy','quote':europe[0]}
    onsite=re.search(r'(?:on[ -]?site|in presenza|office.based|hybrid).{0,85}(?:Jacksonville|Detroit|United States|\bUSA\b|New York|\bUS\b|London|Tokyo|Brussels|Bengaluru)',text,re.I)
    if onsite:return {'status':'GEO_INCOMPATIBLE_CONFIRMED','mode':'onsite_abroad','quote':onsite[0]}
    return {'status':'GEO_UNKNOWN','mode':'remote_emea' if re.search(r'remote.{0,25}EMEA',text,re.I) else 'remote_unspecified' if re.search('remote|remoto',text,re.I) else 'unknown','quote':None}


def metadata_exclusion(item):
    """Only conclusive title/URL structures; a snippet never proves readiness."""
    title=str(item.get('title') or '');path=urlsplit(item.get('url','')).path.lower()
    if LIST_TITLE.search(title) and not re.search(r'/jobs/view/|/job/|/remote-job/|/projects/|/offer/',path):return 'aggregate_listing'
    if WRONG.search(title) and not WEB.search(title):return 'job_incompatible'
    if re.search(r'\b(?:guide|guida)\b',title,re.I) and not ASK.search(title):return 'no_buyer_demand'
    if re.search(r'/hire-developers/|/hire-[\w-]+developer',path) and not ASK.search(title):return 'supplier_offer'
    return None


def source_from_page(page):
    from sales.extract import parse_page
    from .context import channels
    p=parse_page(page)
    return {'url':page['url'],'title':p['doc'].title or p['title'],'text':p['text'],'checked_at':page.get('checked_at'),'evidence_channels':channels(page),'original':page.get('status',200)==200}


def source_from_document(document):
    details=document.get('details') or {}
    return {'url':document['url'],'title':document.get('page_title') or details.get('page_title') or document.get('title',''),'text':document.get('text',''),'checked_at':document.get('checked_at'),'evidence_channels':document.get('evidence_channels') or details.get('evidence_channels',{}),'original':bool(document.get('text'))}


def assess(source, identity=None, result=None, today=None):
    identity=identity or {};result=result or {};today=today or date.today()
    url=source.get('url','');title=source.get('title','');original=source.get('original',False)
    channels=source.get('evidence_channels') or {};visible=channels.get('visible',{})
    units=[u for u in visible.get('units',[]) if not u.get('excluded')]
    text='\n'.join(u['text'] for u in units) if units else source.get('text','')
    jobs=[v for k,v in channels.items() if k.startswith('job:')]
    path=urlsplit(url).path.lower();publisher=urlsplit(url).netloc
    individual_path=bool(re.search(r'/jobs/view/|/job/|/remote-job/|/projects/|/offer/|/job-detail/|/job-\d+|/jobs/[a-z0-9]{15,}',path))
    # A JobPosting embedded in search results is still a listing, not the page's buyer.
    listing=bool((LIST_TITLE.search(title) and not individual_path) or len(jobs)>1 or (re.search(r'^/(?:jobs|jobs/software-engineering)/?$',path) and re.search(r'Sort by|Job Specialism|Job Type|positions|offerte',text,re.I)))
    core=jobs[0].get('text','') if len(jobs)==1 and not listing else text
    job=jobs[0].get('job') or {} if len(jobs)==1 and not listing else {}
    if len(jobs)==1 and not listing and not job:
        # Historical documents retain canonical channels, but not the complete
        # schema object. Only restore fields explicitly saved in that block.
        block=next((b for b in result.get('request_blocks',[]) if b.get('channel')=='job:0'),{})
        job={'title':block.get('role'), 'hiringOrganization':{'name':block.get('subject')},
             'datePosted':(block.get('dates') or {}).get('published_at')}
    role=job.get('title') or title
    completed=re.search(r'(?:we were looking|il cliente cercava|cercavamo).{0,800}(?:delivered|realizzato|consegnat|completat|built)',text,re.I|re.S)
    invitation=STANDING.search(text)
    ask=ASK.search(core)
    kind='UNKNOWN'
    if listing:kind='JOB_AGGREGATION'
    elif invitation and not job and not individual_path and re.search(r'freelanc|collaborator|partner',core,re.I):kind='STANDING_COLLABORATION'
    elif job or individual_path:kind='INDIVIDUAL_JOB'
    elif completed and not ASK.search(text):kind='COMPLETED_PROJECT'
    elif (re.search(r'/(?:blog|learn|resources)/|guide',path) and re.search(r'guide|guida',title+' '+path,re.I)) or '/channels/' in path:kind='EDITORIAL_CONTENT'
    elif SELL.search(text) and not re.search(r'(?:we are|I am|cerchiamo|cerco).{0,60}(?:looking for|seeking|developer|sviluppator)',text,re.I):kind='SUPPLIER_OFFER'
    elif re.search(r'(?:development company|development services|hire .{0,40}developers|starting a tech startup)',title,re.I) and not ask:kind='SUPPLIER_OFFER'
    elif re.search(r'directory|elenco (?:aziende|fornitori)|consulenza web.*annunci',title,re.I):kind='DIRECTORY'
    elif ask and WEB.search(core):kind='BUYER_DEMAND'
    # A personal marketplace request is buyer demand; the marketplace is not buyer.
    if individual_path and '/projects/' in path and ask:kind='BUYER_DEMAND'
    if not original:
        kind='UNKNOWN' if not metadata_exclusion(source) else {'aggregate_listing':'JOB_AGGREGATION','supplier_offer':'SUPPLIER_OFFER','no_buyer_demand':'EDITORIAL_CONTENT'}.get(metadata_exclusion(source),'UNKNOWN')
    fit=technical_fit(role,core) if kind not in NON_DEMAND else {'status':'UNKNOWN','reason':'not_an_individual_request','quote':None}
    # Never borrow geography from navigation or other jobs. Job metadata may
    # locate the role but does not prove remote eligibility on its own.
    geo_text=core
    if job:
        loc=job.get('jobLocation');loc=loc if isinstance(loc,list) else [loc] if loc else []
        location=' '.join(str(a.get('address',{}).get(k,'')) for a in loc if isinstance(a,dict) and isinstance(a.get('address'),dict) for k in ('addressLocality','addressCountry'))
        if re.search(r'\bonsite\b|on-site|in presenza',text,re.I) and not re.search(r'remote|telecommute',core,re.I):geo_text+='\nOnsite '+location
        if not location and re.search(r'\bonsite\b|on-site',text,re.I):
            for e in result.get('job_activity_evidence',[]):
                if e.get('kind')=='geography' and e.get('method')=='JobPosting.jobLocation' and e.get('provenance')=='ORIGINAL_PAGE' and e.get('url')==url:
                    geo_text+='\nOnsite '+str(e.get('value',''))
    geo=geography(geo_text) if kind in {'INDIVIDUAL_JOB','BUYER_DEMAND','STANDING_COLLABORATION'} else {'status':'GEO_UNKNOWN','mode':'not_a_request','quote':None}
    buyer=None;recruiter=None;mentioned=[]
    hiring=job.get('hiringOrganization') or {};subject=hiring.get('name') if isinstance(hiring,dict) else None
    for b in result.get('request_blocks',[]):
        if b.get('subject'):mentioned.append(b['subject'])
    # Recruiting intermediaries explicitly describe a network/placement business.
    recruiting=bool(re.search(r'placement solutions|staffing|recruitment agency|recruiting agency',text,re.I))
    if recruiting:recruiter=publisher
    if kind in {'INDIVIDUAL_JOB','BUYER_DEMAND','STANDING_COLLABORATION'} and not recruiting:
        if subject and subject.casefold()!=publisher.casefold():buyer=subject
        elif kind=='STANDING_COLLABORATION' and identity.get('identity_status')=='verified':buyer=identity.get('name')
        elif identity.get('identity_status')=='verified' and ask and (not individual_path or re.search(re.escape(str(identity.get('name') or '__unknown__'))+r'\s+(?:is seeking|is hiring|cerca|ricerca)',core,re.I)):buyer=identity.get('name')
    publication=job.get('datePosted');basis='JobPosting.datePosted' if publication else None
    if not publication:
        for e in result.get('job_activity_evidence',[]):
            if e.get('kind')=='publication' and e.get('provenance')=='ORIGINAL_PAGE' and e.get('scope')=='specific_job' and e.get('url')==url:
                publication=e.get('value');basis=e.get('method');break
    age=None
    try:age=(today-date.fromisoformat(str(publication)[:10])).days
    except ValueError:pass
    fresh='DATE_UNKNOWN' if age is None or age<0 else 'FRESH_CONFIRMED' if age<=14 else 'STALE_CONFIRMED'
    standing=kind=='STANDING_COLLABORATION'
    external=bool(re.search(r'freelanc|contractor|partita\s*iva|collaborator\w* estern',core,re.I))
    closed=bool(re.search(r'no longer accepting|has been removed|applications closed|posizione chiusa|candidature chiuse',core,re.I))
    pool=bool(re.search(r'join our network.{0,120}upcoming opportunities|variety of upcoming opportunities',core,re.I))
    reasons=[]
    if kind in NON_DEMAND:reasons.append(REASONS[kind])
    if fit['status']=='INCOMPATIBLE':reasons.append('job_incompatible')
    if geo['status']=='GEO_INCOMPATIBLE_CONFIRMED':reasons.append('geo_incompatible')
    if closed:reasons.append('active_request_closed')
    if pool:reasons.append('active_request_unconfirmed')
    if not standing and fresh=='STALE_CONFIRMED':reasons.append('stale_request')
    excluded=bool(reasons)
    requested_recipient=bool(ask and not re.match(r'\s+(?:new )?(?:clients|customers)\b',core[ask.end():],re.I) and WEB.search(core[ask.start():ask.end()+300]+(' '+role if job else '')))
    request=bool(original and not excluded and (requested_recipient or standing) and kind in {'BUYER_DEMAND','INDIVIDUAL_JOB','STANDING_COLLABORATION'})
    if not buyer:reasons.append('buyer_unresolved')
    if not original:reasons.append('source_inaccessible')
    if not standing and fresh=='DATE_UNKNOWN':reasons.append('freshness_unknown')
    if geo['status']=='GEO_UNKNOWN':reasons.append('geo_unknown')
    if not external:reasons.append('contract_unknown')
    if not request and not excluded:reasons.append('active_request_unconfirmed')
    verified_buyer=bool(buyer and identity.get('identity_status')=='verified' and buyer.casefold()==str(identity.get('name','')).casefold() and not recruiter)
    level=0 if not source.get('text') else 1 if not original else 2 if kind=='JOB_AGGREGATION' or (kind=='INDIVIDUAL_JOB' and not verified_buyer) else 3
    if request and verified_buyer:level=4
    stage='DISCOVERED'
    if request:stage='NEEDS_REVIEW' if fit['status']=='COMPATIBLE' else 'PLAUSIBLE'
    checks=result.get('verification') or {}
    if request and not standing and verified_buyer and external and fit['status']=='COMPATIBLE' and geo['status']=='GEO_COMPATIBLE_CONFIRMED' and fresh=='FRESH_CONFIRMED':
        stage='POTENTIAL'
        if checks.get('request_verified') and checks.get('currently_open') and checks.get('status')=='complete':
            stage='READY_TO_CONTACT' if identity.get('contacts') else 'VERIFIED'
    return {'version':VERSION,'page_type':kind,'excluded':excluded,'reasons':list(dict.fromkeys(reasons)),
      'actors':{'publisher':publisher,'buyer':buyer,'buyer_status':'VERIFIED' if verified_buyer else 'ATTRIBUTED_UNVERIFIED' if buyer else 'BUYER_UNKNOWN','supplier':publisher if kind in {'SUPPLIER_OFFER','COMPLETED_PROJECT'} else None,'recruiter':recruiter,'aggregator':publisher if listing else None,'mentioned_entities':list(dict.fromkeys(mentioned))},
      'request_observed':request,'specific_request':request and not standing,'technical_fit':fit,'geography':geo,
      'freshness':{'status':fresh,'published_at':publication,'basis':basis,'age_days':age,'priority':'0-7' if age is not None and 0<=age<=7 else '8-14' if age is not None and 8<=age<=14 else None,'standing_exempt':standing},
      'evidence_level':level,'level':stage,'deep_review_eligible':request or (kind=='UNKNOWN' and original),'original_available':original,
      'evidence':{'url':url,'request_quote':core[max(0,ask.start()-50):ask.end()+250] if ask else None,'counter_quote':completed[0] if completed else None},
      'browser_diagnostic':{'eligible':False,'reason':'no_demonstrated_public_rendering_gap; rebuild browser is scheduled separately'}}


def apply(result, assessment):
    """Add a layer only to a newly evaluated result; never mutate stored history."""
    result['demand_assessment']=assessment
    if assessment['excluded']:
        result.update(state='REJECTED',classification=assessment['reasons'][0],reason='Verifica della domanda: '+', '.join(assessment['reasons']))
        result['priority']='review'
    elif result.get('state') in ('VERIFIED','POTENTIAL') and assessment['level'] not in ('VERIFIED','READY_TO_CONTACT','POTENTIAL'):
        result.update(state='NEEDS_REVIEW',reason='Richiesta da verificare: '+', '.join(assessment['reasons']))
    # Unknowns are preserved; never upgrade a deterministic rejection here.
    return result
