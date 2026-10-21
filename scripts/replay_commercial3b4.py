"""Partial offline replay: metadata, saved originals, gates; no campaign execution."""
import gzip,json,hashlib
from pathlib import Path
from collections import Counter
from sales.commercial.discovery import assess
from sales.commercial.target_fit import evaluate
from sales.commercial.request_profile import hosted_request
from sales.commercial.commercial_gate import sufficient
from sales.commercial.evidence import select
from sales.commercial.catalog import plan,PILOT,BUDGETS

FIXTURE=Path(__file__).resolve().parents[1]/'tests/fixtures/commercial3b4/campaign21.json.gz'
def load():
    with gzip.open(FIXTURE,'rt') as f:return json.load(f)
def replay():
    x=load();traces=[];targets=[];actors=[];gates=[]
    for d in x['commercial_discovery']:
        new=assess(d['body'],d['engine'],d['body'].get('origin'))
        traces.append({'id':d['id'],'engine':d['engine'],'url':d['url'],'before':d['decision'],'after':new['decision'],'reason':new['reason']})
    for r in x['commercial_revisions']:
        b=r['body'];docs=[d for d in x['documents'] if d['id'] in b.get('document_ids',[])];pages=[x['pages'][d['url']] for d in docs if d['url'] in x['pages']]
        if b['engine']=='WEBSITE_REBUILD' and pages:
            fit=evaluate(b.get('identity',{}),pages,b.get('geography'))
            targets.append({'revision':r['id'],'url':b['url'],'original_browser':b.get('browser_outcome'),'target_fit':fit,'audit_selected_in_replay':fit['audit_allowed'],'scope':'target_eligibility_only_no_browser_executed','pages':len(pages)})
        for p in pages:
            actor=hosted_request(p)
            if actor:actors.append({'revision':r['id'],'old_company':b.get('company'),'new_attribution':actor})
    for a in x['commercial_ai_executions']:
        if not a['attempt']:continue
        b=next(r['body'] for r in x['commercial_revisions'] if str(r['opportunity_id'])==a['candidate_id'])
        gate=sufficient(a['engine'],b,a['body'].get('evidence',[]))
        fit=next((t['target_fit'] for t in targets if t['url']==b['url']),None)
        docs=[d for d in x['documents'] if d['id'] in b.get('document_ids',[])];new_evidence,m=select(a['candidate_id'],docs,result={**b,**({'target_fit':fit} if fit else {})})
        gates.append({'id':a['id'],'engine':a['engine'],'url':b['url'],'original_status':a['status'],'saved_bundle_gate':gate,
          'reselected_evidence_gate':sufficient(a['engine'],b,new_evidence),'counterproof_selected':sum('counterevidence' in e.get('roles',[]) for e in new_evidence),
          'scope':'reselection_not_model_call; dispatch_payload_trimming_not_replayed','historical_input_tokens':a['input_tokens'],'historical_output_tokens':a['output_tokens']})
    avoided=[r for r in traces if r['before']=='admit' and r['after']=='exclude']
    return {'phase':'3B.4','fixture_sha256':hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),'scope':'partial_offline_replay_not_real_campaign',
      'historical':{'campaign':21,'appearances':len(traces),'evaluations':len(x['commercial_revisions']),'states':dict(Counter(r['state'] for r in x['commercial_revisions'])),'serper_calls':12,'http_units':163,'ai_calls':6,'browser_started':2,'browser_complete':0},
      'replay':{'discovery':traces,'admitted_now_excluded':len(avoided),'target_fit':targets,'hosted_attribution':actors,'ai_gates':gates,
        'saved_ai_bundles_rejected':sum(not g['saved_bundle_gate']['allowed'] for g in gates),
        'historical_audits_no_longer_selected':sum(t['original_browser']=='partial' and not t['audit_selected_in_replay'] for t in targets),
        'theoretical_resources':{'scope':'counterfactual_unspent_operations_not_actual_savings','audit_slots':sum(t['original_browser']=='partial' and not t['audit_selected_in_replay'] for t in targets),'http_savings':None,'serper_savings':0,'ai_cost_savings':None,'limits':'New counterproof bundles may deserve interpretation; whole pipeline not executed.'}},
      'new_queries_structure':{e:plan(e)[:10] for e in ('FREELANCE','AGENCIES','STARTUPS','WEBSITE_REBUILD')},
      'budgets':{'pilot':PILOT,'standard':BUDGETS,'changed':False},'new_opportunities_verified':None,
      'external_calls':0,'database_writes':0,'limits':['New query yield not tested against Serper','No model answers regenerated','No real sites visited','Target fit is eligibility not qualification']}
if __name__=='__main__':
    r=replay();Path('PHASE-3B.4-METRICS.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r['replay'].items() if k in ('admitted_now_excluded','saved_ai_bundles_rejected','historical_audits_no_longer_selected')}))
