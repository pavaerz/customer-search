"""Acquisition boundaries for commercial prospecting, before crawling or inference."""
import json
import re
from urllib.parse import urlsplit
from .db import domain, now

# Sources may document a named business later; they are never a business prospect.
NON_BUYERS = ('baidu.com','zhihu.com','wikipedia.org','wiktionary.org','treccani.it',
              'reddit.com','quora.com','forumfree.it','forumcommunity.net','stackoverflow.com',
              )
EDITORIAL=('corriere.it','repubblica.it','ansa.it','ilsole24ore.com','venetoup.com','venetoeconomia.it','nordesteconomia.gelocal.it')
GENERIC_PATH = re.compile(r'/(?:bandi|bando|agevolazioni|finanziamenti|forum|question|questions|wiki|vocabolario|enciclopedia|cronaca|sport)(?:/|$)',re.I)


def excluded_url(url):
    host=domain(url)
    if any(host==h or host.endswith('.'+h) for h in NON_BUYERS):
        return 'Portale editoriale, enciclopedia o forum: non è un’impresa da contattare.'
    path=urlsplit(url).path
    if any(host==h or host.endswith('.'+h) for h in EDITORIAL) and path.strip('/') in ('','economia','notizie','news'):
        return 'Indice editoriale generico: serve un articolo riferito a un’impresa.'
    if GENERIC_PATH.search(path):
        return 'Pagina di bandi, discussione o cronaca: non è un sito aziendale da investigare.'
    return None


def acquisition_exclusion(item, payload):
    """Routing only: unknown facts still require original-page verification."""
    url=item.get('url','')
    reason=excluded_url(url)
    if reason:return reason
    from .discovery_relevance import preflight
    reason=preflight(item,payload)
    if reason:return reason
    text=str(item.get('title',''))+' '+str(item.get('content',''))
    letters=re.findall(r'[^\W\d_]',text)
    cjk=re.findall(r'[\u3400-\u9fff]',text)
    if len(cjk)>=4 and len(cjk)/max(1,len(letters))>.25:
        return 'Risultato in lingua non pertinente alla ricerca di imprese italiane.'
    # Contextual followups already carry a verified company domain.
    if payload.get('company_host') and domain(url)==payload['company_host']:return None
    if re.search(r'\b(?:wikipedia|treccani|dizionario|enciclopedia|forum)\b',str(item.get('title','')),re.I):
        return 'Fonte informativa generica, non un’impresa del segmento.'
    return None


def task_in_scope(kind, strategy, payload, filters):
    """No autonomous news/feed spider in a customer acquisition campaign."""
    from .direct_channels import route_exclusion,linkedin_notice
    if kind=='source' or route_exclusion(payload):return False
    if kind=='candidate' and linkedin_notice(payload):return True
    from .discovery_relevance import subject_exclusion,utility_link
    if utility_link(payload.get('url','')):return False
    if payload.get('subject') and subject_exclusion(payload['subject'],payload.get('source_documents',[])):return False
    if excluded_url(payload.get('url','')):return False
    if payload.get('company_host'):return kind in ('candidate','verify','search')
    if strategy=='companies' or payload.get('company_stage')=='identify':return True
    from .company_research import selected_strategies
    if strategy in selected_strategies(filters) and payload.get('hypothesis'):return True
    groups=filters.get('groups',['direct','agencies'])
    return strategy in ('partner','explicit') and 'agencies' in groups


def apply_scope(rs, campaign):
    """Retire obsolete queued work, preserving completed decisions and all evidence."""
    cid=campaign['id'];changed=0
    with rs.store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM campaigns WHERE id=? AND generation=?',(cid,campaign['generation'])).fetchone():return 0
        for table in ('research_tasks','discovery_frontier'):
            rows=c.execute('SELECT id,kind,strategy,payload FROM '+table+" WHERE campaign_id=? AND state IN ('pending','deferred','blocked','failed')",(cid,)).fetchall()
            for row in rows:
                if not task_in_scope(row['kind'],row['strategy'],json.loads(row['payload']),campaign['filters']):
                    changed+=c.execute('UPDATE '+table+" SET state='superseded' WHERE id=?",(row['id'],)).rowcount
        from .company_research import selected_strategies
        allowed=selected_strategies(campaign['filters'])
        for row in c.execute('SELECT strategy,region FROM discovery_branches WHERE campaign_id=?',(cid,)).fetchall():
            if row['strategy'] not in allowed:
                c.execute("UPDATE discovery_branches SET state='retired',reason='Ricerca commerciale circoscritta alle imprese; esplorazione generalista disattivata.' WHERE campaign_id=? AND strategy=? AND region=?",(cid,row['strategy'],row['region']))
        # A stale pending query must not consume the planner's scheduling window forever.
        c.execute("""UPDATE discovery_queries SET status='superseded' WHERE campaign_id=? AND status='pending'
            AND EXISTS (SELECT 1 FROM discovery_frontier f WHERE f.campaign_id=discovery_queries.campaign_id
            AND json_extract(f.payload,'$.query_key')=discovery_queries.fingerprint AND f.state='superseded')""",(cid,))
    if changed:rs.event(cid,'planner',f'{changed} lavori generalisti ritirati dalla coda. Storico conservato; ricerca concentrata sulle imprese.')
    return changed
