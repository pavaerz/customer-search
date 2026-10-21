"""Reuse only an audit of this company/campaign and identical saved pages."""
import json
from .resources import _context

def reusable(store,identity,documents,campaign_id=None):
    context=_context.get();cid=campaign_id or (context.cid if context else None)
    if not cid or identity.get('identity_status')!='verified' or not documents:return None
    from sales.db import domain
    host=domain(identity.get('website') or '')
    if not host:return None
    with store.connect() as c:
        rows=c.execute("SELECT r.id,r.body FROM commercial_revisions r JOIN commercial_opportunities o ON o.id=r.opportunity_id JOIN research_domains d ON d.entity_id=o.entity_id WHERE r.campaign_id=? AND o.engine='WEBSITE_REBUILD' AND d.domain=? ORDER BY r.id DESC",(cid,host)).fetchall()
        for r in rows:
            body=json.loads(r['body']);audit=body.get('browser') or {}
            if not audit.get('pages') or not audit.get('resources_closed'):continue
            old=[dict(d) for d in c.execute('SELECT url,content_hash FROM research_documents WHERE id IN (SELECT value FROM json_each(?))',(json.dumps(body.get('document_ids',[])),))]
            if all(any(d['url']==o['url'] and d['content_hash']==o['content_hash'] for o in old) for d in documents):
                return {**audit,'reused_revision_id':r['id'],'reuse_scope':'identical_documents_same_company_campaign','new_browser_execution':False}
    return None
