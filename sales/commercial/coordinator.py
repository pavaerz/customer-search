"""Four finite planners on the existing persistent, cancellable worker queue.

No provider fallback, automatic CRM insertion, model calls or outbound messages.
An inaccessible engine/query does not discard work from the other engines.
"""
import json,time
from datetime import datetime,timezone,timedelta
from sales.db import now,encode,digest,domain
from sales.providers import canonical,blocked,SearXNG,RSS
from sales.research_store import ResearchStore
from sales.research_analysis import CompanyWeb as ResearchWeb
from sales.direct_channels import DIRECTORIES,INSTITUTIONS,DOCUMENT_PATH,GUIDE_TITLE
from sales.discovery_control import measure,health,annotate
from sales.operation_outcomes import safe_error,error_outcome
from .catalog import ENGINES,VERSIONS,options,plan
from .storage import Opportunities
from .inspection import inspect
from .resources import Budget,BudgetExceeded
from sales.content_policy import ExcludedPDF,require_non_pdf,search_query
from .discovery import assess,followup_allowed
from .planner import choose,paginate,query_key

def campaign_counts(store,cid):
    with store.connect() as c:
        version=c.execute("SELECT json_extract(filters,'$.agent_version') FROM campaigns WHERE id=?",(cid,)).fetchone()
    if version and version[0]=='6.0':
        from sales.agent6.api import counts
        return counts(store,cid)
    with store.connect() as c:
        rows=c.execute('''SELECT o.entity_id,o.engine,o.manual_state,r.state,r.body,
          coalesce(co.do_not_contact,0) OR coalesce(co.prior_contacted,0) OR
          EXISTS (SELECT 1 FROM dismissed_companies d JOIN research_domains rd ON rd.domain=d.domain WHERE rd.entity_id=o.entity_id) OR
          EXISTS (SELECT 1 FROM prospects p WHERE p.company_id=co.id AND p.stage IN ('contacted','replied','proposal','won','lost')) OR
          EXISTS (SELECT 1 FROM interactions i JOIN prospects p ON p.id=i.prospect_id WHERE p.company_id=co.id AND i.kind IN ('contacted','replied','proposal','won','lost')) AS managed
          FROM commercial_opportunities o JOIN research_entities e ON e.id=o.entity_id LEFT JOIN companies co ON co.id=e.company_id
          JOIN commercial_revisions r ON r.id=(SELECT max(v.id) FROM commercial_revisions v WHERE v.opportunity_id=o.id AND v.campaign_id=?)''',(cid,)).fetchall()
        runs=[dict(r) for r in c.execute('SELECT * FROM commercial_engine_runs WHERE campaign_id=?',(cid,))]
        tasks=c.execute('SELECT strategy,kind,state,count(*) n FROM research_tasks WHERE campaign_id=? GROUP BY strategy,kind,state',(cid,)).fetchall()
        campaign_state=c.execute('SELECT status FROM campaigns WHERE id=?',(cid,)).fetchone()[0]
        search_results=c.execute("SELECT coalesce(sum(json_extract(details,'$.returned_urls')),0) FROM discovery_operations WHERE campaign_id=? AND kind='search'",(cid,)).fetchone()[0]
    counts={s:sum(r['state']==s and r['manual_state']!='discarded' for r in rows) for s in ('VERIFIED','POTENTIAL','NEEDS_REVIEW','REJECTED','UNVERIFIABLE')}
    for run in runs:
        run['planner_state']=run['state']
        if campaign_state in ('paused','stopping','interrupted'):run['state']=campaign_state
        run['counts']={s:sum(r['engine']==run['engine'] and r['state']==s and r['manual_state']!='discarded' for r in rows) for s in counts}
        run['examined']=sum(run['counts'].values());run['queries']=sum(t['n'] for t in tasks if t['strategy']==run['engine'] and t['kind']=='search' and t['state']=='done')
    useful={r['entity_id'] for r in rows if r['state'] in ('VERIFIED','POTENTIAL') and not r['managed'] and r['manual_state'] not in ('discarded','contacted')}
    bodies=[(r,json.loads(r['body'])) for r in rows]
    complete=sum(b.get('verification',{}).get('status')=='complete' for r,b in bodies)
    identified=len({r['entity_id'] for r,b in bodies if b.get('identity',{}).get('identity_status')=='verified'})
    from .resources import snapshot
    from .catalog import options
    with store.connect() as c:filters=json.loads(c.execute('SELECT filters FROM campaigns WHERE id=?',(cid,)).fetchone()[0])
    limits=options({**filters,'commercial_engines':filters.get('commercial_engines') or list(ENGINES)})[1]
    resources=snapshot(store,cid,limits)
    from .planner import summary
    feedback=summary(store,cid)
    rebuild=[b for r,b in bodies if r['engine']=='WEBSITE_REBUILD']
    browser_counts={key:sum(b.get('browser_outcome')==key for b in rebuild) for key in ('completed','partial','timeout','navigation_timeout','rendering_timeout','tls_error','robots','access_error','not_sampled','identity_unverified','budget_deferred')}
    # Latest decisions and actual executions answer different questions.
    with store.connect() as c:
        audits=[json.loads(r['body']).get('browser') or {} for r in c.execute('SELECT body FROM commercial_revisions WHERE campaign_id=?',(cid,))]
    executions=[a for a in audits if (a.get('pages') or a.get('resource_requests')) and not a.get('reused_revision_id')]
    browser_history_counts={'executed':len(executions),'complete':sum(bool(a.get('completed')) for a in executions),'incomplete':sum(not a.get('completed') for a in executions),'reused':sum(bool(a.get('reused_revision_id')) for a in audits)}
    from .resources import availability
    from .planner import coverage
    from .ai import summary as ai_summary
    resume=availability(store,cid,limits,filters.get('commercial_engines') or list(ENGINES))
    for run in runs:run.update(next((r for r in resume['engine_budget'] if r['engine']==run['engine']),{}))
    with store.connect() as c:
        traces=[{**json.loads(r['body']),'engine':r['engine']} for r in c.execute('SELECT engine,body FROM commercial_discovery WHERE campaign_id=?',(cid,))]
    direct=[r for r in traces if not r.get('origin',{}).get('parent')]
    trace_counts={'received':len(direct),'admitted':sum(r['decision']=='admit' for r in direct),'excluded':sum(r['decision'] in ('exclude','memory','budget') for r in direct),'duplicates':sum(r['decision']=='duplicate' for r in direct),'not_processed':sum(r['decision']=='not_processed' for r in direct),'followups':len(traces)-len(direct)}
    from .intelligence_metrics import engine_metrics
    intelligence=engine_metrics([b for r,b in bodies],traces,[dict(t) for t in tasks],resources)
    consultive=Opportunities(store).listing({'campaign':cid,'commercial_status':'actionable','limit':1})['commercial_metrics']
    provider_results=[r for r in traces if r.get('appearance_id')]
    stages={'policy':'deep_review_quota' if filters.get('demand_version')=='5.1' else 'legacy_admission_quota',
            'RAW_RESULTS':len(provider_results),'SCREENED_RESULTS':sum(r.get('decision')!='not_processed' for r in provider_results),
            'DERIVED_RESULTS':len(traces)-len(provider_results),
            'ADMITTED_CANDIDATES':sum(t['n'] for t in tasks if t['kind']=='candidate'),
            'DEEP_REVIEW_CANDIDATES':sum(v.get('candidates',{}).get('used',0) for v in resources.values()) if filters.get('demand_version')=='5.1' else None,
            'stop_counter':'candidates: approfondimenti' if filters.get('demand_version')=='5.1' else 'candidates: ammissioni'}
    return {**resume,'candidate_stages':stages,'commercial_opportunity_metrics' :consultive,'intelligence_metrics':intelligence,'ai':ai_summary(store,cid),'planner_coverage':coverage(store,cid,filters.get('commercial_engines') or list(ENGINES),filters.get('regions')),'trace_counts':trace_counts,'query_feedback':feedback,'resources':resources,'resource_limits':limits,'browser_counts':browser_counts,'browser_history_counts':browser_history_counts,'commercial':True,'engine_runs':runs,'commercial_counts':counts,'examined':len(rows),'qualified':counts['VERIFIED'],
            'search_results':search_results,'identified_companies':identified,'complete_verifications':complete,'incomplete_verifications':len(rows)-complete,
            'potential':counts['POTENTIAL'],'useful_companies':len(useful),'rejected':counts['REJECTED'],
            'needs_review':counts['NEEDS_REVIEW'],'unverifiable':counts['UNVERIFIABLE'],
            'discovered':sum(t['n'] for t in tasks if t['kind']=='candidate' and t['state']!='excluded'),
            'verifying':sum(t['n'] for t in tasks if t['kind']=='candidate' and t['state']=='working')}

def preflight(item):
    record=assess(item,item.get('commercial_engine','FREELANCE'))
    if record['decision']=='exclude':return None,record['reason']
    if blocked(record['url']) and record['source']=='web':return None,'Fonte non consultabile automaticamente'
    return record['url'],None

def acquire(store,payload,check):
    check()
    if store.settings()['provider']=='serper':
        from sales.serper_provider import search
        # Reuse only periods already supported by the Serper search adapter.
        # Month is a broad discovery filter, not proof of a 14-day publication.
        period=payload.get('discovery_period','') if not payload.get('resolution_url') else ''
        result,_=search(store,search_query(payload['query']),payload.get('page',1),period,check)
        return result['results']
    from sales.discovery_control import free_search
    config={**store.settings(),'page':payload.get('page',1)}
    from .resources import reserve
    reserve('provider_requests')
    result=free_search(store,lambda:{'results':SearXNG(store).search(payload['query'],config)})
    return result['results']

class Coordinator:
    def __init__(self,store,campaign):
        self.store=store;self.campaign=campaign;self.rs=ResearchStore(store);self.repo=Opportunities(store)
        self.engines,self.budget=options(campaign['filters']);self.cid=campaign['id'];self.generation=campaign['generation']
    def active(self,c):return c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(self.cid,self.generation)).fetchone()
    def enqueue(self,kind,engine,payload,key):
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not self.active(c):return False
            return self._insert(c,kind,engine,payload,key)
    def _insert(self,c,kind,engine,payload,key):
        if c.execute('SELECT 1 FROM research_tasks WHERE campaign_id=? AND fingerprint=?',(self.cid,key)).fetchone():return False
        budget=Budget(self.store,self.campaign,engine,self.budget)
        from .job_activity import window
        days=window(self.campaign['filters'].get('max_job_age_days',14))
        # Persisted recovery proposals used a provenance label. Normalize at
        # the queue boundary so resume and downstream follow-ups share a shape.
        origin=payload.get('origin')
        if isinstance(origin,str):origin={'kind':origin}
        elif origin is None:origin={}
        elif not isinstance(origin,dict):raise ValueError('Invalid query origin metadata')
        payload={**payload,'origin':origin}
        payload={**{'demand_version':self.campaign['filters'].get('demand_version')},**{k:payload.get('origin',{}).get(k) for k in ('strategy_id','demand_type','language','geography_tier')},**payload,'max_job_age_days':days}
        if kind=='search' and engine=='FREELANCE' and 'discovery_period' not in payload:payload['discovery_period']='week' if days<=7 else 'month' if days<=31 else 'year'
        if kind=='candidate':
            require_non_pdf(payload)
            if self.campaign['filters'].get('demand_version')!='5.1':budget.reserve('candidates',connection=c)
            if payload.get('depth',0):budget.reserve('followups',connection=c)
        if kind in ('search','resolve'):
            if payload.get('page',1)>self.budget['max_pages']:raise BudgetExceeded('pages_per_query')
            if kind=='search' and payload.get('page',1)==1:budget.reserve('queries',connection=c)
            if kind=='resolve':budget.reserve('followups',connection=c)
        return bool(c.execute('INSERT OR IGNORE INTO research_tasks(campaign_id,kind,strategy,payload,fingerprint,available_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
          (self.cid,kind,engine,encode({**payload,'commercial_engine':engine,**self.budget}),key,now(),now(),now())).rowcount)
    def initialize(self):
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not self.active(c):return
            for engine in self.engines:c.execute('INSERT OR IGNORE INTO commercial_engine_runs(campaign_id,engine) VALUES (?,?)',(self.cid,engine))
            c.execute("UPDATE commercial_engine_runs SET state='pending',error=NULL WHERE campaign_id=? AND state='blocked'",(self.cid,))
        # Only feeds deliberately configured by the user; no unrelated news seeds.
        for engine in self.engines:
            for feed in self.store.settings().get('rss_feeds',[]):
                if isinstance(feed,str):self.enqueue('source',engine,{'url':feed},'commercial-feed:'+digest(engine+feed))
    def tick(self):
        for engine in self.engines:
            with self.store.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                if not self.active(c):return
                run=c.execute('SELECT * FROM commercial_engine_runs WHERE campaign_id=? AND engine=?',(self.cid,engine)).fetchone()
                if run['state'] in ('blocked','exhausted','budget_reached'):continue
                n=c.execute("SELECT count(*) FROM research_tasks WHERE campaign_id=? AND strategy=? AND kind='candidate'",(self.cid,engine)).fetchone()[0]
                if self.campaign['filters'].get('demand_version')=='5.1':
                    used=c.execute("SELECT used FROM commercial_resources WHERE campaign_id=? AND engine=? AND resource='candidates'",(self.cid,engine)).fetchone()
                    n=used[0] if used else 0
                if n>=self.budget['max_candidates_per_engine']:
                    c.execute("UPDATE commercial_engine_runs SET state='budget_reached',error=? WHERE campaign_id=? AND engine=?",(str(BudgetExceeded('candidates')),self.cid,engine));continue
                pending=c.execute("SELECT kind,count(*) n FROM research_tasks WHERE campaign_id=? AND strategy=? AND state IN ('pending','working') GROUP BY kind",(self.cid,engine)).fetchall()
                counts={r[0]:r[1] for r in pending}
                if counts.get('search') or counts.get('candidate',0)>=12:continue
                allowed=self.campaign['filters'].get('regions')
                queries=[q for q in plan(engine) if not allowed or q['region'] in allowed]
                if self.campaign['filters'].get('search_version')=='5.0':
                    from .search_strategies import plans as search_plans
                    from .search_intelligence import choose as choose_strategy
                    from .geography import REGIONS
                    queries=search_plans(engine,allowed or REGIONS,self.campaign['filters'].get('max_job_age_days',14))
                    payload=choose_strategy(self.store,self.cid,engine,queries)
                else:payload=choose(self.store,self.cid,engine,queries)
                if payload is None:
                    if not pending:c.execute("UPDATE commercial_engine_runs SET state='exhausted' WHERE campaign_id=? AND engine=?",(self.cid,engine))
                    continue
                try:self._insert(c,'search',engine,payload,'commercial-query:'+digest(engine+query_key(payload['query'])+':1'))
                except BudgetExceeded as exc:
                    c.execute("UPDATE commercial_engine_runs SET state='budget_reached',error=? WHERE campaign_id=? AND engine=?",(str(exc),self.cid,engine));continue
                c.execute("UPDATE commercial_engine_runs SET cursor=cursor+1,state='running' WHERE campaign_id=? AND engine=?",(self.cid,engine))
    def trace(self,engine,record,receipt=False):
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not receipt and not self.active(c):return
            # Receipts are audit data, not qualifications. After Stop they may
            # describe results already returned by this task, never new work.
            aid=record.get('appearance_id')
            previous=c.execute("SELECT id FROM commercial_discovery WHERE campaign_id=? AND json_extract(body,'$.appearance_id')=?",(self.cid,aid)).fetchone() if aid else None
            if previous and receipt:return
            if previous:
                c.execute('UPDATE commercial_discovery SET decision=?,body=? WHERE id=?',(record['decision'],encode(record),previous[0]));return
            c.execute('INSERT INTO commercial_discovery(campaign_id,engine,query,url,decision,body,created_at) VALUES (?,?,?,?,?,?,?)',
                      (self.cid,engine,record.get('query'),record.get('url'),record['decision'],encode(record),now()))
    def receipts(self,task,items,resolution=False):
        from .discovery import normalize
        engine=task['strategy'];p=task['payload'];offered=0
        origin={'query':p['query'],'page':p.get('page',1),'region':p.get('region'),'provider':self.store.settings()['provider'],
                'task_id':task['id'],'acquisition':'resolution' if resolution else 'search',
                **{k:p.get(k) for k in ('family','segment','source_preference','strategy_version','strategy_id','demand_type','language','geography_tier','discovery_period')}}
        if resolution:origin.update(parent=p.get('resolution_url'),reason='Ricerca di una fonte ufficiale equivalente')
        records=[]
        for index,item in enumerate(items):
            aid=digest(encode([self.generation,task['id'],task.get('attempts',0),index,item.get('url')]))
            record={**normalize(item,origin),'appearance_id':aid,'decision':'not_processed','reason':'not_processed_stop','priority':0,'source_kind':'not_checked'}
            self.trace(engine,record,receipt=True);records.append((item,record))
        annotate(returned_urls=len(items),new_urls=0)
        return records
    def receive(self,task,items,check,resolution=False):
        records=self.receipts(task,items,resolution);engine=task['strategy'];p=task['payload'];offered=0
        for item,record in records:
            origin=record['origin']
            check()
            if resolution:
                from .discovery import classify
                from .indexed_jobs import resolution_continuity
                continuity=resolution_continuity(p,item)
                if blocked(item.get('url','')) or continuity['status']!='SUPPORTED':
                    self.trace(engine,{**record,'decision':'exclude','reason':continuity['reason'] if continuity['status']!='SUPPORTED' else 'resolution_source_incompatible','resolution':continuity});continue
                item={**item,'resolution_company':p['resolution_company'],'resolution_role':p['resolution_role'],'resolution_stage':p.get('resolution_stage'),'resolution_source':p['resolution_url']}
            offered+=self.offer(engine,{**item,'appearance_id':record['appearance_id']},origin)
            annotate(new_urls=offered)
        return offered
    def offer(self,engine,item,origin):
        item={**item,'demand_version':self.campaign['filters'].get('demand_version'),'max_job_age_days':self.campaign['filters'].get('max_job_age_days',14)}
        record=assess(item,engine,origin)
        if record['decision']!='exclude':
            from .search_memory import decision as remembered
            memory=remembered(self.store,engine,record,now())
            if memory:
                self.trace(engine,{**record,**memory});return False
        if record['decision']!='exclude':
            from .recommendation_store import saved_activity_filter
            known=saved_activity_filter(self.store,item,engine,now())
            if known:
                record.update(decision='exclude',reason='job_activity_known_negative',job_activity=known)
        if record['decision']!='exclude' and blocked(record['url']) and record['source']=='web':
            from .discovery import linkedin_resolution
            resolution=linkedin_resolution(item)
            if resolution and resolution['indexed_job'].get('contract_hint')=='external':
                record.update(decision='indexed_hint',accessibility='indexed_only',reason='Fonte bloccata: indizio conservato, ricerca della fonte ufficiale autorizzata.')
                self.trace(engine,record)
                try:self.enqueue('resolve',engine,{**resolution,'origin':origin},'commercial-resolve:'+digest(engine+resolution['query']))
                except BudgetExceeded as exc:self.rs.event(self.cid,'budget',str(exc),record['url'],{'engine':engine})
                return False
        if record['decision']=='exclude' or (blocked(record['url']) and record['source']=='web'):
            if record['decision']!='exclude':record.update(decision='exclude',reason='inaccessible_policy')
            self.trace(engine,record);self.rs.event(self.cid,'preflight',record['reason'],record['url'],record);return False
        url=record['url'];source_kind=record['source_kind']
        from .discovery import linkedin_resolution

        # Cache commercial decisions only within the same engine/rule version.
        # Legacy decisions cannot suppress a new engine's evaluation.
        with self.store.connect() as c:
            n=c.execute("SELECT count(*) FROM research_tasks WHERE campaign_id=? AND strategy=? AND kind='candidate'",(self.cid,engine)).fetchone()[0]
            recent=c.execute("SELECT r.body FROM commercial_revisions r JOIN commercial_opportunities o ON o.id=r.opportunity_id WHERE o.engine=? AND json_extract(r.body,'$.url')=? AND json_extract(r.body,'$.rule_version')=? AND r.created_at>? AND r.state IN ('VERIFIED','POTENTIAL','REJECTED') ORDER BY r.id DESC LIMIT 1",
              (engine,url,VERSIONS[engine],(datetime.now(timezone.utc)-timedelta(days=7)).isoformat())).fetchone()
        if recent and not (item.get('content_hash') and item['content_hash'] not in str(recent[0])):
            self.trace(engine,{**record,'decision':'memory','reason':'Recent decision, same rule version'})
            self.rs.event(self.cid,'memory','URL già valutato con queste regole negli ultimi 7 giorni; esito conservato nello storico.',url,{'engine':engine});return False
        if reason:=self.rs.suppressed({'website':url}):
            self.trace(engine,{**record,'decision':'exclude','reason':reason});self.rs.event(self.cid,'memory',reason,url,{'engine':engine});return False
        payload={**item,'url':url,'origin':origin,'discovery':record,'source_kind':source_kind,'social':record['source'] if record['source']!='web' else None,'allowed_regions':self.campaign['filters'].get('regions'),'depth':int(item.get('depth',0)),'search_version':self.campaign['filters'].get('search_version')}
        try:accepted=self.enqueue('candidate',engine,payload,'commercial-url:'+digest(engine+str(VERSIONS[engine])+url))
        except BudgetExceeded as exc:
            self.trace(engine,{**record,'decision':'budget','reason':str(exc)});return False
        self.trace(engine,record if accepted else {**record,'decision':'duplicate','reason':'Candidato già in coda'})
        if accepted and (record['source']=='linkedin' or record['source_kind']=='job_portal'):
            resolution=linkedin_resolution(item)
            if resolution:
                try:self.enqueue('resolve',engine,{**resolution,'origin':origin},'commercial-resolve:'+digest(engine+resolution['query']))
                except BudgetExceeded as exc:self.rs.event(self.cid,'budget',str(exc),url,{'engine':engine})
        return accepted
    def execute(self,task,check):
        budget=Budget(self.store,self.campaign,task['strategy'],self.budget)
        budget.task_id=task.get('id')
        budget.on_results=lambda items:self.receipts(task,items,resolution=task['kind']=='resolve')
        with budget.task(check) as guard:return self._execute(task,guard)
    def _execute(self,task,check):
        engine=task['strategy'];payload=task['payload'];check()
        if task['kind']=='resolve':
            items=acquire(self.store,payload,check)
            offered=self.receive(task,items,check,resolution=True)
            # A failed official-source lookup must not replace the indexed
            # opportunity with a generic access error lacking its saved hints.
            if not offered:self.rs.event(self.cid,'resolution_incomplete','Fonte originale autorizzata non risolta; indizio iniziale conservato.',payload['resolution_url'],{'engine':engine,'query':payload['query'],'task_id':task['id']})
            self.rs.event(self.cid,'resolution',f'{offered} domini candidati da verificare; identità ufficiale non ancora confermata.',payload['resolution_url'],{'engine':engine})
        elif task['kind']=='search':
            items=acquire(self.store,payload,check)
            fresh=self.receive(task,items,check)
            self.rs.event(self.cid,'search',f'{ENGINES[engine]}: {len(items)} URL, {fresh} nuovi candidati.',details={'engine':engine,'query':payload['query'],'page':payload.get('page',1)})
            if len(items)>=10 and payload.get('page',1)<self.budget['max_pages'] and paginate(self.store,self.cid,engine,payload['query']):
                page={**payload,'page':payload.get('page',1)+1}
                self.enqueue('search',engine,page,'commercial-query:'+digest(engine+query_key(page['query'])+':'+str(page['page'])))
        elif task['kind']=='source':
            entries=RSS(ResearchWeb(self.store,check)).entries(payload['url']);check()
            for item in entries:self.offer(engine,item,{'feed':payload['url']})
        else:
            from .admission import exclusion
            if reason:=exclusion(payload.get('discovery') or payload,engine):
                self.trace(engine,{**(payload.get('discovery') or payload),'decision':'exclude','reason':reason})
                self.rs.event(self.cid,'preflight',reason,payload['url'],{'stage':'before_read_or_retry','engine':engine})
                return
            from .recommendation_store import saved_activity_filter
            saved_activity=saved_activity_filter(self.store,payload,engine,now())
            if saved_activity:
                self.trace(engine,{**(payload.get('discovery') or payload),'decision':'exclude','reason':'job_activity_known_negative','job_activity':saved_activity})
                self.rs.event(self.cid,'activity_filter','Verifica evitata: osservazioni già disponibili.',payload['url'],{'engine':engine,'activity':saved_activity})
                return
            if payload.get('no_fetch'):
                self.record_failure(task,ValueError('Fonte non consultabile: indizi insufficienti per risolvere il committente; nessuna richiesta alla pagina.'));return
            require_non_pdf(payload)
            if payload.get('social'):
                from .social import inspect_social
                result=inspect_social(self.store,payload,check)
            else:result=inspect(self.store,payload,check)
            check()
            result['result']['discovery']=payload.get('discovery',payload.get('origin',{}))
            result['result']['identity']=result['identity']
            if payload.get('demand_version')=='5.1' and engine!='WEBSITE_REBUILD' and not result['result'].get('demand_assessment'):
                from .demand import assess as demand_assess,source_from_document,apply as apply_demand
                hint=result['result'].get('discovery') or {}
                original=next((d for d in result['documents'] if d.get('url')==result['result'].get('url') and d.get('text')),None)
                source=source_from_document(original) if original else {**hint,'original':False,'text':hint.get('content') or hint.get('snippet','')}
                assessment=demand_assess(source,result['identity'],result['result'])
                if original:apply_demand(result['result'],assessment)
                else:result['result']['demand_assessment']=assessment
            geography=result['result'].setdefault('geography',{})
            geography['query_region']=payload.get('origin',{}).get('region')
            geography['selected_regions']=payload.get('allowed_regions',self.campaign['filters'].get('regions'))
            geography['company_regions']=list(dict.fromkeys(l['region'] for l in geography.get('locations',[]) if l.get('kind')=='company' and l.get('region')))
            geography['project_regions']=list(dict.fromkeys(l['region'] for l in geography.get('locations',[]) if l.get('kind')=='opportunity' and l.get('region')))
            oid=self.repo.save(self.campaign,result['identity'],result['documents'],result['result'])
            # Official deterministic revision is durable before optional AI.
            # AI records are separate; Stop rejects late outputs and no advisory
            # response can directly write a CRM state or trigger another search.
            from .job_activity import evaluate as activity
            activity_result=activity(result['result'],engine,now(),max_age_days=payload.get('max_job_age_days',14))
            skip_deepening=activity_result['category']=='archived' and not activity_result['conflicts']
            if oid and not skip_deepening:
                from .ai import analyze
                try:analyze(self.store,self.campaign,engine,oid,result['result'],result['documents'],check=check)
                except (InterruptedError,BudgetExceeded):raise
                except Exception:
                    # Unexpected adapter/serialization faults must not replace
                    # the durable official decision or expose provider payloads.
                    self.rs.event(self.cid,'ai_fallback','Analisi AI non disponibile; valutazione deterministica conservata.',payload['url'],{'engine':engine,'opportunity_id':oid})
            check()
            self.rs.event(self.cid,'decision',result['result']['reason'],payload['url'],{'engine':engine,'state':result['result']['state'],'opportunity_id':oid,'origin':payload.get('origin',{})})
            if skip_deepening:
                self.rs.event(self.cid,'activity_filter','Approfondimenti AI e follow-up evitati: '+', '.join(activity_result['reasons']),payload['url'],{'engine':engine,'activity':activity_result})
                return
            if result['result'].get('classification')=='publisher_unresolved' and not payload.get('resolution_company'):
                from .indexed_jobs import actor_resolution
                plan=actor_resolution(result['result'])
                if plan:
                    try:self.enqueue('resolve',engine,{**plan,'origin':payload.get('origin',{})},'commercial-resolve-actor:'+digest(engine+plan['resolution_company'].casefold()))
                    except BudgetExceeded as exc:self.rs.event(self.cid,'budget',str(exc),payload['url'],{'engine':engine})
            if payload.get('depth',0)<3:
                for link in result['followups']:
                    if payload.get('depth',0)>=1 and not link.get('ats_binding'):continue
                    if not followup_allowed(result['result'],link):continue
                    target=link.get('engine',engine)
                    if target not in self.engines:continue
                    resolution_fields={k:payload[k] for k in ('resolution_company','resolution_role','resolution_stage','resolution_source') if k in payload} if result['identity'].get('resolution',{}).get('official_domain_verified') else {}
                    title=(str(resolution_fields.get('resolution_company',''))+' '+link.get('anchor','')).strip()
                    self.offer(target,{'url':link['url'],'title':title,'content':' '.join(e['quote'] for e in result['result'].get('evidence',[]) if e.get('url')==link['url']), 'depth':payload.get('depth',0)+1,**resolution_fields,**({'ats_binding':link['ats_binding']} if link.get('ats_binding') else {})},{**payload.get('origin',{}),**link,'acquisition':'followup','parent':payload['url'],'parent_task':task.get('id'),'company':result['identity'].get('name'),'role':result['result'].get('skills'),'commercial_context':result['result'].get('reason')})
            if result['result'].get('deferred_resource'):
                return {'deferred_resource':result['result']['deferred_resource']}
    def record_failure(self,task,error):
        from .evaluation import base
        if isinstance(error,(ExcludedPDF,BudgetExceeded)):return
        if task['kind']!='candidate':return
        p=task['payload'];identity={'name':domain(p['url']),'website':p['url'],'identity_status':'unknown','contacts':[],'source_url':p['url']}
        geo={'eligible':False,'regions':[],'locations':[],'country':None,'remote_italy':False,'reason':'Località non verificabile'}
        page={'url':p['url'],'html':'','checked_at':now(),'status':0}
        result=base(task['strategy'],identity,page,geo)
        from sales.access_status import describe
        result.update(state='UNVERIFIABLE',classification='access_incomplete',reason=safe_error(error),discovery=p.get('discovery',p.get('origin',{})),
                      verification={'status':'incomplete','scope':'access'},access=describe(error) or {'code':'source_or_extraction','retryable':False})
        self.repo.save(self.campaign,identity,[],result)

def run_campaign(store,campaign,check,progress):
    cls=Coordinator
    if campaign['filters'].get('agent_version')=='6.0':
        from sales.agent6.coordinator import AgentCoordinator
        cls=AgentCoordinator
    worker=cls(store,campaign);rs=worker.rs;worker.initialize()
    while True:
        check();current=rs.campaign(campaign['id'])
        if current['useful_companies']>=campaign['target']:
            rs.finish(worker.cid,worker.generation,'completed','Obiettivo raggiunto: aziende con richieste documentate o opportunità potenziali, distinte nei risultati.');return
        worker.tick();task=rs.claim(worker.cid,worker.generation)
        if not task:
            with store.connect() as c:
                pending=c.execute("SELECT min(available_at) FROM research_tasks WHERE campaign_id=? AND state='pending'",(worker.cid,)).fetchone()[0]
                failed=c.execute("SELECT 1 FROM research_tasks WHERE campaign_id=? AND state IN ('failed','blocked') LIMIT 1",(worker.cid,)).fetchone()
            if pending:
                if hasattr(worker,'hard_budget_exhausted') and worker.hard_budget_exhausted():
                    state,message=worker.terminal_state()
                    rs.finish(worker.cid,worker.generation,state,message);return
                from .retry_policy import park_until_manual_resume
                if park_until_manual_resume(pending):
                    rs.finish(worker.cid,worker.generation,'blocked','Verifiche differite: le fonti richiedono una pausa. Riprendi dopo '+pending+'; risultati conservati, nessun tentativo durante il blocco.');return
                rs.progress(worker.cid,worker.generation,'In attesa del prossimo tentativo autorizzato: '+pending,'waiting',pending);time.sleep(.2);continue
            if hasattr(worker,'terminal_state'):
                state,message=worker.terminal_state()
                rs.finish(worker.cid,worker.generation,state,message)
            else:
                rs.finish(worker.cid,worker.generation,'blocked' if failed else 'exhausted','Lavoro disponibile concluso. Alcuni controlli non riusciti sono riprendibili.' if failed else 'Strategie o budget operativi completati. Nessun riempimento automatico dei risultati.')
            return
        try:
            progress(ENGINES.get(task['strategy'],task['strategy'])+' · '+task['payload'].get('query',task['payload'].get('url','')))
            with measure(rs,campaign,task):execution=worker.execute(task,check)
            check()
            if isinstance(execution,dict) and execution.get('deferred_resource'):
                resource=execution['deferred_resource']
                with store.connect() as c:
                    c.execute("UPDATE research_tasks SET state='budget',error=?,updated_at=? WHERE id=?",(str(BudgetExceeded(resource)),now(),task['id']))
                rs.event(worker.cid,'budget','Verifica differita: '+resource+'. Gli altri controlli proseguono.',task['payload'].get('url'),{'engine':task['strategy'],'resource':resource,'task_id':task['id'],'scope':'task'})
            else:rs.task_done(task['id'])
        except InterruptedError:raise
        except ExcludedPDF as exc:
            rs.event(worker.cid,'excluded_pdf','excluded_pdf',exc.url or task['payload'].get('url'),{'engine':task['strategy'],'task_id':task['id']})
            with store.connect() as c:c.execute("UPDATE research_tasks SET state='excluded',error='excluded_pdf',updated_at=? WHERE id=?",(now(),task['id']))
        except BudgetExceeded as exc:
            rs.event(worker.cid,'budget',str(exc),details={'engine':task['strategy'],'resource':exc.resource})
            with store.connect() as c:
                if exc.resource=='browser_runs':
                    c.execute("UPDATE research_tasks SET state='budget',error=?,updated_at=? WHERE id=?",(str(exc),now(),task['id']))
                    continue
                c.execute("UPDATE commercial_engine_runs SET state='budget_reached',error=? WHERE campaign_id=? AND engine=?",(str(exc),worker.cid,task['strategy']))
                # A provider quota does not prevent already discovered HTTP
                # candidates from completing; only dependent tasks are parked.
                kinds=('search','resolve') if exc.resource in ('queries','provider_requests','serper_estimated','followups','pages_per_query') else ('candidate','source','social_resolve') if exc.resource=='http_reads' else ('candidate',) if exc.resource=='browser_runs' else ('search','resolve','candidate','source','social_resolve')
                if campaign['filters'].get('agent_version')=='6.0':kinds=(*kinds,'agent_plan')
                placeholders=','.join('?' for _ in kinds)
                c.execute("UPDATE research_tasks SET state='budget',error=? WHERE campaign_id=? AND strategy=? AND state IN ('pending','working') AND kind IN ("+placeholders+")",(str(exc),worker.cid,task['strategy'],*kinds))
        except Exception as exc:
            check();error=safe_error(exc);outcome=error_outcome(exc,task['kind'])
            rs.event(worker.cid,'engine_error',error,task['payload'].get('url'),{'engine':task['strategy'],**outcome})
            worker.record_failure(task,exc)
            retry=outcome['retryable'] and task['attempts']<3
            from .retry_policy import retry_at
            rs.task_done(task['id'],error,retry=retry,retry_at=retry_at(exc,health(store).get('retry_at') if task['kind']=='search' else None))
            if task['kind']=='search' and not retry:
                # Freeze only this planner; remaining engines and queued pages run.
                with store.connect() as c:c.execute("UPDATE commercial_engine_runs SET state='blocked',error=? WHERE campaign_id=? AND engine=?",(error,worker.cid,task['strategy']))
