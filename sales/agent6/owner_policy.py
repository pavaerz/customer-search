"""User exclusions supported by owner-scoped evidence, not sector/budget guesses."""
import re

from sales.commercial.identity import owner_html
from sales.commercial.indexed_jobs import same_company_name
from sales.commercial.target_fit import excluded_legal_form,group_evidence
from sales.db import domain
from sales.extract import parse_page,types,nodes
from sales.research_evidence import owned_organizations

PUBLIC_NAME=re.compile(r'^(?:Comune di|Città Metropolitana di|Provincia di|Ministero\b|'
                       r'Azienda (?:USL|Unità Sanitaria Locale)|AUSL\b)',re.I)


def exclusions(pages,identity,owner_verified):
    if not owner_verified:return []
    name=identity.get('name') or '';result=[]
    for page in pages:
        if domain(page['url'])!=domain(identity.get('website') or page['url']):continue
        parsed=parse_page({**page,'html':owner_html(page['html'])})
        def add(code,quote,method):
            result.append({'code':code,'actor':name,'url':page['url'],'quote':quote,
                           'method':method,'checked_at':page.get('checked_at')})
        # The existing identity resolver must already have verified the owner.
        # A bare uppercase "SPA" in a wellness brand is not a legal declaration.
        if re.search(r'\bS\.\s*p\.\s*A\.?',name,re.I):
            add('excluded_legal_form',name,'verified_owner_name')
        from sales.commercial.geography import REGIONS
        regional_name=any(name.casefold()=='regione '+region.casefold() for region in REGIONS)
        private_legal_name=bool(re.search(r'\bS\.?\s*[rna]\.?\s*[lc]\.?\b',name,re.I))
        if (PUBLIC_NAME.search(name) or regional_name) and not private_legal_name:
            add('public_administration',name,'verified_public_owner_name')
        organizations=owned_organizations(parsed,domain(page['url']))
        if not parsed.get('job') and not parsed.get('multi_job'):
            organizations += [n for n in nodes(parsed['doc'].schemas) if
                              'GovernmentOrganization' in types(n) and
                              isinstance(n.get('url'),str) and domain(n['url'])==domain(page['url'])]
        for org in organizations:
            orgname=org.get('legalName') or org.get('name') or ''
            if not same_company_name(orgname,name):continue
            if org.get('legalName') and excluded_legal_form(org['legalName']):
                add('excluded_legal_form',org['legalName'],'owned_organization_legal_name')
            if 'GovernmentOrganization' in types(org):
                add('public_administration',orgname,'owned_government_organization')
        for claim in identity.get('identity_evidence',[]):
            quote=claim.get('quote','')
            if claim.get('method')=='legal_owner_scope' and excluded_legal_form(claim.get('name','')):
                add('excluded_legal_form',quote,'verified_legal_owner_scope')
        for fact in group_evidence(parsed['text'],name):
            add('large_group',fact['quote'],'owner_group_self_description')
    return list({(r['code'],r['url'],r['quote']):r for r in result}.values())


def selected_subject_exclusions(body):
    """Apply explicit user scope to a *cited subject*, not the whole source.

    Full owner identity is needed to promote a contact, but not to establish
    that the selected, literally cited S.p.A. falls outside the requested scope.
    Never blacklist a host or borrow a publisher/client's legal form.
    Called only after the original citations passed decision validation.
    """
    raw=body.get('ai_decision') or {}
    name=body.get('entity_name') or ''
    if (not body.get('original') or body.get('validation_status')!='ACCEPTED'
            or raw.get('subject_role') not in ('OWNER','REQUESTER','MENTIONED') or not name):
        return []
    from .owner_names import verified
    result=[]
    if raw.get('subject_role') in ('OWNER','REQUESTER') and verified(body.get('identity',{}),name):
        result.extend(body.get('commercial_exclusions') or [])
    for fact in body.get('facts',[]):
        quote=fact.get('quote') or ''
        if fact.get('field')!='entity' or not fact.get('original'):continue
        if not re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',quote,re.I):continue
        dotted=bool(re.search(r'\bS\.\s*p\.\s*A\.?$',name,re.I))
        spelled=bool(re.search(r'\bsocietà per azioni$',name,re.I))
        # Bare Spa may mean wellness. Accept only a literal, adjacent legal
        # ownership statement, not a VAT number or a different company's form.
        legal_context=bool(re.search(r'\bspa$',name,re.I) and re.search(
            re.escape(name)+r'\s*[,;–—-]?\s*società\s+(?:con\s+socio\s+unico|per\s+azioni)\b',quote,re.I))
        if dotted or spelled or legal_context:
            result.append({'code':'excluded_legal_form','actor':name,'url':fact['url'],
                           'quote':quote,'method':'validated_subject_legal_form',
                           'checked_at':fact.get('checked_at'),'document_id':fact.get('document_id'),
                           'document_start':fact.get('document_start'),'document_end':fact.get('document_end')})
    return list({(p['code'],p['url'],p['quote']):p for p in result}.values())


def apply_user_scope(body):
    """Keep raw AI judgment, transparently stop a proved user exclusion."""
    proofs=selected_subject_exclusions(body)
    if not proofs:return body
    result=dict(body)
    result.update(commercial_exclusions=proofs,decision_authority='explicit_user_exclusion',
                  decision='NOT_INTERESTING',state='REJECTED',priority='low',
                  reason='Soggetto escluso dalle preferenze commerciali: '+', '.join(
                      {'excluded_legal_form':'S.p.A.','public_administration':'pubblica amministrazione',
                       'large_group':'grande gruppo'}.get(p['code'],p['code']) for p in {p['code']:p for p in proofs}.values())+'.',
                  next_verification='',research_action={'type':'STOP','query':'','link_id':'','question':''},
                  user_scope={'status':'EXCLUDED','basis':'attributed_original_evidence',
                              'ai_decision':(body.get('ai_decision') or {}).get('decision')})
    return result
