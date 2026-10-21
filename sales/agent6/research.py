"""AI-first execution over existing queue, HTTP policy, receipts and budget ledger.

No worker is started here. Legacy campaigns never enter this path.
"""
import json
import re

from sales.db import digest, encode, now, domain
from sales.discovery_control import annotate
from sales.content_policy import require_non_pdf, ExcludedPDF
from sales.providers import canonical, blocked
from sales.commercial.coordinator import acquire
from sales.commercial.inspection import document
from sales.research_analysis import CompanyWeb
from sales.commercial.identity import establish as identity_from
from sales.commercial.geography import locate
from . import ai, budget, memory
from . import decision, evidence


def enabled(campaign):
    return campaign['filters'].get('decision_engine') == decision.ENGINE


def social_reference(c,flow,url):
    from .social_seeds import recovery_query
    from sales.commercial.resources import BudgetExceeded
    try:
        proposal=recovery_query(url)
    except ValueError:
        return
    if not proposal:return
    try:
        c.enqueue('search',flow,proposal,'social-reference:'+digest(proposal['social_origin']['url']))
    except BudgetExceeded as exc:
        memory.event(c.store,c.campaign,flow,'social_recovery',digest(url),
                     {'reason':'configured_budget_exhausted','resource':exc.resource,'url':url})


def search(coordinator, task, check):
    c=coordinator; p=task['payload']; flow=task['strategy']
    from .query_pipeline import prepare
    prepared, problem=prepare(p,flow,c.campaign['filters']['regions'],
                             memory.query_receipts(c.store,c.cid,flow),ai_first=True)
    if problem:
        memory.event(c.store,c.campaign,flow,'query_policy',str(task['id']),problem)
        return
    if not budget.remaining(c.store,c.campaign,flow,c.campaign['filters']['commercial']['ai'],'verify'):
        return {'deferred_resource':'ai_verify'}
    # Dispatch may normalize a plan saved by an earlier backend. Receipts must
    # describe the actual provider expression and retain its original wording.
    p=prepared;task={**task,'payload':prepared}
    # New campaigns persist discovery before their bounded metadata selection.
    # Replay uses the original batch and AI receipt, without another Serper call.
    if 'discovery_batch' in p:
        items=p['discovery_batch']
    else:
        items=acquire(c.store,prepared,check)
        if c.campaign['filters'].get('discovery_triage_version')==1:
            from .discovery_triage import checkpoint as checkpoint_batch
            checkpoint_batch(c,task,items)
    rejections=[];new_urls=0;duplicates=0;inaccessible=0;indexed_lookups=0
    receipts=c.receipts(task,items)
    from .sector_alignment import assess as sector_alignment
    from .social_reference_alignment import assess as reference_alignment
    alignment=sector_alignment(items,p) or reference_alignment(items,p)
    triage=None
    if not alignment:
        from .discovery_triage import assess as assess_triage
        triage=assess_triage(c,task,items,check)
        alignment=triage
    held_for_alignment=0
    if p.get('official_lookup_recovery'):
        from .subject_lookup import reading_priority
        # Keep provider receipt positions, but reserve queue capacity for the
        # page most likely to answer the existing question before older routes.
        receipts.sort(key=lambda pair:-reading_priority(pair[0])['value'])
    for item, receipt in receipts:
        check()
        try:
            require_non_pdf(item);url=canonical(item['url'])
        except ExcludedPDF:
            rejections.append({'url':item.get('url'),'reason':'excluded_pdf'})
            c.trace(flow,{**receipt,'decision':'exclude','reason':'excluded_pdf'});continue
        except (ValueError,KeyError):
            continue
        recovery_scope=p.get('official_lookup_recovery') or {}
        if recovery_scope and domain(url)!=recovery_scope['domain']:
            rejections.append({'url':url,'reason':'outside_verified_subject_domain'})
            c.trace(flow,{**receipt,'decision':'exclude','reason':'outside_verified_subject_domain'});continue
        from .discovery_intent import source_issue,source_priority
        issue=source_issue({**item,'url':url},p)
        if issue:
            rejections.append({'url':url,**issue})
            c.trace(flow,{**receipt,'decision':'exclude',**issue})
            continue
        if alignment and item['url'] in alignment['held_urls']:
            held_for_alignment+=1
            c.trace(flow,{**receipt,'decision':'defer','reason':alignment['code'],
                          'discovery_alignment':alignment})
            continue
        if c.rs.suppressed({'website':url}):
            rejections.append({'url':url,'reason':'commercial_suppression'})
            c.trace(flow,{**receipt,'decision':'exclude','reason':'commercial_suppression'});continue
        if p.get('indexed_origin'):
            from .indexed_recovery import candidate_issue
            issue=candidate_issue({**item,'url':url},p['indexed_origin'])
            if issue:
                rejections.append({'url':url,'reason':issue})
                c.trace(flow,{**receipt,'decision':'exclude','reason':issue});continue
        priority=source_priority(item,flow,p)
        if triage and url in triage['read_first_urls']:
            priority={'value':4,'basis':'ai_selected_original_to_verify_not_qualified'}
        if p.get('official_lookup_recovery'):
            priority=reading_priority(item)
        receipt={**receipt,'discovery_priority':priority}
        source={'url':url,'title':item.get('title',''),'checked_at':now(),'original':False}
        body=decision.base(source,flow)
        body.update(state='DISCOVERED',query=p['query'],strategy=p.get('strategy'),
                    discovery=receipt,workflow_state='ORIGINAL_READ_PENDING')
        if blocked(url):
            inaccessible+=1
            body.update(state='UNVERIFIABLE',technical_error='access_policy',validation_status='ACCESS_BLOCKED',
                        reason='Risultato indicizzato; accesso alla fonte non autorizzato. Non è una prova originale.')
            from .social import post_url,platform
            if post_url(url):
                body['social_source']={'url':url,'platform':platform(url),'status':'INDEXED_ONLY_ACCESS_POLICY','original_read':False}
        else:
            added=c.enqueue('candidate',flow,{'url':url,'title':source['title'],'query':p['query'],
                      'strategy':p.get('strategy'),'discovery':receipt,'depth':p.get('depth',0),
                      'social_origin':p.get('social_origin'),
                      'indexed_origin':p.get('indexed_origin'),
                      'research_question':p.get('objective'),'expected_entity':p.get('expected_entity'),
                      'research_parent':p.get('research_parent'),
                      'discovery_priority':priority},
                      'ai-first-url:'+digest(url))
            new_urls+=int(added);duplicates+=int(not added)
            annotate(new_urls=new_urls)
        memory.save_record(c.store,c.campaign,flow,body)
        if blocked(url):
            from .social_seeds import lookup_worthwhile
            if lookup_worthwhile(item):
                social_reference(c,flow,url)
            elif not p.get('indexed_origin') and not p.get('depth') and indexed_lookups<1:
                from .indexed_recovery import proposal
                recovery=proposal(item)
                if recovery:
                    from sales.commercial.resources import BudgetExceeded
                    try:
                        added=c.enqueue('search',flow,recovery,'indexed-official:'+digest(recovery['query']))
                        indexed_lookups+=int(added)
                    except BudgetExceeded as exc:
                        memory.event(c.store,c.campaign,flow,'indexed_recovery',digest(url),
                                     {'reason':'configured_budget_exhausted','resource':exc.resource,'url':url})
        c.trace(flow,{**receipt,'decision':'admit','reason':body['reason']})
    annotate(outcome='discovery_completed',new_urls=new_urls,duplicates=duplicates,
             indexed_unverifiable=inaccessible,excluded=len(rejections),
             held_for_query_alignment=held_for_alignment,qualified=False)
    rejections=[{**r,'domain':domain(r.get('url') or '')} for r in rejections]
    memory.event(c.store,c.campaign,flow,'query',memory.normalized(p['query']),
                 {'query':p['query'],'strategy':p.get('strategy'),'results':len(items),
                  'new_urls':new_urls,'duplicates':duplicates,'indexed_unverifiable':inaccessible,
                  'policy_rejections':rejections,'selection':p.get('selection'),
                  'objective':p.get('objective'),'hypothesis':p.get('hypothesis'),
                  'query_validation':p.get('query_validation'),
                  'discovery_alignment':alignment,
                  'basis':'search_receipt'})
    if alignment:
        prefix='social-reference-alignment:' if p.get('social_origin') else 'sector-alignment:'
        memory.event(c.store,c.campaign,flow,'plan_feedback',prefix+str(task['id']),alignment)
    if not items:
        # A successful empty search can be too specific. A transport error
        # raises before this point and never becomes negative market evidence.
        from .subject_lookup import recovery
        retry=recovery(p)
        if retry:
            check()
            retry,problem=prepare(retry,flow,c.campaign['filters']['regions'],
                                  memory.query_receipts(c.store,c.cid,flow),ai_first=True)
            from sales.commercial.resources import BudgetExceeded
            diagnostic={'source_query':p['query'],'scheduled':False}
            if problem:
                diagnostic.update(reason='query_policy',detail=problem)
            else:
                host=retry['official_lookup_recovery']['domain']
                if c.rs.suppressed({'website':'https://'+host}):
                    diagnostic['reason']='commercial_suppression'
                else:
                    try:
                        added=c.enqueue('search',flow,retry,'official-subject-recovery:'+digest(host))
                        diagnostic.update(scheduled=bool(added),query=retry['query'],
                            reason='empty_subject_search' if added else 'already_queued_or_campaign_stopped')
                    except BudgetExceeded as exc:
                        diagnostic.update(reason='configured_budget_exhausted',resource=exc.resource)
            memory.event(c.store,c.campaign,flow,'subject_recovery',str(task['id']),diagnostic)


def checkpoint(c, task, page):
    """Persist the original before paid inference; replay doesn't refetch it."""
    with c.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not c.active(db):
            raise InterruptedError('Campagna sospesa')
        row=db.execute('SELECT payload FROM research_tasks WHERE id=? AND campaign_id=?',
                       (task['id'],c.cid)).fetchone()
        if row:
            payload={**json.loads(row[0]),'original_page':page}
            db.execute('UPDATE research_tasks SET payload=?,updated_at=? WHERE id=?',
                       (encode(payload),now(),task['id']))


def read(c, task, check):
    p=task['payload'];flow=task['strategy'];key='page:'+canonical(p['url'])
    from .continuations import check_current
    if not check_current(c,p):
        annotate(outcome='continuation_closed',qualified=False)
        return
    if p.get('user_supplied') and blocked(p['url']):
        from .social import platform
        body=decision.base({'url':p['url'],'title':p.get('title',''),'checked_at':now(),'original':False},flow)
        body.update(state='UNVERIFIABLE',validation_status='ACCESS_BLOCKED',
                    technical_error='access_policy',workflow_state='ORIGINAL_READ_FAILED',
                    reason='Link inserito da te. Il post non è consultabile automaticamente: nessun giudizio commerciale.',
                    social_source={'url':p['url'],'platform':platform(p['url']),
                                   'status':'ORIGINAL_UNAVAILABLE','original_read':False,'user_supplied':True})
        memory.save_record(c.store,c.campaign,flow,body)
        social_reference(c,flow,p['url'])
        annotate(outcome='unverifiable',qualified=False,scope='social_original',original_read=False)
        return
    if not p.get('original_page') and not ai.has_saved_work(c.store,c.campaign,flow,key,'verify') and not budget.remaining(
            c.store,c.campaign,flow,c.campaign['filters']['commercial']['ai'],'verify'):
        return {'deferred_resource':'ai_verify'}
    require_non_pdf(p)
    page=p.get('original_page') or CompanyWeb(c.store,check).get(p['url'])
    check();require_non_pdf(page)
    from .source_access import require_content
    require_content(page)
    if page['status']!=200:
        raise ValueError('HTTP '+str(page['status']))
    if not p.get('original_page'):
        checkpoint(c,task,page)
    doc=document(page)
    if p.get('social_origin'):
        from .social_seeds import links_post
        if not links_post(page,p['social_origin']['url']):
            body=decision.base({'url':page['url'],'title':doc.get('title',''),
                                'checked_at':page['checked_at'],'original':True},flow)
            body.update(state='UNVERIFIABLE',validation_status='SOURCE_ATTRIBUTION_UNVERIFIED',
                        reason='Pagina consultata, ma nessun collegamento al post indicato: conferma non dimostrata.',
                        social_origin=p['social_origin'],workflow_state='SOCIAL_REFERENCE_MISSING')
            memory.save_record(c.store,c.campaign,flow,body,[doc])
            annotate(outcome='unverifiable',qualified=False,scope='social_reference')
            return
    if flow in ('AZIENDE','AGENCIES','STARTUPS') and not p.get('unit_id'):
        from .request_collections import observe as observe_collection, route as route_collection
        collection=observe_collection(page,doc)
        if collection:
            route_collection(c,task,page,doc,collection,check)
            annotate(outcome='collection_requires_individual_originals',qualified=False,
                     scope='collection_navigation',original_read=True)
            return
    packet=evidence.packet(page,doc)
    source={'url':page['url'],'title':packet['title'],'checked_at':page['checked_at'],'original':True}
    from .social import post_url,scoped_context,scoped_geography,reciprocal,platform
    is_social=post_url(page['url'])
    if is_social and not packet['units']:
        body=decision.base(source,flow)
        body.update(state='UNVERIFIABLE',validation_status='SOCIAL_SCOPE_UNVERIFIED',
                    reason='Pagina acquisita, ma testo e autore del singolo annuncio non sono isolabili dai contenuti circostanti.',
                    social_source={'url':page['url'],'platform':platform(page['url']),
                                   'status':'PUBLIC_POST_AUTHOR_OR_SCOPE_UNVERIFIED','original_read':True},
                    workflow_state='SOCIAL_SCOPE_UNVERIFIED')
        memory.save_record(c.store,c.campaign,flow,body,[doc])
        annotate(outcome='unverifiable',qualified=False,scope='social_post')
        return
    ident=identity_from([page]);geo=locate([page],ident)
    from sales.commercial.entity_scope import profile
    owner=ident.get('identity_status')=='verified' and not ident.get('identity_conflicts') and not profile(page)['multi_subject']
    from .career_roles import separate as separate_roles, owner_proof as role_owner_proof
    separate_roles(page,packet,owner)
    if is_social:
        # Retain evidence but never mix social author/comments or log in.
        owner=False
    units=packet['units']
    selected=next((u for u in units if u['id']==p.get('unit_id')),units[0])
    if selected.get('career_role'):
        key+=':'+selected['id']
    if not ai.has_saved_work(c.store,c.campaign,flow,key,'verify') and not budget.remaining(
            c.store,c.campaign,flow,c.campaign['filters']['commercial']['ai'],'verify'):
        return {'deferred_resource':'ai_verify'}
    if p.get('browser_requested') and owner and 'ai_first_browser' not in page:
        from sales.commercial.browser import review
        from .website_audit import audit
        report=review(c.store,[page],check,max_pages=1,limits=c.budget)
        page={**page,'ai_first_browser':audit([page],report)}
        checkpoint(c,task,page)
    parent=p.get('research_parent') or {}
    from .owner_names import collect as owner_names, verified as verified_name
    resolved_identity={'name':ident.get('name'),'verified':bool(owner),
                       'domain':domain(ident.get('website') or page['url']),
                       'verified_names':owner_names(page,ident) if owner and selected['origin']=='page' else []}
    if p.get('indexed_origin') and not verified_name(resolved_identity,p['indexed_origin']['company_hint']):
        body=decision.base(source,flow)
        body.update(state='UNVERIFIABLE',validation_status='SOURCE_ATTRIBUTION_UNVERIFIED',
                    reason='Fonte consultata, ma identità del possibile committente indicizzato non confermata.',
                    indexed_origin=p['indexed_origin'],workflow_state='INDEXED_OWNER_UNVERIFIED')
        memory.save_record(c.store,c.campaign,flow,body,[doc])
        return
    target_matches=bool(parent.get('link_url') and canonical(parent['link_url'])==canonical(p['url']))
    if (parent.get('provenance')=='verified_owner_subject_lookup' and parent.get('lookup_domain')
            and parent['lookup_domain']==domain(p['url'])):
        target_matches=True
    joined=bool(owner and parent.get('entity_name') and
                verified_name(resolved_identity,parent['entity_name']) and
                target_matches and
                domain(page['url'])==domain(p['url']) and parent.get('unit'))
    social_context=parent.get('social_context')
    social_link=reciprocal(social_context,page,ident) if joined and social_context else None
    if social_context and not (social_link or {}).get('verified'):
        joined=False
    original_unit=parent['unit'] if joined else selected
    original_packet=parent['packet'] if joined else packet
    social_context=social_context if joined else scoped_context(page,doc,selected,None) if is_social else None
    social_geo=scoped_geography(original_unit,c.campaign['filters']['regions']) if social_context else None
    if joined:
        # Attribution must be demonstrated again on the destination. An Elice
        # card cannot lend its identity to an ilGiornale detail with a new owner.
        source={'url':original_packet['final_url'],'title':parent.get('title',''),
                'checked_at':original_packet['observed_at'],'original':True}
    from .source_context import editorial, select_links
    # A follow-up exists to resolve a question on the destination. Keep the
    # originating facts as context, without letting them displace the new page.
    # The combined passage allowance stays 4600 bytes; provenance stays separate.
    proofs=evidence.passages(original_packet,original_unit,1600 if joined else 3000,
                             source_content=editorial(original_packet,original_unit,flow,owner))
    if joined:
        extra=evidence.passages(packet,selected,3000)
        for index,e in enumerate(extra):
            e.update(id='linked'+str(index),unit_id=original_unit['id'])
        proofs=extra+proofs
    documents=[doc]
    role_owner=role_owner_proof(page,doc,selected,ident)
    if role_owner:proofs.insert(0,role_owner)
    meta=evidence.metadata_document(page,doc,selected)
    if meta:
        documents.append(meta)
        name=ident.get('name') or ''
        # Keep owner metadata citable without repeating descriptions already
        # present in the page and exhausting the evidence input allowance.
        if name:
            anchor=next((m for m in re.finditer(r'[^\n]+',meta['text']) if name in m[0]),None)
            if anchor:
                proofs.insert(0,{'id':'metadata','result_id':original_unit['id'],'unit_id':original_unit['id'],
                                 'url':page['url'],'text':anchor[0],'hash':digest(anchor[0]),
                                 'document_id':meta['id'],'offset':anchor.start(),'original':True,
                                 'checked_at':page['checked_at'],'origin':'original_metadata'})
    address_doc=evidence.owner_address_document(page,doc,selected,owner)
    if address_doc:
        documents.append(address_doc)
        proofs.insert(1 if meta else 0,{'id':'owner-address','result_id':original_unit['id'],
            'unit_id':original_unit['id'],'url':page['url'],'text':address_doc['text'],
            'hash':address_doc['content_hash'],'document_id':address_doc['id'],'offset':0,
            'original':True,'checked_at':page['checked_at'],'origin':'original_metadata'})
    for unit in units:
        if unit.get('document_id'):
            documents.append({'id':unit['document_id'],'url':page['url'],
                              'content_hash':digest(unit['text']),'text':unit['text'],
                              'title':packet['title'],'checked_at':page['checked_at'],
                              'provider':'JSON-LD originale: JobPosting',
                              'parent_document_id':doc['id'],'unit_id':unit['id']})
    from .verification_coverage import context as inspection_context, apply as apply_coverage
    coverage=inspection_context(p.get('browser_requested'),p.get('research_question'),page.get('ai_first_browser'))
    if page.get('ai_first_browser'):
        measured=json.dumps({'coverage':coverage,'observations':page['ai_first_browser']['observations']},ensure_ascii=False,indent=2)
        measurement={'id':digest(measured+page['url']),'url':page['url'],'content_hash':digest(measured),
                     'title':'Osservazioni tecniche','text':measured,'checked_at':page['checked_at'],
                     'provider':'Browser/HTML locale: misure e controlli non completati distinti'}
        documents.append(measurement)
        proofs.append({'id':'measurement','result_id':original_unit['id'],'unit_id':original_unit['id'],
                       'url':page['url'],'document_id':measurement['id'],'text':measured,'hash':digest(measured),
                       'offset':0,'original':True,'checked_at':page['checked_at'],'origin':'browser_or_html_measurement'})
    if not p.get('unit_id'):
        for u in units[1:]:
            c.enqueue('candidate',flow,{**p,'unit_id':u['id'],'original_page':page},
                      'ai-first-unit:'+digest(p['url']+u['id']))
    from .owner_policy import exclusions
    policy=exclusions([page],ident,owner)
    from .response_channels import collect as response_controls, documents as response_documents
    controls=response_controls(page,selected,ident,owner)
    channel_docs,channel_proofs,channels=response_documents(page,doc['id'],original_unit['id'],controls)
    documents+=channel_docs
    # Preserve the dedicated network route ahead of optional marketing prose;
    # generic contacts must not displace another role's terms or invitation.
    owner_proofs=[e for e in proofs if e.get('origin')=='original_metadata']
    network_ids={ch['evidence_id'] for ch in channels if ch.get('observation_kind')=='network_join_instruction'}
    priority_channels=[e for e in channel_proofs if e['id'] in network_ids]
    if priority_channels:
        proofs=owner_proofs+priority_channels+[e for e in proofs if e not in owner_proofs]
    proofs += [e for e in channel_proofs if e not in priority_channels]
    payload={'task':decision.TASK,'unit_id':original_unit['id'],
             'subject_scope_version':1,'allowed_regions':c.campaign['filters']['regions'],
             'flow':flow,'result_ids':[original_unit['id']],
             'evidence':proofs,
             'identity':resolved_identity,
             'dates':original_unit['dates'],'observed_at':packet['observed_at'],
             'max_job_age_days':c.campaign['filters'].get('max_job_age_days',14),
             'geography_allowed':bool(geo['eligible'] and (geo.get('remote_italy') or set(geo['regions']) & set(c.campaign['filters']['regions']))),
             'region':next(iter(geo.get('regions',[])),None),'policy_exclusion':bool(policy),
             'commercial_exclusions':policy,
             'response_channels':channels,
             'links':select_links(packet,selected,flow,owner),
             'prior_question':p.get('research_question'),
             'metadata':{'origin':selected['origin'],'canonical_url':packet['canonical_url'],
                         'last_modified':packet['last_modified'],'selected_unit':selected['id']}}
    if selected.get('career_role'):
        payload['metadata']['role_title']=selected['career_role']['title']
    if selected.get('discussion_scope'):
        scope = selected['discussion_scope']
        payload['metadata']['discussion'] = {k: scope[k] for k in ('basis','author_label','limitations')}
    if social_context:
        payload.update(social_source={**social_context,'official_identity_link':social_link},
                       geography_allowed=social_geo['allowed'],region=social_geo['region'],
                       social_geography=social_geo)
    if coverage['requested']:payload['verification_coverage']=coverage
    from .reading_coverage import expand
    payload=expand(payload,packet,selected,c.campaign['filters']['commercial']['ai'])
    pending=decision.base(source,flow)
    pending.update(query=p.get('query'),strategy=p.get('strategy'),evidence_unit_id=original_unit['id'],
                   social_origin=p.get('social_origin'),
                   indexed_origin=p.get('indexed_origin'),
                   commercial_exclusions=policy,
                   documents=[{'url':page['url'],'title':packet['title'],'checked_at':page['checked_at'],'original':True,
                               'text':selected['text'],'id':doc['id'],'document_id':doc['id']}],
                   continuation=p.get('continuation'),
                   evidence_packet=packet,workflow_state='VERIFICATION_PENDING',
                   reason='Originale acquisito; valutazione commerciale AI in attesa.')
    memory.save_record(c.store,c.campaign,flow,pending,documents)
    from sales.commercial.resources import deep_review_slot
    deep_review_slot()
    result=c.model(flow,key,payload,check,query=p.get('query'),strategy=p.get('strategy'))
    if result.get('output'):
        # Defensive revalidation also covers test providers and future adapters.
        actual={**payload,'evidence':result.get('evidence',payload['evidence'])}
        output,_=decision.validate(result['output'],actual)
        body=decision.materialize(source,output,actual['evidence'],actual,flow)
        body.update(query=p.get('query'),strategy=p.get('strategy'),evidence_unit_id=original_unit['id'],
                    social_origin=p.get('social_origin'),
                    indexed_origin=p.get('indexed_origin'),
                    continuation=p.get('continuation'),
                    evidence_packet=packet,documents=pending['documents'],
                    workflow_state='DECISION_COMPLETE')
    else:
        body={**pending,'validation_status':'MODEL_INVALID','technical_error':result.get('error') or result['status'],
              'reason':'Valutazione non completata: '+str(result.get('error') or result['status'])}
    if is_social:
        social_context=scoped_context(page,doc,selected,body.get('entity_name'))
    if social_context:
        body['social_source']={**social_context,'platform':platform(social_context['url']),
                               'official_identity_link':social_link}
    body['ai_status']=result['status']
    from .reading_coverage import measured
    body['source_coverage']=measured(packet,selected,result.get('evidence',[]))
    if page.get('ai_first_browser'):
        body['website_audit']=page['ai_first_browser']
    body=apply_coverage(body,coverage)
    from .owner_policy import apply_user_scope
    body=apply_user_scope(body)
    body['ai_execution_id']=result.get('execution_id')
    from .research_dispatch import assess as assess_dispatch
    body['research_dispatch']=assess_dispatch(body,payload['links'])
    memory.save_record(c.store,c.campaign,flow,body,documents)
    annotate(outcome='unverifiable' if body.get('verification_hold') else {'INTERESTING':'valid','NOT_INTERESTING':'not_relevant',
                      'NEEDS_RESEARCH':'needs_research'}.get(body.get('decision'),'unverifiable'),
             decision_engine=decision.ENGINE,commercial_decision=body.get('decision'),
             validation_status=body.get('validation_status'),ai_status=body['ai_status'],
             qualified=body.get('decision')=='INTERESTING',
             identity_verified=bool(body.get('identity_verified')))
    if not body['research_dispatch']['allowed']:
        memory.event(c.store,c.campaign,flow,'research_action_not_scheduled',digest(source['url']),
                     body['research_dispatch'])
        annotate(research_action_status='not_scheduled',research_action_reason=body['research_dispatch']['reason'])
        return
    action=body.get('research_action',{})
    if action.get('type')=='SEARCH_SUBJECT' and p.get('depth',0)<c.settings['max_verification_depth']:
        proposal={'query':action['query'],'strategy':'targeted_subject_verification',
                  'objective':action['question'],'hypothesis':body['reason'],
                  'missing':action['question'],'expected_entity':body['entity_name'],
                  'expected_source':'Original public company evidence',
                  'success':'Resolve the stated uncertainty with attributed original evidence',
                  'stop_condition':'No new evidence, repeated URL or configured depth/budget reached',
                  'depth':p.get('depth',0)+1,'selection':'verification'}
        if owner and verified_name(resolved_identity,body['entity_name']):
            # A subject search is not an observed hyperlink. Keep the original
            # request as context only for a destination independently verified
            # as the same owner on the same official domain.
            proposal['research_parent']={'url':source['url'],'title':source['title'],
                'unit':original_unit,'packet':{k:original_packet[k] for k in ('document_id','final_url','observed_at')},
                'entity_name':body['entity_name'],'lookup_domain':domain(page['url']),
                'provenance':'verified_owner_subject_lookup','social_context':social_context}
            from .subject_lookup import context as lookup_context
            proposal['subject_lookup_context']=lookup_context(body)
        from .query_pipeline import prepare
        prepared,problem=prepare(proposal,flow,c.campaign['filters']['regions'],
                                  memory.query_receipts(c.store,c.cid,flow),ai_first=True)
        if not problem:
            c.enqueue('search',flow,prepared,'ai-first-followup:'+digest(memory.normalized(action['query'])))
    if action.get('type')=='INSPECT_BROWSER' and not p.get('browser_requested') and p.get('depth',0)<c.settings['max_verification_depth']:
        c.enqueue('candidate',flow,{**p,'original_page':page,'browser_requested':True,
                  'depth':p.get('depth',0)+1,'research_question':action['question']},
                  'ai-first-browser:'+digest(canonical(page['url'])))
    if action.get('type')=='READ_LINK' and p.get('depth',0)<c.settings['max_verification_depth']:
        link=next(l for l in payload['links'] if l['id']==action['link_id'])
        # A recorded link is provenance, not network authorization. The protected
        # HTTP client will revalidate DNS, redirect, robots and content type.
        if blocked(link['url']):
            return
        destination=canonical(link['url'])
        if destination==canonical(page['url']):
            annotate(research_action_status='not_scheduled',research_action_reason='same_document_reference')
            return
        c.enqueue('candidate',flow,{'url':destination,'title':link['label'],
                  'query':p.get('query'),'strategy':p.get('strategy'),
                  'depth':p.get('depth',0)+1,'research_question':action['question'],
                  'research_parent':{'url':source['url'],'title':source['title'],
                                     'unit':original_unit,'packet':{k:original_packet[k] for k in ('document_id','final_url','observed_at')},
                                     'link_url':destination,'entity_name':body['entity_name'],
                                     'social_context':social_context}},
                  'ai-first-url:'+digest(destination))


def failure(c, task, error):
    from sales.operation_outcomes import safe_error
    p=task['payload']
    body=decision.base({'url':p['url'],'title':p.get('title',''),'original':False,'checked_at':now()},task['strategy'])
    body.update(state='UNVERIFIABLE',validation_status='ACCESS_BLOCKED',technical_error=safe_error(error),
                reason='Fonte non consultabile: '+safe_error(error),workflow_state='ORIGINAL_READ_FAILED',
                query=p.get('query'),strategy=p.get('strategy'))
    from .social import post_url,platform
    if post_url(p['url']):
        body['social_source']={'url':p['url'],'platform':platform(p['url']),
                               'status':'ORIGINAL_UNAVAILABLE','original_read':False}
    memory.save_record(c.store,c.campaign,task['strategy'],body)
