"""Controlled end-to-end run of the actual worker in an isolated CRM copy.

Sample boundaries belong to this pilot, not the application. Search calls use
the real Serper ledger and cache. All business state, evidence and model cache
stay in the copy. No outgoing contact or other provider is invoked.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import threading
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,now,digest
from sales.research_store import ResearchStore
from sales.research_analysis import ResearchWeb
from sales.serper_provider import search as serper_search,CreditLimit
from sales.research_worker import run as worker

ROOT=Path(__file__).resolve().parents[1]

class PilotRequests:
    """Count reservations even when transport fails; cache hits reserve nothing."""
    def __init__(self,store,report,budget,save,search=serper_search):
        self.store=store;self.report=report;self.budget=budget;self.save=save;self.search=search

    def __call__(self,_store,query,page=1,period='',check=lambda:None):
        reserve=self.store.reserve
        def counted(provider='tavily'):
            if provider=='serper' and self.budget is not None and self.report['requests']>=self.budget:
                raise CreditLimit('Campione pilota: budget volontario di richieste raggiunto; campagna di prova conservata.')
            reserve(provider)
            if provider=='serper':self.report['requests']+=1
        entry={'query':query,'page':page,'period':period,'cached':None}
        before=self.report['requests']
        try:
            with patch.object(self.store,'reserve',counted):
                result,cached=self.search(self.store,query,page,period,check)
            entry.update(cached=cached,results=result['results'])
            return result,cached
        except Exception as exc:
            entry['error']=str(exc)[:900];raise
        finally:
            entry['requests']=self.report['requests']-before
            self.report['queries'].append(entry);self.save()

def run(request_budget=None,task_sample=120,company_sample=6,resume=None):
    real=Store()
    if resume:
        dest=Path(resume).resolve();path=dest/'pilot.sqlite3'
        if not path.exists():raise ValueError('Database del pilota non trovato')
        report=json.loads((dest/'report.json').read_text())
        store=Store(path);rs=ResearchStore(store)
        campaign=rs.resume(report['campaign_id'])
        report.setdefault('resumptions',[]).append({'at':now(),'previous_finish':report.pop('finished_at',None),'previous_plan':report['sample_plan']})
        report.pop('stop_reason',None)
    else:
        dest=ROOT/'data/cycle50'/now().replace(':','-');dest.mkdir(parents=True,mode=0o700)
        path=dest/'pilot.sqlite3'
        with closing(sqlite3.connect(real.path)) as src,closing(sqlite3.connect(path)) as dst:
            src.backup(dst)
            dst.execute("UPDATE campaigns SET status='paused',worker_pid=NULL WHERE status IN ('running','waiting','stopping')");dst.commit()
        os.chmod(path,0o600)
        store=Store(path);store.init();rs=ResearchStore(store)
        campaign=rs.create({'target':'b2b','regions':['Veneto','Lombardia','Piemonte','Toscana'],'projects':['website'],'groups':['direct']})
        report={'started_at':now(),'campaign_id':campaign['id'],'directory':str(dest.relative_to(ROOT)),
            'split':'prospective operational sample; not independent commercial precision','requests':0,'queries':[],'reads':[]}
    cid=campaign['id']
    report['sample_plan']={'request_budget':request_budget,'completed_tasks':task_sample,'completed_company_checks':company_sample}
    # Lazy imports can otherwise mix versions if product code is edited while
    # a long pilot is running. Record and verify the complete Python baseline.
    code_paths=sorted(list((ROOT/'sales').glob('*.py'))+list(ROOT.glob('*.py')))
    report['code_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in code_paths}
    pages=dest/'pages';pages.mkdir(mode=0o700,exist_ok=True);lock=threading.Lock()
    original_get=ResearchWeb.get;original_claim=ResearchStore.claim;original_progress=ResearchStore.progress

    def save():
        with store.connect() as c:
            report['tasks']={r[0]:r[1] for r in c.execute('SELECT state,count(*) FROM research_tasks WHERE campaign_id=? GROUP BY state',(cid,))}
            report['assessments']=[dict(r) for r in c.execute('SELECT a.id,a.status,a.project,e.name,e.website,e.identity_status FROM research_assessments a JOIN research_entities e ON e.id=a.entity_id WHERE a.campaign_id=?',(cid,))]
            report['candidate_states']={r[0]:r[1] for r in c.execute('SELECT state,count(*) FROM discovery_candidates WHERE campaign_id=? GROUP BY state',(cid,))}
        with lock:
            temp=dest/'report.tmp';temp.write_text(json.dumps(report,ensure_ascii=False,indent=2));temp.replace(dest/'report.json')
        (ROOT/'docs/pilot50-cycle-latest.json').write_text(json.dumps({'directory':str(dest.relative_to(ROOT)),'campaign_id':cid,'requests':report['requests'],'finished_at':report.get('finished_at'),'tasks':report['tasks']},indent=2))

    paid=PilotRequests(real,report,request_budget,save)

    def capture(web,url,refresh=False):
        result=original_get(web,url,refresh)
        with lock:
            name=digest(url)+'.json';(pages/name).write_text(json.dumps(result,ensure_ascii=False))
            report['reads'].append({'url':url,'status':result['status'],'capture':name})
        return result

    def claim(owner,ident,generation):
        if ident==cid:
            with store.connect() as c:
                completed=c.execute("SELECT count(*) FROM research_tasks WHERE campaign_id=? AND state IN ('done','failed')",(cid,)).fetchone()[0]
                reviewed=c.execute("SELECT count(DISTINCT a.entity_id) FROM research_assessments a JOIN research_entities e ON e.id=a.entity_id WHERE a.campaign_id=? AND e.identity_status='verified'",(cid,)).fetchone()[0]
            if completed>=task_sample or reviewed>=company_sample:
                report['stop_reason']='Declared sample boundary reached between tasks'
                owner.stop(cid);raise InterruptedError('Campione completato')
        return original_claim(owner,ident,generation)

    def progress(owner,ident,generation,message,*args,**kwargs):
        result=original_progress(owner,ident,generation,message,*args,**kwargs)
        report['activity']=message;save();print(message,flush=True);return result

    print(str(dest),flush=True);save()
    try:
        with patch('sales.serper_provider.search',paid),patch.object(ResearchWeb,'get',capture),patch.object(ResearchStore,'claim',claim),patch.object(ResearchStore,'progress',progress):
            worker(path,cid,campaign['generation'])
    finally:
        current=rs.campaign(cid)
        if current['status'] in ('running','waiting','stopping'):
            rs.stop(cid);rs.paused(cid)
        report['code_changed_during_run']=[name for name,expected in report['code_sha256'].items()
            if not (ROOT/name).exists() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected]
        report['finished_at']=now();report['campaign_status']=rs.campaign(cid)['status'];save()
        print(json.dumps({'finished':True,'requests':report['requests'],'tasks':report['tasks'],'assessments':report['assessments']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--request-budget',type=int,default=None);parser.add_argument('--task-sample',type=int,default=120);parser.add_argument('--company-sample',type=int,default=6);parser.add_argument('--resume',type=Path)
    args=parser.parse_args()
    if min(args.task_sample,args.company_sample)<1 or (args.request_budget is not None and args.request_budget<1):parser.error('Sample bounds must be positive')
    run(args.request_budget,args.task_sample,args.company_sample,args.resume)
