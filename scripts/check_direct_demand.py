"""Frozen before/after triage benchmark; --live explicitly acquires a small holdout.

Never starts campaigns, calls a model, sends messages or writes commercial rows.
The development domains are excluded from the evaluation cohort in advance.
"""
import argparse,hashlib,json,os,subprocess,sys,tempfile,time,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sales.db import Store,now,domain
from sales.direct_channels import route_exclusion
from sales.discovery_relevance import preflight
from sales.discovery_planner import searchable_query
from sales.serper_provider import search
from sales.providers import blocked
from sales.direct_channels import linkedin_notice
from sales.research_triage import triage
from sales.research_analysis import ResearchWeb,LocalResearcher

DATA=ROOT/'data/benchmarks50/direct-demand-evaluation2.json'
BASELINE=ROOT/'data/backups/20261014T161155549946Z/project.zip'
DEVELOPMENT={'adviva.it','jampaa.it','web-station.it','fusionwork.it','digitalia.srl','shakersworks.com','lezio.it','serverplan.com','consulmarc.it','internetimage.it','inmatch.com'}
QUERIES=['"frontend" "freelance" "lavora con noi"','inurl:lavora-con-noi "sviluppatore" "freelance"']
FILTERS={'regions':['Veneto','Lombardia','Piemonte','Toscana'],'groups':['direct','agencies'],'target':'b2b','projects':['website']}

def live():
    out={'split':'evaluation','selected_before_acquisition':True,'checked_at':now(),'excluded_development_domains':sorted(DEVELOPMENT),'queries':[],'cases':[],'api_requests':0}
    seen=set();original=ResearchWeb.get
    def save():DATA.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    for query in QUERIES:
        q=searchable_query({'query':query,'strategy':'partner'})
        result,cached=search(Store(),q);out['api_requests']+=int(not cached)
        out['queries'].append({'query':q,'cached':cached,'results':result['results']});save()
        # Fixed sample rule: first three distinct permissible domains per query,
        # excluding development domains. Restrictions/errors stay in the report.
        n=0
        for item in result['results']:
            host=domain(item['url'])
            if host in DEVELOPMENT or host in seen:continue
            payload={**item,'search_snippet':item.get('content',''),'query':q,'strategy':'partner','direct_channels':True,'filters':FILTERS,'hypothesis':{'required_evidence':'Richiesta di collaborazione web nel sito aziendale'}}
            reason=('Fonte esclusa dalla discovery automatica' if blocked(item['url']) and not linkedin_notice(payload) else preflight(payload,payload))
            if reason:
                out.setdefault('prefetch_rejected',[]).append({'url':item['url'],'reason':reason});continue
            if n>=3:break
            n+=1;seen.add(host);case={'payload':payload,'captures':[]};start=time.monotonic()
            def capture(web,url,refresh=False):
                page=original(web,url,refresh);case['captures'].append(page);return page
            with patch.object(ResearchWeb,'get',capture),patch.object(LocalResearcher,'call',side_effect=AssertionError('No inference in screening')):
                try:case['live_result']=triage(Store(),payload,lambda:None)
                except Exception as exc:case['error']=str(exc)
            case['seconds']=round(time.monotonic()-start,2);out['cases'].append(case);save()
            r=case.get('live_result',{});d=r.get('details',{});i=d.get('identity',{})
            print(json.dumps({'url':item['url'],'state':r.get('state'),'reason':r.get('reason'),'company':i.get('name'),'region':i.get('region'),'contacts':i.get('contacts'),'collaboration':d.get('collaboration'),'error':case.get('error'),'seconds':case['seconds']},ensure_ascii=False),flush=True)
    return out

REPLAY=r'''
import json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
from sales.db import Store
from sales.research_triage import triage
from sales.research_analysis import ResearchWeb,LocalResearcher
sample=json.load(open(sys.argv[2]));rows=[]
with tempfile.TemporaryDirectory() as directory:
 store=Store(Path(directory)/'db');store.init()
 for case in sample['cases']:
  payload=dict(case['payload'])
  if len(sys.argv)>3 and sys.argv[3]:payload['filters']={**payload.get('filters',{}),'projects':[sys.argv[3]]}
  pages={p['url']:p for p in case['captures']}
  def get(web,url,refresh=False):
   if url not in pages:raise ValueError('Original page absent from frozen capture: '+url)
   return pages[url]
  with patch.object(ResearchWeb,'get',get),patch.object(LocalResearcher,'call',side_effect=AssertionError('No model in replay')):
   try:
    r=triage(store,payload,lambda:None);d=r.get('details',{});i=d.get('identity',{})
    rows.append({'url':case['payload']['url'],'state':r['state'],'reason':r['reason'],'identity':i,'collaboration':d.get('collaboration'),'company_ready':d.get('company_ready',False)})
   except Exception as e:rows.append({'url':case['payload']['url'],'error':str(e)})
print(json.dumps(rows))
'''

def replay(sample,report_path=None,project=None):
    with tempfile.TemporaryDirectory() as directory:
        with zipfile.ZipFile(BASELINE) as z:
            for name in z.namelist():
                if name.startswith('sales/') and name.endswith('.py'):
                    path=Path(directory)/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name))
        results={}
        for name,root in [('before',directory),('after',str(ROOT))]:
            p=subprocess.run([sys.executable,'-c',REPLAY,str(root),str(DATA),project or ''],cwd=directory,check=True,capture_output=True,text=True)
            results[name]=json.loads(p.stdout)
    report={'checked_at':now(),'split':sample['split'],'sample_size':len(sample['cases']),'sample_sha256':hashlib.sha256(DATA.read_bytes()).hexdigest(),
      'baseline':str(BASELINE.relative_to(ROOT)),'baseline_sha256':hashlib.sha256(BASELINE.read_bytes()).hexdigest(),'api_requests':sample['api_requests'],'project_override':project,
      'scope':'Original-page triage and contact routes, not full project qualification or sales conversion. Same frozen pages for both versions.',
      'selection':sample.get('selection','Selection rule not recorded in this capture; consult cohort metadata. Do not assume a random or representative sample.'),
      'versions':results,'metrics':{}}
    for name,rows in results.items():
        report['metrics'][name]={'examined':len(rows),'identified':sum(r.get('identity',{}).get('identity_status')=='verified' for r in rows),'promising':sum(r.get('state')=='promising' for r in rows),'documented_collaborations_with_contact':sum(bool(r.get('collaboration')) for r in rows),'unverifiable':sum(bool(r.get('error')) or r.get('state')=='unverifiable' for r in rows),'qualified':0,'model_calls':0,'replay_api_requests':0,'precision_at_10':None,'precision_at_20':None}
    report['limits']=['Small cohort, not proof of commercial efficacy.','No purchased budget inferred; original invitation can require availability confirmation.','Precision needs manual labels and adequate denominators; no score fabricated.','Baseline can request uncaptured pages; these remain explicit errors, never commercial rejections.']
    (report_path or ROOT/'docs/benchmark50-direct-demand.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report['metrics'],ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--sample',type=Path);parser.add_argument('--report',type=Path);parser.add_argument('--project',choices=['website','ecommerce','webapp']);args=parser.parse_args()
    if args.sample:DATA=args.sample.resolve()
    sample=live() if args.live else json.loads(DATA.read_text());replay(sample,args.report,args.project)
