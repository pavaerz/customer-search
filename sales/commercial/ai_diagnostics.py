"""Minimized validation diagnostics: codes/fields/IDs, no raw model reply."""
import json

CODES={
 'unsupported_requested_service':('MODEL_UNSUPPORTED_CLAIM','requested_service'),
 'unsupported_technical_relevance':('MODEL_UNSUPPORTED_CLAIM','technical_relevance'),
 'unsupported_actor':('ACTOR_ALIAS_UNRESOLVED','actor'),
 'contradictory_actor':('ACTOR_ATTRIBUTION_CONFLICT','actor'),
 'actor_section_conflict':('ACTOR_ATTRIBUTION_CONFLICT','actor'),
 'indexed_request_currentness_unknown':('TEMPORAL_STATUS_UNVERIFIED','relationship_type'),
 'temporal_evidence_not_independently_verified':('TEMPORAL_STATUS_UNVERIFIED','temporal_evidence'),
 'unsupported_currentness':('TEMPORAL_STATUS_UNVERIFIED','temporal_evidence'),
 'generic_collaboration_not_current':('TEMPORAL_STATUS_UNVERIFIED','temporal_evidence'),
 'temporal_role_mismatch':('EVIDENCE_ROLE_MISMATCH','temporal_evidence'),
 'identity_role_mismatch':('EVIDENCE_ROLE_MISMATCH','identity_evidence'),
 'invalid_evidence_attribution':('EVIDENCE_MISSING','supporting_evidence'),
 'unsupported_intent':('EVIDENCE_MISSING','supporting_evidence'),
 'invented_quote':('MODEL_UNSUPPORTED_CLAIM','supporting_evidence'),
}

def diagnose(output,candidate_id,evidence,result,images=None):
    from .ai_schema import validate_output,SCHEMA_VERSION,fingerprint
    response_hash=fingerprint(output)
    try:
        validate_output(output,candidate_id,evidence,result,images)
        return {'code':'VALID','schema_version':SCHEMA_VERSION,'fields':[],'evidence_ids':[]}
    except ValueError as exc:
        reason=str(exc)
        code,field=CODES.get(reason,('MODEL_UNSUPPORTED_CLAIM' if reason.startswith(('unsupported_','contradictory_','unresolved_')) else 'SCHEMA_INVALID','schema'))
    if isinstance(output,str):
        try:output=json.loads(output)
        except ValueError:output={}
    valid={e['id'] for e in evidence}
    refs=[]
    if isinstance(output,dict):
        for key in ('supporting_evidence','identity_evidence','temporal_evidence','contradictions','business_facts','technical_indicators'):
            for ref in output.get(key,[]) if isinstance(output.get(key),list) else []:
                if isinstance(ref,dict) and isinstance(ref.get('id'),str) and ref['id'] in valid:refs.append(ref['id'])
    category={'invented_quote':'INCORRECT_QUOTE','invalid_evidence_attribution':'EVIDENCE_UNAVAILABLE','unsupported_actor':'ACTOR_ATTRIBUTION','contradictory_actor':'ACTOR_ATTRIBUTION','actor_section_conflict':'ACTOR_ATTRIBUTION','temporal_role_mismatch':'EVIDENCE_ROLE','identity_role_mismatch':'EVIDENCE_ROLE'}.get(reason,'SCHEMA_INCOMPATIBLE' if code=='SCHEMA_INVALID' else 'UNSUPPORTED_CLAIM')
    if field=='temporal_evidence' and category=='UNSUPPORTED_CLAIM':category='UNVERIFIED_DATE'
    # No arbitrary model text retained. Fingerprint permits comparison without
    # storing names/credentials. A controlled service label can be retained.
    from .ai_schema import fingerprint
    from .commercial_gate import service_equivalence
    disputed=output.get(field) if isinstance(output,dict) else None
    safe_value=next((v for v in ('WordPress','WooCommerce','frontend','ecommerce') if field=='requested_service' and isinstance(disputed,str) and disputed.casefold()==v.casefold()),None)
    return {'category':category,'contested_value':safe_value,'contested_fingerprint':fingerprint(disputed) if disputed is not None else None,'semantic_review_required':reason=='unsupported_requested_service','bundle_has_request':any('request' in e.get('roles',[]) for e in evidence),'code':code,'fields':[field],'evidence_ids':list(dict.fromkeys(refs))[:24],
            'reason':reason if reason.isidentifier() and len(reason)<80 else 'validation_failed',
            'schema_version':SCHEMA_VERSION,'raw_response_retained':False,'response_hash':response_hash,'diagnosis':'SCHEMA_ERROR' if code=='SCHEMA_INVALID' else 'INSUFFICIENT_EVIDENCE' if code in ('EVIDENCE_MISSING','TEMPORAL_STATUS_UNVERIFIED') else 'UNKNOWN' if field=='actor' or reason=='temporal_role_mismatch' else 'MODEL_UNSUPPORTED_CLAIM'}
