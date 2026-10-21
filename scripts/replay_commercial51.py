"""Reproduce Phase 5.1 from frozen local evidence; no DB or network imports."""
import copy,gzip,hashlib,json
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from sales.commercial.demand import assess,source_from_document
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/commercial51/campaign30.json.gz'

def load():
 with gzip.open(FIXTURE,'rt',encoding='utf8') as f:return json.load(f)
def binary(pairs):
 # None is an unlabelled target, never a negative. Unknown predictions abstain
 # (reported separately) and count as misses for a labelled positive.
 known=[(a,b) for a,b in pairs if a is not None]
 tp=sum(a is True and b is True for a,b in known);fp=sum(a is False and b is True for a,b in known)
 fn=sum(a is True and b is not True for a,b in known);tn=sum(a is False and b is False for a,b in known)
 return {'labelled':len(known),'tp':tp,'fp':fp,'fn':fn,'tn':tn,'abstentions':sum(b is None for a,b in known),'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,'false_positive_rate':fp/sum(a is False for a,b in known) if any(a is False for a,b in known) else None}
def categorical(pairs):
 pairs=[(a,b) for a,b in pairs if a is not None];known=[(a,b) for a,b in pairs if b not in (None,'UNKNOWN')]
 confusion=Counter(a+' -> '+str(b) for a,b in pairs if a!=b)
 return {'labelled':len(pairs),'predictions':len(known),'correct':sum(a==b for a,b in pairs),'accuracy':sum(a==b for a,b in pairs)/len(pairs) if pairs else None,'precision_among_non_unknown':sum(a==b for a,b in known)/len(known) if known else None,'confusion':dict(confusion)}
def replay():
 f=load();docs={d['url']:d for d in f['documents']};refs={c['id']:c for c in f['cases']};rows=[]
 for x in f['items']:
  b=x['body'];doc=docs.get(b['url']);source=source_from_document(doc) if doc else {**b.get('discovery',{}),'original':False,'text':b.get('discovery',{}).get('snippet') or b.get('discovery',{}).get('content','')}
  new=assess(source,b.get('identity'),b,date.fromisoformat(f['as_of']))
  old_page={'job_posting':'INDIVIDUAL_JOB','job_portal':'INDIVIDUAL_JOB','article':'EDITORIAL_CONTENT','directory':'DIRECTORY','aggregator':'JOB_AGGREGATION'}.get(b.get('source_kind'),'UNKNOWN')
  old_demand=(b.get('commercial_intent') or {}).get('commercial_role') in ('BUYER','PARTNERSHIP_BUYER','FREELANCE_BUYER')
  old_geo=x.get('activity',{}).get('geographic_eligibility','GEO_UNKNOWN');old_geo={'GEO_COMPATIBLE':'GEO_COMPATIBLE_CONFIRMED','GEO_INCOMPATIBLE':'GEO_INCOMPATIBLE_CONFIRMED'}.get(old_geo,old_geo)
  rows.append({**refs[x['id']],'new':new,'baseline_pred':{'page_type':old_page,'buyer_demand':old_demand,'preserve_lead':x['state'] in ('NEEDS_REVIEW','POTENTIAL','VERIFIED'),'qualified':x['state'] in ('POTENTIAL','VERIFIED'),'technical_fit':bool(b.get('skills')),'geography':old_geo}})
 gold=[r for r in rows if r['reference']['certainty']=='Gold'];scores={}
 for label,key,newkey in [('buyer_demand','buyer_demand','request_observed'),('commercial_lead','preserve_lead','request_observed'),('qualified','qualified','qualified'),('technical_fit','technical_fit','technical_fit')]:
  def pred(r):
   if newkey=='qualified':return r['new']['level'] in ('VERIFIED','POTENTIAL','READY_TO_CONTACT')
   if newkey=='technical_fit':return {'COMPATIBLE':True,'INCOMPATIBLE':False}.get(r['new'][newkey]['status'])
   return r['new'][newkey]
  scores[label]={'baseline':binary([(r['reference'][key],r['baseline_pred'][key]) for r in gold]),'new':binary([(r['reference'][key],pred(r)) for r in gold])}
 scores['page_type']={k:categorical([(r['reference']['page_type'],r['new']['page_type'] if k=='new' else r['baseline_pred']['page_type']) for r in gold]) for k in ('baseline','new')}
 scores['geography']={k:categorical([(r['reference']['geography'],r['new']['geography']['status'] if k=='new' else r['baseline_pred']['geography']) for r in gold if r['reference']['geography_labelled']]) for k in ('baseline','new')}
 yields=defaultdict(lambda:{'candidates':0,'excluded':0,'retained_requests':0,'qualified':0,'unknown_page_type':0})
 by_url={r['url']:r for r in rows}
 for r in rows:
  traces=[t for t in f['traces'] if t['url']==r['url'] and t['engine']==r['engine'] and t['decision']=='admit']
  body=traces[0]['body'] if traces else {};body=json.loads(body) if isinstance(body,str) else body
  strategy=body.get('strategy_id') or body.get('origin',{}).get('strategy_id') or 'unattributed'
  r['strategy']=strategy;out=yields[strategy];out['candidates']+=1;out['excluded']+=int(r['new']['excluded']);out['retained_requests']+=int(r['new']['request_observed']);out['unknown_page_type']+=int(r['new']['page_type']=='UNKNOWN')
 failures=Counter(t.get('error') or 'unknown' for t in f['tasks'] if t['state']=='failed')
 metrics={'phase':'5.1','mode':'offline_replay','as_of':f['as_of'],'fixture_sha256':hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),'analyzed':len(rows),'labels':dict(Counter(r['reference']['certainty'] for r in rows)),
 'original_pages_available':sum(r['audit']['original_available'] for r in rows),'scope':'Source/qualification replay on saved extracted channels, not a rerun of HTTP discovery. Missing HTML/links cannot be reconstructed.',
 'metrics':scores,'false_positives':scores['commercial_lead']['new']['fp'],'false_negatives':scores['commercial_lead']['new']['fn'],'baseline_false_positives':scores['commercial_lead']['baseline']['fp'],
 'precision_baseline':scores['commercial_lead']['baseline']['precision'],'precision_new':scores['commercial_lead']['new']['precision'],'recall_baseline':scores['commercial_lead']['baseline']['recall'],'recall_new':scores['commercial_lead']['new']['recall'],
 'geography_errors':{k:len([1 for r in gold if r['reference']['geography_labelled'] and r['reference']['geography']!=(r['new']['geography']['status'] if k=='new' else r['baseline_pred']['geography'])]) for k in ('baseline','new')},
 'attribution_errors':{'scope':'mandatory Twine and Prout evidence actor assigned to publisher; no exhaustive verified buyer gold corpus','baseline_cases':[929,950],'new_cases':[r['id'] for r in rows if r['id'] in (929,950) and r['new']['actors']['buyer']==r['audit']['publisher']]},
 'page_type_errors':{k:sum(r['reference']['page_type']!=(r['new']['page_type'] if k=='new' else r['baseline_pred']['page_type']) and (r['new']['page_type'] if k=='new' else r['baseline_pred']['page_type'])!='UNKNOWN' for r in gold) for k in ('baseline','new')},
 'page_type_abstentions':{k:sum((r['new']['page_type'] if k=='new' else r['baseline_pred']['page_type'])=='UNKNOWN' for r in gold) for k in ('baseline','new')},
 'candidates_excluded':sum(r['new']['excluded'] for r in rows),'candidates_retained':sum(not r['new']['excluded'] for r in rows),'specific_or_standing_requests_retained':sum(r['new']['request_observed'] for r in rows),
 'unknown_rate':{'baseline_page_type':sum(r['baseline_pred']['page_type']=='UNKNOWN' for r in rows)/len(rows),'new_page_type':sum(r['new']['page_type']=='UNKNOWN' for r in rows)/len(rows),'unlabelled_reference':sum(r['reference']['certainty']=='Unknown' for r in rows)/len(rows)},
 'candidate_budget':{'baseline_reservations':sum(r['used'] for r in f['resources'] if r['resource']=='candidates'),'known_exclusions_before_deepening':sum(r['new']['excluded'] for r in rows),'simulation_not_usage':True,'new_live_reservations':None,'note':'Historical evidence replay identifies avoidable deepening, not guaranteed saved HTTP/credits or new yield; other limits unchanged.'},
 'strategy_yield':dict(yields),'operational_errors':{'historical_failed_tasks':sum(failures.values()),'historical_reasons':dict(failures),'new_live_errors':None},
 'api_calls':{'openai':0,'serper':0,'external_http':0},'costs':{'external_calls_usd':0,'serper_credits':0},'campaigns_started':0,'tests_passed':None,'tests_failed':None,
 'limitations':['Only three labelled viable leads, not three verified opportunities.','Same-corpus development replay, no independent holdout and no conversion evidence.','Page taxonomy crosswalk is incomplete in 5.0; UNKNOWN lowers coverage, not automatically a false-positive.','70 saved original pages; inaccessible originals remain unverified.','Prout explicitly lists $500 fixed price; scope/economic suitability is not confirmed.','No browser execution justified for these semantic cases.']}
 return metrics,rows

def write():
 metrics,rows=replay();(ROOT/'PHASE-5.1-METRICS.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
 (ROOT/'implementation-report/phase51-replay.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:metrics[k] for k in ('analyzed','labels','precision_baseline','precision_new','baseline_false_positives','false_positives','specific_or_standing_requests_retained','page_type_errors','geography_errors')},ensure_ascii=False))
if __name__=='__main__':write()
