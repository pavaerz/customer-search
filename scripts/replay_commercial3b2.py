"""Offline 3B.2 replay. Frozen fixtures only; no store/provider/browser instances."""
import copy,gzip,hashlib,json
from collections import Counter
from pathlib import Path
from sales.commercial.discovery import assess
from sales.commercial.qualification import evaluate
from sales.commercial.context import documents
from sales.commercial.evidence import select,trim_to_payload
from sales.commercial.ai import interpretation_documents,eligibility
from sales.commercial.ai_schema import SYSTEM,response_schema,SCHEMA_VERSION,PROMPT_VERSION

ROOT=Path(__file__).resolve().parents[1];FIXTURE=ROOT/'tests/fixtures/commercial3b2'
def load(path):
    with gzip.open(path,'rt') as f:return json.load(f)
def body(row):
    b=row.get('body',row);return json.loads(b) if isinstance(b,str) else b

def replay(cid):
    data=load(FIXTURE/f'campaign{cid}.json.gz');pages=data['pages'];docs=data['documents']
    if cid==15:
        pages=load(ROOT/'tests/fixtures/commercial3b/campaign15-pages.json.gz')['pages']
    discovery=[]
    for row in data['commercial_discovery']:
        b=body(row);new=assess(b,row['engine'],b.get('origin'))
        discovery.append({'id':row['id'],'engine':row['engine'],'url':row['url'],'query':row['query'],'region':b.get('origin',{}).get('region'),
                          'before':row['decision'],'after':new['decision'],'reason':new['reason'],'result_type':new.get('result_type'),'priority':new['priority']})
    revisions=[]
    for row in data['commercial_revisions']:
        old=body(row);new=copy.deepcopy(old);url=old['url'];engine=old['engine'];scope='not_replayed_missing_original'
        hint=old.get('discovery') or {'url':url,'title':old.get('title','')}
        pre=assess(hint,engine)
        if engine!='WEBSITE_REBUILD' and url in pages and old.get('identity') and old.get('geography'):
            new=evaluate(engine,old['identity'],pages[url],old['geography']);new['identity']=copy.deepcopy(old['identity']);new['discovery']=old.get('discovery',{});scope='original_html_qualification'
        elif engine=='WEBSITE_REBUILD':scope='saved_measurements_only_no_browser_rerun'
        elif old.get('social'):scope='index_hint_only_no_currentness_verification'
        candidate_docs=[copy.deepcopy(d) for d in docs if d.get('id') in old.get('document_ids',[])]
        if not candidate_docs:
            urls={old.get('url'),old.get('website')}
            candidate_docs=[copy.deepcopy(d) for d in docs if d['url'] in urls]
        # Re-extract only from timestamp-matched saved HTML; source text is not invented.
        for d in candidate_docs:
            if d['url'] in pages:d['evidence_channels']=documents(pages[d['url']])
        if cid==15:
            candidate_docs=[{'id':'saved15:'+u,'url':u,'text':'','evidence_channels':documents(p),'checked_at':p['checked_at']} for u,p in pages.items() if u in {url,old.get('website')}]
        inputs=interpretation_documents(new,candidate_docs)
        evidence,metrics=select(row['opportunity_id'],inputs,8192,new)
        payload={'candidate_id':str(row['opportunity_id']),'engine':engine,'evidence':evidence,'schema_version':SCHEMA_VERSION,'prompt_version':PROMPT_VERSION,'schema':response_schema()}
        if engine=='WEBSITE_REBUILD':
            browser=new.get('browser') or {};screen=new.get('screening') or {}
            payload['technical_context']={'screening':screen.get('status'),'browser_completed':browser.get('completed',False),'browser_outcome':new.get('browser_outcome'),'limits':list(dict.fromkeys([*new.get('limits',[]),*browser.get('limits',[])]))[:6],'measured_findings':[{k:e.get(k) for k in ('code','quote','url','severity','category')} for e in new.get('evidence',[]) if e.get('kind')=='measurement'][:8]}
        trim_to_payload(payload,SYSTEM,8192,metrics)
        revisions.append({'id':row['id'],'url':url,'engine':engine,'scope':scope,'before':{'state':old['state'],'company':old.get('company'),'classification':old.get('classification')},
                          'after':{'state':new['state'] if scope=='original_html_qualification' else None,'company':new.get('company'),'classification':new.get('classification'),'actor_attribution':new.get('actor_attribution'),'contract':new.get('contract'),'compensation':new.get('compensation'),'verification':new.get('verification')},
                          'preflight':pre['decision'],'ai_eligible':eligibility(new),'bundle':metrics,'selected_evidence':[{'id':e['id'],'text':e['text'],'url':e['url'],'roles':e['roles']} for e in evidence],
                          'technical_context':payload.get('technical_context'),'browser':{'outcome':old.get('browser_outcome'),'completed':old.get('browser',{}).get('completed'),'remeasured':False}})
    queries=[]
    for task in data['research_tasks']:
        if task['kind']!='search':continue
        p=task['payload'];p=json.loads(p) if isinstance(p,str) else p
        items=[d for d in discovery if d['query']==p.get('query') and d['engine']==task['strategy']]
        queries.append({'engine':task['strategy'],'query':p.get('query'),'family':p.get('family'),'region':p.get('region'),'task_state':task['state'],'appearances':len(items),'historical_admitted':sum(d['before']=='admit' for d in items),'new_preflight_admitted':sum(d['after']=='admit' for d in items),'new_reasons':dict(Counter(d['reason'] for d in items if d['after']=='exclude'))})
    from sales.commercial.ai_diagnostics import diagnose
    ai_replay=[]
    for row in data['commercial_ai_executions']:
        b=body(row);old=next((body(r) for r in data['commercial_revisions'] if str(r['opportunity_id'])==str(row['candidate_id'])),{})
        ai_replay.append({'execution_id':row['id'],'engine':row['engine'],'historical_status':row['status'],
                         'new_validation':diagnose(b['output'],row['candidate_id'],b.get('evidence',[]),old) if b.get('output') else None,
                         'scope':'saved_output_validation' if b.get('output') else 'not_reproducible_original_output_not_retained',
                         'input_tokens':row.get('input_tokens'),'output_tokens':row.get('output_tokens'),
                         'reserved_cost':row.get('reserved_cost'),'reported_cost':row.get('reported_cost')})
    engines={}
    for engine in ('FREELANCE','AGENCIES','STARTUPS','WEBSITE_REBUILD'):
        ds=[d for d in discovery if d['engine']==engine];rs=[body(r) for r in data['commercial_revisions'] if body(r)['engine']==engine]
        tasks=[t for t in data['research_tasks'] if t['strategy']==engine]
        engines[engine]={'queries':sum(t['kind']=='search' for t in tasks),'appearances':len(ds),'candidate_tasks':sum(t['kind']=='candidate' for t in tasks),
                         'historical_evaluations':len(rs),'historical_states':dict(Counter(r['state'] for r in rs)),
                         'identity_verified':sum(r.get('identity',{}).get('identity_status')=='verified' for r in rs),
                         'request_verified':sum(bool(r.get('verification',{}).get('request_verified')) for r in rs),
                         'currently_open':sum(bool(r.get('verification',{}).get('currently_open')) for r in rs),
                         'new_preflight_exclusions':dict(Counter(d['reason'] for d in ds if d['after']=='exclude')),
                         'historical_ai_calls':sum(a['engine']==engine for a in ai_replay),
                         'historical_browser_attempts':sum(bool(r.get('browser',{}).get('executed')) for r in rs),
                         'historical_browser_complete':sum(bool(r.get('browser',{}).get('completed')) for r in rs)}
    return {'campaign':cid,'by_engine':engines,'ai_saved_output_replay':ai_replay,'historical':{'appearances':len(discovery),'states':dict(Counter(body(r)['state'] for r in data['commercial_revisions'])),'ai_attempts':len([a for a in data['commercial_ai_executions'] if a.get('attempt')])},
            'new_code':{'preflight_admitted':sum(d['after']=='admit' for d in discovery),'preflight_excluded':sum(d['after']=='exclude' for d in discovery),'qualification_replayed':sum(r['scope']=='original_html_qualification' for r in revisions),'replayed_states':dict(Counter(r['after']['state'] for r in revisions if r['after']['state']))},
            'queries':queries,'discovery':discovery,'revisions':revisions,'missing_pages':data['missing_pages'],'historical_resource_ledger':data['commercial_resources'],'historical_operation_types':dict(Counter((r.get('kind') or r.get('operation') or 'unknown') for r in data['discovery_operations'])),'live_calls':0,'new_ai_outputs':0,'browser_runs':0}

def main():
    report={'phase':'3B.2','method':'Frozen public saved data; preflight replay and bounded original HTML qualification. No AI inference, no missing HTTP simulated; historical states are not ground truth.',
            'fixtures':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*FIXTURE.glob('*.gz'),ROOT/'tests/fixtures/commercial3b/campaign15-pages.json.gz']},
            'campaigns':[replay(cid) for cid in (15,16,19)],'synthetic_cases':'tests/test_commercial_intelligence3b2.py: separately labelled; no invented market performance',
            'limitations':['No real model response for new bundles.','No browser remeasurement.','Eligibility and selected evidence are not opportunities or acquired clients.','Only saved HTML with matching acquisition timestamp is reused.']}
    path=ROOT/'PHASE-3B.2-METRICS.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{k:c[k] for k in ('campaign','historical','new_code','live_calls')} for c in report['campaigns']],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
