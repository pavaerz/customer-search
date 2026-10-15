"""Re-evaluate captured company pages; only the local model may use HTTP."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sales.db import Store,now
from sales.providers import canonical
from sales.research_analysis import ResearchWeb,inspect_candidate


def run():
    folder=ROOT/'data/pilot50-next/implicit'
    original=json.loads((folder/'deep-report.json').read_text())
    pages=json.loads((folder/'deep-pages.json').read_text())
    captured={canonical(key):value for key,value in pages.items()}
    captured.update({canonical(value['url']):value for value in pages.values()})
    def frozen(web,url,refresh=False):
        key=canonical(url)
        if key not in captured:raise ValueError('Pagina fuori dal campione congelato: '+key)
        return captured[key]
    report={'checked_at':now(),'scope':'Development recheck of two companies; not independent precision evaluation.',
            'search_requests':0,'web_requests':0,'companies':[]}
    with patch.object(ResearchWeb,'get',frozen):
        for before in original['companies']:
            payload={'url':before['url'],'strategy':'companies','filters':{'groups':['direct'],'projects':['website']}}
            result=inspect_candidate(Store(folder/'sample.sqlite3'),payload,lambda:None,lambda m:print(m,flush=True))
            report['companies'].append({'url':payload['url'],'before_status':before.get('result',{}).get('assessment',{}).get('status'),
                                        'before_region':before.get('result',{}).get('identity',{}).get('region'),'result':result})
            (folder/'recheck.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps({'url':payload['url'],'region':result['identity']['region'],
                              'status':result['assessment']['status'],'missing':result['assessment']['missing']},ensure_ascii=False),flush=True)
    report['finished_at']=now()
    (folder/'recheck.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':run()
