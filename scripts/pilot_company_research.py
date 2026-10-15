"""Small real company-first diagnostic; isolated CRM copy, SearXNG only."""
import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store, now, domain
from sales.research_store import ResearchStore
from sales.company_research import company_queries, research_tasks, verification_priority, company_verification
from sales.research_discovery import search
from sales.discovery_planner import Planner
from sales.research_triage import triage
from sales.research_analysis import inspect_candidate


def run(maximum=12, deep=1, offset=0, output="docs/company-first-pilot.json", exclude_report=None):
    root=Path(__file__).resolve().parents[1]
    destination=root/'data'/'company-pilots'/now().replace(':','-')
    destination.mkdir(parents=True,mode=0o700)
    path=destination/'pilot.sqlite3'
    # Preserve suppressions and preferences; no commercial mutation of the real DB.
    with sqlite3.connect(root/'data'/'sales.sqlite3') as original, sqlite3.connect(path) as copy:
        original.backup(copy)
        copy.execute("UPDATE campaigns SET status='paused',worker_pid=NULL WHERE status IN ('running','waiting','stopping')")
    os.chmod(path,0o600)
    store=Store(path);store.init();rs=ResearchStore(store)
    campaign=rs.create({'regions':['Veneto'],'projects':['website'],'groups':['direct'],'target':'b2b'})
    report={'started_at':now(),'scope':'Piccolo campione diagnostico B2B Veneto. Identità/attività non equivalgono a opportunità. Nessun invio o nuovo contatto nel CRM reale.',
            'provider':'SearXNG','query_offset':offset,'excluded_report':exclude_report,'paid_requests':0,'queries':[],'companies':[],'investigations':[],'assessments':[], 'limits':[]}
    started=time.monotonic()
    def save():
        (destination/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    def query(q,strategy='companies',context=None):
        payload={**(context or {}),'query':q,'page':1,'period':'','region':'Veneto'}
        payload['query_key']=Planner(rs).offer_query(campaign,strategy,payload)
        try:
            result=search(rs,campaign,{'strategy':strategy,'payload':payload},lambda:None)
            report['queries'].append({'query':q,**result})
        except Exception as exc:
            report['queries'].append({'query':q,'error':str(exc)[:600]})
        save()
    for q in list(company_queries('Veneto'))[offset:offset+3]:query(q)
    with store.connect() as c:
        jobs=[json.loads(r[0]) for r in c.execute("SELECT payload FROM discovery_frontier WHERE campaign_id=? AND kind='candidate' ORDER BY id",(campaign['id'],))]
    # Round-robin source queries; not the first results of only one query.
    pending={};selected=[]
    for p in jobs:pending.setdefault(p.get('query_key') or p.get('source_url'),[]).append(p)
    hosts=set()
    if exclude_report:
        hosts={domain(x['url']) for x in json.loads(Path(exclude_report).read_text())['companies']}
    while pending and len(selected)<maximum:
        for key in list(pending):
            p=pending[key].pop(0)
            if not pending[key]:del pending[key]
            if domain(p['url']) not in hosts:
                hosts.add(domain(p['url']));selected.append(p)
            if len(selected)>=maximum:break
    ready=[]
    for payload in selected:
        try:
            result=triage(store,payload,lambda:None);d=result.get('details',{});identity=d.get('identity',{})
            record={'url':payload['url'],'state':result['state'],'reason':result['reason'],'company_ready':bool(d.get('company_ready')),
                    'identity':{k:identity.get(k) for k in ('name','website','legal_id','region','identity_status')},
                    'target_quote':d.get('target_quote'),'limits':d.get('limits',[]),'pages':[x['url'] for x in d.get('company_documents',[])]}
            if d.get('company_ready'):ready.append((payload,result))
        except Exception as exc:record={'url':payload['url'],'state':'unverifiable','reason':str(exc)[:600]}
        report['companies'].append(record);save()
        print(json.dumps(record,ensure_ascii=False),flush=True)
    shortlist=[]
    for payload,result in ready[:2]:
        candidates,queries=research_tasks(payload,result)
        q=queries[0];query(q['query'],'change',q)
        with store.connect() as c:
            candidates += [json.loads(r[0]) for r in c.execute("SELECT payload FROM discovery_frontier WHERE campaign_id=? AND kind='candidate' AND json_extract(payload,'$.company_host')=?",(campaign['id'],domain(result['details']['identity']['website'])))]
        seen=set()
        for child in candidates[:6]:
            if child['url'] in seen:continue
            seen.add(child['url'])
            try:
                r=triage(store,child,lambda:None)
                report['investigations'].append({'url':child['url'],'state':r['state'],'reason':r['reason'],'excerpts':r.get('details',{}).get('excerpts',[])})
                if r['state']=='promising':shortlist.append((child,r))
            except Exception as exc:report['investigations'].append({'url':child['url'],'state':'unverifiable','reason':str(exc)[:600]})
            save()
    # Same deterministic route as production: companies need no explicit ad to get reviewed.
    shortlist.extend((company_verification(p,r),r) for p,r in ready if company_verification(p,r))
    shortlist.sort(key=lambda x:verification_priority(x[1]),reverse=True)
    evaluated=set()
    for child,r in shortlist:
        if len(evaluated)>=deep:break
        if domain(child['url']) in evaluated:continue
        evaluated.add(domain(child['url']))
        try:
            result=inspect_candidate(store,child,lambda:None,lambda message:print(message,flush=True))
            report['assessments'].append({'url':child['url'],'identity':result.get('identity',{}),'assessment':result.get('assessment'), 'publisher':result.get('publisher',False)})
        except Exception as exc:report['assessments'].append({'url':child['url'],'error':str(exc)[:600]})
        save()
    report['finished_at']=now();report['seconds']=round(time.monotonic()-started,1)
    report['summary']={'pages_sampled':len(selected),'businesses_identified':len(ready),'deep_checks':len(report['assessments']),
                       'qualified':sum((x.get('assessment') or {}).get('status')=='qualified' for x in report['assessments']) if report['assessments'] else None}
    report['limits'].append('Campione piccolo, settori e stadi diversi dai confronti Serper precedenti: nessuna comparazione di precisione o efficacia commerciale. Non misura risposte o clienti.')
    rs.stop(campaign['id']);rs.paused(campaign['id']);save()
    (root/output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report['summary']),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--companies',type=int,default=12);p.add_argument('--deep-checks',type=int,default=1);p.add_argument('--query-offset',type=int,default=0);p.add_argument('--output',default='docs/company-first-pilot.json');p.add_argument('--exclude-report');args=p.parse_args()
    run(args.companies,args.deep_checks,args.query_offset,args.output,args.exclude_report)
