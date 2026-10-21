"""Link current-campaign discovery traces to a verified company evaluation.

No deletion, key rewriting, historic campaign changes or name-based merges.
Original independent requests and manually managed records remain independent.
"""
import json
from sales.db import encode,now
from sales.commercial.recommendations import canonical_url


def link(c,cid,rid,body):
    if not body.get('identity_verified') or not body.get('source_aliases'):return
    aliases={canonical_url(url) for url in body['source_aliases']}
    linked_ids=set(body.get('linked_discovery_ids',[]));flows=set(body.get('flows',[]))
    for row in c.execute('SELECT id,body FROM agent6_records WHERE campaign_id=? AND id<>?',(cid,rid)).fetchall():
        old=json.loads(row['body'])
        if old.get('original') or old.get('canonical_record_id') or canonical_url(old['url']) not in aliases:continue
        if c.execute('SELECT 1 FROM agent6_feedback WHERE record_id=?',(row['id'],)).fetchone():continue
        # Revisions keep the discovery decision; the trace explicitly points
        # to its final evaluation instead of remaining unfinished in the UI.
        linked={**old,'canonical_record_id':rid,'workflow_state':'CANONICAL_LINKED',
            'canonical_link_basis':'verified_company_acquisition_alias','canonical_url':body['url']}
        c.execute('UPDATE agent6_records SET body=?,updated_at=? WHERE id=?',(encode(linked),now(),row['id']))
        c.execute('INSERT INTO agent6_record_revisions(record_id,body,created_at) VALUES (?,?,?)',(row['id'],encode(linked),now()))
        linked_ids.add(row['id']);flows.update(old.get('flows',[]))
    if linked_ids:
        body.update(linked_discovery_ids=sorted(linked_ids),flows=sorted(flows))
        c.execute('UPDATE agent6_records SET body=? WHERE id=?',(encode(body),rid))
        c.execute('INSERT INTO agent6_record_revisions(record_id,body,created_at) VALUES (?,?,?)',(rid,encode(body),now()))
