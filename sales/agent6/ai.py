"""New task schema over the existing cancellable provider and shared AI ledger."""
import json,time,copy,re
from datetime import datetime,timezone,timedelta
from sales.db import digest,encode,now
from sales.commercial.ai import _reserve,_save_event,_active,_usage,validate_config
from sales.commercial.ai_provider import infer,ProviderError
from . import schema,budget
from .grounding import provider_payload

def input_bytes(payload):
    from sales.commercial.ai_tasks import system_for,schema_for
    task=payload['task']
    # Use the actual task's system prompt and structured-output schema. Bytes
    # remain a conservative local token bound, not a provider tokenizer. Include
    # message framing instead of charging website reviews for the planner text.
    return (len(json.dumps(provider_payload(payload),ensure_ascii=False).encode())+
            len(system_for(task).encode())+len(json.dumps(schema_for(task),ensure_ascii=False).encode())+128)

def has_saved_work(store,campaign,flow,key,stage):
    ledger_key='agent6:verify:'+key if stage=='verify' else 'agent6:'+stage+':'+flow+':'+key
    with store.connect() as c:
        return bool(c.execute("SELECT 1 FROM commercial_ai_executions WHERE campaign_id=? AND engine=? AND candidate_id=? AND attempt=1 AND status IN ('completed','invalid','timeout','error') AND json_extract(body,'$.resume_protocol')=7 LIMIT 1",(campaign['id'],flow,ledger_key)).fetchone())

def replay(store,campaign,flow,ledger_key,cachekey,payload,input_fingerprint=None,legacy_cachekey=None):
    """Resume a completed logical call, including partial responses, for free.

    A plan's history may change after it was saved; its task identity remains.
    Document calls must additionally match the exact evidence fingerprint.
    Cancelled/abandoned work is never presented as a completed evaluation.
    """
    with store.connect() as c:
        if not _active(c,campaign):raise InterruptedError('Campagna sospesa')
        rows=c.execute("SELECT body,cache_key FROM commercial_ai_executions WHERE campaign_id=? AND engine=? AND candidate_id=? AND attempt=1 ORDER BY id DESC",(campaign['id'],flow,ledger_key)).fetchall()
    for row in rows:
        saved=json.loads(row['body'])
        if saved.get('resume_protocol')!=7 or saved.get('status') not in ('completed','invalid','timeout','error'):continue
        same_input=bool(input_fingerprint and saved.get('input_fingerprint')==input_fingerprint)
        legacy=bool(legacy_cachekey and row['cache_key']==legacy_cachekey)
        if row['cache_key']!=cachekey and payload['task']!=schema.PLAN and not (same_input or legacy):continue
        if saved.get('output'):
            clean=copy.deepcopy(saved['output'])
            for a in clean.get('analyses',[]):
                a.pop('evidence_status',None);a.pop('identity_issues',None);a.pop('field_errors',None)
                a['missing']=a.get('missing',[])[:8]
            value,_=schema.validate_response(clean,payload)
            # Keep withholding diagnostics from the original validation.
            for a in value.get('analyses',[]):
                old=next(x for x in saved['output']['analyses'] if x['result_id']==a['result_id'])
                if old.get('identity_issues'):a['identity_issues']=old['identity_issues']
                if old.get('field_errors'):a['field_errors']=old['field_errors'];a['missing']=old['missing']
            saved['output']=value
        return {**saved,'replayed':True,'replayed_prior_contract':row['cache_key']!=cachekey and payload['task']!=schema.PLAN}

def call(store,campaign,flow,key,payload,check,provider=None):
    result=_call_once(store,campaign,flow,key,payload,check,provider)
    cfg=validate_config(campaign['filters']['commercial']['ai'])
    if (payload['task']=='COMMERCIAL_DECISION_1' and not payload.get('repair')
            and cfg['max_retries']>0 and result['status']=='invalid'
            and result.get('error') in ('unknown_or_ambiguous_segment','unsupported_actor','unknown_assessment_fact','wrong_geography_fact')):
        # Same candidate identity: the atomic ledger enforces its existing cap,
        # flow/campaign/cost limits, concurrency and Stop. At most ONE repair;
        # resume replays both receipts rather than paying for them again.
        repaired={**payload,'repair':{
            'execution_id':result['execution_id'],'code':result['error'],
            'instruction':'Reassess the complete decision using only the supplied segment IDs. '
                          'Never cite a document ID or link ID as a fact. Use a complete '
                          'evidenced subject name or leave it empty. Do not invent or '
                          'upgrade a request to make validation pass. Assessment fact '
                          'indices start at zero and must refer to your actual facts array. '
                          'Geography indices must refer only to facts explicitly labelled geography. '
                          'A passage containing both a request and its location may support two '
                          'separate facts; never borrow a publisher or another role location.'}}
        retry=_call_once(store,campaign,flow,key,repaired,check,provider)
        if retry['status'] not in ('budget_exhausted','skipped'):
            return retry
    return result


def _call_once(store,campaign,flow,key,payload,check,provider=None):
    cfg=validate_config(campaign['filters']['commercial']['ai']);payload=copy.deepcopy(payload)
    if payload.get('evidence'):
        from .grounding import attach
        payload['evidence']=attach(payload['evidence'])
    stage=budget.stage_for(key,payload)
    ledger_key=('agent6:verify:'+key if stage=='verify' else 'agent6:'+stage+':'+flow+':'+key)
    # New commercial decisions use a local text tokenizer, including the actual
    # per-request schema. Legacy replay keeps its previous byte-bound behavior.
    def estimate():
        if payload['task']=='COMMERCIAL_DECISION_1':
            from sales.commercial.token_count import estimate as count
            return count(payload,cfg)
        return {'tokens':input_bytes(payload),'basis':'legacy_utf8_bytes','exact':False}
    try:
        estimate()
    except (ImportError,OSError,ValueError):
        return _save_event(store,campaign,flow,ledger_key,cfg,'',payload['task'],
            {'status':'skipped','output':None,'error':'tokenizer_unavailable',
             'stage':stage,'fallback':True,'cache_hit':False})
    while estimate()['tokens']>cfg['max_input_tokens'] and payload.get('evidence'):
        last=payload['evidence'][-1]
        # Try complete source lines before discarding the entire lowest-priority
        # passage. Headers often contain the employer name and publication date;
        # losing a 900-character header for a small overrun loses those facts.
        boundaries=[m.start() for m in re.finditer(r'\n',last['text']) if m.start()>0]
        fitted=False
        for end in reversed(boundaries):
            part=last['text'][:end]
            shortened={**last,'text':part,'hash':digest(part)}
            from .grounding import segments
            shortened['segments']=segments(shortened)
            payload['evidence'][-1]=shortened
            if estimate()['tokens']<=cfg['max_input_tokens']:
                fitted=True;break
        if fitted:break
        payload['evidence'].pop()
    if payload.get('response_channels'):
        # Never offer a route whose citable control was removed by the input
        # bound. The original observation remains stored outside this payload.
        surviving={e['id'] for e in payload.get('evidence',[])}
        payload['response_channels']=[c for c in payload['response_channels']
                                      if c.get('evidence_id') in surviving]
    # Planner history is descriptive context: trim oldest samples, never proofs.
    if payload['task']==schema.PLAN:
        while input_bytes(payload)>cfg['max_input_tokens']:
            arrays=[(k,v) for k,v in payload.get('memory',{}).items() if isinstance(v,list) and v]
            if not arrays:break
            # Preserve the latest two concrete query observations while other
            # history can be trimmed. A longer provenance label must not erase
            # all observed searches in favour of abstract strategy summaries.
            alternatives=[v for k,v in arrays if k!='recent_queries' or len(v)>2]
            max(alternatives or [v for _,v in arrays],key=lambda x:len(encode(x))).pop()
    legacy_cachekey=digest(encode([cfg['provider'],cfg['endpoint'],cfg['model'],
        'commercial-assessment-v3' if payload['task']=='COMMERCIAL_DECISION_1' else '7.0-segments',payload]))
    cachekey=legacy_cachekey;input_fingerprint=None;contract_fingerprint=None
    if payload['task']=='DISCOVERY_TRIAGE_1':
        from sales.commercial.ai_tasks import system_for,request_schema
        # A changed source-selection contract must not reuse an older semantic
        # cache merely because the SERP is identical. Same-contract resume
        # remains free through the ordinary persisted execution receipt.
        cachekey=digest(encode(['discovery-triage-contract-v1',legacy_cachekey,
                               system_for(payload['task']),request_schema(payload)]))
    if payload['task']=='COMMERCIAL_DECISION_1':
        from sales.commercial.ai_tasks import system_for,request_schema
        input_fingerprint=digest(encode([cfg['provider'],cfg['endpoint'],cfg['model'],payload]))
        contract_fingerprint=digest(encode([system_for(payload['task'],payload),request_schema(payload)]))
        cachekey=digest(encode(['commercial-contract-v4',input_fingerprint,contract_fingerprint]))
    base={'status':'skipped','output':None,'error':None,'mode':cfg['mode'],'provider':cfg['provider'],'model':cfg['model'],'cache_hit':False,'task':payload['task'],'stage':stage,'allocation':budget.allocation(campaign,cfg,flow),'decision_authority':'validated_research_actions_only','fallback':True}
    base['purpose']=budget.purpose(payload)
    if payload['task']=='COMMERCIAL_DECISION_1':
        base['decision_authority']='commercial_decision_with_evidence_validation'
        base['input_estimate']=estimate()
        base['repair_of']=(payload.get('repair') or {}).get('execution_id')
        base.update(input_fingerprint=input_fingerprint,contract_fingerprint=contract_fingerprint)
    def skipped(reason,status='skipped'):
        return _save_event(store,campaign,flow,ledger_key,cfg,cachekey,payload['task'],{**base,'status':status,'error':reason})
    check()
    previous=replay(store,campaign,flow,ledger_key,cachekey,payload,input_fingerprint,legacy_cachekey)
    if previous:return previous
    if not cfg['enabled'] or cfg['provider']=='DISABLED':return skipped('ai_disabled')
    if estimate()['tokens']>cfg['max_input_tokens']:return skipped('input_budget')
    if payload['task'] in (schema.READ,schema.SCREEN,'COMMERCIAL_DECISION_1') and not payload.get('evidence'):return skipped('evidence_insufficient')
    if payload['task']=='COMMERCIAL_DECISION_1' and not any(
            e.get('origin')!='original_metadata' and e['text'].strip() for e in payload['evidence']):
        return skipped('commercial_text_missing')
    with store.connect() as c:
        cached=c.execute('SELECT body FROM agent6_cache WHERE key=? AND created_at>?',(cachekey,(datetime.now(timezone.utc)-timedelta(hours=cfg['cache_ttl_hours'])).isoformat())).fetchone()
    if cached:
        value,validation_errors=schema.validate_response(json.loads(cached[0]),payload)
        return _save_event(store,campaign,flow,ledger_key,cfg,cachekey,payload['task'],{**base,'status':'cache_hit','output':value,'validation_errors':validation_errors,'partial':bool(validation_errors),'fallback':False,'cache_hit':True,'estimated_cost':0,'evidence':payload.get('evidence',[])})
    rates=(cfg['input_cost_per_million'],cfg['output_cost_per_million'])
    if cfg['provider']=='REMOTE' and None in rates:return skipped('cost_unknown')
    cost=(cfg['max_input_tokens']*rates[0]+cfg['max_output_tokens']*rates[1])/1e6 if cfg['provider']=='REMOTE' else 0
    ident,denied,ledger_key,stage,caps=budget.reserve(store,campaign,flow,key,payload,cfg,cachekey,cost,estimate()['tokens'])
    if denied:return skipped(denied,'budget_exhausted')
    def guard():
        check()
        with store.connect() as c:
            if not _active(c,campaign):raise InterruptedError('Campagna sospesa')
    start=time.monotonic();usage={};result={**base,'status':'running','execution_id':ident,'resume_protocol':7};raw=None
    try:
        response=(provider or infer)(payload,cfg,guard);usage=_usage(response.get('usage',{}));raw=response.get('output');guard()
        if usage.get('input_tokens',0)>cfg['max_input_tokens'] or usage.get('output_tokens',0)>cfg['max_output_tokens']:raise ValueError('token_limit')
        value,validation_errors=schema.validate_response(raw,payload)
        result.update(status='completed',output=value,fallback=False,validation_errors=validation_errors,partial=bool(validation_errors))
    except InterruptedError:result.update(status='cancelled',error='stopped')
    except ProviderError as exc:usage=_usage(exc.usage);result.update(status='error',error=str(exc),retryable=exc.retryable)
    except TimeoutError:result.update(status='timeout',error='timeout')
    except schema.ValidationError as exc:result.update(status='invalid',error=str(exc),diagnostic=exc.diagnostic)
    except Exception as exc:result.update(status='invalid',error=str(exc) if type(exc) is ValueError and str(exc).replace('_','').isalpha() else 'invalid_response')
    estimate=(usage['input_tokens']*rates[0]+usage['output_tokens']*rates[1])/1e6 if cfg['provider']=='REMOTE' and {'input_tokens','output_tokens'}<=set(usage) else cost
    if result['status']=='invalid':
        result.setdefault('diagnostic',{'code':result['error']})
        result['diagnostic'].update(task=payload['task'],stage=stage,evidence_count=len(payload.get('evidence',[])),result_count=len(payload.get('result_ids',[])),output_hash=digest(encode(raw)) if raw is not None else None)
    result.update(usage=usage,reserved_cost=cost,estimated_cost=estimate,reported_cost=None,evidence=payload.get('evidence',[]),duration=time.monotonic()-start,raw_response_retained=False)
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not _active(c,campaign):result.update(status='cancelled',output=None,error='stopped')
        if result['status']=='invalid' or result.get('validation_errors'):
            from .diagnostics import retain
            result['diagnostic_excerpt_retained']=retain(c,ident,campaign['id'],payload['task'],raw,result.get('validation_errors') or result.get('diagnostic'))
        else:
            from .diagnostics import purge
            purge(c)
        c.execute('UPDATE commercial_ai_executions SET status=?,estimated_cost=?,input_tokens=?,output_tokens=?,duration=?,body=? WHERE id=?',(result['status'],estimate,usage.get('input_tokens'),usage.get('output_tokens'),result['duration'],encode(result),ident))
        if result['status']=='completed' and not result.get('validation_errors'):
            # Store schema output, without derived validation-only keys.
            original=json.loads(raw) if isinstance(raw,str) else json.loads(json.dumps(raw))
            for a in original.get('analyses',[]):a.pop('evidence_status',None)
            c.execute('INSERT OR REPLACE INTO agent6_cache VALUES (?,?,?)',(cachekey,encode(original),now()))
    if result['status']=='cancelled':raise InterruptedError('Campagna sospesa')
    return result
