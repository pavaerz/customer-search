"""Resume an unattempted, evidenced original-link investigation in a NEW run.

Read-only selection over history; writes only new queue tasks through the normal
coordinator. This is not a promotion, a retry policy or an import of old results.
Only root-page READ_LINK actions are recoverable in v1. Joined/multi-unit actions
need their full parent chain and are deliberately not reconstructed by guessing.
"""
import json
from datetime import datetime, timedelta
from sales.db import digest, now
from sales.providers import canonical, blocked
from sales.content_policy import require_non_pdf, ExcludedPDF
from . import memory
from .research_dispatch import assess

MAX_CONTEXT_AGE = timedelta(days=7)


def holds(store, row):
    from sales.research_store import ResearchStore
    from .entities import commercial_hold
    body=row['body']
    if body.get('suppressed') or body.get('commercial_exclusions'):
        return True
    if ResearchStore(store).suppressed({'website':body.get('official_domain') or body['url']}):
        return True
    with store.connect() as db:
        if commercial_hold(db,body):return True
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='agent8_annotations'").fetchone():
            corrections=db.execute("SELECT a.changes FROM agent8_annotations a JOIN agent6_records r ON r.id=a.record_id WHERE r.request_key=? ORDER BY a.id",(row['request_key'],)).fetchall()
            relevance=None
            for correction in corrections:
                changes=json.loads(correction[0])
                if 'relevance' in changes:relevance=changes['relevance']
            if relevance=='irrelevant':return True
        # Also preserve request-specific CRM stages without a resolved company.
        return bool(db.execute("SELECT 1 FROM prospects WHERE identity=? AND stage IN ('contacted','replied','proposal','won','lost')",
                              ('agent6:'+row['request_key'],)).fetchone())


def load(store, rid):
    with store.connect() as db:
        row=db.execute('SELECT * FROM agent6_records WHERE id=?',(rid,)).fetchone()
    return {**dict(row),'body':json.loads(row['body'])} if row else None


def current(store, row):
    """Any newer original decision/attempt closes this historical continuation."""
    with store.connect() as db:
        return not db.execute("SELECT 1 FROM agent6_records WHERE request_key=? AND id>? AND json_extract(body,'$.original')=1",
                              (row['request_key'],row['id'])).fetchone()


def source_allowed(store, row):
    b=row['body']
    return bool(b.get('decision_engine')=='ai_first_1' and b.get('original')
        and b.get('validation_status')=='ACCEPTED' and b.get('ai_status')=='completed'
        and b.get('decision')=='NEEDS_RESEARCH' and b.get('entity_name')
        and not b.get('verification_hold') and not b.get('technical_error')
        and not b.get('canonical_record_id') and current(store,row) and not holds(store,row))


def proposal(store, row, campaign, settings):
    """Validate saved source provenance again; never invent a destination."""
    b=row['body'];action=b.get('research_action',{});packet=b.get('evidence_packet',{})
    if not source_allowed(store,row) or action.get('type')!='READ_LINK' or not action.get('question'):
        return None
    if b.get('subject_geography',{}).get('status')=='OUT_OF_TARGET':return None
    observed=datetime.fromisoformat(packet['observed_at'])
    age=datetime.fromisoformat(now())-observed
    if not timedelta(0)<=age<=MAX_CONTEXT_AGE:return None
    if canonical(b['url'])!=canonical(packet['final_url']):return None
    unit=next((u for u in packet['units'] if u['id']==b.get('evidence_unit_id')),None)
    if not unit or unit['origin']!='page' or b.get('social_source'):return None
    link=next((l for l in packet['links'] if l['id']==action.get('link_id')),None)
    if not link or not assess(b,[link])['allowed']:return None
    destination=canonical(link['url']);require_non_pdf(link)
    if blocked(destination) or destination==canonical(b['url']):return None
    with store.connect() as db:
        old=db.execute('SELECT filters FROM campaigns WHERE id=?',(row['campaign_id'],)).fetchone()
        if not old:return None
        if set(json.loads(old[0]).get('regions',[]))!=set(campaign['filters']['regions']):return None
        tasks=db.execute("SELECT payload FROM research_tasks WHERE campaign_id=? AND kind='candidate' ORDER BY id DESC",
                         (row['campaign_id'],)).fetchall()
        parent=next((p for t in tasks if canonical((p:=json.loads(t[0])).get('url',''))==canonical(b['url'])
                     and not p.get('research_parent') and not p.get('unit_id')),None)
        if not parent or parent.get('depth',0)>=settings['max_verification_depth']:return None
        page=parent.get('original_page')
        if not page:return None
        # Verify the offered link against the saved HTML, not a model-supplied URL.
        from .evidence import packet as parse_packet
        from sales.commercial.inspection import document
        parsed=parse_packet(page,document(page))
        if parsed['document_id']!=packet['document_id'] or link not in parsed['links']:return None
        if not any(u['id']==unit['id'] and u['text']==unit['text'] for u in parsed['units']):return None
        if not any(f.get('field')=='entity' for f in b.get('facts',[])):return None
        for fact in b['facts']:
            doc=db.execute('SELECT text,content_hash,url FROM research_documents WHERE id=?',(fact.get('document_id'),)).fetchone()
            start,end=fact.get('document_start'),fact.get('document_end')
            if (not doc or digest(doc['text'])!=doc['content_hash'] or type(start) is not int or type(end) is not int
                or start<0 or end<=start or doc['text'][start:end]!=fact.get('quote')
                or canonical(doc['url'])!=canonical(fact.get('url','')) or not fact.get('original')):return None
        # No repeated access failures or already-completed follow-up. A pending
        # or budget-deferred task has not consumed the investigation; it may move.
        for task in db.execute("SELECT payload,state FROM research_tasks WHERE campaign_id>=? AND campaign_id<? AND kind='candidate'",
                               (row['campaign_id'],campaign['id'])):
            p=json.loads(task['payload'])
            if canonical(p.get('url',''))==destination and task['state'] not in ('pending','budget'):
                return None
        for r in db.execute('SELECT body FROM agent6_records WHERE campaign_id>=? AND campaign_id<?',
                            (row['campaign_id'],campaign['id'])):
            other=json.loads(r[0])
            if canonical(other.get('url',''))==destination and (other.get('original') or other.get('workflow_state')=='ORIGINAL_READ_FAILED'):
                return None
    if holds(store,{**row,'body':{**b,'url':destination,'official_domain':destination}}):return None
    return {'url':destination,'title':link['label'],'query':b.get('query'),'strategy':b.get('strategy'),
        'depth':parent.get('depth',0)+1,'research_question':action['question'],
        'continuation':{'version':1,'record_id':row['id'],'campaign_id':row['campaign_id'],
                        'source_url':b['url'],'source_document_id':packet['document_id'],
                        'basis':'unattempted_offered_link_from_validated_original',
                        'source_observed_at':packet['observed_at']},
        'research_parent':{'url':b['url'],'title':b.get('title',''),'unit':unit,
            'packet':{k:packet[k] for k in ('document_id','final_url','observed_at')},
            'link_url':destination,'entity_name':b['entity_name'],'social_context':None}}


def restore(c):
    if c.campaign['filters'].get('continuation_version')!=1:return
    with c.store.connect() as db:
        rows=[{**dict(r),'body':json.loads(r['body'])} for r in db.execute(
            "SELECT r.* FROM agent6_records r JOIN campaigns c ON c.id=r.campaign_id WHERE r.campaign_id<? AND c.status NOT IN ('running','waiting','stopping') AND json_extract(r.body,'$.decision')='NEEDS_RESEARCH' ORDER BY r.id DESC",(c.cid,))]
    from sales.commercial.resources import BudgetExceeded
    for row in rows:
        if row['flow'] not in c.engines:continue
        try:p=proposal(c.store,row,c.campaign,c.settings)
        except (KeyError,ValueError,TypeError,ExcludedPDF):continue
        if not p:continue
        try:queued=c.enqueue('candidate',row['flow'],p,'ai-first-url:'+digest(p['url']))
        except BudgetExceeded:
            memory.event(c.store,c.campaign,row['flow'],'continuation_deferred',str(row['id']),
                         {'record_id':row['id'],'reason':'current_followup_budget'})
            continue
        if queued:
            memory.event(c.store,c.campaign,row['flow'],'continuation_queued',str(row['id']),
                         {**p['continuation'],'destination':p['url'],'question':p['research_question'],
                          'status':'not_yet_verified'})


def check_current(c, payload):
    """Feedback added after queuing still prevents the subsequent HTTP/AI work."""
    origin=payload.get('continuation')
    if not origin:return True
    row=load(c.store,origin['record_id'])
    if not row or not source_allowed(c.store,row):return False
    try:
        age=datetime.fromisoformat(now())-datetime.fromisoformat(origin['source_observed_at'])
        if not timedelta(0)<=age<=MAX_CONTEXT_AGE:return False
    except (KeyError,TypeError,ValueError):return False
    return not c.rs.suppressed({'website':payload['url']})
