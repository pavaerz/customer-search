"""Independent directory sample: real source -> named links -> original company pages.
Old award dates identify companies only. They cannot pass the timing qualification gate.
"""
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,now
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.research_analysis import ResearchWeb,resolve_publisher,inspect_candidate
from sales.research_triage import triage

def main(database='data/pilot41-directory/pilot.sqlite3'):
 store=Store(Path(database));store.init();store.configure({'ollama_model':'qwen2.5:7b'});rs=ResearchStore(store);f=Funnel(rs);campaign=rs.create({'regions':['Veneto']});cid=campaign['id']
 report={'started_at':now(),'source':'https://cnaveneto.it/cambiamenti-imprese-nord-est/','method':'Elenco nominativo pubblico con link espliciti. Fonte storica usata solo per identificare aziende; serve un bisogno attuale indipendente.','triage':[],'deep':[],'manual_review':[]}
 def check():
  if not rs.active(cid,campaign['generation']):raise InterruptedError()
 def save():
  report['metrics']=f.metrics(cid);report['campaign']=rs.campaign(cid)
  out=store.path.parent/'report.json';tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2));tmp.chmod(0o600);tmp.replace(out)
 try:
  page=ResearchWeb(store,check).get(report['source'])
  result=resolve_publisher(store,page,{'directory':True,'strategy':'startup','filters':campaign['filters']},check);report['linked_subjects']=len(result['discovered']);promising=[]
  for payload in result['discovered']:
   print('Triage '+payload['subject']+' '+payload['url'],flush=True);started=time.monotonic()
   try:r=triage(store,payload,check)
   except Exception as exc:r={'state':'unverifiable','reason':str(exc),'details':{}}
   r['details']['elapsed_seconds']=round(time.monotonic()-started,2);ident=f.transition(campaign,payload,r['state'],r['reason'],r['details']);report['triage'].append({'id':ident,'subject':payload['subject'],'url':payload['url'],'state':r['state'],'reason':r['reason'],'identity':r['details'].get('identity')})
   if r['state']=='promising':promising.append(payload)
   save()
  # Proportional pilot sample, not an engine cap. Full evidence gates are unchanged.
  for payload in promising[:3]:
   print('Deep '+payload['subject'],flush=True);started=time.monotonic();f.transition(campaign,payload,'verifying','Verifica approfondita nel pilota')
   try:
    r=inspect_candidate(store,payload,check,lambda s:print(s,flush=True))
    if r.get('publisher'):raise ValueError('Il dominio collegato è un editore, non una identità aziendale confermata')
    aid=rs.save(cid,campaign['generation'],None,r['identity'],r['documents'],r['assessment']);a=rs.opportunity(aid)['assessment'];f.transition(campaign,payload,a['status'],'; '.join(a['reasons']),{'identity':r['identity'],'deep_seconds':round(time.monotonic()-started,2)},aid);report['deep'].append({'url':payload['url'],'identity':r['identity'],'assessment':a})
   except Exception as exc:f.transition(campaign,payload,'unverifiable',str(exc));report['deep'].append({'url':payload['url'],'error':str(exc)})
   save()
 finally:rs.stop(cid);rs.paused(cid);report['finished_at']=now();save()
 print(json.dumps({k:rs.campaign(cid)[k] for k in ('discovered','promising','qualified')},ensure_ascii=False),flush=True)
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--database',default='data/pilot41-directory/pilot.sqlite3');main(parser.parse_args().database)
