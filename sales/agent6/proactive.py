"""Protected company discovery → website audit → commercial interpretation.

The proactive route never invents an explicit request. It stores checkpoints
after every acquired page and browser result; a resumed task reuses them.
"""
import json,re
from urllib.parse import urljoin
from sales.db import now,encode,digest,domain
from sales.extract import parse_page
from sales.research_analysis import CompanyWeb,identity_from
from sales.commercial.inspection import document
from sales.commercial.resources import BudgetExceeded
from sales.commercial import target_fit
from sales.operation_outcomes import safe_error
from . import website_audit,website_review,memory,budget,ai,qualification
from .source_access import require_content

STRATEGY='official_company_sector_region'
ACTIVITY=re.compile(r'produzion|produttor|manifattur|industr|metalmeccan|artigian|arredament|ediliz|impiant|logistic|hotel|alberg|turismo|commercio|catalog|servizi b2b|aziend|impres|\bs\.?r\.?l\.?\b',re.I)


def is_query(p,flow):return flow=='AZIENDE' and p.get('strategy')==STRATEGY


def query_policy(q,regions=None):
    from .commercial_policy import positive_query,bounded_boolean_query,query_branches
    from sales.research_rules import region_of,ALLOWED_REGIONS
    text=positive_query(q.get('query',''))
    if len(text)>160 or len(re.findall(r'\bOR\b',text))>2:return {'allowed':False,'reason':'proactive_query_overloaded'}
    if not bounded_boolean_query(text):return {'allowed':False,'reason':'ungrouped_or_or_unbalanced_query'}
    try:branches=query_branches(text)
    except ValueError as exc:return {'allowed':False,'reason':str(exc)}
    for branch in branches:
        if not ACTIVITY.search(branch) or not re.search(r'sito|ufficial|prodott|serviz|catalog|produzion|produttor|lavorazion|costruzion|installazion',branch,re.I):
            return {'allowed':False,'reason':'missing_company_activity_discovery_scope'}
        if re.search(r'elenco|directory|paginegialle|migliori|top \d|portfolio|agenzi[ae] web',branch,re.I):
            return {'allowed':False,'reason':'proactive_not_official_company_search'}
        region=region_of(branch)
        if region not in ALLOWED_REGIONS:return {'allowed':False,'reason':'proactive_territory_missing'}
        if regions is not None and region not in regions:return {'allowed':False,'reason':'proactive_territory_outside_campaign'}
    return {'allowed':True,'intent':'proactive_company','reason':'verify_official_activity_then_audit_no_declared_demand'}


def candidate_allowed(item):
    role=target_fit.source_role(item.get('url',''),item.get('title',''),item.get('content',item.get('snippet','')))
    return role not in target_fit.EXCLUDED or role in ('directory','multi_company_catalog')


def run(worker,task,check):
    p=task['payload'];flow=task['strategy'];store=worker.store
    checkpoint=p.get('website_checkpoint') or {'pages':[],'attempts':[]}
    def save():
        check()
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not worker.active(c):raise InterruptedError('Campagna sospesa')
            row=c.execute('SELECT payload FROM research_tasks WHERE id=? AND campaign_id=?',(task['id'],worker.cid)).fetchone()
            if row:c.execute('UPDATE research_tasks SET payload=?,updated_at=? WHERE id=?',
                (encode({**json.loads(row[0]),'website_checkpoint':checkpoint}),now(),task['id']))
    def fetch(url,purpose):
        check()
        existing=next((x for x in checkpoint['pages'] if x.get('requested_url',x['url'])==url),None)
        if existing:return existing
        if any(a['url']==url for a in checkpoint['attempts']):return None
        if len(checkpoint['attempts'])>=worker.budget['max_reads']:return None
        try:
            page=CompanyWeb(store,check).get(url);check()
            kept={k:page[k] for k in ('url','status','html','checked_at','content_type','redirect_chain','acquisition_requested_url') if k in page}
            kept.update(requested_url=url,purpose=purpose)
            # Non-200 responses are saved as measured errors, not read content.
            if page['status']==200:require_content(page)
            checkpoint['pages'].append(kept)
            checkpoint['attempts'].append({'url':url,'purpose':purpose,'status':page['status'],'checked_at':page.get('checked_at')})
            save();return kept
        except (InterruptedError,BudgetExceeded):raise
        except Exception as exc:
            checkpoint['attempts'].append({'url':url,'purpose':purpose,'error':safe_error(exc),'checked_at':now()});save()
            return None
    first=fetch(p['url'],'discovery')
    first_role=target_fit.source_role(first['url'],parse_page(first)['title'],parse_page(first)['text']) if first and first.get('status')==200 else 'unknown'
    source_only=first_role in ('directory','multi_company_catalog','training_provider','institution')
    if first and first_role in ('directory','multi_company_catalog'):
        from .source_subjects import directory_subjects
        for subject in directory_subjects(first):
            worker.enqueue('candidate',flow,{'url':subject['url'],'title':subject['name'],
                'expected_entity':subject['name'],'source_subject':subject,'proactive':True,
                'query':p.get('query'),'strategy':p.get('strategy')},'agent-subject:'+digest(subject['url']+'|'+subject['name']))
    root=urljoin(first['url'] if first else p['url'],'/')
    if first and first['url']!=root and not source_only:fetch(root,'homepage')
    for acquired in checkpoint['pages']:
        d=parse_page(acquired)
        role=target_fit.source_role(acquired['url'],d['title'],d['text'])
        if role in ('training_provider','institution'):
            source_only=True;first_role=role;break
    cursor=0
    while not source_only and cursor<len(checkpoint['pages']):
        page=checkpoint['pages'][cursor];cursor+=1
        if page.get('status')!=200 or page.get('purpose')=='external_solution':continue
        # Check declared alternate commercial journeys before spending the read
        # quota on secondary own pages. Never follow their outbound links.
        for link in website_audit.external_solutions(page):fetch(link['url'],'external_solution')
        for link in website_audit.public_links(page):fetch(link['url'],link['purpose'])
    from .site_identity import resolve
    valid,identity,provenance=resolve(checkpoint['pages'],p['url'],p.get('expected_entity'))
    from .schema import actor_span_valid
    if identity.get('name') and not actor_span_valid(identity['name'],0,len(identity['name'])):
        identity={**identity,'identity_status':'unknown'}
    eligible=identity.get('region') in worker.campaign['filters']['regions']
    fit=target_fit.evaluate(identity,valid,{'eligible':eligible}) if valid else {'status':'INSUFFICIENT_EVIDENCE','audit_allowed':False,'reasons':['original_unavailable'],'offer_evidence':[]}
    if source_only:
        fit={**fit,'status':'NOT_SUITABLE','audit_allowed':False,'source_role':first_role,
            'reasons':['publication_or_training_source_not_target_company']}
    expected=p.get('expected_entity')
    identity_matches=not expected or qualification.same_company_name(expected,identity.get('name',''))
    if not identity_matches:
        fit={**fit,'status':'NOT_SUITABLE','audit_allowed':False,'reasons':['unexpected_company_identity']}
    if not provenance['relationship_verified'] and identity_matches:
        fit={**fit,'status':'INSUFFICIENT_EVIDENCE','audit_allowed':False,'reasons':['redirect_identity_relationship_unverified']}
    if fit['audit_allowed'] and 'browser' not in checkpoint:
        from sales.commercial.browser import review
        try:
            # First render one commercial entry page on desktop/mobile. A
            # three-page deep audit is not the default cost of identification.
            entry=next((v for v in valid if v.get('purpose')=='homepage'),valid[0])
            checkpoint['browser']=review(store,[entry],check,max_pages=1,
                limits={**worker.budget,'browser_audit_level':'STANDARD'})
            checkpoint['audit_plan']={'level':'STANDARD','entry_url':entry['url'],
                'reason':'verified_company_targeted_desktop_mobile','full_site_coverage':False}
        except InterruptedError:raise
        except BudgetExceeded as exc:
            if exc.resource!='browser_runs':raise
            checkpoint['browser']={'completed':False,'outcome':'browser_budget','pages':[],'findings':[]}
        save()
    if fit['audit_allowed'] and checkpoint.get('browser') and not checkpoint.get('browser_recovery_attempted'):
        from .audit_recovery import targets,merge
        from sales.commercial.browser import review
        recovery_pages=[p for p in valid if p['url'] in {r['url'] for r in checkpoint['browser'].get('pages',[])}] or valid[:1]
        recovery_limits={**worker.budget,'browser_audit_level':checkpoint['browser'].get('requested_level','STANDARD')}
        remaining_resources=worker.budget.get('browser_max_resources',60)-checkpoint['browser'].get('resource_requests',0)
        missing=targets(checkpoint['browser'],recovery_pages,recovery_limits) if remaining_resources>0 else {}
        if missing:
            # Persist the attempt before starting. Stop/Resume cannot loop it.
            checkpoint['browser_recovery_attempted']=True;save()
            remaining=worker.budget.get('browser_total_seconds',120)-checkpoint['browser'].get('elapsed_ms',0)/1000
            try:
                retry=review(store,[p for p in valid if p['url'] in missing],check,
                    max_pages=min(worker.budget['max_browser_pages'],len(missing)),
                    limits={**recovery_limits,'browser_total_seconds':remaining,'browser_viewports':missing,'browser_max_resources':remaining_resources})
                checkpoint['browser']=merge(checkpoint['browser'],retry,recovery_pages,recovery_limits)
            except BudgetExceeded as exc:
                if exc.resource!='browser_runs':raise
                checkpoint['browser']['recovery_unavailable']='configured_browser_run_limit'
            save()
    from .audit_depth import plan as deep_plan,merge as merge_deep
    deeper=deep_plan(checkpoint.get('browser') or {},valid,worker.budget) if fit['audit_allowed'] else None
    if deeper and not checkpoint.get('deep_attempted'):
        checkpoint['deep_attempted']=True
        checkpoint['deep_reason']={k:v for k,v in deeper.items() if k!='pages'};save()
        from sales.commercial.browser import review
        try:
            deep=review(store,deeper['pages'],check,max_pages=len(deeper['pages']),
                limits={**worker.budget,'browser_audit_level':'DEEP',
                    'browser_total_seconds':deeper['seconds'],'browser_max_resources':deeper['resources']})
            checkpoint['browser']=merge_deep(checkpoint['browser'],deep)
            checkpoint['deep_finished']=True
            checkpoint['audit_plan']={'level':'DEEP','reason':deeper['reason'],'full_site_coverage':False}
        except BudgetExceeded as exc:
            if exc.resource!='browser_runs':raise
            checkpoint['deep_unavailable']='configured_browser_run_limit'
        save()
    report=website_audit.audit(checkpoint['pages'],checkpoint.get('browser'),checkpoint['attempts'])
    from urllib.parse import urlsplit
    homepage_read=any(page.get('purpose')=='homepage' or urlsplit(page.get('requested_url',page['url'])).path in ('','/') for page in valid)
    report['homepage_read']=homepage_read
    report['audit_plan']=checkpoint.get('audit_plan',{'level':'HTTP','reason':'prequalification_or_browser_unavailable'})
    if checkpoint.get('deep_attempted') and not checkpoint.get('deep_finished') and not checkpoint.get('deep_unavailable'):
        report['browser_status']='PARTIAL'
        report['coverage_limits'].append('Approfondimento interrotto: conservate le misure precedenti, consumo residuo della fase non ricostruibile; nessun retry cieco.')
    report['scores']['BUSINESS_FIT']={'score':None,'value':fit['status'],'basis':fit,'meaning':'documented_service_fit_not_budget_or_buying_intent'}
    report['scores']['COMMERCIAL_OPPORTUNITY']={'score':None,'basis':'commercial_review_pending'}
    source={'url':valid[0]['url'] if valid else p['url'],'title':parse_page(valid[0])['title'] if valid else p.get('title',''),
        'text':parse_page(valid[0])['text'] if valid else '', 'original':bool(valid),
        'checked_at':min((x['checked_at'] for x in valid if x.get('checked_at')),default=None)}
    body=qualification.evaluate(source,None,[],flow)
    owned=identity.get('identity_status')=='verified' and provenance['relationship_verified'] and not source_only
    body.update(kind='COMPANY_SIGNAL',state='NEEDS_REVIEW' if valid else 'UNVERIFIABLE',opportunity_type='OPPORTUNITA_PROATTIVA',
        entity_name=identity.get('name') if owned else None,identity_verified=owned,
        official_domain=identity.get('website') if owned else None,
        entity_key=digest('official-domain:'+domain(identity['website'])) if owned else None,
        identity=identity,contacts=identity.get('contacts',[]) if owned else [],analysis_at=now(),
        website_audit=report,commercial_fit=fit,explicit_demand=False,purchase_intent='UNKNOWN',
        acquisition_provenance=provenance,
        source_aliases=sorted({p['url'],source['url'],root}) if owned else [],
        query=p.get('query'),strategy=p.get('strategy') or STRATEGY,region=identity.get('region'),
        sector=parse_page(valid[0]).get('sector') if valid else None,
        service='website',reason='Sito da valutare: non risulta una richiesta dichiarata di rifacimento.',
        counterevidence=[f['kind'] for f in fit.get('counterevidence',[])],
        next_verification='Verificare la portata del progetto e la priorità con il referente.',
        missing=['commercial_scope'],workflow_state='WEBSITE_AUDIT',evidence_level='ORIGINAL_READ' if valid else 'SNIPPET_ONLY')
    docs=[document(page) for page in valid]
    body['documents']=[{'id':d['id'],'document_id':d['id'],'url':d['url'],'text':d['text'],'original':True,'checked_at':d['checked_at']} for d in docs]
    body['facts']=[{'field':'business_activity','quote':f['quote'],'url':f['url'],'checked_at':f['checked_at'],'original':True,
                    'basis':'observed_business_offering_not_request'} for f in fit.get('offer_evidence',[])]
    for fact in body['facts']:
        doc=next((d for d in docs if d['url']==fact['url']),None)
        if doc:
            fact.update(document_id=doc['id'],content_hash=doc['content_hash'])
            start=doc['text'].find(fact['quote'])
            if start>=0:fact.update(document_start=start,document_end=start+len(fact['quote']))
    event=p.get('news_context');event_current=False
    if event:
        from .news import fresh
        event_current=fresh(event,source['checked_at'],worker.campaign['filters'].get('max_job_age_days',14))
        body['news_correlation']={'subject':event['subject'],'source_url':event['source_url'],
            'published_at':event['published_at'],'event_date':event.get('event_date'),
            'original_event_checked_at':event['checked_at'],'event_current':event_current,
            'identity_linked':bool(owned and identity_matches),'link_basis':p.get('source_link_basis'),
            'status':'SITE_CHECKED_RELATION_PENDING' if owned and identity_matches else 'IDENTITY_NOT_LINKED'}
        body['opportunity_type']='SEGNALE_INDIRETTO'
        if owned and identity_matches:
            body['facts'].append(event['event'])
            saved=event['document'];docs.append(saved)
            body['documents'].append({'id':saved['id'],'document_id':saved['id'],'url':saved['url'],
                'text':saved['text'],'original':True,'checked_at':saved['checked_at']})
    if not fit['audit_allowed']:
        body.update(state='REJECTED' if fit['status'] in ('NOT_SUITABLE','LOW_PRIORITY') else 'NEEDS_REVIEW',
            reason='Compatibilità commerciale non dimostrata: '+', '.join(fit['reasons']),missing=fit['reasons'])
    elif report['website_opportunity']!='REVIEW_COMPLETE_PROJECT':
        measured=report['browser_status']=='COMPLETE'
        body.update(state='REJECTED' if measured else 'NEEDS_REVIEW',
            reason='Non emergono prove sufficienti per proporre un rifacimento completo.' if measured else 'Controlli del sito incompleti: nessuna necessità di rifacimento presunta.',
            missing=[] if measured else ['browser_coverage'])
    elif event and not event_current:
        body.update(state='NEEDS_REVIEW',reason='Impresa e sito esaminati; attualità dell’evento non dimostrata. La pubblicazione non prova un bisogno attuale.',
            missing=['event_currentness'],next_verification='Cercare un riscontro attuale prima di collegare l’evento a una proposta.')
    else:
        if event:
            from .news_review import payload as news_payload
            request=news_payload(report,fit,identity,event,event_current)
        else:request=website_review.payload(report,fit,identity)
        request['flow']=flow
        result=worker.model(flow,'website:'+root,request,check,query=p.get('query'),strategy=p.get('strategy') or STRATEGY)
        value=result.get('output');body['commercial_review']=result
        if value:
            body.update(hypothesis=value['reason'],hypothesis_type='COMMERCIAL_HYPOTHESIS',
                proposed_scope=value['scope'],proposal_type='COMPLETE_NEW_WEBSITE' if value['decision']=='COMPLETE_PROJECT' else value['decision'],
                objections=value['objections'],missing=value['unknowns'])
            if value['decision']=='COMPLETE_PROJECT' and report['browser_status']=='COMPLETE' and homepage_read and (not event or event_current and owned and identity_matches):
                body.update(state='POTENTIAL',reason='Opportunità proattiva documentata: '+value['reason']+' Interesse all’acquisto non dichiarato.',
                    workflow_state='QUALIFIED',evidence_level='WEBSITE_AUDIT_VERIFIED',missing=[],
                    next_verification='Confermare interesse e priorità; budget aziendale sconosciuto.')
                report['scores']['COMMERCIAL_OPPORTUNITY']={'score':None,'value':'SUPPORTED_HYPOTHESIS','basis':value['observation_ids'],'meaning':'supported_complete_project_hypothesis_not_declared_demand'}
                if event:
                    body['opportunity_type']='OPPORTUNITA_PROATTIVA'
                    body['news_correlation'].update(status='EVENT_AND_SITE_CORRELATED',
                        relation=value['event_relation'],existing_solution_check=value['existing_solution_check'],
                        basis='commercial_inference_from_attributed_event_and_measured_site_not_declared_request')
            elif value['decision'] in ('LIMITED_FIX','NO_OPPORTUNITY'):
                body.update(state='REJECTED',reason=value['reason'],missing=[])
            else:body.update(state='NEEDS_REVIEW',reason=value['reason']+' Audit parziale: completare le verifiche mancanti prima della qualifica.' if report['browser_status']!='COMPLETE' else value['reason'],
                missing=list(dict.fromkeys(value['unknowns']+(['browser_coverage'] if report['browser_status']!='COMPLETE' else []))))
        else:body.update(reason='Audit conservato; interpretazione commerciale non completata.',ai_status=result['status'])
    memory.save_record(store,worker.campaign,flow,body,docs)
    worker.rs.event(worker.cid,'website_audit',body['reason'],body['url'],{'state':body['state'],'pages':len(valid),'opportunity_type':body['opportunity_type']})
    if body.get('ai_status')=='budget_exhausted':return {'deferred_resource':'ai_verify'}
