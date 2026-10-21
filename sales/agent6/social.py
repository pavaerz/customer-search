"""Public social requests with explicit access and author-to-company boundaries.

This module never overrides blocked(), robots, TLS or authentication policy.
An indexed hint can lead to an independently verified company invitation; it
cannot be upgraded to a read social post. Public unblocked originals still need
a reciprocal official-company reference before their demand is attributed.
"""
import re
from urllib.parse import urlsplit,urljoin,parse_qsl,urlencode,urlunsplit
from sales.db import domain
from sales.providers import canonical,blocked
from sales.extract import parse_page,nodes,types
from sales.research_evidence import owned_organizations
from sales.commercial.indexed_jobs import same_company_name

PLATFORMS={'linkedin.com','instagram.com','facebook.com','x.com','twitter.com','reddit.com','mastodon.social','bsky.app'}

def instagram_post_path(path):
    """Stable post locator, not proof of its author or permission to read it."""
    match=re.fullmatch(r'/(?:[A-Za-z0-9_.]{1,30}/)?(p|reel)/([A-Za-z0-9_-]+)/?',path)
    return '/'+match[1]+'/'+match[2] if match else None

def same_reference(left, right):
    """Compare a public reference, not transport permission or company identity.

    Only explicit LinkedIn/Instagram host aliases are equivalent. Instagram's
    optional username prefix does not change the case-sensitive post locator;
    it does not prove authorship either. Keep unknown query parameters; never
    equate a generic profile, a different post or an arbitrary subdomain.
    """
    aliases={'linkedin.com':'www.linkedin.com','it.linkedin.com':'www.linkedin.com',
             'www.linkedin.com':'www.linkedin.com',
             'instagram.com':'www.instagram.com','www.instagram.com':'www.instagram.com'}
    def key(value):
        p=urlsplit(canonical(value))
        host=aliases.get(p.hostname) if p.port is None else None
        if host:
            path=(instagram_post_path(p.path) if host=='www.instagram.com' else None) or p.path
            params=[(k,v) for k,v in parse_qsl(p.query)
                    if k.lower() not in ('trk','trackingid','igsh','igshid')]
            return urlunsplit(('https',host,path.rstrip('/') or '/',urlencode(params),''))
        return urlunsplit((p.scheme,p.netloc,p.path.rstrip('/') or '/',p.query,''))
    try:
        return key(left)==key(right)
    except (ValueError,TypeError,AttributeError):
        return False


def platform(url):
    host=domain(url)
    return next((p for p in PLATFORMS if host==p or host.endswith('.'+p)),None)


def post_url(url):
    p=platform(url);path=urlsplit(url).path
    if p=='instagram.com':return instagram_post_path(path) is not None
    if p=='facebook.com' and re.fullmatch(r'/(?:[A-Za-z0-9_.-]+/)?videos/\d+/?',path):return True
    patterns={'linkedin.com':r'^/(?:posts/|feed/update/|jobs/view/)',
        'instagram.com':r'^/(?:p|reel)/[^/]+','facebook.com':r'/(?:posts/|permalink/|permalink\.php)',
        'x.com':r'^/[^/]+/status/\d+','twitter.com':r'^/[^/]+/status/\d+',
        'reddit.com':r'^/r/[^/]+/comments/','mastodon.social':r'^/@[^/]+/\d+',
        'bsky.app':r'^/profile/[^/]+/post/[^/]+'}
    return bool(p and re.search(patterns[p],path))


def query_policy(q):
    from .commercial_policy import positive_query
    text=positive_query(q.get('query',''))
    sites=re.findall(r'(?<!\S)site:([^\s()]+)',text,re.I)
    if len(text)>160 or len(re.findall(r'\bOR\b',text))>2:return {'allowed':False,'reason':'social_query_overloaded'}
    if len(sites)!=1 or not platform('https://'+sites[0]) or re.search(r'[?#@]',sites[0]):
        return {'allowed':False,'reason':'social_query_requires_one_supported_public_platform'}
    return {'allowed':True,'platform':platform('https://'+sites[0]),'access':'subject_to_existing_access_policy'}


def content_scope(page,doc):
    """Map the declared post body to exact original offsets, excluding comments.

    A structured post body alone is not evidence: it must occur verbatim in the
    delivered public text. Ambiguous/absent matches stay unverified.
    """
    from sales.extract import Document
    if not post_url(page['url']):return None
    posts=[n for n in nodes(parse_page(page)['doc'].schemas) if 'SocialMediaPosting' in types(n)]
    if len(posts)!=1:return None
    target=posts[0].get('url') or posts[0].get('@id')
    if isinstance(target,str):
        try:
            if not same_reference(urljoin(page['url'],target),page['url']):return None
        except ValueError:return None
    value=posts[0].get('articleBody') or posts[0].get('text')
    if not isinstance(value,str):return None
    text=Document(value).text
    if len(text)<30 or doc['text'].count(text)!=1:return None
    start=doc['text'].index(text);ranges=[[start,start+len(text)]]
    author=posts[0].get('author') or {};name=author.get('name') if isinstance(author,dict) else None
    if isinstance(name,str) and name and doc['text'].count(name)==1:
        a=doc['text'].index(name)
        if not start<=a<start+len(text):ranges.append([a,a+len(name)])
    return {'allowed_ranges':sorted(ranges),'analysis_text':text,'basis':'one_public_post_body_exactly_located_in_original_document'}


def context(body,page,doc):
    if not post_url(page['url']) or not body.get('original'):return None
    posts=[n for n in nodes(parse_page(page)['doc'].schemas) if 'SocialMediaPosting' in types(n)]
    scope=content_scope(page,doc)
    if len(posts)!=1 or not scope:return {'url':page['url'],'status':'PUBLIC_POST_AUTHOR_OR_SCOPE_UNVERIFIED','original_read':True,'author_profile':None,'reposted':False}
    post=posts[0];author=post.get('author');author=author if isinstance(author,dict) else {}
    name=body.get('entity_name') or ''
    profile=author.get('url') or author.get('@id')
    author_name=author.get('name')
    author_name=author_name.strip() if isinstance(author_name,str) else ''
    author_type='Person' if 'Person' in types(author) else 'Organization' if 'Organization' in types(author) else 'Unknown'
    if not isinstance(profile,str) or not author_name:profile=None
    if profile:
        try:profile=canonical(profile)
        except ValueError:profile=None
    if profile and platform(profile)!=platform(page['url']):profile=None
    # An author's own claim/worksFor metadata is not company verification.
    # Preserve the actual author, separately from the subject selected in the
    # isolated post. A different person's profile cannot verify that subject.
    subject_in_post=bool(name and re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',
                                            scope['analysis_text'],re.I))
    from sales.extract import iso_date
    from .qualification import temporal
    published=iso_date(post.get('datePublished')) or temporal(scope['analysis_text'],doc['checked_at'],True).get('published_at')
    return {'url':page['url'],'status':'PUBLIC_POST_READ','original_read':True,
        'author_name':author_name or None,'author_profile':profile,
        'author_type':author_type,'subject_name':name or None,
        'subject_named_in_post':subject_in_post,
        'published_at':published,'checked_at':doc['checked_at'],'content_hash':doc['content_hash'],
        'reposted':bool(post.get('sharedContent') or post.get('isBasedOn')),
        'basis':'public_post_metadata_identity_requires_reciprocal_official_reference'}


def reciprocal(context,page,identity):
    if not context or not context.get('original_read') or context.get('reposted') or not context.get('author_profile'):
        return {'verified':False,'reason':'original_author_unverified_or_repost'}
    subject=context.get('subject_name') or context.get('author_name','')
    if identity.get('identity_status')!='verified' or not same_company_name(identity.get('name',''),subject):
        return {'verified':False,'reason':'official_company_identity_not_matched'}
    person_subject=not same_company_name(identity.get('name',''),context.get('author_name',''))
    if person_subject and (context.get('author_type')!='Person' or not context.get('subject_named_in_post')):
        return {'verified':False,'reason':'personal_author_subject_unverified'}
    from sales.commercial.identity import owner_html
    from .response_channels import Controls
    clean=owner_html(page['html'])
    parsed=parse_page({**page,'html':clean});matches=[]
    def same(value):
        if person_subject:
            # A team profile link proves neither who commissions this request
            # nor that all posts by the person belong to the company.
            return same_reference(value,context['url'])
        return same_reference(value,context['author_profile']) or same_reference(value,context['url'])
    for organization in ([] if person_subject else owned_organizations(parsed,domain(page['url']))):
        values=organization.get('sameAs',[]);values=[values] if isinstance(values,str) else values
        for value in values if isinstance(values,list) else []:
            if isinstance(value,str) and same(value):matches.append({'url':page['url'],'reference':value,'method':'owned_organization_sameAs'})
    for link in Controls(clean).links:
        value=urljoin(page['url'],link['attrs'].get('href') or '')
        if same(value):matches.append({'url':page['url'],'reference':value,'method':
                                      'official_page_specific_person_post' if person_subject else 'official_page_public_profile_link'})
    return {'verified':bool(matches),'proofs':matches,
            'relationship':'person_post_referenced_by_company' if person_subject else 'company_author_reference',
            'person_role':'UNKNOWN' if person_subject else None,
            'reason':'reciprocal_official_reference' if matches else 'official_reference_missing'}


def scoped_context(page,doc,unit,name):
    """AI-first provenance, including an isolated platform JobPosting.

    A job's hiringOrganization is a claim, not verified ownership. Its public
    original URL must be linked from the independently verified employer page.
    """
    if unit.get('origin')!='JobPosting':
        return context({'original':True,'entity_name':name},page,doc)
    import json
    job=json.loads(unit['text']);org=job.get('hiringOrganization') or {}
    matched=isinstance(org,dict) and same_company_name(org.get('name',''),name or '')
    return {'url':page['url'],'platform':platform(page['url']),
            'status':'PUBLIC_POST_READ','original_read':True,
            'author_name':org.get('name') if matched else None,
            # Exact original is the only acceptable reciprocal reference here;
            # a generic company LinkedIn profile doesn't prove this job.
            'author_profile':page['url'] if matched else None,
            'published_at':next((d['value'] for d in unit['dates'] if d['role']=='published_at'),None),
            'checked_at':page['checked_at'],'content_hash':doc['content_hash'],
            'reposted':False,'basis':'specific_job_hiring_organization_requires_official_job_link'}


def scoped_geography(unit,regions):
    """No platform footer, company HQ or another job can establish eligibility."""
    import json
    from sales.commercial.job_activity import geo_value
    from sales.commercial.geography import resolve_location
    from sales.extract import Document
    text=unit.get('analysis_text',unit['text'])
    if unit['origin']=='JobPosting':
        job=json.loads(unit['text'])
        text=Document(job.get('description') or '').text
        # These are job-level fields; hiringOrganization.address isn't one.
        text+=' '+json.dumps({k:job[k] for k in ('jobLocation','jobLocationType','applicantLocationRequirements') if k in job},
                            ensure_ascii=False)
    value,reason=geo_value(text)
    region=resolve_location(text)['region']
    remote=bool(re.search(r'\bremote\b|remoto|TELECOMMUTE|smart working',text,re.I))
    return {'allowed':value=='GEO_COMPATIBLE' and (remote or region in regions),
            'region':region,'reason':reason,'basis':'isolated_original_request'}
