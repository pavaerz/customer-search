"""Summarize the captured development pilot without new API calls or estimates."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sales.db import now
from sales.providers import blocked,canonical


def run():
    folder=ROOT/'data/pilot50-next/implicit'
    before=json.loads((folder/'adapted-search.json').read_text())
    after=json.loads((folder/'search-access-comparison.json').read_text())
    paired=[]
    for current in after:
        previous=next(q for q in before if q['query']==current['original_query'])
        pair={'query':current['original_query'],'before':{},'after':{}}
        for label,q in (('before',previous),('after',current)):
            pair[label]={'returned':len(q['results']),'excluded_by_access_policy':sum(blocked(r['url']) for r in q['results']),
                         'urls':[r['url'] for r in q['results']]}
        paired.append(pair)
    final=json.loads((folder/'recheck.json').read_text())
    if not final.get('finished_at'):raise RuntimeError('Recheck still running; no final metrics')
    companies=[]
    for r in final['companies']:
        identity=r['result']['identity'];a=r['result']['assessment']
        companies.append({'name':identity['name'],'website':identity['website'],'region':identity['region'],
                          'status':a['status'],'why':a['why'],'reasons':a['reasons'],
                          'signals':len(a['signals']),'unmet_requirements':a.get('missing',[]),'analysis_status':a.get('analysis_status'),
                          'solution_urls':a.get('solution_urls',[]),'coverage':a.get('coverage'),
                          'budget':a.get('budget'),'need_inference':a.get('need_inference')})
    search_files=[folder.parent/'implicit-search.json',folder/'consumer-search.json',folder/'adapted-search.json',folder/'search-access-comparison.json']
    query_records=[]
    for p in search_files:
        data=json.loads(p.read_text());query_records+=data if isinstance(data,list) else [data]
    captures=[folder/'pages.json',folder/'adapted-pages.json',folder/'ag-brand-pages.json',folder/'deep-pages.json']
    urls=set()
    for p in captures:
        data=json.loads(p.read_text())
        pages=list(data.values()) if isinstance(data,dict) else [r['page'] for r in data if r.get('page')]
        urls.update(canonical(p['url']) for p in pages)
    report={'checked_at':now(),'split':'development','reviewer':'Assistant; not independent human review',
            'queries':len(query_records),'serper_requests':sum(q.get('cached') is False for q in query_records),
            'original_pages_captured':len(urls),'search_comparison':paired,'companies':companies,
            'qualified':sum(c['status']=='qualified' for c in companies),'precision_at_20':None,
            'commercial_effectiveness_established':False,
            'limitations':['Two company dossiers are not a sufficient independent evaluation sample.',
                          'Removing inaccessible results does not make the remaining URLs commercially relevant.',
                          'Inference promotion is covered by controlled tests; no real positive inference case established by this pilot.',
                          'No emails sent, no production CRM promotion, no additional paid service.'],
            'capture_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in captures+search_files}}
    (ROOT/'docs/pilot50-inference.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:report[k] for k in ('queries','serper_requests','original_pages_captured','qualified','precision_at_20')}))


if __name__=='__main__':run()
