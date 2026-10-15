"""Version only changes that affect automatic evaluation, never manual decisions."""
FOUNDATION_VERSION='search-foundation-v1'

import json
import re
from .db import digest,encode,domain

RULES={'organization':1,'documents':1,'context':1,'collaboration':1}

def stamp(filters=None):
    filters=filters or {}
    return {'rules':dict(RULES),'scope':{k:sorted(filters[k]) if isinstance(filters.get(k),list) else filters.get(k)
            for k in ('regions','groups','projects','target')}}


def relevant(reason,details):
    text=(reason+' '+str(details.get('limits',[]))).casefold()
    parts=[]
    if re.search(r'fornitore di servizi digitali|vende servizi digitali|candidatur|collaborazion',text):parts.append('collaboration')
    if re.search(r'pagina necessaria|privacy|pagina identità|soluzione collegata',text):parts.append('documents')
    if re.search(r'capacità|contesto|correlazione da suddividere',text):parts.append('context')
    if details.get('organization') or re.search(r'ulss|ente sanitario|directory',text):parts.append('organization')
    if re.search(r'region|territorio|categoria di cliente|segmento selezionato',text):parts.append('scope')
    return parts


def reconsideration(store,url,filters):
    """Targeted automatic stale decisions only; a mere visit is not an assessment."""
    from .research_store import ResearchStore
    if ResearchStore(store).suppressed({'website':url}):return None
    with store.connect() as c:
        row=c.execute('''SELECT d.*,c.filters FROM discovery_candidates d JOIN campaigns c ON c.id=d.campaign_id
            WHERE d.url=? ORDER BY d.updated_at DESC,d.id DESC LIMIT 1''',(url,)).fetchone()
    if not row or row['state'] not in ('rejected','needs_review','unverifiable'):return None
    details=json.loads(row['details']);old=details.get('evaluation_policy') or {}
    current=stamp(filters)
    for part in relevant(row['reason'],details):
        changed=(old.get('scope',stamp(json.loads(row['filters']))['scope'])!=current['scope']) if part=='scope' else old.get('rules',{}).get(part)!=current['rules'][part]
        if changed:
            return {'token':digest(encode(current)),'changed_rule':part,'previous_candidate_id':row['id'],
                    'previous_state':row['state'],'previous_reason':row['reason'],'previous_policy':old or None}
    return None
