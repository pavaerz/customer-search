"""Separate publisher/owner from mentioned employers before collecting identity."""
import re
from sales.db import domain
from sales.extract import parse_page
from sales.research_analysis import identity_from
from .context import source_kind


def identity(pages):
    page=pages[0]
    from .entity_scope import profile,unresolved
    if profile(page)['multi_subject']:return unresolved(page)
    kind=source_kind(page);p=parse_page(page)
    if kind in ('directory','aggregator','job_portal','article','institution','portfolio'):
        return {'name':p['doc'].meta.get('og:site_name') or domain(page['url']),
                'website':page['url'],'identity_status':'unknown','group':'direct',
                'contacts':[],'locations':[],'region':None,'legal_id':None,
                'basis':'Fonte multi-soggetto: collegamento ufficiale al committente non verificato.',
                'attribution':{'publisher':domain(page['url']),'domain_owner':None,'client':None,'role':kind}}
    from .identity import establish
    result=establish(pages)
    result['contacts']=[x for x in result.get('contacts',[]) if not (x['type']=='email' and (re.search(r'@(?:example|website|email)\.',x['value'],re.I) or '...' in x['value']))]
    result['attribution']={'publisher':domain(page['url']),'domain_owner':result.get('name'),
                           'client':result.get('name') if result['identity_status']=='verified' else None,'role':'owner'}
    return result


def geographic_conflicts(geo, blocks, allowed=None):
    from .geography import region
    observations=[]
    for b in blocks:
        for e in b['evidence']:
            if re.search(r'sede|localit|location',e['quote'],re.I):
                found=region(e['quote'])
                if found:observations.append({'region':found,'quote':e['quote'],'url':e['url'],'kind':'request_text'})
    declared={x['region'] for x in geo['locations'] if x.get('region') and x.get('kind')=='opportunity'}
    printed={x['region'] for x in observations}
    conflicts=[]
    if declared and printed and not printed<=declared:conflicts.append({'structured':sorted(declared),'text':observations})
    geo={**geo,'conflicts':conflicts,'request_locations':observations}
    if conflicts:geo.update(eligible=False,reason='Località dell’annuncio discordanti; non usare quella dell’editore.')
    if allowed and not geo.get('remote_italy') and geo['regions'] and not set(geo['regions'])&set(allowed):
        geo.update(eligible=False,country='Fuori area',reason='Regione documentata fuori dall’area ammessa.')
    if allowed and not geo.get('remote_italy') and not geo['regions']:
        from .geography import REGIONS
        if set(allowed)!=set(REGIONS):
            geo.update(eligible=False,reason='Italia documentata ma regione non risolta: non presumere compatibilità con l’area selezionata.')
    return geo


def requesting_identity(identity,result,source_url):
    """A hosted project must not inherit the publisher's domain/entity/CRM."""
    attribution=result.get('actor_attribution')
    if not attribution:return identity
    return {**identity,'name':result['requesting_actor'],'website':None,'source_url':source_url,
            'identity_status':'unknown','legal_id':None,'contacts':[],'locations':[],
            'region':None,'regions':[],'attribution':attribution,
            'basis':'Progetto identificato nella sezione della fonte; dominio ufficiale non verificato.'}
