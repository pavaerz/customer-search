"""Completion-first dispatch shared by the commercial channels.

Priorities are operational rules, never probabilities or sales estimates.
The caller owns the SQLite transaction: selection, claim and trace are atomic.
No HTTP, model calls, settings changes or historical reclassification here.
"""
import json
from . import budget


def pipeline_phase(task):
    if task['kind']=='agent_plan':return 'DISCOVERY'
    if task['kind']=='search':return 'DOSSIER_COMPLETION' if task.get('selection')=='verification' else 'DISCOVERY'
    if task['kind']=='agent_screen':return 'SCREENING'
    if task['kind']=='candidate':return 'ORIGINAL_VERIFICATION' if task.get('saved_original') else 'SOURCE_ACQUISITION'
    return 'FINALIZATION'


def stage(task):
    if task['kind'] == 'candidate':
        return 'verify'
    if task['kind'] == 'agent_plan':
        return 'replan' if task.get('round', 0) else 'plan'
    return 'screen'


def discovery_turn(c, campaign, flow, cfg, rows):
    """A bounded first discovery cycle, not unlimited priority for empty flows.

    C45's two populated queues consumed the slots of three empty-query flows.
    Allow those flows to reuse a proposal or replan before another *new* page,
    but never ahead of a saved original/targeted dossier completion. Two actual
    searches end this exception; transport errors are not commercial outcomes.
    """
    if campaign['filters'].get('decision_engine') != 'ai_first_1':return False
    first_cycle=min(3,sum(budget.allocation(campaign,cfg,flow).values()))
    if sum(r['engine']==flow for r in rows)>=first_cycle:return False
    run=c.execute('SELECT state FROM commercial_engine_runs WHERE campaign_id=? AND engine=?',
                  (campaign['id'],flow)).fetchone()
    if run and run['state'] in ('blocked','exhausted','budget_reached'):return False
    if c.execute("""SELECT 1 FROM research_tasks WHERE campaign_id=? AND strategy=?
        AND kind='candidate' AND state IN ('pending','working') LIMIT 1""",
        (campaign['id'],flow)).fetchone():return False
    receipts=c.execute("""SELECT body FROM agent6_memory WHERE campaign_id=?
        AND flow=? AND kind='query'""",(campaign['id'],flow)).fetchall()
    completed=[json.loads(r['body']) for r in receipts]
    return sum(isinstance(r.get('results'),int) and not r.get('technical_error')
               for r in completed)<2


def pending_verification(c, campaign, cfg, rows, timestamp):
    flows = c.execute("""SELECT DISTINCT strategy,kind FROM research_tasks
        WHERE campaign_id=? AND (kind='candidate' OR
          (kind='search' AND json_extract(payload,'$.selection')='verification') OR
          (kind='agent_screen' AND json_extract(payload,'$.parent.selection')='verification')) AND
        (state='working' OR (state='pending' AND available_at<=?))""",
        (campaign['id'], timestamp)).fetchall()
    # The completion path can temporarily be a search or indexed screening.
    # Protect it from replanning without relabelling snippets as original reads.
    return sorted({r['strategy'] for r in flows
            if budget.available(c, campaign, r['strategy'], cfg,
                                'verify' if r['kind']=='candidate' else 'screen', rows)})


def planning_hold(c, campaign, flow, timestamp):
    """Hold new plans while useful work is executable; stop futile local loops.

Three consecutive policy-rejected/duplicate plans are an observed failure to
propose a new strategy, not an external credit limit or a domain blacklist.
Provider/transport failures are not counted as commercial failures.
"""
    cfg = campaign['filters']['commercial']['ai']
    rows = c.execute('''SELECT engine,candidate_id,body,reserved_cost,reported_cost
        FROM commercial_ai_executions WHERE campaign_id=? AND attempt=1''',
        (campaign['id'],)).fetchall()
    waiting = pending_verification(c, campaign, cfg, rows, timestamp)
    recover = discovery_turn(c,campaign,flow,cfg,rows) and budget.available(
        c,campaign,flow,cfg,'replan',rows)>0
    if waiting and not recover:
        return {'reason': 'finish_pending_originals', 'flows': waiting, 'stop': False}
    plans = c.execute("""SELECT body FROM agent6_memory WHERE campaign_id=?
        AND flow=? AND kind='plan' ORDER BY id DESC LIMIT 3""",
        (campaign['id'], flow)).fetchall()
    if len(plans) == 3 and all(not json.loads(p['body']).get('chosen') for p in plans):
        return {'reason': 'three_plans_without_executable_strategy', 'stop': True,
                'sample': 3}
    return None


def choose(c, campaign, timestamp):
    # Do not deserialize saved HTML for every queued task on every dispatch.
    tasks = [dict(r) for r in c.execute("""SELECT id,kind,strategy,attempts,
        coalesce(json_extract(payload,'$.round'),0) AS round,
        coalesce(json_extract(payload,'$.selection'),json_extract(payload,'$.parent.selection')) AS selection,
        json_extract(payload,'$.prior.facts') AS facts,
        json_extract(payload,'$.prior.missing') AS missing,
        json_extract(payload,'$.prior.completion_queue.promising') AS promising,
        json_extract(payload,'$.research_parent') AS research_parent,
        json_extract(payload,'$.browser_requested') AS browser_requested,
        json_extract(payload,'$.original_page.url') AS saved_original
        ,coalesce(json_extract(payload,'$.discovery_priority.value'),0) AS discovery_priority
        FROM research_tasks WHERE campaign_id=? AND state='pending'
        AND available_at<=?""", (campaign['id'], timestamp))]
    if not tasks:
        return None, None
    cfg = campaign['filters']['commercial']['ai']
    rows = c.execute('''SELECT engine,candidate_id,body,reserved_cost,reported_cost
        FROM commercial_ai_executions WHERE campaign_id=? AND attempt=1''',
        (campaign['id'],)).fetchall()
    counts = {r['strategy']: r['n'] for r in c.execute('''SELECT strategy,
        sum(attempts) n FROM research_tasks WHERE campaign_id=? GROUP BY strategy''',
        (campaign['id'],))}
    capacities = {}
    discovery_turns={f:discovery_turn(c,campaign,f,cfg,rows) for f in {t['strategy'] for t in tasks}}
    ranked = []
    for task in tasks:
        task_stage = stage(task)
        if campaign['filters'].get('decision_engine')=='ai_first_1' and task['kind']=='search':
            task_stage='verify'
        key = (task['strategy'], task_stage)
        if key not in capacities:
            capacities[key] = budget.available(c, campaign, task['strategy'], cfg, task_stage, rows)
        # Original acquisition is already justified at admission. Resume a
        # saved page before fetching another one; no speculative spend estimate.
        tier = {'verify': 6, 'screen': 3, 'plan': 2, 'replan': 0}[task_stage]
        if task['kind'] == 'search':
            tier = 5 if task['selection'] == 'verification' else 1
        completion_path=task['kind']=='candidate' or task['selection']=='verification'
        if task['kind']=='agent_screen' and completion_path:tier=4
        facts = json.loads(task['facts'] or '[]')
        evidence = len({f.get('field') for f in facts if f.get('quote')})
        signal = min(3, evidence)
        progress = int(bool(task['saved_original']))
        # Coverage precedes marginal signal strength among equal-stage tasks.
        # A lower-quality snippet can never outrank a justified original read.
        # Within the same completion/discovery class, six dispatches of
        # imbalance give an executable neglected flow a turn. A generic plan
        # cannot displace a pending completion solely through fairness.
        # Within verification, finish saved originals
        # and near-complete dossiers before starting another acquisition.
        fair_turn=max(counts.values(),default=0)-counts.get(task['strategy'],0)>=6
        near_complete=bool(task.get('promising'))
        priority_class=int(completion_path)
        first_cycle=discovery_turns[task['strategy']] and task['kind'] in ('agent_plan','search')
        if campaign['filters'].get('decision_engine')=='ai_first_1':
            protected=bool(progress or task['selection']=='verification' or
                           task.get('research_parent') or task.get('browser_requested') or near_complete)
            priority_class=3 if protected else 2 if first_cycle else 1 if completion_path else 0
        rank = (bool(capacities[key]), priority_class, fair_turn, tier, progress, near_complete,
                -counts.get(task['strategy'], 0), signal,
                task['discovery_priority'] if campaign['filters'].get('decision_engine')=='ai_first_1' else 0,
                -task['id'])
        ranked.append((rank, task, {'stage': task_stage, 'pipeline_phase':pipeline_phase(task),'priority_tier': tier,
            'flow_dispatches': counts.get(task['strategy'], 0),
            'cited_fact_categories': evidence, 'original_saved': bool(progress),
            'discovery_priority':task['discovery_priority'],
            'missing': json.loads(task['missing'] or '[]'),
            'ai_capacity': capacities[key], 'basis': 'saved_completion_then_first_cycle_then_new_pages' if campaign['filters'].get('decision_engine')=='ai_first_1' else 'completion_then_flow_coverage',
            'first_cycle_discovery_turn':first_cycle,
            'sales_probability': None,'fairness_turn':fair_turn,
            'near_complete':near_complete,'completion_path':completion_path,
            'expected_information':'complete_missing_original_checks' if completion_path else 'new_candidates',
            'estimated_next_cost':{'ai_calls_max':1,'serper_requests_max':1 if task['kind']=='search' else 0,'usd':None},
            'dependencies':json.loads(task['missing'] or '[]')}))
    _, selected, decision = max(ranked, key=lambda item: item[0])
    decision.update(task_id=selected['id'], flow=selected['strategy'],
                    runnable_tasks=len(tasks))
    return selected['id'], decision
