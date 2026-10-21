"""Website observations over pages acquired through the protected HTTP client.

No network here. Missing measurements are UNKNOWN; HTML presence is not a
rendering, performance, accessibility-compliance or successful form submission.
"""
import re
from urllib.parse import urljoin,urlsplit
from sales.db import digest,domain
from sales.extract import Document
from sales.content_policy import require_non_pdf,ExcludedPDF
from .source_access import inspect

OFFER=re.compile(r'prodott|serviz|catalog|lavorazion|soluzion|product|service',re.I)
CONTACT=re.compile(r'contatt|preventiv|richied|contact|request|quote',re.I)
SOLUTION=re.compile(r'\b(?:shop|store|e.?commerce|negozio online|acquista|prenota|booking|prenotazioni|portale|area (?:clienti|riservata)|configuratore)\b',re.I)


Head = Document  # Compatibility name; canonical extraction has one implementation.


def public_links(page):
    """Commercial and contact pages only; no PDF or inferred URL paths."""
    out=[]
    for link in Document(page.get('html','')).links:
        url=urljoin(page['url'],link['url']);label=link['text']
        if urlsplit(url).scheme not in ('http','https') or domain(url)!=domain(page['url']):continue
        try:require_non_pdf(url)
        except ExcludedPDF:continue
        if re.search(r'logout|delete|unsubscribe|add-to-cart|checkout|\?',url,re.I):continue
        kind='contact' if CONTACT.search(label) else 'offering' if OFFER.search(label) else None
        if kind and url not in [x['url'] for x in out]:out.append({'url':url,'label':label,'purpose':kind})
    return sorted(out,key=lambda v:v['purpose']!='contact')


def external_solutions(page):
    """Links declared by the official site, not proof of ownership or adequacy."""
    out=[]
    for link in Document(page.get('html','')).links:
        url=urljoin(page['url'],link['url'])
        if urlsplit(url).scheme not in ('http','https') or domain(url)==domain(page['url']):continue
        if not SOLUTION.search(link['text']):continue
        try:require_non_pdf(url)
        except ExcludedPDF:continue
        if re.search(r'logout|delete|unsubscribe|add-to-cart|checkout',url,re.I):continue
        if url not in [x['url'] for x in out]:out.append({'url':url,'label':link['text'],'source_url':page['url'],
            'checked_at':page.get('checked_at'),'source_hash':digest(page.get('html',''))})
    return out


def audit(pages,browser=None,attempts=()):
    observations=[];summaries=[];seen=set();solutions=[]
    def observe(page,code,status,value,*,severity='info',category='TECHNICAL_ISSUES',impact='',action='',method='html',journey=None):
        proof={'url':page['url'],'checked_at':page.get('checked_at'),
            'content_hash':digest(page.get('html','')),'method':method,'value':value}
        item={'id':digest(str([page['url'],code,value]))[:24],'code':code,'status':status,
            'severity':severity,'dimension':category,'evidence':proof,
            'impact':impact,'action':action,'certainty':'MEASURED' if status!='UNKNOWN' else 'UNKNOWN',
            'measurement_status':'NOT_MEASURED' if status=='UNKNOWN' else 'OBSERVED',
            'journey':journey}
        observations.append(item)
    for page in pages:
        require_non_pdf(page)
        # Third-party systems supply counterevidence only. Their defects and
        # identity cannot contribute to the company's website rebuild score.
        if page.get('purpose')=='external_solution':continue
        if page['url'] in seen:continue
        seen.add(page['url']);access=inspect(page)
        summary={'url':page['url'],'checked_at':page.get('checked_at'),'access':access,
                 'content_hash':digest(page.get('html',''))}
        summaries.append(summary)
        http=page.get('status')
        observe(page,'http_status','PASS' if http==200 else 'ISSUE' if http in (404,410) else 'UNKNOWN',
            http,method='http',severity='major' if http in (404,410) else 'info')
        if not access['content_read']:
            observe(page,'public_content','UNKNOWN',access['status'],method='access_check')
            continue
        d=Head(page.get('html',''));links=public_links(page)
        if page.get('purpose')!='external_solution':
            for link in external_solutions(page):
                target=next((p for p in pages if p.get('requested_url',p['url'])==link['url']),None)
                access_result=inspect(target) if target else {'content_read':False,'status':'NOT_READ'}
                solutions.append({**link,'access':access_result,'adequacy':'UNKNOWN',
                    'text':Document(target.get('html','')).text[:1800] if access_result['content_read'] else None,
                    'target_hash':digest(target.get('html','')) if target else None,
                    'basis':'official_outbound_link_not_verified_ownership_or_adequacy'})
        summary.update(title=d.title,links=links,headings=d.headings,
                       contact_forms=len(d.forms),text_characters=len(d.text))
        observe(page,'https','PASS' if urlsplit(page['url']).scheme=='https' else 'ISSUE',urlsplit(page['url']).scheme,severity='moderate',action='Verificare configurazione HTTPS; non implica rifacimento.')
        observe(page,'redirects','MEASURED' if page.get('requested_url') else 'UNKNOWN',
            {'requested':page.get('requested_url'),'final':page['url']},method='http')
        for code,value in [('title',d.title),('meta_description',d.meta.get('description')),
                           ('canonical',d.canonicals),('viewport',d.meta.get('viewport')),
                           ('h1',[h['text'] for h in d.headings if h['tag']=='h1']),('structured_data',d.schemas)]:
            observe(page,code,'PASS' if value else 'ISSUE',value or None,severity='minor',
                category='CONTENT_AND_STRUCTURE' if code in ('title','meta_description','h1') else 'TECHNICAL_ISSUES',
                action='Controllo puntuale del documento; assenza del tag non dimostra un progetto completo.')
        observe(page,'images_without_alt','ISSUE' if any('alt' not in i for i in d.images) else 'PASS',
            {'total':len(d.images),'missing_alt':sum('alt' not in i for i in d.images)},severity='minor')
        observe(page,'navigation','MEASURED',{'links':len(d.links),'commercial_links':links},category='CONTENT_AND_STRUCTURE')
        observe(page,'contact_forms','MEASURED',{'count':len(d.forms),'submission_tested':False},category='CONTENT_AND_STRUCTURE')
        observe(page,'cta_presence','MEASURED',{'labelled_contact_paths':[x for x in links if x['purpose']=='contact'],
            'mailto':sum(l['url'].startswith('mailto:') for l in d.links)},category='CONTENT_AND_STRUCTURE')
        for code in ('responsive','form_delivery','performance','site_creation_date','complete_link_coverage'):
            observe(page,code,'UNKNOWN',None,method='not_measured')
        for link in links:
            target=next((p for p in pages if p.get('requested_url',p['url'])==link['url'] or p['url']==link['url']),None)
            if target is not None and target.get('status') in (404,410):
                observe(page,'broken_commercial_path','ISSUE',{'target':link['url'],'label':link['label'],'http':target['status']},
                    severity='major',category='CONTENT_AND_STRUCTURE',method='http',journey=link['purpose'],
                    impact='Il percorso indicato non raggiunge la pagina commerciale.',action='Verificare la struttura dei percorsi; un singolo link può richiedere una correzione limitata.')
    browser=browser or {}
    findings={str([f.get('url'),f.get('viewport'),f.get('code'),f.get('quote')]):f for f in browser.get('findings',[])+browser.get('independent_findings',[])}
    for finding in findings.values():
        source=next((p for p in pages if p['url']==finding.get('url')),None)
        measured=next((p for p in browser.get('pages',[]) if p.get('url')==finding.get('url') and p.get('viewport')==finding.get('viewport') and p.get('complete') and p.get('scope')=='rendered'),None)
        if not source or not measured:continue
        if finding.get('code') not in ('mobile_content','desktop_content','horizontal_overflow','obstructed_controls'):continue
        observe(source,finding['code'],'ISSUE',{'quote':finding['quote'],'viewport':finding.get('viewport'),
            'measurements':measured.get('measurements',{})},severity=finding.get('severity','moderate'),
            method='browser_two_measurements',journey='navigation',impact='Contenuti o controlli non interamente fruibili nella misura eseguita.',
            action='Esaminare il percorso nel suo insieme; il rilievo non prova da solo la necessità di rifacimento.')
    for summary in summaries:
        complete=[p for p in browser.get('pages',[]) if p.get('url')==summary['url'] and p.get('complete') and p.get('scope')=='rendered']
        if any(p.get('viewport')==390 for p in complete):
            issue=any(o['evidence']['url']==summary['url'] and o['code'] in ('mobile_content','horizontal_overflow','obstructed_controls') and o['evidence']['method']=='browser_two_measurements' and o['evidence']['value'].get('viewport')==390 for o in observations)
            for o in observations:
                if o['evidence']['url']==summary['url'] and o['code']=='responsive':
                    o.update(status='ISSUE' if issue else 'PASS',certainty='MEASURED')
                    o['evidence'].update(method='browser_rendered_390',value={'viewport':390,'scope':'sampled_page_only'})
    major=[o for o in observations if o['status']=='ISSUE' and o['severity']=='major' and o['journey']]
    for observation in observations:
        observation['observation_type']='OBSERVED_UX_ISSUE' if observation['code'] in ('broken_commercial_path','mobile_content','desktop_content','horizontal_overflow','obstructed_controls') else 'OBSERVED_TECHNICAL_ISSUE' if observation['status']=='ISSUE' else 'OBSERVED_CHECK'
    from .qualitative_audit import observations as assess_content,design_observations
    qualitative=assess_content(pages)
    observations.extend(qualitative)
    design=design_observations(pages,browser)
    observations.extend(design)
    major.extend(qualitative)
    # A small SEO defect or mobile CSS issue alone can never justify a rebuild.
    breadth=len({o['evidence']['url'] for o in major})>=2 and len({o['dimension'] for o in major})>=2
    scores={}
    for dimension in ('TECHNICAL_ISSUES','CONTENT_AND_STRUCTURE'):
        items=[o for o in observations if o['dimension']==dimension and o['status']=='ISSUE']
        scores[dimension]={'score':min(100,sum({'minor':2,'moderate':8,'major':20}.get(o['severity'],0) for o in items)),
                           'basis':[o['id'] for o in items],'meaning':'observed_issue_weight_not_sales_probability'}
    unknown=sum(o['status']=='UNKNOWN' for o in observations)
    scores['EVIDENCE_CONFIDENCE']={'score':round(100*(len(observations)-unknown)/max(1,len(observations))),
        'basis':'coverage_of_declared_checks_not_company_confidence','unknown':unknown}
    from .progressive_audit import controls
    return {'version':'9.2.1','controls':controls(observations,browser,pages),'pages':summaries,'observations':observations,'attempts':list(attempts),'external_solutions':solutions,
        'design_assessment':{'status':'PARTIAL' if design else 'NOT_ASSESSED',
            'reason':'Gerarchia tipografica limitata agli stili renderizzati osservati; gusto estetico, attualità visiva e coerenza del marchio non dedotti dal solo HTML.',
            'observation_ids':[o['id'] for o in design]},
        'requested_level':browser.get('requested_level'),'completed_level':browser.get('completed_level'),
        'coverage_limits':browser.get('limits',[]),'browser_failure_codes':browser.get('failure_codes',[]),
        'completed_viewports':[{'url':p['url'],'viewport':p.get('viewport')} for p in browser.get('pages',[]) if p.get('complete') and p.get('scope')=='rendered'],
        'scores':scores,'website_opportunity':'REVIEW_COMPLETE_PROJECT' if breadth else 'LIMITED_OR_UNPROVEN',
        'major_evidence_ids':[o['id'] for o in major],'browser_status':'COMPLETE' if browser.get('completed') else 'PARTIAL' if browser.get('pages') else 'UNKNOWN',
        'scope':'sampled_pages_only','purchase_intent':'UNKNOWN','budget':None}
