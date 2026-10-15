"""Reproducible proportional pilot. Separate DB; no outreach, no historical candidates.
Usage: .venv/bin/python scripts/pilot41.py [--phase discovery|qualify] [--database PATH]
Discovery: one query per strategy, original-page triage of up to 3 new URLs per strategy,
plus independent public sources. These are pilot sample sizes, not engine limits.
Qualification: up to 3 promising company pages + 1 publisher from the saved sample.
"""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,now,digest
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.research_strategies import TEMPLATES
from sales.research_discovery import search,inspect_source
from sales.research_triage import triage
from sales.research_analysis import inspect_candidate

def run(args):
 store=Store(Path(args.database));store.init();store.configure({'ollama_model':'qwen2.5:7b'});rs=ResearchStore(store);f=Funnel(rs);campaign=rs.campaign()
 if not campaign:campaign=rs.create({'regions':['Veneto']})
 elif not campaign['running']:campaign=rs.resume(campaign['id'])
 cid=campaign['id'];report={'started_at':now(),'phase':args.phase,'database':str(store.path),'cohort':'New discovery 4.1; no CRM seeding','queries':[],'sources':[],'reviews':[]}
 def check():
  if not rs.active(cid,campaign['generation']):raise InterruptedError()
 def log(message):print(message,flush=True)
 def save():
  report['metrics']=f.metrics(cid);report['campaign']=rs.campaign(cid)
  out=store.path.parent/('pilot-'+args.phase+'.json');temporary=out.with_suffix('.tmp');temporary.write_text(json.dumps(report,indent=2,ensure_ascii=False));temporary.chmod(0o600);temporary.replace(out)
 try:
  if args.phase=='discovery':
   for strategy,templates in ([] if args.sources_only else TEMPLATES.items()):
    query=templates[0].format(area='Veneto',sector='produzione alimentare');task={'strategy':strategy,'payload':{'query':query,'page':1,'period':'year','region':'Veneto'}};entry={'strategy':strategy,'query':query};log(query)
    try:search(rs,campaign,task,check);entry['status']='completed'
    except Exception as exc:entry.update(status='unavailable',reason=str(exc))
    report['queries'].append(entry);save()
   for url,kind in [('https://venetoup.com/','html'),('https://cnaveneto.it/startup/','html'),('https://venetoup.com/feed/','rss'),('https://venetosviluppo.it/index.php/news','html'),('https://www.confindustriavenest.it/stampa-e-media/comunicati-stampa','html')]:
    log('Source '+url);entry={'url':url}
    try:inspect_source(rs,campaign,{'payload':{'url':url,'kind':kind,'depth':0}},check);entry['status']='available'
    except Exception as exc:entry.update(status='unavailable',reason=str(exc))
    report['sources'].append(entry);save()
   with store.connect() as c:nested=[json.loads(r[0]) for r in c.execute("SELECT payload FROM discovery_frontier WHERE campaign_id=? AND kind='source' ORDER BY id LIMIT 4",(cid,))]
   for payload in nested:
    entry={'url':payload['url'],'kind':payload['kind']};log('Declared source '+payload['url'])
    try:inspect_source(rs,campaign,{'payload':payload},check);entry['status']='available'
    except Exception as exc:entry.update(status='unavailable',reason=str(exc))
    report['sources'].append(entry);save()
   with store.connect() as c:rows=[dict(r) for r in c.execute("SELECT * FROM discovery_frontier WHERE campaign_id=? AND kind='candidate' ORDER BY id",(cid,))]
   per_strategy={};seen=set()
   for row in rows:
    strategy=row['strategy'];payload=json.loads(row['payload'])
    if per_strategy.get(strategy,0)>=3 or payload['url'] in seen:continue
    per_strategy[strategy]=per_strategy.get(strategy,0)+1;seen.add(payload['url']);started=time.monotonic();log('Triage '+payload['url'])
    try:result=triage(store,payload,check)
    except Exception as exc:result={'state':'unverifiable','reason':str(exc),'details':{}}
    result['details']['elapsed_seconds']=round(time.monotonic()-started,2);ident=f.transition(campaign,payload,result['state'],result['reason'],result['details']);report['reviews'].append({'id':ident,'url':payload['url'],'strategy':strategy,'state':result['state'],'reason':result['reason']});save()
  else:
   rows=[r for r in f.listing({'campaign':cid,'limit':100})['items'] if r['state']=='promising' or r['details'].get('resolve_subject')];selected=sorted(rows,key=lambda r:r['details'].get('publisher',False))[:4]
   for row in selected:
    payload={'url':row['url'],'strategy':row['strategy'],'filters':campaign['filters'],'publisher':row['details'].get('publisher',False),'directory':row['details'].get('directory',False)};log('Deep '+row['url']);started=time.monotonic();f.transition(campaign,payload,'verifying','Pilota: verifica approfondita')
    try:
     result=inspect_candidate(store,payload,check,log)
     if result.get('publisher'):
      f.transition(campaign,payload,'needs_review','Fonte editoriale: aziende collegate da verificare.',{'resolved_urls':[r['url'] for r in result['discovered']]})
      report['reviews'].append({'id':row['id'],'url':row['url'],'publisher':True,'discovered':result['discovered'],'queries':result.get('resolve_queries')})
     else:
      a=result['assessment'];aid=rs.save(cid,campaign['generation'],None,result['identity'],result['documents'],a);f.transition(campaign,payload,a['status'],'; '.join(a['reasons']),{'identity':result['identity'],'elapsed_seconds':round(time.monotonic()-started,2)},aid)
      report['reviews'].append({'id':row['id'],'url':row['url'],'assessment':a,'identity':result['identity']})
    except Exception as exc:
     f.transition(campaign,payload,'unverifiable',str(exc));report['reviews'].append({'id':row['id'],'url':row['url'],'error':str(exc)})
    save()
 finally:
  rs.stop(cid);rs.paused(cid);report['finished_at']=now();save()
 log(json.dumps({k:rs.campaign(cid)[k] for k in ('discovered','qualified','promising','rejected')},ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--sources-only',action='store_true');p.add_argument('--phase',choices=['discovery','qualify'],default='discovery');p.add_argument('--database',default='data/pilot41/pilot.sqlite3');run(p.parse_args())
