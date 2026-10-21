"""Interpret protected HTTP redirects without trusting unrelated final hosts."""
import re
from urllib.parse import urljoin
from sales.db import domain
from sales.commercial.identity import establish


def resolve(pages,requested,expected=None):
    first=next((p for p in pages if p.get('requested_url',p['url'])==requested and p.get('status')==200),None)
    final=first['url'] if first else requested
    root=urljoin(final,'/')
    owned=[p for p in pages if p.get('status')==200 and domain(p['url'])==domain(root) and p.get('purpose')!='external_solution']
    owned.sort(key=lambda p:p['url']!=root)
    identity=establish(owned) if owned else {'name':None,'identity_status':'unknown','contacts':[]}
    initial_host=domain(requested);final_host=domain(final)
    changed=initial_host!=final_host
    # A .it/.com redirect plus a corroborated owner name is a relationship;
    # a random parking/affiliate host is not. No TLS/robots/SSRF exceptions.
    stem=lambda host:host.rsplit('.',1)[0]
    name=re.sub(r'\W','',(identity.get('name') or '').casefold())
    name_anchor=re.sub(r'\W','',stem(final_host))
    from .qualification import same_company_name
    related=(not changed or bool(first and identity.get('identity_status')=='verified'
        and stem(initial_host)==stem(final_host) and len(name_anchor)>=4 and name_anchor in name))
    if expected and not same_company_name(expected,identity.get('name') or ''):related=False
    return owned,identity,{'requested_url':requested,'final_url':final,'final_domain':final_host,
        'canonical_url':root,'redirect_chain':first.get('redirect_chain',[]) if first else [],
        'chain_recorded':bool(first and ('redirect_chain' in first or not changed)),
        'relationship_verified':related,'cross_domain':changed,
        'basis':'same_host' if not changed else 'same_domain_stem_and_verified_company_name' if related else 'unverified_cross_domain_relationship',
        'checked_at':first.get('checked_at') if first else None}
