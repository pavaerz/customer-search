"""One bounded official-source lookup from a specific indexed vacancy.

Search metadata only identifies a hypothesis. It never verifies the employer,
contract, vacancy date or contact, and never overrides source access policy.
"""
import re
from urllib.parse import urlsplit
from sales.db import domain
from sales.commercial.context import TECH,EXTERNAL,EMPLOYEE,EXCLUDED
from sales.commercial.indexed_jobs import parse_indexed_job,publisher_host,same_company_name
from .schema import actor_span_valid


def proposal(item):
    url=item.get('url','');title=item.get('title','');snippet=item.get('content') or item.get('snippet') or ''
    if not publisher_host(url) or not TECH.search(title) or not EXTERNAL.search(title):return None
    # Only a single identified vacancy route, never a multi-employer index.
    path=urlsplit(url).path
    if not re.fullmatch(r'/(?:jobs/view|offerta|vacancy|jobad)/[^/]+/?|/offerta-\d+-[A-Za-z0-9-]+/?',path):return None
    if EMPLOYEE.search(title+' '+snippet) or EXCLUDED.search(snippet):return None
    candidates=[]
    first=parse_indexed_job(item)
    if first['resolution_allowed']:candidates.append(first['company_candidate'])
    # Match a complete sentence's grammatical requester, not a trailing title
    # fragment or one of several employers in a search index.
    requesters=[]
    for match in re.finditer(r'(?:^|[.!?]\s+|\n)([A-ZÀ-Þ][\wÀ-ÿ&\x27 -]{1,69})\s+(?:cerca|ricerca|sta assumendo)\s+([^.!?\n]+)',snippet):
        name,request=match.groups()
        if actor_span_valid(name,0,len(name)):
            requesters.append(name)
            if TECH.search(request):candidates.append(name)
    names=list(dict.fromkeys(candidates))
    if not names or not all(same_company_name(names[0],n) for n in names+requesters):return None
    name=names[0]
    if not actor_span_valid(name,0,len(name)):return None
    from sales.commercial.evaluation import skills
    terms=skills(title)
    if not terms:return None
    role=re.search(r'front[ -]?end|wordpress|woocommerce|web developer|full[ -]?stack',title,re.I)
    query='"'+name.replace('"','')+'" '+(role[0] if role else terms[0])+' careers -site:'+domain(url)
    hint={'source_url':url,'title':title,'snippet':snippet,'company_hint':name,
          'role_hint':title,'identity_verified':False,'original_request_verified':False,
          'basis':'specific_indexed_vacancy_not_original_evidence'}
    return {'query':query,'strategy':'indexed_official_request','selection':'verification',
        'objective':'Verificare sul sito del possibile committente la richiesta indicizzata e le condizioni per un freelance.',
        'hypothesis':'Un annuncio indicizzato menziona '+name+' e un ruolo tecnico esterno; identità e richiesta restano da verificare.',
        'missing':'Originale del committente, identità, rapporto esterno, attualità e compatibilità Italia.',
        'expected_entity':name,'expected_source':'Pagina ufficiale del committente con richiesta indipendentemente verificabile.',
        'success':'Originale attribuibile al soggetto con un invito pertinente e condizioni esplicite o limiti dichiarati.',
        'stop_condition':'Identità diversa, fonte ripubblicata, nessuna richiesta originale o budget raggiunto.',
        'indexed_origin':hint,'depth':1}


def candidate_issue(item,origin):
    """Cheap routing before download; original ownership still must be verified."""
    if publisher_host(item.get('url','')):return 'indexed_recovery_requires_official_source'
    name=origin['company_hint']
    title=item.get('title','')
    if not re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',title,re.I):
        # A legal name in the indexed vacancy may have only its brand in the
        # official-site title. Admit that hypothesis only when the result also
        # contains the complete legal name. Neither hint verifies ownership.
        brand=re.sub(r'\s+\b(?:s\.?\s*r\.?\s*l\.?\s*s\.?|s\.?\s*r\.?\s*l\.?|s\.?\s*n\.?\s*c\.?|s\.?\s*a\.?\s*s\.?)\s*$', '',name,flags=re.I).strip()
        snippet=item.get('content') or item.get('snippet') or ''
        if (brand==name or len(brand)<3 or not same_company_name(name,brand)
            or not re.search(r'(?<!\w)'+re.escape(brand)+r'(?!\w)',title,re.I)
            or not re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',snippet,re.I)):
            return 'indexed_recovery_subject_not_identified'
    return None
