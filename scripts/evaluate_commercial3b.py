"""Offline historical replay + scripted AI contract cases. No real inference."""
import copy,gzip,json,tempfile,time
from pathlib import Path
from sales.db import Store
from sales.research_store import ResearchStore
from sales.commercial.ai import analyze,summary,interpretation_documents
from sales.commercial.ai_schema import evidence_bundle,unknown_output
from sales.commercial.ai_evaluation import evaluate_cases
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/commercial3b'
def load(name):
 with gzip.open(FIXTURE/name,'rt') as f:return json.load(f)
def main():
 snapshot=load('campaign15.json.gz');sources=load('campaign15-pages.json.gz')['documents']
 replay=json.loads((ROOT/'implementation-report/phase-3b-replay.json').read_text());after={r['revision']:r['after'] for r in replay['decisions']}
 historical=sorted(snapshot['commercial_revisions'],key=lambda r:r['id']);shadow=[]
 with tempfile.TemporaryDirectory() as tmp:
  store=Store(Path(tmp)/'test.db');store.init();rs=ResearchStore(store)
  campaign=rs.create({'commercial_engines':['FREELANCE','AGENCIES','STARTUPS','WEBSITE_REBUILD'],'commercial':{'ai':{'enabled':True,'provider':'MOCK','max_calls_per_campaign':40,'max_calls_per_engine':20}}})
  for row in historical:
   original=copy.deepcopy(row['body']);result={**copy.deepcopy(original),**after[row['id']]}
   docs=[sources[k] for k in original.get('document_ids',[]) if k in sources]
   start=time.monotonic();advisory=analyze(store,campaign,result['engine'],row['opportunity_id'],result,docs)
   assert original==row['body'];assert result['state']==after[row['id']]['state']
   shadow.append({'revision':row['id'],'official_state':result['state'],'simulated':True,'ai_status':advisory['status'],'ai_intent':(advisory.get('output') or {}).get('commercial_intent'),'fallback':advisory['fallback'],'measured_local_seconds':time.monotonic()-start,'decision_changed_by_ai':False,'real_inference':False})
  usage=summary(store,campaign['id'])
 cases=[]
 names={757:'KForge',760:'DIEGO HELP',755:'Verdurazon',768:'NUMERAWAY',770:'Digisourced',763:'Jaabz',766:'Jobs in Leeds',751:'Freelancedev'}
 available=[]
 for row in historical:
  if row['id'] in names:
   available.append({'name':names[row['id']],'result':row['body'],'documents':[sources[k] for k in row['body'].get('document_ids',[]) if k in sources]})
 for row in load('ai-extra-historical.json.gz'):
  available.append({'name':'Inputcomm' if row['revision']==707 else 'DSI Design','result':row['result'],'documents':row['documents']})
 for case in available:
  case['documents']=interpretation_documents(case['result'],case['documents'])
  candidate=case['name'];bundle=evidence_bundle(candidate,case['documents']);out=unknown_output({'candidate_id':candidate})
  # These responses are deliberately scripted fixture expectations, NOT output
  # of an actual model and NOT independent human labels.
  if candidate in ('KForge','DIEGO HELP') and bundle:
   term='fornitori' if candidate=='KForge' else 'guida'
   proof=next((e for e in bundle if term in e['text'].lower()),None)
   if proof:
    out.update(source_type='company_page' if candidate=='KForge' else 'editorial',commercial_intent='PARTNERSHIP_SELLER' if candidate=='KForge' else 'EDITORIAL',direction='SELLER' if candidate=='KForge' else 'NONE',relationship_type='SERVICE_OFFER' if candidate=='KForge' else 'EDITORIAL_INFORMATION',supporting_evidence=[{'id':proof['id'],'quote':proof['text']}],confidence=.5,recommended_action='discard')
  cases.append({'id':candidate,'candidate_id':candidate,'documents':case['documents'],'result':case['result'],'response':out,'label_source':'HISTORICAL_SYSTEM_LABEL','split':'development'})
 evaluated=evaluate_cases(cases,simulated=True)
 result={'scope':{'A':'Saved historical sources and deterministic replay','B':'Synthetic guard tests in test_commercial_ai3b','C':'Real Chromium on local fixtures only, separate browser metrics','D':'MOCK default abstentions + explicitly scripted contract responses','E':'Real AI NOT executed'},'baseline':replay['historical']['states'],'hybrid_official':replay['replay']['states'],'shadow':shadow,'ai_usage_simulated':usage,'evaluation':evaluated,'avoided_incompatible_resolution':1,'real_api_calls':0,'real_ai_inferences':0,'real_paid_cost':0,'quality_limits':['No independent HUMAN_LABELED holdout','No model precision/recall estimate','MOCK quality and latency are not real-model performance','Browser historical measurements not refreshed']}
 (ROOT/'implementation-report/phase-3b-ai-evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'mock_calls':usage['calls'],'states_unchanged_by_ai':True,'cases':len(cases),'validation_counts':evaluated['counts'],'precision':evaluated['metrics']['precision'],'recall':evaluated['metrics']['recall'],'real_api_calls':0,'real_ai_inferences':0},indent=2))
if __name__=='__main__':main()
