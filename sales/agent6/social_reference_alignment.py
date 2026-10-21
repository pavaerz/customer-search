"""Abstain from a reference SERP that instead explains the HTTPS protocol.

Metadata controls acquisition priority, never verifies or rejects a requester.
Missing metadata or an exact reference keeps the original-reading path open.
"""
import re
from .social_seeds import reference_token


def assess(items, proposal):
    origin=proposal.get('social_origin') or {}
    if not origin.get('url') or len(items)<3:return None
    try:token=reference_token(origin['url'])
    except ValueError:return None
    if not token:return None
    reference=re.compile(r'(?<![\w-])'+re.escape(token)+r'(?![\w-])',re.I)
    held=[]
    for item in items:
        title=str(item.get('title') or '')
        description=str(item.get('content') or item.get('snippet') or '')
        text=title+' '+description
        # A result explicitly mentioning this post might be useful. Its actual
        # link and independent original evidence are still required later.
        if reference.search(text+' '+str(item.get('url') or '')):return None
        if re.search(r'hiring|vacanc|careers|lavora con noi|cerchiamo|cercasi|'
                     r'freelanc|partita\s*IVA|collaboratori',text,re.I):continue
        protocol_title=bool(re.search(r'\b(?:HTTPS|SSL|TLS)\b',title,re.I))
        protocol_explanation=bool(re.search(r'protocol|encrypt|cifrat|certificat|brows|padlock|connection|'
                                            r'hypertext transfer',description,re.I))
        certificate_authority=bool(re.search(r'certificate authority',description,re.I))
        if len(description.strip())>=40 and protocol_explanation and (protocol_title or certificate_authority):
            held.append(item['url'])
    if len(held)<3 or len(held)/len(items)<.75:return None
    return {'code':'social_reference_protocol_drift','results':len(items),
        'held_urls':held,'basis':'reference_lookup_returned_protocol_explanations',
        'effect':'defer_unrelated_sources_keep_social_lead_unverified',
        'instruction':'These results describe HTTPS/TLS instead of the supplied social post. '
                      'Do not treat them as employers or evidence that the request is absent. '
                      'Keep the post unverified; no domain blacklist or generic topic expansion.'}
