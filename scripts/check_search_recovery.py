"""Live free search checks on temporary data; does not qualify or contact leads."""
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,now
from sales.research_store import ResearchStore
from sales.research_discovery import search
from sales.discovery_control import measure,diagnostics,search_capabilities
from sales.research_analysis import ResearchWeb
from sales.extract import parse_page
import os

def run():
 with tempfile.TemporaryDirectory() as tmp:
  s=Store(Path(tmp)/'check.db');s.init();rs=ResearchStore(s);campaign=rs.create({'regions':['Veneto','Toscana']})
  report={'checked_at':now(),'capabilities':search_capabilities(s,os.environ['SEARXNG_URL']),'queries':[],'pages':[]}
  for q in ('nuova linea prodotti Veneto','nuovo showroom Padova','ordini rivenditori Toscana'):
   task={'id':None,'kind':'search','strategy':'change','payload':{'query':q,'page':1,'period':'','region':'Veneto'}}
   try:
    with measure(rs,campaign,task):out=search(rs,campaign,task,lambda:None)
    report['queries'].append({'query':q,'urls':len(out['urls']),'sample':out['urls'][:3]})
   except Exception as e:report['queries'].append({'query':q,'error':str(e)})
  candidates=[u for q in report['queries'] for u in q.get('sample',[])][:2]
  for url in candidates:
   try:
    p=ResearchWeb(s).get(url);d=parse_page(p);report['pages'].append({'url':url,'status':p['status'],'title':d['title'][:200]})
   except Exception as e:report['pages'].append({'url':url,'error':str(e)})
  report['providers']=diagnostics(rs,campaign['id'])['providers']
  Path('docs/search-recovery-pilot.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':run()
