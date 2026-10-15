"""Recheck demonstrated target-routing failures using frozen original responses."""
import json,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,digest,now
from sales.research_analysis import ResearchWeb,LocalResearcher
from sales.research_triage import triage

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/cycle50/2026-10-14T10-15-46.907683+00-00'
URLS=[
    'https://hile.it/impianti-industriali/',
    'https://sipasolutions.com/it/chi-siamo',
    'https://www.veneziatoday.it/economia/sigit-nuova-proprietaria-speedline-via-rilancio.html',
    'https://www.padovanews.it/2026/09/22/nanni-fresenius-kabi-nuova-linea-raddoppia-velocita-produzione/',
]

def run():
    report=json.loads((SOURCE/'report.json').read_text());store=Store(SOURCE/'pilot.sqlite3');out=[]
    def get(web,url,refresh=False):return json.loads((SOURCE/'pages'/(digest(url)+'.json')).read_text())
    for url in URLS:
        with store.connect() as c:
            before=dict(c.execute('SELECT * FROM discovery_candidates WHERE campaign_id=? AND url=?',(report['campaign_id'],url)).fetchone())
            payload=json.loads(c.execute("SELECT payload FROM research_tasks WHERE campaign_id=? AND kind='candidate' AND json_extract(payload,'$.url')=? ORDER BY id LIMIT 1",(report['campaign_id'],url)).fetchone()[0])
        details=json.loads(before['details'])
        with patch.object(ResearchWeb,'get',get),patch.object(LocalResearcher,'call',side_effect=AssertionError('No model in this replay')):
            result=triage(store,payload,lambda:None)
        out.append({'url':url,'before':{'state':before['state'],'identity':details.get('identity'),
            'publisher':details.get('publisher',False),'company_ready':details.get('company_ready',False),'assessment_id':before['assessment_id']},
            'after':{'state':result['state'],'reason':result['reason'],'identity':result['details'].get('identity'),
                'publisher':result['details'].get('publisher',False),'company_ready':result['details'].get('company_ready',False),
                'resolve':result.get('resolve',False),'source':result.get('source',False)}})
    assert out[0]['after']['company_ready'] and out[0]['after']['identity']['region']=='Veneto'
    assert out[1]['after']['state']=='rejected' and 'S.p.A.' in out[1]['after']['reason']
    assert all(r['after']['publisher'] and r['after']['resolve'] and not r['after']['company_ready'] for r in out[2:])
    result={'checked_at':now(),'source':str(SOURCE.relative_to(ROOT)),'split':'development regressions, not independent precision',
            'search_requests':0,'web_requests':0,'model_requests':0,'cases':out}
    (ROOT/'docs/regression50-target-routing.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps([{'url':r['url'],**{k:v for k,v in r['after'].items() if k!='identity'}} for r in out],ensure_ascii=False,indent=2))

if __name__=='__main__':run()
