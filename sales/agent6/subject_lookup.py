"""One official-domain recovery of an empty, evidence-led subject search.

This changes acquisition syntax, not commercial meaning or qualification.
It never initiates broad discovery, retries provider errors or claims an open job.
"""
import re
from urllib.parse import urlsplit

from sales.db import domain
from .discovery_intent import EXTERNAL
from .response_channels import public_url

ROLES=re.compile(r'\b(?:web developer|sviluppatore web|web designer|front[ -]?end|wordpress|woocommerce|full[ -]?stack)\b',re.I)


def context(body):
    """Carry only the validated original facts that justify this follow-up."""
    if (body.get('decision')!='NEEDS_RESEARCH' or body.get('validation_status')!='ACCEPTED'
            or not body.get('identity_verified') or not body.get('original')
            or body.get('commercial_exclusions')
            or body.get('relationship') not in ('OPEN_FREELANCE_COLLABORATION','SPONTANEOUS_APPLICATION','EXPLICIT_REQUEST')
            or body.get('compensation') in ('EQUITY_ONLY','UNPAID')):
        return None
    facts=body.get('facts',[])
    if any(f.get('field')=='closed' for f in facts):
        return None
    host=domain(body.get('official_domain') or '')
    own=[f for f in facts if f.get('original') and domain(f.get('url',''))==host]
    if (not any(f.get('field')=='request' for f in own)
            or not any(f.get('field') in ('request','contract') and EXTERNAL.search(f.get('quote','')) for f in own)):
        return None
    return {'purpose':'verify_external_collaboration','entity_name':body['entity_name'],
            'official_domain':host,'source_url':body['url'],
            'facts':[f for f in own if f.get('field') in ('entity','request','contract','technical')],
            'basis':'validated_original_not_current_availability'}


def recovery(proposal):
    if (proposal.get('selection')!='verification' or proposal.get('official_lookup_recovery')
            or proposal.get('page',1)!=1):
        return None
    scope=proposal.get('subject_lookup_context') or {}
    parent=proposal.get('research_parent') or {}
    host=scope.get('official_domain','')
    name=scope.get('entity_name')
    if (scope.get('purpose')!='verify_external_collaboration' or not name
            or parent.get('provenance')!='verified_owner_subject_lookup'
            or name!=parent.get('entity_name') or name!=proposal.get('expected_entity')
            or scope.get('source_url')!=parent.get('url')
            or host!=parent.get('lookup_domain') or domain(parent.get('url',''))!=host
            or domain(parent.get('packet',{}).get('final_url',''))!=host
            or not public_url('https://'+host,'https://'+host)):
        return None
    facts=scope.get('facts',[])
    own=[f for f in facts if f.get('original') and domain(f.get('url',''))==host]
    if (not any(f.get('field')=='request' for f in own)
            or not any(f.get('field') in ('request','contract') and EXTERNAL.search(f.get('quote','')) for f in own)):
        return None
    # The role comes from the prior AI query AND a cited original. A legal
    # suffix or incidental adjective is not carried into this broader lookup.
    query=proposal['query']
    facts_text=' '.join(f.get('quote','') for f in own)
    roles=[m.group() for m in ROLES.finditer(query) if re.search(re.escape(m.group()),facts_text,re.I)]
    if not roles:
        return None
    role=roles[0].lower()
    # A careers-navigation phrase is a location to inspect, never demand proof.
    rewritten='site:'+host+' (freelance OR "lavora con noi" OR "'+role+'")'
    if rewritten.casefold()==query.casefold():
        return None
    return {**proposal,'query':rewritten,'page':1,'strategy':'official_subject_lookup_recovery',
            'discovery_period':'','official_lookup_recovery':{
                'domain':host,'original_query':query,'reason':'empty_subject_search',
                'method':'official_domain_with_request_or_careers_or_observed_role',
                'source_url':scope['source_url'],'qualifies_opportunity':False},
            'query_validation':{},'stop_condition':'One official-domain recovery per company and campaign; existing budget and depth; no repeated URL.'}


def reading_priority(item):
    """Careers navigation before obsolete routes, internships and portfolios.

    Metadata only orders reads; it cannot prove availability or reject a firm.
    """
    path=urlsplit(item.get('url','')).path.lower()
    title=item.get('title','').lower()
    reason='owner_page_to_inspect';value=0
    if re.search(r'vecchia[-_/]versione|old[-_/]version|/archive[s]?/|/archivio/',path):
        reason='apparently_previous_version_read_later';value=-2
    elif re.search(r'(?:^|[/_-])(?:stage|internship|tirocinio)(?:$|[/_-])',path):
        reason='internship_route_read_later';value=-2
    elif re.search(r'(?:^|[/_-])(?:portfolio|case-stud(?:y|ies)|blog)(?:$|[/_-])',path):
        reason='portfolio_or_editorial_route_read_later';value=-1
    elif re.search(r'lavora con noi|join (?:our )?team|careers|collabora con noi|candidatur',title) or re.search(
            r'unisciti-al-team|lavora-con-noi|collabora-con-noi|/careers/?$',path):
        reason='official_careers_page_for_currentness_check';value=3
    return {'value':value,'basis':reason,'effect':'reading_order_only_not_current_availability'}
