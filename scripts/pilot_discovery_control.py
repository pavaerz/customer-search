"""Small read-only live pilot in a separate database; never alters the CRM."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store, now
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.discovery_control import measure, diagnostics
from sales.discovery_planner import Planner
from sales.research_discovery import search, inspect_source
from sales.research_triage import triage


def run():
    target=Path('data/discovery-pilots')/now().replace(':','-')
    target.mkdir(parents=True,mode=0o700)
    store=Store(target/'pilot.sqlite3');store.init();rs=ResearchStore(store);campaign=rs.create({'regions':['Veneto']});f=Funnel(rs);planner=Planner(rs)
    report={'started_at':now(),'database':str(store.path),'queries':[],'sources':[],'candidates':[],'scope':'Live discovery and preliminary original-page checks only; no deep qualification or outreach.'}
    started=time.monotonic()
    for strategy,query in [('change','"nuova linea" "prodotti" Veneto'),('explicit','"cerchiamo" "nuovo sito" Veneto'),('process','aziende Veneto configuratore preventivi')]:
        payload={'query':query,'page':1,'period':'year','region':'Veneto'}
        fp=planner.offer_query(campaign,strategy,payload);payload['query_key']=fp
        task={'kind':'search','strategy':strategy,'payload':payload}
        try:
            with measure(rs,campaign,task):r=search(rs,campaign,task,lambda:None)
            report['queries'].append({'query':query,**r})
        except Exception as exc:report['queries'].append({'query':query,'error':str(exc)})
        print(json.dumps(report['queries'][-1],ensure_ascii=False),flush=True)
    for url in ('https://www.confartigianatovicenza.it/feed/','https://cnaveneto.it/feed/','https://www.venetoeconomia.it/feed/','https://cnaveneto.it/startup/','https://www.confindustriavenest.it/stampa-e-media/comunicati-stampa'):
        task={'kind':'source','strategy':'sources','payload':{'url':url,'kind':'rss' if url.endswith('/feed/') else 'html','region':'Veneto'}}
        try:
            with measure(rs,campaign,task):inspect_source(rs,campaign,task,lambda:None)
            report['sources'].append({'url':url,'status':'read'})
        except Exception as exc:report['sources'].append({'url':url,'error':str(exc)})
        print(json.dumps(report['sources'][-1],ensure_ascii=False),flush=True)
    with store.connect() as c:jobs=[dict(r) for r in c.execute("SELECT * FROM discovery_frontier WHERE kind='candidate' ORDER BY id LIMIT 12")]
    for row in jobs:
        payload=json.loads(row['payload']);task={**row,'payload':payload};t=time.monotonic()
        try:
            with measure(rs,campaign,task):r=triage(store,payload,lambda:None)
            f.transition(campaign,payload,r['state'],r['reason'],r['details'])
            identity=r['details'].get('identity',{})
            result={'url':payload['url'],'state':r['state'],'reason':r['reason'],'identity':{k:identity.get(k) for k in ('name','region','identity_status')},'publisher':r['details'].get('publisher'),'excerpt':r['details'].get('document',{}).get('research_text','')[:1600]}
        except Exception as exc:
            f.transition(campaign,payload,'unverifiable',str(exc));result={'url':payload['url'],'state':'unverifiable','reason':str(exc)}
        result['seconds']=round(time.monotonic()-t,2);report['candidates'].append(result)
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({k:v for k,v in result.items() if k!='excerpt'},ensure_ascii=False),flush=True)
    report['diagnostics']=diagnostics(rs,campaign['id']);report['elapsed_seconds']=round(time.monotonic()-started,2)
    report['qualified']=None;report['qualification_note']='Not measured: this pilot stops before expensive deep research; no shortlist or client acquisition claimed.'
    rs.stop(campaign['id']);rs.paused(campaign['id'])
    (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    Path('docs/discovery-live-pilot.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(str(target/'report.json'),flush=True)


if __name__=='__main__':run()
