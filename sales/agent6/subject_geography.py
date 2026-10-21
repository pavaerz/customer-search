"""Evidence-bound geography of the selected subject, not its publisher.

New calls opt in; saved decisions keep their original schema and meaning.
Unknown eligibility never implies exclusion or permits commercial promotion.
"""
from .schema import obj,arr,TEXT,ValidationError


SYSTEM='When subject_scope_version is supplied, fill subject_geography using geography\nfact indices about the SELECTED subject, not another company or publisher.\nallowed_regions applies to local/proactive businesses. Remote collaborations can\nuse REMOTE_ITALY only with evidence that work from Italy is permitted; an office\noutside the preferred regions alone does not exclude an eligible remote request.\nIN_TARGET requires a cited allowed region/address; OUT_OF_TARGET requires cited\nlocation evidence and NOT_INTERESTING with STOP, even for an opening or funding.\nDo not borrow an Italian location from a different company in the same article.\nUNKNOWN is incomplete eligibility, not proof of absence or permission to promote.\n'

def contract():
    from sales.commercial.geography import REGIONS
    return obj({'status':{'type':'string','enum':['IN_TARGET','REMOTE_ITALY','OUT_OF_TARGET','UNKNOWN']},
                'fact_indices':arr({'type':'integer','enum':list(range(12))},4),
                'region':{'type':'string','enum':['',*REGIONS]},'reason':TEXT})


SYSTEM += '\nregion contains exactly one supported region name for IN_TARGET, otherwise an empty string. Never concatenate regions. If a cited passage mixes several locations or the subject location is ambiguous, use UNKNOWN and explain the missing verification. A member address on a platform does not establish the platform location.\n'
SYSTEM += ('Every subject_geography.fact_indices entry must reference a fact with field="geography". '
           'If one passage supports both a request and its location, cite it as two facts with those different fields; '
           'point geography only to the geography fact. Do not relabel unrelated facts as geography.\n')


def validate(output,facts,payload):
    scope=output.get('subject_geography')
    if not scope:return
    if not scope['reason'].strip():raise ValidationError('missing_geography_reason')
    indices=scope['fact_indices']
    if any(i>=len(facts) or facts[i]['field']!='geography' for i in indices):
        raise ValidationError('wrong_geography_fact')
    if scope['status']!='UNKNOWN' and not indices:
        raise ValidationError('unproven_subject_geography')
    text='\n'.join(facts[i]['quote'] for i in indices)
    if scope['status']=='IN_TARGET':
        from sales.commercial.geography import resolve_location
        from sales.commercial.municipalities import resolve_quotation, resolve_address_quotation
        # The official full registry is consulted only for selected geography
        # facts. Never scan all article prose for short/common town names.
        locations=[]
        for i in indices:
            location=resolve_location(facts[i]['quote'])
            if location['basis']=='UNKNOWN':
                location=resolve_quotation(facts[i]['quote']) or resolve_address_quotation(facts[i]['quote']) or location
            locations.append(location)
        regions={location['region'] for location in locations}
        if scope['region'] not in payload['allowed_regions'] or scope['region'] not in regions:
            raise ValidationError('subject_region_not_supported',
                                  region_allowed=scope['region'] in payload['allowed_regions'],
                                  cited_region_resolved=scope['region'] in regions,
                                  fact_indices=indices)
    elif scope['region']:
        raise ValidationError('unexpected_subject_region')
    if scope['status']=='REMOTE_ITALY':
        from .social import scoped_geography
        import re
        prose=bool(re.search(r'\bremote\b|remoto|TELECOMMUTE|smart working',text,re.I)) and scoped_geography(
                {'text':text,'origin':'page'},payload['allowed_regions'])['allowed']
        if not prose and not structured_remote([facts[i] for i in indices],payload):
            raise ValidationError('remote_italy_not_supported')
    if scope['status']=='OUT_OF_TARGET' and (output['decision']!='NOT_INTERESTING' or output['action']['type']!='STOP'):
        raise ValidationError('out_of_target_followup')
    if scope['status']=='UNKNOWN' and output['decision']=='INTERESTING':
        raise ValidationError('subject_geography_unverified')


def materialize(scope,facts):
    return {**scope,'facts':[facts[i] for i in scope['fact_indices']],
            'basis':'selected_subject_original_evidence','version':1}


def structured_remote(facts,payload):
    """Accept cited IT only inside this job's applicant Country property.

    A publisher address, arbitrary IT token or a different unit cannot supply
    eligibility. Facts are already hash/offset validated by decision.validate.
    Parse complete supplied property values, not the model's interpretation.
    """
    import json,re
    if payload.get('metadata',{}).get('origin')!='JobPosting':return False
    proofs={}
    for e in payload.get('evidence',[]):
        if not e.get('original') or e.get('unit_id')!=payload['unit_id']:continue
        text=e['text']
        for field in ('jobLocationType','applicantLocationRequirements'):
            # Job documents are generated with indent=2. Nested organization
            # properties have deeper indentation and are not job eligibility.
            for m in re.finditer(r'(?m)^  "'+field+r'"\s*:\s*',text):
                try:value,length=json.JSONDecoder().raw_decode(text[m.end():])
                except (ValueError,TypeError):continue
                a=e.get('offset',0)+m.start();b=e.get('offset',0)+m.end()+length
                cited=any(f.get('document_id')==e.get('document_id') and f.get('url')==e['url']
                    and a<=f['document_start']<f['document_end']<=b+1 for f in facts)
                if not cited:continue
                key=(e.get('document_id'),e['url'],e['unit_id'])
                if field=='jobLocationType' and value=='TELECOMMUTE':proofs.setdefault(key,set()).add('remote')
                if field=='applicantLocationRequirements':
                    values=value if isinstance(value,list) else [value]
                    if any(isinstance(v,dict) and v.get('@type')=='Country'
                           and str(v.get('name','')).strip().casefold() in ('it','italia','italy') for v in values):
                        # Cite the eligible country, not another country in an
                        # array where IT happens to occur elsewhere.
                        for f in facts:
                            if (f.get('document_id')==key[0] and f.get('url')==key[1] and
                                a<=f['document_start']<f['document_end']<=b+1 and
                                re.search(r'"name"\s*:\s*"(?:IT|Italia|Italy)"',f['quote'],re.I)):
                                proofs.setdefault(key,set()).add('italy')
    return any(v=={'remote','italy'} for v in proofs.values())
