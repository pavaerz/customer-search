"""Replay saved Serper results only. No HTTP, model calls or production writes."""
import argparse
import collections
import json
from pathlib import Path
import sqlite3
import sys
import types
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.prospect_scope import acquisition_exclusion
from sales.discovery_planner import query_key
from sales.research_analysis import document
from sales.discovery_relevance import subject_exclusion


def run(db, backup):
    with zipfile.ZipFile(backup/'project.zip') as z:
        old=types.ModuleType('sales.previous_scope');old.__package__='sales'
        exec(compile(z.read('sales/prospect_scope.py'),'previous_scope','exec'),old.__dict__)
    c=sqlite3.connect('file:'+str(db.resolve())+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    tasks=[dict(r) for r in c.execute("SELECT * FROM research_tasks WHERE campaign_id=4 AND kind='search'")]
    comparisons=[];missing=0
    for task in tasks:
        p=json.loads(task['payload']);key='serper:search:v2:'+query_key(p)
        row=c.execute('SELECT body FROM cache WHERE key=?',(key,)).fetchone()
        if not row:missing+=1;continue
        for item in json.loads(row[0])['results']:
            before=old.acquisition_exclusion(item,p);after=acquisition_exclusion(item,p)
            comparisons.append({'query':p['query'],'url':item['url'],'title':item.get('title'),
                'subject':p.get('subject'),'before':before,'after':after})
    errors=[dict(r) for r in c.execute("SELECT message,url,details FROM research_events WHERE campaign_id=4 AND kind='error'")]
    counts=collections.Counter('robots_unverifiable' if 'robots.txt non verificabile' in r['message'] else 'tls_certificate' if 'CERTIFICATE_VERIFY_FAILED' in r['message'] else 'timeout' if 'timed out' in r['message'] else 'other' for r in errors)
    scoped=[];subjects=[];seen=set()
    for task in tasks:
        p=json.loads(task['payload'])
        if not p.get('subject') or p.get('company_host'):continue
        reason=subject_exclusion(p['subject'],p.get('source_documents',[]))
        subjects.append({'subject':p['subject'],'query':p['query'],'excluded_reason':reason})
        for doc in p.get('source_documents',[]):
            if doc['url'] in seen:continue
            seen.add(doc['url']);row=c.execute('SELECT body FROM cache WHERE key=?',('page:'+doc['url'],)).fetchone()
            if not row:continue
            new=document(json.loads(row[0]));scoped.append({'url':doc['url'],'before_scope':doc.get('body_scope'),
                'after_scope':new.get('body_scope'),'before_chars':len(doc.get('research_text',doc['text'])),
                'after_chars':len(new['research_text'])})
    result={'campaign':4,'method':'Replay offline di risultati Serper e pagine già salvati; nessuna ricerca nuova.',
        'queries':len(tasks),'cached_queries':len(tasks)-missing,'missing_cached_queries':missing,
        'search_results':len(comparisons),'before_accepted':sum(not r['before'] for r in comparisons),
        'after_accepted':sum(not r['after'] for r in comparisons),
        'newly_filtered':[r for r in comparisons if not r['before'] and r['after']],
        'newly_allowed':[r for r in comparisons if r['before'] and not r['after']],
        'errors_before':dict(counts),'errors_unique_urls':len({r['url'] for r in errors}),
        'candidate_states':dict(c.execute('SELECT state,count(*) FROM discovery_candidates WHERE campaign_id=4 GROUP BY state').fetchall()),
        'historically_promising':c.execute("SELECT count(DISTINCT candidate_id) FROM discovery_transitions t JOIN discovery_candidates d ON d.id=t.candidate_id WHERE d.campaign_id=4 AND t.state='promising'").fetchone()[0],
        'timings':[dict(r) for r in c.execute('SELECT kind,count(*) operations,round(sum(seconds),1) seconds FROM discovery_operations WHERE campaign_id=4 GROUP BY kind')],
        'subject_resolution':subjects,'article_scoping':scoped,
        'limits':'Il replay verifica instradamento e letture evitabili, non misura nuovi clienti, disponibilità attuale delle fonti o accelerazione di una campagna completa.'}
    c.close();return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=Path('data/sales.sqlite3'));p.add_argument('--backup',type=Path,required=True);p.add_argument('--output',type=Path,default=Path('docs/campaign4-corrections.json'));a=p.parse_args()
    report=run(a.db,a.backup);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('newly_filtered','newly_allowed','subject_resolution','article_scoping')},ensure_ascii=False))
