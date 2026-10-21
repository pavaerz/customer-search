"""Explicit names of one verified site owner; no fuzzy or cross-domain joins."""
import json
import re
from html.parser import HTMLParser

from sales.db import domain
from sales.extract import parse_page
from sales.research_evidence import owned_organizations
from sales.commercial.identity import owner_html, THIRD_PARTY
from .identity_aliases import graphic_key
from .entities import vat

THIRD_PARTY_NAMES = re.compile(THIRD_PARTY.pattern + r'|\bclients?\b|comments?', re.I)


class Footers(HTMLParser):
    void = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        inside, blocked = self.stack[-1][1:] if self.stack else (False, False)
        inside = inside or tag == 'footer'
        blocked = blocked or tag in {'script', 'style', 'template', 'noscript', 'form', 'nav'}
        blocked = blocked or 'hidden' in a or a.get('aria-hidden', '').lower() == 'true'
        blocked = blocked or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', a.get('style', ''), re.I))
        blocked = blocked or bool(THIRD_PARTY_NAMES.search(' '.join(a.get(k, '') for k in ('id', 'class', 'aria-label'))))
        if tag in {'p', 'div', 'br', 'li', 'footer'}:
            self.parts.append('\n')
        if tag not in self.void:
            self.stack.append((tag, inside, blocked))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == 'footer':
            self.parts.append('\n[footer boundary]\n')
        if tag in {'p', 'div', 'li', 'footer'}:
            self.parts.append('\n')
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, text):
        if self.stack and self.stack[-1][1] and not self.stack[-1][2]:
            self.parts.append(text)


def collect(page, identity):
    name = identity.get('name') or ''
    host = domain(identity.get('website') or '')
    if (identity.get('identity_status') != 'verified' or identity.get('identity_conflicts')
            or not host or domain(page['url']) != host or not name):
        return []
    from sales.commercial.entity_scope import profile
    if profile(page)['multi_subject']:
        return []
    clean = {**page, 'html': owner_html(page['html'])}
    orgs = list(owned_organizations(parse_page(clean), host))
    owners = [org for org in orgs if any(graphic_key(org.get(k)) == graphic_key(name)
              for k in ('name', 'legalName') if isinstance(org.get(k), str))]
    if not owners:
        return []
    aliases = []
    for org in owners:
        if not all(isinstance(org.get(k), str) and org[k].strip() for k in ('name', 'legalName')):
            continue
        for candidate in (org['name'], org['legalName']):
            if graphic_key(candidate) != graphic_key(name):
                aliases.append({'name': candidate, 'canonical_name': name, 'url': page['url'],
                    'original': True, 'basis': 'owned_schema_name_legalName',
                    'quote': json.dumps({k: org[k] for k in ('name', 'legalName', 'url')}, ensure_ascii=False)})
    # A proprietor's full name needs a literal owner declaration, address and
    # valid-format/check-digit VAT in the SAME visible footer line. A prefix
    # match anywhere in a document is insufficient. This is not a registry check.
    owner = re.compile(r'^\s*('+re.escape(name)+r"\s+di\s+[\wÀ-ÿ’'.-]+(?:\s+[\wÀ-ÿ’'.-]+){1,9})\s+[-–|·]\s+(?:Via|Viale|Piazza|Corso|Località)\b", re.I)
    tax = re.compile(r'\b(?:P\.?\s*I\.?\s*(?:V\.?\s*A\.?)?|Partita\s+IVA)\s*[:.-]?\s*(?:IT\s*)?(\d{11})\b', re.I)
    lines = [' '.join(line.split()) for line in ''.join(Footers(clean['html']).parts).splitlines()]
    # A brand and its legal form may be split across a three-line owner block.
    # Require the exact brand + legal suffix, address, and the SAME verified
    # VAT as the owner identity. This does not infer aliases from search titles.
    compact=[line for line in lines if line]
    legal_name=re.compile(r'^('+re.escape(name)+r'\s+(?:s\.?\s*r\.?\s*l\.?\s*s\.?|s\.?\s*r\.?\s*l\.?|s\.?\s*n\.?\s*c\.?|s\.?\s*a\.?\s*s\.?|s\.?\s*p\.?\s*a\.?))$',re.I)
    known_tax=re.sub(r'\D','',identity.get('legal_id') or '')
    for index,line in enumerate(compact):
        match=legal_name.fullmatch(line)
        block=compact[index:index+3]
        if not match or len(block)!=3 or not known_tax or '[footer boundary]' in block:
            continue
        quote='\n'.join(block);number=tax.search(block[2])
        if (not re.match(r'^(?:Via|Viale|Piazza|Corso|Località)\b',block[1],re.I)
            or THIRD_PARTY_NAMES.search(quote) or not number
            or number[1]!=known_tax or not vat('IT'+number[1])):
            continue
        aliases.append({'name':match[1],'canonical_name':name,'url':page['url'],
                        'original':True,'basis':'owned_legal_footer','quote':quote,
                        'legal_id':'IT'+number[1]})
    for line in lines:
        if THIRD_PARTY_NAMES.search(line):
            continue
        match = owner.search(line); number = tax.search(line)
        if not match or not number or not vat('IT'+number[1]):
            continue
        legal = identity.get('legal_id')
        if legal and re.sub(r'\D', '', legal) != number[1]:
            continue
        aliases.append({'name': match[1], 'canonical_name': name, 'url': page['url'],
                        'original': True, 'basis': 'owned_proprietor_footer',
                        'quote': line, 'legal_id': 'IT'+number[1]})
    # Conflicting full owner names or VATs require another check, not a union.
    if len({graphic_key(a['name']) for a in aliases}) > 1 or len({a['legal_id'] for a in aliases if a.get('legal_id')}) > 1:
        return []
    return list({(a['name'], a['basis'], a['quote']): a for a in aliases}.values())


def verified(identity, name):
    if not identity.get('verified') or not name:
        return False
    if graphic_key(identity.get('name')) == graphic_key(name):
        return True
    for alias in identity.get('verified_names', []):
        if (alias.get('original') and alias.get('basis') in {'owned_schema_name_legalName', 'owned_proprietor_footer', 'owned_legal_footer'}
                and graphic_key(alias.get('canonical_name')) == graphic_key(identity.get('name'))
                and graphic_key(alias.get('name')) == graphic_key(name)
                and domain(alias.get('url') or '') == identity.get('domain')
                and re.search(r'(?<!\w)'+re.escape(alias['name'])+r'(?!\w)', alias.get('quote', ''), re.I)):
            return True
    return False
