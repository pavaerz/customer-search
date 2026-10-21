"""Fully offline end-to-end recovery pilot and saved Campaign 34 replay."""
import copy,json,sys,socket
from pathlib import Path
from collections import Counter
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import test_agent6_recovery341 as regression
import test_agent6_campaign32 as support
import test_agent6 as original
from sales.agent6 import schema,memory
from sales.commercial.coordinator import run_campaign


def main():
 t=support.Campaign32Fix();t.setUp();reads=[];searches=[]
 try:
  items=[{'url':v['url'],'title':v['title'],'content':v['snippet']} for domain in ('mateagency.it','e89.it') for v in regression.SAVED['url_audit'] if domain in v['url']]
  items.append({'url':'https://alfa.example/careers','title':'Alfa Srl','content':original.TEXT})
  def search(store,p,check):check();searches.append(p['query']);return copy.deepcopy(items)
  def page(web,url):
   reads.append(url)
   if url!='https://alfa.example/careers':raise ValueError('HTTP 404') # controlled failure, NOT real E89 status
   return {'url':url,'status':200,'checked_at':original.DATE,'html':(Path(__file__).resolve().parents[1]/'tests/fixtures/agent6/campaign34/original-synthetic.html').read_text()}
  def infer(payload,cfg,check):
   check()
   if payload['task']==schema.PLAN:
    output={'decision':'stop','reason':'No other strategy in this controlled fixture','queries':[]}
    if payload['flow']=='AZIENDE':output={'decision':'search','reason':'Controlled recovery then request search','queries':[support.query('x'*301) if payload['round']==0 else support.query()]}
   elif payload['task']==schema.SCREEN:
    analyses=[]
    for rid in payload['result_ids']:
     e=next(e for e in payload['evidence'] if e['result_id']==rid)
     if 'mateagency.it' in e['url']:a=regression.analysis(e,'AGENCY_PARTNERSHIP','request','INTENTIONAL INVALID OFFLINE QUOTE')
     elif 'e89.it' in e['url']:a=regression.analysis(e,'AGENCY_PARTNERSHIP','request',e['text'])
     else:
      a=regression.analysis(e,'BUYER_DEMAND','request','We are looking for a freelance WordPress developer to build our complete website. Remote from Italy.')
      a['facts'].insert(0,{'field':'entity','ref':regression.ref(e,'Alfa Srl')});a['missing']=[]
     analyses.append(a)
    output={'analyses':analyses}
   else:
    # Same checked literal/offset contract, controlled data only.
    output=support.provider(payload,cfg,check)['output']
   return {'output':output,'usage':{'input_tokens':100,'output_tokens':100}}
  with patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')),patch('sales.agent6.ai.infer',side_effect=infer),patch('sales.agent6.coordinator.acquire',side_effect=search),patch('sales.agent6.coordinator.CompanyWeb.get',page):
   run_campaign(t.store,t.c,lambda:None,lambda _:None)
  with t.store.connect() as c:
   records=[json.loads(r[0]) for r in c.execute('select body from agent6_records')]
   calls=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('select * from commercial_ai_executions where attempt=1')]
   mem=dict(c.execute('select kind,count(*) from agent6_memory group by kind').fetchall());integrity=c.execute('pragma integrity_check').fetchone()[0]
  alpha=next(r for r in records if r['url']=='https://alfa.example/careers');e89=next(r for r in records if 'e89.it' in r['url']);mate=next(r for r in records if 'mateagency.it' in r['url'])
  assert alpha['state']=='VERIFIED' and alpha['identity_verified'] and alpha['original'] and alpha['documents']
  assert any('e89.it' in u for u in reads) and not any('mateagency.it' in u for u in reads)
  assert e89['state']=='UNVERIFIABLE' and mate['state']=='UNVERIFIABLE'
  assert len(searches)==1 and len(calls)<=20
  assert len([r for r in calls if r['engine']=='AZIENDE' and r['body']['stage'] in ('plan','replan')])==2
  assert any(r['body'].get('partial') for r in calls)
  fixture_bodies=regression.evaluate_real()
  p,o=regression.partial_fixture();validated,errors=schema.validate_response(o,p)
  result={'scope':'OFFLINE ONLY: saved snippets plus explicit synthetic original and controlled model responses','network_calls':0,'production_database_writes':0,'integrity':integrity,'limits_unchanged':{'campaign_ai_calls':20,'flow_ai_calls':8,'candidate_ai_calls':1,'max_estimated_usd':1},'mock_calls':len(calls),'stages':dict(Counter(r['body']['stage'] for r in calls)),'mock_searches':searches,'mock_page_attempts':reads,'saved_synthetic_document':'tests/fixtures/agent6/campaign34/original-synthetic.html','synthetic_result':{'url':alpha['url'],'state':alpha['state'],'identity_verified':alpha['identity_verified'],'original':alpha['original'],'reason':alpha['reason']},'real_e89_snippet_not_lost':True,'e89_read_failure':'SIMULATED HTTP404; not a live observation','mate_invalid_never_read':True,'memory_events':mem,'saved_34_replay':{'valid_siblings':len(validated['analyses']),'errors':errors,'semantic_cases':[{k:b.get(k) for k in ('url','state','kind','model_kind','entity_name','relationship','reason','semantic_issues','identity_issues','scope_observation')} for b in fixture_bodies.values()]},'real_opportunities_created':0}
  out=Path('implementation-report/customersearch-34.1-offline-pilot.json');out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps({'offline':True,'mock_calls':len(calls),'synthetic_cycle_completed':True,'real_opportunities':0,'integrity':integrity}))
 finally:t.tearDown()

if __name__=='__main__':main()
