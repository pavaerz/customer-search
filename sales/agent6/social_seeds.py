"""User-supplied post URLs and bounded public-source recovery. No transport."""
import re
from urllib.parse import urlsplit,urlunsplit,urljoin,unquote,quote

from sales.providers import canonical
from .social import platform,post_url,same_reference,instagram_post_path


def normalize(values):
    if values is None:
        return []
    if not isinstance(values,list) or len(values)>20:
        raise ValueError('Inserisci al massimo 20 link social, uno per riga.')
    result=[]
    for value in values:
        if not isinstance(value,str) or not 1<=len(value)<=2000:
            raise ValueError('Link social non valido.')
        url=canonical(value.strip());parts=urlsplit(url)
        if platform(url) not in ('linkedin.com','instagram.com') or not post_url(url):
            raise ValueError('Inserisci il link a un post, reel o annuncio LinkedIn/Instagram, non al profilo.')
        path=unquote(parts.path)
        if platform(url)=='instagram.com':path=instagram_post_path(path) or path
        pattern=(r'/(?:p|reel)/[\w-]+/?' if platform(url)=='instagram.com' else
                 r'/(?:posts/[\w.-]+|jobs/view/[\w-]+|feed/update/urn:li:(?:activity|share|ugcPost):\d+)/?')
        if not re.fullmatch(pattern,path) or parts.port is not None:
            raise ValueError('Percorso del post social non valido.')
        # Tracking, fragments and viewer/session parameters are not post identity.
        url=urlunsplit(('https',parts.netloc,quote(path.rstrip('/')+'/',safe='/:-._'), '', ''))
        if not any(same_reference(url,other) for other in result):result.append(url)
    return result


def validate_filters(filters):
    values=normalize(filters.get('social_urls'))
    if values and (filters.get('decision_engine')!='ai_first_1' or
                   'SOCIAL' not in filters.get('commercial_engines',[])):
        raise ValueError('Per approfondire i link seleziona Social nella ricerca AI-first.')
    return values


def reference_token(url):
    """Use an identifier already present in the supplied URL, never guess one.

    Full quoted URLs can yield protocol tutorials instead of post references.
    The original URL remains the identity checked after acquisition.
    """
    url=normalize([url])[0]
    path=urlsplit(url).path
    if platform(url)=='instagram.com':return path.rstrip('/').rsplit('/',1)[1]
    match=re.search(r'(?:activity-|urn:li:(?:activity|share|ugcPost):)(\d{10,})(?!\d)',path)
    if match:return match[1]
    match=re.fullmatch(r'/jobs/view/(\d+)/?',path)
    if match:return match[1]
    # Some old LinkedIn URLs have only a slug. Preserve the supplied reference,
    # without a bare protocol term and without inventing a numeric identifier.
    needle=platform(url)+path
    return needle if len(needle)<=240 else None


def recovery_query(url):
    """Find references to this exact public post, not unrelated topic results."""
    url=normalize([url])[0]
    needle=reference_token(url)
    if not needle:return None
    return {'query':'"'+needle+'" -site:'+platform(url),
            'strategy':'social_original_reference','selection':'verification',
            'objective':'Cercare una fonte pubblica accessibile che richiami il post indicato.',
            'hypothesis':'Una pagina ufficiale può documentare autonomamente la richiesta citata nel post.',
            'missing':'Originale social non consultabile; identità, richiesta e attualità non verificate.',
            'expected_entity':'Soggetto ancora da identificare',
            'expected_source':'Fonte pubblica che collega il post originale',
            'success':'Collegamento al post e prove originali attribuibili al committente.',
            'stop_condition':'Nessun riferimento al post, fonte bloccata o budget configurato raggiunto.',
            'social_origin':{'url':url,'status':'ORIGINAL_UNAVAILABLE','original_read':False},
            'depth':1}


def links_post(page,url):
    from sales.extract import Document
    expected=normalize([url])[0]
    for link in Document(page['html']).links:
        try:
            if same_reference(normalize([urljoin(page['url'],link['url'])])[0],expected):return True
        except (ValueError,TypeError):
            continue
    return False


def lookup_worthwhile(item):
    """A search hint can justify verification, never qualify the social post.

    Keep the recovery tied to an actual development/collaboration invitation;
    generic advice, supplier CTAs and unrelated profiles consume no follow-up.
    """
    if not post_url(item.get('url','')):return False
    from .discovery_intent import APPLICATION
    title=str(item.get('title') or '')
    snippet=str(item.get('content') or item.get('snippet') or '')
    # This gate spends a search, it does not reject or verify the post. The
    # stem "svilupp" also matches sales growth and professional development;
    # require a technical role or an actual digital deliverable instead.
    technical=re.compile(r'\b(?:sviluppator\w*|programmator\w*|front[ -]?end|back[ -]?end|full[ -]?stack|'
        r'web\s*(?:developer|designer)|software\s*(?:developer|engineer)|wordpress|woocommerce|'
        r'sit[oi]\s+(?:web|internet)|e[ -]?commerce|\bAPI\b|applicazion[ei]\s+web|\bCTO\b|'
        r'sviluppo\s+(?:web|software)|sviluppare\s+(?:software|una\s+piattaforma)|'
        r'(?:rifare|rifacimento|realizzare|nuovo)\s+(?:(?:il|un|del)\s+)?sito)\b',re.I)
    invitation=re.compile(r'\b(?:cerco|cerchiamo|cercasi|ricerchiamo|seeking|looking for|we need)\b',re.I)
    if re.search(r'\b(?:percorso formativo|corso per|diventa tecnico)\b',title,re.I):
        return False
    # Ellipses and bullets often join unrelated excerpts. An invitation in a
    # different result fragment cannot turn a platform/industry into a request.
    fragments=[title]+re.split(r'\.{3,}|…|\s[·•]\s|\n',snippet)
    return any(technical.search(text) and (invitation.search(text) or APPLICATION.search(text))
               for text in fragments)
