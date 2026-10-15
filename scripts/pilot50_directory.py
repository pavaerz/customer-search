"""Controlled real directory-to-company pilot, separate CRM and explicit consumption.

Two subjects per source and two search results per subject are sample sizes,
not production limits. All paid queries use the actual account usage ledger.
"""
import json,sys,sqlite3,os,time
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,now,domain
from sales.source_catalog import DIRECTORIES
from sales.research_analysis import ResearchWeb,resolve_publisher,inspect_candidate
from sales.research_triage import triage
from sales.company_research import company_verification,acquisition_rank
from sales.serper_provider import search
from sales.providers import blocked
from sales.prospect_scope import acquisition_exclusion
from sales.research_strategies import NOISE
from sales.commercial_planner import hypothesis
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel

ROOT=Path(__file__).resolve().parents[1]

def run():
    destination=ROOT/'data'/'directory-pilots'/now().replace(':','-');destination.mkdir(parents=True,mode=0o700)
    real=Store();path=destination/'pilot.sqlite3'
    with closing(sqlite3.connect(real.path)) as src,closing(sqlite3.connect(path)) as dst:
        with dst:
            src.backup(dst);dst.execute("UPDATE campaigns SET status='paused',worker_pid=NULL WHERE status IN ('running','waiting','stopping')")
    os.chmod(path,0o600);store=Store(path);store.init();web=ResearchWeb(store)
    filters={'target':'b2b','regions':['Veneto'],'projects':['website'],'groups':['direct']}
    rs=ResearchStore(store);campaign=rs.create(filters);funnel=Funnel(rs)
    report={'started_at':now(),'split':'development','sources':[],'subjects':[],'queries':[],'companies':[],'assessments':[],'requests':0,'errors':[]}
    def save():
        (destination/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        (ROOT/'docs/pilot50-directory-latest.json').write_text(json.dumps({'directory':str(destination.relative_to(ROOT)),'requests':report['requests'],'sources':len(report['sources']),'companies':len(report['companies']),'finished':report.get('finished_at')},indent=2))
    def emit(data):print(json.dumps(data,ensure_ascii=False),flush=True);save()
    candidates=[]
    for region,profile,sector,url in DIRECTORIES:
        payload={'url':url,'directory':True,'publisher':True,'strategy':'companies','region':region,'filters':filters}
        try:
            page=web.get(url);resolved=resolve_publisher(store,page,payload,lambda:None)
            report['sources'].append({'url':url,'profiles':len(resolved['discovered']),'names':len(resolved.get('resolve_queries',[])),'excluded':resolved.get('excluded_names',[])})
            subjects=resolved['discovered'][:2] or resolved.get('resolve_queries',[])[:2]
            for subject in subjects:
                try:
                    result=resolve_publisher(store,web.get(subject['url']),subject,lambda:None) if subject.get('directory') else {'discovered':[],'resolve_queries':[subject]} if 'query' in subject else {'discovered':[subject]}
                    report['subjects'].append({'source':url,'subject':subject.get('directory_subject') or subject.get('subject'),'profile':subject.get('url'),'links':[x['url'] for x in result['discovered']],'queries':[q['query'] for q in result.get('resolve_queries',[])]})
                    candidates+=result['discovered']
                    for query in result.get('resolve_queries',[])[:1]:
                        answer,cached=search(real,query['query']);report['requests']+=not cached
                        report['queries'].append({'query':query['query'],'cached':cached,'results':answer['results']})
                        offered=0
                        for item in sorted(answer['results'],key=lambda item:acquisition_rank(item,'b2b',query.get('subject')),reverse=True):
                            url=item['url']
                            if blocked(url) or NOISE.search(url) or acquisition_exclusion(item,query):continue
                            candidates.append({**query,'url':url,'company_stage':'identify','hypothesis':hypothesis('companies',region),'research_intent':'company','filters':filters});offered+=1
                            if offered==2:break
                except Exception as exc:report['errors'].append({'url':subject.get('url'),'error':str(exc)[:600]})
        except Exception as exc:report['errors'].append({'url':url,'error':str(exc)[:600]})
        emit({'source':payload['url'],'candidates':len(candidates),'requests':report['requests']})
    identified=set();ready=[]
    for payload in candidates:
        if payload.get('subject') in identified:continue
        payload.update(company_stage='identify',strategy='companies',filters=filters)
        started=time.monotonic()
        try:
            result=triage(store,payload,lambda:None);details=result.get('details',{})
            funnel.transition(campaign,payload,result['state'],result['reason'],details)
            record={'url':payload['url'],'payload':payload,'subject':payload.get('subject'),'state':result['state'],'reason':result['reason'],'details':details,'seconds':round(time.monotonic()-started,2)}
            if details.get('company_ready'):
                identified.add(payload.get('subject'));ready.append((payload,result))
        except Exception as exc:record={'url':payload['url'],'state':'unverifiable','error':str(exc)[:600]}
        report['companies'].append(record);emit({k:v for k,v in record.items() if k not in ('details','payload')})
    # One actual complete investigation; never promote identity alone.
    for payload,result in ready[:1]:
        try:
            verification=company_verification(payload,result)
            inspected=inspect_candidate(store,verification,lambda:None,lambda message:print(message,flush=True))
            aid=rs.save(campaign['id'],campaign['generation'],None,inspected['identity'],inspected['documents'],inspected['assessment'])
            report['assessments'].append({'id':aid,**inspected})
        except Exception as exc:report['errors'].append({'url':payload['url'],'error':str(exc)[:600]})
        save()
    report['finished_at']=now();report['summary']={'sources':len(report['sources']),'subjects':len(report['subjects']),'requests':report['requests'],'pages_triaged':len(report['companies']),'verified_target_companies':len(ready),'deep_checks':len(report['assessments']),'qualified':sum(x['assessment']['status']=='qualified' for x in report['assessments']) if report['assessments'] else None}
    report['limits']=['Development sample selected by source order; not an independent precision estimate.','Identity is not evidence of commercial need.','Failed access remains unknown; no restrictions bypassed.']
    rs.stop(campaign['id']);rs.paused(campaign['id']);emit(report['summary'])

if __name__=='__main__':run()
