"""Deterministic Phase 4.4 replay from saved evidence only. Never contacts a site."""
import gzip,json,hashlib
from pathlib import Path
from collections import Counter
from sales.commercial.recommendations import rank,canonical_url,safe_url
from sales.commercial.opportunity_view import build
from sales.commercial.audit_summary import coverage
ROOT=Path(__file__).resolve().parents[1]
def evaluate():
 path=ROOT/'tests/fixtures/commercial44/campaign28.json.gz'
 with gzip.open(path,'rt') as f:x=json.load(f)
 rows=rank(x['items'],x['snapshot_at']);recommended=[r for r in rows if r['recommended']]
 engines={}
 for engine in ('FREELANCE','AGENCIES','STARTUPS','WEBSITE_REBUILD'):
  subset=[r for r in rows if r['engine']==engine];social=[r for r in subset if r['classification']=='social_incomplete']
  engines[engine]={'records':len(subset),'recommended':sum(r['recommended'] for r in subset),'social_incomplete':len(social),'social_recovered':sum(r['recommended'] for r in social),'usable_url_format':sum(bool(r['original_url']) for r in subset),'url_accessibility_not_implied':True,'recommended_tiers':dict(Counter(r['tier'] for r in subset if r['recommended'])),'all_tiers':dict(Counter(r['tier'] for r in subset)),'excluded_reasons':dict(Counter(r['exclusion'] for r in subset if not r['recommended']))}
 groups={}
 for r in rows:
  if r['engine']=='WEBSITE_REBUILD' or not r['original_url']:continue
  groups.setdefault(canonical_url(r['original_url']),[]).append(r['id'])
 duplicates=[{'url_key':k,'ids':ids,'extra_records':len(ids)-1} for k,ids in groups.items() if len(ids)>1]
 browsers=[{'id':i['id'],'company':i['body'].get('company'),'elapsed_ms':i['body']['browser'].get('elapsed_ms'),'coverage':coverage(i['body']['browser'])} for i in x['items'] if (i['body'].get('browser') or {}).get('resource_requests')]
 corrections=[]
 for ident in (856,857,797):
  item=next(i for i in x['items'] if i['id']==ident);v=build(item['body'])
  corrections.append({'id':ident,'official_state':item['state'],'body_reason':item['body'].get('reason'),'view_status':v['status'],'view_reason':v['reason'],'missing':v['missing'],'official_domain':v['official_domain']})
 return {'phase':'4.4','campaign_id':28,'scope':'OFFLINE_SAVED_EVIDENCE','as_of':x['snapshot_at'],'fixture_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'records':len(rows),'engines':engines,'recommended_total':len(recommended),'recommended_tiers':dict(Counter(r['tier'] for r in recommended)),'duplicates_in_saved_non_outbound_records':duplicates,'duplicates_removed_from_recommendations':sum(r['duplicate_of'] is not None for r in rows),'recommended':recommended,'evaluations':rows,'commercial_corrections':corrections,'browser':{'historical_runs':len(browsers),'historical_complete':sum(b['coverage']['completed'] for b in browsers),'historical_only':True,'completion_improvement_demonstrated':False,'audits':browsers},'operations':{'new_campaigns':0,'serper_calls':0,'openai_calls':0,'external_browser_runs':0,'production_database_writes':0,'emails_sent':0,'applications_sent':0,'credentials_modified':False,'budgets_changed':False},'limits':['Recommendations are not verified commissions or currently available jobs.','Original URL format does not guarantee a live or accessible page.','Same source records are not independent positives.','Scoring weights are editorial rules, not empirically validated conversion estimates.','No browser completion improvement is claimed.']}
if __name__=='__main__':
 m=evaluate();out=ROOT/'implementation-report/phase44-replay.json';out.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:m[k] for k in ('records','engines','recommended_total','recommended_tiers','duplicates_in_saved_non_outbound_records')},ensure_ascii=False))
