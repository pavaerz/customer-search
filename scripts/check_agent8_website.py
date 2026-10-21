"""Real offline Chromium measurements consumed by Website Opportunity Audit.

Run with PYTHONPATH=.:tests. Local fixtures only; no commercial claims or calls.
"""
import json
from sales.db import now
from sales.agent6.website_audit import audit
from test_commercial_browser3b import Browser3BTests,TEXT


def main():
    cases=[]
    for kind in ('usable','overflow','incomplete'):
        fixture=Browser3BTests();fixture.setUp()
        try:
            body=TEXT if kind=='usable' else '<main>'+''.join('<p style="width:1900px">'+('Informazioni sui prodotti e sui servizi industriali. '*5)+'</p>' for _ in range(3))+'</main>'
            extra='<link rel="stylesheet" href="/persistent-css.css">' if kind=='incomplete' else ''
            result=fixture.render(extra,body=body,limits={'browser_resource_timeout_ms':1500 if kind=='incomplete' else 500,
                'browser_render_timeout_ms':300 if kind=='incomplete' else 1200,'browser_total_seconds':10,
                'browser_audit_level':'STANDARD'})
            fixture.assert_closed(result)
            page={'url':fixture.origin+'/','status':200,'checked_at':now(),
                'html':'<!doctype html><html><body>'+body+extra+'</body></html>'}
            report=audit([page],result)
            responsive=next(o for o in report['observations'] if o['code']=='responsive')
            defects=[o for o in report['observations'] if o['evidence']['method']=='browser_two_measurements']
            if kind=='usable':
                assert result['completed'],result.get('limits')
                assert responsive['status']=='PASS' and not defects
            elif kind=='overflow':
                assert result['completed'],result.get('limits')
                assert responsive['status']=='ISSUE'
                assert any(o['code']=='mobile_content' and o['certainty']=='MEASURED' for o in defects)
                assert all(o['evidence']['value']['measurements']['clipped']>=2 for o in defects if o['code'].endswith('_content'))
                assert report['website_opportunity']=='LIMITED_OR_UNPROVEN','CSS alone must not become a rebuild'
            else:
                assert not result['completed'] and result['pages']
                assert responsive['status']=='UNKNOWN' and not defects
            assert next(o for o in report['observations'] if o['code']=='performance')['status']=='UNKNOWN'
            cases.append({'scenario':kind,'completed':result['completed'],'responsive':responsive['status'],
                'measured_defects':[o['code'] for o in defects],'elapsed_ms':result['elapsed_ms'],
                'processes_closed':result['resources_closed']})
        finally:fixture.doCleanups()
    print(json.dumps({'scope':'synthetic_local_sources_real_browser_measurements','cases':cases,
        'external_calls':0,'production_writes':0,'commercial_opportunities':0}))


if __name__=='__main__':main()
