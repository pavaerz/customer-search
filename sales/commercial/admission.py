"""Conclusive metadata exclusions shared by discovery, inspection and retries.

Absence of a signal is not a conclusive exclusion: unknown companies retain
the planner's exploration allowance. Metadata never establishes a buyer.
"""
import re
from urllib.parse import urlsplit


def exclusion(item, engine):
    from .source_intelligence import exclusion as source_exclusion
    if reason:=source_exclusion(item,engine):return reason
    title=str(item.get('title') or '')
    snippet=str(item.get('snippet') or item.get('content') or '')
    path=urlsplit(item.get('url') or '').path
    text=title+' '+snippet
    if re.search(r'/(?:sitemap|mappa-sito)(?:[./_-]|$)',path,re.I):return 'non_commercial_page'
    if re.search(r'\bMVP\b',text,re.I) and not re.search(r'Microsoft\s+MVP',text,re.I) and re.search(r'\b(?:volley|pallavolo|campionato|coppa|finale|giocatore|basket|premiat\w*)\b',text,re.I):
        if not re.search(r'\b(?:software|applicazione|piattaforma|minimum viable product|sviluppatore|developer)\b',snippet,re.I):return 'sports_mvp_not_software'
    if re.search(r'bootcamp|campi.estivi|corso di formazione',title+' '+path,re.I):
        from .intent import request_clause
        if not request_clause(snippet):return 'training_not_request'
    if re.search(r'voucher|fondo perduto|bando|incentivi',title,re.I):
        from .intent import request_clause
        from .relevance import technical_request
        clause=request_clause(snippet) or ''
        if not clause or not technical_request(clause):return 'funding_information_not_request'
    if re.search(r'/(?:articles|articoli)/',path,re.I):
        from .intent import request_clause
        if engine=='WEBSITE_REBUILD' or not request_clause(snippet):return 'editorial_not_company'
    if engine=='WEBSITE_REBUILD' and re.search(r'\b(?:software|gestionale|ERP)\s+(?:\w+\s+){0,2}per\s+(?:officin|aziend|imprese|negoz|ristorant)',text,re.I):
        return 'software_supplier_not_customer'
    if re.search(r'nuovo sito targato wordpress|just another wordpress',title,re.I):
        from .relevance import technical_request
        from .intent import request_clause
        clause=request_clause(snippet) or ''
        if not clause or not technical_request(clause):return 'cms_credit_not_technical_request'
    if listing_url(item.get('url','')):return 'generic_job_listing'
    return None


def listing_url(url):
    """Known index route, not every page on a job publisher."""
    u=urlsplit(url);host=(u.hostname or '').removeprefix('www.')
    from urllib.parse import unquote
    if host in ('bebee.com','it.bebee.com') and re.match(r'^/(?:[a-z]{2}/)?jobs/(?:role|remote)(?:/|$)',unquote(u.path),re.I):return True
    return host=='lavoro.it' and bool(re.fullmatch(r'/[^/]+/[^/]+/?',u.path)) and not re.search(r'/(?:annuncio|offerta|jobs|job)/',u.path,re.I)
