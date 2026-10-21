"""Offline evidence/response harness. Labels are never inferred from CRM states."""
from collections import Counter
from .ai_schema import evidence_bundle,validate_output

LABEL_SOURCES={'HUMAN_LABELED','HISTORICAL_SYSTEM_LABEL','SYNTHETIC_LABEL'}
BUYER={'BUYER_INTENT','PARTNERSHIP_BUYER','FREELANCE_OPPORTUNITY'}


def evaluate_cases(cases,*,simulated=True):
    """Evaluate saved responses, not infer them. No network, DB or AI provider.

    A case uses id, candidate_id, documents, result, response; optional truth is
    {positive: bool, technical_relevance: bool, intent: str}. Only independently
    HUMAN_LABELED holdout cases can support headline model metrics, and only if
    responses came from a real model and both classes have adequate counts.
    """
    output=[]
    for case in cases:
        label_source=case.get('label_source','HISTORICAL_SYSTEM_LABEL')
        if label_source not in LABEL_SOURCES:raise ValueError('Invalid ground-truth provenance')
        documents=case.get('documents') or [];candidate=case.get('candidate_id',case['id'])
        row={'id':case['id'],'label_source':label_source,'split':case.get('split','development'),'simulated':bool(simulated),'evidence_available':bool(documents),'ground_truth':case.get('truth') or {},'historical_state':case.get('result',{}).get('state'),'inference_executed':False}
        if not documents:
            row.update(status='missing_evidence',positive=None,reason='No saved source; no invented reconstruction.')
        else:
            bundle=evidence_bundle(candidate,documents)
            try:
                result=validate_output(case.get('response'),candidate,bundle,case.get('result',{}))
                positive=result['commercial_intent'] in BUYER and result['relationship_type']=='CURRENT_OPEN_REQUEST'
                row.update(status='validated',positive=positive,intent=result['commercial_intent'],technical_relevance=result['technical_relevance'],abstained=result['commercial_intent']=='UNKNOWN',evidence_references=sum(len(result[k]) for k in ('supporting_evidence','identity_evidence','temporal_evidence','contradictions')),output=result)
            except (ValueError,TypeError) as exc:
                row.update(status='invalid',positive=None,reason=str(exc))
        output.append(row)
    independent=[r for r in output if r['label_source']=='HUMAN_LABELED' and r['split']=='holdout' and type(r['ground_truth'].get('positive')) is bool]
    truth=Counter(r['ground_truth']['positive'] for r in independent)
    enough=not simulated and len(independent)>=20 and truth[True]>=5 and truth[False]>=5
    validated=[r for r in output if r['status']=='validated']
    metric={'precision':None,'recall':None,'false_positive':None,'false_negative':None,'abstention_rate':sum(r.get('abstained',False) for r in validated)/len(validated) if validated else None,'evidence_attribution_accuracy':None,'commercial_compatibility_accuracy':None,'cost_per_candidate':None,'latency_per_candidate':None,'independent_holdout_count':len(independent),'meaning':'Validation contracts only; no claim of commercial/model effectiveness.'}
    if enough:
        judged=[r for r in independent if r['positive'] is not None]
        tp=sum(r['positive'] and r['ground_truth']['positive'] for r in judged)
        fp=sum(r['positive'] and not r['ground_truth']['positive'] for r in judged)
        fn=sum(not r['positive'] and r['ground_truth']['positive'] for r in judged)
        metric.update(precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,false_positive=fp,false_negative=fn,meaning='Limited independent human-labelled holdout; model quality, not conversion.')
    return {'cases':output,'counts':dict(Counter(r['status'] for r in output)),'label_sources':dict(Counter(r['label_source'] for r in output)),'metrics':metric,'real_inferences':0,'paid_calls':0,'simulated':bool(simulated),'missing_evidence':[r['id'] for r in output if r['status']=='missing_evidence']}
