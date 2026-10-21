"""Observed listing → distinct original links, never a company qualification.

Only CollectionPage/ItemList entries corroborated by a visible whole linked card
are handled. Titles are request labels, not verified company names. All quotes
remain literal ranges of the acquired document. No network or inferred dates.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from sales.extract import Document, nodes, types, web_reference
from sales.db import digest
from sales.content_policy import skip_pdf
from .source_context import VOID, NON_CONTENT


class Cards(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.html=html;self.stack=[];self.open=None;self.cards=[]
        self.lines=[0]
        for m in re.finditer('\n',html):self.lines.append(m.end())
        self.feed(html)

    def position(self):
        line,col=self.getpos();return self.lines[line-1]+col

    def handle_starttag(self,tag,attrs):
        a=dict(attrs);hidden=bool(self.stack and self.stack[-1][1])
        hidden=hidden or tag in ('nav','header','footer','aside','script','style','template','noscript','form')
        hidden=hidden or 'hidden' in a or a.get('aria-hidden','').lower()=='true'
        hidden=hidden or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',a.get('style',''),re.I))
        hidden=hidden or (tag not in ('html','body') and bool(NON_CONTENT.search(a.get('class','')+' '+a.get('id',''))))
        if tag=='a':
            if self.open:self.open['invalid']=True
            elif not hidden:self.open={'start':self.position(),'href':web_reference(a.get('href','')),'invalid':False}
        if tag not in VOID:self.stack.append((tag,hidden))

    def handle_endtag(self,tag):
        if tag=='a' and self.open:
            value=self.open;self.open=None
            if not value['invalid']:
                value['end']=self.html.find('>',self.position())+1
                if value['end']>value['start']:self.cards.append(value)
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                del self.stack[i:];break

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)

    def handle_data(self,data):
        if self.open and data.strip() and self.stack and self.stack[-1][1]:
            self.open['invalid']=True


def observe(page,doc):
    """Return a collection only when at least two distinct cards are proven."""
    parsed=Document(page['html']);entries={};base=urlsplit(page['url'])
    for n in nodes(parsed.schemas):
        if 'CollectionPage' not in types(n):continue
        target=n.get('url') or n.get('@id')
        if not isinstance(target,str) or urljoin(page['url'],target).split('#')[0]!=page['url'].split('#')[0]:continue
        main=n.get('mainEntity')
        if not isinstance(main,dict) or 'ItemList' not in types(main):continue
        for item in main.get('itemListElement',[]):
            if not isinstance(item,dict) or 'ListItem' not in types(item):continue
            url=item.get('url');name=item.get('name')
            if not isinstance(url,str) or not isinstance(name,str):continue
            url=urljoin(page['url'],url);p=urlsplit(url)
            if p.scheme not in ('http','https') or p.netloc!=base.netloc or p.username or p.password:continue
            if p.path==base.path or skip_pdf(url):continue
            if re.search(r'logout|delete|unsubscribe|checkout|add-to-cart|[?&](?:token|key|auth|action)=',url,re.I):continue
            entries[url]=' '.join(name.split())
    if len(entries)<2:return None
    cards=[];seen=set()
    for a in Cards(page['html']).cards:
        if not a['href'] or a['end']-a['start']>32000:continue
        url=urljoin(page['url'],a['href'])
        if url not in entries or url in seen:continue
        fragment=Document(page['html'][a['start']:a['end']]);text=fragment.text
        if not 80<=len(text)<=6000 or doc['text'].count(text)!=1:continue
        if not any(h['text'].casefold()==entries[url].casefold() for h in fragment.headings):continue
        start=doc['text'].find(text);seen.add(url)
        cards.append({'url':url,'title':entries[url],'text':text,'document_id':doc['id'],
                      'document_start':start,'document_end':start+len(text),'content_hash':digest(text),
                      'source_url':page['url'],'checked_at':page['checked_at'],
                      'basis':'visible_linked_card_matching_collection_item_not_verified_request'})
    if len(cards)<2:return None
    # Routing hints only: never transfer a role, place or compensation from one
    # card to another, or claim a shortlist card is a verified buyer.
    request=re.compile(r'cerch|cerc[ao]|cercasi|collabor|co.?founder|socio|soci |looking for|seeking',re.I)
    technical=re.compile(r'svilupp|programmator|frontend|front.end|web.?design|wordpress|woocommerce|\bCTO\b|\bMVP\b|applicazion|\bapp\b|software|co.?founder tecnic',re.I)
    candidates=[c for c in cards if request.search(c['text']) and technical.search(c['text'])]
    # Company product/service catalogues can use the exact same schema. Without
    # a bounded technical-request hint, retain the normal company-reading path.
    if not candidates:return None
    # A named technical role is a stronger navigation hint than the mere fact
    # that a business uses an app. Still no inferred paid work or Italy access.
    role=re.compile(r'sviluppator|programmator|frontend|front.end|web.?design|\bCTO\b|co.?founder tecnic',re.I)
    selected=sorted(candidates,key=lambda c:not bool(role.search(c['text'])))[:3]
    return {'cards':cards,'selected':selected,'basis':'collection_navigation_only_no_commercial_decision'}


def route(c,task,page,doc,collection,check):
    """Use the existing durable queue, resource limits and suppression rules."""
    from . import decision,memory
    from sales.providers import canonical,blocked
    from sales.commercial.resources import BudgetExceeded
    p=task['payload'];flow=task['strategy'];outcomes=[]
    depth=p.get('depth',0)
    for item in collection['selected']:
        check()
        if depth>=c.settings['max_verification_depth']:
            outcomes.append({'url':item['url'],'status':'depth_limit'});continue
        if blocked(item['url']) or c.rs.suppressed({'website':item['url']}):
            outcomes.append({'url':item['url'],'status':'access_or_commercial_exclusion'});continue
        target=canonical(item['url'])
        try:
            added=c.enqueue('candidate',flow,{'url':target,'title':item['title'],
                'query':p.get('query'),'strategy':p.get('strategy'),'depth':depth+1,
                'listing_origin':item,
                'research_question':'Leggere il singolo annuncio: verificare committente, richiesta tecnica, condizioni, luogo e attualità. La scheda dell’elenco non li dimostra.',
                'discovery_priority':{'value':2,'basis':'specific_original_link_from_request_collection'}},
                'ai-first-url:'+digest(target))
            outcomes.append({'url':target,'status':'queued' if added else 'already_queued_or_stopped'})
        except BudgetExceeded as exc:
            outcomes.append({'url':target,'status':'budget_limit','resource':exc.resource})
    check()
    body=decision.base({'url':page['url'],'title':doc.get('title',''),'original':True,'checked_at':page['checked_at']},flow)
    body.update(state='NEEDS_REVIEW',validation_status='COLLECTION_ONLY',workflow_state='INDIVIDUAL_ORIGINALS_REQUIRED',
                reason='Elenco di annunci: le singole fonti richiedono verifiche separate. Nessuna azienda qualificata dalla raccolta.',
                collection_navigation={'card_count':len(collection['cards']),'selected':collection['selected'],
                                       'outcomes':outcomes,'basis':collection['basis']},
                query=p.get('query'),strategy=p.get('strategy'))
    memory.save_record(c.store,c.campaign,flow,body,[doc])
    memory.event(c.store,c.campaign,flow,'collection_navigation',digest(page['url']),body['collection_navigation'])
