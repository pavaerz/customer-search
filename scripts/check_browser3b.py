"""Offline local Chromium benchmark; run with PYTHONPATH=.:tests + offline guard."""
import json
from pathlib import Path
from test_commercial_browser3b import Browser3BTests


def main():
    cases=[]
    scenarios=[
        ('many_resources', ''.join('<link rel="stylesheet" href="/asset-%s.css">'%i for i in range(12))+
         ''.join('<img src="/asset-%s.svg" width="40" height="40">'%i for i in range(12))+
         '<script async src="/async-content.js"></script>',
         {'browser_resource_timeout_ms':1000,'browser_render_timeout_ms':1800}),
        ('slow_font', '<style>@font-face{font-family:slow;src:url(/font-slow.woff2)}body{font-family:slow}</style>',
         {'browser_resource_timeout_ms':1500,'browser_render_timeout_ms':300}),
    ]
    for name,html,limits in scenarios:
        fixture=Browser3BTests();fixture.setUp()
        try:
            result=fixture.render(html,limits=limits);fixture.assert_closed(result)
            if name=='many_resources':assert result['completed'],result
            else:assert not result['completed'] and result['pages'] and not result['findings'],result
            cases.append({'scenario':name,'result':result,'server_peak':fixture.server.peak,
                          'fixture_requests':len(fixture.server.seen)})
        finally:fixture.doCleanups()
    output={'scope':'SYNTHETIC_LOCAL_CHROMIUM','external_requests':0,'real_campaigns':0,
            'real_sites_retested':False,'cases':cases}
    path=Path('implementation-report/phase-3b-browser-metrics.json');path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{'scenario':c['scenario'],'completed':c['result']['completed'],
        'dom_pages':len(c['result']['pages']),'early_checkpoints':len(c['result']['dom_checkpoints']),
        'first_dom_ms':c['result']['dom_checkpoints'][0]['elapsed_ms'],'elapsed_ms':c['result']['elapsed_ms'],
        'peak_reads':c['result']['peak_resource_reads'],'resources_closed':c['result']['resources_closed']} for c in cases],ensure_ascii=False))


if __name__=='__main__':main()
