"""Read-only selection of saved evidence, shared by UI and learning."""

def current_original(versions):
    """Keep a valid interpretation of the exact same cached original on AI error.

    Different content, observation date, or a valid later conclusion supersedes
    it normally. This cannot make old evidence fresh or override manual reviews.
    """
    current=next((r for r in versions if r['body'].get('original')),versions[0])
    b=current['body']
    if b.get('validation_status')!='MODEL_INVALID' or not b.get('technical_error'):return current,None
    def docs(body):
        return {d.get('document_id') or d.get('id') for d in body.get('documents',[]) if isinstance(d,dict)}-{None}
    original_docs=docs(b)
    if not original_docs or not b.get('checked_at'):return current,None
    for old in versions:
        ob=old['body']
        if (ob.get('original') and ob.get('validation_status')=='ACCEPTED'
                and not ob.get('verification_hold') and ob.get('url')==b.get('url')
                and ob.get('checked_at')==b['checked_at'] and docs(ob)==original_docs):
            return old,{'record_id':current['id'],'error':b['technical_error'],
                        'basis':'same_documents_and_observation_time_no_new_commercial_evidence'}
    return current,None

