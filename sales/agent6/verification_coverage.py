"""An unfinished requested measurement is not a negative commercial finding.

Separate operational coverage from the model's preserved interpretation. No
qualification, new inference, automatic retry or rewriting historical rows.
"""


def context(requested, question, audit=None):
    audit=audit or {}
    return {'requested':bool(requested),'question':question or '',
            'browser_status':audit.get('browser_status','NOT_EXECUTED'),
            'completed_viewports':audit.get('completed_viewports',[]),
            'limits':audit.get('coverage_limits',[])[:8],
            'unmeasured_controls':sorted({o['code'] for o in audit.get('observations',[])
                                          if o.get('status')=='UNKNOWN'}),
            'external_solutions':[{'url':s['url'],'content_read':bool(s.get('access',{}).get('content_read')),
                                   'adequacy':s.get('adequacy','UNKNOWN')}
                                  for s in audit.get('external_solutions',[])],
            'meaning':'Coverage of the requested inspection; unknown is not absent or defective.'}


def apply(body, coverage):
    if not coverage.get('requested'):return body
    body={**body,'verification_coverage':coverage}
    assessment=body.get('commercial_assessment') or {}
    # Only withhold an absence-of-proof conclusion after an unfinished check
    # requested by this research path. Independent exclusions/small tasks and
    # actual positive/negative findings retain their own commercial meaning.
    incomplete=(coverage.get('browser_status')!='COMPLETE'
                and body.get('decision')=='NOT_INTERESTING'
                and assessment.get('intent') in ('COMPANY_ACTIVITY','UNKNOWN')
                and assessment.get('scope')=='UNKNOWN'
                and assessment.get('existing_solution')=='NOT_CHECKED'
                and not body.get('commercial_exclusions') and not body.get('suppressed')
                and not any(f.get('field')=='closed' for f in body.get('facts',[])))
    if not incomplete:return body
    return {**body,'verification_hold':True,'state':'UNVERIFIABLE',
            'workflow_state':'VERIFICATION_INCOMPLETE',
            'technical_error':'requested_browser_check_incomplete',
            'reason':'Il controllo richiesto sul sito non è stato completato. Non ci sono prove sufficienti '
                     'per proporre un progetto né per concludere questa verifica commerciale.',
            'next_verification':coverage.get('question') or 'Completare il controllo funzionale richiesto sul sito.',
            'negative_feedback_reliable':False}
