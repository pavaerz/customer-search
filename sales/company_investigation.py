"""Evidence-led questions for a verified company; never a buying-intent score.

Only original, company-scoped passages can seed an investigation. The questions
describe what remains to be checked, including reasons not to propose a project.
"""
from datetime import datetime,timezone
import re
from .db import digest,domain
from .research_rules import normalize
from urllib.parse import urljoin

EVENTS=(
    ('brand',r'nuov[oa]\s+(?:marchio|brand|divisione)|lanci\w*\s+(?:il\s+)?marchio',
     'Come viene presentata e distinta la nuova offerta?',
     'marchio prodotti servizi',
     'Il sito presenta già il marchio e la sua offerta? Una pagina aggiuntiva è sufficiente?'),
    ('offer',r'nuov[ae]\s+line[ae]\s+(?:di\s+)?prodotti|nuov[oa]\s+servizio',
     'Il cliente può capire e richiedere la nuova offerta?',
     'catalogo prodotti servizi contatti',
     'Catalogo, schede e percorso di richiesta sono già operativi? Basta aggiornare i contenuti?'),
    ('market',r'espansion\w*\s+(?:internazional\w*|commercial\w*)|nuov[oi]\s+mercat[oi]|mercato\s+(?:tedesco|francese|estero)|rete\s+(?:di\s+)?distributor\w*',
     'Come vengono serviti i mercati o distributori citati?',
     'mercati distributori contatti',
     'Sono già presenti strumenti o partner locali? Basta una traduzione o una pagina dedicata?'),
)


def plan(identity,documents):
    if identity.get('identity_status')!='verified':return []
    host=domain(identity.get('website',''));out=[];seen=set();families=set()
    # Investigate the newest fact in each family first; avoid generating the
    # same catalogue/market query for every historical article on a company.
    for doc in sorted(documents,key=lambda d:str(d.get('published_at') or ''),reverse=True):
        # Publisher footers, other companies and copied snippets cannot seed a plan.
        owned=bool(doc.get('official') and domain(doc.get('url',''))==host)
        scoped=doc.get('scoped_to_subject')
        words=lambda value:set(re.findall(r'\w{3,}',normalize(value)))-{'srl','spa','società','azienda'}
        expected=words(identity.get('name',''))
        if not owned and (not scoped or not expected or words(scoped)!=expected):continue
        text=doc.get('research_text',doc.get('text',''))
        try:
            date=datetime.fromisoformat(doc['published_at'][:10]).date()
            age=(datetime.now(timezone.utc).date()-date).days
            if not 0<=age<=180:continue
        except (KeyError,TypeError,ValueError):
            # Undated changes may be old. Preserve them as context, not an event-led task.
            continue
        for kind,pattern,question,terms,countercheck in EVENTS:
            if kind in families:continue
            match=re.search(pattern,text,re.I)
            if not match:continue
            start=max(text.rfind('\n',0,match.start()),text.rfind('. ',0,match.start()))+1
            stop=text.find('\n',match.end());stop=len(text) if stop<0 else stop
            quote=text[start:min(stop,match.end()+250)].strip()
            if normalize(quote) not in normalize(doc.get('text','')):continue
            key=digest(normalize(quote))
            if key in seen:continue
            seen.add(key);families.add(kind)
            # Literal nearby words improve specificity without invented brand names.
            phrase=' '.join(re.findall(r'[\wÀ-ÿ]+',quote)[:14])[:180]
            out.append({'id':key,'kind':kind,'status':'hypothesis','document_id':doc['id'],
                        'url':doc['url'],'quote':quote,'published_at':doc['published_at'],
                        'question':question,'countercheck':countercheck,
                        'queries':[f'site:{host} {phrase}',f'site:{host} {terms}'],
                        'limit':'Annuncio riscontrato nella fonte; bisogno, perimetro e fornitore ancora da verificare.'})
            prefix=quote.split(':',1)[0].strip()
            prefix=re.sub(r'^(?:Nasce|Presentiamo|Scopri)\s+','',prefix)
            if ':' in quote and re.fullmatch(r'[A-ZÀ-Ý][\wÀ-ÿ-]+(?:\s+[A-ZÀ-Ý][\wÀ-ÿ-]+){1,4}',prefix):
                out[-1]['named_topic']=prefix
    return out


def topic_links(pages,questions):
    """Follow actual links named by the event, even with an opaque URL path.

    This is evidence acquisition, not a finding that the linked solution works.
    Network/robots protections remain the responsibility of the normal reader.
    """
    from .extract import parse_page
    from .providers import canonical,blocked
    found=[]
    for question in questions:
        topic=question.get('named_topic')
        if not topic:continue
        for page in pages:
            if page['url']!=question['url']:continue
            for link in parse_page(page)['doc'].links:
                if normalize(topic) not in normalize(link['text']):continue
                try:url=canonical(urljoin(page['url'],link['url']))
                except (ValueError,TypeError):continue
                if url==page['url'] or blocked(url):continue
                if url not in found:found.append(url)
    return found


def linked_brand_solutions(pages,identity):
    """Read a related brand explicitly linked by the company before proposing one.

    The link is evidence of a relationship to investigate, not proof of ownership
    or adequacy. Fetching still uses the protected reader and existing limits.
    """
    from .extract import parse_page
    from .providers import canonical,blocked
    from .linked_sites import referenced_sites
    words=lambda text:set(re.findall(r'\w{2,}',normalize(text)))-{'srl','spa','società','azienda','sito','www','com','it'}
    expected=words(identity.get('name',''))
    if not expected or identity.get('identity_status')!='verified':return []
    host=domain(identity.get('website',''));out=[]
    for page in pages:
        if domain(page['url'])!=host:continue
        contextual=set(referenced_sites(page['html']))
        for link in parse_page(page)['doc'].links:
            label=link['text']
            named_brand=expected<=words(label) and re.search(r'\b(?:design|brand|marchio|shop|collection|collezione)\b',label,re.I)
            if not named_brand and link['url'] not in contextual:continue
            try:url=canonical(urljoin(page['url'],link['url']))
            except (TypeError,ValueError):continue
            if blocked(url) or domain(url)==host or url in out:continue
            out.append(url)
    return out
