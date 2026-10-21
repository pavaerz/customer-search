"""Conservative consistency checks. Indexed hints never verify identity or demand."""
import re
from .schema import identity_role

EXTERNAL=re.compile(r'\bfreelanc\w*|\bcontractor\b|partita\s*iva|collaborator\w*\s+estern',re.I)
REFUSAL=re.compile(r'no\s+(?:freelancers?|contractors?)|not\s+(?:a\s+)?freelance|non\s+(?:cerchiamo|accettiamo).{0,25}(?:freelance|partita)',re.I)
EMPLOYEE=re.compile(r'full[ -]time|internships?|dipendent|permanent|tempo indeterminato',re.I)


def inspect(source,analysis,facts):
    analysis=analysis or {}
    requests='\n'.join(f['quote'] for f in facts if f['field'] in ('request','contract'))
    external=bool(EXTERNAL.search(requests)) and not REFUSAL.search(requests)
    employee=bool(EMPLOYEE.search(requests))
    status='mixed' if external and employee else 'external_mentioned' if external else 'employee_mentioned' if employee else 'unknown'
    issues=[]
    if analysis.get('kind')=='EMPLOYEE_JOB' and external:issues.append('employee_category_conflicts_with_external_evidence')
    # Hypothesis cannot override the facts or justify a page request on its own.
    if analysis.get('kind')=='EMPLOYEE_JOB' and EXTERNAL.search(analysis.get('hypothesis','')) and not REFUSAL.search(analysis.get('hypothesis','')):
        issues.append('employee_category_conflicts_with_hypothesis')
    identity_issues=analysis.get('identity_issues',[])
    identity_issues=identity_issues+[{'code':'non_company_identity','role':identity_role(f['quote'])} for f in facts if f['field']=='entity' and identity_role(f['quote'])]
    # A role must be observed in the actual source, not invented by the model.
    title=source.get('title','');text=source.get('text','')
    role=re.search(r'\b(?:web editor|social media manager|copywriter)\b',title,re.I)
    content_work=re.search(r'web editing|social media marketing|redazione (?:di )?contenuti|copywriting',text,re.I)
    development=re.search(r'(?:frontend|front.end|web|wordpress) developer|sviluppator\w*|sviluppo (?:siti|web|app)',text,re.I)
    scope_out=bool(role and content_work and not development)
    return {'issues':list(dict.fromkeys(issues)),'identity_issues':identity_issues,
            'relationship':{'status':status,'basis':'original_citation' if source.get('original') else 'indexed_citation','quote':requests or None},
            'scope_exclusion':scope_out,'scope_observation':{'title_quote':role[0],'text_quote':content_work[0],'url':source['url'],'original':bool(source.get('original'))} if scope_out else None}


def decision_metadata(body):
    if body.get('decision_engine')=='ai_first_1':
        if body.get('decision_authority')=='explicit_user_exclusion':
            return {'decision_category':'user_exclusion','semantic_conflict':False,
                    'scope_exclusion':True,'negative_feedback_reliable':False}
        accepted=body.get('validation_status')=='ACCEPTED'
        negative=accepted and body.get('decision')=='NOT_INTERESTING' and not body.get('verification_hold')
        return {'decision_category':'technical_error' if body.get('technical_error') else 'ai_validated' if accepted else 'uncertain',
                'semantic_conflict':False,'scope_exclusion':False,
                'negative_feedback_reliable':bool(negative and body.get('original') and body.get('identity_verified') and body.get('facts') and not body.get('suppressed'))}
    issues=body.get('semantic_issues') or []
    if body.get('technical_error'):category='technical_error'
    elif body.get('scope_exclusion'):category='scope_exclusion'
    elif issues:category='semantic_conflict'
    elif body['state']=='REJECTED' and body.get('original') and body.get('counterevidence'):category='verified_rejection'
    else:category='uncertain' if body['state'] in ('REJECTED','DISCOVERED','UNVERIFIABLE','NEEDS_REVIEW') else 'supported_observation'
    return {'decision_category':category,'semantic_conflict':bool(issues),'scope_exclusion':bool(body.get('scope_exclusion')),
            'negative_feedback_reliable':category=='verified_rejection' and not issues and not body.get('identity_issues')}
