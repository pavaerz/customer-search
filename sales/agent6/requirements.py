"""Opportunity-specific requirements. Unknown optional facts are not negatives."""

PROFILES = {
    'BUYER_DEMAND': {
        'required': ['entity', 'request', 'technical', 'contract', 'geography', 'publication'],
        'optional': ['budget', 'contact'], 'not_required_for_type': ['digital_gap', 'signal', 'existing_solution'],
        'qualified_state': 'VERIFIED',
    },
    'AGENCY_PARTNERSHIP': {
        'required': ['entity', 'request', 'contract', 'geography', 'publication'],
        'optional': ['budget', 'contact', 'technical'], 'not_required_for_type': ['digital_gap', 'signal', 'existing_solution'],
        'qualified_state': 'POTENTIAL',
    },
    'COMPANY_SIGNAL': {
        'required': ['entity', 'signal', 'publication', 'digital_gap', 'scope'],
        'optional': ['budget', 'contact', 'existing_solution', 'feasibility'], 'qualified_state': 'POTENTIAL',
    },
}


def reconcile(body):
    profile = PROFILES.get(body.get('kind'))
    if not profile:
        return
    # A declared low budget still fails objective gates. Only an absent budget
    # is optional; never attribute the freelancer's thresholds to the buyer.
    optional = set(profile['optional'])
    previous = body.get('missing', [])
    body['optional_unknowns'] = sorted(set(body.get('optional_unknowns', [])) | (set(previous) & optional))
    if body.get('budget', {}).get('kind') == 'UNKNOWN':
        body['optional_unknowns'] = sorted(set(body['optional_unknowns']) | {'budget'})
    inapplicable=set(profile.get('not_required_for_type',[]))
    body['inapplicable_requirements']=sorted(set(previous)&inapplicable)
    body['missing'] = [x for x in previous if x not in optional|inapplicable]
    body['qualification_requirements'] = {**profile,
        'conditional': ['scope_if_specific_project', 'feasibility_security_integrations_if_webapp'],
        'optional_unknowns': body['optional_unknowns'],
        'exclusions': ['employee_only', 'closed_request', 'unpaid_service', 'wrong_subject', 'outside_scope'],
        'unknown_means': 'not_confirmed_not_false', 'promotion': 'all_source_bound_gates_must_pass'}
