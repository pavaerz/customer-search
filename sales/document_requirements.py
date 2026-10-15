"""Assign an evidence purpose before interpreting an inaccessible document."""
import re
from urllib.parse import urlsplit


def requirement(url, *, original=False, solution=False, label=''):
    text=urlsplit(url).path+' '+label
    if original:return {'importance':'indispensable','requirement':'original_source'}
    if solution:return {'importance':'indispensable','requirement':'solutions'}
    if re.search(r'privacy|cookie|/legal',text,re.I):
        return {'importance':'complementary','requirement':'legal_background'}
    if re.search(r'contatt|contact',text,re.I):
        return {'importance':'substitutable','requirement':'contact'}
    if re.search(r'chi.siamo|about|azienda|company',text,re.I):
        return {'importance':'substitutable','requirement':'identity'}
    # Product, offer and counterproof pages cannot be dismissed just because
    # another page contains the generic word "services".
    return {'importance':'important','requirement':'solutions'}


def unresolved(item,coverage):
    if item['importance'] in ('complementary','irrelevant'):return False
    if item['importance']=='substitutable' and coverage.get(item['requirement']) is True:return False
    return True
