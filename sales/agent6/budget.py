"""Dynamic reservations inside configured maxima; no budget or credit changes.

Stage allocations are planning hints. Only actual pending verifications and a
minimum first cycle for other flows reserve capacity, not empty stage buckets.
The shared ledger still atomically enforces cost, concurrency and hard maxima.
"""
import json,math
from sales.commercial.ai import _reserve
from sales.db import now

STAGES=('plan','screen','verify','replan')

def purpose(payload):
    """Detailed reporting purpose; shares the existing atomic budget pools."""
    if payload['task']=='DISCOVERY_TRIAGE_1':return 'discovery_source_selection'
    if payload.get('repair'):return 'targeted_recovery'
    if payload.get('completion_goal') and any(e.get('original') for e in payload.get('evidence',[])):return 'dossier_completion'
    if payload['task'] in ('WEBSITE_OPPORTUNITY_REVIEW_8','NEWS_OPPORTUNITY_REVIEW_8'):return 'website_audit_interpretation'
    if payload['task']=='RESEARCH_PLAN_6':return 'discovery_replanning' if payload.get('round',0) else 'discovery_planning'
    return 'original_verification' if any(e.get('original') for e in payload.get('evidence',[])) else 'initial_screening'

def stage_for(key,payload):
    if payload['task'] in ('WEBSITE_OPPORTUNITY_REVIEW_8','NEWS_OPPORTUNITY_REVIEW_8'):return 'verify'
    if payload['task']=='RESEARCH_PLAN_6':return 'replan' if payload.get('round',0)>0 else 'plan'
    return 'verify' if any(e.get('original') for e in payload.get('evidence',[])) else 'screen'

def allocation(campaign,cfg,flow):
    flows=list(dict.fromkeys(campaign['filters'].get('commercial_engines') or [flow]))
    total=cfg['max_calls_per_campaign']
    if cfg['provider']=='REMOTE':
        rates=(cfg['input_cost_per_million'],cfg['output_cost_per_million'])
        if None in rates:total=0
        else:
            cost=(cfg['max_input_tokens']*rates[0]+cfg['max_output_tokens']*rates[1])/1e6
            if cost:total=min(total,math.floor((cfg['max_estimated_cost']+1e-12)/cost))
    # Fair persistent allocation: an early flow cannot spend another flow's start.
    index=flows.index(flow) if flow in flows else len(flows)
    share=total//len(flows)+int(index<total%len(flows)) if flow in flows else 0
    n=min(cfg['max_calls_per_engine'],share)
    caps=dict.fromkeys(STAGES,0)
    if n:caps['plan']=1
    if n>=2:caps['verify']=1
    if n>=3:caps['screen']=1
    if n>=4:caps['replan']=1
    for i in range(max(0,n-4)):caps['verify' if i%2==0 else 'screen']+=1
    return caps

def row_stage(row):
    body=json.loads(row['body'] or '{}')
    if body.get('stage') in STAGES:return body['stage']
    # Count legacy 6.0 attempts on resume without rewriting the ledger.
    key=row['candidate_id']
    if key.startswith('plan:'):return 'plan' if key=='plan:0' else 'replan'
    if key.startswith('batch:'):return 'screen'
    if key.startswith('page:'):return 'verify'
    return None


def initial_plan_repair(c,campaign,flow,flow_plans):
    """One repair of a rejected/empty first cycle, not generic exploration."""
    if flow_plans!=1:return False
    receipts=c.execute("SELECT body FROM agent6_memory WHERE campaign_id=? AND flow=? AND kind='query'",
                       (campaign['id'],flow)).fetchall()
    if receipts:
        # C47 SOCIAL had one successful zero-result search and no original to
        # verify. Another flow's recovery must not erase its reserved start.
        # A nonempty receipt can still contain only inaccessible social hints
        # and excluded source routes (C48). That is not evidence of no demand:
        # permit one change of strategy, never repeated access attempts.
        if len(receipts)!=1:return False
        receipt=json.loads(receipts[0]['body'])
        if receipt.get('technical_error'):return False
        if receipt.get('results')==0:return True
        count=receipt.get('results')
        inaccessible=receipt.get('indexed_unverifiable',0)
        excluded=receipt.get('policy_rejections',[])
        if type(count) is not int or count<=0 or type(inaccessible) is not int or inaccessible<0 or not isinstance(excluded,list):return False
        accounted=inaccessible+len(excluded)
        if receipt.get('new_urls')!=0 or accounted!=count:return False
        if c.execute("""SELECT 1 FROM research_tasks WHERE campaign_id=? AND strategy=?
            AND state IN ('pending','working') AND kind IN ('candidate','search','agent_screen') LIMIT 1""",
            (campaign['id'],flow)).fetchone():return False
        return not c.execute("""SELECT 1 FROM commercial_ai_executions WHERE campaign_id=?
            AND engine=? AND attempt=1 AND json_extract(body,'$.stage')='verify' LIMIT 1""",
            (campaign['id'],flow)).fetchone()
    row=c.execute("SELECT body FROM agent6_memory WHERE campaign_id=? AND flow=? AND kind='plan' ORDER BY id DESC LIMIT 1",
                  (campaign['id'],flow)).fetchone()
    if not row:return False
    plan=json.loads(row['body'])
    return plan.get('queries')==[] and plan.get('chosen') is None and bool(plan.get('rejected_queries') or plan.get('invalid_proposals'))


def global_limit_reasons(cfg,rows):
    """Hard campaign limits cannot be recovered by waiting for a web origin."""
    reasons=[]
    if len(rows)>=cfg['max_calls_per_campaign']:
        reasons.append({'code':'ai_campaign_calls','used':len(rows),'limit':cfg['max_calls_per_campaign']})
    if cfg['provider']=='REMOTE':
        rates=(cfg['input_cost_per_million'],cfg['output_cost_per_million'])
        if None not in rates:
            spent=sum(max(r['reserved_cost'],r['reported_cost'] or 0) for r in rows)
            reservation=(cfg['max_input_tokens']*rates[0]+cfg['max_output_tokens']*rates[1])/1e6
            if spent+reservation>cfg['max_estimated_cost']+1e-12:
                reasons.append({'code':'ai_cost_capacity','reserved_or_spent_usd':spent,
                                'next_reservation_usd':reservation,'limit_usd':cfg['max_estimated_cost']})
    return reasons

def available(c,campaign,flow,cfg,stage,rows):
    flows=list(dict.fromkeys(campaign['filters'].get('commercial_engines') or [flow]))
    counts={f:sum(r['engine']==f for r in rows) for f in flows}
    total_left=max(0,cfg['max_calls_per_campaign']-len(rows))
    if cfg['provider']=='REMOTE':
        rates=(cfg['input_cost_per_million'],cfg['output_cost_per_million'])
        if None in rates:return 0
        per_call=(cfg['max_input_tokens']*rates[0]+cfg['max_output_tokens']*rates[1])/1e6
        spent=sum(max(r['reserved_cost'],r['reported_cost'] or 0) for r in rows)
        if per_call:total_left=min(total_left,max(0,math.floor((cfg['max_estimated_cost']-spent+1e-12)/per_call)))
    engine_left=max(0,cfg['max_calls_per_engine']-counts.get(flow,0))
    if campaign['filters'].get('decision_engine')=='ai_first_1':
        # Bounded planning cannot eat the original-evaluation pool. These are
        # ceilings within unchanged configured maxima, not extra purchased calls.
        if stage=='screen':
            # One bounded SERP batch per flow in new campaigns. Leave capacity
            # for a first original read in this flow as well as other flows.
            if (campaign['filters'].get('discovery_triage_version')!=1 or
                    any(r['engine']==flow and row_stage(r)=='screen' for r in rows) or
                    engine_left<2 or total_left<2):return 0
        planning=sum(row_stage(r) in ('plan','replan') for r in rows)
        if stage in ('plan','replan'):
            # Inside the SAME total ceiling, leave room for one targeted repair
            # per flow when the configured capacity permits. C44 used the entire
            # planning allowance just starting its five flows.
            planning_cap=min(cfg['max_calls_per_campaign'],
                             max(len(flows), min(2*len(flows), cfg['max_calls_per_campaign']//3)))
            flow_plans=sum(r['engine']==flow and row_stage(r) in ('plan','replan') for r in rows)
            # C46 used the single ordinary recovery slot on AGENCIES and then
            # rejected NEWS before it had one executable query. A first-plan
            # repair may use its own reserved start, still within every shared
            # cap and at most two planning calls for that flow.
            first_repair=stage=='replan' and initial_plan_repair(c,campaign,flow,flow_plans)
            if (planning>=planning_cap and not first_repair) or flow_plans>=2:return 0
    if stage=='replan':
        # This check is also inside _reserve's atomic transaction: a planner
        # already queued cannot race a newly admitted original verification.
        from .scheduling import pending_verification,discovery_turn
        recovery=total_left>=2 and discovery_turn(c,campaign,flow,cfg,rows)
        if not recovery and pending_verification(c,campaign,cfg,rows,now()):return 0
    # A delayed origin retry cannot reserve the last slot against work that is
    # runnable now. Running work and the initial per-flow cycle remain protected;
    # when the retry becomes due, normal reservations apply again without reset.
    timestamp=now()
    pending={r['strategy']:r['n'] for r in c.execute("SELECT strategy,count(*) n FROM research_tasks WHERE campaign_id=? AND kind='candidate' AND (state='working' OR (state='pending' AND available_at<=?)) GROUP BY strategy",(campaign['id'],timestamp))}
    screening={r['strategy'] for r in c.execute("SELECT DISTINCT strategy FROM research_tasks WHERE campaign_id=? AND kind IN ('search','agent_screen') AND (state='working' OR (state='pending' AND available_at<=?))",(campaign['id'],timestamp))}
    runs={r['engine']:r['state'] for r in c.execute('SELECT engine,state FROM commercial_engine_runs WHERE campaign_id=?',(campaign['id'],))}
    reservations={};starts={}
    for f in flows:
        # Enough to start and inspect an original, proportionately when the
        # user deliberately configures a smaller shared maximum.
        first_cycle=min(3,sum(allocation(campaign,cfg,f).values()))
        start=max(0,first_cycle-counts[f]) if runs.get(f) not in ('blocked','exhausted','budget_reached') else 0
        if campaign['filters'].get('decision_engine')=='ai_first_1' and not pending.get(f) and f not in screening:
            from .scheduling import discovery_turn
            if not discovery_turn(c,campaign,f,cfg,rows):start=0
        # A queued search/screen still needs a screening call and potentially
        # an original read. Replanning elsewhere must not spend that path's
        # capacity before it can become a candidate task. One path per flow,
        # not one reservation per raw URL; release it when screening concludes.
        verify=min(pending.get(f,0)+(2 if f in screening else 0),max(0,cfg['max_calls_per_engine']-counts[f]))
        reservations[f]=max(start,verify)
        starts[f]=start
    if sum(reservations.values())>total_left:
        # When not every queued path fits, don't let each flow reserve all
        # remaining calls against every other flow (deadlock with credit left).
        # Allocate scarce slots deterministically, originals first, then flows
        # with fewer actual calls. Hard campaign/engine/cost caps still apply.
        granted=dict.fromkeys(flows,0)
        order=sorted(flows,key=lambda f:(not bool(pending.get(f)),counts[f],flows.index(f)))
        left=total_left
        if campaign['filters'].get('decision_engine')=='ai_first_1':
            completing={r['strategy'] for r in c.execute("""SELECT DISTINCT strategy
                FROM research_tasks WHERE campaign_id=?
                AND (state='working' OR (state='pending' AND available_at<=?))
                AND (json_extract(payload,'$.original_page.url') IS NOT NULL
                     OR json_extract(payload,'$.research_parent') IS NOT NULL
                     OR json_extract(payload,'$.browser_requested')=1
                     OR json_extract(payload,'$.selection')='verification')""",(campaign['id'],now()))}
            for f in order:
                if left and f in completing and reservations[f]:
                    granted[f]+=1;left-=1
            # Protect the first cycle BEFORE spreading spare slots over large
            # candidate queues. C45's originals-first scarce allocation erased
            # other flows' reservations precisely when they needed recovery.
            start_order=sorted(flows,key=lambda f:(counts[f],flows.index(f)))
            while left and any(granted[f]<starts[f] for f in flows):
                for f in start_order:
                    if left and granted[f]<starts[f]:granted[f]+=1;left-=1
        while left and any(granted[f]<reservations[f] for f in flows):
            for f in order:
                if left and granted[f]<reservations[f]:granted[f]+=1;left-=1
        reservations=granted
    protected=sum(v for f,v in reservations.items() if f!=flow)
    own_pending=min(pending.get(flow,0),engine_left) if stage!='verify' else 0
    own_original=1 if stage=='screen' and campaign['filters'].get('discovery_triage_version')==1 else 0
    return max(0,min(engine_left-own_pending-own_original,total_left-protected-own_pending-own_original))

def reserve(store,campaign,flow,key,payload,cfg,cachekey,cost,estimated_input):
    stage=stage_for(key,payload);caps=allocation(campaign,cfg,flow)
    identifier=('agent6:verify:'+key if stage=='verify' else 'agent6:'+stage+':'+flow+':'+key)
    def policy(c,rows):
        if stage=='verify' and sum(r['candidate_id'] in (identifier,key) for r in rows)>=cfg['max_calls_per_candidate']:return 'candidate_budget'
        if not available(c,campaign,flow,cfg,stage,rows):return 'capacity_reserved_for_pending_work'
    ident,denied=_reserve(store,campaign,flow,identifier,cfg,cachekey,payload['task'],cost,estimated_input,
        candidate_limit=stage=='verify',reservation_policy=policy,metadata={'stage':stage,'purpose':purpose(payload),'allocation':caps})
    return ident,denied,identifier,stage,caps

def remaining(store,campaign,flow,cfg,stage):
    with store.connect() as c:
        rows=c.execute('SELECT engine,candidate_id,body,reserved_cost,reported_cost FROM commercial_ai_executions WHERE campaign_id=? AND attempt=1',(campaign['id'],)).fetchall()
        return available(c,campaign,flow,cfg,stage,rows)
