"""Cheap source intent/routing. Search snippets are never qualification proof."""
import re
from urllib.parse import urlsplit
from sales.db import domain
from sales.direct_channels import DOCUMENT_PATH,DIRECTORIES,INSTITUTIONS,GUIDE_TITLE
from .context import CAREERS,TECH


def classify(item):
    url=str(item.get('url') or '');host=domain(url);path=urlsplit(url).path
    title=str(item.get('title') or '');text=title+' '+str(item.get('content') or '')
    from .relevance import preflight_type
    pretype,_=preflight_type(item)
    if pretype=='EDITORIAL':return 'article'
    if pretype=='INSTITUTIONAL':return 'institution'
    if DOCUMENT_PATH.search(url):return 'document'
    if re.search(r'/public/[a-z]{2}/azienda/|/Beni_di_consumo/[^/]+\.php$',path,re.I):return 'directory'
    from .intent import source_intent
    structural=source_intent(url,title,str(item.get('content') or ''))
    if structural:return {'DIRECTORY':'directory','EDITORIAL':'article','AGGREGATOR':'aggregator'}[structural]
    if host.endswith('linkedin.com'):return 'inaccessible'
    if any(host==d or host.endswith('.'+d) for d in DIRECTORIES+('pmilombarde.it','houzz.it','virgilio.it')):return 'directory'
    if any(host==d or host.endswith('.'+d) for d in INSTITUTIONS) or re.search(r'portaleappalti|/PortaleAppalti/|\.gov\.it$',url,re.I):return 'institution'
    if re.search(r'/(?:blog|news|notizie|portfolio)/',path) or GUIDE_TITLE.search(title):return 'article'
    if re.search(r'/(?:annunci|jobs)/',path) and host in ('apriamoinsieme.it','careerjet.it','cercolavoro.com','it.whatjobs.com'):return 'job_portal'
    if CAREERS.search(path+' '+title):return 'official_job_hint'
    if re.search(r'\b(?:offro|realizzazione siti|creazione siti|servizi di sviluppo)\b',text,re.I):return 'service_seller'
    return 'company_site_hint'


def linkedin_resolution(item):
    """Use title/URL hints only to resolve a lawful original source."""
    from .indexed_jobs import resolution
    return resolution(item)

# Phase 3A: normalized discovery records, independent of qualification.
from sales.providers import canonical
from sales.db import now,digest
from sales.content_policy import is_pdf

SOCIALS=('instagram.com','linkedin.com')

def source(url):
    host=domain(url)
    return next((s.split('.')[0] for s in SOCIALS if host==s or host.endswith('.'+s)),'web')

def normalize(item,origin=None):
    origin=origin or {};url=item.get('url') or item.get('link') or ''
    try:clean=canonical(url)
    except (ValueError,TypeError):clean=None
    return {**item,'original_url':url,'url':clean or url,'canonical_url':clean,
            'title':str(item.get('title') or ''),'snippet':str(item.get('content') or item.get('snippet') or ''),
            'query':origin.get('query'),'executed_query':(__import__('sales.content_policy',fromlist=['search_query']).search_query(origin['query']) if origin.get('provider')=='serper' and origin.get('query') else origin.get('query')),'provider':origin.get('provider'),'source':source(url),
            'subject':item.get('subject'),'timestamp':now(),'origin':origin}

def _assess(item,engine,origin=None):
    r=normalize(item,origin);url=r['url'];host=domain(url);path=urlsplit(url).path
    text=r['title']+' '+r['snippet'];kind=classify({**r,'content':r['snippet']})
    r.update(source_kind=kind,decision='admit',priority=30,reason='Indizi insufficienti: candidato a bassa priorità.',accessibility='not_checked')
    from .intent import classify_block
    intent=classify_block(text,url=url,title=r['title'],source_kind=kind)
    r['commercial_intent']=intent
    from .relevance import preflight_type,technical_request,NON_WEB_ROLE
    ptype,pbasis=preflight_type(r)
    mapping={'directory':'DIRECTORY','aggregator':'AGGREGATOR','article':'EDITORIAL','institution':'INSTITUTIONAL','job_portal':'JOB_POSTING'}
    r['result_type']=mapping.get(kind,ptype)
    r['preflight']={'level':'A','basis':pbasis,'identity_verified':False,'http_reads':0,'ai_calls':0}
    if r['result_type']=='UNKNOWN' and intent.get('buyer_evidence'):
        r['result_type']='AGENCY_COLLABORATION' if engine=='AGENCIES' else 'DIRECT_REQUEST'
    def reject(reason):r.update(decision='exclude',priority=0,reason=reason);return r
    from .job_activity import early_exclusion
    from datetime import datetime,timezone
    activity_filter=early_exclusion({**r,'job_activity_evidence':item.get('job_activity_evidence',[])},engine,datetime.now(timezone.utc),item.get('max_job_age_days',14))
    if activity_filter:
        r['job_activity']=activity_filter['activity']
        return reject(activity_filter['reason'])
    if is_pdf(r):return reject('excluded_pdf')
    if item.get('ats_binding'):
        from .ats import allowed
        if not allowed(url,item['ats_binding']):return reject('ats_tenant_mismatch')
        r.update(priority=70,reason='Portale collegato da un sito ufficiale: verificare tenant, organizzazione e annuncio.',admission_stage='ATS_LINK')
        return r
    from .admission import exclusion
    if reason:=exclusion(r,engine):return reject(reason)
    from .target_fit import source_role,EXCLUDED
    commercial_source=source_role(url,r['title'],r['snippet'])
    r['commercial_source_role']=commercial_source
    if engine=='WEBSITE_REBUILD' and commercial_source in EXCLUDED:return reject('incompatible_target:'+commercial_source)
    from .request_profile import freshness,agency_signal,startup_type
    r['freshness']=freshness(r.get('date'),verified=False,text=r['title'],index_hint=True)
    if engine=='AGENCIES':r['agency_signal']=agency_signal(text)
    if engine=='STARTUPS':r['request_type']=startup_type(text)
    from .indexed_jobs import parse_indexed_job
    job_hint=parse_indexed_job(r)
    # Employment is still not a commercial commission. A relevant individual
    # job may nevertheless reach the separate manual recommendation projection.
    employee_hint=(engine!='WEBSITE_REBUILD' and job_hint.get('contract_hint')=='employment'
                   and job_hint.get('compatibility_reason')=='Rapporto dipendente in presenza.')
    if job_hint['commercial_compatibility'] is False and not employee_hint:
        r['indexed_job']=job_hint
        return reject('incompatible_requested_role' if 'embedded/firmware' in job_hint['compatibility_reason'] else 'incompatible_primary_job')
    if re.search(r'/members(?:/|$)',path,re.I):return reject('community_member_directory')
    if not r['canonical_url']:return reject('invalid_url')
    if host=='facebook.com' or host.endswith('.facebook.com') or host in ('fb.com','fb.watch'):return reject('excluded_facebook')
    if DOCUMENT_PATH.search(url):return reject('excluded_document')
    if re.search(r'/(?:privacy[-_/]?policy|privacy|cookie-policy|unsubscribe|mappa-sito|sitemap)(?:/|$)',path,re.I):return reject('non_commercial_page')
    if re.search(r'\.(?:gov\.it)(?:$)',host) or host=='regione.veneto.it' or host.endswith('.regione.veneto.it'):return reject('institution')
    if re.search(r'directory|elenco.aziende|lista.aziende|database.aziende|ricerca.aziende',path+' '+r['title'],re.I):return reject('directory')
    # An individual third-party vacancy can identify a client; a generic
    # listing cannot. Never identify its publisher as the hiring company.
    if kind=='aggregator' and individual_vacancy(r):
        kind='job_portal';r['source_kind']=kind
    hosted_request=(engine!='WEBSITE_REBUILD' and kind in ('article','institution') and bool(intent.get('buyer_evidence')) and technical_request(text))
    if kind in ('directory','institution','article','aggregator') and not hosted_request:return reject(kind)
    if hosted_request:r.update(result_type='DIRECT_REQUEST',priority=60,reason='Richiesta tecnica su fonte terza; committente da identificare separatamente dall’editore.')
    if item.get('resolution_stage')=='COMPANY_DOMAIN_CANDIDATE' and item.get('resolution_company'):
        from .indexed_jobs import resolution_continuity
        continuity=resolution_continuity(item,r)
        if continuity['status']!='SUPPORTED':return reject(continuity['reason'])
        r.update(priority=65,admission_stage='COMPANY_DOMAIN_CANDIDATE',reason='Possibile dominio del soggetto cercato: verificare identità e pagina collaborazioni, nessuna richiesta presunta.')
        return r
    if engine=='AGENCIES' and pbasis=='non_digital_agency':return reject('non_digital_agency')
    if engine=='AGENCIES':
        from .request_profile import agency_supplier_pitch
        if agency_supplier_pitch(text):return reject('agency_supplier_not_buyer')
        from .intent import request_clause
        clause=request_clause(text) or ''
        directed=bool((intent.get('buyer_evidence') and intent.get('technical') and re.search(r'sviluppator|web designer|frontend|developer',text,re.I)) or technical_request(clause) or (technical_request(text) and re.search(r'collaboriamo con|sviluppatori web e team tech|partner tecnic|sviluppatori freelance|cerchiamo (?:spesso )?(?:figure )?freelance',text,re.I)))
        from .request_profile import collaboration_signal
        if not directed and collaboration_signal(text) and kind in ('official_job_hint','company_site_hint'):
            r.update(priority=40,admission_stage='COLLABORATION_SIGNAL',reason='Invito a professionisti esterni: verificare soggetto, competenze e disponibilità nella fonte originale.',technical_request_verified=False,accessibility='not_checked')
            return r
        if not directed:return reject('technical_collaboration_not_attributed')
    if engine!='WEBSITE_REBUILD' and not technical_request(text) and NON_WEB_ROLE.search(text):return reject('incompatible_requested_role')
    if engine!='WEBSITE_REBUILD' and re.search(r'credito|creditiz|mediazione|avvocat|studio.legale|associazion|formazione|viaggi|turismo|fondazione',text+' '+host,re.I) and not (TECH.search(text) and re.search(r'cerchiamo sviluppator|freelance|partita IVA',text,re.I)):return reject('incompatible_subject')
    if engine!='WEBSITE_REBUILD' and re.search(r'formazione|corsi di|fondi europei|finanziament|incentivi|premio.startup|podcast|episodi|migliori startup|giustizia|mediatore|architetto|journalist|giornalista|offerte.internet|natale|viaggi|turismo',text+' '+path,re.I) and not (TECH.search(text) and re.search(r'freelance|partita IVA|cerchiamo sviluppator',text,re.I)):return reject('non_commercial_intent')
    web_seller=bool(re.search(r'wordpress|woocommerce|web[ -]?(?:design|develop)|sviluppo (?:web|software)|(?:siti|applicazioni|piattaforme) web|realizzazione siti|creazione siti',text,re.I))
    if re.search(r'offriamo (?:sviluppatori|servizi)|realizziamo|realizzazione siti|creazione siti|sviluppo.*su misura|web[ -]app[ -]su[ -]misura|/servizi/',text+' '+path,re.I) and intent['intent'] not in ('BUYER_INTENT','FREELANCE_OPPORTUNITY','JOB_OFFER') and not CAREERS.search(path+' '+text) and (engine!='WEBSITE_REBUILD' or web_seller):return reject('service_seller')
    if r['source']=='instagram':
        kind='instagram_post' if re.match(r'^/p/[^/]+/?$',path) else 'instagram_reel' if re.match(r'^/reel/[^/]+/?$',path) else 'instagram_hashtag' if '/explore/' in path else 'instagram_profile'
        r['source_kind']=kind
        if kind in ('instagram_hashtag','instagram_profile'):return reject('social_listing_or_profile')
    elif r['source']=='linkedin':
        kind='linkedin_job' if re.search(r'/jobs/view/[^/]+',path) else 'linkedin_post' if re.search(r'/posts/|/feed/update/',path) else 'linkedin_company' if '/company/' in path else 'linkedin_listing'
        r['source_kind']=kind
        if kind not in ('linkedin_job','linkedin_post'):return reject('social_listing_or_profile')
    # A portal's list is neither its own request nor a known hiring company.
    portals=('careerjet','whatjobs','jobslooker','trovolavoro','talent-soft','talentsoft','apriamoinsieme','datapizza')
    if any(p in host for p in portals):
        individual=bool(re.search(r'/jobad/\d+|/annunci/[^/]+/\d+|/jobs/view/|/offerta/|/offerte-lavoro/.+-',path))
        if not individual and not individual_vacancy(r):r['source_kind']='aggregator';return reject('generic_job_listing')
        r['source_kind']='job_portal'
    from .context import EXTERNAL,EMPLOYEE
    tech=technical_request(text);demand=intent['intent'] in ('BUYER_INTENT','FREELANCE_OPPORTUNITY','JOB_OFFER');external=bool(EXTERNAL.search(text))
    if (intent['intent']=='SELLER_INTENT' or intent.get('commercial_role') in ('SELLER','PARTNERSHIP_SELLER')) and (engine!='WEBSITE_REBUILD' or web_seller):return reject('seller_intent')
    if EMPLOYEE.search(text) and not external:
        from .recommendations import assess as recommend
        from datetime import datetime,timezone
        candidate={'id':0,'engine':engine,'state':'UNVERIFIABLE','body':{'engine':engine,'url':url,'discovery':r,'classification':'metadata_only'}}
        suggestion=recommend(candidate,datetime.now(timezone.utc))
        if suggestion['recommended']:
            r.update(priority=30,recommendation_only=True,reason='Annuncio tecnico per rapporto dipendente: conservato per revisione manuale, non come commessa freelance.',accessibility='indexed_only' if r['source']!='web' else 'not_checked')
            return r
        return reject('employment_only')
    if r['source']=='linkedin':
        from .indexed_jobs import parse_indexed_job
        r['indexed_job']=parse_indexed_job(r)
        # Preserve an attributable individual vacancy as a resolution lead;
        # contract/date remain unknown even when title mentions freelance.
        if r['source_kind']=='linkedin_job' and r['indexed_job']['company_candidate']:
            r.update(priority=25,accessibility='indexed_only',reason='Annuncio individuale indicizzato: azienda e ruolo candidati, fonte originale da verificare.')
            return r
    if r['source']!='web':
        r['accessibility']='indexed_only'
        if not tech or not demand:
            # A named individual vacancy without snippet can still be resolved.
            if not text.strip() and r['source_kind']=='linkedin_job':return r
            if tech and external:
                r.update(priority=25,reason='Ruolo esterno plausibile nello snippet, ma richiesta non attribuibile: indizio incompleto.')
                return r
            return reject('no_indexed_request')
        r.update(priority=85 if external else 55,reason='Richiesta tecnica indicizzata; testo originale, autore e attualità da verificare.')
    elif tech and demand:
        r.update(priority=90 if external else 60,reason='Richiesta tecnica e contesto del committente presenti; da verificare sulla fonte.')
    elif CAREERS.search(path+' '+text):
        r.update(priority=40,reason='Pagina candidature: ruolo tecnico e natura esterna ancora da verificare.')
    elif engine=='WEBSITE_REBUILD':
        if kind=='service_seller':return reject('service_seller')
        r.update(priority=55 if re.search(r'produzion|produttor|manufacturer|industr|artigian|s\.?r\.?l',text,re.I) else 35,reason='Possibile sito aziendale: identità e bisogno richiedono screening e prove tecniche.')
    elif text.strip() and not tech:return reject('no_technical_context')
    if r['freshness']['priority_hint']=='recent':r['priority']=min(95,r['priority']+5)
    r['investigation_value']={'basis':'observable_metadata_not_sales_probability','priority':r['priority'],'missing':['official_identity','original_request' if engine!='WEBSITE_REBUILD' else 'measured_defects'],'next_step':'resolve_original' if r['accessibility']=='indexed_only' else 'targeted_read'}
    return r

def assess(item,engine,origin=None):
    r=_assess(item,engine,origin)
    from .source_intelligence import describe,project_request
    # Project briefs need not advertise a job title. Admission alone cannot
    # supply identity, contract, budget or current availability to qualification.
    if engine!='WEBSITE_REBUILD' and r['decision']=='exclude' and r['reason'] in ('no_technical_context','technical_collaboration_not_attributed') and project_request(r):
        r.update(decision='admit',priority=65,reason='Richiesta di progetto plausibile; fonte, committente e ambito da verificare.',result_type='DIRECT_REQUEST',admission_stage='PROJECT_BRIEF')
    r['source_intelligence']=describe(r)
    r['admission_category']='EXCLUDED' if r['decision']=='exclude' else 'OUTBOUND_PROSPECT' if engine=='WEBSITE_REBUILD' else 'EMPLOYMENT_SEPARATE' if r.get('recommendation_only') else 'PLAUSIBLE_REQUEST' if r.get('commercial_intent',{}).get('buyer_evidence') or project_request(r) else 'UNCERTAIN_REVIEW'
    return r

def followup_allowed(result,link):
    from .admission import listing_url
    if link.get('ats_binding'):
        from .ats import allowed
        return result.get('identity',{}).get('identity_status')=='verified' and allowed(link.get('url',''),link['ats_binding'])
    if listing_url(link.get('url','')):return False
    demand=result.get('demand_assessment') or {}
    if demand.get('page_type')=='JOB_AGGREGATION':
        from .demand import technical_fit
        path=urlsplit(link.get('url','')).path
        return bool(link.get('recruitment_context') and not is_pdf(link.get('url',''))
                    and re.search(r'/(?:jobs?|projects|offer)/[^/]+',path)
                    and technical_fit(link.get('anchor',''),'')['status']=='COMPATIBLE')
    if demand.get('excluded'):return False
    if result.get('classification')=='excluded':return False
    identity=result.get('identity',{})
    resolved=identity.get('resolution') or {}
    if resolved.get('official_domain_verified') and identity.get('identity_status')=='verified':
        # A supplier homepage can resolve an employer without advertising the
        # vacancy itself. Only follow its own observed recruitment links.
        if not is_pdf(link.get('url','')) and domain(link.get('url',''))==domain(identity.get('website') or '') and CAREERS.search(urlsplit(link.get('url','')).path+' '+link.get('anchor','')):
            return True
    role=result.get('commercial_intent',{}).get('commercial_role') if result.get('commercial_intent') else None
    if role in ('SELLER','PARTNERSHIP_SELLER'):return False
    if result.get('source_kind') in ('directory','institution','article','aggregator','portfolio'):return False
    if link.get('engine')=='AGENCIES' and result.get('route_to')=='AGENCIES':return True
    url=link['url'];path=urlsplit(url).path;anchor=link.get('anchor','')
    if is_pdf(url):return False
    if re.search(r'latest_jobs|/apply/?$|my-basket|all-rss|list-of-all|domiciliazioni|apri-una-nuova-sede',path,re.I):return False
    identity=result.get('identity',{})
    # Publishers and unrelated sectors do not create a fresh branch just by
    # offering "careers" in their footer.
    if result.get('engine')=='WEBSITE_REBUILD':return False
    org=identity.get('organization',{}).get('category')
    technical_subject=identity.get('group')=='agencies' or org=='digital_agency' or bool(TECH.search(str(identity.get('description') or '')+' '+str(identity.get('name') or '')))
    if not technical_subject and not result.get('request_blocks'):return False
    if result.get('source_kind') in ('job_portal','careers') and not TECH.search(anchor) and result.get('classification')!='no_collaboration':return False
    # Technical service links are not vacancies, even under a careers page.
    local=link.get('anchor_context','')
    from .intent import request_clause
    recruitment=bool(CAREERS.search(path+' '+anchor) or (local and request_clause(local)))
    return bool(recruitment and (CAREERS.search(path+' '+anchor) or TECH.search(anchor)))


def individual_vacancy(item):
    """A bounded third-party job page may be investigated without trusting it."""
    path=urlsplit(item.get('url','')).path
    individual=bool(re.search(r'/jobs/view/[^/]+|/jobad/\d+|/(?:offerta|vacancy)/[^/]+|/annunci/[^/]+/\d+|/annunci/[^/]+\.job',path,re.I))
    text=str(item.get('title',''))+' '+str(item.get('snippet') or item.get('content') or '')
    return bool(individual and TECH.search(text))
