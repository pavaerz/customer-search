"""Spend gate for a model's follow-up action, not a commercial classifier.

Preserve the assessment and proposed question for review. A supplied service or
completed project alone is not a reason to spend another search on its supplier.
"""
import re


def invitation_check(body, links):
    """An offered invitation can justify one reading, never an open-ended search.

    A services page may also recruit partners. The model must identify the
    subject and ask whether external technical collaboration is actually open.
    The normal depth, duplicate, network and budget gates still apply.
    """
    action=body.get('research_action',{})
    if (body.get('decision')!='NEEDS_RESEARCH' or action.get('type')!='READ_LINK'
        or not body.get('entity_name') or not any(f.get('field')=='entity' for f in body.get('facts',[]))):
        return False
    link=next((l for l in links if l.get('id')==action.get('link_id')),None)
    if not link:return False
    # Inspect the observed label, not a guessed URL or the model's description.
    invitation=re.search(r'lavora con noi|collabora con noi|candidatur|careers?|join (?:us|our)|'
        r'(?:entra|iscriviti|join).{0,35}(?:network|rete|team)|diventa partner',link.get('label',''),re.I)
    question=action.get('question','')
    technical=re.search(r'svilupp|frontend|front.end|wordpress|web|digital|developer',question,re.I)
    external=re.search(r'freelanc|estern|partita\s*iva|contractor',question,re.I)
    decisive=re.search(r'invit|accett|collabor|candid|condizion|requisit|eligib',question,re.I)
    return bool(invitation and technical and external and decisive)


def assess(body, links=()):
    if body.get('research_action',{}).get('type') not in ('SEARCH_SUBJECT','READ_LINK','INSPECT_BROWSER'):
        return {'allowed':True,'reason':'no_paid_followup_requested'}
    assessment=body.get('commercial_assessment',{})
    fields={f.get('field') for f in body.get('facts',[])}
    if (assessment.get('intent') in ('SUPPLYING_SERVICES','TRAINING','COMPLETED_PROJECT')
        and not fields.intersection({'request','digital_gap'})):
        if assessment.get('intent')=='SUPPLYING_SERVICES' and invitation_check(body,links):
            return {'allowed':True,'reason':'observed_invitation_requires_verification',
                    'basis':'offered_invitation_link_and_named_subject_not_confirmed_demand'}
        return {'allowed':False,'reason':'supplier_without_observed_request_or_gap',
                'explanation':'La fonte descrive servizi, formazione o progetti conclusi: manca una richiesta o una lacuna digitale osservata che giustifichi altre ricerche.',
                'basis':'declared_ai_intent_and_cited_fact_fields_not_company_rejection'}
    return {'allowed':True,'reason':'commercial_followup_not_contradicted_by_declared_intent'}
