"""Escalate a measured targeted audit only when another page can test it."""
from sales.commercial.audit_policy import finish


def plan(browser,pages,limits):
    if not browser.get('completed') or browser.get('deep_attempted'):return None
    if 'elapsed_ms' not in browser or 'resource_requests' not in browser:return None
    seconds=limits.get('browser_total_seconds',120)-browser['elapsed_ms']/1000
    resources=limits.get('browser_max_resources',60)-browser['resource_requests']
    if seconds<5 or resources<5:return None
    major=[f for f in browser.get('findings',[]) if f.get('severity')=='major']
    if not major:return None
    visited={p['url'] for p in browser.get('pages',[])}
    remaining=max(0,limits.get('max_browser_pages',3)-len(visited))
    targets=[p for p in pages if p['url'] not in visited and p.get('status')==200 and p.get('purpose') in ('offering','contact')][:remaining]
    if not targets:return None
    return {'pages':targets,'reason':'check_whether_measured_major_issue_affects_other_commercial_journeys',
        'seconds':seconds,'resources':resources,'basis':[{'url':f['url'],'code':f['code']} for f in major]}


def merge(first,deep):
    out={**first,'deep_attempted':True,'requested_level':'DEEP',
        'completed':bool(first.get('completed') and deep.get('completed')),
        'resources_closed':bool(first.get('resources_closed') and deep.get('resources_closed'))}
    for key in ('pages','findings','independent_findings','screenshots','diagnostics','limits','failure_codes','path_checks','ignored_resources'):
        out[key]=first.get(key,[])+deep.get(key,[])
    for key in ('elapsed_ms','resource_requests','resource_bytes'):out[key]=first.get(key,0)+deep.get(key,0)
    out['outcome']='completed' if out['completed'] else 'partial'
    return finish(out,'DEEP',True)
