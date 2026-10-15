"""Find explicitly referenced company sites, without asserting their ownership.

Use a small local HTML block with one unambiguous destination. A generic CTA
alone, a partner link or page-wide proximity cannot establish the relationship.
The normal protected HTTP reader must still inspect every returned destination.
"""
from html.parser import HTMLParser
import re

REFERENCE = re.compile(
    r'\b(?:visita(?:te)?|consulta(?:te)?|accedi(?:te)?)\s+(?:anche\s+)?'
    r'(?:(?:il|al)\s+)?nostro\s+(?:sito(?:\s+(?:web|dedicato))?|'
    r'portale|shop|negozio\s+online|e-commerce)\b', re.I)
BLOCKS = {'div', 'p', 'section', 'article', 'li'}
BOUNDARIES = {'section', 'article', 'li'}
SKIP = {'script', 'style', 'noscript', 'template', 'nav', 'header', 'footer', 'aside', 'blockquote'}
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class ReferencedSites(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.stack = []; self.links = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = tag in SKIP or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
        hidden = hidden or bool(self.stack and self.stack[-1]['hidden'])
        if tag in VOID:
            self.handle_data(' ')
            return
        self.stack.append({'tag': tag, 'text': '', 'links': [], 'hidden': hidden,
                           'href': attrs.get('href') if tag == 'a' else None})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID: self.handle_endtag(tag)

    def handle_data(self, data):
        if self.stack and not self.stack[-1]['hidden']:
            self.stack[-1]['text'] = (self.stack[-1]['text'] + data)[:1001]

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack)-1, -1, -1)
                      if self.stack[i]['tag'] == tag), None)
        if index is None: return
        while len(self.stack) > index:
            node = self.stack.pop()
            if node['hidden']: continue
            text = node['text']
            if node['href']: node['links'].append(node['href'])
            urls = list(dict.fromkeys(node['links']))
            if (node['tag'] in BLOCKS | {'a'} and len(text) <= 1000
                    and len(urls) == 1 and REFERENCE.search(text)):
                if urls[0] not in self.links: self.links.append(urls[0])
            if self.stack:
                parent = self.stack[-1]
                # Never join a declaration in one article/section with a CTA
                # in another. Inline markup and layout divs remain transparent.
                if node['tag'] in BOUNDARIES:
                    parent['text'] = 'x' * 1001
                else:
                    parent['text'] = (parent['text'] + text + (' ' if node['tag'] in BLOCKS else ''))[:1001]
                parent['links'] = list(dict.fromkeys(parent['links'] + urls))[:2]


def referenced_sites(html):
    return ReferencedSites(html).links
