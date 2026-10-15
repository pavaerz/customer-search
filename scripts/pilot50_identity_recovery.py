"""Replay saved identity searches against original websites, in a private DB copy.

No Serper requests are made here. The saved two-query development probe is not
an independent quality benchmark. Missing source provenance is a hard failure.
"""
import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sales.db import Store,now,domain
from sales.company_research import acquisition_rank,company_verification
from sales.research_analysis import inspect_candidate
from sales.research_triage import triage


def query_records(value):
    if isinstance(value,dict):
        if value.get('query') and value.get('subject') and value.get('source_documents'):
            yield value
        for child in value.values():yield from query_records(child)
    elif isinstance(value,list):
        for child in value:yield from query_records(child)


def run():
    destination=ROOT/'data/identity-pilots'/now().replace(':','-')
    destination.mkdir(parents=True,mode=0o700)
    source=Store();path=destination/'pilot.sqlite3'
    with closing(sqlite3.connect(source.path)) as src,closing(sqlite3.connect(path)) as dst:
        with dst:
            src.backup(dst)
            dst.execute("UPDATE campaigns SET status='paused',worker_pid=NULL WHERE status IN ('running','waiting','stopping')")
    os.chmod(path,0o600);store=Store(path);store.init()
    inputs=ROOT/'data/pilot50-next'
    queries=list(query_records(json.loads((inputs/'resolved-directories.json').read_text())))
    alternatives=json.loads((inputs/'identity-alternatives.json').read_text())
    filters={'target':'b2b','regions':['Veneto'],'groups':['direct'],'projects':['website']}
    report={'started_at':now(),'split':'development','requests':0,'companies':[],
            'limits':['Previously failed identities, selected for development; not a precision sample.',
                      'Saved search results rank pages only; original pages establish identity.',
                      'No purchase, outreach or production CRM mutation.']}
    def save():
        (destination/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        (ROOT/'docs/pilot50-identity-recovery.json').write_text(json.dumps({
            'directory':str(destination.relative_to(ROOT)),
            'finished':report.get('finished_at'),'requests':0,
            'results':[{k:v for k,v in r.items() if k in ('subject','url','state','reason','company_ready','assessment_status','error','seconds')} for r in report['companies']]},ensure_ascii=False,indent=2))
    for alternative in alternatives:
        original=next((q for q in queries if q['subject']==alternative['name']),None)
        if original is None:raise ValueError('Missing original source for '+alternative['name'])
        items=sorted(alternative['results'],key=lambda item:acquisition_rank(item,'b2b',original['subject']),reverse=True)
        item=items[0]
        payload={**original,'url':item['url'],'strategy':'companies','company_stage':'identify','filters':filters}
        record={'subject':original['subject'],'url':item['url'],'original_query':original['query'],'alternate_query':alternative['query']}
        report['companies'].append(record);started=time.monotonic()
        try:
            result=triage(store,payload,lambda:None)
            record.update(state=result['state'],reason=result['reason'],company_ready=bool(result.get('details',{}).get('company_ready')),triage=result)
            print(json.dumps({k:record[k] for k in ('subject','state','reason','company_ready')},ensure_ascii=False),flush=True);save()
            if record['company_ready']:
                verification=company_verification(payload,result)
                inspected=inspect_candidate(store,verification,lambda:None,lambda message:print(message,flush=True))
                record.update(assessment=inspected,assessment_status=inspected['assessment']['status'])
        except Exception as exc:record.update(error=str(exc)[:900])
        record['seconds']=round(time.monotonic()-started,2);save()
    report['finished_at']=now()
    report['summary']={'companies_examined':len(report['companies']),
                       'verified':sum(bool(r.get('company_ready')) for r in report['companies']),
                       'qualified':sum(r.get('assessment_status')=='qualified' for r in report['companies']),
                       'deep_checks':sum('assessment_status' in r for r in report['companies']),
                       'requests':0}
    save();print(json.dumps(report['summary']),flush=True)


if __name__=='__main__':run()
