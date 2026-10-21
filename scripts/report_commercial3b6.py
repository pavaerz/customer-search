"""Assemble saved offline artifacts. No database, network or AI access."""
import json,re,hashlib,gzip
from pathlib import Path
from collections import Counter
from urllib.parse import urlsplit,urlunsplit
ROOT=Path(__file__).resolve().parents[1]
def read(p):
    from scripts.analysis_archive import read_text
    return json.loads(read_text(p))
def test_log(name):
    text=(ROOT/name).read_text();m=re.search(r'Ran (\d+) tests in ([\d.]+)s',text)
    return {'path':name,'tests':int(m[1]) if m else None,'seconds':float(m[2]) if m else None,'passed':bool(re.search(r'^OK$',text,re.M)),'resource_warning':'ResourceWarning' in text}
def build():
    prior=read('PHASE-3B.5-METRICS.json');camp=read('analysis-report/CAMPAIGN-23-METRICS.json');replay=read('implementation-report/phase-3b6-replay.json')
    with gzip.open(ROOT/'tests/fixtures/commercial3b6/campaign23.json.gz','rt') as f:x=json.load(f)
    browsers=[]
    for r in x['commercial_revisions']:
        if r['id'] not in (912,918):continue
        b=r['body']['browser'];fail=[d for d in b['diagnostics'] if d.get('error')];resources={}
        for d in fail:
            if d['phase']!='resource':continue
            u=urlsplit(d['url']);url=urlunsplit((u.scheme,u.netloc,u.path,'',''))
            resources.setdefault(url,{'url':url,'resource_type':d.get('resource_type'),'role':d.get('role'),'error':d.get('error'),'code':d.get('code'),'occurrences':0})['occurrences']+=1
        browsers.append({'revision':r['id'],'company':r['body']['company'],'historical_only':True,
            'resource_requests':b['resource_requests'],'elapsed_ms':b['elapsed_ms'],'audit_state':b['audit_state'],
            'failure_codes':dict(Counter(d.get('code') for d in fail)),
            'failed_resources':list(resources.values()),'partial_measurements':b['pages'],
            'confirmed_findings':b['findings'],'resources_closed':b['resources_closed']})
    paths=['PHASE-3B.5-REPORT.md','PHASE-3B.5-METRICS.json','analysis-report/CAMPAIGN-23-REPORT.md','analysis-report/CAMPAIGN-23-METRICS.json']
    from scripts.analysis_archive import read_text
    artifacts={p:read_text(p).encode('utf-8') for p in paths}
    return {'phase':'3B.6','source_artifacts':{p:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for p,data in artifacts.items()},
        'historical':{'campaign':23,'baseline_previous_phase_tests':prior['tests'],'counts':camp['counts'],'ai_attempts':replay['ai_contract_mapping'],'browser_diagnostics':browsers},
        'offline_replay':replay,'tests':{'full_suite':test_log('implementation-report/phase-3b6-tests.txt'),'contracts_and_planner':test_log('implementation-report/phase-3b6-contract-tests.txt'),'browser':test_log('implementation-report/phase-3b6-browser-tests.txt'),'ui':read('implementation-report/phase-3b6-ux.json')},
        'integrity':read('implementation-report/phase-3b6-integrity.json'),
        'demonstrated':{'previously_admitted_metadata_paths_excluded':replay['recalculated']['prior_admissions_now_excluded'],'download_deadline_excludes_mandatory_policy_wait':'real local Chromium, injected serialized 300ms policy with 200ms transfer cap','partial_audits_qualify':False,'shadow_authority':'deterministic_only'},
        'unmeasured':['External browser completion rate','New query yield','Remote AI valid response rate with new contracts','Real commercial conversion'],
        'operational':{'campaigns_started':0,'external_calls':0,'openai_calls':0,'serper_calls':0,'email_sent':0,'production_database_writes':0,'budgets_changed':False,'model_changed':False,'crm_changed':False,'commit_or_push':False},
        'issues':[{'area':'Discovery','state':'FIXED_ON_SAVED_CASES','limit':'Not universal publisher/owner segmentation; exploration retained.'},{'area':'Browser','state':'PARTIALLY_FIXED','limit':'Policy wait no longer charged as transfer. Robots denials and real transport errors persist; sites not revisited.'},{'area':'AI','state':'CONTRACTS_SEPARATED_OFFLINE','limit':'Invalid raw replies unavailable; no claims of 9/9 recovery.'},{'area':'Commercial quality','state':'NOT_MEASURED','limit':'No new qualified client from an offline replay.'}]}
if __name__=='__main__':
    metrics=build();(ROOT/'PHASE-3B.6-METRICS.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n');print(json.dumps(metrics['tests']['full_suite']))
