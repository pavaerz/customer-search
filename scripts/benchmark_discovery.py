"""Reproducible offline A/B replay. Synthetic controls, NOT acquisition performance."""
import argparse
import importlib.util
import json
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store, now, digest
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.research_triage import triage
from sales.research_analysis import ResearchWeb
from sales import research_discovery as current
from sales.discovery_planner import Planner

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_BACKUP=ROOT/'data/backups/20261013T185956503392Z/project.zip'


def compare(archive):
    with tempfile.TemporaryDirectory() as tmp:
        source=Path(tmp)/'baseline.py'
        with zipfile.ZipFile(archive) as z:source.write_bytes(z.read('sales/research_discovery.py'))
        spec=importlib.util.spec_from_file_location('sales._baseline_discovery',source)
        baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
        results={}
        for label,module in [('before',baseline),('after',current)]:
            store=Store(Path(tmp)/(label+'.db'));store.init();rs=ResearchStore(store);campaign=rs.create({'regions':['Veneto']});f=Funnel(rs)
            module.seed_campaign(rs,campaign)
            with store.connect() as c:
                initial=c.execute('SELECT count(*) FROM discovery_frontier').fetchone()[0]
                # Replay the same three commercial goals in isolation from other branches.
                c.execute('DELETE FROM research_tasks');c.execute('DELETE FROM discovery_frontier');c.execute('DELETE FROM discovery_branches');c.execute('DELETE FROM discovery_queries')
            checked={};calls=[];started=time.monotonic()
            def result(url,**kwargs):
                from urllib.parse import urlsplit,parse_qs
                params=parse_qs(urlsplit(url).query);q=params['q'][0];page=int(params.get('pageno',['1'])[0]);calls.append((q,page))
                # Each intent yields one new page. Noise must not earn endless pagination.
                intent='explicit' if 'fornitore' in q else 'process' if 'configuratore' in q else 'change'
                return {'results':[{'url':f'https://{intent}{page}.example/','title':q,'engines':['fixture']}],'unresponsive_engines':[]}
            def get(web,url,refresh=False):
                intent='explicit' if 'explicit' in url else 'process' if 'process' in url else 'change'
                text={'explicit':'Cerchiamo un fornitore per realizzare un nuovo sito aziendale completo.', 'process':'Il catalogo configurabile contiene molteplici varianti. Gli ordini multilistino richiedono integrazione.', 'change':'Consigli per leggere un quotidiano e scegliere la carta da stampa.'}[intent]
                host=url.split('/')[2]
                vat=f'{int(digest(host)[:10],16)%100000000000:011d}'
                return {'url':url,'status':200,'checked_at':now(),'html':f'<title>Impresa {host} Srl</title><main><p>{text}</p></main><footer><p>Impresa {host} Srl</p><p>Via Roma 2, 35100 Padova (PD)</p><p>P. IVA {vat}</p><a href="mailto:info@{host}">info@{host}</a></footer>'}
            for strategy,q in [('explicit','fornitore nuovo sito Veneto'),('process','configuratore Veneto'),('change','nuova linea Veneto')]:
                payload={'query':q,'page':1,'period':'year','region':'Veneto'}
                if label=='after':
                    planner=Planner(rs);fp=planner.offer_query(campaign,strategy,payload)
                    with store.connect() as c:c.execute('INSERT INTO discovery_branches(campaign_id,strategy,region,cursor,last_query) VALUES (?,?,?,?,?)',(campaign['id'],strategy,'Veneto',0,fp))
                else:f.offer(campaign['id'],'search',strategy,payload)
            # Equal network allowance: 9 queries, 3 intents, round-robin. Qualification unchanged.
            with patch('sales.discovery_control.search_capabilities',return_value={'paging':True,'time_range':True,'engines':['fixture']}),patch.dict('os.environ',{'SEARXNG_URL':'http://127.0.0.1:8888'}),patch.object(module,'api_json',side_effect=result),patch.object(ResearchWeb,'get',get):
                for round_number in range(3):
                    with store.connect() as c:tasks=[dict(r) for r in c.execute("SELECT * FROM discovery_frontier WHERE kind='search' AND state='pending' ORDER BY id LIMIT 3")]
                    for task in tasks:
                        task['payload']=json.loads(task['payload']);module._last_search=0
                        module.search(rs,campaign,task,lambda:None)
                        with store.connect() as c:c.execute("UPDATE discovery_frontier SET state='assigned' WHERE id=?",(task['id'],))
                    with store.connect() as c:jobs=[dict(r) for r in c.execute("SELECT * FROM discovery_frontier WHERE kind='candidate' AND state='pending'")]
                    for job in jobs:
                        payload=json.loads(job['payload']);r=triage(store,payload,lambda:None);checked[payload['url']]=r
                        f.transition(campaign,payload,r['state'],r['reason'],r['details'])
                        with store.connect() as c:c.execute("UPDATE discovery_frontier SET state='assigned' WHERE id=?",(job['id'],))
                    if label=='after':Planner(rs).tick(campaign)
            pertinent=[r for r in checked.values() if r['state']=='promising']
            correct=sum(r['details'].get('identity',{}).get('identity_status')=='verified' and r['details']['identity'].get('website')==url and r['details']['identity'].get('name')=='Impresa '+url.split('/')[2]+' Srl' for url,r in checked.items() if r['state']=='promising')
            results[label]={'initial_frontier':initial,'queries':len(calls),'original_pages':len(checked),'pertinent_companies':len(pertinent),'correct_identifications':correct,'identification_precision':correct/len(pertinent) if pertinent else None,'promising':len(pertinent),'qualified':None,'deep_verification_failure_rate':None,'preliminary_failure_rate':sum(r['state']=='unverifiable' for r in checked.values())/len(checked) if checked else None,'elapsed_seconds':round(time.monotonic()-started,3),'seconds_per_promising':round((time.monotonic()-started)/len(pertinent),4) if pertinent else None,'irrelevant_pagination':sum(q=='nuova linea Veneto' and p>1 for q,p in calls),'query_trace':calls}
        return {'protocol':'Deterministic synthetic replay, same 3 intents and max 9 queries. Original HTML triage; no model/qualification execution. Qualified and deep failures remain null because deep qualification was not run. Timing is local replay CPU/SQLite, not live network speed.', 'baseline_code_sha256':digest(source.read_text()),'results':results,'limitations':['Small synthetic sample, no evidence of improved market recall or conversion.','This replay isolates pagination waste and initial queue size. A separate live report describes available sources.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,default=DEFAULT_BACKUP);args=p.parse_args()
    report=compare(args.baseline);Path('docs/discovery-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
