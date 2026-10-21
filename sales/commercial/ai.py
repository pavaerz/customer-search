"""Evidence interpreter with independent, persistent, conservative AI accounting.

Nothing here writes CRM/revisions. Both shadow and assist are advisory; only
shadow is intended for the initial comparison. Failures retain deterministic
results. Provider requests are reserved atomically before dispatch, including
retries. Unknown invoices are never reported as exact costs.
"""
import json
import math
import time
from .ai_schema import SCHEMA_VERSION,PROMPT_VERSION,SYSTEM,fingerprint,evidence_bundle,validate_output,minimize,response_schema
from .ai_provider import infer,endpoint_valid,ProviderError

DEFAULTS={'enabled':False,'provider':'DISABLED','model':'','mode':'shadow','endpoint':'','timeout':30,'max_input_tokens':8192,'max_output_tokens':1000,'max_calls_per_campaign':20,'max_calls_per_engine':8,'max_calls_per_candidate':1,'max_estimated_cost':0.0,'max_concurrent_requests':1,'max_retries':0,'input_cost_per_million':None,'output_cost_per_million':None,'cache_ttl_hours':24}
BOUNDS={'timeout':(1,120),'max_input_tokens':(1024,32768),'max_output_tokens':(64,8192),'max_calls_per_campaign':(0,100000),'max_calls_per_engine':(0,100000),'max_calls_per_candidate':(0,20),'max_concurrent_requests':(1,4),'max_retries':(0,2),'cache_ttl_hours':(1,168)}


def validate_config(raw=None):
    if raw is None:raw={}
    if not isinstance(raw,dict) or set(raw)-set(DEFAULTS):raise ValueError('Configurazione AI non riconosciuta; non inserire chiavi API.')
    cfg={**DEFAULTS,**raw}
    if type(cfg['enabled']) is not bool:raise ValueError('Abilitazione AI non valida')
    if cfg['provider'] not in ('DISABLED','MOCK','LOCAL','REMOTE') or cfg['mode'] not in ('shadow','assist'):raise ValueError('Provider o modalità AI non validi')
    for name,(low,high) in BOUNDS.items():
        if type(cfg[name]) is not int or not low<=cfg[name]<=high:raise ValueError('Limite AI non valido: '+name)
    for name in ('max_estimated_cost','input_cost_per_million','output_cost_per_million'):
        value=cfg[name]
        if value is None and name!='max_estimated_cost':continue
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=100000:raise ValueError('Costo AI non valido: '+name)
    if not isinstance(cfg['model'],str) or len(cfg['model'])>150 or '\n' in cfg['model']:raise ValueError('Modello AI non valido')
    if not isinstance(cfg['endpoint'],str) or len(cfg['endpoint'])>500:raise ValueError('Endpoint AI non valido')
    if cfg['provider']=='LOCAL':
        cfg['endpoint']=cfg['endpoint'] or 'http://127.0.0.1:11434/api/chat'
        if any(marker in cfg['model'].casefold() for marker in (':cloud','-cloud','/cloud','://')):raise ValueError('Usare un modello locale installato, senza cloud')
    if cfg['provider'] in ('LOCAL','REMOTE'):
        if cfg['endpoint']:endpoint_valid(cfg['endpoint'],cfg['provider'])
        if cfg['enabled'] and (not cfg['endpoint'] or not cfg['model'].strip()):raise ValueError('Specificare modello ed endpoint AI')
    if cfg['enabled'] and cfg['provider']=='DISABLED':raise ValueError('Selezionare un provider AI')
    return cfg


def migrate(connection):
    # No executescript (would commit the caller's transaction). Additive only.
    connection.execute('''CREATE TABLE IF NOT EXISTS commercial_ai_executions(id INTEGER PRIMARY KEY,campaign_id INTEGER NOT NULL,candidate_id TEXT NOT NULL,engine TEXT NOT NULL,generation INTEGER NOT NULL,provider TEXT NOT NULL,model TEXT NOT NULL,mode TEXT NOT NULL,reason TEXT NOT NULL,cache_key TEXT NOT NULL,status TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,reserved_cost REAL NOT NULL DEFAULT 0,estimated_cost REAL,reported_cost REAL,input_tokens INTEGER,output_tokens INTEGER,estimated_input_tokens INTEGER,estimated_output_tokens INTEGER,duration REAL NOT NULL DEFAULT 0,cache_hit INTEGER NOT NULL DEFAULT 0,started_at REAL NOT NULL,expires_at REAL NOT NULL,body TEXT NOT NULL DEFAULT '{}')''')
    connection.execute('CREATE INDEX IF NOT EXISTS commercial_ai_campaign ON commercial_ai_executions(campaign_id,candidate_id,engine,id)')
    connection.execute('CREATE INDEX IF NOT EXISTS commercial_ai_cache ON commercial_ai_executions(cache_key,status,started_at)')
    if connection.execute("SELECT 1 FROM sqlite_master WHERE name='research_schema' AND type='table'").fetchone():
        from sales.db import now
        connection.execute('INSERT OR IGNORE INTO research_schema VALUES (63,?)',(now(),))


def _active(c,campaign):
    return bool(c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(campaign['id'],campaign['generation'])).fetchone())


def eligibility(result):
    """AI is for ambiguity, never a way around a certain exclusion/access denial."""
    demand=result.get('demand_assessment') or {}
    if demand.get('excluded'):return False,'demand_excluded'
    from .relevance import preflight_type
    source_type,_=preflight_type(result.get('discovery') or result)
    if source_type in ('EDITORIAL','INSTITUTIONAL') and not result.get('request_blocks'):return False,'noncommercial_source'
    classification=result.get('classification','')
    if classification in ('actor_unresolved','contradictory_request') or result.get('entity_scope',{}).get('multi_subject'):return False,'unresolved_actor_scope'
    if classification in ('excluded_pdf','excluded','suppressed','incompatible','technical_incompatible','target_incompatible','hosted_incompatible'):return False,'deterministic_exclusion'
    if result.get('target_fit',{}).get('status') in ('NOT_SUITABLE','LOW_PRIORITY'):return False,'deterministic_target_exclusion'
    if result.get('engine')=='WEBSITE_REBUILD' and 'outside_or_unresolved_selected_area' in result.get('target_fit',{}).get('reasons',[]):return False,'target_geography_unresolved_or_excluded'
    intent=result.get('commercial_intent') or {}
    if result.get('source_kind') in ('institution','directory','aggregator') or (intent.get('commercial_role')=='EDITORIAL' and not result.get('request_blocks')):return False,'noncommercial_source'
    if result.get('state') in ('VERIFIED','REJECTED') and (intent.get('commercial_role') in ('SELLER','PARTNERSHIP_SELLER','EMPLOYER','DIRECTORY','AGGREGATOR') or result.get('state')=='VERIFIED'):return False,'deterministic_conclusive'
    if result.get('engine')=='WEBSITE_REBUILD' and result.get('classification') in ('excluded','suppressed'):return False,'deterministic_exclusion'
    return True,'semantic_ambiguity'


def _base(cfg,result,status,error=None):
    return {'status':status,'mode':cfg['mode'],'provider':cfg['provider'],'model':cfg['model'],'execution_id':None,'output':None,'official_state':result.get('state'),'differences':[],'fallback':True,'error':error,'cache_hit':False,'schema_version':SCHEMA_VERSION,'prompt_version':PROMPT_VERSION,'decision_authority':'deterministic_only'}


def _reserve(store,campaign,engine,candidate_id,cfg,key,reason,cost,estimated_input,*,candidate_limit=True,reservation_policy=None,metadata=None):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not _active(c,campaign):raise InterruptedError('Campagna sospesa')
        timestamp=time.time()
        # Crashes keep their conservative charge; they do not block concurrency forever.
        c.execute("UPDATE commercial_ai_executions SET status='abandoned' WHERE campaign_id=? AND status='running' AND expires_at<?",(campaign['id'],timestamp))
        rows=c.execute('SELECT engine,candidate_id,reserved_cost,reported_cost,body FROM commercial_ai_executions WHERE campaign_id=? AND attempt=1',(campaign['id'],)).fetchall()
        if len(rows)>=cfg['max_calls_per_campaign']:return None,'campaign_budget'
        if sum(r['engine']==engine for r in rows)>=cfg['max_calls_per_engine']:return None,'engine_budget'
        if candidate_limit and sum(r['candidate_id']==str(candidate_id) for r in rows)>=cfg['max_calls_per_candidate']:return None,'candidate_budget'
        if reservation_policy:
            denied=reservation_policy(c,rows)
            if denied:return None,denied
        spent=sum(max(r['reserved_cost'],r['reported_cost'] or 0) for r in rows)
        if spent+cost>cfg['max_estimated_cost']+1e-12:return None,'cost_budget'
        running=c.execute("SELECT count(*) FROM commercial_ai_executions WHERE status='running' AND expires_at>=?",(timestamp,)).fetchone()[0]
        if running>=cfg['max_concurrent_requests']:return None,'concurrency_budget'
        # Serialize identical evidence/model work, including across campaigns.
        if c.execute("SELECT 1 FROM commercial_ai_executions WHERE cache_key=? AND status='running'",(key,)).fetchone():return None,'inference_pending'
        cur=c.execute('INSERT INTO commercial_ai_executions(campaign_id,candidate_id,engine,generation,provider,model,mode,reason,cache_key,status,attempt,reserved_cost,estimated_input_tokens,started_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(campaign['id'],str(candidate_id),engine,campaign['generation'],cfg['provider'],cfg['model'],cfg['mode'],reason,key,'running',1,cost,estimated_input,timestamp,timestamp+cfg['timeout']+2))
        if metadata:c.execute('UPDATE commercial_ai_executions SET body=? WHERE id=?',(json.dumps(metadata),cur.lastrowid))
        return cur.lastrowid,None


def _save_event(store,campaign,engine,candidate_id,cfg,key,reason,body):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not _active(c,campaign):return body
        # One repeated fallback per signature; retrying/resume does not create noise.
        existing=c.execute('SELECT id FROM commercial_ai_executions WHERE campaign_id=? AND candidate_id=? AND engine=? AND cache_key=? AND status=? AND attempt=0',(campaign['id'],str(candidate_id),engine,key,body['status'])).fetchone()
        if existing:body['execution_id']=existing[0];return body
        timestamp=time.time()
        cur=c.execute('INSERT INTO commercial_ai_executions(campaign_id,candidate_id,engine,generation,provider,model,mode,reason,cache_key,status,started_at,expires_at,body,cache_hit) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(campaign['id'],str(candidate_id),engine,campaign['generation'],cfg['provider'],cfg['model'],cfg['mode'],reason,key,body['status'],timestamp,timestamp,json.dumps(body),int(body['cache_hit'])))
        body['execution_id']=cur.lastrowid
        c.execute('UPDATE commercial_ai_executions SET body=? WHERE id=?',(json.dumps(body),cur.lastrowid))
    return body


def interpretation_documents(result,documents):
    """Saved index hints are interpretable data, explicitly not original pages."""
    originals=list(documents or [])
    indexed=result.get('discovery') or {}
    if not isinstance(indexed,dict):return originals
    title=indexed.get('title');snippet=indexed.get('snippet') or indexed.get('content')
    pieces=[x.strip() for x in (title,snippet) if isinstance(x,str) and x.strip()]
    url=indexed.get('url') or result.get('url')
    if not pieces or not url:return originals
    if originals and not result.get('social'):return originals
    text='\n'.join(pieces)
    record={'id':'INDEX_'+fingerprint([url,text,indexed.get('appearance_id')])[:24],
            'url':url,'text':text,'published_at':None,'checked_at':indexed.get('timestamp'),
            'acquisition':'search_index','original_verified':False,
            'provider':indexed.get('provider','unknown'),'title':title or ''}
    return [record,*originals]


def analyze(store,campaign,engine,candidate_id,result,documents,check=lambda:None,provider=None,config=None,images=None):
    """Return a separate advisory. Never mutate result/documents or perform tools."""
    raw=config if config is not None else (campaign.get('filters',{}).get('commercial',{}).get('ai') or {})
    cfg=validate_config(raw)
    if not cfg['enabled'] or cfg['provider']=='DISABLED':return _base(cfg,result,'disabled')
    allowed,reason=eligibility(result)
    if not allowed:return _save_event(store,campaign,engine,candidate_id,cfg,'eligibility:'+reason,reason,_base(cfg,result,'skipped',reason))
    # Keep arbitrary image paths/URLs out of model input. Multimodal providers may
    # receive already acquired fixture bytes through an explicitly injected adapter.
    if images and provider is None:return _base(cfg,result,'fallback','multimodal_adapter_not_configured')
    from .evidence import select,trim_to_payload
    evidence,bundle_metrics=select(candidate_id,interpretation_documents(result,documents),max_chars=cfg['max_input_tokens'],result=result)
    if not evidence:return _save_event(store,campaign,engine,candidate_id,cfg,'no_evidence',reason,_base(cfg,result,'fallback','no_evidence'))
    from .ai_tasks import task_for,schema_for,system_for,request_context
    task=task_for(engine)
    payload={'task':task,'candidate_id':str(candidate_id),'engine':engine,'evidence':evidence,'schema_version':SCHEMA_VERSION,'prompt_version':PROMPT_VERSION,'schema':schema_for(task)}
    payload['verified_context']=request_context(result)
    if engine=='WEBSITE_REBUILD':
        browser=result.get('browser') or {};screen=result.get('screening') or {}
        payload['technical_context']={'screening':screen.get('status'),'browser_completed':browser.get('completed',False),'browser_outcome':result.get('browser_outcome'),'limits':list(dict.fromkeys([*result.get('limits',[]),*browser.get('limits',[])]))[:6],'measured_findings':[{k:e.get(k) for k in ('code','quote','url','severity','category')} for e in result.get('evidence',[]) if e.get('kind')=='measurement'][:8]}
    # UTF-8 bytes are a conservative upper bound, not provider-reported tokens.
    estimated_input=trim_to_payload(payload,system_for(task),cfg['max_input_tokens'],bundle_metrics)
    if not evidence:return _save_event(store,campaign,engine,candidate_id,cfg,'input_limit',reason,_base(cfg,result,'fallback','input_limit'))
    if bundle_metrics['status']=='EVIDENCE_INSUFFICIENT':
        body={**_base(cfg,result,'fallback','evidence_insufficient'),'bundle_metrics':bundle_metrics}
        return _save_event(store,campaign,engine,candidate_id,cfg,'evidence_insufficient',reason,body)
    from .commercial_gate import sufficient
    gate=sufficient(engine,result,evidence)
    bundle_metrics['commercial_sufficiency']=gate['allowed']
    if not gate['allowed']:
        bundle_metrics['status']='EVIDENCE_INSUFFICIENT'
        body={**_base(cfg,result,'skipped',gate['reason']),'commercial_gate':gate,'bundle_metrics':bundle_metrics}
        return _save_event(store,campaign,engine,candidate_id,cfg,fingerprint([result,evidence,'commercial_gate']),gate['reason'],body)
    if images:
        payload['images']=_images(images,candidate_id)
        # Visual token/cost accounting varies by model; only fixture MOCK adapters
        # are supported until an explicit per-image price/token policy is added.
        if cfg['provider']!='MOCK':return _base(cfg,result,'fallback','visual_cost_policy_unavailable')
    key=fingerprint([payload,cfg['provider'],cfg['model'],SCHEMA_VERSION,PROMPT_VERSION])
    check()
    with store.connect() as c:
        if not _active(c,campaign):raise InterruptedError('Campagna sospesa')
        cached=c.execute("SELECT body FROM commercial_ai_executions WHERE cache_key=? AND status='completed' AND started_at>=? ORDER BY id DESC LIMIT 1",(key,time.time()-cfg['cache_ttl_hours']*3600)).fetchone()
    if cached:
        prior=json.loads(cached[0])
        try:prior['output']=validate_output(prior['output'],candidate_id,evidence,result,payload.get('images'))
        except ValueError:return _save_event(store,campaign,engine,candidate_id,cfg,key,reason,_base(cfg,result,'fallback','cached_claim_no_longer_supported'))
        body={**_base(cfg,result,'cache_hit'),'output':prior['output'],'fallback':False,'cache_hit':True,'differences':_differences(result,prior['output']),'evidence':evidence,'bundle_metrics':bundle_metrics,'estimated_cost':0,'reported_cost':0,'cost_kind':'REPORTED_COST','simulated':cfg['provider']=='MOCK'}
        return _save_event(store,campaign,engine,candidate_id,cfg,key,reason,body)
    rates=(cfg['input_cost_per_million'],cfg['output_cost_per_million'])
    if cfg['provider']=='REMOTE' and any(v is None for v in rates):return _save_event(store,campaign,engine,candidate_id,cfg,key,reason,_base(cfg,result,'fallback','unknown_cost_no_dispatch'))
    cost=(cfg['max_input_tokens']*rates[0]+cfg['max_output_tokens']*rates[1])/1e6 if cfg['provider']=='REMOTE' else 0.0
    for attempt in range(cfg['max_retries']+1):
        check();ident,denied=_reserve(store,campaign,engine,candidate_id,cfg,key,reason,cost,estimated_input)
        if denied:return _save_event(store,campaign,engine,candidate_id,cfg,key,reason,_base(cfg,result,'budget_exhausted',denied))
        body=_base(cfg,result,'running');body.update(commercial_gate=gate,execution_id=ident,evidence=evidence,bundle_metrics=bundle_metrics,estimated_cost=cost,reported_cost=None,cost_kind='ESTIMATED_COST' if cfg['provider']=='REMOTE' else 'UNKNOWN_COST',simulated=cfg['provider']=='MOCK')
        start=time.monotonic();usage={};reported=None;output_tokens_estimate=None
        try:
            def guard():
                check()
                if time.monotonic()-start>=cfg['timeout']:raise TimeoutError('ai_timeout')
                with store.connect() as c:
                    if not _active(c,campaign):raise InterruptedError('Campagna sospesa')
            response=(provider or infer)(payload,cfg,guard)
            guard()
            if not isinstance(response,dict):raise ValueError('invalid_provider_response')
            usage=_usage(response.get('usage',{}));reported=_cost(response.get('reported_cost'))
            output_tokens_estimate=len(json.dumps(response.get('output'),ensure_ascii=False).encode())
            if usage.get('input_tokens',0)>cfg['max_input_tokens']:raise ValueError('input_token_limit')
            if usage.get('output_tokens',0)>cfg['max_output_tokens']:raise ValueError('output_token_limit')
            from .ai_diagnostics import diagnose
            body['validation']=diagnose(response.get('output'),candidate_id,evidence,result,payload.get('images'))
            validated=validate_output(response.get('output'),candidate_id,evidence,result,payload.get('images'))
            body.update(status='completed',output=validated,fallback=False,differences=_differences(result,validated))
        except InterruptedError:
            body.update(status='cancelled',error='stopped_or_generation_changed')
        except TimeoutError:
            body.update(status='timeout',error='ai_timeout')
        except ProviderError as exc:
            usage=_usage(exc.usage)
            body.update(status='error' if exc.retryable else 'invalid',error=str(exc))
        except Exception as exc:
            # No arbitrary exception details (providers can echo sensitive payloads).
            safe=str(exc) if isinstance(exc,ValueError) and re_safe(str(exc)) else type(exc).__name__
            body.update(status='invalid' if isinstance(exc,ValueError) else 'error',error=safe)
        if body.get('status')=='invalid' and body.get('validation'):
            from .private_diagnostics import retain
            try:retain(store,ident,body['validation'])
            except (OSError,ValueError):pass  # diagnostic storage cannot alter official decisions
        body.update(duration=round(time.monotonic()-start,4),usage=usage,estimated_input_tokens=estimated_input,estimated_output_tokens=output_tokens_estimate,reported_cost=reported)
        if reported is not None:body['cost_kind']='REPORTED_COST'
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not _active(c,campaign):body.update(status='cancelled',output=None,fallback=True,error='stopped_or_generation_changed')
            c.execute('UPDATE commercial_ai_executions SET status=?,estimated_cost=?,reported_cost=?,input_tokens=?,output_tokens=?,estimated_output_tokens=?,duration=?,body=? WHERE id=?',(body['status'],cost,reported,usage.get('input_tokens'),usage.get('output_tokens'),output_tokens_estimate,body['duration'],json.dumps(body),ident))
        if body['status']=='cancelled':raise InterruptedError('Campagna sospesa')
        if body['status'] not in ('error','timeout') or attempt==cfg['max_retries']:return body
    return body


def re_safe(value):
    import re
    return bool(re.fullmatch(r'[a-z_]{3,80}',value))


def _usage(value):
    if not isinstance(value,dict):return {}
    return {k:value[k] for k in ('input_tokens','output_tokens','total_tokens','cached_input_tokens','reasoning_tokens') if type(value.get(k)) is int and 0<=value[k]<=10_000_000}


def _cost(value):
    return float(value) if type(value) in (int,float) and math.isfinite(value) and value>=0 else None


def _differences(result,output):
    if output.get('task')=='WEBSITE_AUDIT_CONTEXT':return []
    old=(result.get('commercial_intent') or {}).get('intent','UNKNOWN');new=output['commercial_intent']
    return [{'field':'commercial_intent','official':old,'ai':new}] if old!=new else []


def _images(images,candidate_id):
    import base64
    if not isinstance(images,list) or len(images)>2:raise ValueError('invalid_visual_evidence')
    result=[]
    for item in images:
        if not isinstance(item,dict) or item.get('candidate_id')!=str(candidate_id) or item.get('mime_type') not in ('image/png','image/jpeg') or item.get('acquisition')!='authorized_fixture' or not isinstance(item.get('data'),bytes) or len(item['data'])>1_000_000:raise ValueError('invalid_visual_evidence')
        if (item['mime_type']=='image/png' and not item['data'].startswith(b'\x89PNG\r\n\x1a\n')) or (item['mime_type']=='image/jpeg' and not item['data'].startswith(b'\xff\xd8\xff')):raise ValueError('invalid_visual_format')
        result.append({'id':'VISUAL_'+fingerprint(base64.b64encode(item['data']).decode())[:20],'mime_type':item['mime_type'],'data':base64.b64encode(item['data']).decode(),'limits':['Fixture locale; nessun contenuto social scaricato.']})
    return result


def lookup(store,cid,candidate_id,engine=None):
    where='campaign_id=? AND candidate_id=?';args=[cid,str(candidate_id)]
    if engine:where+=' AND engine=?';args.append(engine)
    with store.connect() as c:row=c.execute('SELECT body FROM commercial_ai_executions WHERE '+where+' ORDER BY id DESC LIMIT 1',args).fetchone()
    return json.loads(row[0]) if row else None


def summary(store,cid):
    with store.connect() as c:rows=c.execute('SELECT * FROM commercial_ai_executions WHERE campaign_id=? ORDER BY id',(cid,)).fetchall()
    attempts=[r for r in rows if r['attempt']]
    from collections import Counter
    bodies=[json.loads(r['body']) for r in rows]
    diagnostics=dict(Counter(b.get('validation',{}).get('code','NOT_RECORDED') for b in bodies if b.get('status') in ('completed','invalid')))
    bundles=[b['bundle_metrics'] for b in bodies if b.get('bundle_metrics')]
    engine_detail={}
    for engine in sorted({r['engine'] for r in rows}):
        er=[r for r in rows if r['engine']==engine];eb=[json.loads(r['body']) for r in er]
        engine_detail[engine]={'calls':sum(bool(r['attempt']) for r in er),'avoided':sum(r['status']=='skipped' for r in er),'states':dict(Counter(r['status'] for r in er)),'skip_reasons':dict(Counter(b.get('error') for b in eb if b.get('status')=='skipped')),'validation_categories':dict(Counter(b.get('validation',{}).get('category','NOT_RECORDED') for b in eb if b.get('status')=='invalid')),'input_tokens':sum(r['input_tokens'] or 0 for r in er),'output_tokens':sum(r['output_tokens'] or 0 for r in er),'reserved_cost':sum(r['reserved_cost'] or 0 for r in er)}
    return {'engine_details':engine_detail,'calls_avoided':sum(r['status']=='skipped' for r in rows),'skip_reasons':dict(Counter(b.get('error') for b in bodies if b.get('status')=='skipped')),'validation_categories':diagnostics,'evidence_bundle_coverage':{'bundles':len(bundles),'selected':sum(b['evidence_selected'] for b in bundles),'available':sum(b['evidence_available'] for b in bundles),'insufficient':sum(b['status']=='EVIDENCE_INSUFFICIENT' for b in bundles)},'calls':len(attempts),'cache_hits':sum(r['cache_hit'] for r in rows),'estimated_cost':sum(r['estimated_cost'] if r['estimated_cost'] is not None else r['reserved_cost'] for r in attempts),'reported_cost':(sum(r['reported_cost'] for r in attempts) if attempts and all(r['reported_cost'] is not None for r in attempts) else None),'reported_cost_known_subtotal':sum(r['reported_cost'] or 0 for r in attempts),'reported_cost_known_calls':sum(r['reported_cost'] is not None for r in attempts),'unknown_cost_calls':sum(r['reported_cost'] is None for r in attempts),'errors':sum(r['status'] in ('invalid','timeout','error','abandoned') for r in attempts),'fallbacks':sum(r['status'] not in ('completed','cache_hit') for r in rows),'by_engine':{engine:sum(r['engine']==engine for r in attempts) for engine in sorted({r['engine'] for r in rows})},'states':{state:sum(r['status']==state for r in rows) for state in sorted({r['status'] for r in rows})},'input_tokens':sum(r['input_tokens'] or 0 for r in attempts),'output_tokens':sum(r['output_tokens'] or 0 for r in attempts),'usage_known_calls':sum(r['input_tokens'] is not None and r['output_tokens'] is not None for r in attempts)}
