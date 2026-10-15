"""Re-evaluate preserved original HTML, without network or rewriting the measured trial."""
import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store
from sales.research_analysis import ResearchWeb
from sales.research_triage import triage


def run(run_id, output):
    store=Store()
    with store.connect() as c:row=c.execute('SELECT report,state FROM search_trials WHERE id=?',(run_id,)).fetchone()
    if not row:raise ValueError('Prova non trovata')
    if row['state']=='running':raise ValueError('Attendere o fermare la prova prima della revisione')
    report=json.loads(row['report']);source=store.path.parent/'search-trials'/f'trial-{run_id}.sqlite3'
    with tempfile.TemporaryDirectory() as tmp:
        copy=Path(tmp)/'recheck.sqlite3'
        with sqlite3.connect(source) as original,sqlite3.connect(copy) as target:original.backup(target)
        isolated=Store(copy)
        with isolated.connect() as c:pages={r['key'][5:]:json.loads(r['body']) for r in c.execute("SELECT key,body FROM cache WHERE key LIKE 'page:%'")}
        def read(url,*args,**kwargs):
            if url not in pages:raise ValueError('Fonte HTML non conservata: nessuna nuova richiesta eseguita')
            return pages[url]
        results=[]
        with patch.object(ResearchWeb,'get',side_effect=read):
            for candidate in report['candidates']:
                before=candidate.get('triage',{})
                try:
                    after=triage(isolated,{**candidate,'filters':{'regions':['Veneto']}},lambda:None)
                    identity=after.get('details',{}).get('identity',{})
                    results.append({'url':candidate['url'],'before':before.get('state'),'after':after['state'],'reason':after['reason'],'publisher':after.get('details',{}).get('publisher',False),'identity_status':identity.get('identity_status'),'location':identity.get('location')})
                except Exception as exc:results.append({'url':candidate['url'],'before':before.get('state'),'after':'unverifiable','reason':str(exc)})
    value={'source_run':run_id,'method':'Regressione offline delle pagine originali conservate; nessuna query, modello o nuova qualifica. Il report originale non è modificato.',
           'before_promising':sum(x['before']=='promising' for x in results),'after_promising':sum(x['after']=='promising' for x in results),'results':results}
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in value.items() if k!='results'},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=int,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    run(args.run,args.output)
