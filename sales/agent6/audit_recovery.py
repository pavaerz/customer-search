"""One targeted browser recovery within the original candidate time allowance."""
from sales.commercial.audit_policy import finish


def targets(report,pages,limits):
    if report.get('completed') or report.get('targeted_recovery_attempted'):return {}
    codes=set(report.get('failure_codes',[]))
    if not codes or not all('timeout' in code for code in codes):return {}
    remaining=limits.get('browser_total_seconds',120)-report.get('elapsed_ms',0)/1000
    if remaining<5:return {}
    level=limits.get('browser_audit_level','DEEP')
    widths=(390,) if level=='BASIC' else (390,1366)
    done={(p['url'],p.get('viewport')) for p in report.get('pages',[]) if p.get('complete') and p.get('scope')=='rendered'}
    selected=pages[:limits.get('max_browser_pages',3)] if level=='DEEP' else pages[:1]
    missing={p['url']:[w for w in widths if (p['url'],w) not in done] for p in selected}
    return {url:widths for url,widths in missing.items() if widths}


def merge(previous,retry,pages,limits):
    result={**previous,**retry,'targeted_recovery_attempted':True,
        'recovery_history':[{'elapsed_ms':previous.get('elapsed_ms'),'failure_codes':previous.get('failure_codes',[]),'limits':previous.get('limits',[])}]}
    rows={(p['url'],p.get('viewport')):p for p in previous.get('pages',[])}
    for p in retry.get('pages',[]):
        key=(p['url'],p.get('viewport'))
        if p.get('complete') or not rows.get(key,{}).get('complete'):rows[key]=p
    result['pages']=list(rows.values())
    for field in ('screenshots','independent_findings','findings','path_checks','diagnostics'):
        result[field]=previous.get(field,[])+retry.get(field,[])
    result['elapsed_ms']=previous.get('elapsed_ms',0)+retry.get('elapsed_ms',0)
    for field in ('resource_requests','resource_bytes'):result[field]=previous.get(field,0)+retry.get(field,0)
    required=targets({**result,'completed':False,'targeted_recovery_attempted':False,
        'failure_codes':['rendering_timeout'],'elapsed_ms':0},pages,limits)
    result['completed']=bool(retry.get('resources_closed') and not retry.get('limits') and retry.get('pages')
        and all(p.get('complete') for p in retry['pages']) and not required)
    result['outcome']='completed' if result['completed'] else 'partial'
    finish(result,limits.get('browser_audit_level','DEEP'),True)
    return result
