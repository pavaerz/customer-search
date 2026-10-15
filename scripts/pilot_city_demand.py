"""Read new company originals from two frozen city queries. No search/model calls.

Cohort: first 3 eligible, previously unread domains per query in application
visit order. All exclusions/errors are retained, no production campaign created.
"""
import json,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sales.db import Store,now,domain
from sales.direct_channels import visit_priority,linkedin_notice
from sales.discovery_relevance import preflight
from sales.providers import blocked
from sales.research_triage import triage
from sales.research_analysis import ResearchWeb,LocalResearcher

folder=ROOT/'data/benchmarks50';source=folder/'demand-city-evaluation.json'
# Freeze exclusion set from earlier read cohorts before inspecting new originals.
seen=set()
for filename in ('direct-demand-evaluation.json','direct-demand-evaluation2.json','direct-demand-unread-originals.json','direct-demand-development-replay.json'):
 for case in json.loads((folder/filename).read_text())['cases']:seen.add(domain(case['payload']['url']))
seen.add('web-station.it')
source_data=json.loads(source.read_text())
out={'checked_at':now(),'split':'new-originals evaluation; new city queries selected before results','selection':'First 3 eligible unread domains per query in app visit order','excluded_development_domains':sorted(seen),'api_requests':0,'search_requests_for_source':sum(not q['cached'] for q in source_data['queries']),'cases':[],'excluded':[]}
dest=folder/'city-demand-originals.json';original=ResearchWeb.get
for q in source_data['queries']:
 count=0
 for item in sorted(q['results'],key=lambda x:visit_priority(x)[0],reverse=True):
  host=domain(item['url'])
  if host in seen:continue
  payload={**item,'search_snippet':item.get('content',''),'query':q['query'],'strategy':'partner','direct_channels':True,'acquisition_reason':visit_priority(item)[1],
           'filters':{'regions':['Veneto','Lombardia','Piemonte','Toscana'],'groups':['direct','agencies'],'target':'b2b','projects':['website']},'hypothesis':{'required_evidence':'Richiesta freelance web sul sito aziendale'}}
  reason='Accesso automatico escluso' if blocked(item['url']) and not linkedin_notice(item) else preflight(payload,payload)
  if reason:out['excluded'].append({'url':item['url'],'reason':reason});continue
  if count>=3:break
  count+=1;seen.add(host);case={'payload':payload,'captures':[]};start=time.monotonic()
  def capture(web,url,refresh=False):
   result=original(web,url,refresh);case['captures'].append(result);return result
  with patch.object(ResearchWeb,'get',capture),patch.object(LocalResearcher,'call',side_effect=AssertionError('No model in triage')):
   try:case['live_result']=triage(Store(),payload,lambda:None)
   except Exception as exc:case['error']=str(exc)
  case['seconds']=round(time.monotonic()-start,2);out['cases'].append(case);dest.write_text(json.dumps(out,ensure_ascii=False,indent=2))
  r=case.get('live_result',{});d=r.get('details',{});i=d.get('identity',{})
  print(json.dumps({'url':item['url'],'state':r.get('state'),'reason':r.get('reason'),'name':i.get('name'),'region':i.get('region'),'contacts':i.get('contacts'),'collaboration':d.get('collaboration'),'error':case.get('error'),'seconds':case['seconds']},ensure_ascii=False),flush=True)
