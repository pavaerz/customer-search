"""Independent coverage ledger over saved measurements; no extra acquisitions."""


def controls(observations, browser, pages):
    out=[]
    for o in observations:
        e=o['evidence'];method=e.get('method','');unknown=o['status']=='UNKNOWN'
        level=4 if method.startswith('browser') else 1 if method=='http' else 2
        status='NOT_TESTED' if unknown else 'FAIL_OBSERVED' if o['status']=='ISSUE' else 'PASS' if o['status']=='PASS' else 'INCONCLUSIVE'
        if unknown and o['code']=='public_content':status='BLOCKED'
        out.append({'code':o['code'],'level':level,'status':status,'source':e['url'],
            'checked_at':e.get('checked_at'),'evidence':e,'error':e.get('value') if status=='BLOCKED' else None,
            'coverage':'sampled_page' if not unknown else 'not_measured',
            'reliability':'observed' if status in ('PASS','FAIL_OBSERVED') else 'unresolved'})
    for page in pages:
        url=page['url'];rows=[r for r in browser.get('pages',[]) if r.get('url')==url and r.get('scope')=='rendered']
        for width in (390,1366):
            measured=[r for r in rows if r.get('viewport')==width]
            complete=any(r.get('complete') for r in measured)
            out.append({'code':'rendering_'+str(width),'level':4,'status':'PASS' if complete else 'PARTIAL' if measured else 'NOT_TESTED',
                'source':url,'checked_at':page.get('checked_at'),'evidence':{'viewport':width,'measurements':[r.get('measurements',{}) for r in measured if r.get('complete')]},
                'error':None if complete else browser.get('failure_codes',[]),
                'coverage':'sampled_viewport' if complete else 'incomplete',
                'reliability':'observed' if complete else 'unresolved'})
    # Fetching some resources isn't proof of complete dependency coverage.
    resource_status=('PASS' if browser.get('completed') and browser.get('resources_closed') else 'PARTIAL') if browser.get('resource_requests') else 'NOT_TESTED'
    out.append({'code':'resource_access','level':3,'status':resource_status,
        'source':pages[0]['url'] if pages else None,'checked_at':pages[0].get('checked_at') if pages else None,
        'evidence':{'attempted':browser.get('resource_requests',0),'ignored':browser.get('ignored_resources',[])},
        'error':browser.get('failure_codes',[]),'coverage':'requested_resources_only','reliability':'limited'})
    return out
