"""Replay demonstrated identification errors on the same original pages."""
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,digest,now
from sales.research_analysis import ResearchWeb,LocalResearcher
from sales.research_triage import triage

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/company-screening/2026-10-14T10-40-33.965496+00-00'
HOSTS=('fullserviceimpianti.com','bertolino.com','radarsrl.it')


def run():
    original=json.loads((SOURCE/'report.json').read_text())
    store=Store(SOURCE/'pilot.sqlite3');cases=[];manifest={}
    def read(web,url,refresh=False):
        path=SOURCE/'pages'/(digest(url)+'.json')
        manifest[str(path.relative_to(SOURCE))]=hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text())
    for case in original['cases']:
        if not any(host in case['url'] for host in HOSTS):continue
        payload={'url':case['url'],'strategy':'companies','company_stage':'identify',
                 'filters':{'target':'b2b','regions':['Veneto','Lombardia','Piemonte','Toscana'],
                            'projects':['website'],'groups':['direct']}}
        with patch.object(ResearchWeb,'get',read),patch.object(LocalResearcher,'call',side_effect=AssertionError('No model in frozen screening')):
            after=triage(store,payload,lambda:None)
        def summary(result):
            d=result['details'];i=d.get('identity',{})
            return {'state':result['state'],'reason':result['reason'],'company_ready':d.get('company_ready',False),
                    'identity':{k:i.get(k) for k in ('name','location','region','legal_id','identity_status')},
                    'limits':d.get('limits',[])}
        cases.append({'url':case['url'],'before':summary(case['result']),'after':summary(after)})
    assert len(cases)==3
    assert all(c['after']['company_ready'] for c in cases)
    result={'checked_at':now(),'source':str(SOURCE.relative_to(ROOT)),
            'split':'Development regression on original captured pages, not independent qualification precision.',
            'search_requests':0,'web_requests':0,'model_requests':0,'sha256':manifest,'cases':cases}
    (ROOT/'docs/regression50-identity-formats.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(cases,ensure_ascii=False,indent=2))


if __name__=='__main__':run()
