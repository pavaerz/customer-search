"""Cheap, source-bound 3B.2 signals. These are admission hints, never proof."""
import re
from urllib.parse import urlsplit
from sales.db import domain

WEB_ROLE=re.compile(r'full[ -]?stack|front[ -]?end|back[ -]?end|web\s*(?:developer|designer)|sviluppator\w*|programmator\w*|wordpress|woocommerce|javascript|typescript|react|node\.?js|\bphp\b|e.?commerce',re.I)
NON_WEB_ROLE=re.compile(r'social media manager|social media specialist|copywriter|giornalista|journalist|marketing manager|sales manager|addett\w* alle vendite|firmware engineer|embedded (?:software )?engineer',re.I)

def technical_request(text,role=None):
    """Use the role/request clause before the employer's industry or related jobs."""
    from .context import TECH
    from .intent import request_clause
    scope=role or request_clause(text) or text
    if NON_WEB_ROLE.search(scope) and not WEB_ROLE.search(scope):return False
    return bool(WEB_ROLE.search(scope) or TECH.search(scope) or ((not role or re.search(r"co[ -]?founder|CTO",role,re.I)) and TECH.search(text)))

def preflight_type(item):
    host=domain(item.get('url',''));path=urlsplit(item.get('url','')).path
    title=str(item.get('title') or '');snippet=str(item.get('snippet') or item.get('content') or '')
    if host=='wikipedia.org' or host.endswith('.wikipedia.org'):return 'EDITORIAL','encyclopedia_domain'
    if re.search(r'(^|\.)(?:comune|regione|provincia)\.|\.gov\.it$|^univ?\w*\.it$',host) or re.search(r'^(?:Università|Comune di|Museo|Gazzetta Ufficiale|Parco archeologico|Biblioteca)\b',title,re.I):return 'INSTITUTIONAL','institution_identity_metadata'
    if re.search(r'^(?:Duomo|Cattedrale)\b',title,re.I):return 'INSTITUTIONAL','cultural_institution_metadata'
    if 'linkedin.com'==host or host.endswith('.linkedin.com'):return ('JOB_POSTING' if '/jobs/view/' in path else 'SOCIAL_POST'),'social_url'
    if host=='instagram.com' or host.endswith('.instagram.com'):return 'SOCIAL_POST','social_url'
    if re.search(r'agenzia (?:per il lavoro|immobiliare|di stampa)|agenzia governativa',title+' '+snippet,re.I):return 'UNKNOWN','non_digital_agency'
    return 'UNKNOWN','insufficient_metadata'
