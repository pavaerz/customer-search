"""Read-only 8.0 activity projection; never rewrite stored historical totals."""
from sales.db import domain
from sales.commercial.recommendations import canonical_url
from .entities import index


def measures(rows,tasks=()):
    graph=index(rows);companies=set();qualified=set();pages=set();sites=set();browser_sites=set();unknown_access=0
    compatible=set();contacts=set();invitations=set();explicit=set();promising=set();light=set()
    for row in rows:
        b=row['body'];key=graph['record_keys'][row['id']]
        anchor=graph['links'][row['id']]
        if anchor['domain']:
            companies.add(key)
            if row['state'] in ('VERIFIED','POTENTIAL'):qualified.add(key)
            if b.get('contacts'):contacts.add(key)
            if b.get('commercial_fit',{}).get('audit_allowed'):compatible.add(key)
            if any(f.get('field')=='request' and f.get('original') for f in b.get('facts',[])):
                if b.get('kind')=='AGENCY_PARTNERSHIP':invitations.add(key)
                if b.get('kind')=='BUYER_DEMAND':explicit.add(key)
            from .completion import dossier
            if row['state'] not in ('VERIFIED','POTENTIAL') and dossier(b)['promising']:promising.add(key)
        # HTTP 200 or original=True alone is insufficient: login/challenge
        # interstitials must not count as consulted original pages.
        if b.get('original') and b.get('access',{}).get('content_read'):
            pages.add(canonical_url(b['url']))
        for doc in b.get('documents',[]):
            if doc.get('original') and doc.get('access',{}).get('content_read'):
                pages.add(canonical_url(doc['url']))
        audit=b.get('website_audit') or {}
        if b.get('original') and 'access' not in b and not audit and not any(d.get('access') for d in b.get('documents',[])):
            unknown_access+=1
        audited=set()
        for page in audit.get('pages',[]):
            if page.get('access',{}).get('content_read'):
                pages.add(canonical_url(page['url']))
                if anchor['domain']==domain(page['url']):audited.add(anchor['domain'])
        sites.update(audited)
        if audit.get('pages') and all(p.get('access',{}).get('content_read') for p in audit['pages']):light.update(audited)
        if audit.get('browser_status')=='COMPLETE':browser_sites.update(audited)
    return {'identified_companies':len(companies),'qualified_companies':len(qualified),
        'companies_with_documented_fit':len(compatible),'companies_with_public_contact':len(contacts),
        'documented_external_invitations':len(invitations),'documented_explicit_requests':len(explicit),
        'promising_dossiers':len(promising),'sites_with_completed_http_screen':len(light),
        'usable_qualified_dossiers':len(qualified),'sales_conversion':None,
        'original_pages_read':len(pages),'sites_with_audit':len(sites),
        'sites_with_completed_browser':len(browser_sites),
        'original_records_without_access_status':unknown_access,
        'active_verification_tasks':sum(t['n'] for t in tasks if t['kind']=='candidate' and t['state']=='working'),
        'pending_verification_tasks':sum(t['n'] for t in tasks if t['kind']=='candidate' and t['state']=='pending'),
        'basis':'distinct_verified_entities_and_access_confirmed_pages',
        'historical_totals_unchanged':True}
