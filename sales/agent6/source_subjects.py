"""Conservative public directory-to-company handoff; no inferred owner."""
import json
from html.parser import HTMLParser
from urllib.parse import urlsplit
from sales.db import domain,digest
from sales.content_policy import require_non_pdf,ExcludedPDF


def directory_subjects(page):
    class Scripts(HTMLParser):
        def __init__(self):super().__init__();self.active=False;self.parts=[];self.values=[]
        def handle_starttag(self,tag,attrs):
            if tag=='script':self.active=dict(attrs).get('type','').lower()=='application/ld+json';self.parts=[]
        def handle_data(self,text):
            if self.active:self.parts.append(text)
        def handle_endtag(self,tag):
            if tag=='script' and self.active:
                try:self.values.append(json.loads(''.join(self.parts)))
                except (ValueError,TypeError):pass
                self.active=False
    parser=Scripts();parser.feed(page.get('html',''));out=[]
    def visit(node,in_list=False):
        if isinstance(node,list):
            for v in node:visit(v,in_list)
        elif isinstance(node,dict):
            kinds=node.get('@type',[]);kinds=[kinds] if isinstance(kinds,str) else kinds
            if in_list and any(k in kinds for k in ('Organization','LocalBusiness','Corporation')):
                name=node.get('name');url=node.get('url')
                if isinstance(name,str) and isinstance(url,str) and urlsplit(url).scheme in ('https','http') and domain(url)!=domain(page['url']):
                    try:require_non_pdf(url)
                    except ExcludedPDF:return
                    from .schema import actor_span_valid
                    if actor_span_valid(name,0,len(name)):out.append({'name':name,'url':url,'publisher_url':page['url'],
                        'checked_at':page.get('checked_at'),'content_hash':digest(page.get('html','')),
                        'evidence_location':'JSON-LD ItemList / Organization',
                        'basis':'directory_structured_subject_official_link_unverified'})
            for k,v in node.items():
                if isinstance(v,(dict,list)):visit(v,in_list or k=='itemListElement')
    visit(parser.values)
    return list({(x['name'],x['url']):x for x in out}.values())[:3]
