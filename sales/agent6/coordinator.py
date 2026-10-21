"""Persistent PLAN → SEARCH → ANALYZE → VERIFY → LEARN loop.

Model calls occur only inside an explicitly started worker, never during preview.
All actions are bounded read-only searches/pages, using existing network policy.
"""
import json,re
from urllib.parse import urlsplit
from sales.db import now,encode,digest,domain
from sales.commercial.coordinator import Coordinator,acquire
from sales.commercial.resources import Budget,BudgetExceeded,deep_review_slot
from sales.content_policy import require_non_pdf,ExcludedPDF
from sales.providers import canonical,blocked
from sales.research_analysis import CompanyWeb,identity_from
from sales.commercial.inspection import document
from sales.commercial.recommendations import canonical_url as canonical_request
from . import FLOWS,config,flow_label
from . import ai,schema,memory,qualification,budget,commercial_policy,scheduling

class AgentCoordinator(Coordinator):
    def initialize(self):
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not self.active(c):raise InterruptedError('Campagna sospesa')
            for flow in self.engines:c.execute('INSERT OR IGNORE INTO commercial_engine_runs(campaign_id,engine) VALUES (?,?)',(self.cid,flow))
            c.execute("UPDATE commercial_engine_runs SET state='pending',error=NULL WHERE campaign_id=? AND state='blocked'",(self.cid,))
        self.settings=config(self.campaign['filters'].get('agent_settings'))
        if self.campaign['filters'].get('decision_engine')=='ai_first_1':
            from .social_seeds import validate_filters
            for url in validate_filters(self.campaign['filters']):
                if self.rs.suppressed({'website':url}):continue
                self.enqueue('candidate','SOCIAL',{'url':url,'title':'Link social inserito da te',
                             'strategy':'user_social_link','query':'','depth':0,'user_supplied':True},
                             'ai-first-url:'+digest(url))
        from .continuations import restore
        restore(self)
    def tick(self):
        for flow in self.engines:
            with self.store.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                if not self.active(c):return
                run=c.execute('SELECT * FROM commercial_engine_runs WHERE campaign_id=? AND engine=?',(self.cid,flow)).fetchone()
                # A reservation is temporary: completed work in another flow
                # can release capacity. Revive only AI-deferred tasks, never
                # network blocks or a provider limit, without resetting usage.
                ledger=c.execute('SELECT engine,candidate_id,body,reserved_cost,reported_cost FROM commercial_ai_executions WHERE campaign_id=? AND attempt=1',(self.cid,)).fetchall()
                for kind,stage in (('candidate','verify'),('agent_screen','screen'),('search','screen'),('agent_plan','replan')):
                    if self.campaign['filters'].get('decision_engine')=='ai_first_1' and kind=='search':
                        stage='verify'
                    if budget.available(c,self.campaign,flow,self.campaign['filters']['commercial']['ai'],stage,ledger):
                        revived=c.execute("UPDATE research_tasks SET state='pending',error=NULL,available_at=? WHERE campaign_id=? AND strategy=? AND kind=? AND state='budget' AND error LIKE ?",(now(),self.cid,flow,kind,'%ai_'+stage+'%')).rowcount
                        if revived:
                            c.execute("UPDATE commercial_engine_runs SET state='running',error=NULL WHERE campaign_id=? AND engine=?",(self.cid,flow))
                            run={**dict(run),'state':'running'}
                if run['state'] in ('blocked','exhausted','budget_reached'):continue
                if c.execute("SELECT 1 FROM research_tasks WHERE campaign_id=? AND strategy=? AND state IN ('pending','working')",(self.cid,flow)).fetchone():continue
                if c.execute("SELECT 1 FROM research_tasks WHERE campaign_id=? AND strategy=? AND state='budget' AND error LIKE '%ai_%'",(self.cid,flow)).fetchone():continue
                used=c.execute("SELECT used FROM commercial_resources WHERE campaign_id=? AND engine=? AND resource='queries'",(self.cid,flow)).fetchone()
                if used and used[0]>=self.budget['max_queries_per_engine']:
                    c.execute("UPDATE commercial_engine_runs SET state='budget_reached',error='Query autorizzate esaurite' WHERE campaign_id=? AND engine=?",(self.cid,flow));continue
                n=c.execute("SELECT count(*) FROM research_tasks WHERE campaign_id=? AND strategy=? AND kind='agent_plan'",(self.cid,flow)).fetchone()[0]
                hold=scheduling.planning_hold(c,self.campaign,flow,now()) if n else None
                if hold:
                    if hold['stop']:
                        c.execute("UPDATE commercial_engine_runs SET state='exhausted',error=? WHERE campaign_id=? AND engine=?",
                            ('Tre piani consecutivi senza una strategia nuova eseguibile; nessun limite del saldo provider.',self.cid,flow))
                    continue
                self._insert(c,'agent_plan',flow,{'round':n},'agent-plan:'+flow+':'+str(n))
                c.execute("UPDATE commercial_engine_runs SET state='running',cursor=? WHERE campaign_id=? AND engine=?",(n+1,self.cid,flow))
    def mark(self,flow,state,reason):
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if self.active(c):c.execute('UPDATE commercial_engine_runs SET state=?,error=? WHERE campaign_id=? AND engine=?',(state,reason,self.cid,flow))
    def hard_budget_exhausted(self):
        cfg=self.campaign['filters']['commercial']['ai']
        with self.store.connect() as c:
            rows=c.execute('SELECT reserved_cost,reported_cost FROM commercial_ai_executions WHERE campaign_id=? AND attempt=1',
                           (self.cid,)).fetchall()
        return bool(budget.global_limit_reasons(cfg,rows))
    def terminal_state(self):
        """Explain the observed stopping condition, not a provider balance."""
        cfg=self.campaign['filters']['commercial']['ai']
        with self.store.connect() as c:
            runs=[dict(r) for r in c.execute('SELECT engine,state,error FROM commercial_engine_runs WHERE campaign_id=?',(self.cid,))]
            tasks=[dict(r) for r in c.execute("SELECT strategy,kind,state,error,count(*) count FROM research_tasks WHERE campaign_id=? AND state IN ('failed','blocked','budget') GROUP BY strategy,kind,state,error",(self.cid,))]
            ledger=c.execute('SELECT engine,reserved_cost,reported_cost FROM commercial_ai_executions WHERE campaign_id=? AND attempt=1',(self.cid,)).fetchall()
        reasons=budget.global_limit_reasons(cfg,ledger)
        for flow in self.engines:
            used=sum(r['engine']==flow for r in ledger)
            if used>=cfg['max_calls_per_engine']:reasons.append({'code':'ai_flow_calls','flow':flow,'used':used,'limit':cfg['max_calls_per_engine']})
        reasons.extend({'code':'flow_resource_limit','flow':r['engine'],'detail':r['error']} for r in runs if r['state']=='budget_reached')
        failed=any(t['state'] in ('failed','blocked') for t in tasks) or any(r['state']=='blocked' for r in runs)
        if reasons:
            labels={'ai_campaign_calls':'massimo di chiamate AI della campagna','ai_flow_calls':'massimo di chiamate AI del flusso','ai_cost_capacity':'capacità residua del budget AI insufficiente per un’altra chiamata','flow_resource_limit':'limite operativo del flusso'}
            detail='; '.join(labels[r['code']]+(' '+r['flow'] if r.get('flow') else '')+(': '+r['detail'] if r.get('detail') else '') for r in reasons)
            message='Ricerca conclusa: '+detail+'. Risultati conservati. Il saldo dei provider non è stato interrogato.'
            state='exhausted'
        elif failed or tasks:
            state='blocked';message='Ricerca interrotta da controlli non completati, non da esaurimento dei crediti. Consulta i motivi per flusso; risultati e verifiche restano salvati.'
            reasons.append({'code':'unfinished_checks','flows':[r['engine'] for r in runs if r['state']=='blocked']})
        else:
            state='exhausted';message='Ricerca conclusa: nessuna nuova strategia ammessa e non ancora eseguita proposta dai flussi. Risultati conservati; non significa che non esistano altre opportunità.'
            reasons.append({'code':'strategies_exhausted'})
        # Close current run indicators with the campaign. Never rewrite a
        # terminal historical campaign or imply a worker is still running.
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if self.active(c):
                for run in runs:
                    if run['state'] not in ('running','pending'):continue
                    own=[t for t in tasks if t['strategy']==run['engine']]
                    terminal='budget_reached' if any(t['state']=='budget' for t in own) else 'blocked' if any(t['state'] in ('failed','blocked') for t in own) else 'exhausted'
                    c.execute('UPDATE commercial_engine_runs SET state=?,error=? WHERE campaign_id=? AND engine=?',
                        (terminal,message,self.cid,run['engine']))
                    run.update(state=terminal,error=message)
        self.rs.event(self.cid,'agent_termination',message,details={'reason_codes':reasons,'flows':runs,'unfinished_tasks':tasks,'ai_calls':len(ledger)})
        return state,message
    def model(self,flow,key,payload,check,**accounting):
        if payload['task'] in (schema.SCREEN,schema.READ):payload={**payload,'recover_fields':True}
        result=ai.call(self.store,self.campaign,flow,key,payload,check)
        memory.event(self.store,self.campaign,flow,'model',key+':'+str(result.get('execution_id')),{'execution_id':result.get('execution_id'),'task':payload['task'],'status':result['status'],'reason':result.get('error'),'estimated_cost':result.get('estimated_cost'),'basis':'model_interpretation','partial':result.get('partial',False),'validation_errors':result.get('validation_errors',[]),'diagnostic':result.get('diagnostic'),**accounting})
        return result
    def _execute(self,task,check):
        p=task['payload'];flow=task['strategy'];check()
        from .research import enabled
        if enabled(self.campaign) and task['kind'] in ('search','candidate'):
            from .research import search,read
            return search(self,task,check) if task['kind']=='search' else read(self,task,check)
        if task['kind']=='agent_plan':return self.planning(task,check)
        if task['kind']=='agent_screen':return self.screening(task,check)
        if task['kind']=='search':
            from . import proactive
            proactive_search=proactive.is_query(p,flow)
            policy=commercial_policy.assess_query(p,flow,self.campaign['filters']['regions']) if p.get('selection')!='verification' else commercial_policy.investigation(p.get('prior') or {})
            if policy['allowed'] and p.get('selection')!='verification':
                from .query_pipeline import prepare
                prepared,problem=prepare(p,flow,self.campaign['filters']['regions'],memory.query_receipts(self.store,self.cid,flow))
                if problem:policy={**problem,'allowed':False}
                else:p={**p,**prepared}
            if not policy['allowed']:
                memory.event(self.store,self.campaign,flow,'query_policy',str(task['id']),{'query':p.get('query'),**policy,'allowed':False})
                return
            stage='verify' if proactive_search or p.get('news_context') else 'screen'
            if not budget.remaining(self.store,self.campaign,flow,self.campaign['filters']['commercial']['ai'],stage):
                return {'deferred_resource':'ai_'+stage}
            items=acquire(self.store,p,check);receipts=self.receipts(task,items)
            # Deterministic policy only before semantic batch analysis.
            accepted=[];policy_rejections=[]
            for item,receipt in receipts:
                try:require_non_pdf(item);url=canonical(item['url'])
                except ExcludedPDF:
                    self.trace(flow,{**receipt,'decision':'exclude','reason':'excluded_pdf'});continue
                except (ValueError,KeyError):continue
                if self.rs.suppressed({'website':url}):
                    self.trace(flow,{**receipt,'decision':'exclude','reason':'commercial_suppression'});continue
                if flow in ('SOCIAL','LINKEDIN') and p.get('selection')!='verification':
                    from .social import post_url
                    if not post_url(url):
                        self.trace(flow,{**receipt,'decision':'exclude','reason':'social_result_not_a_public_post_or_specific_job'});continue
                if p.get('news_context'):
                    if not proactive.candidate_allowed(item):
                        self.trace(flow,{**receipt,'decision':'exclude','reason':'news_resolution_requires_company_site'});continue
                    from .news import enqueue_site
                    enqueue_site(self,flow,url,p['news_context'],p,'search_for_named_subject_official_identity_unverified')
                    self.trace(flow,{**receipt,'decision':'admit','reason':'news_subject_identity_and_site_check'})
                    continue
                policy=commercial_policy.preflight(item)
                if not policy['allowed']:
                    self.trace(flow,{**receipt,'decision':'exclude','reason':policy['reason']});policy_rejections.append({'domain':domain(url),'reason':policy['reason']});continue
                if proactive_search:
                    if not proactive.candidate_allowed(item):
                        self.trace(flow,{**receipt,'decision':'exclude','reason':'not_official_company_candidate'})
                        policy_rejections.append({'domain':domain(url),'reason':'not_official_company_candidate'});continue
                    pending=qualification.evaluate({'url':url,'title':item.get('title',''),'text':'','original':False},None,[],flow)
                    pending.update(state='DISCOVERED',opportunity_type='SEGNALE_INDIRETTO',
                        reason='Azienda individuata per settore e territorio: identità, sito e compatibilità da verificare.',
                        query=p['query'],strategy=p.get('strategy'),discovery=receipt,workflow_state='ORIGINAL_READ_PENDING')
                    self.enqueue('candidate',flow,{'url':url,'title':item.get('title',''),'query':p['query'],
                        'strategy':p['strategy'],'proactive':True,'prior':pending,'discovery':receipt},'agent-proactive:'+digest(domain(url)))
                    memory.save_record(self.store,self.campaign,flow,pending)
                    self.trace(flow,{**receipt,'decision':'admit','reason':'proactive_identity_and_website_audit_required'})
                    continue
                # A literal, local technical freelance invitation already
                # justifies an original read. Paying AI to repeat the snippet
                # classification adds no evidence and can starve verification.
                from .completion import skip_screening
                indexed={'url':url,'title':item.get('title',''),'text':item.get('title','')+'\n'+item.get('content',item.get('snippet','')),'original':False,'checked_at':now()}
                literal=skip_screening(indexed,flow)
                if literal:
                    literal.update(query=p['query'],strategy=p.get('strategy'),discovery=receipt,
                        ai_screening='not_needed_literal_invitation',depth=p.get('depth',0))
                    self.offer6(flow,item,receipt,literal,p)
                    continue
                accepted.append((item,receipt))
            batch_size=max(1,min(4,self.campaign['filters']['commercial']['ai']['max_output_tokens']//300))
            for offset in range(0,len(accepted),batch_size):
                batch=accepted[offset:offset+batch_size]
                self.enqueue('agent_screen',flow,{'batch':batch,'parent':p,'query':p['query']},'agent-screen:'+str(task['id'])+':'+str(offset))
                for item,receipt in batch:
                    pending=qualification.evaluate({'url':receipt['url'],'title':item.get('title',''),'text':'','original':False},None,[],flow)
                    pending.update(state='DISCOVERED',workflow_state='SCREENING_PENDING',evidence_level='SNIPPET_ONLY',
                        reason='Risultato salvato in coda: screening non ancora eseguito.',query=p['query'],strategy=p.get('strategy'),discovery=receipt)
                    memory.save_record(self.store,self.campaign,flow,pending)
            memory.event(self.store,self.campaign,flow,'query',memory.normalized(p['query']),{'query':p['query'],'strategy':p.get('strategy','unattributed'),'results':len(items),'policy_rejections':policy_rejections,'objective':p.get('objective'),'hypothesis':p.get('hypothesis'),'selection':p.get('selection'),'basis':'search_receipt'})
            self.rs.event(self.cid,'agent_search',f'{flow_label(flow)}: {len(items)} risultati, screening salvato in coda.',details={'query':p['query'],'objective':p.get('objective')});return
        if task['kind']=='candidate':return self.reading(task,check)
        raise ValueError('unsupported_agent_task')
    def screening(self,task,check):
        flow=task['strategy'];batch=task['payload']['batch'];p=task['payload']['parent'];offset=0
        if not ai.has_saved_work(self.store,self.campaign,flow,'batch:'+str(task['id'])+':0','screen') and not budget.remaining(self.store,self.campaign,flow,self.campaign['filters']['commercial']['ai'],'screen'):
            return {'deferred_resource':'ai_screen'}
        records=[{'id':'r'+str(i+1),'url':r['url'],'text':(item.get('title','')+'\n'+item.get('content',item.get('snippet',''))),'original':False} for i,(item,r) in enumerate(batch)]
        evidence=schema.bundle(records,4500)
        result=self.model(flow,'batch:'+str(task['id'])+':'+str(offset),{'task':schema.SCREEN,'result_ids':[r['id'] for r in records],'evidence':evidence,'flow':flow,'repair':task['payload'].get('repair'), 'instruction':'Screen direction and named subject only; at most two facts per snippet. Never date an indexed request. A repair contains one result: select only its supplied segment IDs; omit unsupported fields.'},check,query=p['query'],strategy=p.get('strategy'))
        analyses={a['result_id']:a for a in (result.get('output') or {}).get('analyses',[])}
        for batch_index,(item,receipt) in enumerate(batch):
            check();source={'url':receipt['url'],'title':item.get('title',''),'text':item.get('title','')+'\n'+item.get('content',item.get('snippet','')),'original':False,'checked_at':now()}
            a=analyses.get('r'+str(batch_index+1));body=qualification.evaluate(source,a,result.get('evidence',[]),flow)
            body.update(query=p['query'],strategy=p.get('strategy','unattributed'),discovery=receipt,depth=p.get('depth',0))
            if body['state']=='REJECTED':
                self.trace(flow,{**receipt,'decision':'exclude','reason':body['reason']});memory.save_record(self.store,self.campaign,flow,body);continue
            if not a:
                failures=result.get('validation_errors') or (result.get('diagnostic') or {}).get('failures',[])
                failure=next((x for x in failures if x.get('result_id')=='r'+str(batch_index+1)),{'code':result.get('error') or 'missing_result'})
                from .recovery import literal_invitation
                recovered=literal_invitation(source,flow)
                if recovered:
                    recovered.update(query=p['query'],strategy=p.get('strategy','unattributed'),discovery=receipt,depth=p.get('depth',0),
                        validation_error=failure,screening_error='ai_'+str(failure['code']),workflow_state='SCREENING_FAILED_RECOVERABLE')
                    memory.save_record(self.store,self.campaign,flow,recovered)
                    self.offer6(flow,item,receipt,recovered,p)
                    continue
                body.update(state='UNVERIFIABLE',technical_error='ai_'+str(failure['code']),validation_error=failure,
                    workflow_state='SCREENING_FAILED_RECOVERABLE',reason='Analisi del risultato non completata: '+str(failure['code']))
                # One semantic repair on the individual result, never rerun
                # valid siblings. Transport retries still obey max_retries.
                transient=result['status']=='timeout' or result.get('retryable')
                semantic=result['status'] in ('invalid','completed') or result.get('error')=='provider_response_truncated'
                permitted=semantic or transient and self.campaign['filters']['commercial']['ai']['max_retries']>0
                if permitted and not task['payload'].get('repair_attempt'):
                    repair={'code':failure['code'],'instruction':'Re-evaluate this one result with canonical segment references; no invented citations.'}
                    self.enqueue('agent_screen',flow,{'batch':[(item,receipt)],'parent':p,'query':p['query'],'repair_attempt':1,'repair':repair},
                        'agent-screen-repair:'+digest(flow+canonical_request(receipt['url'])))
                    body['recovery_action']='single_result_repair_queued'
                else:body['recovery_action']='repair_exhausted' if task['payload'].get('repair_attempt') else 'retry_not_permitted'
                memory.save_record(self.store,self.campaign,flow,body);self.trace(flow,{**receipt,'decision':'not_processed','reason':'analysis_unavailable','validation_error':failure});continue
            self.offer6(flow,item,receipt,body,p)
    def planning(self,task,check):
        with self.store.connect() as c:
            saved=c.execute("SELECT body FROM agent6_memory WHERE campaign_id=? AND flow=? AND kind='plan' AND key=?",(self.cid,task['strategy'],str(task['id']))).fetchone()
        saved_plan=json.loads(saved[0]) if saved else {}
        chosen=saved_plan.get('chosen')
        if chosen:
            # Finish the persisted choice after Stop; do not advance the
            # exploration schedule or charge another query for the same task.
            for proposal in saved_plan.get('chosen_queries') or [chosen]:
                self.enqueue('search',task['strategy'],proposal,'agent-query:'+digest(task['strategy']+memory.normalized(proposal['query'])))
            return
        flow=task['strategy'];hist=memory.history(self.store,flow);round_index=task['payload']['round']
        if round_index:
            with self.store.connect() as c:hold=scheduling.planning_hold(c,self.campaign,flow,now())
            if hold:
                if hold['stop']:
                    self.mark(flow,'exhausted','Tre piani senza una strategia nuova eseguibile; risultati conservati.')
                    return
                return {'deferred_resource':'ai_replan'}
        context={'strategies':hist['strategy_groups'][:8],'recent_queries':hist['recent_queries'][:8],'sources':hist['sources'][:8],'feedback_count':hist['feedback_count'],'legacy_context':hist['legacy_context'][:3],'shared_companies':[{k:v for k,v in e.items() if k!='evidence'} for e in hist['shared_companies'][:4]],**memory.planning_feedback(self.store,self.cid,flow)}
        context['campaign_id']=self.cid
        context['memory_scope']='History is not current budget/queue state. Plan feedback is campaign-scoped; technical failures are not no demand.'
        from .query_pipeline import prepare,adaptation
        from .research import enabled
        ai_first=enabled(self.campaign)
        if ai_first:
            from functools import partial
            prepare=partial(prepare,ai_first=True)
        # Only actual receipts in this campaign stop regional clones. Older
        # outcomes inform ranking, without creating a permanent blacklist.
        receipts=memory.query_receipts(self.store,self.cid,flow)
        context['discovery_adaptation']=adaptation(receipts)
        context['current_date']=now()[:10]
        if round_index:
            # A model plan may contain several sound proposals. Consume its
            # still-new proposals before paying for another plan; revalidate
            # against current outcomes so stale/noisy families are not reused.
            with self.store.connect() as c:
                plans=[json.loads(r[0]) for r in c.execute("SELECT body FROM agent6_memory WHERE campaign_id=? AND flow=? AND kind='plan' ORDER BY id DESC LIMIT 12",(self.cid,flow))]
                dispatched={memory.normalized(json.loads(r[0]).get('query','')) for r in c.execute("SELECT payload FROM research_tasks WHERE campaign_id=? AND strategy=? AND kind='search'",(self.cid,flow))}
            pool={};reuse_rejected=[]
            for plan in plans:
                for proposal in plan.get('queries',[]):
                    key=memory.normalized(proposal['query'])
                    if key in dispatched or memory.seen_query(self.store,flow,proposal['query'],self.settings['memory_hours']):continue
                    candidate,error=prepare(proposal,flow,self.campaign['filters']['regions'],receipts)
                    if candidate:pool[key]=candidate
                    elif error:reuse_rejected.append({'query':proposal['query'],'reason':error.get('reason')})
            if reuse_rejected:
                memory.event(self.store,self.campaign,flow,'query_policy','reuse:'+str(task['id']),
                    {'origin':'saved_plan','rejected':reuse_rejected,'basis':'same_policy_as_new_and_dispatch'})
            reusable=list(pool.values())
            if ai_first and flow=='SOCIAL':
                from .query_pipeline import social_coverage
                reusable=social_coverage(reusable,receipts)
            if ai_first and flow=='AZIENDE':
                from .query_pipeline import company_coverage
                reusable=company_coverage(reusable,receipts)
            reuse=memory.choose(reusable,hist,round_index,self.settings['exploration_percent'])
            if reuse:
                memory.event(self.store,self.campaign,flow,'plan',str(task['id']),{'reason':'Proposta AI già salvata e rivalidata sugli esiti attuali.',
                    'queries':list(pool.values()),'chosen':reuse,'basis':'revalidated_saved_proposal_no_model_call'})
                self.enqueue('search',flow,reuse,'agent-query:'+digest(flow+memory.normalized(reuse['query'])))
                return
        from .strategies import brief,recovery_proposals
        if round_index and not ai_first:
            alternatives=[]
            for proposal in recovery_proposals(flow,self.campaign['filters']['regions'],receipts):
                prepared,problem=prepare(proposal,flow,self.campaign['filters']['regions'],receipts)
                if prepared and not memory.seen_query(self.store,flow,prepared['query'],self.settings['memory_hours']):
                    with self.store.connect() as c:
                        queued=c.execute("SELECT 1 FROM research_tasks WHERE campaign_id=? AND strategy=? AND kind='search' AND json_extract(payload,'$.query')=?",(self.cid,flow,prepared['query'])).fetchone()
                    if not queued:alternatives.append(prepared)
            selected=memory.choose(alternatives,hist,round_index,self.settings['exploration_percent'])
            if selected:
                memory.event(self.store,self.campaign,flow,'plan',str(task['id']),{'queries':alternatives,'chosen':selected,
                    'basis':'deterministic_recovery_no_model_call','reason':'Alternativa verificabile dopo esiti improduttivi o squilibrio di strategie.'})
                self.enqueue('search',flow,selected,'agent-query:'+digest(flow+memory.normalized(selected['query'])))
                return
        strategy=brief(flow,self.campaign['filters']['regions'],round_index)
        if ai_first:
            strategy={**strategy,'commercial_goal':'Find usable work or collaboration for an Italian web/frontend freelancer. Official standing freelance invitations and spontaneous portfolios are useful outreach, not active paid projects. Proactive needs require commercial evidence; news/funding alone is not demand. Read originals before judging. Preserve five distinct channels.'}
            if flow=='SOCIAL':
                from .query_pipeline import missing_social_platforms
                strategy.pop('focus_platform',None)
                strategy.update(required_platforms=['linkedin.com','instagram.com'],
                    platforms_to_cover=missing_social_platforms(receipts),
                    query_constraints='One platform per query. Initially propose one specific LinkedIn query '
                    'and one specific Instagram query for identifiable buyers or external collaborators. '
                    'Cover both before repeating one platform. Use actual search receipts to target the '
                    'missing platform on replanning. No login, scraping bypass or guessed source URLs.')
        if flow=='AZIENDE':
            from .proactive import STRATEGY
            from .query_pipeline import strategy_balance
            balance=strategy_balance(flow,receipts);preferred=balance['preferred']
            strategy.update(preferred_strategy=STRATEGY if preferred=='proactive' else 'explicit_complete_project',
                strategy_balance=balance,
                instruction='For proactive discovery use strategy exactly official_company_sector_region and search sector + one territory + official products/services. No developer request is required. For explicit demand use explicit_complete_project. Alternate the two strategies.')
        output=self.model(flow,'plan:'+str(round_index),{'task':schema.PLAN,'flow':flow,'regions':self.campaign['filters']['regions'],'memory':context,'exploration_percent':self.settings['exploration_percent'],'round':round_index,'goal':strategy['goal'],'channel_strategy':strategy},check)
        if not output.get('output'):
            diagnostic=output.get('diagnostic') or {'code':output.get('error')}
            repair=output['status']=='invalid' and round_index==0 and budget.remaining(self.store,self.campaign,flow,self.campaign['filters']['commercial']['ai'],'replan')>0
            memory.event(self.store,self.campaign,flow,'plan_feedback',str(task['id']),{'diagnostic':diagnostic,'repair_scheduled':repair,'instruction':'Repair invalid proposals using the supplied error codes. Queries: 5–300 characters; every required field nonempty. No generic fallback. One repair within the existing replan quota.'})
            if repair:
                self.rs.event(self.cid,'plan_repair','Piano invalido: un tentativo di riparazione nella quota già disponibile.',details={'flow':flow,'diagnostic':diagnostic});return
            codes=[x.get('code') for x in diagnostic.get('failures',[])] or [diagnostic.get('code')]
            self.mark(flow,'blocked','Pianificazione non recuperata: '+', '.join(str(x) for x in codes));return
        out=output['output'];candidates=[];rejected=[]
        if output.get('validation_errors'):
            memory.event(self.store,self.campaign,flow,'plan_feedback',str(task['id']),{'invalid_proposals':output['validation_errors'],'valid_proposals_retained':len(out['queries']),'instruction':'Retain valid proposals; avoid the diagnosed defects in future plans.'})
        for q in out['queries']:
            if flow=='LINKEDIN' and 'site:linkedin.com' not in q['query']:q={**q,'query':'site:linkedin.com '+q['query']}
            prepared,problem=prepare(q,flow,self.campaign['filters']['regions'],receipts)
            if problem:
                rejected.append({'query':q['query'],**problem});continue
            q={**prepared,'page':1,'strategy_id':q['strategy'],'expected_cost':{'serper_requests':1,'http_reads':'successive, entro quota'}}
            if flow=='LINKEDIN' and 'site:linkedin.com' not in q['query']:q['query']='site:linkedin.com '+q['query']
            if memory.seen_query(self.store,flow,q['query'],self.settings['memory_hours']):
                rejected.append({'query':q['query'],'reason':'recent_query_duplicate',
                                 'detail':'Already searched within the configured memory window; propose a materially different query.'})
            else:candidates.append(q)
        selectable=candidates
        if ai_first and flow=='SOCIAL':
            from .query_pipeline import social_coverage
            selectable=social_coverage(candidates,receipts)
        if ai_first and flow=='AZIENDE':
            from .query_pipeline import company_coverage
            selectable=company_coverage(candidates,receipts)
        selected=memory.choose(selectable,hist,round_index,self.settings['exploration_percent'])
        if out['decision']=='stop':selected=None
        chosen_queries=[selected] if selected else []
        if ai_first and flow=='SOCIAL' and round_index==0 and selected and out['decision']!='stop':
            from .query_pipeline import missing_social_platforms,social_query_platform
            # Both requested platforms already have model-generated, validated
            # proposals. Queue one per missing platform in this SAME plan;
            # do not require another inference just to dispatch its other half.
            # Search execution still reserves each request atomically and obeys
            # Stop, shared/provider/flow caps and the current source policy.
            for platform in missing_social_platforms(receipts):
                if platform==social_query_platform(selected['query']):continue
                other=memory.choose([q for q in selectable if social_query_platform(q['query'])==platform],
                                    hist,round_index,self.settings['exploration_percent'])
                if other:chosen_queries.append(other)
        memory.event(self.store,self.campaign,flow,'plan',str(task['id']),{'reason':out['reason'],'queries':candidates,'rejected_queries':rejected,'invalid_proposals':output.get('validation_errors',[]),'chosen':selected,'chosen_queries':chosen_queries,'basis':'model_plan_with_memory_ranking'})
        retryable_rejected=[r for r in rejected if r.get('reason')!='recent_query_duplicate' or ai_first and round_index==0]
        if not selected and (retryable_rejected or candidates and not selectable) and out['decision']!='stop' and budget.remaining(self.store,self.campaign,flow,self.campaign['filters']['commercial']['ai'],'replan'):
            instruction=('Propose a commercially relevant query for the missing LinkedIn/Instagram platform.'
                         if candidates and not selectable else
                         'Formulate a different commercially testable query, not a completed portfolio or generic hiring.')
            memory.event(self.store,self.campaign,flow,'plan_feedback',str(task['id']),{'rejected':rejected,'instruction':instruction});return
        if out['decision']=='stop' or not selected:
            self.mark(flow,'exhausted','Nessuna ipotesi nuova e utile: '+out['reason']);return
        for proposal in chosen_queries:
            self.enqueue('search',flow,proposal,'agent-query:'+digest(flow+memory.normalized(proposal['query'])))
            self.rs.event(self.cid,'agent_plan',proposal['objective'],details={k:proposal[k] for k in ('query','hypothesis','missing','stop_condition','selection')})
    def offer6(self,flow,item,receipt,body,parent):
        direction=commercial_policy.investigation(body,initial=True)
        if not direction['allowed']:
            body.update(state='DISCOVERED',reason='Approfondimento non giustificato: '+direction['reason'])
            memory.save_record(self.store,self.campaign,flow,body)
            self.trace(flow,{**receipt,'decision':'not_processed','reason':direction['reason']});return
        url=receipt['url'];key='agent-url:'+digest(canonical_request(url))
        with self.store.connect() as c:known=c.execute('SELECT id FROM research_tasks WHERE campaign_id=? AND fingerprint=?',(self.cid,key)).fetchone()
        if known:
            self.trace(flow,{**receipt,'decision':'duplicate','reason':'URL già in verifica in un altro flusso'});memory.save_record(self.store,self.campaign,flow,body);return
        if blocked(url):
            body.update(state='UNVERIFIABLE',technical_error='access_policy',reason='Contenuto indicizzato: accesso automatico non autorizzato. Cercare fonte ufficiale.')
            if flow in ('SOCIAL','LINKEDIN'):
                body.update(social_source={'url':url,'status':'INDEXED_ONLY_ACCESS_POLICY','original_read':False},
                    workflow_state='ORIGINAL_READ_FAILED',evidence_level='SNIPPET_ONLY')
            memory.save_record(self.store,self.campaign,flow,body)
            self.trace(flow,{**receipt,'decision':'admit','reason':'indexed_only'});self.investigate(flow,body,parent);return
        self.enqueue('candidate',flow,{'url':url,'title':item.get('title',''),'discovery':receipt,'query':parent['query'],'strategy':parent.get('strategy'),'depth':parent.get('depth',0),'prior':parent.get('prior') or body,'expected_entity':parent.get('expected_entity'),'verification_goal':parent.get('missing')},key)
        body.update(workflow_state='ORIGINAL_READ_PENDING',evidence_level='SNIPPET_ONLY')
        memory.save_record(self.store,self.campaign,flow,body)
        self.trace(flow,{**receipt,'decision':'admit','reason':'Analisi semantica: lettura mirata'} )
    def reading(self,task,check):
        p=task['payload'];flow=task['strategy'];require_non_pdf(p)
        if p.get('proactive'):
            from .proactive import run
            return run(self,task,check)
        if not ai.has_saved_work(self.store,self.campaign,flow,'page:'+canonical_request(p['url']),'verify') and not budget.remaining(self.store,self.campaign,flow,self.campaign['filters']['commercial']['ai'],'verify'):
            return {'deferred_resource':'ai_verify'}
        page=p.get('original_page') or CompanyWeb(self.store,check).get(p['url']);check();require_non_pdf(page)
        if page.get('status')!=200:raise ValueError('HTTP '+str(page.get('status')))
        from .source_access import require_content
        access=require_content(page)
        from .source_scope import text_scope,request_page_type
        doc=document(page);scope=text_scope(doc['text']);text=scope['text']
        source={'url':page['url'],'title':doc.get('page_title') or doc['title'],'text':text,'checked_at':page['checked_at'],'original':True,'document_id':doc['id'],
                'access':access,'source_scope':{k:v for k,v in scope.items() if k!='text'},'request_page_type':request_page_type(page['html'])}
        from .document_units import extract as document_units
        source['document_units']=document_units(source)
        from .social import content_scope
        post_scope=content_scope(page,doc)
        if post_scope:
            source.update(post_scope,text=doc['text'])
            text=doc['text']
        from .social import post_url
        if post_url(page['url']) and not post_scope:
            # The delivered page may mix a post, comments and neighbouring
            # authors. Preserve the acquisition without treating it as a
            # single attributable request or spending AI on mixed evidence.
            prior=p.get('prior') or {}
            source['evidence_eligible']=False
            body=qualification.evaluate(source,None,[],flow)
            body.update(state='NEEDS_REVIEW',entity_name=prior.get('entity_name'),kind=prior.get('kind','UNKNOWN'),
                facts=[f for f in prior.get('facts',[]) if not f.get('original')],
                query=p.get('query'),strategy=p.get('strategy'),depth=p.get('depth',0),
                reason='Pagina pubblica consultata, ma il testo del post non è separabile con certezza da commenti e altri autori.',
                next_verification='Cercare una richiesta indipendente sul sito ufficiale del soggetto.',
                missing=['post_author','post_scope','request'],evidence_level='ORIGINAL_READ',workflow_state='VERIFICATION_PENDING',
                social_source={'url':page['url'],'status':'PUBLIC_POST_AUTHOR_OR_SCOPE_UNVERIFIED','original_read':True},
                documents=[{'id':digest(canonical_request(source['url'])),**source,'document_id':doc['id']}],access=access)
            memory.save_record(self.store,self.campaign,flow,body,[doc])
            self.investigate(flow,body,p)
            return
        if not p.get('original_page'):
            # Preserve the fetched public page before inference. Stop/Resume
            # can finish its verification without fetching or paying twice.
            saved={k:page[k] for k in ('url','status','html','checked_at','content_type') if k in page}
            with self.store.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                if not self.active(c):raise InterruptedError('Campagna sospesa')
                row=c.execute('SELECT payload FROM research_tasks WHERE id=? AND campaign_id=?',(task.get('id'),self.cid)).fetchone()
                if row:c.execute('UPDATE research_tasks SET payload=?,updated_at=? WHERE id=?',(encode({**json.loads(row[0]),'original_page':saved}),now(),task['id']))
            p['original_page']=saved
        text_key=digest(' '.join(text.split()))
        with self.store.connect() as c:
            previous=c.execute("SELECT body FROM agent6_records WHERE campaign_id=? AND json_extract(body,'$.original')=1",(self.cid,)).fetchall()
        for row in previous:
            old=json.loads(row['body'])
            if domain(old['url'])==domain(source['url']) and old['url']!=source['url'] and (old.get('ai_status') in ('completed','cache_hit') or old['state']=='REJECTED'):
                if any(digest(' '.join(d.get('text','').split()))==text_key for d in old.get('documents',[])):
                    self.rs.event(self.cid,'duplicate_page','Pagina già esaminata: stesso contenuto, nessuna nuova prova.',source['url'],{'flow':flow});return
        # Preserve rejected originals, but avoid paying AI for conclusive objective negatives.
        from sales.extract import parse_page
        parsed=parse_page(page)
        from sales.targeting import exclusion as target_exclusion
        source['target_exclusion']=target_exclusion(page,parsed)
        source['allowed_regions']=self.campaign['filters']['regions']
        source['editorial']=parsed.get('editorial',False)
        source['job_date']=parsed.get('published_at') if parsed.get('date_origin')=='JobPosting.datePosted' else None
        social_context=p.get('social_context') or p.get('prior',{}).get('social_context')
        if social_context:
            from .social import reciprocal
            social_link=reciprocal(social_context,page,identity_from([page]))
            source['social_identity_link']=social_link
            if social_link['verified']:
                original=next((d for d in p.get('prior',{}).get('documents',[]) if d.get('original') and d['url']==social_context['url']),None)
                if original:
                    source.update(request_identity_linked=True,linked_request_text=original.get('analysis_text') or original['text'],
                        job_date=social_context.get('published_at'),job_date_basis='SocialMediaPosting.datePublished or labelled original date',
                        checked_at=min(page['checked_at'],social_context.get('checked_at') or page['checked_at']))
        gates=qualification.objective(source,self.campaign['filters'].get('max_job_age_days',14))
        if source['document_units']:
            # A closed job or employee contract cannot reject the other cards.
            # Qualification still requires consistent citations within one unit.
            gates['counterevidence']=[]
        # Financial counterevidence must first be attributed to the actual
        # requester; an amount in another company's context cannot stop reading.
        gates['counterevidence']=[v for v in gates['counterevidence'] if v not in ('budget_below_minimum','declared_budget_insufficient_for_target')]
        if not parsed.get('job') and source['request_page_type']!='forum_thread' and not source.get('request_identity_linked'):gates['counterevidence']=[v for v in gates['counterevidence'] if v!='stale_request']
        evidence=[];analysis=None;result={}
        if not gates['counterevidence']:
            checkpoint=qualification.evaluate(source,None,[],flow)
            checkpoint.update(query=p.get('query'),strategy=p.get('strategy'),workflow_state='VERIFICATION_PENDING',evidence_level='ORIGINAL_READ',
                reason='Fonte originale conservata; verifica commerciale ancora da completare.',
                documents=[{'id':digest(canonical_request(source['url'])),**source,'document_id':doc['id']}])
            memory.save_record(self.store,self.campaign,flow,checkpoint,[doc])
            deep_review_slot()
            records=[{'id':'r1',**source,'document_id':doc['id']}]
            if p.get('prior'):
                for old in p['prior'].get('documents',[])[:2]:
                    if old.get('evidence_eligible',True):records.append({**old,'id':'r1'})
            from . import passages
            recovery=(p.get('verification_repair') or {}).get('signals')
            evidence=passages.recovery_bundle(records,recovery,4500) if recovery else passages.bundle(records,4500)
            result=self.model(flow,'page:'+canonical_request(p['url']),{'task':schema.READ,'flow':flow,'result_ids':['r1'],'evidence':evidence,'repair':p.get('verification_repair'),'completion_goal':p.get('verification_goal') if p.get('prior',{}).get('original') else None,'question':p.get('verification_goal') or 'Identify requester and missing commercial evidence; do not confuse publisher or mentioned company. A company may sell services AND invite external collaborators. Read technical invitations before deciding SUPPLIER_OFFER. On multi-listing pages never combine facts from separate ads.'},check,query=p.get('query'),strategy=p.get('strategy'))
            evidence=result.get('evidence',[]);analysis=next(iter((result.get('output') or {}).get('analyses',[])),None)
            if p.get('retained_analysis'):
                from .field_recovery import merge
                analysis,evidence=merge(p['retained_analysis'],p.get('retained_evidence',[]),analysis,evidence,
                    p.get('verification_repair',{}).get('fields',[]))
        ident=identity_from([page])
        from sales.commercial.indexed_jobs import publisher_host
        from sales.commercial.entity_scope import profile
        if publisher_host(page['url']) or profile(page)['multi_subject']:
            ident={**ident,'identity_status':'unknown','identity_conflicts':['publisher_or_multiple_subjects']}
        from .identity_aliases import match as match_owner
        if p.get('expected_entity') and not match_owner(ident,p['expected_entity'],source)['matched']:
            ident={**ident,'identity_status':'unverified','identity_conflicts':['unexpected_company']}
        body=qualification.evaluate(source,analysis,evidence,flow,ident,self.campaign['filters'].get('max_job_age_days',14))
        if not analysis and p.get('verification_repair',{}).get('code')=='original_invitation_ignored':
            invitations=[s for s in body.get('commercial_signals',[]) if s['type'] in ('collaboration_invitation','explicit_project_request')]
            if invitations and not gates['counterevidence']:
                body.update(state='NEEDS_REVIEW',reason='Invito originale conservato; il recupero AI non ha completato identità e condizioni.',
                    signal_recovery={'signal_ids':[s['id'] for s in invitations], 'basis':'original_signal_survives_failed_repair'},
                    semantic_issues=body['semantic_issues']+['original_invitation_recovery_incomplete'])
        body['ai_validation_errors']=(analysis or {}).get('field_errors',[])
        resolved=set(body.get('deterministic_completion',{}).get('added_fields',[]))
        body['field_errors']=[e for e in body['ai_validation_errors'] if e.get('field') not in resolved]
        body['source_scope']=source['source_scope']
        if post_scope:body['source_scope']['post']={k:v for k,v in post_scope.items() if k!='analysis_text'}
        from .social import context as social_original_context,post_url
        if post_url(page['url']):
            context=social_original_context(body,page,doc)
            body['social_context']=context;body['social_source']=context
        elif social_context:
            body['social_context']=social_context
            body['social_source']={**social_context,'official_identity_link':source.get('social_identity_link')}
        from . import passages
        body.update(query=p.get('query'),strategy=p.get('strategy'),depth=p.get('depth',0),documents=[{'id':digest(canonical_request(source['url'])),**source,'document_id':doc['id']}],access=access,ai_status=result.get('status'),ai_error=result.get('error'),evidence_coverage=passages.coverage([{'id':'r1',**source}],evidence))
        body.update(evidence_level=body.get('evidence_level','ORIGINAL_READ'),workflow_state='VERIFICATION_PENDING' if not analysis and not gates['counterevidence'] else 'EVALUATED')
        if p.get('prior',{}).get('screening_error'):
            body['screening_recovery']={k:p['prior'].get(k) for k in ('screening_error','validation_error','recovery_basis')}
        if body['state'] in ('VERIFIED','POTENTIAL'):
            body.update(evidence_level=body.get('evidence_level') if body.get('evidence_level')=='CROSS_VERIFIED' else 'ORIGINAL_VERIFIED',workflow_state='QUALIFIED')
        if result.get('error'):body['technical_error']='ai_'+result['error']
        if not analysis and not gates['counterevidence']:
            cfg=self.campaign['filters']['commercial']['ai']
            semantic=result.get('status')=='invalid' or result.get('error')=='provider_response_truncated'
            transient=result.get('status')=='timeout' or result.get('retryable')
            permitted=semantic or transient and cfg['max_retries']>0
            if permitted and not p.get('verification_repair') and cfg['max_calls_per_candidate']>1:
                self.enqueue('candidate',flow,{**p,'_deep_review_reserved':True,
                    'verification_repair':{'attempt':1,'code':result.get('error'),'instruction':'Re-evaluate the saved original using only its canonical segments; omit unsupported claims.'}},
                    'agent-verify-repair:'+digest(canonical_request(p['url'])))
                body['recovery_action']='original_verification_repair_queued'
            else:body['recovery_action']='candidate_limit_or_retry_policy' if cfg['max_calls_per_candidate']<=1 else 'repair_exhausted_or_not_permitted'
        field_repair=False
        if body.get('signal_recovery'):
            if not p.get('verification_repair') and self.campaign['filters']['commercial']['ai']['max_calls_per_candidate']>1:
                self.enqueue('candidate',flow,{**p,'_deep_review_reserved':True,
                    'verification_repair':{'attempt':1,'code':'original_invitation_ignored',
                        'signals':[{'url':s['url'],'start':s['start'],'end':s['context_end']} for s in body['commercial_signals'] if s['id'] in body['signal_recovery']['signal_ids']][:3],
                        'instruction':'Resolve the original invitation independently from supplier services. Re-extract kind, actual company identity and invitation conditions. No automatic promotion, invented budget or project. Quote only supplied canonical segments.'}},
                    'agent-verify-repair:'+digest(canonical_request(p['url'])))
                body['recovery_action']='original_signal_repair_queued';field_repair=True
            else:body['recovery_action']='signal_recovery_exhausted_or_budget_not_authorized'
        if analysis and analysis.get('field_errors') and not gates['counterevidence'] and body['state'] not in ('REJECTED','VERIFIED','POTENTIAL'):
            # One bounded repair, on the already downloaded page. Preserve good
            # fields and never turn an invalid company name into a guessed one.
            from .completion import repair_fields
            fields=repair_fields(analysis,body)
            if not fields:body['recovery_action']='no_new_evidence_for_field_repair'
            if fields and not p.get('verification_repair') and self.campaign['filters']['commercial']['ai']['max_calls_per_candidate']>1:
                self.enqueue('candidate',flow,{**p,'_deep_review_reserved':True,
                    'retained_analysis':analysis,'retained_evidence':evidence,
                    'verification_repair':{'attempt':1,'fields':fields,
                        'instruction':'Repair ONLY these missing fields using supplied original segments. Omit unsupported fields; do not re-evaluate valid facts or invent the company name.'}},
                    'agent-verify-repair:'+digest(canonical_request(p['url'])))
                body['recovery_action']='targeted_field_repair_queued';field_repair=True
        memory.save_record(self.store,self.campaign,flow,body,[doc]);self.rs.event(self.cid,'agent_decision',body['reason'],body['url'],{'flow':flow,'state':body['state'],'missing':body['missing']})
        if field_repair:return
        if flow=='NEWS':
            from .news import investigate as investigate_news
            if investigate_news(self,flow,body,page,doc,p):return
        if commercial_policy.investigation(body)['allowed']:
            # Follow only a specifically labelled current application/official link.
            links=qualification.followup_links(page)
            # A contact link cannot resolve a publication date or add a contact
            # already present. Follow only links relevant to a missing check.
            import re
            missing=set(body.get('missing',[]))
            links=[link for link in links if
                (re.search(r'contatt|contact',link['label'],re.I) and bool(missing & {'contact','entity','official_domain'})) or
                (re.search(r'apply|candidati|collabora con noi|lavora con noi|careers',link['label'],re.I) and bool(missing & {'publication','closed','request','contract'})) or
                (re.search(r'sito ufficiale|official website',link['label'],re.I) and bool(missing & {'entity','official_domain'}))]
            for link in links[:1]:
                from urllib.parse import urljoin
                url=urljoin(page['url'],link['url'])
                if p.get('depth',0)<self.settings['max_verification_depth']:
                    try:
                        require_non_pdf({'url':url})
                        if not blocked(url):self.enqueue('candidate',flow,{'url':canonical(url),'title':link['label'],'depth':p.get('depth',0)+1,'query':p.get('query'),'strategy':p.get('strategy'),'expected_entity':body.get('entity_name'),'prior':body,'social_context':body.get('social_context'),'verification_goal':'Verificare il collegamento ufficiale: '+link['label']},'agent-url:'+digest(canonical_request(url)))
                    except (ValueError,ExcludedPDF):pass
            self.investigate(flow,body,p)
    def investigate(self,flow,body,parent):
        depth=parent.get('depth',0)
        if depth>=self.settings['max_verification_depth']:return
        # No anonymous generic searches. Name must be literal evidence, not guessed from URL.
        direction=commercial_policy.investigation(body)
        if not direction['allowed']:return
        name=body['entity_name'];goal=direction['goal']
        query=commercial_policy.verification_query(body,goal)
        fingerprint='agent-investigate:'+digest(flow+name.casefold()+goal)
        # Same subject + missing requirement cannot trigger another search without new facts.
        evidence_key=digest(name.casefold()+goal+' '.join(direction['evidence'].casefold().split()))
        with self.store.connect() as c:
            if c.execute("SELECT 1 FROM agent6_memory WHERE campaign_id=? AND kind='verification' AND json_extract(body,'$.evidence_key')=?",(self.cid,evidence_key)).fetchone():return
        if memory.seen_query(self.store,flow,query,self.settings['memory_hours']):return
        payload={'query':query,'page':1,'strategy':parent.get('strategy') or 'verification','objective':'Verificare '+goal+' per '+name,'hypothesis':'Identità e richiesta possono essere confermate da fonte ufficiale.','missing':goal,'expected_entity':name,'expected_source':'official_company','success':'Prova attribuibile alla stessa impresa','stop_condition':'Nessuna fonte autorizzata o profondità/budget esauriti','depth':depth+1,'prior':body,'selection':'verification'}
        if parent.get('news_context'):
            payload.update(news_context=parent['news_context'],hypothesis='Evento aziendale documentato; dominio, situazione digitale e bisogno ancora da verificare.')
        if body.get('social_context'):payload['social_context']=body['social_context']
        # Both follow-up and query ledgers apply. Reserve only if not already queued.
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM research_tasks WHERE campaign_id=? AND fingerprint=?',(self.cid,fingerprint)).fetchone():return
            Budget(self.store,self.campaign,flow,self.budget).reserve('followups',connection=c)
            self._insert(c,'search',flow,payload,fingerprint)
        memory.event(self.store,self.campaign,flow,'verification',fingerprint,{'objective':payload['objective'],'missing':goal,'query':query,'stop_condition':payload['stop_condition'],'expected_cost':{'serper_requests':1},'priority':'missing_required_evidence','evidence_key':evidence_key})
    def record_failure(self,task,error):
        from .research import enabled
        if enabled(self.campaign) and task['kind']=='candidate' and not isinstance(error,(ExcludedPDF,BudgetExceeded)):
            from .research import failure
            return failure(self,task,error)
        if task['kind']=='agent_plan' and not isinstance(error,(ExcludedPDF,BudgetExceeded)):
            from sales.operation_outcomes import safe_error
            # Keep the failed task resumable, but do not spawn an unbounded
            # sequence of new plans for the same internal failure.
            self.mark(task['strategy'],'blocked','Pianificazione interrotta: '+safe_error(error))
            return
        if isinstance(error,(ExcludedPDF,BudgetExceeded)) or task['kind']!='candidate':return
        from sales.operation_outcomes import safe_error
        from sales.access_status import describe
        p=task['payload'];code=(describe(error) or {}).get('code') or safe_error(error)
        body=qualification.evaluate({'url':p['url'],'title':p.get('title',''),'text':'','original':False,'technical_error':code},None,[],task['strategy'])
        prior=p.get('prior') or {}
        body.update(query=p.get('query'),strategy=p.get('strategy'),entity_name=prior.get('entity_name'),kind=prior.get('kind','UNKNOWN'),facts=prior.get('facts',[]),missing=prior.get('missing',[]),workflow_state='ORIGINAL_READ_FAILED',evidence_level=prior.get('evidence_level','SNIPPET_ONLY'))
        from .social import post_url
        if post_url(p['url']):
            body['social_source']={'url':p['url'],'status':'ORIGINAL_UNAVAILABLE','original_read':False,'access_error':code}
        if body.get('entity_name'):
            try:self.investigate(task['strategy'],body,p)
            except BudgetExceeded:pass
        memory.save_record(self.store,self.campaign,task['strategy'],body)
