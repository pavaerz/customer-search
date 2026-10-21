"""News → attributed company event → official-site investigation.

A publisher is never the buyer. These functions only admit verification; they
do not invent a digital gap, an event date or an expressed buying request.
"""
import re
from datetime import date
from urllib.parse import urljoin
from sales.db import digest,domain
from sales.providers import canonical,blocked
from sales.content_policy import require_non_pdf,ExcludedPDF
from sales.extract import parse_page
from sales.commercial.indexed_jobs import same_company_name
from .schema import actor_span_valid

EVENT=re.compile(r'nuov[oaie]\s+(?:prodott|mercat|march|line|serviz|sed[ei]|showroom|canal|gestione|proprietà)|espansion|internazional|lancio|launch|new (?:product|market|brand|service|office|ownership|management)|rebrand|expand|inaugur|investiment|riapertur|\briapr\w*|\breopen\w*',re.I)
GENERIC=re.compile(r'statistic|sondaggi|sondaggio|indagine congiunturale|previsioni economiche|aziende su dieci|\d+\s*%.*imprese',re.I)


def query_policy(q):
    from .commercial_policy import positive_query,query_branches,bounded_boolean_query,GAP,PORTFOLIO
    text=positive_query(q.get('query',''))
    if len(text)>160 or len(re.findall(r'\bOR\b',text))>2:return {'allowed':False,'reason':'news_query_overloaded'}
    if not bounded_boolean_query(text):return {'allowed':False,'reason':'news_unbalanced_query'}
    try:branches=query_branches(text)
    except ValueError:return {'allowed':False,'reason':'news_unbalanced_query'}
    if any(not EVENT.search(b) or GENERIC.search(b) or PORTFOLIO.search(b) for b in branches):
        return {'allowed':False,'reason':'news_requires_company_event_not_macro_topic'}
    context=' '.join(q.get(k,'') for k in ('hypothesis','missing','success','stop_condition'))
    if not GAP.search(context):return {'allowed':False,'reason':'news_missing_falsifiable_digital_check'}
    return {'allowed':True,'intent':'company_event_to_verify','reason':'event_not_a_request_verify_company_site_and_related_gap'}


def direction(body):
    name=body.get('entity_name') or ''
    if body.get('kind') not in ('EDITORIAL','COMPANY_SIGNAL') or not actor_span_valid(name,0,len(name)):return None
    if body.get('state') in ('REJECTED','POTENTIAL','VERIFIED') or body.get('suppressed'):return None
    entity=any(f.get('field')=='entity' and f.get('quote','').strip()==name for f in body.get('facts',[]))
    if not entity:return None
    for f in body.get('facts',[]):
        quote=f.get('quote','')
        if (f.get('field')=='signal' and re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',quote,re.I)
            and EVENT.search(quote) and not GENERIC.search(quote)):
            return {'allowed':True,'reason':'attributed_event_requires_official_site_check',
                'goal':'official_domain' if not body.get('identity_verified') else 'digital_gap','evidence':quote}
    return None


def context(body,page,doc):
    d=direction(body)
    if not d or not body.get('original'):return None
    from .commercial_policy import preflight
    if not preflight({'url':page['url'],'title':doc.get('title',''),'content':doc.get('text','')})['allowed']:return None
    # Signals must be original quotations from this article, never a recycled
    # search snippet or another company's evidence in a preceding task.
    signals=[f for f in body['facts'] if f.get('field')=='signal' and f.get('original') and f.get('url')==page['url'] and f.get('quote')==d['evidence']]
    if not signals:return None
    parsed=parse_page(page)
    publication=parsed.get('published_at') if parsed.get('date_origin') in ('article:published_time','Dati strutturati datePublished','Elemento time') else None
    # Multiple unrelated <time> tags are deliberately not resolved by guessing.
    publication_basis=parsed.get('date_origin') if publication else None
    return {'subject':body['entity_name'],'source_url':page['url'],'title':doc['title'],
        'published_at':publication,'publication_basis':publication_basis,'event_date':None,
        'checked_at':doc['checked_at'],'event':signals[0],
        'document':{k:doc[k] for k in ('id','url','text','content_hash','checked_at','title')},
        'identity_verified':bool(body.get('identity_verified')),'official_domain':body.get('official_domain'),
        'basis':'attributed_public_event_not_declared_digital_demand'}


def fresh(context,checked_at,window):
    try:
        published=date.fromisoformat(context['published_at'][:10]);checked=date.fromisoformat(checked_at[:10])
        age=(checked-published).days
    except (ValueError,TypeError,KeyError):return False
    if not 0<=age<=window:return False
    # A recently republished description of an old event is not a new event.
    years=[int(y) for y in re.findall(r'\b(20\d{2})\b',context['event']['quote'])]
    if years and any(y!=published.year for y in years):return False
    return True


def targets(context,page):
    if context['identity_verified'] and domain(context.get('official_domain') or '')==domain(page['url']):
        return [{'url':urljoin(page['url'],'/'),'basis':'event_on_verified_company_domain'}]
    out=[]
    for link in parse_page(page)['doc'].links:
        if link.get('navigation') or not same_company_name(link.get('text',''),context['subject']):continue
        try:
            url=canonical(urljoin(page['url'],link['url']));require_non_pdf(url)
        except (ValueError,ExcludedPDF):continue
        if domain(url)==domain(page['url']) or blocked(url):continue
        out.append({'url':url,'basis':'article_links_named_subject_identity_still_to_verify'})
    return list({t['url']:t for t in out}.values())[:2]


def enqueue_site(worker,flow,url,context,parent,basis):
    # One company+event task; another channel can contribute a distinct event,
    # while syndicated copies of this quote do not create repeated audits.
    event_key=digest(re.sub(r'\W','',context['event']['quote'].casefold()))
    worker.enqueue('candidate',flow,{'url':url,'title':context['subject'],
        'query':parent.get('query'),'strategy':parent.get('strategy'),'depth':parent.get('depth',0)+1,
        'proactive':True,'news_context':context,'expected_entity':context['subject'],
        'verification_goal':'Verificare sito ufficiale e conseguenze digitali dell’evento.',
        'source_link_basis':basis},'agent-news-site:'+digest(domain(url)+event_key))


def investigate(worker,flow,body,page,doc,parent):
    ctx=context(body,page,doc)
    if not ctx or parent.get('depth',0)>=worker.settings['max_verification_depth']:return False
    found=targets(ctx,page)
    if found:
        for target in found:enqueue_site(worker,flow,target['url'],ctx,parent,target['basis'])
        worker.rs.event(worker.cid,'news_company_check','Evento attribuito: verifico l’impresa sul sito collegato, non l’editore.',page['url'],{'flow':flow,'subject':ctx['subject'],'targets':found})
        return True
    worker.investigate(flow,body,{**parent,'news_context':ctx})
    return True
