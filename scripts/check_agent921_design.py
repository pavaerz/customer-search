"""Real local browser -> typed design observation, without external requests."""
import json
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'tests')]
from test_commercial_browser3b import Browser3BTests
from sales.agent6.website_audit import audit
from sales.db import now


def main():
    fixture=Browser3BTests();fixture.setUp()
    try:
        body='<main><h1>Servizi industriali</h1><p>'+('Produciamo componenti per impianti industriali su misura. '*6)+'</p></main>'
        css='<style>main h1,main p{font-size:16px;font-weight:400;color:#123456}</style>'
        result=fixture.render(css,body=body,limits={'browser_total_seconds':15,'browser_audit_level':'STANDARD'})
        fixture.assert_closed(result)
        assert result['completed'],result.get('limits')
        page={'url':fixture.origin+'/','status':200,'html':css+body,'checked_at':now()}
        report=audit([page],result)
        observations=[o for o in report['observations'] if o.get('observation_type')=='DESIGN_ASSESSMENT']
        assert {o['evidence']['value']['viewport'] for o in observations}=={390,1366}
        assert all(o['evidence']['method']=='browser_computed_styles' for o in observations)
        assert report['website_opportunity']=='LIMITED_OR_UNPROVEN'
        print(json.dumps({'scope':'synthetic_local_design_real_computed_styles','viewports':[390,1366],
            'typed_design_observations':len(observations),'automatic_full_project':False,
            'external_calls':0,'production_writes':0,'processes_closed':result['resources_closed']}))
    finally:fixture.doCleanups()


if __name__=='__main__':main()
