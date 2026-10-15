"""Replay the first duplicate company reviews from the cycle pilot.

Frozen responses are reused. Newly selected official pages are read through the
normal protected reader. Actual local analysis; zero search-provider calls.
This is a regression replay, not an independent commercial evaluation.
"""
import json,sqlite3,sys,time
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,now,digest
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.research_analysis import ResearchWeb,inspect_candidate
from sales.research_triage import triage
from sales.company_queue import completed_review

ROOT=Path(__file__).resolve().parents[1]

def run():
    pointer=json.loads((ROOT/'docs/pilot50-cycle-diagnosis.json').read_text());source=ROOT/pointer['directory']
    pointer['campaign_id']=json.loads((source/'report.json').read_text())['campaign_id']
    dest=ROOT/'data/cycle50-replay'/now().replace(':','-');dest.mkdir(parents=True,mode=0o700)
    store=Store(dest/'replay.sqlite3');store.init();rs=ResearchStore(store)
    with closing(sqlite3.connect(source/'pilot.sqlite3')) as original,store.connect() as copy:
        original.row_factory=sqlite3.Row
        for row in original.execute('SELECT * FROM cache'):copy.execute('INSERT OR IGNORE INTO cache VALUES (?,?,?)',tuple(row))
        tasks=[dict(r) for r in original.execute("SELECT * FROM research_tasks WHERE campaign_id=? AND kind='verify' AND json_extract(payload,'$.company_key')='IT03249340278' ORDER BY id LIMIT 2",(pointer['campaign_id'],))]
    assert len(tasks)==2
    payloads=[json.loads(t['payload']) for t in tasks]
    campaign=rs.create(payloads[0]['filters']);funnel=Funnel(rs)
    for t,p in zip(tasks,payloads):funnel.offer(campaign['id'],'verify',t['strategy'],p,t['fingerprint'])
    funnel.fill(campaign);task=rs.claim(campaign['id'],campaign['generation'])
    with store.connect() as c:jobs=c.execute('SELECT count(*) FROM research_tasks WHERE campaign_id=?',(campaign['id'],)).fetchone()[0]
    assert jobs==1
    original_get=ResearchWeb.get;reads=[];pages=dest/'pages';pages.mkdir(mode=0o700)
    def get(web,url,refresh=False):
        frozen=source/'pages'/(digest(url)+'.json')
        if frozen.exists():result=json.loads(frozen.read_text());kind='frozen'
        else:result=original_get(web,url,refresh);kind='live protected read'
        (pages/(digest(url)+'.json')).write_text(json.dumps(result,ensure_ascii=False))
        reads.append({'url':url,'mode':kind,'status':result['status']});return result
    start=time.monotonic()
    with patch.object(ResearchWeb,'get',get):
        result=inspect_candidate(store,task['payload'],lambda:None,lambda message:print(message,flush=True))
    aid=rs.save(campaign['id'],campaign['generation'],task['id'],result['identity'],result['documents'],result['assessment'])
    with patch.object(ResearchWeb,'get',get):
        repeated=triage(store,payloads[1],lambda:None)
    reused=completed_review(rs,campaign,payloads[1],repeated)
    assert reused and reused['id']==aid,'An unchanged source must reuse this completed review'
    rs.task_done(task['id']);rs.stop(campaign['id']);rs.paused(campaign['id'])
    report={'checked_at':now(),'source':pointer['directory'],'split':'regression replay, not independent precision',
        'baseline_job_ids':[t['id'] for t in tasks],'before_review_jobs':len(tasks),'after_review_jobs':jobs,
        'source_urls_retained':[i['url'] for i in task['payload']['review_inputs']],
        'unchanged_page_reused_assessment':reused['id'],
        'queries':0,'reads':reads,'seconds':round(time.monotonic()-start,2),'assessment_id':aid,
        'identity':result['identity'],'assessment':result['assessment'],'document_urls':[d['url'] for d in result['documents']]}
    (dest/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (ROOT/'docs/regression50-company-queue.json').write_text(json.dumps({**{k:v for k,v in report.items() if k not in ('identity','assessment')},'directory':str(dest.relative_to(ROOT)),
        'company':result['identity']['name'],'status':result['assessment']['status'],'why':result['assessment']['why']},ensure_ascii=False,indent=2))
    print(json.dumps({'directory':str(dest.relative_to(ROOT)),'status':result['assessment']['status'],'before':len(tasks),'after':jobs,'reads':len(reads),'queries':0}),flush=True)

if __name__=='__main__':run()
