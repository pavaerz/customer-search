"""Offline pipeline pilot. Synthetic service doubles are NOT commercial results."""
import json,sys
from pathlib import Path
from collections import Counter
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_agent6_campaign32 import Campaign32Fix,provider,FROZEN,policy,TEXT,DATE
from sales.commercial.coordinator import run_campaign

def literal_provider(payload,cfg,check):
 response=provider(payload,cfg,check)
 sources={e['id']:e['text'] for e in payload.get('evidence',[])}
 for a in response['output'].get('analyses',[]):
  refs=([a['kind_ref']] if a['kind_ref'] else [])+[f['ref'] for f in a['facts']]
  for ref in refs:
   if 'start' not in ref:continue
   text=sources[ref['id']];start,end=ref['start'],ref['end'];quote=text[start:end]
   occurrence=text[:start].count(quote)
   ref.clear();ref.update(id=next(e['id'] for e in payload['evidence'] if e['text']==text),quote=quote,occurrence=occurrence)
 return response

def main():
 t=Campaign32Fix();t.setUp()
 try:
  def acquire(store,p,check):
   check();return [{'url':'https://'+p['commercial_engine'].lower()+'.example/careers','title':'Alfa Srl','content':TEXT}]
  def get(web,url):
   return {'url':url,'status':200,'checked_at':DATE,'html':'<title>Alfa Srl</title>'+''.join('<p>'+x+'</p>' for x in TEXT.splitlines())+'<p>Partita IVA: 12345678901</p><p>Sede legale: Via Roma 12, 35100 Padova (PD)</p><a href="mailto:info@alfa.example">info@alfa.example</a>'}
  with patch('sales.agent6.coordinator.acquire',side_effect=acquire),patch('sales.agent6.coordinator.CompanyWeb.get',get),patch('sales.agent6.ai.infer',side_effect=literal_provider):
   run_campaign(t.store,t.c,lambda:None,lambda m:None)
  with t.store.connect() as c:
   rows=[dict(r) for r in c.execute('select engine,status,attempt,body from commercial_ai_executions where campaign_id=?',(t.c['id'],))]
   states=dict(c.execute('select state,count(*) from agent6_records group by state').fetchall())
   checked=c.execute('pragma integrity_check').fetchone()[0]
  stages={f:dict(Counter(json.loads(r['body']).get('stage') for r in rows if r['engine']==f and r['attempt'])) for f in t.filters['commercial_engines']}
  assert all(s.get('plan')==1 and s.get('verify',0)>=1 for s in stages.values()),stages
  assert sum(r['attempt'] for r in rows)<=20
  result={'scope':'OFFLINE SYNTHETIC PILOT; no real leads generated','external_calls':0,'production_writes':0,'database_integrity':checked,'same_call_limits':{'campaign':20,'flow':8,'candidate':1,'usd':1},'stages':stages,'synthetic_states_do_not_count_as_real_opportunities':states,'real_campaign32_query_policy_replay':[{'query':q['query'],**policy.assess_query(q,'AZIENDE')} for q in FROZEN['plan']['queries']],'real_invalid_raw_outputs_available':False}
  Path('implementation-report/campaign32-fix-offline-pilot.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
 finally:t.tearDown()
if __name__=='__main__':main()
