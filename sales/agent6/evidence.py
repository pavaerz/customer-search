"""AI-first evidence packets. Acquisition stays in the existing protected web client.

Dates and identities are observations, never commercial decisions. Each listing is
isolated before passages are selected; previous search snippets are never proofs.
"""
import re
import json
from datetime import date
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

from sales.db import digest
from sales.extract import Document, nodes, types
from sales.content_policy import skip_pdf
from .passages import bundle


def date_value(raw):
    """Preserve precision and timezone; an expiry may legitimately be in the future."""
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})(?:T.*)?$', raw)
    if match:
        try:
            return date(*map(int, match.groups())).isoformat()
        except ValueError:
            return None
    match = re.match(r'^(\d{1,2})[/.](\d{1,2})[/.](\d{4})(?:\s.*)?$', raw)
    if match:
        try:
            return date(int(match[3]), int(match[2]), int(match[1])).isoformat()
        except ValueError:
            return None
    return None


def dates(text, metadata=(), unit_id='page'):
    claims = []
    for role, raw, origin in metadata:
        value = date_value(raw)
        if value:
            claims.append(dict(role=role, value=value, raw=raw, origin=origin,
                               unit_id=unit_id, explicit=True, precision='day',
                               timezone='as_supplied' if 'T' in raw else 'unknown'))
    pattern = (r'(?im)(?P<label>postato(?: il)?|pubblicato(?: il)?|posted(?: on)?|'
               r'aggiornato(?: il)?|scadenza|deadline)\s*:?\s*(?P<date>\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}[/.]\d{4})')
    for m in re.finditer(pattern, text):
        role = 'expires_at' if m['label'].lower() in ('scadenza', 'deadline') else 'modified_at' if m['label'].lower().startswith('aggiornat') else 'published_at'
        value = date_value(m['date'])
        if value:
            claims.append(dict(role=role, value=value, raw=m[0], origin='visible_label',
                               unit_id=unit_id, start=m.start(), end=m.end(),
                               explicit=True, precision='day', timezone='unknown'))
    # Unlabelled dates are retained but do not automatically date a vacancy.
    for m in re.finditer(r'(?m)^\s*(\d{1,2}/\d{1,2}/\d{4})(?:\s*[-–]\s*\d\d:\d\d)?\s*$', text):
        value = date_value(m[1])
        if value:
            claims.append(dict(role='unassigned', value=value, raw=m[0], origin='visible_card',
                               unit_id=unit_id, start=m.start(), end=m.end(),
                               explicit=True, precision='day', timezone='unknown'))
    return claims


def packet(page, doc):
    parsed = Document(page['html'])
    text = doc['text']
    units = []
    jobs = [n for n in nodes(parsed.schemas) if 'JobPosting' in types(n)]
    metadata = [('published_at', parsed.meta.get('article:published_time'), 'og:article:published_time'),
                ('modified_at', parsed.meta.get('article:modified_time'), 'og:article:modified_time')]
    articles=[n for n in nodes(parsed.schemas) if types(n)&{'Article','NewsArticle','BlogPosting'}]
    page_nodes=articles or [n for n in nodes(parsed.schemas) if 'WebPage' in types(n)]
    if len(page_nodes)==1:
        n=page_nodes[0]
        # A related article's structured data must not date the current page.
        target=n.get('url') or n.get('@id')
        if not isinstance(target,str) or urljoin(page['url'],target).split('#')[0]==page['url'].split('#')[0]:
            metadata += [(role,n.get(field),'Schema.org.'+field) for field,role in
                         [('datePublished','published_at'),('dateModified','modified_at'),('validThrough','expires_at')]]
    for attributes in parsed.time_attributes:
        role=next((role for field,role in [('datePublished','published_at'),('dateModified','modified_at'),('validThrough','expires_at')]
                   if field in attributes.get('itemprop','').split()),'unassigned')
        metadata.append((role,attributes['datetime'],'HTML.time'))
    header=page.get('last_modified')
    if header:
        try:metadata.append(('modified_at',parsedate_to_datetime(header).isoformat(),'HTTP.Last-Modified'))
        except (TypeError,ValueError,OverflowError):pass
    from .social import post_url,content_scope,same_reference
    social_post=post_url(page['url'])
    scope=content_scope(page,doc) if social_post else None
    if social_post and not jobs:
        # A social page is not a company document. Only the uniquely located
        # post and its attributed author may enter inference; comments, footer,
        # platform metadata and neighbouring posts are never evidence.
        if scope:
            post=next(n for n in nodes(parsed.schemas) if 'SocialMediaPosting' in types(n))
            unit_id=doc['id']+':social'
            units.append({'id':unit_id,'text':text,'origin':'SocialMediaPosting',
                          'allowed_ranges':scope['allowed_ranges'],
                          'analysis_text':scope['analysis_text'],
                          'dates':dates(scope['analysis_text'],[(role,post.get(field),'SocialMediaPosting.'+field)
                              for field,role in [('datePublished','published_at'),('dateModified','modified_at'),
                                                 ('expires','expires_at')]],unit_id)})
    elif jobs:
        for i, job in enumerate(jobs):
            # On an external platform require the specific advertised job,
            # never borrow the metadata of a related vacancy.
            if social_post:
                target=job.get('url') or job.get('@id')
                if not isinstance(target,str) or not same_reference(urljoin(page['url'],target),page['url']):
                    continue
            # JSON remains a quote of a supplied structured-data object, not a
            # synthetic company/request assembled from unrelated DOM cards.
            content = json.dumps(job, ensure_ascii=False, indent=2)
            unit_id = doc['id']+':job:'+str(i)
            units.append({'id':unit_id, 'text':content, 'origin':'JobPosting',
                          'document_id':digest(page['url']+':JobPosting:'+content),
                          'dates':dates(content, [('published_at',job.get('datePosted'),'JobPosting.datePosted'),
                              ('modified_at',job.get('dateModified'),'JobPosting.dateModified'),
                              ('expires_at',job.get('validThrough'),'JobPosting.validThrough')], unit_id)})
    else:
        starts = list(re.finditer(r'(?im)^(?:Organizzazione|Azienda|Company|Employer)\s*:', text))
        if len(starts) > 1:
            boundaries=[m.start() for m in starts]
            # Printed listings often put requester/title BEFORE the owner label
            # and end each card with a date. Do not lend the next title to the
            # previous employer. Without that boundary retain the owner scope.
            stamp=r'(?m)^\s*\d{1,2}/\d{1,2}/\d{4}(?:\s*[-–]\s*\d\d:\d\d)?\s*$'
            for i in range(1,len(starts)):
                previous=list(re.finditer(stamp,text[starts[i-1].end():starts[i].start()]))
                if previous:boundaries[i]=starts[i-1].end()+previous[-1].end()
            prefix=text[:starts[0].start()].splitlines(keepends=True)
            if len(prefix)>=2:boundaries[0]=sum(map(len,prefix[:-2]))
            for i, m in enumerate(starts):
                start=boundaries[i]
                end = boundaries[i+1] if i+1 < len(starts) else len(text)
                unit_id = doc['id']+':card:'+str(i)
                part = text[start:end]
                units.append({'id':unit_id,'text':part,'offset':start,'origin':'labelled_card',
                              'dates':dates(part, unit_id=unit_id)})
        else:
            unit_id = doc['id']+':page'
            units.append({'id':unit_id,'text':text,'origin':'page',
                          'dates':dates(text, metadata, unit_id)})
            from .discussion import scope as discussion_scope
            discussion = discussion_scope(page, text)
            if discussion:
                units[-1].update(allowed_ranges=discussion['allowed_ranges'],
                                 discussion_scope=discussion,
                                 dates=dates('', [('published_at', discussion['published_at'], 'discussion_post.date')], unit_id))
    scoped_urls=set()
    if social_post:
        for n in nodes(parsed.schemas):
            if 'SocialMediaPosting' in types(n) and scope:
                raw=n.get('articleBody') or n.get('text') or ''
                scoped_urls.update(urljoin(page['url'],l['url']) for l in Document(raw).links)
                scoped_urls.update(re.findall(r'https?://[^\s<>"\']+',scope['analysis_text']))
            elif 'JobPosting' in types(n):
                target=n.get('url') or n.get('@id')
                if not isinstance(target,str) or not same_reference(urljoin(page['url'],target),page['url']):
                    continue
                org=n.get('hiringOrganization')
                if isinstance(org,dict) and isinstance(org.get('url'),str):scoped_urls.add(org['url'])
    links = []
    for link in parsed.links:
        url = urljoin(page['url'], link['url'])
        if urlsplit(url).scheme not in ('http','https') or skip_pdf(url):
            continue
        if social_post and url not in scoped_urls:continue
        if re.search(r'logout|delete|unsubscribe|add-to-cart|checkout|[?&](?:token|key|auth|action)=',url,re.I):
            continue
        existing=next((x for x in links if x['url']==url),None)
        if existing is None:
            links.append({'id':'l'+digest(url)[:16], 'url':url, 'label':link['text'][:180]})
        elif not existing['label'].strip() and link['text'].strip():
            # An earlier icon/image link must not erase a later literal label
            # such as "Lavora con noi" for the same destination.
            existing['label']=link['text'][:180]
    def link_priority(link):
        # Navigation priority, never a claim that a job/collaboration exists.
        # Keep careers/invitations available before the eight-link input cap.
        text=link['label']+' '+urlsplit(link['url']).path
        if re.search(r'lavora|lavoro|careers?|jobs?|collabora|candidatur|join[- /]us|work[- /]with',text,re.I):return 0
        if re.search(r'contatt|contact',text,re.I):return 1
        if re.search(r'partner|prodott|product|servizi|services?|shop',text,re.I):return 2
        return 3
    links.sort(key=link_priority)
    from .source_context import observe
    content_context = observe(page, text)
    return {'document_id':doc['id'], 'initial_url':page.get('initial_url',page.get('requested_url',page['url'])),
            'final_url':page['url'], 'redirect_chain':page.get('redirect_chain',[]),
            'http_status':page['status'], 'content_type':page.get('content_type'),
            'last_modified':page.get('last_modified'), 'cache_control':page.get('cache_control'),
            'canonical_url':urljoin(page['url'],parsed.canonical) if parsed.canonical else None,
            'observed_at':page['checked_at'], 'title':parsed.title,
            'description':parsed.meta.get('description'), 'open_graph':parsed.meta,
            'headings':parsed.headings, 'structured_data':parsed.schemas,
            'time_elements':parsed.times, 'units':units, 'links':links,
            'editorial_metadata':bool(articles), 'content_context':content_context,
            'page_date_claims':dates('',metadata,doc['id']+':page')}


def metadata_document(page, doc, unit):
    """Literal extracted owner metadata, separately persisted and citable.

    Never attach publisher metadata to a listing/job unit. No invented identity
    or synthetic HTML; these fields come from the acquired original.
    """
    if unit['origin']!='page' or unit.get('discussion_scope'):
        return None
    from sales.extract import parse_page
    from sales.research_evidence import owned_organizations
    from sales.db import domain
    parsed=parse_page(page);d=parsed['doc']
    values={'title':d.title,'meta':{k:v for k,v in d.meta.items() if k in ('og:site_name','description','og:description')}}
    values['organizations']=[{k:n[k] for k in ('name','legalName','url') if k in n}
                             for n in owned_organizations(parsed,domain(page['url']))]
    text=json.dumps(values,ensure_ascii=False,indent=2)
    return {'id':digest(page['url']+':metadata:'+text),'url':page['url'],'text':text,
            'content_hash':digest(text),'title':'Metadati originali','checked_at':page['checked_at'],
            'provider':'Metadati estratti dalla fonte originale','parent_document_id':doc['id']}


def owner_address_document(page, doc, unit, verified_owner):
    """Citable owner schema addresses, kept ahead of optional marketing prose.

    The model still chooses the subject and assesses eligibility. Never attach
    a publisher office to a job, social post or multi-subject article.
    """
    if not verified_owner or unit['origin']!='page':return None
    from sales.extract import parse_page
    from sales.research_evidence import owned_organizations,address_text
    from sales.db import domain
    parsed=parse_page(page)
    if parsed.get('editorial') or parsed.get('job') or parsed.get('multi_job'):return None
    addresses=[]
    for org in owned_organizations(parsed,domain(page['url'])):
        values=org.get('address',[])
        if not isinstance(values,list):values=[values]
        for value in values:
            if not isinstance(value,dict):continue
            address=address_text(value)
            if address and len(address)<=500:
                row={'owner':org.get('legalName') or org.get('name',''),'address':address}
                if row not in addresses:addresses.append(row)
    if not addresses:return None
    text='\n'.join(json.dumps(row,ensure_ascii=False) for row in addresses[:4])
    return {'id':digest(page['url']+':owner-address:'+text),'url':page['url'],'text':text,
            'content_hash':digest(text),'title':'Sedi dichiarate nei metadati del titolare',
            'checked_at':page['checked_at'],'provider':'Indirizzi JSON-LD originali: componenti concatenati',
            'parent_document_id':doc['id']}


def passages(packet, unit, limit=4500, *, source_content=False):
    records = [{'id':unit['id'], 'url':packet['final_url'], 'text':unit['text'],
                'document_id':unit.get('document_id',packet['document_id']), 'original':True,
                'checked_at':packet['observed_at'],
                'allowed_ranges':unit.get('allowed_ranges')}]
    if unit.get('discussion_scope'):
        records[0]['preferred_spans'] = unit['discussion_scope']['preferred_spans']
    if unit['origin']=='JobPosting':
        records[0]['structured_lines']=job_lines(unit['text'])
    if source_content and unit['origin'] == 'page' and not unit.get('discussion_scope'):
        from .source_context import passage_hints
        records[0].update(passage_hints(packet, unit))
    result = bundle(records, limit,compact=True)
    for e in result:
        e['unit_id'] = unit['id']
        e['offset'] += unit.get('offset',0)
    return result


def job_lines(text):
    """Literal JSON ranges, splitting escaped paragraph breaks, never rewriting.

    JSON-LD descriptions are one physical line after json.dumps. Treating that
    line as one passage used to keep its introduction and drop later terms.
    Escaped backslashes are consumed as tokens, so a literal \\n is not confused
    with a paragraph. Only the current JobPosting document is considered.
    """
    for line in re.finditer(r'[^\n]+',text):
        if not re.match(r'\s*"description"\s*:',line[0]):continue
        # Keep metadata objects together: a bare name/IT value loses whether
        # it describes an employer, publisher or applicant location.
        ranges=[[0,line.start()]] if line.start() else []
        start=line.start()
        for token in re.finditer(r'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})|</(?:p|li|h[1-6]|div)>|<br\s*/?>',line[0],re.I):
            if token[0].startswith('\\') and token[0] not in (r'\n',r'\r'):continue
            end=line.start()+token.start()
            # Literal HTML paragraphs are common in ATS JSON-LD. Keep closing
            # tags in the quotation; never decode or synthesize source text.
            if token[0].startswith('<'):end=line.start()+token.end()
            if text[start:end].strip():ranges.append([start,end])
            start=line.start()+token.end()
        if text[start:line.end()].strip():ranges.append([start,line.end()])
        if text[line.end():].strip():ranges.append([line.end(),len(text)])
        return ranges
    return [[m.start(),m.end()] for m in re.finditer(r'[^\n]+',text)]
