"""Read-only status of explicit original-page follow-ups, never entity merging.

A concluded branch is not proof that the company has no needs. Historical
decisions remain unchanged. Unrelated requests and incomplete checks stay open.
"""
import json
from collections import defaultdict

from sales.db import domain
from sales.commercial.indexed_jobs import same_company_name
from sales.providers import canonical


def resolutions(rows, tasks):
    by_url=defaultdict(list)
    for row in rows:
        b=row['body']
        by_url[(row['campaign_id'],row['flow'],canonical(b.get('url') or ''))].append(row)
    children=defaultdict(set);records={r['id']:r for r in rows};incomplete=set()

    def observed(b):
        return (b.get('decision_engine')=='ai_first_1' and b.get('original')
                and b.get('validation_status')=='ACCEPTED' and not b.get('verification_hold')
                and not b.get('technical_error') and b.get('relationship') in ('BUSINESS_SIGNAL','PROACTIVE_NEED'))

    for task in tasks:
        p=task['payload'];parent=p.get('research_parent') or {}
        if not parent.get('url') or not parent.get('link_url') or not p.get('url'):continue
        if canonical(parent['link_url'])!=canonical(p['url']):continue
        # Limit projection to a followed link on the same website. No transfer
        # from an editorial publisher, directory or another company/domain.
        if not domain(p['url']) or domain(p['url'])!=domain(parent['url']):continue
        prefix=(task['campaign_id'],task['strategy'])
        for a in by_url[(*prefix,canonical(parent['url']))]:
            ab=a['body']
            if not observed(ab) or ab.get('decision')!='NEEDS_RESEARCH':continue
            if ab.get('research_action',{}).get('type')!='READ_LINK':continue
            linked=False
            for b in by_url[(*prefix,canonical(p['url']))]:
                bb=b['body']
                if b['id']==a['id'] or not observed(bb):continue
                if bb.get('checked_at','')<ab.get('checked_at',''):continue
                if not all(same_company_name(ab.get('entity_name'),name)
                           for name in (parent.get('entity_name'),bb.get('entity_name'))):continue
                children[a['id']].add(b['id'])
                linked=True
            if not linked:incomplete.add(a['id'])

    def end(rid,seen):
        if rid in seen or rid in incomplete or len(seen)>=12:return None
        b=records[rid]['body']
        if b.get('decision')=='NOT_INTERESTING' and b.get('research_action',{}).get('type')=='STOP':
            return [[rid]]
        if b.get('decision')!='NEEDS_RESEARCH' or not children[rid]:return None
        paths=[]
        for child in children[rid]:
            result=end(child,seen|{rid})
            if not result:return None
            paths.extend([[rid]+path for path in result])
        return paths

    out={}
    for rid in list(children):
        paths=end(rid,set())
        if not paths:continue
        terminal=sorted({p[-1] for p in paths})
        out[rid]={'status':'FOLLOWUP_CONCLUDED','basis':'explicit_same_site_followup_no_history_rewrite',
                  'label':'Approfondimento concluso senza opportunità dimostrata',
                  'paths':paths,'terminal_records':[
                      {'id':i,'url':records[i]['body']['url'],'reason':records[i]['body']['reason'],
                       'checked_at':records[i]['body'].get('checked_at')} for i in terminal],
                  'limit':'La conclusione riguarda questo percorso di ricerca; non certifica il funzionamento del sito né esclude altri bisogni.'}
    return out


def read(store, rows):
    with store.connect() as c:
        tasks=[{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute(
            "SELECT campaign_id,strategy,payload FROM research_tasks WHERE kind='candidate' AND json_extract(payload,'$.research_parent.url') IS NOT NULL")]
    return resolutions(rows,tasks)
