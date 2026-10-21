"""Bounded exact-request memory, independent of company-level CRM exclusions."""
import json,re
from datetime import datetime,timezone
from .recommendations import canonical_url
from .job_activity import utc

def signature(d):
    # No query/clock/provider metadata: a different route is not a new request.
    return ' '.join(re.findall(r'\w+',str(d.get('title') or '')+' '+str(d.get('snippet') or d.get('content') or ''),re.U)).casefold()

def decision(store,engine,record,as_of):
    key=canonical_url(record['url']);clock=utc(as_of)
    with store.connect() as c:
        rows=c.execute('SELECT r.created_at,r.body,r.opportunity_id,o.manual_state FROM commercial_revisions r JOIN commercial_opportunities o ON o.id=r.opportunity_id WHERE o.engine=? AND r.id=o.latest_revision',(engine,)).fetchall()
        has=c.execute("SELECT 1 FROM sqlite_master WHERE name='commercial_job_reviews'").fetchone()
        reviews={r['opportunity_id']:r['status'] for r in c.execute('SELECT opportunity_id,status FROM commercial_job_reviews ORDER BY id')} if has else {}
    for row in rows:
        b=json.loads(row['body']);d=b.get('discovery') or {}
        if canonical_url(b.get('url',''))!=key and canonical_url(d.get('original_url',''))!=key:continue
        if row['manual_state'] in ('discarded','contacted') or reviews.get(row['opportunity_id'])=='not_interesting':
            return {'decision':'memory','reason':'user_decision_same_opportunity','previous_opportunity':row['opportunity_id']}
        at=utc(row['created_at']);age=(clock-at).total_seconds() if at else None
        if age is None or age<0:continue
        # A missing page may recover: bounded backoff, not a permanent blacklist.
        if 'HTTP 404' in str(b.get('reason','')) and age<7*86400 and signature(d)==signature(record):
            return {'decision':'memory','reason':'known_404_backoff','previous_opportunity':row['opportunity_id']}
        if age<86400 and signature(d) and signature(d)==signature(record) and b.get('classification') in ('ongoing','generic_availability','open_collaboration','general_collaboration_policy'):
            return {'decision':'memory','reason':'known_request_unchanged','previous_opportunity':row['opportunity_id'],'existing_list':'historical_opportunities'}
    return None
