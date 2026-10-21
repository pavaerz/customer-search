"""Pre-inference sufficiency: admitting ambiguity is not qualifying a buyer."""
import re
from .intent import classify_block, request_clause
from .relevance import technical_request
from .context import EXTERNAL, CAREERS

SKIP='SKIP_AI_INSUFFICIENT_EVIDENCE'

def sufficient(engine,result,evidence):
    demand=result.get('demand_assessment') or {}
    if demand.get('version')=='5.1' and engine!='WEBSITE_REBUILD':
        # Semantic advice can interpret an unknown actor. It may not assert one:
        # the existing grounding/identity validators still apply to every claim.
        from .demand import ASK as demand_ask
        proofs=[e['id'] for e in evidence if e.get('kind')!='indexed_text'
                and e.get('url')==result.get('url') and len(e.get('text',''))>=30
                and (request_clause(e['text']) or demand_ask.search(e['text']) or EXTERNAL.search(e['text']))
                and technical_request(e['text'])]
        if demand.get('page_type')=='STANDING_COLLABORATION':
            from .demand import STANDING
            for e in evidence:
                if e.get('kind')=='indexed_text' or e.get('url')!=result.get('url') or not e.get('section'):continue
                if STANDING.search(e.get('text','')) and EXTERNAL.search(e.get('text','')):
                    peers=[p for p in evidence if p.get('section')==e['section'] and p.get('url')==e['url'] and p.get('kind')!='indexed_text' and technical_request(p.get('text',''))]
                    if peers:proofs.extend([e['id'],*[p['id'] for p in peers]])
        allowed=bool(proofs and demand.get('request_observed') and not demand.get('excluded'))
        return {'allowed':allowed,'reason':'semantic_request_without_identity_authority' if allowed else SKIP,
                'request_evidence_ids':proofs,'actor_verified':False,'scope':'semantic_advisory_only','role':'UNKNOWN'}
    from .opportunity_view import normalize
    actor=(result.get('identity') or {}).get('name') or result.get('company')
    subject=[e for e in evidence if 'identity' in e.get('roles',[]) and e.get('kind')!='indexed_text' and e.get('url') and actor and normalize(actor) in normalize(e.get('text',''))]
    if not subject or (result.get('identity') or {}).get('identity_status')!='verified':
        return {'allowed':False,'reason':SKIP,'detail':'missing_verified_subject_after_trimming','request_evidence_ids':[],'role':'UNKNOWN'}
    if engine=='WEBSITE_REBUILD':
        from .target_fit import useful_ai_text
        meaningful=[]
        for e in evidence:
            if not e.get('url') or e.get('kind')=='indexed_text':continue
            text=e.get('text','')
            measured=any(f.get('quote')==text and f.get('kind')=='measurement' for f in result.get('evidence',[]))
            if measured or useful_ai_text(text):meaningful.append(e['id'])
        return {'allowed':bool(meaningful),'reason':'substantive_target_or_measured_evidence' if meaningful else SKIP,
                'role':'UNKNOWN','request_evidence_ids':meaningful,'scope':'technical_advisory_only'}
    requests=[];roles=[]
    from .indexed_jobs import parse_indexed_job
    hint=parse_indexed_job(result.get('discovery') or result)
    if hint['commercial_compatibility'] is False:
        return {'allowed':False,'reason':SKIP,'role':'EMPLOYER','request_evidence_ids':[],'detail':'incompatible_primary_job'}
    for e in evidence:
        text=e['text'];intent=classify_block(text,url=e.get('url',''),title=result.get('title',''))
        role=intent.get('commercial_role','UNKNOWN');roles.append(role)
        if role in ('SELLER','PARTNERSHIP_SELLER','EMPLOYER','EDITORIAL','DIRECTORY','AGGREGATOR'):continue
        core=bool(request_clause(text) and technical_request(text)) or (role=='PARTNERSHIP_BUYER' and technical_request(text))
        # An indexed individual role is useful ambiguity, never proof of actor,
        # currentness or contract. Related-job snippets cannot supply the core.
        indexed=e.get('kind')=='indexed_text'
        title=(result.get('discovery') or {}).get('title','')
        if indexed and title and title in text and '/jobs/view/' in e.get('url',''):
            core=core or bool(technical_request(title) and EXTERNAL.search(title))
        if core and e.get('url'):requests.append(e['id'])
    return {'allowed':bool(requests),'reason':'commercial_request_nucleus' if requests else SKIP,
            'role':'BUYER' if requests else next((r for r in roles if r!='UNKNOWN'),'UNKNOWN'),
            'request_evidence_ids':requests,'actor_verified':False}

def service_equivalence(claim,supporting):
    """Closed terminology equivalences, not fuzzy similarity or permissive tokens.

    Any extra feature, migration, budget or unsupported scope stays invalid.
    """
    aliases={
        'wordpress':('wordpress','sviluppo wordpress','wordpress development'),
        'woocommerce':('woocommerce','sviluppo woocommerce','woocommerce development'),
        'frontend':('frontend','front-end','sviluppo frontend','frontend development','front-end development'),
        'ecommerce':('e-commerce','ecommerce','sviluppo e-commerce','e-commerce development'),
    }
    if not isinstance(claim,str):return False
    value=claim.strip().casefold()
    for service,labels in aliases.items():
        if value not in labels:continue
        pattern={'frontend':r'front[ -]?end','ecommerce':r'e[ -]?commerce'}.get(service,service)
        return bool(re.search(r'\b'+pattern+r'\b',supporting,re.I) and technical_request(supporting))
    return False


def page_relevance(page,engine):
    """Only conclusive supplier direction stops identity/deep reads early."""
    from sales.extract import parse_page
    from .context import extract
    parsed=parse_page(page);blocks=extract(page)
    role=classify_block(parsed['text'],url=page['url'],title=parsed['title']).get('commercial_role','UNKNOWN')
    has_request=any(b.get('asking') or request_clause(b.get('text','')) for b in blocks)
    if engine=='AGENCIES':
        from .request_profile import agency_signal
        has_request=has_request or agency_signal(parsed['text']) in ('A_OPEN_TECHNICAL_REQUEST','B_DECLARED_EXTERNAL_PRACTICE','C_INDIRECT_AMBIGUOUS')
    excluded=engine!='WEBSITE_REBUILD' and not has_request and role in ('SELLER','PARTNERSHIP_SELLER','DIRECTORY','AGGREGATOR')
    return {'allowed':not excluded,'role':role,'reason':'supplier_not_buyer' if excluded else 'requires_bounded_verification','level':'original_page','request_blocks':len(blocks)}
