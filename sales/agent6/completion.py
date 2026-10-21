"""Source-bound dossier completion. No model, I/O, promotion or guessed facts.

Deterministic observations use the same hashed span contract as model facts.
They complement (never silently replace) validated semantic evidence.
"""
import copy
import re
from sales.db import digest, domain

LEGAL = re.compile(r'(?:proprietà di|ragione sociale\s*:|owned by)\s+'
    r'((?:[A-ZÀ-Ý][\wÀ-ÿ&.-]*\s+){1,6}(?:S\.?\s*r\.?\s*l\.?\s*s?\.?|LLC|Ltd\.?))\b', re.I)
TECH = re.compile(r'web\s*design|wordpress|woocommerce|frontend|front.end|sviluppator|sviluppo (?:web|siti)|web developer', re.I)
EXTERNAL = re.compile(r'freelanc|contractor|collaborator\w* estern|(?:collaborare|professionist|requisiti)[^\n]{0,220}partita\s*IVA', re.I)
CUSTOMER = re.compile(r'cerchiamo partner non clienti|looking for partners not clients', re.I)
VOLUNTEER = re.compile(r'volontari|avvocati|domiciliatari|tutela legale', re.I)
INVITE = re.compile(r'cerchiamo|cercasi|ricerchiamo|alla ricerca|collabora con noi|interessato a collaborare|looking for|seeking', re.I)


def skip_screening(source,flow):
    from .recovery import literal_invitation
    if flow in ('SOCIAL','LINKEDIN','NEWS') or source_role(source)['role'] not in ('UNKNOWN','AGENCY'):return None
    try:return literal_invitation(source,flow)
    except ValueError:return None


def source_role(source):
    """Role of the publication, not proof of the subject's identity."""
    from sales.commercial.target_fit import source_role as classify
    from sales.commercial.indexed_jobs import publisher_host
    from .social import platform
    text=source.get('text','');title=source.get('title','');url=source['url']
    if platform(url):role='SOCIAL'
    elif publisher_host(url):role='JOB_PORTAL'
    elif source.get('editorial'):role='PUBLISHER'
    else:
        found=classify(url,title,text)
        role={'directory':'DIRECTORY','multi_company_catalog':'DIRECTORY','aggregator':'JOB_PORTAL',
            'company_information_portal':'DIRECTORY','sector_portal':'PUBLISHER','editorial':'PUBLISHER',
            'institution':'INSTITUTION','training_provider':'TRAINING_PROVIDER','web_agency':'AGENCY'}.get(found,'UNKNOWN')
    return {'role':role,'domain':domain(url),'page_title':title,
        'basis':'structural_publication_signals_not_subject_identity','original':bool(source.get('original'))}


def legal_identity(text):
    matches=list(LEGAL.finditer(text))
    names={m[1].strip().rstrip('.') for m in matches}
    if len(names)!=1:return None
    m=matches[0];return {'name':m[1].strip().rstrip('.'),'start':m.start(1),'end':m.end(1)}


def prepare(source, analysis, evidence, identity):
    """Complete literal original facts only for a verified, single owner.

    Publishers/social/multi-ad sources cannot borrow legal footer identity.
    AI facts are retained unless an exact owner legal declaration contradicts
    their SEO name. Both old name and replacement provenance are recorded.
    """
    a=copy.deepcopy(analysis);pool=copy.deepcopy(evidence);ident=copy.deepcopy(identity or {})
    role=source_role(source);diagnostic={'method':'source_bound_completion','source_role':role,
        'added_fields':[],'superseded_entity':None,'paid_calls':0}
    text=source.get('text','')
    from .document_units import extract as document_units
    if source.get('document_units') or document_units(source):return a,pool,ident,diagnostic
    if a:
        from .schema import quote,actor_span_valid
        kept=[]
        for f in a.get('facts',[]):
            if f['field']!='entity':kept.append(f);continue
            q=quote(f['ref'],pool)['quote']
            if actor_span_valid(q,0,len(q)):kept.append(f)
            else:
                # Named subject at the start of a literal company-event
                # headline; no inferred domain, budget or digital need.
                m=re.match(r'([A-ZÀ-Ý][\wÀ-ÿ&.-]*(?:\s+[A-ZÀ-Ý][\wÀ-ÿ&.-]*){0,3})\s+(?:lancia|annuncia|inaugura)\b',q)
                if m and a.get('kind')=='COMPANY_SIGNAL' and 'start' in f['ref']:
                    kept.append({**f,'ref':{**f['ref'],'end':f['ref']['start']+m.end(1)}})
                    diagnostic['entity_basis']='literal_named_event_subject_not_official_identity'
                else:a['missing']=list(dict.fromkeys(a.get('missing',[])+['entity']))
        a['facts']=kept
    eligible=(source.get('original') and not source.get('document_units') and
        not source.get('allowed_ranges') and role['role'] not in ('PUBLISHER','DIRECTORY','JOB_PORTAL','SOCIAL','INSTITUTION') and
        ident.get('identity_status')=='verified' and not ident.get('identity_conflicts'))
    if not eligible or not a:return a,pool,ident,diagnostic
    from .schema import quote
    requests='\n'.join(quote(f['ref'],pool)['quote'] for f in a.get('facts',[]) if f['field']=='request')
    retained=[]
    for f in a.get('facts',[]):
        q=quote(f['ref'],pool)['quote']
        if f['field']=='technical' and len(q.split())<=6 and q not in requests:
            contexts=[text[max(0,m.start()-220):m.end()+220] for m in re.finditer(re.escape(q),text)] if q else []
            if not any(INVITE.search(c) and EXTERNAL.search(c) for c in contexts):
                diagnostic.setdefault('withheld_fields',[]).append({'field':'technical','quote':q,'reason':'isolated_service_label_not_requested_skill'})
                a['missing']=list(dict.fromkeys(a.get('missing',[])+['technical']))
                continue
        retained.append(f)
    a['facts']=retained
    legal=legal_identity(text)
    if legal:
        from .qualification import same_company_name
        from .schema import quote
        cited_names=[quote(f['ref'],pool)['quote'] for f in a.get('facts',[]) if f['field']=='entity']
        different=[n for n in cited_names if not same_company_name(n,legal['name']) and not re.fullmatch(r'web agency(?:\s+[\wÀ-ÿ-]+){1,3}',n,re.I)]
        if different:
            diagnostic['blocked_reason']='cited_subject_differs_from_site_owner'
            return a,pool,ident,diagnostic
    if legal:
        ident.update(name=legal['name'],legal_name=legal['name'],page_title=source.get('title'),
            name_provenance={'url':source['url'],'quote':text[legal['start']:legal['end']],
                'start':legal['start'],'end':legal['end'],'content_hash':digest(text),'method':'literal_legal_owner'})
    block={'id':'observed:'+digest(source['url']+text)[:20], 'result_id':a.get('result_id','r1'),
        'url':source['url'],'text':text,'hash':digest(text),'original':True,'offset':0,
        'checked_at':source.get('checked_at'),'document_id':source.get('document_id')}
    pool.append(block)
    def add(field,start,end,replace=False):
        if not (0<=start<end<=len(text)):return
        if replace:a['facts']=[f for f in a.get('facts',[]) if f['field']!=field]
        if any(f['field']==field for f in a.get('facts',[])):return
        a.setdefault('facts',[]).append({'field':field,'ref':{'id':block['id'],'start':start,'end':end}})
        diagnostic['added_fields'].append(field)
    if legal:
        from .schema import quote
        diagnostic['superseded_entity']=[quote(f['ref'],evidence)['quote'] for f in a.get('facts',[]) if f['field']=='entity']
        add('entity',legal['start'],legal['end'],True)
    elif ident.get('name'):
        # Exact standalone owner name, independently supported by the existing
        # identity resolver. A textual occurrence inside another sentence is
        # not enough to attribute an advertisement or borrow its publisher.
        m=re.search(r'(?m)^\s*'+re.escape(ident['name'])+r'\s*$',text)
        if m:
            at=text.find(ident['name'],m.start(),m.end())
            add('entity',at,at+len(ident['name']))
    from .signals import extract_signals
    invitations=[s for s in extract_signals(source) if s['type']=='collaboration_invitation'
        and TECH.search(s['context']) and EXTERNAL.search(s['context']) and not CUSTOMER.search(s['context'])]
    if invitations:
        s=max(invitations,key=lambda v:len(v['quote']))
        # Supply the actual bounded invitation and its adjacent requirements;
        # don't call an agency's offered service a requested skill.
        for field in ('request','technical','contract'):
            add(field,s['start'],s['context_end'],replace=field=='request')
        if a.get('kind') in ('UNKNOWN','SUPPLIER_OFFER','EDITORIAL'):
            diagnostic['superseded_kind']=a['kind']
            a['kind']='AGENCY_PARTNERSHIP' if role['role']=='AGENCY' else 'BUYER_DEMAND'
            a['kind_ref']={'id':block['id'],'start':s['start'],'end':s['context_end']}
            # A corrected negative is a recoverable lead, not an automatic
            # commercial promotion. An independent currentness check remains.
            a['missing']=list(dict.fromkeys(a.get('missing',[])+['publication']))
    for c in ident.get('contacts',[]):
        value=c.get('value','');start=text.find(value)
        if c.get('url')==source['url'] and value and start>=0:
            add('contact',start,start+len(value));break
    resolved=set(diagnostic['added_fields'])
    a['missing']=[f for f in a.get('missing',[]) if f not in resolved and not (f=='official_domain' and ident.get('website'))]
    a['field_errors']=[e for e in a.get('field_errors',[]) if e.get('field') not in resolved]
    if 'entity' in resolved:a['identity_issues']=[]
    return a,pool,ident,diagnostic


def relationship(source, facts):
    """Narrow negative/uncertain relationships; absence is never a positive."""
    text=source.get('text','');requests=[f for f in facts if f.get('field')=='request']
    context=[]
    for f in requests:
        q=f.get('quote','');at=text.find(q)
        if at>=0:context.append(text[max(0,at-120):min(len(text),at+len(q)+300)])
    local='\n'.join(context)
    from .request_scope import nontechnical_request
    grounded=[f for f in requests if f.get('quote') and f['quote'] in text]
    unrelated=[f for f in grounded if nontechnical_request(f['quote'])]
    if unrelated:return 'NONTECHNICAL_PARTNERSHIP' if len(unrelated)==len(grounded) else 'MIXED_INVITATIONS'
    if local and CUSTOMER.search(local):return 'CUSTOMER_PARTNERSHIP'
    if local and VOLUNTEER.search(local) and not TECH.search(local):return 'NONTECHNICAL_VOLUNTEERING'
    if local and re.search(r'gestione di (?:uno dei |un )?portali',local,re.I) and not TECH.search(local):return 'PORTAL_MANAGEMENT_UNSPECIFIED'
    if local and INVITE.search(local):return 'INVITATION'
    return 'UNKNOWN'


def repair_fields(analysis, body):
    """Only repair a consequential unresolved field with unused source proof.

    A valid partial output with no new literal evidence isn't improved by
    asking the same question again. Unknown names/dates remain unknown.
    """
    if not analysis or not body.get('original'):return []
    if body.get('state') in ('REJECTED','VERIFIED','POTENTIAL'):return []
    supported={f['field'] for f in body.get('facts',[]) if f.get('original')}
    available={'request','technical','contract'} if any(s['type'] in ('collaboration_invitation','explicit_project_request') for s in body.get('commercial_signals',[])) else set()
    if body.get('identity_verified'):available|={'entity','contact'}
    return sorted({e['field'] for e in analysis.get('field_errors',[]) if e.get('field') in available-supported})


def dossier(body):
    """Inspectable persistent next action. Null costs are deliberately unknown."""
    missing=list(dict.fromkeys(body.get('missing',[])))
    proof={f['field'] for f in body.get('facts',[]) if f.get('original')}
    invitation='request' in proof and body.get('kind') in ('AGENCY_PARTNERSHIP','BUYER_DEMAND')
    promising=bool(invitation and body.get('identity_verified') and body.get('state') not in ('REJECTED','UNVERIFIABLE'))
    return {'candidate_key':body.get('entity_key') or digest(body['url']),
        'phase':'qualified' if body.get('state') in ('VERIFIED','POTENTIAL') else 'verification' if body.get('original') else 'discovery',
        'promising':promising,'completed_checks':sorted(proof|({'official_domain'} if body.get('identity_verified') else set())),
        'missing_checks':missing,'optional_unknowns':body.get('optional_unknowns',[]),'next_action':body.get('next_verification'),
        'commercial_maturity':'verified_request' if body.get('state')=='VERIFIED' else 'qualified_lead' if body.get('state')=='POTENTIAL' else 'interesting_incomplete' if promising else 'unqualified',
        'active_assignment':'UNKNOWN' if body.get('kind')=='AGENCY_PARTNERSHIP' else 'DOCUMENTED_REQUEST' if body.get('state')=='VERIFIED' else 'UNKNOWN',
        'contract_acquired':'UNKNOWN',
        'pipeline_checks':{'SOURCE_ACQUISITION':'completed' if body.get('original') else 'pending',
            'IDENTITY_RESOLUTION':'completed' if body.get('identity_verified') else 'pending',
            'ORIGINAL_VERIFICATION':'completed' if proof else 'pending',
            'QUALIFICATION':body.get('state'),
            'DOSSIER_COMPLETION':'pending' if missing else 'completed',
            'FINALIZATION':'qualified' if body.get('state') in ('POTENTIAL','VERIFIED') else 'incomplete' if promising else 'unqualified'},
        'blocked_reason':body.get('technical_error'), 'estimated_project_value':None,
        'next_cost':{'ai_calls':None,'serper_requests':None,'usd':None},
        'priority_reason':'documented_invitation_and_identity' if promising else 'evidence_incomplete',
        'current_availability':'VERIFIED_RECENT_SOURCE' if body.get('freshness',{}).get('status')=='RECENT' else 'UNKNOWN',
        'sales_probability':None}
