"""Read original pages, establish official identity, then classify the request."""
import re
from urllib.parse import urljoin,urlsplit
from sales.db import domain,now
from sales.providers import canonical,blocked
from sales.research_analysis import CompanyWeb as ResearchWeb,document as legacy_document
from sales.extract import parse_page
from sales.organization import classify
from sales.targeting import exclusion
from sales.direct_channels import careers_links,DIRECTORIES,GUIDE_TITLE
from sales.research_store import ResearchStore
from .geography import locate
from sales.content_policy import require_non_pdf,skip_pdf,ExcludedPDF,note_pdf
from .resources import BudgetExceeded
from .evaluation import base
from sales.operation_outcomes import safe_error
from .attribution import identity as identity_from,geographic_conflicts
from .context import source_kind,extract,documents,followups as contextual_links

def document(page,provider='Fonte originale',official=False):
    from sales.db import digest,encode
    require_non_pdf(page)
    d=legacy_document(page,provider,official);d['evidence_channels']=documents(page)
    d['page_title']=parse_page(page)['doc'].title
    d['id']=digest(d['id']+'|commercial2|'+digest(encode(d['evidence_channels'])))
    return d

def inspect(store,payload,check=lambda:None):
    outcome=_inspect(store,payload,check)
    if payload['commercial_engine']!='WEBSITE_REBUILD' and payload.get('demand_version')=='5.1':
        from .demand import assess, source_from_document, apply
        docs=outcome['documents'];result=outcome['result']
        doc=next((d for d in docs if d['url']==result.get('url')),None)
        if doc:apply(result,assess(source_from_document(doc),outcome['identity'],result))
    return outcome


def _inspect(store,payload,check=lambda:None):
    require_non_pdf(payload)
    engine=payload['commercial_engine'];web=ResearchWeb(store,check);url=canonical(payload['url'])
    if blocked(url):raise ValueError('Fonte non accessibile automaticamente: serve una fonte originale autorizzata.')
    reads=0;get=web.get
    def bounded_get(target):
        nonlocal reads
        check()
        if reads>=payload.get('max_reads',6):raise ValueError('Budget di letture per candidato raggiunto: verifica incompleta')
        reads+=1
        require_non_pdf(target)
        from .admission import listing_url
        if listing_url(target):raise ValueError('generic_job_listing: elenco escluso prima della lettura')
        page=get(target);require_non_pdf(page)
        if listing_url(page['url']):raise ValueError('generic_job_listing: destinazione finale non pertinente')
        return page
    web.get=bounded_get
    first=web.get(url);check()
    if first['status']!=200:raise ValueError('Fonte originale HTTP '+str(first['status']))
    if engine!='WEBSITE_REBUILD' and payload.get('demand_version')=='5.1':
        from .demand import assess,source_from_page,apply
        screening=assess(source_from_page(first))
        if screening['excluded']:
            identity={'name':domain(first['url']),'website':None,'identity_status':'unknown','contacts':[]}
            result=base(engine,identity,first,locate([],identity))
            apply(result,screening)
            # Listing links remain separate candidates; never borrow one job's
            # role, salary or contract for the publisher or the whole listing.
            links=contextual_links(first) if screening['page_type']=='JOB_AGGREGATION' else []
            return {'identity':identity,'documents':[document(first)],'result':result,'followups':links[:3]}
    if payload.get('demand_version')=='5.1':
        from .resources import deep_review_slot
        deep_review_slot()
    if payload.get('ats_binding'):
        from .ats import inspect_portal
        return inspect_portal(store,web,first,payload)
    from .entity_scope import profile,unresolved,publication_role
    scope=profile(first)
    if scope['multi_subject']:
        identity=unresolved(first);geo=locate([],identity);result=base(engine,identity,first,geo)
        result.update(state='UNVERIFIABLE',classification='actor_unresolved',source_kind='multi_company_catalog',entity_scope=scope,pages_read=reads,reason='ACTOR_UNRESOLVED: fonte multisoggetto; dati dei singoli espositori o committenti non aggregabili.',verification={'status':'incomplete','scope':'actor_attribution'})
        parsed=parse_page(first)
        if engine=='WEBSITE_REBUILD' and publication_role(parsed['title'],parsed['text']) in ('directory','multi_company_catalog'):
            # A demonstrated directory is excluded from company-site audits;
            # unresolved subjects in other catalogs remain attribution limits.
            result.update(state='REJECTED',classification='excluded',source_kind='directory',
                reason='Portale di imprese: non è il sito del committente da sottoporre ad audit.',
                verification={'status':'complete','scope':'exclusion'})
        return {'identity':identity,'documents':[document(first)],'result':result,'followups':[]}
    # Phase 4.5: inspect the original position before company/contact/browser
    # deepening. A publication date never qualifies an opportunity by itself.
    if engine!='WEBSITE_REBUILD':
        from .job_activity import extract_page,evaluate as activity
        observed=extract_page(first)
        probe={'url':first['url'],'title':parse_page(first)['title'],'job_activity_evidence':observed}
        a=activity(probe,engine,now(),max_age_days=payload.get('max_job_age_days',14))
        if a['category']=='archived' and not a['conflicts']:
            identity=identity_from([first]);geo=locate([first],identity)
            from .qualification import evaluate as qualify_original
            result=qualify_original(engine,identity,first,geo)
            result.update(state='REJECTED',classification='expired' if a['application_status']=='CLOSED_CONFIRMED' else 'job_stale' if a['freshness_status']=='STALE_CONFIRMED' else 'job_geo_incompatible',pages_read=reads,
                          reason='Annuncio non candidabile secondo la fonte: '+', '.join(a['reasons']),activity=a)
            return {'identity':identity,'documents':[document(first)],'result':result,'followups':[]}
    kind=source_kind(first)
    from .target_fit import source_role,EXCLUDED,evaluate as target_fit
    from .request_profile import hosted_request
    parsed_first=parse_page(first)
    hosted_actor=hosted_request(first) if engine!='WEBSITE_REBUILD' and (kind in ('article','institution','aggregator','job_portal') or (domain(first['url']) in __import__('sales.commercial.opportunity_view',fromlist=['PUBLISHERS']).PUBLISHERS) or re.search(r'/annunci/[^/]+\.job',first['url'])) else None
    if hosted_actor:
        owner=identity_from([first]);hosted_actor['publisher_identity']=domain(first['url'])
        actor=hosted_actor['requesting_actor']
        identity={'name':actor,'website':None,'identity_status':'unknown','group':'direct',
                  'contacts':[],'identity_contacts':[],'legal_id':None,'locations':[],'location':None,'country':None,'regions':[],'region':None,'attribution':hosted_actor,
                  'source_url':first['url'],'basis':'Nome dichiarato nella fonte terza; identità ufficiale e contatti non verificati.',
                  'publisher_observation':{'name':owner.get('name'),'scope':'unverified_page_metadata_not_requesting_company'},
                  'name_fields':{'selected_name':actor,'legal_name':None,'page_title':parsed_first['title'],'original_name':actor,'normalization':hosted_actor['basis']}}
        geo=locate([],identity);result=base(engine,identity,first,geo)
        relationship=hosted_actor['relationship']
        incompatible=relationship['employment_relationship']=='EMPLOYEE' or hosted_actor['freshness']['priority_hint'] in ('closed','historical')
        result.update(state='REJECTED' if incompatible else 'UNVERIFIABLE',classification='hosted_incompatible' if incompatible else 'publisher_unresolved',
            source_kind='job_portal',actor_attribution=hosted_actor,requesting_actor=identity['name'],identity=identity,website=None,
            request_type=hosted_actor['request_type'],relationship=relationship,freshness=hosted_actor['freshness'],pages_read=reads,
            reason='Rapporto dipendente esplicito o richiesta chiusa/storica; non commessa freelance attuale.' if incompatible else 'Committente dichiarato nella fonte terza; dominio ufficiale, contratto e attualità da verificare.',
            verification={'status':'complete' if incompatible else 'incomplete','scope':'hosted_request_attribution','request_verified':False,'identity_verified':False})
        blocks=extract(first)
        relevant=[b for b in blocks if b.get('subject')==identity['name'] and b.get('commercial_intent',{}).get('buyer_evidence')]
        if not relevant and hosted_actor['basis']=='original_title_and_company_line':
            bounded=[b for b in blocks if not b.get('subject') and b.get('commercial_intent',{}).get('buyer_evidence')]
            if len(bounded)==1:relevant=[{**bounded[0],'subject':identity['name'],'attribution_basis':hosted_actor['basis']}]
        result['request_blocks']=relevant
        result['evidence']=[e for b in relevant for e in b.get('evidence',[])]
        result['commercial_intent']=relevant[0].get('commercial_intent') if relevant else None
        return {'identity':identity,'documents':[document(first)],'result':result,'followups':[]}
    from .admission import exclusion as metadata_exclusion
    precluded=metadata_exclusion({'url':first['url'],'title':parsed_first['title'],'content':parsed_first['text'][:2000]},engine)
    if precluded:
        identity=unresolved(first,precluded);geo=locate([],identity);result=base(engine,identity,first,geo)
        result.update(state='REJECTED',classification='excluded',source_kind=kind,pages_read=reads,
            reason=precluded,verification={'status':'complete','scope':'source_relevance'})
        return {'identity':identity,'documents':[document(first)],'result':result,'followups':[]}
    commercial_source=source_role(first['url'],parsed_first['title'],parsed_first['text'])
    if engine=='WEBSITE_REBUILD' and commercial_source in EXCLUDED:
        identity=identity_from([first]);geo=locate([],identity);result=base(engine,identity,first,geo)
        result.update(state='REJECTED',classification='target_incompatible',source_kind=commercial_source,
            reason='Fonte incompatibile con il target del rifacimento: '+commercial_source,identity=identity,
            target_fit=target_fit(identity,[first],geo),pages_read=reads,
            verification={'status':'complete','scope':'commercial_target'})
        return {'identity':identity,'documents':[document(first)],'result':result,'followups':[]}

    from .discovery import individual_vacancy
    if kind=='aggregator' and individual_vacancy({'url':first['url'],'title':parse_page(first)['title']}):kind='job_portal'
    from .intent import request_clause
    from .relevance import technical_request
    hosted=kind in ('article','institution') and engine!='WEBSITE_REBUILD' and request_clause(parse_page(first)['text']) and technical_request(parse_page(first)['text'])
    if kind in ('directory','institution','article','portfolio','aggregator'):
        identity=identity_from([first]);geo=locate([],identity)
        result=base(engine,identity,first,geo)
        result.update(state='REJECTED',classification='excluded',source_kind=kind,
                      verification={'status':'complete','scope':'source_relevance'},
                      reason='Fonte '+kind+': non è una richiesta attribuibile al committente.')
        if kind=='article' or hosted:
            from .qualification import evaluate
            result=evaluate(engine,identity,first,geo)
            result['source_kind']=kind
        from .attribution import requesting_identity
        identity=requesting_identity(identity,result,first['url'])
        if result.get('actor_attribution'):result['website']=None
        return {'identity':identity,'documents':[document(first)],'result':result,'followups':[]}
    from .commercial_gate import page_relevance
    relevance=page_relevance(first,engine)
    from .request_profile import collaboration_signal
    generic_invitation=engine=='AGENCIES' and collaboration_signal(parse_page(first)['text'])
    if not relevance['allowed'] and not generic_invitation and payload.get('resolution_stage')!='COMPANY_DOMAIN_CANDIDATE':
        identity=identity_from([first]);geo=locate([first],identity)
        result=base(engine,identity,first,geo)
        result.update(state='REJECTED',classification='seller',source_kind=kind,
                      commercial_relevance=relevance,commercial_intent={'commercial_role':relevance['role']},pages_read=reads,identity=identity,
                      verification={'status':'complete','scope':'commercial_direction'},
                      reason='La fonte offre servizi: nessuna richiesta di competenze esterne attribuibile.')
        return {'identity':identity,'documents':[document(first)],'result':result,'followups':[]}
    home_url=urljoin(first['url'],'/');pages=[first];limits=[];followups=[];failures=[]
    if first['url']!=home_url:
        home=web.get(home_url);check()
        if home['status']!=200:raise ValueError('Dominio ufficiale non verificabile')
        pages.insert(0,home)
    host=domain(home_url)
    # ATS identity must be resolved, never assign the platform to the hiring company.
    pp=parse_page(first);employer=(pp.get('job') or {}).get('hiringOrganization') or {}
    employer_url=employer.get('sameAs') or employer.get('url') if isinstance(employer,dict) else None
    if kind=='job_portal' and not employer_url:
        # An attributable third-party lead remains visible. The coordinator
        # can resolve its named employer; the publisher is never that employer.
        identity=identity_from([first]);identity['identity_status']='unknown'
        geo=locate([],identity);result=base(engine,identity,first,geo)
        from .indexed_jobs import parse_indexed_job
        result.update(state='UNVERIFIABLE',classification='publisher_unresolved',source_kind='job_portal',
                      reason='Annuncio individuale di terzi: committente e fonte ufficiale da verificare.',
                      indexed_job=parse_indexed_job({'url':first['url'],'title':pp['title'],'content':pp['text']}),
                      verification={'status':'incomplete','scope':'employer_attribution'})
        return {'identity':identity,'documents':[document(first)],'result':result,'followups':[]}
    if employer_url and isinstance(employer_url,str) and domain(employer_url)!=host:
        candidate=web.get(canonical(employer_url));check()
        declared=str(employer.get('name') or '').casefold()
        actual=identity_from([candidate])
        if candidate['status']!=200 or not declared or declared!=str(actual.get('name','')).casefold():raise ValueError('Committente dell’annuncio non collegato al sito ufficiale')
        # Require a reverse link from the official company to this ATS/vacancy.
        if not any(domain(urljoin(candidate['url'],l['url']))==domain(url) for l in parse_page(candidate)['doc'].links):raise ValueError('Collegamento ufficiale al portale candidature non verificato')
        pages=[candidate,first];host=domain(candidate['url'])
    links=[]
    for p in pages:
        for l in parse_page(p)['doc'].links:
            href=urljoin(p['url'],l['url'])
            if skip_pdf(href):continue
            if domain(href)==host and href.startswith(('http://','https://')) and re.search(r'contatt|contact|chi.siamo|about|azienda|company',l['text']+' '+urlsplit(href).path,re.I):links.append(href)
        followups+=contextual_links(p)
    for href in list(dict.fromkeys(links))[:2]:
        if engine=='WEBSITE_REBUILD' and identity_from([p for p in pages if domain(p['url'])==host]).get('identity_status')=='verified':break
        if href in {p['url'] for p in pages}:continue
        check()
        try:
            p=web.get(href)
            if p['status']==200:pages.append(p)
            else:
                limits.append('Pagina identità HTTP '+str(p['status']))
                failures.append({'url':href,'status':p['status']})
        except (InterruptedError,BudgetExceeded):raise
        except ExcludedPDF as exc:note_pdf(exc.url)
        except Exception as exc:limits.append(safe_error(exc))
    own=[p for p in pages if domain(p['url'])==host];identity=identity_from(own)
    blocks=extract(first)
    if kind=='job_portal' and host==domain(first['url']):identity=identity_from([first])
    request_geo_text=' '.join(b['text'] for b in blocks) if payload.get('search_version')=='5.0' else pp['text']
    geo=geographic_conflicts(locate(own+[first],identity,request_geo_text),blocks,payload.get('allowed_regions'))
    identity['region']=geo['regions'][0] if geo['regions'] else identity.get('region')
    identity['regions']=geo['regions'];identity['organization']=classify(own,identity)
    if payload.get('resolution_company'):
        from .indexed_jobs import same_company_name
        if not same_company_name(payload['resolution_company'],identity.get('name')):
            identity['identity_status']='unknown';identity['basis']='Committente indicizzato e proprietario del dominio non collegati.'
        from .evaluation import skills
        expected_skills=set(skills(payload.get('resolution_role','')))
        actual_skills=set(skills(' '.join(b['text'] for b in blocks)))
        if payload.get('resolution_stage')!='COMPANY_DOMAIN_CANDIDATE' and (not expected_skills or not expected_skills&actual_skills):
            identity['identity_status']='unknown';identity['basis']='Il ruolo della fonte originale non coincide con quello da risolvere.'
        identity['resolution']={'declared_actor':payload['resolution_company'],'publisher_source':payload.get('resolution_source'),
            'candidate_domain':home_url,'official_domain_verified':identity['identity_status']=='verified','role_verified':bool(expected_skills&actual_skills),
            'contact_verified':identity['identity_status']=='verified' and bool(identity.get('contacts')),'scope':'identity_does_not_verify_original_request'}
    docs=[document(p,'Fonte originale',domain(p['url'])==host) for p in pages]
    result=base(engine,identity,first,geo)
    rejected=ResearchStore(store).suppressed(identity)
    finding=next((x for p in own if (x:=exclusion(p,allow_legal_spa=engine=='WEBSITE_REBUILD'))),None)
    if finding:rejected=finding['reason']
    if identity['organization']['category'] in ('public_body','directory','editorial_source'):rejected='Fonte istituzionale, editoriale o directory: non è il committente cercato.'
    if GUIDE_TITLE.search(pp['title'] or ''):rejected='Guida informativa, non richiesta commerciale.'
    if rejected:result.update(state='REJECTED',classification='excluded',reason=rejected,verification={'status':'complete','scope':'exclusion'})
    elif engine=='WEBSITE_REBUILD':
        from . import rebuild,browser
        from .resources import stage_plan
        allocation=stage_plan(payload)
        fit=target_fit(identity,own,geo)
        # Browser reads the relevant rendered paths itself. Fetching the same
        # catalogue first spends its headroom before any rendered observation.
        screening=rebuild.screen(pages,failures,limits)
        selection=rebuild.browser_selection(identity,screening,{**payload,'geography_eligible':geo.get('eligible',False),'target_fit':fit})
        screening['browser_selection']=selection
        screening['resource_plan']=allocation
        screening['target_fit']=fit
        from .audit_memory import reusable
        report=reusable(store,identity,docs)
        reused=report is not None
        if not reused and selection['code']=='budget_deferred':
            resource='browser_runs' if not selection['resources']['browser_runs'] else 'http_reads'
            report={'completed':False,'executed':False,'outcome':'budget_deferred','findings':[],'pages':[],
                    'limits':['Audit non avviato: risorse disponibili esaurite. Screening conservato.'],
                    'deferred_resource':resource,'resources_closed':True}
        if selection['selected'] and not reused:
            # One representative offer page only after admission to the audit;
            # leave the planned browser headroom intact. No arbitrary crawling.
            if allocation['optional_http_allowance']>=2 and reads<payload.get('max_reads',6):
                offer=[]
                for p in own:
                    for l in parse_page(p)['doc'].links:
                        href=urljoin(p['url'],l['url'])
                        if domain(href)==host and not skip_pdf(href) and re.search(r'prodott|serviz|catalog',l['text'],re.I) and href not in {x['url'] for x in pages}:offer.append(href)
                if offer:
                    try:
                        extra=web.get(offer[0])
                        if extra['status']==200:pages.append(extra)
                        else:failures.append({'url':offer[0],'status':extra['status']})
                    except (InterruptedError,BudgetExceeded):raise
                    except ExcludedPDF as exc:note_pdf(exc.url)
                    except Exception as exc:limits.append(safe_error(exc))
                    screening={**rebuild.screen(pages,failures,limits),'browser_selection':selection,'resource_plan':allocation,'target_fit':fit}
            try:report=browser.review(store,pages,check,payload.get('max_browser_pages',3),limits={**payload,'browser_advanced':True,'browser_audit_level':payload.get('browser_audit_level','STANDARD')})
            except BudgetExceeded as exc:
                if exc.resource not in ('browser_runs','http_reads'):raise
                # A reserved HTTP task is still useful after the browser quota.
                # Persist its real evidence and defer only the missing phase.
                report={'completed':False,'executed':False,'outcome':'budget_deferred',
                        'level':'HTTP','findings':[],'pages':[],'diagnostics':[],
                        'limits':['Quota '+('letture HTTP' if exc.resource=='http_reads' else 'browser')+' esaurita; screening conservato.'],
                        'deferred_resource':exc.resource,'resources_closed':True}
        result=rebuild.evaluate(identity,pages,geo,screening,report)
        result['target_fit']=fit
        if not fit['audit_allowed']:
            result.update(state='REJECTED' if fit['status']=='NOT_SUITABLE' else 'NEEDS_REVIEW' if fit['status']=='LOW_PRIORITY' else 'UNVERIFIABLE',classification='target_not_selected',reason='Audit non selezionato: '+'; '.join(fit['reasons']))
        docs=[document(p,'Sito aziendale',domain(p['url'])==host) for p in pages]
    else:
        from . import freelance,agencies,startups
        evaluator={'FREELANCE':freelance.evaluate,'AGENCIES':agencies.evaluate,'STARTUPS':startups.evaluate}
        if engine not in evaluator:raise ValueError('Motore non ancora implementato')
        result=evaluator[engine](identity,first,geo)
    from .request_profile import freshness,agency_signal,startup_type
    result.setdefault('freshness',freshness(result.get('published_at'),verified=bool(result.get('published_at')),text=pp['text']))
    if engine=='AGENCIES':result['agency_signal']=agency_signal(pp['text'])
    if engine=='STARTUPS':result['request_type']=startup_type(pp['text'])
    result['limits']+=limits
    result['commercial_relevance']=relevance
    result['pages_read']=reads
    result['source_kind']=kind
    result['attribution']=identity.get('attribution',{})
    if result.get('route_to')=='AGENCIES':
        followups.insert(0,{'url':first['url'],'engine':'AGENCIES','parent':first['url'],'reason':'Disponibilità continuativa dichiarata: instradamento al motore partner'})
    # Bounded first-party links, no guessed jobs paths or editorial crawling.
    followups+=contextual_links(first)
    from .ats import observed_links
    for page in own:followups=observed_links(page,identity)+followups
    chosen={}
    for link in followups:
        if skip_pdf(link['url']):continue
        if link.get('engine') or link['url'] not in {p['url'] for p in pages}:chosen.setdefault((link.get('engine',engine),link['url']),link)
    if result.get('actor_attribution'):
        from .attribution import requesting_identity
        identity=requesting_identity(identity,result,first['url'])
        result['website']=None
    result['result_type']='OFFICIAL_PROJECT' if result.get('actor_role')=='PROJECT' and identity.get('identity_status')=='verified' else 'OFFICIAL_COMPANY' if identity.get('identity_status')=='verified' else 'UNKNOWN'
    result['identity']=identity
    # Add scope to cited spans, never turn an unresolved subject into a fact.
    actor=(result.get('actor_attribution') or {}).get('requesting_actor') or identity.get('name')
    for proof in result.get('evidence',[]):
        proof['actor']=actor
        proof['actor_role']='SOURCE_OWNER' if proof.get('kind')=='measurement' else 'REQUESTING_COMPANY'
        proof['attribution_status']='verified_owner' if identity.get('identity_status')=='verified' and not result.get('actor_attribution') else 'unresolved'
        proof['attribution_scope']='owned_site_measurement' if proof.get('kind')=='measurement' else result.get('selected_block') or 'source_section'
    from .discovery import followup_allowed
    return {'identity':identity,'documents':docs,'result':result,'followups':[l for l in chosen.values() if followup_allowed(result,l)][:3]}
