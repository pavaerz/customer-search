"""Observed article/main context, not company identity or commercial evidence.

No requests and no guessed selectors per host. Only unique literal lines can
be mapped back to a stored document; ambiguous text keeps its original scope.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from sales.extract import web_reference,layout_text_boundary

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
        'meta', 'param', 'source', 'track', 'wbr'}
BLOCK = {'p', 'div', 'section', 'article', 'li', 'br', 'h1', 'h2', 'h3'}
NON_CONTENT = re.compile(r'(?:^|[\s_-])(?:nav|menu|sidebar|footer|comments?|related|'
                         r'recommended|newsletter|cookie|login|share|sharing)(?:$|[\s_-])', re.I)


class Context(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []
        self.links = []

    def state(self):
        return self.stack[-1][1:3] if self.stack else (0, False)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        level, hidden = self.state()
        marks = ' '.join((a.get('id', ''), a.get('class', '')))
        hidden = hidden or tag in {'nav', 'footer', 'aside', 'script', 'style',
                                   'template', 'noscript', 'form'} or 'hidden' in a
        # A semantic article header holds its title/date/introduction; the site
        # header outside an article is navigation. Do not discard both alike.
        hidden = hidden or (tag == 'header' and level < 2)
        hidden = hidden or a.get('aria-hidden', '').lower() == 'true'
        hidden = hidden or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', a.get('style', ''), re.I))
        # Body layout flags (e.g. "no-sidebar", "menu-link-color") describe
        # the theme, not a non-content subtree.
        layout_container = any(re.fullmatch(r'(?:[\w]+[-_])*(?:site-content|main-content|content-area)', token)
                               for token in marks.split())
        excluded_marks = any(NON_CONTENT.search(token) and not re.search(r'(?:^|-)no-|without-', token)
                             and not (layout_container and re.search(
                                 r'(?:^|[-_])sidebar[-_](?:enabled|disabled|left|right|none)$', token))
                             and not (tag == 'article' and token.startswith('share-'))
                             for token in marks.split()) if tag not in {'body', 'html'} else False
        hidden = hidden or excluded_marks or a.get('role') in {'navigation', 'complementary'}
        if tag == 'main' or a.get('role') == 'main' or set(marks.split()) & {'page-content', 'wp-main-content', 'main-content'}:
            level = max(level, 1)
        if tag == 'article' or set(marks.split()) & {'content-page-inner'}:
            level = max(level, 2)
        # Elementor's theme post-content widget is the article body, unlike a
        # generic text/heading widget or a list of related posts. Match the
        # framework's semantic marker exactly, independent of publisher host.
        post_body = a.get('data-widget_type') == 'theme-post-content.default'
        post_body = post_body or 'elementor-widget-theme-post-content' in marks.split()
        if post_body or a.get('itemprop') == 'articleBody' or set(marks.split()) & {'entry-content', 'post-content', 'article-body', 'article-content'}:
            level = max(level, 3)
        layout=layout_text_boundary(a)
        if tag in BLOCK or layout:
            self.parts.append((level, '\n'))
        if tag == 'a' and not hidden and level:
            href = web_reference(a.get('href', ''))
            if href:
                self.links.append((level, href))
        if tag not in VOID:
            self.stack.append((tag, level, hidden,layout))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in BLOCK:
            self.parts.append((self.state()[0], '\n'))
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if any(item[3] for item in self.stack[i:]):
                    self.parts.append((self.state()[0], '\n'))
                del self.stack[i:]
                break

    def handle_data(self, data):
        level, hidden = self.state()
        if level and not hidden:
            self.parts.append((level, data))


def observe(page, text):
    parser = Context()
    parser.feed(page['html'])
    # Prefer the narrow article body over surrounding site main/layout.
    level = max((n for n, t in parser.parts if t.strip()), default=0)
    if not level:
        return {'basis': 'no_explicit_content_boundary', 'ranges': [], 'links': []}
    content = ''.join(t if n == level else '\n' for n, t in parser.parts)
    lines = {' '.join(line.split()) for line in content.splitlines() if line.strip()}
    occurrences = {}
    for match in re.finditer(r'[^\n]+', text):
        occurrences.setdefault(match[0], []).append(list(match.span()))
    # Ambiguous labels at the content boundaries stay excluded: adjacency in
    # flattened text alone cannot prove an occurrence belongs to this subtree.
    anchors = sorted(occurrences[line][0] for line in lines
                     if len(occurrences.get(line, [])) == 1)
    # Repeated card labels between uniquely located anchors can remain in their
    # literal paragraph. Do not pull identical menus from outside the body.
    ranges = sorted(span for line in lines for span in occurrences.get(line, [])
                    if anchors and anchors[0][0] <= span[0] and span[1] <= anchors[-1][1])
    merged = []
    for start, end in ranges:
        if merged and not text[merged[-1][1]:start].strip():
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return {'basis': 'literal_unique_lines_in_content_landmark', 'ranges': merged,
            'links': list(dict.fromkeys(urljoin(page['url'], href)
                                       for n, href in parser.links if n == level))}


def editorial(packet, unit, flow, owner):
    """Content priority is an input view, never a publisher/client attribution."""
    if unit['origin'] != 'page':
        return False
    # Public proposals and editorial pages need their observed main text even
    # without Article JSON-LD. A content boundary does not establish its owner.
    # An unverified agency service page still needs its site-level identity and
    # careers navigation (C46 Aptica). A generic <main> alone must not hide those;
    # actual editorial metadata continues to restrict agency articles as before.
    return bool(flow == 'NEWS' or (not owner and (packet.get('editorial_metadata', False)
                         or (flow != 'AGENCIES' and packet.get('content_context', {}).get('ranges')))))


def select_links(packet, unit, flow, owner, limit=8):
    # Fragment/cookie controls on a job page are not another source to read.
    # Application controls remain separately available as response channels.
    current = packet['final_url'].split('#')[0]
    links = [link for link in packet['links'] if link['url'].split('#')[0] != current]
    if unit.get('discussion_scope'):
        allowed = set(unit['discussion_scope']['links'])
        return [{**link, 'context':'source_content'} for link in links if link['url'] in allowed][:limit]
    if unit.get('career_role'):
        permitted=set(unit['career_role']['links'])
        links=[link for link in links if link['url'] in permitted]
    if not editorial(packet, unit, flow, owner):
        return links[:limit]
    context = packet.get('content_context', {})
    observed = {url: i for i, url in enumerate(context.get('links', []))}
    # Keep stable IDs and URL filters from evidence.packet. A content link is
    # not proof that the destination is official or that its business has need.
    candidates = [link for link in links if link['label'].strip()
                  and link['url'].split('#')[0] != current]
    if context.get('basis') == 'literal_unique_lines_in_content_landmark':
        # Fewer than eight meaningful links is fine. Never backfill an article
        # with publisher navigation, hidden controls or commenter destinations.
        candidates = [link for link in candidates if link['url'] in observed]
    return [{**link, 'context': 'source_content' if link['url'] in observed else 'other_page_link'}
            for link in sorted(candidates, key=lambda item: observed.get(item['url'], len(observed)))[:limit]]


def passage_hints(packet, unit):
    """Preserve whole literal ranges; never turn a link label into an entity."""
    if unit.get('career_role'):return {}
    ranges = packet.get('content_context', {}).get('ranges', [])
    if not ranges:
        return {}
    hints = [[a, min(b, a + 600)] for a, b in ranges[:2]]
    if len(ranges) == 1 and ranges[0][1] - ranges[0][0] > 1800:
        a, b = ranges[0]
        for point in ((a + b) // 2, max(a, b - 800)):
            hints.append([point, min(b, point + 400)])
    # Names/cards near content links may occur after a long introduction.
    content_urls = set(packet['content_context']['links'])
    for link in packet['links']:
        if link['url'] not in content_urls or len(link['label'].strip()) < 4:
            continue
        for match in re.finditer(re.escape(link['label']), unit['text']):
            if any(a <= match.start() and match.end() <= b for a, b in ranges):
                hints.append(list(match.span()))
                break
        if len(hints) >= 8:
            break
    return {'allowed_ranges': ranges, 'preferred_spans': hints}
