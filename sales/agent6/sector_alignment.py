"""Detect a wholly unanchored sector SERP before spending on its originals.

This is a query-level abstention, not company qualification. Sparse metadata,
mixed result sets and bounded subject lookups remain with the original reader.
Receipts remain available to the planner; no domains are blacklisted.
"""
import re
import unicodedata

from .query_pipeline import sector_terms


def words(text):
    text=''.join(c for c in unicodedata.normalize('NFKD',text.casefold())
                 if not unicodedata.combining(c))
    # Italian singular/plural endings only; no arbitrary prefix matching.
    return {w[:-1] if len(w)>5 and w[-1] in 'aeio' else w
            for w in re.findall(r'[a-z]{4,}',text)}


def assess(items,proposal):
    if (proposal.get('strategy')!='official_company_sector_region'
            or proposal.get('selection')=='verification'
            or proposal.get('expected_entity') or proposal.get('research_parent')
            or len(items)<3):
        return None
    anchors=words(' '.join(sector_terms(proposal.get('query',''))))
    if not anchors:return None
    held=[]
    for item in items:
        description=item.get('content') or item.get('snippet') or ''
        text=item.get('title','')+' '+description
        # Missing descriptions must not be interpreted as an unrelated source.
        if anchors & words(text):return None
        if len(description.strip())>=40 and len(words(text))>=6:
            held.append(item['url'])
    if len(held)<3 or len(held)/len(items)<0.75:return None
    return {'code':'sector_results_without_query_anchor','results':len(items),
            'held_urls':held,
            'sector_terms':sector_terms(proposal['query']),
            'basis':'metadata_only_no_sector_overlap_in_entire_result_set',
            'effect':'hold_this_query_results_not_reject_companies',
            'instruction':'None of these result descriptions mentions a sector term from the query. '
                          'Do not spend original verification on this set. Reconsider the query: '
                          'try a shorter sector and territory expression or a meaningful sector synonym. '
                          'This is insufficient discovery evidence, not absence of business demand; '
                          'do not blacklist these domains or treat it as a provider error.'}
