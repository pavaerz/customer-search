"""Observed official-to-ATS links. Tenant paths are boundaries, not identity proof."""
import re
from urllib.parse import urlsplit,urljoin
from sales.db import domain
from sales.extract import parse_page
from sales.content_policy import is_pdf
from .indexed_jobs import same_company_name

# Explicitly supported tenant URL shapes; no arbitrary external navigation.
TENANTS={'inrecruiting.intervieweb.it':r'^/([^/]+)/(?:it|en)/(?:career|jobs?)(?:/|$)',
         'jobs.lever.co':r'^/([^/]+)(?:/|$)', 'apply.workable.com':r'^/([^/]+)(?:/|$)',
         'boards.greenhouse.io':r'^/([^/]+)(?:/|$)'}
def tenant(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.username or p.password:return None
    m=re.match(TENANTS.get(p.hostname,r'(?!)'),p.path,re.I)
    return (p.hostname,m[1].casefold()) if m else None

def observed_links(page,identity):
    if identity.get('identity_status')!='verified' or domain(page['url'])!=domain(identity.get('website') or ''):return []
    out=[]
    for link in parse_page(page)['doc'].links:
        url=urljoin(page['url'],link['url']);anchor=link['text'].strip()
        if not tenant(url) or is_pdf(url) or not re.search(r'posizioni|lavora|career|jobs|candidat|opportunit',anchor+' '+urlsplit(url).path,re.I):continue
        out.append({'url':url,'anchor':anchor,'parent':page['url'],'reason':'Portale candidature collegato dal sito ufficiale; annunci e attualità da verificare.',
          'ats_binding':{'company':identity['name'],'official_url':identity['website'],'origin_url':page['url'],'portal_url':url,'stage':'PORTAL_FOUND'}})
    return out[:2]

def allowed(url,binding):
    same_tenant=bool(tenant(url) and tenant(url)==tenant(binding.get('portal_url','')))
    observed_job=url==binding.get('observed_job_url') and urlsplit(url).scheme=='https' and domain(url)==domain(binding.get('portal_url','')) and bool(re.match(r'^/jobs/[^/]+',urlsplit(url).path))
    return bool((same_tenant or observed_job) and not is_pdf(url) and not re.search(r'/apply|/login|/attachment|/download',urlsplit(url).path,re.I))

def inspect_portal(store,web,first,payload):
    """Recheck official reverse link and per-job organization on every task."""
    from .identity import establish
    from .geography import locate
    from .evaluation import base
    from .inspection import document
    from .qualification import evaluate
    from .context import TECH
    b=payload['ats_binding'];engine=payload['commercial_engine']
    if not allowed(first['url'],b):raise ValueError('ATS: redirect fuori dal portale e dal tenant autorizzati')
    origin=web.get(b['origin_url'])
    if domain(origin['url'])!=domain(b['official_url']):raise ValueError('ATS: origine ufficiale non confermata')
    home=origin if origin['url']==b['official_url'] else web.get(b['official_url'])
    if origin['status']!=200 or home['status']!=200 or domain(home['url'])!=domain(b['official_url']):raise ValueError('ATS: pagina ufficiale non verificabile')
    own=[home,origin] if home is not origin else [origin];identity=establish(own)
    if identity['identity_status']!='verified' or not same_company_name(identity['name'],b['company']):raise ValueError('ATS: identità originaria non confermata')
    observed=observed_links(origin,identity)
    if not any(x['url']==b['portal_url'] for x in observed):raise ValueError('ATS: collegamento ufficiale non più presente')
    if b.get('observed_job_url'):
        portal=web.get(b['portal_url'])
        if not allowed(portal['url'],{k:v for k,v in b.items() if k!='observed_job_url'}) or not any(urljoin(portal['url'],l['url'])==b['observed_job_url'] for l in parse_page(portal)['doc'].links):raise ValueError('ATS: annuncio non collegato dal portale verificato')
    p=parse_page(first);job=p.get('job') or {};org=job.get('hiringOrganization') or {};name=org.get('name') if isinstance(org,dict) else org
    from .attribution import geographic_conflicts
    from sales.organization import classify
    from sales.research_store import ResearchStore
    from sales.targeting import exclusion
    identity['organization']=classify(own,identity)
    geo=geographic_conflicts(locate(own,identity),[],payload.get('allowed_regions'));result=base(engine,identity,first,geo);links=[]
    stages={'portal_found':True,'portal_verified':True,'job_found':bool(job),'job_relevant':False,'request_open':False,
            'origin_company':identity['name'],'official_source':origin['url'],'portal_url':b['portal_url'],'final_url':first['url']}
    suppressed=ResearchStore(store).suppressed(identity)
    excluded=next((exclusion(p) for p in own if exclusion(p)),None)
    if suppressed or excluded:
        result.update(state='REJECTED',classification='excluded',reason=suppressed or excluded['reason'],verification={'status':'complete','scope':'exclusion'})
    elif job and name and same_company_name(identity['name'],name):
        result=evaluate(engine,identity,first,geo)
        stages['job_relevant']=bool(result.get('skills')) and result.get('state')!='REJECTED'
        stages['request_open']=bool(result.get('verification',{}).get('currently_open'))
    else:
        result.update(state='UNVERIFIABLE',classification='ats_portal' if not job else 'ats_employer_mismatch',reason='Portale ufficialmente collegato; manca un annuncio tecnico attribuibile e attualmente aperto.' if not job else 'Organizzazione dell’annuncio diversa o non verificata; nessuna attribuzione al titolare.',verification={'status':'incomplete','scope':'ats_job_attribution'})
    if not job and not suppressed and not excluded:
        for l in p['doc'].links:
            u=urljoin(first['url'],l['url'])
            job_binding={**b,'stage':'JOB_FOUND','observed_job_url':u,'job_parent_url':first['url']}
            if u!=first['url'] and allowed(u,job_binding) and TECH.search(l['text']):
                links.append({'url':u,'anchor':l['text'],'ats_binding':job_binding,'reason':'Ruolo tecnico nel portale collegato; organizzazione e contratto da verificare.'})
    result.update(identity=identity,ats=stages,pages_read=len(own)+1)
    return {'identity':identity,'documents':[document(x,'Fonte originale',x in own) for x in own+[first]],'result':result,'followups':links[:3]}
