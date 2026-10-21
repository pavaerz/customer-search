"""Exclude neighbouring requests without rewriting source quotations/offsets."""
import re
from html.parser import HTMLParser

RELATED=r'(?:Similar jobs|More jobs like this|Related jobs|Similar threads|Related threads|Discussioni simili|Discussioni correlate|Annunci simili|Annunci correlati|Offerte di lavoro correlate|Altre offerte di lavoro)'
HEADING=re.compile(r'^\s*'+RELATED+r'\s*[:：]?\s*$',re.I)


def text_scope(text):
    cursor=0
    for line in text.splitlines(keepends=True):
        if HEADING.fullmatch(line.strip()):
            return {'text':text[:cursor],'selected_ranges':[[0,cursor]],'excluded_ranges':[[cursor,len(text)]],
                'boundary':line.strip(),'basis':'explicit_related_requests_heading'}
        cursor+=len(line)
    return {'text':text,'selected_ranges':[[0,len(text)]],'excluded_ranges':[],
        'boundary':None,'basis':'no_explicit_related_requests_boundary_full_text_retained'}


def request_page_type(html):
    # Template evidence describes a thread, not a company or a current opening.
    return 'forum_thread' if re.search(r'\bdata-template\s*=\s*["\']thread_view["\']',html,re.I) else None


def main_html(html):
    """Only headings form a boundary; a sentence mentioning similar jobs does not."""
    class Headings(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True);self.tag=None;self.parts=[];self.start=0;self.cut=None
        def handle_starttag(self,tag,attrs):
            if tag in ('h1','h2','h3','h4','h5','h6'):
                self.tag=tag;self.parts=[]
                line,column=self.getpos();self.start=sum(len(s) for s in html.splitlines(keepends=True)[:line-1])+column
        def handle_data(self,data):
            if self.tag:self.parts.append(data)
        def handle_endtag(self,tag):
            if tag==self.tag:
                if self.cut is None and HEADING.fullmatch(''.join(self.parts).strip()):self.cut=self.start
                self.tag=None
    parser=Headings();parser.feed(html)
    return html[:parser.cut] if parser.cut is not None else html
