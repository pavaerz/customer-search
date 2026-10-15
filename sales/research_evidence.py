"""Conservative source scoping. Original HTML/text remains available as evidence."""
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit
from .extract import Document, nodes, types, iso_date
from .db import domain


class CommercialText(HTMLParser):
    """Remove explicitly marked consent overlays, never arbitrary commercial paragraphs."""
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self, html, article=False):
        super().__init__(convert_charrefs=False)
        self.article=article
        self.stack=[];self.output=[];self.removed=0;self.feed(html)
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        marker=' '.join(str(attrs.get(k,'')) for k in ('id','class'))
        consent=bool(re.search(r'cookie[-_ ]?(?:banner|consent|notice|law)|onetrust|iubenda|cky-consent|cmplz-cookie|privacy[-_ ]?(?:modal|popup)|consent[-_ ]?(?:modal|banner)',marker,re.I))
        related=self.article and bool(set(marker.split()) & {'single-art__content','native-summary-content','td-post-next-prev-content','related-posts','related-articles','article-related'})
        skip=any(x[1] for x in self.stack) or consent or related
        if consent:self.removed+=1
        if tag not in self.VOID:self.stack.append((tag,skip))
        if not skip:self.output.append(self.get_starttag_text())
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag not in self.VOID:self.handle_endtag(tag)
    def handle_endtag(self, tag):
        skip=any(x[1] for x in self.stack)
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                self.stack=self.stack[:i];break
        if not skip:self.output.append('</'+tag+'>')
    def handle_data(self, data):
        if not any(x[1] for x in self.stack):self.output.append(data)
    def handle_entityref(self,name):self.handle_data('&'+name+';')
    def handle_charref(self,name):self.handle_data('&#'+name+';')


def commercial_text(html):
    cleaned=CommercialText(html)
    return Document(''.join(cleaned.output)).text,cleaned.removed


class ArticleBody(HTMLParser):
    """Locate explicit visible body containers, never JSON-LD's hidden articleBody.

    Keep exact source slices. Ambiguous/malformed containers fall back to the
    visible page instead of arbitrarily picking the first article on an index.
    """
    def __init__(self,html,headline=''):
        super().__init__(convert_charrefs=False)
        self.html=html;self.offsets=[0];self.stack=[];self.spans=[]
        self.headline=headline;self.heading_parent=None
        for match in re.finditer('\n',html):self.offsets.append(match.end())
        self.feed(html)

    def source_position(self):
        line,column=self.getpos();return self.offsets[line-1]+column

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);classes=set((attrs.get('class') or '').split())
        priority=0 if 'articleBody' in (attrs.get('itemprop') or '').split() else 1 if classes & {'entry-content','post-content','td-post-content','content-to-read','elementor-widget-theme-post-content'} else None
        if attrs.get('id')=='content-to-read':priority=1
        # Some custom article templates mark the CMS body as #editor. Accept it
        # only as a sibling following the H1 matching the primary Article, not
        # an arbitrary editor elsewhere in the page or an editable form.
        if (priority is None and attrs.get('id')=='editor' and self.stack and
            self.heading_parent==self.stack[-1][1] and 'contenteditable' not in attrs and
            not any(t in ('form','aside','nav','footer','header') for t,_,_ in self.stack)):
            priority=2
        if tag in ('script','style','template'):priority=None
        if tag not in CommercialText.VOID:self.stack.append((tag,self.source_position(),priority))

    def handle_startendtag(self,tag,attrs):pass

    def handle_endtag(self,tag):
        for index in range(len(self.stack)-1,-1,-1):
            if self.stack[index][0]==tag:
                _,start,priority=self.stack[index]
                if tag=='h1' and index:
                    text=Document(self.html[start:self.source_position()]).text
                    if headline_words(text)==headline_words(self.headline):self.heading_parent=self.stack[index-1][1]
                if priority is not None:self.spans.append((priority,start,self.source_position()))
                self.stack=self.stack[:index];break


def headline_words(value):return ' '.join(re.findall(r'\w+',unescape(str(value)).casefold()))


def primary_articles(parsed):
    articles=[n for n in nodes(parsed['doc'].schemas) if types(n)&{'Article','NewsArticle','BlogPosting'}]
    words=headline_words
    title=words(parsed['title'])
    matched=[n for n in articles if n.get('headline') and words(n['headline']) in title]
    return matched or ([articles[0]] if len(articles)==1 and not articles[0].get('headline') else [])


def article_body_text(html,parsed):
    primary=primary_articles(parsed)
    if not primary:return None,None
    tree=ArticleBody(html,primary[0].get('headline',''))
    if not tree.spans:return None,None
    priority=min(s[0] for s in tree.spans)
    choices=[s for s in tree.spans if s[0]==priority]
    if len(choices)!=1:return None,None
    _,start,end=choices[0]
    cleaned=CommercialText(html[start:end],article=True)
    text=Document(''.join(cleaned.output)).text
    if not text.strip():return None,None
    return text,'Corpo articolo esplicito nel markup; testo integrale conservato separatamente.'


def article_access_limit(parsed):
    if not parsed.get('editorial'):return None
    declared=any(n.get('isAccessibleForFree') in (False,'false') for n in primary_articles(parsed))
    notice=re.search(r'accedi ai contenuti esclusivi riservati ai nostri abbonati|abbonati per (?:continuare|leggere)|effettua il login per leggere',parsed['text'],re.I)
    if declared or notice:
        return 'Articolo riservato o anteprima per abbonati: fonte incompleta, nessuna azienda qualificata da questo contenuto.'
    return None


def source_date(page, parsed):
    """A site's creation date is not an event date, even with WordPress Article markup."""
    path=urlsplit(page['url']).path.strip('/').lower()
    evergreen=not path or bool(re.fullmatch(r'[a-z]{2}(?:-[a-z]{2})?|(?:[a-z]{2}/)?(?:index\.(?:html?|php)|home|homepage|chi-siamo|about(?:-us)?|azienda|company|contatti|contact(?:-us)?|rivenditori|dealers?|store-locator|dealer-locator)/?',path))
    if evergreen:return None,None
    if parsed.get('job'):return iso_date(parsed['job'].get('datePosted')),'JobPosting.datePosted'
    # Generic WebPage.datePublished alone dates the resource, not a business event.
    if parsed.get('date_origin')=='Dati strutturati datePublished':
        dates=[]
        for node in nodes(parsed['doc'].schemas):
            if types(node)&{'Article','NewsArticle','BlogPosting'}:
                url=node.get('url')
                if url and isinstance(url,str) and urlsplit(url).path.rstrip('/')!=urlsplit(page['url']).path.rstrip('/'):continue
                date=iso_date(node.get('datePublished'))
                if date:dates.append(date)
        if len(set(dates))==1:return dates[0],'Articolo: data di pubblicazione, non data evento verificata'
        return None,None
    if not parsed.get('published_at'):
        # Related articles can add unrelated <time> elements. Prefer the single
        # explicitly labelled publication date, never the first arbitrary date.
        dates={iso_date(v) for v in parsed['doc'].publication_times}
        if None not in dates and len(dates)==1:
            return dates.pop(),'Elemento time datePublished; data pubblicazione, non data evento'
    return parsed.get('published_at'),parsed.get('date_origin')


def owned_organizations(parsed, host):
    """Do not borrow a dealer's address or a recruiter's hiringOrganization."""
    if parsed.get('job') or parsed.get('multi_job'):return []
    return [n for n in nodes(parsed['doc'].schemas)
            if types(n)&{'Organization','Corporation','LocalBusiness','ProfessionalService'}
            and isinstance(n.get('url'),str) and domain(n['url'])==host]


def address_text(address):
    if not isinstance(address,dict):return None
    parts=[address.get(k) for k in ('streetAddress','postalCode','addressLocality','addressRegion','addressCountry') if isinstance(address.get(k),str)]
    return ', '.join(parts) or None


def identity_text(page, parsed):
    """Directory/article bodies describe third parties; only the legal footer is safe there."""
    risky=bool(parsed.get('editorial') or parsed.get('job') or parsed.get('multi_job') or re.search(r'rivenditor|dealer|store.?locator|punti.?vendita|dove.?acquist|distributor',page['url']+' '+parsed['title'],re.I))
    html=page['html']
    if risky:html='\n'.join(re.findall(r'<footer\b[^>]*>.*?</footer\s*>',html,re.I|re.S))
    return re.sub(r'<(/?)(?:footer|header)\b',r'<\1div',html,flags=re.I)


def preliminary_disposition(page, parsed, text):
    from .research_rules import EMPLOYEE,FULL,REQUEST
    title=parsed['title'];path=urlsplit(page['url']).path
    vacancy_context=any(re.search(r'candidat|curriculum|posizione|ricerchiamo|cerchiamo',text[max(0,m.start()-250):m.end()+250],re.I) for m in EMPLOYEE.finditer(text))
    if parsed.get('job') or vacancy_context:
        # A third-party vacancy cannot establish the employer's official identity.
        return {'reason':'Assunzione di personale, non una commessa. L’eventuale bisogno digitale richiede prove indipendenti.',
                'next_action':'Identificare il datore di lavoro e cercare un progetto distinto dall’assunzione; nessuna qualifica da questo annuncio.'}
    if re.search(r'rivenditor|dealer|store.?locator|punti.?vendita|dove.?acquist',title+' '+path,re.I) and not (REQUEST.search(text) and FULL.search(text)):
        return {'reason':'Elenco di rivenditori: indirizzi e strumenti descritti non dimostrano un bisogno del produttore.',
                'next_action':'Usare solo dati societari attribuiti al titolare del sito; cercare un segnale commerciale indipendente.'}
    if re.search(r'\b(?:come (?:aprire|lanciare|rifare|vendere)|guida (?:definitiva|completa|per)|modelli di modul|templates?|migliori marketplace)\b',title,re.I) and not (REQUEST.search(text[:1500]) and FULL.search(text[:1500])):
        return {'reason':'Guida o catalogo di strumenti: descrive come fare, non un bisogno specifico del committente.',
                'next_action':'Cercare un fatto aziendale specifico; nessuna verifica commerciale approfondita su questa guida.'}
    if re.search(r'/(?:forum\d*|forum|portfolio|portfolio-category|progetti)/',path,re.I):
        return {'reason':'Discussione o raccolta di progetti: il soggetto e una richiesta attuale non sono ancora verificati.',
                'next_action':'Verificare una fonte originale riferita a un committente identificabile.'}
    return None
