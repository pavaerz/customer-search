"""Literal discussion-post boundaries; never infer authors from comments.

Supported markup is explicit BEM post-page structure. Unknown/ambiguous layouts
keep their prior behavior. This is not a platform-access bypass or a classifier.
"""
from html.parser import HTMLParser
import re
from datetime import date
from urllib.parse import urljoin
from sales.extract import Document, VOID_TAGS

MARKS = {'post-page__title', 'post-page__byline', 'post-page__body', 'post-page__date'}


class Fragments(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.html = html
        self.lines = [0]
        for line in html.splitlines(keepends=True):
            self.lines.append(self.lines[-1] + len(line))
        self.stack, self.found = [], []
        self.feed(html)

    def position(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get('class') or '').split())
        hidden = bool(self.stack and self.stack[-1][3]) or tag in ('script', 'style', 'template', 'noscript')
        hidden |= 'hidden' in a or a.get('aria-hidden') == 'true'
        hidden |= bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', a.get('style') or '', re.I))
        hidden |= any('comment' in c for c in classes)
        if tag not in VOID_TAGS:
            self.stack.append((tag, self.position(), classes & MARKS, hidden))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                _, start, marks, hidden = self.stack[i]
                end = self.html.find('>', self.position()) + 1
                if marks and not hidden and end:
                    self.found.append((marks, self.html[start:end]))
                del self.stack[i:]
                break


def scope(page, text):
    parsed = Fragments(page['html'])
    fields, links = {}, []
    for marks, html in parsed.found:
        for mark in marks:
            fragment = Document(html)
            fields.setdefault(mark, []).append(fragment.text)
            if mark in ('post-page__body', 'post-page__byline'):
                links.extend(urljoin(page['url'], l['url']) for l in fragment.links if l.get('url'))
    # Multiple posts/cards or an absent byline cannot establish this boundary.
    if any(len(fields.get(k, [])) != 1 for k in ('post-page__body', 'post-page__byline', 'post-page__title')):
        return None
    body = fields['post-page__body'][0]
    byline = fields['post-page__byline'][0]
    if len(body) < 40 or not byline.lower().startswith('by ') or len(byline) > 160:
        return None
    ranges, anchors = [], []
    for mark in ('post-page__title', 'post-page__byline', 'post-page__body', 'post-page__date'):
        values = fields.get(mark, [])
        if len(values) != 1 or not values[0] or text.count(values[0]) != 1:
            if mark != 'post-page__date':
                return None
            continue
        value = values[0]
        start = text.index(value)
        ranges.append([start, start + len(value)])
        anchors.append(ranges[-1])
    publication = None
    raw_date = fields.get('post-page__date', [])
    if len(raw_date) == 1:
        match = re.fullmatch(r'on (\w+) (\d{1,2}), (\d{4})', raw_date[0])
        months = 'January February March April May June July August September October November December'.split()
        if match and match[1] in months:
            try:
                publication = date(int(match[3]), months.index(match[1])+1, int(match[2])).isoformat()
            except ValueError:
                pass
    return {'basis': 'unique_literal_post_body_and_byline', 'allowed_ranges': sorted(ranges),
            'preferred_spans': anchors, 'author_label': byline,
            'links': list(dict.fromkeys(links)), 'published_at': publication,
            'limitations': 'Comments excluded, including author replies; they require separate attribution. Publisher is not requester.'}
