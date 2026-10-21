"""Offline campaign-39 replay. Frozen inputs, no production DB or network.

Print JSON to stdout; optional --output writes a requested local artifact.
Historical browser failures are never replaced by simulated successes.
"""
import copy,gzip,json,sys,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.agent6 import qualification,commercial_view
from sales.research_analysis import identity_from
from sales.commercial import target_fit

FIXTURE=Path(__file__).resolve().parents[1]/'tests/fixtures/agent91/campaign39.json.gz'


def load():return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def replay_case(case):
    before=case['record']['body'];body=copy.deepcopy(before);flow=case['record']['flow']
    if before.get('website_audit'):
        pages=[p for p in case['pages'] if p.get('status')==200 and p.get('purpose')!='external_solution']
        ident=identity_from(pages) if pages else {}
        fit=target_fit.evaluate(ident,pages,{'eligible':ident.get('region') in load()['configuration']['regions']}) if pages else {}
        body['commercial_fit']=fit
        if not fit.get('audit_allowed'):
            body.update(state='REJECTED' if fit.get('status')=='NOT_SUITABLE' else 'NEEDS_REVIEW',
                reason='Preselezione offline: '+', '.join(fit.get('reasons',[])))
            if fit.get('source_role') in ('directory','training_provider','multi_company_catalog','institution'):
                body.update(identity_verified=False,entity_key=None,official_domain=None,contacts=[])
        body['replay']={'new_browser_measurements':0,'historical_audit_retained':True}
        return commercial_view.enrich(body)
    docs=before.get('documents',[])
    source=copy.deepcopy(docs[0]) if docs else {'url':before['url'],'title':before.get('title',''),
        'text':'','original':False,'checked_at':before.get('checked_at')}
    task='RESEARCH_READ_6' if docs else 'RESEARCH_SCREEN_6'
    available=[a for a in case['ai_executions'] if a['response'].get('task')==task]
    if not available:
        body['replay']={'insufficient_saved_ai':True};return commercial_view.enrich(body)
    # Use the FIRST recorded page output, before the historical paid repair.
    saved=available[0]['response'];evidence=saved['evidence']
    rid=next(e['result_id'] for e in evidence if e['url']==before['url'])
    analysis=next((a for a in (saved.get('output') or {}).get('analyses',[]) if a['result_id']==rid),None)
    if not docs:source['text']='\n'.join(e['text'] for e in evidence if e['url']==before['url'])
    identity=identity_from(case['pages']) if case['pages'] else None
    body=qualification.evaluate(source,analysis,evidence,flow,identity)
    body.update(documents=docs,query=before.get('query'),strategy=before.get('strategy'),
        replay={'historical_ai_execution':available[0]['id'],'new_ai_calls':0,'saved_original':bool(docs)})
    return commercial_view.enrich(body)


def report():
    fixture=load();rows=[]
    for case in fixture['cases']:
        old=case['record'];new=replay_case(case)
        rows.append({'record_id':old['id'],'flow':old['flow'],'url':old['body']['url'],
            'before':{'name':old['body'].get('entity_name'),'state':old['state'],'kind':old['body'].get('kind')},
            'after':{'name':new.get('entity_name'),'state':new['state'],'kind':new.get('kind'),
                'identity_verified':new.get('identity_verified'),'contacts':new.get('contacts',[]),
                'promising':new['completion_queue']['promising'],'missing':new.get('missing',[]),
                'reason':new.get('reason'),'budget':new.get('budget'),'completion':new.get('deterministic_completion'),
                'browser_status':new.get('website_audit',{}).get('browser_status')},
            'evidence_fields':sorted({f['field'] for f in new.get('facts',[]) if f.get('original')})})
    return {'mode':'offline_replay_not_new_campaign','historical_campaign':39,'cases':rows,
        'observed_90':{'ai_calls':100,'valid':58,'partial':37,'invalid':5,'serper_calls':35,
            'qualified':0,'estimated_cost_usd':0.249648},
        'replay_91':{'reviewed_cases':len(rows),'new_ai_calls':0,'new_serper_calls':0,
            'qualified':sum(r['after']['state'] in ('VERIFIED','POTENTIAL') for r in rows),
            'promising':sum(r['after']['promising'] for r in rows),
            'new_browser_measurements':0,'external_calls':0,'production_writes':0},
        'limits':['Targeted 11-case regression sample, not a new representative campaign.',
            'Frozen AI outputs are reused; future provider outputs and cost savings are not predicted.',
            'Partial historical browsers stay partial; no new freshness, availability or budget evidence.',
            'No paid call or customer conversion is simulated as an observed result.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    value=json.dumps(report(),ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(value)
    else:print(value)
