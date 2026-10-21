"""Atomic per-engine resource reservations; cache hits never reserve paid calls.

Task runtime is leased up front and unused time refunded on graceful exit.
After process death the unreturned lease remains charged (conservative).
"""
import time,math
from contextvars import ContextVar
from contextlib import contextmanager
from sales.db import now

_context=ContextVar('commercial_resources',default=None)
LIMITS={'queries':'max_queries_per_engine','provider_requests':'max_provider_requests','serper_estimated':'max_serper_credits','http_reads':'max_http_reads','followups':'max_followups','candidates':'max_candidates_per_engine','browser_runs':'max_browser_runs','runtime_seconds':'max_runtime_seconds'}
class BudgetExceeded(ValueError):
    def __init__(self,resource):
        self.resource=resource
        super().__init__('Budget operativo esaurito: '+resource)

class Budget:
    def __init__(self,store,campaign,engine,limits):
        self.store=store;self.cid=campaign['id'];self.generation=campaign['generation'];self.engine=engine;self.limits=limits
    def reserve(self,resource,amount=1,connection=None):
        def write(c):
            if not c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(self.cid,self.generation)).fetchone():raise InterruptedError('Campagna sospesa')
            row=c.execute('SELECT used FROM commercial_resources WHERE campaign_id=? AND engine=? AND resource=?',(self.cid,self.engine,resource)).fetchone()
            used=row[0] if row else 0
            if used+amount>self.limits[LIMITS[resource]]:raise BudgetExceeded(resource)
            c.execute('INSERT INTO commercial_resources VALUES (?,?,?,?,?) ON CONFLICT(campaign_id,engine,resource) DO UPDATE SET used=used+excluded.used,updated_at=excluded.updated_at',(self.cid,self.engine,resource,amount,now()))
        if connection is not None:return write(connection)
        with self.store.connect() as c:c.execute('BEGIN IMMEDIATE');write(c)
    def browser_continuation(self,connection=None):
        if not getattr(self,'task_id',None):return False
        def read(c):
            import json
            row=c.execute('SELECT payload FROM research_tasks WHERE id=? AND campaign_id=?',(self.task_id,self.cid)).fetchone()
            marker=json.loads(row[0]).get('_browser_slot',{}) if row else {}
            return marker.get('state')=='interrupted' and marker.get('attempts',0)<2
        if connection is not None:return read(connection)
        with self.store.connect() as c:return read(c)
    def browser_slot(self):
        if not getattr(self,'task_id',None):return self.reserve('browser_runs')
        import json
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(self.cid,self.generation)).fetchone():raise InterruptedError('Campagna sospesa')
            row=c.execute('SELECT payload FROM research_tasks WHERE id=? AND campaign_id=?',(self.task_id,self.cid)).fetchone()
            if not row:return self.reserve('browser_runs',connection=c)
            payload=json.loads(row[0]);marker=payload.get('_browser_slot',{})
            if marker and not self.browser_continuation(c):raise BudgetExceeded('browser_runs')
            if not marker:self.reserve('browser_runs',connection=c)
            payload['_browser_slot']={'state':'started','attempts':marker.get('attempts',0)+1}
            c.execute('UPDATE research_tasks SET payload=? WHERE id=?',(json.dumps(payload),self.task_id))
    def browser_finished(self,interrupted=False):
        if not getattr(self,'task_id',None):return
        import json
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT payload FROM research_tasks WHERE id=? AND campaign_id=?',(self.task_id,self.cid)).fetchone()
            if not row:return
            payload=json.loads(row[0]);marker=payload.get('_browser_slot')
            if not marker:return
            marker['state']='interrupted' if interrupted else 'finished'
            c.execute('UPDATE research_tasks SET payload=? WHERE id=?',(json.dumps(payload),self.task_id))
    def used(self,resource):
        with self.store.connect() as c:
            r=c.execute('SELECT used FROM commercial_resources WHERE campaign_id=? AND engine=? AND resource=?',(self.cid,self.engine,resource)).fetchone()
        return r[0] if r else 0
    def paid(self):
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE');self.reserve('provider_requests',connection=c);self.reserve('serper_estimated',connection=c)
    @contextmanager
    def task(self,check):
        lease=min(300,self.limits['max_runtime_seconds']-self.used('runtime_seconds'))
        if lease<=0:raise BudgetExceeded('runtime_seconds')
        self.reserve('runtime_seconds',lease);start=time.monotonic();self.deadline=start+lease
        def guard():
            check()
            if time.monotonic()-start>=lease:raise BudgetExceeded('runtime_seconds')
        token=_context.set(self)
        try:guard();yield guard
        finally:
            _context.reset(token)
            refund=max(0,lease-max(1,math.ceil(time.monotonic()-start)))
            if refund:
                with self.store.connect() as c:c.execute('UPDATE commercial_resources SET used=max(0,used-?),updated_at=? WHERE campaign_id=? AND engine=? AND resource=?',(refund,now(),self.cid,self.engine,'runtime_seconds'))

def reserve(resource):
    current=_context.get()
    if current:current.reserve(resource)

def paid_request():
    current=_context.get()
    if current:current.paid()

def snapshot(store,cid,limits):
    with store.connect() as c:rows=c.execute('SELECT engine,resource,used FROM commercial_resources WHERE campaign_id=?',(cid,)).fetchall()
    result={}
    for r in rows:result.setdefault(r['engine'],{})[r['resource']]={'used':r['used'],'limit':limits[LIMITS[r['resource']]]}
    return result


def timeout(maximum):
    current=_context.get()
    if not current or not hasattr(current,'deadline'):return maximum
    remaining=current.deadline-time.monotonic()
    if remaining<=0:raise BudgetExceeded('runtime_seconds')
    return min(maximum,remaining)


RESOURCE_LABELS={'queries':'query','candidates':'candidati','runtime_seconds':'tempo di lavoro','http_reads':'letture web','followups':'collegamenti di approfondimento','provider_requests':'richieste al provider','serper_estimated':'crediti Serper stimati','browser_runs':'analisi browser','pages_per_query':'pagine della query'}

def availability(store,cid,limits,engines):
    """Read-only projection; exhausted discovery may still have accepted work."""
    with store.connect() as c:
        runs=[dict(r) for r in c.execute('SELECT * FROM commercial_engine_runs WHERE campaign_id=?',(cid,))]
        rows=c.execute('SELECT engine,resource,used FROM commercial_resources WHERE campaign_id=?',(cid,)).fetchall()
        tasks=c.execute("SELECT strategy,kind,state FROM research_tasks WHERE campaign_id=? AND state IN ('pending','working','failed','blocked')",(cid,)).fetchall()
    import json
    with store.connect() as c:filters=json.loads(c.execute('SELECT filters FROM campaigns WHERE id=?',(cid,)).fetchone()[0])
    deep=filters.get('demand_version')=='5.1'
    used={(r['engine'],r['resource']):r['used'] for r in rows}
    details=[];can_resume=False
    for engine in engines:
        run=next((r for r in runs if r['engine']==engine),{})
        remaining=lambda key:max(0,limits[LIMITS[key]]-used.get((engine,key),0))
        exhausted=[key for key in LIMITS if not remaining(key)]
        recorded=next((key for key in LIMITS if (run.get('error') or '').endswith(': '+key)),None)
        if run.get('state')=='budget_reached' and not recorded:recorded=next(iter(exhausted),None)
        time_ok=remaining('runtime_seconds')>0
        search_ok=time_ok and all(remaining(k)>0 for k in ('queries','candidates','provider_requests','serper_estimated')) and run.get('state') not in ('exhausted','budget_reached')
        queue_ok=any(t['strategy']==engine and time_ok and ((t['kind'] in ('candidate','source','social_resolve') and remaining('http_reads')>0) or (t['kind'] in ('search','resolve') and remaining('provider_requests')>0 and remaining('serper_estimated')>0)) for t in tasks)
        possible=search_ok or queue_ok;can_resume|=possible
        details.append({'engine':engine,'queries_remaining':remaining('queries'),'exhausted_resource':recorded,
                        'budget_reason':(('Quota di approfondimenti raggiunta: '+str(used.get((engine,'candidates'),0))+' / '+str(limits['max_candidates_per_engine'])+'. Prefiltri separati; limiti di query e servizi invariati.') if deep and recorded=='candidates' else 'Limite del motore raggiunto: '+RESOURCE_LABELS[recorded]+'. Non indica il saldo Serper.') if recorded else '',
                        'resume_available':bool(possible)})
    return {'resume_available':bool(can_resume),'resume_reason':('Riprendi continua il lavoro disponibile senza azzerare le quote.' if can_resume else 'Nessun lavoro riprendibile con le quote attuali. Avvia una nuova ricerca con limiti adeguati; i risultati restano conservati.'),'engine_budget':details}


def received_results(items):
    current=_context.get()
    if current and hasattr(current,'on_results'):current.on_results(items)


def headroom(limits=None):
    """Per-engine remaining resources, including reservations made by siblings."""
    current=_context.get()
    from .catalog import BUDGETS
    cfg=current.limits if current else {**BUDGETS,**(limits or {})}
    room={r:max(0,cfg[LIMITS[r]]-(current.used(r) if current else 0)) for r in ('http_reads','browser_runs')}
    if current and current.browser_continuation():room['browser_runs']=max(1,room['browser_runs'])
    return room


def stage_plan(limits=None):
    room=headroom(limits)
    reserve=min(60,room['http_reads']) if room['browser_runs'] else 0
    return {'policy':'identity_then_browser_before_optional_reads','stages':['DISCOVERY','IDENTITY_CHECK','HTTP_SCREENING','BROWSER_AUDIT','FINAL_EVALUATION'],
            'http_remaining':room['http_reads'],'browser_runs_remaining':room['browser_runs'],
            'browser_http_headroom':reserve,'optional_http_allowance':max(0,room['http_reads']-reserve),
            'reservation_kind':'sequential_task_headroom_not_consumed_quota'}


def deep_review_slot():
    """Reserve once per persisted task, including retries/resume. Same limit."""
    current=_context.get()
    if not current:return
    if not getattr(current,'task_id',None):return current.reserve('candidates')
    import json
    with current.store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT payload FROM research_tasks WHERE id=? AND campaign_id=?',(current.task_id,current.cid)).fetchone()
        if not row:raise InterruptedError('Task non più disponibile')
        payload=json.loads(row[0])
        if payload.get('_deep_review_reserved'):return
        current.reserve('candidates',connection=c)
        payload['_deep_review_reserved']=True
        c.execute('UPDATE research_tasks SET payload=? WHERE id=?',(json.dumps(payload),current.task_id))
