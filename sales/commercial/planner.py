"""Explainable query feedback; exploration is retained, no predictive claims."""
import json,re
from datetime import datetime,timezone
from sales.db import digest

def query_key(query):
    return digest(' '.join(sorted(re.findall(r'[^\s]+',query.casefold().replace('-filetype:pdf','')))))

def metrics(store,cid,engine,query):
    with store.connect() as c:
        records=[json.loads(r[0]) for r in c.execute('SELECT body FROM commercial_discovery WHERE campaign_id=? AND engine=? AND query=?',(cid,engine,query))]
        revisions=[json.loads(r[0]) for r in c.execute('SELECT body FROM commercial_revisions r WHERE r.id=(SELECT max(x.id) FROM commercial_revisions x WHERE x.opportunity_id=r.opportunity_id AND x.campaign_id=r.campaign_id) AND campaign_id=? AND json_extract(body,\'$.engine\')=? AND json_extract(body,\'$.discovery.query\')=?',(cid,engine,query))]
        costs=c.execute("SELECT coalesce(sum(coalesce(json_extract(details,'$.credits_estimated'),json_extract(details,'$.credits'),0)),0) FROM discovery_operations WHERE campaign_id=? AND task_id IN (SELECT id FROM research_tasks WHERE campaign_id=? AND strategy=? AND json_extract(payload,'$.query')=?)",(cid,cid,engine,query)).fetchone()[0]
    with store.connect() as c:
        operations=c.execute("SELECT pages,cached_pages,seconds FROM discovery_operations WHERE campaign_id=? AND task_id IN (SELECT id FROM research_tasks WHERE campaign_id=? AND strategy=? AND (json_extract(payload,'$.query')=? OR json_extract(payload,'$.origin.query')=?))",(cid,cid,engine,query,query)).fetchall()
    operation_resources={'operation_page_reads':sum(r['pages'] for r in operations),'cached_page_reads':sum(r['cached_pages'] for r in operations),'operation_seconds_sum':sum(r['seconds'] or 0 for r in operations),'not_http_ledger_or_campaign_wall_time':True}
    unique={r['canonical_url']:r for r in records}
    relevant=sum(r['decision']=='admit' and r['priority']>=55 for r in unique.values())
    usable=sum(r['verification']['status']=='complete' and bool(r.get('evidence')) for r in revisions if 'verification' in r)
    qualified=sum(r['state'] in ('VERIFIED','POTENTIAL') for r in revisions)
    def inaccessible(r):
        return r.get('verification',{}).get('scope')=='access' or (r.get('social',{}).get('accessibility') in ('unavailable','indexed_only') and not r.get('document_ids')) or r.get('browser_outcome') in ('timeout','navigation_timeout','rendering_timeout','tls_error','robots','access_error')
    from collections import Counter
    return {'appearances':len(records),'unique_urls':len(unique),'admitted':sum(r['decision']=='admit' for r in records),'excluded':sum(r['decision']=='exclude' for r in records),'explicit_requests':sum(bool(r.get('request_blocks')) for r in revisions),'resources':{**operation_resources,'provider_credits_estimated':costs,'candidate_pages':sum(r.get('pages_read',0) for r in revisions),'browser_audits':sum(bool(r.get('browser')) and r['browser'].get('executed',True) for r in revisions),'scope':'per_query_observations_not_full_ledger'},'identified':sum(r.get('identity',{}).get('identity_status')=='verified' for r in revisions),'attributable_requests':sum(bool(r.get('verification',{}).get('request_verified')) for r in revisions),'contact_channels':sum(bool(r.get('contacts')) for r in revisions),'source_exclusions':dict(Counter(r.get('reason') for r in records if r.get('decision')=='exclude')),'seen':len(unique),'relevant':relevant,'verifiable':usable,'qualified':qualified,
            'accessible':sum(bool(r.get('document_ids')) and not inaccessible(r) for r in revisions),'unresolved':sum(r['state']=='UNVERIFIABLE' for r in revisions),
            'inaccessible':sum(inaccessible(r) for r in revisions),'duplicates':sum(r['decision']=='duplicate' for r in records),
            'estimated_credits':costs,'cost_per_relevant':costs/relevant if relevant else None,'cost_per_qualified':costs/qualified if qualified else None}

def paginate(store,cid,engine,query):
    m=metrics(store,cid,engine,query)
    # An initial page is exploration; subsequent pages must earn their cost.
    return m['relevant']>0 and m['relevant']/max(1,m['seen'])>=.25 and m['inaccessible']<=m['relevant']

def choose(store,cid,engine,plans):
    with store.connect() as c:
        used=[json.loads(r[0]) for r in c.execute("SELECT payload FROM research_tasks WHERE campaign_id=? AND strategy=? AND kind='search'",(cid,engine))]
    # Count actual persisted search assignments, including earlier campaigns.
    # Least-explored territory wins; catalog order breaks ties Nord/Centro/Sud.
    # Query geography remains a search preference, never company evidence.
    with store.connect() as c:
        history=[json.loads(r[0]) for r in c.execute("SELECT payload FROM research_tasks WHERE kind='search' AND campaign_id=? AND strategy IN ('FREELANCE','AGENCIES','STARTUPS','WEBSITE_REBUILD') ORDER BY id",(cid,))]
        completed=[json.loads(r[0]) for r in c.execute("SELECT payload FROM research_tasks WHERE strategy=? AND kind='search' AND state='done' AND campaign_id<=? ORDER BY id",(engine,cid))]
    region_counts={}
    for old in history:
        reg=old.get('region')
        if reg is not None:region_counts[reg]=region_counts.get(reg,0)+1
    region_order=list(dict.fromkeys(p.get('region') for p in plans))
    plans=sorted(plans,key=lambda p:(region_counts.get(p.get('region'),0),region_order.index(p.get('region'))))
    plans=[dict(p) for p in plans]
    # Relax the same semantic family after repeated completed empty responses.
    # No additional query is enqueued and existing quota accounting is unchanged.
    relaxed_families=set()
    with store.connect() as c:
        for family in dict.fromkeys(p.get('family') for p in plans):
            prior=[u for u in completed if u.get('family')==family][-2:]
            if family not in {p.get('family') for p in plans if p.get('strategy_version') in ('3b.4','3b.5','3b.6','4.0','4.1','4.2','4.3','4.5')} and len(prior)==2 and all(c.execute("SELECT count(*) FROM commercial_discovery WHERE engine=? AND query=?",(engine,u['query'])).fetchone()[0]==0 for u in prior):
                relaxed_families.add(family)
    for p in plans:
        if p.get('family') in relaxed_families:
            original=p['query'];relaxed=re.sub(r'"([^"\n]+)"',lambda m:m[1],original)
            if relaxed!=original:p.update(query=relaxed,relaxation={'reason':'two_completed_zero_result_queries','original_query':original,'policy':'same_family_remove_exact_phrase_constraints'})
        p['cache_strategy']='EXPLORE_NEW_QUERY' if history else 'REUSE'
        p['geographic_exploration']={'region':p.get('region'),'previous_queries':region_counts.get(p.get('region'),0),'policy':'balanced_within_selected_campaign_regions','not_company_evidence':True}
    seen={query_key(x['query']) for x in used}
    remaining=[p for p in plans if p.get('eligible',True) and query_key(p['query']) not in seen]
    if not remaining:return None
    # Hard exploration gate: no regional repetition while a compatible family
    # remains untried. The catalog's first three entries are the Pilot coverage.
    families={u.get('family',u['query']) for u in used}
    unexplored=[p for p in remaining if p.get('family',p['query']) not in families]
    versions={p.get('strategy_version') for p in plans}
    with store.connect() as c:feedback=family_history(c,engine,cid,next(iter(versions)) if len(versions)==1 else None)
    for p in remaining:p['historical_family_feedback']=feedback.get(p.get('family'),{'sample_sufficient':False,'policy':'retain_exploration','penalty':0})
    exploration=[p for p in unexplored if p.get('exploration')]
    if len(used)%4==3 and exploration:return exploration[0]
    if unexplored:return min(unexplored,key=lambda p:((sum(u.get('sector_group')==p.get('sector_group') for u in used) if engine=='WEBSITE_REBUILD' else 0),p['historical_family_feedback']['penalty']))
    # Evaluate whole families, never retain only their best historic query.
    # A single inaccessible result does not penalize a family. Subsequent
    # failures progressively reduce its priority; unknowns bring no bonus.
    scores={};counts={};last={}
    for i,u in enumerate(used):
        fam=u.get('family',u['query']);m=metrics(store,cid,engine,u['query'])
        agg=scores.setdefault(fam,{'seen':0,'relevant':0,'verifiable':0,'qualified':0,'inaccessible':0})
        for k in agg:agg[k]+=m[k]
        counts[fam]=counts.get(fam,0)+1;last[fam]=i
    # One fairness turn in four bounds starvation after exploration.
    exploit_turn=len(used)-len(families)
    if exploit_turn%4==3:
        return min(enumerate(remaining),key=lambda pair:(last.get(pair[1].get('family'),-1),pair[0]))[1]
    def score(p):
        m=scores[p.get('family',p['query'])]
        return (4*m['qualified']+2*m['verifiable']+.25*m['relevant']-max(0,m['inaccessible']-1))/max(1,m['seen'])-p['historical_family_feedback']['penalty']
    return max(enumerate(remaining),key=lambda pair:(score(pair[1]),-pair[0]))[1]


def coverage(store,cid,engines,regions=None):
    from .catalog import plan,query_source
    with store.connect() as c:
        rows=c.execute("SELECT strategy,payload FROM research_tasks WHERE campaign_id=? AND kind='search' ORDER BY id",(cid,)).fetchall()
    with store.connect() as c:
        row=c.execute('SELECT filters FROM campaigns WHERE id=?',(cid,)).fetchone()
    filters=json.loads(row[0]) if row else {}
    result=[]
    for engine in engines:
        if filters.get('search_version')=='5.0' and (not rows or any(json.loads(r['payload']).get('strategy_version')=='5.0' for r in rows)):
            from .search_strategies import plans as strategy_plans
            from .geography import REGIONS
            plans=strategy_plans(engine,regions or REGIONS,filters.get('max_job_age_days',14))
        else:plans=[p for p in plan(engine) if not regions or p['region'] in regions]
        families=list(dict.fromkeys(p['family'] for p in plans))
        used=[json.loads(r['payload']) for r in rows if r['strategy']==engine]
        tried=set(u.get('family',u['query']) for u in used)
        sources=set(query_source(u['query']) for u in used)
        result.append({'engine':engine,'total_families':len(families),'tried_families':sum(f in tried for f in families),
                       'remaining_families':[f for f in families if f not in tried],
                       'sources_tried':sorted(sources),'sources_remaining':sorted({p['source'] for p in plans}-sources)})
    return result

def summary(store,cid):
    """Small bounded campaign feedback for the UI, never a conversion estimate."""
    with store.connect() as c:
        queries=c.execute("SELECT strategy,payload,json_extract(payload,'$.query') AS query FROM research_tasks WHERE campaign_id=? AND kind='search' GROUP BY strategy,query ORDER BY min(id)",(cid,)).fetchall()
    return [{'engine':r['strategy'],'query':r['query'],**{k:json.loads(r['payload']).get(k) for k in ('family','segment','region','source','source_preference','strategy_version')},**metrics(store,cid,r['strategy'],r['query'])} for r in queries]


def cache_decision(acquired_at,last_used_at=None,ttl_seconds=21600,now_at=None,query_exhausted=False):
    """Pure freshness policy. Invalid dates never make stale content fresh.

    EXPLORE_NEW_QUERY advises the planner, not a refresh or a budget bypass.
    """
    if not isinstance(ttl_seconds,(int,float)) or isinstance(ttl_seconds,bool) or ttl_seconds<=0:raise ValueError('TTL positivo richiesto')
    def parse(value):
        if isinstance(value,datetime):dt=value
        elif value:
            try:dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
            except ValueError:return None
        else:return None
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    current=parse(now_at) or datetime.now(timezone.utc);acquired=parse(acquired_at)
    age=(current-acquired).total_seconds() if acquired else None
    fresh=age is not None and 0<=age<ttl_seconds
    decision='EXPLORE_NEW_QUERY' if fresh and query_exhausted else 'REUSE' if fresh else 'REFRESH'
    return {'decision':decision,'acquired_at':acquired_at,'last_used_at':last_used_at,'ttl_seconds':ttl_seconds,'age_seconds':age,'freshness':'fresh' if fresh else 'unknown' if age is None else 'stale','cache_hit':decision=='REUSE','budget_required':decision!='REUSE'}


def family_history(connection,engine,before_campaign,strategy_version=None):
    """Descriptive feedback only; completed searches, explicit denominators.

    At least three completed searches and twenty appearances are required to
    demote a family. Never blacklist it and retain the exploration fairness turn.
    """
    rows=connection.execute("SELECT campaign_id,payload FROM research_tasks WHERE strategy=? AND kind='search' AND state='done' AND campaign_id<?",(engine,before_campaign)).fetchall()
    mapping={};families={}
    for row in rows:
        p=json.loads(row['payload'])
        # Rewritten query families are new experiments, not evidence that the
        # previous formulation's observed precision carries over.
        if strategy_version and p.get('strategy_version')!=strategy_version:continue
        family=p.get('family',p.get('query'))
        from .strategies import FAMILIES
        family=next((name for name,template,_ in FAMILIES.get(engine,()) if template==family),family)
        if not family:continue
        mapping[(row['campaign_id'],p.get('query'))]=family
        m=families.setdefault(family,{'queries':0,'appearances':0,'admitted':0,'excluded':0,'evaluated':0,'qualified':0,'identity_verified':0,'technical_requests':0,'verified_requests':0,'penalty':0})
        m['queries']+=1
    for row in connection.execute('SELECT campaign_id,query,decision FROM commercial_discovery WHERE engine=? AND campaign_id<?',(engine,before_campaign)):
        family=mapping.get((row['campaign_id'],row['query']))
        if family:
            m=families[family];m['appearances']+=1;m['admitted']+=row['decision']=='admit';m['excluded']+=row['decision']=='exclude'
    for row in connection.execute("SELECT campaign_id,body FROM commercial_revisions WHERE campaign_id<? AND json_extract(body,'$.engine')=? AND id IN (SELECT max(id) FROM commercial_revisions GROUP BY campaign_id,opportunity_id)",(before_campaign,engine)):
        b=json.loads(row['body']);family=mapping.get((row['campaign_id'],b.get('discovery',{}).get('query')))
        if family:
            m=families[family];m['evaluated']+=1;m['qualified']+=b.get('state') in ('VERIFIED','POTENTIAL');m['identity_verified']+=b.get('identity',{}).get('identity_status')=='verified'
            m['technical_requests']+=bool(b.get('request_blocks'));m['verified_requests']+=bool(b.get('verification',{}).get('request_verified'))
    for m in families.values():
        m['sample_sufficient']=m['queries']>=3 and m['appearances']>=20
        if m['sample_sufficient'] and not m['qualified'] and not m['verified_requests'] and (m['excluded']/max(1,m['appearances'])>=.8 or (m['evaluated']>=10 and not m['technical_requests'] and engine!='WEBSITE_REBUILD')):m['penalty']=1
        m['policy']='demote_not_disable' if m['penalty'] else 'retain_exploration'
    return families
