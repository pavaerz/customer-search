"""Owned worker for grant discovery, independent of customer campaigns and CRM."""
import argparse,json
from pathlib import Path
from urllib.parse import urljoin
from .db import Store,encode,now
from .grants import official,assessment
from .grant_documents import GrantWeb as ResearchWeb,collect
from .grant_eligibility import GrantAnalyst,explicit_exclusions,evaluate
from .providers import canonical
from .extract import parse_page
import re


def run(path,cid,generation):
    store=Store(Path(path))
    def active(c):return c.execute("SELECT * FROM grant_runs WHERE id=? AND generation=? AND state='running'",(cid,generation)).fetchone()
    def check():
        with store.connect() as c:
            if not active(c):raise InterruptedError('Ricerca fermata')
    web=ResearchWeb(store,check)
    try:
        with store.connect() as c:
            row=active(c)
            if not row:return
            profile=json.loads(row['profile'])
        while True:
            check()
            with store.connect() as c:
                task=c.execute("SELECT * FROM grant_tasks WHERE run_id=? AND state='pending' ORDER BY id LIMIT 1",(cid,)).fetchone()
                if not task:
                    failed=c.execute("SELECT count(*) FROM grant_tasks WHERE run_id=? AND state='failed'",(cid,)).fetchone()[0]
                    c.execute("UPDATE grant_runs SET state=?,message=?,updated_at=? WHERE id=? AND generation=? AND state='running'",('partial' if failed else 'completed','Fonti disponibili esaminate. Alcune pagine non sono verificabili.' if failed else 'Fonti disponibili esaminate. I risultati mostrano il confronto con il tuo profilo.',now(),cid,generation));return
                c.execute("UPDATE grant_tasks SET state='working' WHERE id=?",(task['id'],))
                c.execute('UPDATE grant_runs SET message=?,updated_at=? WHERE id=?',('Lettura della fonte ufficiale · '+task['url'],now(),cid))
            try:
                if not official(task['url']):raise ValueError('Dominio fuori dal catalogo di fonti ufficiali')
                page=web.get(task['url'],refresh=True);check()
                if not official(page['url']):raise ValueError('Redirect verso un dominio non presente nel catalogo ufficiale')
                if page['status']!=200:raise ValueError('Fonte HTTP '+str(page['status']))
                parsed=parse_page(page)
                if re.search(r'effettua il login|accedi per leggere',parsed['text'][:2000],re.I):raise ValueError('Contenuto riservato: verifica manuale necessaria')
                if task['kind']=='index':
                    urls=[]
                    for link in parsed['doc'].links:
                        if link.get('navigation'):continue
                        try:url=canonical(urljoin(page['url'],link['url']))
                        except ValueError:continue
                        if not official(url) or url in (page['url'],task['url']):continue
                        if re.search(r'bando|incentiv|agevolaz|contribut|finanziament|smart.start|autoimpiego',link['text']+' '+url,re.I) and not re.search(r'privacy|cookie|login|newsletter',url,re.I):urls.append(url)
                    with store.connect() as c:
                        c.execute('BEGIN IMMEDIATE')
                        if not active(c):raise InterruptedError()
                        for url in dict.fromkeys(urls):c.execute("INSERT OR IGNORE INTO grant_tasks(run_id,url,kind) VALUES (?,?,'grant')",(cid,url))
                else:
                    a=assessment(page,profile)
                    if a:
                        with store.connect() as c:c.execute("UPDATE grant_runs SET message=? WHERE id=? AND generation=? AND state='running'",('Lettura requisiti e allegati · '+a['title'],cid,generation))
                        documents,limitations=collect(web,page,check)
                        rules=explicit_exclusions(documents)
                        bundle={'documents':documents,'rules':rules,'complete':False,'limitations':limitations}
                        initial=evaluate(bundle,profile)
                        if initial['status']!='excluded':
                            with store.connect() as c:c.execute("UPDATE grant_runs SET message=? WHERE id=? AND generation=? AND state='running'",('Confronto dei requisiti · '+a['title'],cid,generation))
                            try:
                                analysis=GrantAnalyst(store,check).extract(documents)
                                bundle['rules']+=analysis['rules'];bundle['complete']=analysis['complete'];bundle['limitations']+=analysis['limitations']
                            except InterruptedError:raise
                            except Exception as exc:bundle['limitations'].append('Analisi automatica interrotta: '+str(exc)[:200])
                        a['eligibility_bundle']=bundle
                        a['eligibility']=evaluate(bundle,profile);a['status']=a['eligibility']['status'];a['reason']=a['eligibility']['reason']
                        with store.connect() as c:
                            c.execute('BEGIN IMMEDIATE')
                            if not active(c):raise InterruptedError()
                            c.execute('INSERT OR IGNORE INTO grant_items(run_id,url,title,body,checked_at) VALUES (?,?,?,?,?)',(cid,page['url'],a['title'],encode(a),page['checked_at']))
                with store.connect() as c:c.execute("UPDATE grant_tasks SET state='done' WHERE id=?",(task['id'],))
            except InterruptedError:raise
            except Exception as exc:
                with store.connect() as c:c.execute("UPDATE grant_tasks SET state='failed',error=? WHERE id=?",(str(exc)[:700],task['id']))
    except InterruptedError:pass
    except Exception as exc:
        with store.connect() as c:c.execute("UPDATE grant_runs SET state='error',message=?,updated_at=? WHERE id=? AND generation=? AND state='running'",('Ricerca interrotta: '+str(exc)[:500],now(),cid,generation))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db');p.add_argument('--run',type=int);p.add_argument('--generation');a=p.parse_args();run(a.db,a.run,a.generation)
