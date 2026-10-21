"""Deterministic strategy feedback and read-only forecast on existing ledgers.

No training, migrations, provider calls or campaign writes. Legacy families are
reported separately; their yield is not attributed to rewritten strategies.
"""
import json
from collections import Counter
from datetime import datetime,timezone
from .planner import query_key
from .search_strategies import catalog,plans
from .job_activity import utc,evaluate as activity


def history(store,as_of=None,before_campaign=None):
    clock=utc(as_of) or datetime.now(timezone.utc)
    with store.connect() as c:
        tasks=[dict(r) for r in c.execute("SELECT id,campaign_id,strategy,kind,payload,state,updated_at FROM research_tasks WHERE kind IN ('search','resolve') ORDER BY id")]
        traces=[dict(r) for r in c.execute('SELECT campaign_id,engine,url,decision,body FROM commercial_discovery')]
        revisions=[dict(r) for r in c.execute('SELECT opportunity_id,campaign_id,state,body FROM commercial_revisions WHERE id IN (SELECT max(id) FROM commercial_revisions GROUP BY campaign_id,opportunity_id)')]
        ops=[dict(r) for r in c.execute("SELECT task_id,seconds,details FROM discovery_operations WHERE kind IN ('search','resolve')")]
        has=c.execute("SELECT 1 FROM sqlite_master WHERE name='commercial_job_reviews'").fetchone()
        reviews={r['opportunity_id']:r['status'] for r in c.execute('SELECT opportunity_id,status FROM commercial_job_reviews ORDER BY id')} if has else {}
    stats={};lookup={};query_history=[];bytask={};domains={}
    for op in ops:bytask.setdefault(op['task_id'],[]).append(op)
    for t in tasks:
        if before_campaign is not None and t['campaign_id']>=before_campaign:continue
        p=json.loads(t['payload']);sid=p.get('strategy_id') or p.get('origin',{}).get('strategy_id') or 'legacy:'+t['strategy']+':'+str(p.get('family','unknown'))
        m=stats.setdefault(sid,dict(strategy_id=sid,engine=t['strategy'],queries_generated=0,resolution_queries=0,queries_executed=0,query_cache_hits=0,network_requests=0,received=0,admitted=0,excluded=0,duplicates=0,evaluated=0,plausible_requests=0,verified_requests=0,qualified=0,recent=0,italy_compatible=0,accessible=0,access_errors=0,credits=0,seconds=0,interesting=0,not_interesting=0,unique_urls=set(),unique_queries=set(),source_families=Counter()))
        if p.get('query'):
            key=(t['strategy'],query_key(p['query']),p.get('discovery_period',''))
            query_history.append(dict(key=key,state=t['state'],at=t['updated_at'],campaign_id=t['campaign_id'],strategy_id=sid))
            lookup[(t['campaign_id'],t['strategy'],p['query'])]=sid
        m['queries_generated']+=t['kind']=='search';m['resolution_queries']+=t['kind']=='resolve'
        if t['state']=='done' and t['kind']=='search':m['queries_executed']+=1;m['unique_queries'].add(query_key(p.get('query','')))
        # Retries and pagination are separate receipts; never lose earlier costs.
        for op in bytask.get(t['id'],[]):
            d=json.loads(op.get('details') or '{}')
            m['query_cache_hits']+=bool(d.get('cache_hit'));m['network_requests']+=bool(d.get('network_attempted'))
            m['credits']+=d.get('credits_estimated',d.get('credits',0)) or 0;m['seconds']+=op.get('seconds') or 0
    for t in traces:
        b=json.loads(t['body']);sid=lookup.get((t['campaign_id'],t['engine'],b.get('query')))
        if not sid:continue
        m=stats[sid];m['received']+=1;m['unique_urls'].add(t['url']);m['admitted']+=t['decision']=='admit';m['excluded']+=t['decision']=='exclude';m['duplicates']+=t['decision'] in ('duplicate','memory')
        m['source_families'][b.get('source_intelligence',{}).get('family') or b.get('source_kind','UNKNOWN')]+=1
        from urllib.parse import urlsplit
        host=urlsplit(t['url']).hostname or 'unknown';s=domains.setdefault(host,dict(appearances=0,admitted=0,duplicates=0,excluded=0))
        s['appearances']+=1;s['admitted']+=t['decision']=='admit';s['duplicates']+=t['decision'] in ('duplicate','memory');s['excluded']+=t['decision']=='exclude'
    for r in revisions:
        b=json.loads(r['body']);d=b.get('discovery',{});sid=lookup.get((r['campaign_id'],b.get('engine'),d.get('query')))
        if not sid:continue
        m=stats[sid];m['evaluated']+=1
        plausible=bool(b.get('request_blocks') or b.get('partner_hint'));m['plausible_requests']+=plausible
        m['verified_requests']+=bool(b.get('verification',{}).get('request_verified'));m['qualified']+=r['state']=='VERIFIED'
        accessible=bool(b.get('document_ids')) and b.get('classification')!='access_incomplete'
        m['accessible']+=accessible;m['access_errors']+=b.get('classification') in ('access_incomplete','social_incomplete')
        a=activity(b,b.get('engine'),clock);m['recent']+=a['freshness_status']=='FRESH_CONFIRMED';m['italy_compatible']+=a['geographic_eligibility']=='GEO_COMPATIBLE'
        m['interesting']+=reviews.get(r['opportunity_id'])=='interesting';m['not_interesting']+=reviews.get(r['opportunity_id'])=='not_interesting'
        from urllib.parse import urlsplit
        host=urlsplit(b.get('url','')).hostname or 'unknown'
        source=domains.setdefault(host,dict(appearances=0,admitted=0,duplicates=0,excluded=0))
        for key,value in {'evaluated_observations':1,'accessible_observations':int(accessible),
          'plausible_request_observations':int(plausible),'verified_request_observations':int(bool(b.get('verification',{}).get('request_verified'))),
          'dated_observations':int(a['freshness_status'] in ('FRESH_CONFIRMED','STALE_CONFIRMED')),
          'italy_compatible_observations':int(a['geographic_eligibility']=='GEO_COMPATIBLE')}.items():source[key]=source.get(key,0)+value

    for m in stats.values():
        m['unique_urls']=len(m['unique_urls']);m['unique_queries']=len(m['unique_queries']);m['source_families']=dict(m['source_families'])
        # Yield is observational, not precision against independent labels.
        m['sample_sufficient']=m['unique_queries']>=5 and m['unique_urls']>=30 and m['evaluated']>=10
        m['priority_adjustment']=0
        if m['sample_sufficient']:
            m['priority_adjustment']=min(12,3*m['verified_requests']+m['plausible_requests'])-min(12,round(12*(m['excluded']+m['duplicates'])/max(1,m['received'])))
            if m['interesting']+m['not_interesting']>=10:m['priority_adjustment']+=max(-3,min(3,m['interesting']-m['not_interesting']))
        for name,n,d in [('plausible_yield',m['plausible_requests'],m['evaluated']),('duplicate_rate',m['duplicates'],m['received']),('accessible_rate',m['accessible'],m['evaluated']),('verified_yield',m['verified_requests'],m['evaluated']),('yield_per_credit',m['verified_requests'],m['credits'])]:
            m[name]={'numerator':n,'denominator':d,'value':n/d if d else None}
    return {'strategies':stats,'queries':query_history,'sources':domains,'as_of':clock.isoformat(),'learning':'descriptive_not_predictive','precision_requires_labelled_benchmark':True}


def select(available,used,h,as_of=None):
    clock=utc(as_of or h['as_of']);seen={(query_key(p['query']),p.get('discovery_period','')) for p in used};remaining=[];excluded=[]
    for p in available:
        key=(query_key(p['query']),p.get('discovery_period',''))
        if key in seen:excluded.append({'query':p['query'],'strategy_id':p['strategy_id'],'reason':'assigned_in_this_campaign'});continue
        prior=[q for q in h['queries'] if q['key']==(p['engine'],*key) and q['state']=='done' and utc(q['at']) and 0<=(clock-utc(q['at'])).total_seconds()<21600]
        if prior:
            excluded.append({'query':p['query'],'strategy_id':p['strategy_id'],'reason':'already_explored_within_6h','previous_campaign':prior[-1]['campaign_id']});continue
        remaining.append(dict(p))
    if not remaining:return None,excluded
    counts=Counter(p['strategy_id'] for p in used);tiers=Counter(p['geography_tier'] for p in used);langs=Counter(p['language'] for p in used)
    regions=Counter(p.get('region') for p in used if p.get('demand_type')=='OUTBOUND')
    fresh=[p for p in remaining if not counts[p['strategy_id']]]
    pool=fresh or remaining
    # At least one fairness turn in four; max strategy share once >1 family
    # has actually had its first exploration. Budgets remain the caller's caps.
    if not fresh and len({p['strategy_id'] for p in available})>1:
        balanced=[p for p in pool if counts[p['strategy_id']]<max(2,(len(used)+1)*p['max_query_share'])]
        if balanced:pool=balanced
    fairness=len(used)%4==3
    def score(p):
        adj=h['strategies'].get(p['strategy_id'],{}).get('priority_adjustment',0)
        return (counts[p['strategy_id']] if fairness else 0,counts[p['strategy_id']] if fresh else 0,regions[p.get('region')] if p.get('demand_type')=='OUTBOUND' else 0,tiers[p['geography_tier']],langs[p['language']],-(p['priority']+adj))
    chosen=min(pool,key=score)
    chosen['allocation']={'policy':'exploration_turn' if fairness or fresh else 'bounded_observed_yield','observations':h['strategies'].get(chosen['strategy_id']), 'limits':'Existing engine caps; no transfer or budget increase','not_market_evidence':True}
    return chosen,excluded


def choose(store,cid,engine,available):
    with store.connect() as c:used=[json.loads(r[0]) for r in c.execute("SELECT payload FROM research_tasks WHERE campaign_id=? AND strategy=? AND kind='search' ORDER BY id",(cid,engine))]
    # Pagination is the same query, not a second exploration turn.
    used=list({(query_key(p['query']),p.get('discovery_period','')):p for p in used}.values())
    return select(available,used,history(store))[0]


def approval_token(filters,budget,ai):
    from sales.db import digest,encode
    from .geography import REGIONS
    scope={}
    if filters.get('social_urls'):
        from sales.agent6.social_seeds import validate_filters
        scope['social_urls']=validate_filters(filters)
    return digest(encode({**scope,'mode':filters.get('mode','standard'),'engines':sorted(set(filters['commercial_engines'])),
      'regions':sorted(set(filters.get('regions') or REGIONS)),'days':filters.get('max_job_age_days',14),
      'budget':budget,'ai':ai,'search_version':'5.0'}))

def preview(store,filters,as_of=None):
    from .catalog import options,DEEP_PROFILE
    from .ai_settings import campaign_config
    from .geography import REGIONS
    f=dict(filters);f.setdefault('commercial_engines',['FREELANCE','AGENCIES','STARTUPS','WEBSITE_REBUILD'])
    if set(f)-{'commercial_engines','mode','regions','max_job_age_days','work_budget','commercial','deep_authorized','target'}:raise ValueError('Filtri del piano non validi')
    regions=f.get('regions') or list(REGIONS)
    if not isinstance(regions,list) or any(r not in REGIONS for r in regions):raise ValueError('Regioni non valide')
    engines,budget=options(f);ai=campaign_config(store,f)['ai'];h=history(store,as_of);selected=[];excluded=[];available=[]
    for e in engines:
        ps=plans(e,regions,f.get('max_job_age_days',14));available+=ps;used=[]
        for _ in range(budget['max_queries_per_engine']):
            p,skip=select(ps,used,h,as_of)
            if not p:break
            used.append(p)
        selected+=used;keys={query_key(p['query']) for p in used}
        _,skip=select(ps,used,h,as_of);reasons={query_key(s['query']):s for s in skip}
        for p in ps:
            if query_key(p['query']) not in keys:excluded.append({'query':p['query'],'strategy_id':p['strategy_id'],'reason':reasons.get(query_key(p['query']),{}).get('reason','engine_query_cap')})
    n=len(engines);totals={k:n*budget[k] for k in ('max_provider_requests','max_serper_credits','max_http_reads','max_browser_runs','max_runtime_seconds','max_candidates_per_engine')}
    totals.update(ai_max_calls=ai['max_calls_per_campaign'] if ai['enabled'] else 0,ai_max_estimated_usd=ai['max_estimated_cost'] if ai['enabled'] else 0,serper_balance=None,serper_cash_cost=None)
    ids={p['strategy_id'] for p in selected}
    return {'version':'5.0','approval_token':approval_token(f,budget,ai),'mode':f.get('mode','standard'),'generated_at':h['as_of'],'available_strategies':catalog(),'selected_strategies':sorted(ids),'not_selected_strategies':[{'id':s['id'],'reason':'engine_not_selected' if s['engine'] not in engines else 'current_budget_or_recent_exploration'} for s in catalog() if s['id'] not in ids],
      'available_queries':len(available),'planned_queries':len(selected),'queries':selected,'excluded_queries':excluded,'languages':sorted({p['language'] for p in selected}),'geography_tiers':sorted({p['geography_tier'] for p in selected}),
      'limits_per_engine':budget,'maximums':totals,'ai':{k:ai[k] for k in ('enabled','provider','model','mode','max_calls_per_campaign','max_estimated_cost')},
      'forecast_not_execution':True,'authorization_required':f.get('mode')=='deep','external_calls':0,'database_writes':0,
      'coverage_note':'Ordine iniziale: può adattarsi agli esiti. Nessuna strategia pianificata è già stata eseguita. Le regioni selezionate limitano presenza e outbound; remoto solo con Italia ammessa.',
      'duration_note':'Somma dei tetti di lavoro dei motori, non previsione di durata a parete; backoff e pause possono allungarla.',
      'history':{'strategies':h['strategies'],'sources':h['sources']}}
