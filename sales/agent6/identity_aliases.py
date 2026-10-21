"""Source-bound owner aliases, never a cross-domain company merge key."""
import re
import unicodedata
from sales.db import domain
from sales.commercial.indexed_jobs import same_company_name


def graphic_key(name):
    return ''.join(c for c in unicodedata.normalize('NFKC', name or '').casefold() if c.isalnum())


def match(identity, cited_name, source):
    public = identity.get('name') or ''
    out = {'matched': False, 'public_name': public, 'original_name': cited_name,
           'basis': 'unresolved', 'source_url': source.get('url')}
    if identity.get('identity_status') != 'verified' or identity.get('identity_conflicts'):
        return out
    official = identity.get('website') or ''
    if official and domain(official) != domain(source.get('url','')) and not source.get('request_identity_linked'):
        return out
    if same_company_name(public, cited_name or ''):
        return {**out, 'matched': True, 'basis': 'exact_name_existing_identity_checks'}
    if not source.get('original') or source.get('editorial') or source.get('document_units') or source.get('allowed_ranges'):
        return out
    if not official or domain(official) != domain(source.get('url', '')):
        return out
    from .completion import source_role
    if source_role(source)['role'] not in ('UNKNOWN', 'AGENCY'):
        return out
    key = graphic_key(public)
    # No initials, substring similarity, token reordering or fuzzy edit distance.
    if len(key) < 6 or key != graphic_key(cited_name):
        return out
    text = source.get('text', '')
    if not cited_name or cited_name not in text:
        return out
    footer = [line for line in text.splitlines() if re.search(r'©|copyright|ragione sociale', line, re.I)]
    host = graphic_key(domain(official).removeprefix('www.').rsplit('.', 1)[0])
    if key != host and not any(key in graphic_key(line) for line in footer):
        return out
    return {**out, 'matched': True, 'basis': 'graphic_alias_on_verified_owner_domain',
            'official_domain': domain(official), 'quote': cited_name}
