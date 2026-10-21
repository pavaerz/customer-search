"""Prepare evidence-bound evaluation inputs from saved originals, without AI.

Uses the real reader and input-budget adapter in temporary test databases.
Network, inference and worker loops are disabled. Labels live only in the
review manifest, never in the model payloads. Run with tests/offline_guard.
"""
import copy
import gzip
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from sales.agent6 import evidence, grounding
from sales.commercial.inspection import document
from sales.commercial.ai_provider import ProviderError
from sales.commercial.token_count import estimate
from sales.db import encode

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'implementation-report/commercial-objective/validation-inputs'


def fixtures():
    historical=json.loads((ROOT/'tests/fixtures/ai_first/historical.json').read_text())
    pages=json.loads(gzip.decompress((ROOT/'tests/fixtures/ai_first/commercial-originals.json.gz').read_bytes()))
    c44=json.loads((ROOT/'CUSTOMERSEARCH-AI-FIRST-LIVE-01-METRICS.json').read_text())
    reviews={r['url']:r for r in c44['manual_review']['cases']}
    cases=[]
    for item in historical['cases']:
        key=item['case']
        if key not in pages:
            continue
        allowed=[item['expected']]
        if key=='G':
            # Known stale, unverified requester: either decline this source or
            # request identity evidence, never promote it as a current request.
            allowed=['NOT_INTERESTING','NEEDS_RESEARCH']
        cases.append({'id':'historical-'+key,'flow':'AZIENDE' if key in ('D','E') else 'AGENCIES',
                      'page':pages[key][0],'select_requester':'Elice Group' if key=='F' else None,
                      'review':{'expected':item['expected'],'allowed':allowed,
                                'role':item.get('opportunity_type'),
                                'basis':'Saved original and existing historical review; not a live vacancy check.',
                                'record_id':item['record_id'],'campaign_id':item['campaign_id'],
                                'positive_means':'Standing invitation, paid projects and compensation unknown.' if key in ('A','B') else None}})
    saved=json.loads(gzip.decompress((ROOT/'tests/fixtures/ai_first/campaign44/originals.json.gz').read_bytes()))
    for item in saved:
        review=reviews[item['page']['url']]
        expected='NEEDS_RESEARCH' if review['record_id'] in (1168,1171) else 'NOT_INTERESTING'
        cases.append({'id':'campaign44-'+str(review['record_id']),'flow':review['flow'],
                      'page':item['page'],'select_requester':None,
                      'review':{'expected':expected,'allowed':['NEEDS_RESEARCH','NOT_INTERESTING'] if expected=='NEEDS_RESEARCH' else [expected],
                                'basis':review['commercial_review'],'record_id':review['record_id'],'campaign_id':44}})
    blocked=[]
    for item in c44['agent6_records']:
        body=item['body'];body=json.loads(body) if isinstance(body,str) else body
        if body.get('validation_status')=='ACCESS_BLOCKED' and 'linkedin.com/' in body.get('url',''):
            blocked.append({'record_id':item['id'],'url':body['url'],'state':item['state'],
                            'original_read':False,'ai_input_prepared':False,
                            'reason':'No saved social original: snippet excluded from commercial evaluation.'})
    return cases,blocked


def capture(case):
    # Test harness only creates a temporary database and opt-in test campaign;
    # it does not load production configuration, start workers or infer.
    from test_ai_first import IntegratedPath
    base=IntegratedPath();base.setUp()
    captured=[]
    def disabled_provider(payload,cfg,check):
        check()
        captured.append({'payload':copy.deepcopy(payload),'token_estimate':estimate(payload,cfg),
                         'config':{k:cfg[k] for k in ('model','max_input_tokens','max_output_tokens')}})
        raise ProviderError('OFFLINE_INPUT_CAPTURE_NO_INFERENCE')
    try:
        page=case['page']
        task_payload={'url':page['url'],'original_page':page,'depth':0}
        if case.get('select_requester'):
            packet=evidence.packet(page,document(page))
            unit=next(u for u in packet['units'] if 'Organizzazione: '+case['select_requester'] in u['text'])
            task_payload['unit_id']=unit['id']
        # Match C44's model/input/output configuration only, with MOCK
        # transport and a provider that cannot perform inference.
        base.c['filters']['commercial']['ai'].update(model='gpt-5.4-mini',
            max_input_tokens=8192,max_output_tokens=1500,max_retries=0)
        with base.store.connect() as db:
            db.execute('UPDATE campaigns SET filters=? WHERE id=?',(encode(base.c['filters']),base.c['id']))
        base.w.campaign=base.c
        base.w.enqueue('candidate',case['flow'],task_payload,case['id'])
        with base.store.connect() as db:
            row=db.execute('SELECT * FROM research_tasks WHERE fingerprint=?',(case['id'],)).fetchone()
            task={**dict(row),'payload':json.loads(row['payload'])}
        with patch('sales.agent6.ai.infer',side_effect=disabled_provider),patch(
                'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No source download allowed')),patch(
                'socket.create_connection',side_effect=AssertionError('No network allowed')):
            base.w.execute(task,lambda:None)
        with base.store.connect() as db:
            executions=[dict(r) for r in db.execute('SELECT status,body FROM commercial_ai_executions')]
        if len(captured)!=1:
            raise RuntimeError(case['id']+': capture count '+str(len(captured))+'; '+str([r['status'] for r in executions]))
        item=captured[0]
        if item['token_estimate']['tokens']>item['config']['max_input_tokens']:
            raise RuntimeError('Input exceeds configured maximum')
        item['wire_payload']=grounding.provider_payload(item['payload'])
        return item
    finally:
        base.tearDown()


def main():
    cases,blocked=fixtures()
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    for case in cases:
        item=capture(case)
        path=OUT/(case['id']+'.json')
        text=json.dumps(item,ensure_ascii=False,indent=2)+'\n'
        path.write_text(text);path.chmod(0o600)
        rows.append({'id':case['id'],'flow':case['flow'],'url':case['page']['url'],
                     'source_html_sha256':hashlib.sha256(case['page']['html'].encode()).hexdigest(),
                     'payload_file':path.name,'payload_sha256':hashlib.sha256(text.encode()).hexdigest(),
                     'estimated_input_tokens':item['token_estimate']['tokens'],
                     'identity':item['payload']['identity'],'review':case['review']})
    manifest={'mode':'offline_prepared_inputs_no_model_results','sources':rows,'blocked_social':blocked,
              'paid_calls':0,'serper_calls':0,'production_database_accesses':0,
              'max_configured_input_tokens':8192,'max_configured_output_tokens':1500,
              'proposed_evaluation':{'requires_explicit_approval':True,'maximum_ai_calls_including_repairs':20,
                                     'maximum_estimated_usd':0.50,'maximum_serper_calls':0,
                                     'campaigns_created_in_production':0,
                                     'scope':'Evaluate these frozen originals; not a live discovery campaign.'},
              'limits':['Only two labelled positive agency invitations; not market-representative.',
                        'No readable LinkedIn/Instagram original in this corpus.',
                        'No confirmed positive startup or proactive rebuild in this corpus.',
                        'No new AI accuracy, precision, recall or commercial conversion measured.']}
    path=OUT/'MANIFEST.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
    print(json.dumps({'originals':len(rows),'blocked_social':len(blocked),'paid_calls':0,
                      'largest_estimated_input':max(r['estimated_input_tokens'] for r in rows)}))


if __name__=='__main__':
    main()
