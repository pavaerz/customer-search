"""Bounded audit policy. Unknown dependencies remain essential, never optimistic."""
from urllib.parse import urlsplit
LEVELS=('BASIC','STANDARD','DEEP')
TRACKERS={'www.google-analytics.com','google-analytics.com','analytics.google.com','stats.g.doubleclick.net','connect.facebook.net','www.facebook.com'}

def resource_role(url,kind,origin):
    host=urlsplit(url).hostname
    if host in TRACKERS:return 'TRACKING'
    if kind in ('media','ping','beacon'):return 'OPTIONAL'
    path=urlsplit(url).path.lower()
    if host!=urlsplit(origin).hostname and kind in ('script','fetch','xhr','document'):
        if (host in ('www.google.com','www.recaptcha.net','www.gstatic.com') and '/recaptcha/' in path) or path.endswith('/form_embed.js'):return 'FORM'
        if host=='cdn-cookieyes.com':return 'CONSENT'
    if kind in ('document','stylesheet','font','script'):return 'CRITICAL'
    if host!=urlsplit(origin).hostname:return 'THIRD_PARTY'
    return 'UNKNOWN'

def finish(report,requested='DEEP',capture=True):
    requested=requested if requested in LEVELS else 'DEEP';report['requested_level']=requested
    pages=report.get('pages',[]);valid=[p for p in pages if p.get('complete')]
    widths={p.get('viewport') for p in valid if p.get('url')==(pages[0].get('url') if pages else None)}
    completed='BASIC' if valid else None
    shots=report.get('screenshots',[])
    if {390,1366}<=widths and (not capture or {390,1366}<={p.get('viewport') for p in shots if p.get('reliability')=='CONFIRMED'}):completed='STANDARD'
    if requested=='DEEP' and report.get('completed') and completed=='STANDARD':completed='DEEP'
    if requested=='BASIC' and report.get('completed'):completed='BASIC'
    report['completed_level']=completed
    report['completed_phases']=sorted({d['phase'] for d in report.get('diagnostics',[]) if d.get('status')=='completed'})
    report['failed_phases']=sorted({d['phase'] for d in report.get('diagnostics',[]) if d.get('error') and d.get('affects_completion') is not False})
    report['missing_resources']=[{'url':d['url'],'role':resource_role(d['url'],d.get('resource_type','unknown'),pages[0]['url'] if pages else ''),'reason':d.get('error')} for d in report.get('diagnostics',[]) if d['phase']=='resource' and d.get('error')][:60]
    if report.get('completed') and completed not in LEVELS[LEVELS.index(requested):]:report['completed']=False
    if not report.get('completed') and report.get('outcome')=='completed':report['outcome']='partial'
    report['measurement_reliability']='CONFIRMED' if report.get('completed') else 'UNVALIDATED' if pages else 'NOT_MEASURABLE'
    report['observations']=[{'url':p['url'],'viewport':p.get('viewport'),'code':'horizontal_overflow','value_px':p.get('measurements',{}).get('overflow'),'status':'CONFIRMED' if p.get('complete') else 'UNVALIDATED'} for p in pages if p.get('measurements',{}).get('overflow',0)>100]
    report['independent_measurements']=[{'url':p['url'],'viewport':p.get('viewport'),'scope':'visible_page_only_not_form_submission','status':'CONFIRMED','measurements':{k:p.get('measurements',{}).get(k) for k in ('visible_content','width','overflow','clipped','blocked')}} for p in valid]
    retain_independent_findings(report)
    for f in report.get('findings',[]):f['status']='CONFIRMED' if report.get('completed') else 'UNVALIDATED'
    if not report.get('completed'):report['findings']=[]
    return report


def retain_independent_findings(report):
    """A later page failure cannot erase earlier validated viewport evidence.

    Legacy consumers still receive findings only on full success. The website
    path explicitly checks the corresponding page measurement before use.
    """
    valid={(p.get('url'),p.get('viewport')) for p in report.get('pages',[]) if p.get('complete') and p.get('scope')=='rendered'}
    findings=report.get('independent_findings',[])+report.get('findings',[])
    found={}
    for f in findings:
        if (f.get('url'),f.get('viewport')) not in valid:continue
        key=(f.get('url'),f.get('viewport'),f.get('code'),f.get('quote'))
        found[key]={**f,'status':'CONFIRMED','scope':'completed_viewport_only'}
    report['independent_findings']=list(found.values())
