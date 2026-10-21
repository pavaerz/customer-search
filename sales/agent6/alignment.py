"""Commercial interest, evidence and contact are independent; no network or writes."""
import re
from urllib.parse import urlsplit
from sales.db import domain

SKILLS = re.compile(r'\b(?:HTML|PHP|SCSS|CSS|JavaScript|jQuery|React|Next\.?js|WordPress|WooCommerce|e.?commerce|frontend|front.end|web.?app|MVP)\b|sviluppo (?:web|siti)|web develop', re.I)
DIGITAL = re.compile(r'digital|software|programm|svilupp|developer|web|tecnic|technical|designer|UX|UI', re.I)
UNRELATED = re.compile(r'\b(?:camerier|cuoch|magazzinier|autist|addett[oi] alle pulizie|waiter|warehouse worker)\w*', re.I)


def affinity(body):
    facts = [f for f in body.get('facts', []) if f.get('original') and f.get('field') in ('request', 'technical', 'scope')]
    text = '\n'.join(f.get('quote', '') for f in facts)
    value = ('HIGH_AFFINITY' if SKILLS.search(text) else
             'CLEARLY_UNRELATED' if UNRELATED.search(text) and not DIGITAL.search(text) else
             'POSSIBLE_AFFINITY' if DIGITAL.search(text) else 'UNKNOWN_AFFINITY')
    return {'value': value, 'basis': 'original_requested_activity_not_stack_whitelist',
            'evidence': [{'url': f['url'], 'quote': f['quote']} for f in facts]}


def contacts(body):
    """Accept public generic mailboxes, never derive addresses from names/domains.

    Identity extractors supply provenance. A contact from another domain requires
    a linked original document or an attributed contact fact, not a bare URL.
    """
    if not body.get('identity_verified') or not body.get('original'):
        return []
    owned = domain(body.get('official_domain') or '')
    public = []
    for c in body.get('contacts', []):
        value, url = c.get('value', ''), c.get('url', '')
        if not value or urlsplit(url).scheme not in ('http', 'https'):
            continue
        attributed = any(f.get('original') and f.get('field') == 'contact'
                         and f.get('url') == url and value in f.get('quote', '') for f in body.get('facts', []))
        if not (owned and domain(url) == owned) and not attributed:
            continue
        if c.get('type') == 'email' and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
            continue
        if c.get('type') not in ('email', 'phone', 'contact_form', 'form', 'application_link'):
            continue
        if c.get('type')=='application_link':
            from .response_channels import public_url
            if not public_url(value,url) or c.get('attribution')!='observed_owner_response_control' or not attributed:
                continue
        public.append(dict(c))
    return public


def arrangement(body):
    status = body.get('engagement', {}).get('status', 'UNKNOWN')
    if status=='CONTRADICTORY_TERMS':
        return 'UNCLEAR_ARRANGEMENT'
    if status=='UNPAID' and body.get('engagement',{}).get('entrepreneurial'):
        return 'TECHNICAL_COFOUNDER_OPPORTUNITY'
    return {'PAID_CONTRACT': 'PAID_DEVELOPMENT_OPPORTUNITY',
            'COFOUNDER_ROLE': 'TECHNICAL_COFOUNDER_OPPORTUNITY',
            'EQUITY_ONLY': 'EQUITY_ONLY_OPPORTUNITY'}.get(status,
            'FREELANCE_COLLABORATION' if body.get('external') else 'UNCLEAR_ARRANGEMENT')


def startup_profile(body):
    """Expose cited terms, never use a startup label to infer traction or value."""
    patterns = {
        'idea': r'\b(?:idea|vision)\s*:', 'problem': r'\b(?:problem[ae]?|problema)\s*:',
        'product': r'\b(?:prodotto|product|MVP)\s*:', 'stage': r'\b(?:fase|stage)\s*:',
        'founders': r'\b(?:founders?|fondatori)\s*:', 'business_model': r'\b(?:business model|modello di business)\s*:',
        'users_customers': r'\b(?:utenti|clienti|users|customers)\s*:',
        'investment': r'\b(?:investimenti|investment|funding)\s*:',
        'commitment': r'\b(?:impegno|commitment|ore settimanali|hours per week)\s*:',
    }
    original=[f for f in body.get('facts',[]) if f.get('original')]
    return {key: {'status':'DOCUMENTED' if proofs else 'UNKNOWN','evidence':proofs}
            for key, pattern in patterns.items()
            for proofs in [[{'quote':f['quote'],'url':f['url']} for f in original
                            if re.search(pattern,f.get('quote',''),re.I)]]}


def dimensions(body):
    if body.get('decision_engine')=='ai_first_1':
        from .decision import projection
        return projection(body)
    channels = contacts(body)
    qualified = body.get('state') in ('VERIFIED', 'POTENTIAL')
    supported = body.get('original') and body.get('identity_verified') and not body.get('semantic_issues')
    reason = any(f.get('original') and f.get('field') == 'request' for f in body.get('facts', []))
    interest = ('SUPPORTED' if qualified else 'TO_EXPLORE' if supported and reason and body.get('state') != 'REJECTED' else 'UNKNOWN')
    return {
        'COMMERCIAL_INTEREST': interest,
        'EVIDENCE_CONFIDENCE': 'SUPPORTED' if supported and qualified else 'PARTIAL' if supported else 'UNKNOWN',
        'CONTACT_READINESS': 'CONTACT_AVAILABLE' if channels else 'CONTACT_MISSING',
        'OPPORTUNITY_QUALIFIED': qualified,
        'CONTACT_AVAILABLE': bool(channels),
        'READY_FOR_OUTREACH': bool(qualified and channels),
        'public_channels': channels,
        'affinity': affinity(body),
        'arrangement': arrangement(body),
        'startup_profile': startup_profile(body) if body.get('flow')=='STARTUPS' or body.get('engagement',{}).get('entrepreneurial') else None,
        'equity_value': None,
        'sales_probability': None,
    }
