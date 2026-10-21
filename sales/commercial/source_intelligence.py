"""Source-role hypotheses and cheap exclusions; no domain reputation claims."""
import re
from urllib.parse import urlsplit

JUNIOR=re.compile(r'\b(?:stage|tirocinio|tirocini|internship|stagista|junior)\b',re.I)
NON_WEB=re.compile(r'\b(?:addett[ao/i ]+vendit\w*|sales (?:representative|assistant)|venditor\w*|content creator|social media manager|SEO specialist|graphic designer|help[ -]?desk|cybersecurity|data engineer\w*|SAP consultant|consulente SAP)\b',re.I)
ASK=re.compile(r'\b(?:cerchiamo|cerco|cercasi|ricerchiamo|seeking|hiring|looking for|we need|abbiamo bisogno|dobbiamo rifare|richiesta (?:di )?preventivo)\b',re.I)
WEB=re.compile(r'wordpress|woocommerce|front[ -]?end|react|next\.?js|javascript|(?:sito|siti) (?:web|aziendale)|website|web developer',re.I)

def exclusion(item,engine):
    title=str(item.get('title') or '');snippet=str(item.get('snippet') or item.get('content') or '')
    path=urlsplit(item.get('url') or '').path;text=title+' '+snippet
    if engine!='WEBSITE_REBUILD':
        from .demand import metadata_exclusion
        if item.get('demand_version')=='5.1' and (reason:=metadata_exclusion(item)):return reason
        # Primary title is decisive; mentioning a required skill in the footer
        # or snippet cannot turn a sales/content job into development work.
        if JUNIOR.search(title):return 'internship_or_junior'
        if NON_WEB.search(title):return 'incompatible_requested_role'
        from .job_activity import GEO_NO
        if GEO_NO.search(text):return 'explicit_geographic_restriction'
        if re.search(r'co[ -]?founder|cofondator|socio tecnico',title,re.I) and re.search(r'non retribuito|unpaid|equity.only|solo equity|senza compenso',text,re.I):return 'unpaid_founder'
        if not ASK.search(text) and re.search(r'/(?:product-archive|products?|prodotti)/',path,re.I) and not WEB.search(title):return 'product_not_request'
        editorial=bool(re.search(r'\b(?:il caso|case study|guida a|guide to|come funziona|how to|cosa sono|quand[oi].{0,30}IA|recensione)\b',title,re.I))
        if editorial and not ASK.search(snippet):return 'article'
        # Careers shell without any relevant request stays out; absence of
        # snippet on an individual LinkedIn post stays reviewable instead.
        if re.search(r'no (?:open )?positions|nessuna posizione aperta',text,re.I) and not ASK.search(text):return 'careers_without_open_position'
    if engine=='WEBSITE_REBUILD' and re.search(r'(?:divisione|divisone|società controllata|subsidiary|parte del gruppo).{0,60}(?:group|gruppo)|(?:division|subsidiary) of',text,re.I):return 'corporate_group_requires_review'
    return None


def project_request(item):
    text=str(item.get('title') or '')+' '+str(item.get('snippet') or item.get('content') or '')
    return bool(ASK.search(text) and WEB.search(text) and re.search(r'nostr[oa] sito|new business website|rifare|migrazion|migration|custom|checkout|integrazion|integration|progetto|project|MVP',text,re.I) and not re.search(r'offriamo|realizziamo siti|we offer|our services',text,re.I))


def describe(record):
    kind=record.get('source_kind');path=urlsplit(record.get('url','')).path
    mapping={'official_job_hint':'OFFICIAL_CAREERS','job_portal':'JOB_BOARD','article':'ARTICLE','aggregator':'AGGREGATOR','directory':'DIRECTORY','linkedin_job':'SOCIAL_POST','linkedin_post':'SOCIAL_POST','instagram_post':'SOCIAL_POST','company_site_hint':'UNKNOWN','service_seller':'OFFICIAL_COMPANY'}
    family=mapping.get(kind,'UNKNOWN')
    if record.get('agency_signal') and re.search(r'partner|collabora',path,re.I):family='AGENCY_PARTNERSHIP'
    if re.search(r'project|progett|brief',path,re.I) and project_request(record):family='PROJECT_MARKETPLACE'
    return {'family':family,'basis':'url_title_snippet_only','verified_original':False,
      'accessibility':record.get('accessibility','not_checked'),'reliability':'UNKNOWN',
      'publication_verified':False,'not_domain_reputation':True}
