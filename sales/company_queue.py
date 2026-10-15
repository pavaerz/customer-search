"""Coalesce waiting reviews of a known company without discarding evidence.

Running and completed jobs are immutable: a later discovery can require another
review. This is scheduling, never an identity or qualification shortcut.
"""
import json
from .db import domain, encode, now, digest

MAX_SUBJECT_REVIEWS = 8


def review_budget(connection,cid,payload):
    """Admission budget, not a commercial verdict. Retries remain on the same task."""
    from .evaluation_policy import FOUNDATION_VERSION
    host=payload.get('company_host');company=payload.get('company_key')
    if not host or not company or not payload.get('official_link') or payload.get('publisher'):
        return payload,None
    facts=sorted({digest(encode([d.get('research_text',d.get('text','')),d.get('published_at'),d.get('access_limit')]))
                  for d in payload.get('source_documents',[]) if d.get('text') or d.get('research_text')})
    # Without captured content a genuinely different URL still needs inspection.
    signature=digest(encode([company,host,FOUNDATION_VERSION,payload.get('evaluation_policy'),
                            facts or [payload.get('url')],payload.get('evidence_revision')]))
    revised={**payload,'review_budget':{'version':FOUNDATION_VERSION,'signature':signature}}
    rows=connection.execute("SELECT payload FROM discovery_frontier WHERE campaign_id=? AND kind='verify' AND json_extract(payload,'$.company_key')=? AND json_extract(payload,'$.company_host')=?",(cid,company,host)).fetchall()
    records=[json.loads(r[0]) for r in rows]
    previous=[p.get('review_budget',{}) for p in records if p.get('evaluation_policy')==payload.get('evaluation_policy')]
    aliases={s for r in rows for s in json.loads(r[0]).get('review_signatures',[])}
    if signature in aliases or any(p.get('signature')==signature for p in previous):
        return revised,'Verifica identica già accodata o effettuata; nessuna nuova prova o regola.'
    if sum(p.get('version')==FOUNDATION_VERSION for p in previous)>=MAX_SUBJECT_REVIEWS:
        return revised,'Budget di approfondimento del soggetto raggiunto in questa campagna; occorre una revisione mirata.'
    return revised,None


def evidence_key(doc):
    return digest(encode([doc.get('id'),doc.get('content_hash'),doc.get('published_at'),
                          doc.get('research_text',doc.get('text','')),doc.get('access_limit')]))


def completed_review(rs, campaign, payload, result):
    """Reuse a completed review for an unchanged page already read in this run.

    Only automatic follow-up pages on a verified host are eligible. New content,
    editorial evidence, incomplete reviews and older campaigns must be checked.
    """
    host=payload.get('company_host');company=payload.get('company_key')
    details=result.get('details',{})
    if (payload.get('followup_depth')!=1 or not host or not company or
        not payload.get('official_link') or details.get('publisher') or
        result['state'] in ('rejected','unverifiable')):return None
    docs=[details.get('document',{})]+payload.get('source_documents',[])
    if not docs[0].get('id') or domain(docs[0].get('url',''))!=host:return None
    with rs.store.connect() as c:
        row=c.execute("""SELECT a.*,e.details AS identity FROM research_assessments a
            JOIN research_entities e ON e.id=a.entity_id
            JOIN research_domains d ON d.entity_id=e.id
            WHERE a.campaign_id=? AND d.domain=? AND e.identity_status='verified'
            AND (e.legal_id=? OR (?=? AND e.legal_id IS NULL))
            ORDER BY a.id DESC LIMIT 1""",(campaign['id'],host,company,company,host)).fetchone()
    if not row:return None
    body=json.loads(row['body'])
    from .evaluation_policy import stamp
    if body.get('evaluation_policy')!=stamp(campaign.get('filters')):return None
    if row['status'] not in ('qualified','rejected') or body.get('analysis_status')!='completed':return None
    if not {evidence_key(d) for d in docs}<=set(body.get('examined_documents',[])):return None
    return {'id':row['id'],'assessment':body,'identity':json.loads(row['identity'])}


def inputs(payload):
    return payload.get('review_inputs') or [{k:v for k,v in payload.items()
        if k not in ('source_documents','investigation_plan','review_inputs','merged_keys')}]


def combine(left, right, key):
    merged=dict(left)
    for field in ('source_documents','investigation_plan'):
        values=left.get(field,[])+right.get(field,[])
        if field=='investigation_plan':
            values += [p['investigation_question'] for p in (left,right) if p.get('investigation_question')]
        merged[field]=list({encode(v):v for v in values}.values())
    merged['review_inputs']=list({encode(v):v for v in inputs(left)+inputs(right)}.values())
    merged['merged_keys']=list(dict.fromkeys(left.get('merged_keys',[])+[key]))
    merged['verification_priority']=max(left.get('verification_priority',0),right.get('verification_priority',0))
    for field in ('evaluation_policy','review_budget'):
        if field in right:merged[field]=right[field]
    merged['review_signatures']=list(dict.fromkeys(left.get('review_signatures',[])+
        [p['review_budget']['signature'] for p in (left,right) if p.get('review_budget')]))
    return merged


def coalesce(connection, cid, payload, key):
    """Called within the offer transaction, serialized against claim/Stop.

    Only exact company keys AND official hosts can share a pending review. The
    normal inspector still verifies identity, reads all inputs and checks scope.
    None means a new job is necessary; bool means the offer was handled.
    """
    host=payload.get('company_host');company=payload.get('company_key')
    if not company or not host or not payload.get('official_link') or payload.get('publisher'):
        return None
    if domain(payload.get('url',''))!=host:return None
    rows=connection.execute("""SELECT f.*,t.id AS task_id,t.state AS task_state
        FROM discovery_frontier f LEFT JOIN research_tasks t
        ON t.campaign_id=f.campaign_id AND t.fingerprint=f.fingerprint
        WHERE f.campaign_id=? AND f.kind='verify'
        AND json_extract(f.payload,'$.company_key')=?
        AND json_extract(f.payload,'$.company_host')=? ORDER BY f.id""",(cid,company,host)).fetchall()
    waiting=None
    for row in rows:
        old=json.loads(row['payload'])
        if key==row['fingerprint'] or key in old.get('merged_keys',[]):return False
        if old.get('publisher') or not old.get('official_link'):continue
        if row['state']=='pending' or row['task_state'] in ('pending','deferred'):
            waiting=waiting or (row,old)
    if not waiting:return None
    row,old=waiting;merged=encode(combine(old,payload,key))
    connection.execute('UPDATE discovery_frontier SET payload=? WHERE id=?',(merged,row['id']))
    if row['task_id']:
        connection.execute('UPDATE research_tasks SET payload=?,updated_at=? WHERE id=?',(merged,now(),row['task_id']))
    return True
