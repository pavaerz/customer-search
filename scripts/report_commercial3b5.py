"""Assemble local replay/test artifacts. No network, database or model access."""
import ast
import hashlib
import json
import re
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from scripts.replay_commercial3b5 import load,replay
from sales.commercial.discovery import assess

ISSUES={
 'amts_cross_company_attribution':('FIXED','Historical HTML: publisher, AUTOVIP address and Italdesign size no longer merged.'),
 'general_multisubject_extraction':('PARTIALLY_FIXED','Explicit listings/structured multi-employer pages blocked; no general entity-splitting parser for arbitrary HTML.'),
 'employee_number_parsing':('FIXED','Grouped numbers, ranges, approximations, truncation and other-company assertions tested.'),
 'apice_false_actor':('FIXED','Saved original: candidate addressing removed from requester conflicts; WordPress/PrestaShop freelance retained.'),
 'parklab_geography':('FIXED','Saved address resolves Milano/Lombardia; IT no longer masks the municipality.'),
 'complete_italian_geography':('PARTIALLY_FIXED','Versioned local subset, not a complete official municipality/postcode registry.'),
 'vanzo_false_directory':('FIXED','Historical /rivenditori/ no longer sufficient to exclude manufacturer; identity still uncertain.'),
 'olivi_identity':('FIXED','Historical legal footer parsed after copyright prefix; VAT and supporting contacts reconcile.'),
 'ai_alias_and_evidence':('PARTIALLY_FIXED','Verified with bounded synthetic aliases and historical evidence selection. Four missing original replies cannot be revalidated.'),
 'ai_private_diagnostics':('FIXED','Metadata-only retention, permissions, size bound and disabled mode tested. No raw replies.'),
 'browser_external_reliability':('PARTIALLY_FIXED','Local Chromium levels, resource policy and failure handling tested. External TLS/robots/timeouts not re-tested or bypassed.'),
 'browser_partial_measurements':('FIXED','Incomplete rendering never confirms overflow or produces qualification findings in tested cases.'),
 'historical_audit_visibility':('FIXED','Read view preserves revision 897 under latest decision 899; real temporary SQLite regression.'),
 'company_opportunity_deduplication':('PARTIALLY_FIXED','Future verified standing partner pages merge; explicit jobs stay distinct. Legacy Italiaonline opportunities remain unchanged.'),
 'agency_discovery_precision':('PARTIALLY_FIXED','Historical noisy query admissions 8 -> 1; future precision/recall not measured.'),
 'startup_query_yield':('PARTIALLY_FIXED','Alternative less exact families implemented with unchanged quotas; yield untested without Serper.'),
 'consultative_lead_priority':('FIXED','Derived labels and ordering; AMTS data review, Pichler low priority, technical leads distinguished. UI tested locally.'),
}
RULES={
 875:('Candidate addressing treated as a second requester; generic page publication dated vacancy.','Exclude candidate-addressing actors; separate page date from request date; plural technical roles.','Actual availability and location remain unknown.'),
 876:('Generic IT token blocked city resolution; standing policy could be treated as an open project.','Resolve only known address components; keep standing policies in NEEDS_REVIEW; select technical recipient.','No current commissioned project or budget demonstrated.'),
 878:('Reseller path alone implied external directory.','Use page and owner context; retain uncertainty in identity.','Company identity and eligible location still require corroboration.'),
 879:('Copyright prefix blocked anchored legal-name recognition.','Parse legal footer with normalized prefix; reconcile VAT/name/contact; consistent reason.','No completed browser or commercial need demonstrated.'),
 891:('Catalog merged publisher and exhibitor data; 1.300 truncated to 300.','Explicit multisubject boundary; ACTOR_UNRESOLVED; do not borrow exhibitor records.','No individual requesting company identified.'),
 901:('Safety training document reached company screening.','Reject title/context about safety courses before audit.','No web development demand demonstrated.'),
}

def test_log(path):
    text=Path(path).read_text()
    m=re.search(r'Ran (\d+) tests in ([\d.]+)s',text)
    return {'path':str(path),'tests':int(m[1]) if m else None,'seconds':float(m[2]) if m else None,'passed':bool(re.search(r'^OK$',text,re.M)),'sha256':hashlib.sha256(text.encode()).hexdigest(),'warnings':'ResourceWarning' in text}

def build():
    x=load();data=replay();latest={}
    for r in x['commercial_revisions']:latest[r['opportunity_id']]=r
    revised={r['revision']:r for r in data['replay']}
    after=Counter(revised[r['id']]['replay_decision'] for r in latest.values())
    traces=[]
    for d in x['commercial_discovery']:
        new=assess(d['body'],d['engine'],d['body'].get('origin'))
        traces.append({'id':d['id'],'engine':d['engine'],'url':d['url'],'query':d['body'].get('query'),'task_id':d['body'].get('origin',{}).get('task_id'),'origin':d['body'].get('origin',{}).get('acquisition'),'original':d['decision'],'replay':new['decision'],'reason':new['reason']})
    query=[r for r in traces if r['task_id']==3821 and r['origin']=='search']
    for r in data['replay']:
        r.pop('replayed_body',None)
        before_rule,after_rule,missing=RULES.get(r['revision'],('Recorded 3B.4 evaluation.','Same commercial gates with 3B.5 identity/context parser; browser not executed.','See recorded limits; unknown information is not inferred.'))
        r.update(previous_rule=before_rule,new_rule=after_rule,missing_checks=missing,
                 scope=r.get('scope','saved_originals_identity_context_target_only_not_whole_pipeline'))
    attempts=[a for a in x['commercial_ai_executions'] if a['attempt']]
    hist={'campaign':22,'snapshot_at':x['snapshot_at'],'duration_seconds':397.809,'search_results':86,'followups':1,'revisions':len(x['commercial_revisions']),'unique_opportunities':len(latest),'latest_states':dict(Counter(r['state'] for r in latest.values())),
          'ai':{'attempts':len(attempts),'states':dict(Counter(a['status'] for a in attempts)),'errors':dict(Counter(a['body'].get('error') for a in attempts if a['status']=='invalid')),'invalid_original_replies_missing':sum(not a['body'].get('output') for a in attempts if a['status']=='invalid'),'input_tokens':sum(a.get('input_tokens') or 0 for a in attempts),'output_tokens':sum(a.get('output_tokens') or 0 for a in attempts)},
          'browser':{'executed':2,'complete':0,'partial':2,'revision_ids':[884,897]},'serper_calls':12,'http_units':188}
    metrics={'phase':'3B.5','generated_at':datetime.now(timezone.utc).isoformat(),'historical':hist,
      'replay':{'scope':'Partial helper replay over saved HTML. No queue, external access, browser or AI regenerated. Not a new campaign.','fixture_sha256':hashlib.sha256(Path('tests/fixtures/commercial3b5/campaign22.json.gz').read_bytes()).hexdigest(),'original_html_pages':66,'missing_saved_originals':x['missing_originals'],
        'latest_states':dict(after),'decisions':data['replay'],'discovery':traces,'agency_query':{'original_admitted':sum(r['original']=='admit' for r in query),'replay_admitted':sum(r['replay']=='admit' for r in query),'appearances':len(query)},
        'regression_cases':{'cross_company_merge_prevented':1,'false_actor_conflicts_removed':1,'specific_city_regions_restored':1,'false_directory_restored':1,'legal_identity_recovered':1,'historical_partial_audits_preserved':2},
        'admitted_now_excluded':sum(r['original']=='admit' and r['replay']=='exclude' for r in traces),'admissions_not_qualifications':True,'new_verified':0,'new_potential':0},
      'tests':{'suite':test_log('implementation-report/phase-3b5-tests.txt'),'browser':test_log('implementation-report/phase-3b5-browser-tests.txt'),'ui':json.loads(Path('implementation-report/phase-3b5-ux.json').read_text()),'integrity':json.loads(Path('implementation-report/phase-3b5-integrity.json').read_text())},
      'simulated':{'label':'Synthetic fixtures, not external success rates','ai_valid_alias_accepted':1,'ai_invalid_variants_rejected':7,'browser_real_chromium_local':{'cases':7,'basic_complete':1,'standard_complete':2,'partial':4,'tls_transport_simulated':1,'robots_transport_simulated':1},'temporary_sqlite_memory_tests':7,'ui_mock_inferences':1},
      'issues':{k:{'status':v[0],'evidence_and_limit':v[1]} for k,v in ISSUES.items()},
      'operational':{'production_database_writes':0,'external_api_calls':0,'external_visits':0,'new_campaigns':0,'openai_calls':0,'serper_calls':0,'budget_changes':False,'region_changes':False,'credentials_changes':False,'commit_or_push':False,'backend_restarted':False},
      'unmeasured':{'future_search_yield':None,'sales_conversion':None,'revenue':None,'external_browser_completion_rate_after_patch':None}}
    Path('PHASE-3B.5-METRICS.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
    return metrics

if __name__=='__main__':
    m=build();print(json.dumps({'states':m['replay']['latest_states'],'agency_query':m['replay']['agency_query'],'tests':m['tests']['suite'],'admitted_now_excluded':m['replay']['admitted_now_excluded']},indent=2))
