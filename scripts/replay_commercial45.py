"""Saved campaign 28 replay, separate user-reported manual-observation scenario."""
import gzip,json
from pathlib import Path
from collections import Counter
from sales.commercial.recommendations import rank
from sales.commercial.job_activity import evaluate,observation,early_exclusion
ROOT=Path(__file__).resolve().parents[1]
def evaluate_saved():
 with gzip.open(ROOT/'tests/fixtures/commercial44/campaign28.json.gz','rt') as f:x=json.load(f)
 previous=[r for r in rank(x['items'],x['snapshot_at']) if r['recommended']];bodies={i['id']:i for i in x['items']};rows=[]
 for r in previous:
  i=bodies[r['id']];a=evaluate(i['body'],i['engine'],x['snapshot_at'])
  if a['category']=='not_applicable':a['category']='verify'
  rows.append({'id':r['id'],'title':r['title'],'engine':r['engine'],'previous_state':'RECOMMENDED_4.4','official_state':r['official_state'],'compatibility_score':r['compatibility_score'],'original_url':r['original_url'],**a})
 def summary(items):return {'total':len(items),'categories':{k:sum(r['category']==k for r in items) for k in ('recent','verify','archived')},
  'publication_verified':sum(bool(r['published_at']) for r in items),
  'publication_age_known':sum(r['freshness_status'] in ('FRESH_CONFIRMED','STALE_CONFIRMED') for r in items),
  'opening_verified':sum(r['application_status']=='OPEN_CONFIRMED' for r in items),
  'certainly_closed':sum(r['application_status']=='CLOSED_CONFIRMED' for r in items),
  'certainly_stale':sum(r['freshness_status']=='STALE_CONFIRMED' for r in items),
  'certainly_incompatible':sum(r['geographic_eligibility']=='GEO_INCOMPATIBLE' for r in items),
  'geography_known':sum(r['geographic_eligibility']!='GEO_UNKNOWN' for r in items),
  'insufficient_for_recent':sum(r['category']=='verify' for r in items)}
 fixture=json.loads((ROOT/'tests/fixtures/commercial45/manual_observations.json').read_text());scenario=[]
 for ident,spec in fixture['opportunities'].items():
  i=bodies[int(ident)];ev=[observation(e['kind'],e['value'],i['body']['url'],fixture['scenario_clock'],e['quote'],'MANUAL_OBSERVATIONS',**e.get('extra',{})) for e in spec['observations']]
  a=evaluate(i['body'],i['engine'],fixture['scenario_clock'],ev);scenario.append({'id':int(ident),'scenario':'MANUAL_OBSERVATIONS','observations':ev,**a})
 early=[{'id':i['id'],'result':early_exclusion(i['body'].get('discovery') or {},i['engine'],x['snapshot_at'])} for i in x['items'] if i['engine']=='FREELANCE']
 return {'phase':'4.5','campaign_id':28,'as_of':x['snapshot_at'],'scope':'OFFLINE_SAVED_EVIDENCE','saved_summary':summary(rows),'previous_recommendations':rows,
  'manual_scenario':{'label':'MANUAL_OBSERVATIONS','clock_policy':fixture['clock_policy'],'not_written_to_database':True,'summary':summary(scenario),'items':scenario},
  'resource_measurement':{'saved_freelance_metadata_examined':len(early),'certain_metadata_exclusions':sum(bool(x['result']) for x in early),'metadata_exclusions':early,'actual_saved_serper_credits':0,'actual_saved_http_requests':0,'actual_saved_ai_calls':0,'note':'Offline replay measures eligibility only. No live counterfactual or savings claim. One-read early stop is tested synthetically.'},
  'operations':{'new_campaigns':0,'serper_calls':0,'openai_calls':0,'external_browser_runs':0,'production_database_writes':0,'emails':0,'applications':0,'budgets_changed':False}}
if __name__=='__main__':
 m=evaluate_saved();(ROOT/'implementation-report/phase45-replay.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'saved':m['saved_summary'],'manual':m['manual_scenario']['summary']},ensure_ascii=False))
