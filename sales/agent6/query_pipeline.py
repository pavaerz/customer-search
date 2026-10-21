"""Bounded query repair and receipt-based adaptation before any search spend.

No generated buying intent, provider calls, permanent bans or budget changes.
Repairs only group atomic alternatives and narrow shared qualifiers; commercial
policy still checks EVERY branch. Unsupported syntax is never sent to a provider.
"""
import re
from datetime import date
from collections import defaultdict
from sales.research_rules import REGION_CITIES, region_of


def tokens(text):
    return re.findall(r'"[^"\n]*"|[()]|[^\s()]+', text)


def normalize(query, today=None):
    original=query;query=' '.join(query.split());repairs=[]
    if query.count('"')%2:return {'query':original,'allowed':False,'reason':'unbalanced_quotes','repairs':[]}
    parts=tokens(query);depth=0;top_or=False
    for term in parts:
        if term=='(':depth+=1
        elif term==')':depth-=1
        elif term=='OR' and depth==0:top_or=True
        if depth<0:return {'query':original,'allowed':False,'reason':'unbalanced_parentheses','repairs':[]}
    if depth:return {'query':original,'allowed':False,'reason':'unbalanced_parentheses','repairs':[]}
    # site:it is a mistaken TLD constraint, not the hostname of an Italian firm.
    fixed=re.sub(r'(?<!\S)(-?site:)it(?=\s|[()]|$)',r'\1.it',query,flags=re.I)
    if fixed!=query:repairs.append('italian_tld_operator');query=fixed
    # Preserve the intended Italian TLD restriction from C44; never strip a
    # failed restriction and silently turn it into an unrestricted query.
    fixed=re.sub(r'(?<!\S)(-?site:)\*\.it(?=\s|[()]|$)',r'\1.it',query,flags=re.I)
    if fixed!=query:repairs.append('italian_tld_wildcard');query=fixed
    for term in tokens(query):
        raw=term.lstrip('-')
        if raw.lower().startswith('site:'):
            host=raw[5:]
            if not re.fullmatch(r'(?:https?://)?(?:\.[a-z]{2,}|(?:[\w-]+\.)+[a-z]{2,})(?:/[^\s"()]*)?',host,re.I):
                return {'query':original,'allowed':False,'reason':'invalid_site_operator','repairs':repairs}
        if ':' in raw and re.match(r'^[a-z]+:',raw,re.I) and raw.split(':')[0].lower() not in ('site','filetype','after','before','intitle','inurl'):
            return {'query':original,'allowed':False,'reason':'unsupported_search_operator','repairs':repairs}
        if raw.startswith(('after:','before:')):
            try:date.fromisoformat(raw.split(':',1)[1])
            except ValueError:return {'query':original,'allowed':False,'reason':'invalid_date_operator','repairs':repairs}
    if top_or:
        # For a flat expression only, group adjacent atomic alternatives. This
        # applies all shared qualifiers to every branch (narrows the search),
        # without dropping a territory, site restriction or commercial term.
        # Complex nesting is left to the model; every branch still faces policy.
        parts=tokens(query)
        if '(' not in parts and ')' not in parts:
            grouped=[];i=0
            while i<len(parts):
                alternatives=[parts[i]];i+=1
                while i<len(parts) and parts[i]=='OR':
                    if i+1>=len(parts):return {'query':original,'allowed':False,'reason':'empty_boolean_branch','repairs':repairs}
                    alternatives.append(parts[i+1]);i+=2
                if len(alternatives)>1:
                    if any(a in ('OR','AND') or a.startswith('-') or re.match(r'\w+:',a) for a in alternatives):
                        return {'query':original,'allowed':False,'reason':'ambiguous_boolean_repair','repairs':repairs}
                    grouped.append('('+' OR '.join(alternatives)+')')
                else:grouped.extend(alternatives)
            query=' '.join(grouped);repairs.append('shared_qualifiers_on_atomic_alternatives')
        else:
            query='('+query+')';repairs.append('explicit_boolean_group')
    return {'query':query,'original_query':original,'allowed':True,'repairs':repairs}


def family(query):
    """Regional clones share a signature; new source/intent/sector changes it."""
    text=query.casefold().replace('-filetype:pdf','')
    # Same requested action, not a new strategy: changing person/number of
    # “cercare” must not erase three observed empty searches. The query sent to
    # the provider remains untouched; source, service and role stay distinct.
    text=re.sub(r'\b(?:cerco|cerca|cercasi|cerchiamo|ricerchiamo)\b','cerca',text)
    places=set(REGION_CITIES)
    for cities in REGION_CITIES.values():places.update(cities.split())
    for place in sorted(places,key=len,reverse=True):
        text=re.sub(r'(?<!\w)'+re.escape(place.casefold()).replace(r'\-',r'[- ]')+r'(?!\w)',' ',text)
    return ' '.join(re.findall(r'[\w.:]+',text))


def semantic_family(query):
    """Additional SOCIAL circuit breaker: service/platform swaps aren't a reset.

    The original exact family remains available for diagnostics and non-social
    sources. External partnerships, requests and employment stay separate.
    """
    from .learning import strategy_id
    from .social import platform
    sites=re.findall(r'(?<!\S)site:([^\s()]+)',query.casefold())
    if not any(platform('https://'+s) for s in sites):return family(query)
    text=family(query)
    intent=strategy_id(query,'SOCIAL').split(':')[2]
    # Group equivalent development services, not industries or company names.
    if not re.search(r'wordpress|frontend|front.end|sviluppator|developer|web.?design|ecommerce|e.commerce|web.?app|\bmvp\b',text):return family(query)
    subject='agency' if re.search(r'agenzi|agency',text) else 'startup' if 'startup' in text else 'requester'
    return 'social_development:'+intent+':'+subject


def strategy_balance(flow,receipts):
    from .proactive import STRATEGY
    modes=[r.get('strategy')==STRATEGY for r in receipts if r.get('selection')!='verification' and isinstance(r.get('results'),int) and not r.get('technical_error')]
    proactive=sum(modes);explicit=len(modes)-proactive
    return {'required':flow=='AZIENDE' and abs(proactive-explicit)>=2,
            'preferred':'proactive' if proactive<=explicit else 'explicit',
            'proactive_queries':proactive,'explicit_queries':explicit}


def company_coverage(proposals,receipts):
    """Select the underrepresented mode when the AI already proposed it.

    Never manufacture a query, discard the alternative plan or force a weak
    company into the results. Targeted verification does not alter this balance.
    """
    from .proactive import STRATEGY
    preferred=strategy_balance('AZIENDE',receipts)['preferred']=='proactive'
    matching=[p for p in proposals if (p.get('strategy')==STRATEGY)==preferred]
    return matching or list(proposals)


def sector_terms(query):
    text=re.sub(r'(?<!\S)-?\w+:[^\s()]+',' ',query)
    terms=re.findall(r'[a-zà-ü]{4,}',family(text))
    generic=set(('azienda aziende impresa imprese sito siti ufficiale ufficiali prodotti prodotto servizi servizio '
        'catalogo cataloghi produzione produttore produttori commercio ecommerce online digitale digitali '
        'attivita attività contatti vendita vendite industria industriale industriali italiane italiano italia '
        'societa società manifattura manifatturiere settore settori realtà realtà mercato mercati '
        'company companies business businesses official website websites products product services service '
        'manufacturing manufacturer manufacturers catalogue catalog contact contacts production sales').split())
    return sorted(set(terms)-generic)


def adaptation(receipts):
    groups=defaultdict(list)
    for row in receipts:
        if isinstance(row.get('results'),int) and not row.get('technical_error'):
            for key in {family(row.get('query','')),semantic_family(row.get('query',''))}:
                groups[key].append(row)
    out=[]
    for key,rows in groups.items():
        # Different receipts, not duplicated report rows, determine the sample.
        rows=list({(r.get('campaign_id'),r.get('query')):r for r in rows}.values())
        recent=rows[:3]
        zero=len(recent)==3 and all(r['results']==0 for r in recent)
        noise=len(recent)==3 and all(r['results']>0 and len(r.get('policy_rejections',[]))>=.7*r['results'] for r in recent)
        if zero or noise:
            out.append({'family':key,'sample':3,'reason':'zero_results' if zero else 'mostly_non_company_sources',
                'action':'change_sector_source_or_commercial_action_before_another_territory',
                'permanent_blacklist':False})
    return out


def social_query_platform(query):
    from .social import platform
    sites=re.findall(r'(?<!\S)site:([^\s()]+)',query,re.I)
    return platform('https://'+sites[0]) if len(sites)==1 else None


def missing_social_platforms(receipts):
    covered={social_query_platform(r.get('query','')) for r in receipts
             if isinstance(r.get('results'),int) and not r.get('technical_error')}
    return [p for p in ('linkedin.com','instagram.com') if p not in covered]


def social_coverage(proposals,receipts):
    """Spend existing proposals on both requested platforms before repeats.

    No query is invented or dispatched here. If saved proposals only repeat an
    already searched platform, return none so planning can request the missing
    source within its unchanged quota. Transport errors are not source coverage.
    """
    missing=missing_social_platforms(receipts)
    return [q for q in proposals if social_query_platform(q['query']) in missing] if missing else list(proposals)


def discovery_exact_terms(result, proposal):
    """Release stacked phrase constraints, retaining one request anchor.

    Only flat discovery queries with multiple independent positive phrases.
    Never rewrite a named-subject lookup, exclusions, operators or Boolean
    expressions. Original evidence, not search syntax, proves buying intent.
    """
    query=result['query']
    if proposal.get('selection')=='verification' or proposal.get('expected_entity'):
        return result
    if re.search(r'[()]|\b(?:OR|AND)\b',query):return result
    phrases=list(re.finditer(r'(?<!\S)"([^"\n]+)"(?=\s|$)',query))
    if len(phrases)<2:return result
    from .discovery_intent import APPLICATION
    from .commercial_policy import REQUEST
    anchors=[m for m in phrases if REQUEST.search(m[1]) or APPLICATION.search(m[1])]
    anchor=max(anchors,key=lambda m:len(m[1]),default=None)
    for match in reversed(phrases):
        # Quoted operators or Boolean literals must remain literals.
        if re.search(r'[:()*]|\b(?:OR|AND)\b|(?<!\S)[+-]',match[1]):return result
        if anchor is not None and match.start()==anchor.start():continue
        query=query[:match.start()]+match[1]+query[match.end():]
    return {**result,'query':query,'repairs':[*result['repairs'],'discovery_phrase_matching_relaxed_terms_preserved']}


def prepare(proposal,flow,regions,receipts=(),today=None,*,ai_first=False):
    from .commercial_policy import assess_query
    result=normalize(proposal['query'],today)
    if not result['allowed']:return None,result
    if ai_first:
        previous=proposal.get('query_validation') or {}
        if previous.get('query')==result['query']:
            result={**result,'original_query':previous.get('original_query',result['original_query']),
                    'repairs':list(dict.fromkeys(previous.get('repairs',[])+result['repairs']))}
        result=discovery_exact_terms(result,proposal)
    q={**proposal,'query':result['query']}
    if ai_first:
        from .schema import plan_issue
        issue=plan_issue(q,0)
        if issue:return None,{**issue,'allowed':False,'reason':issue['code']}
        from .discovery_intent import assess
        intent=assess(q,flow,regions)
        if not intent['allowed']:return None,intent
        saturated=next((x for x in adaptation(receipts) if x['family'] in (family(q['query']),semantic_family(q['query']))),None)
        if saturated:return None,{'allowed':False,'reason':'query_family_saturated','adaptation':saturated}
        # This admits a research direction, never a lead or a declared need.
        # The decision on original evidence remains with the AI-first reader.
        return {**q,'query_validation':result,'channel':flow,
                'commercial_policy':intent,
                'query_family':family(q['query'])},None
    if flow=='AZIENDE' and q.get('strategy')=='official_company_sector_region' and not sector_terms(q['query']):
        return None,{**result,'allowed':False,'reason':'specific_business_sector_missing'}
    policy=assess_query(q,flow,regions)
    if not policy['allowed']:return None,{**result,**policy}
    year=(today or date.today()).year
    # Do not silently change an old year into a claim of current demand.
    years=[int(x) for x in re.findall(r'(?<![\w:-])(20\d{2})(?![\w-])',q['query'])]
    if years and any(y<(year if flow=='NEWS' else year-1) or y>year for y in years):
        return None,{**result,'allowed':False,'reason':'query_year_outside_current_discovery_window'}
    from .proactive import is_query
    balance=strategy_balance(flow,receipts)
    if balance['required'] and is_query(q,flow)!=(balance['preferred']=='proactive'):
        return None,{'allowed':False,'reason':'company_strategy_balance_requires_'+balance['preferred'],'balance':balance}
    saturated=next((x for x in adaptation(receipts) if x['family'] in (family(q['query']),semantic_family(q['query']))),None)
    if saturated:return None,{**result,'allowed':False,'reason':'query_family_saturated','adaptation':saturated}
    return {**q,'commercial_policy':policy,'query_validation':result,
        'query_family':family(q['query']),'semantic_family':semantic_family(q['query']),'strategy_balance':balance,'region':region_of(q['query']) or 'remote Italy',
        'channel':flow,'sector_or_subject_terms':sector_terms(q['query']),
        'priority':'after_pending_original_verification',
        'priority_basis':'validated_commercial_hypothesis_then_observed_outcomes'},None
