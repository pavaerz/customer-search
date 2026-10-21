"""Commercial First: pure, evidence-derived advice, never an official decision.

No network, writes, model calls or dependence on AI output. Historical revisions
remain immutable. Missing evidence is displayed, never treated as a positive.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from sales.db import domain

STATES=('READY_TO_CONTACT','WORTH_REVIEWING','RESEARCH_REQUIRED','NOT_ACTIONABLE')
LABELS=dict(zip(STATES,('Pronte al contatto','Piste da approfondire','Identità o prove da ricercare','Non utilizzabili')))
PUBLISHERS={'bebee.com','it.clickajobs.com','clickajobs.com','linkedin.com','it.linkedin.com','jooble.org','it.jooble.org','iprogrammatori.it','cercolavoro.com','app.cliccalavoro.it'}

def normalize(value):return ' '.join(re.findall(r'\w+',str(value or '').casefold()))
def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:32]
def date_value(value):
    try:
        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError,TypeError):return None

def declared_actor(body,documents=()):
    """Only explicit source attribution, never a publisher/domain guess."""
    a=body.get('actor_attribution') or {};name=a.get('requesting_actor') or body.get('requesting_actor')
    if name:return name
    names=set()
    for block in body.get('request_blocks') or []:
        if block.get('subject') and (str(block.get('channel','')).startswith('job:') or block.get('source_kind')=='job_posting'):names.add(block['subject'])
    for doc in documents:
        details=doc.get('details',doc)
        if isinstance(details,str):details=json.loads(details)
        for channel in (details.get('evidence_channels') or {}).values():
            for unit in channel.get('units',[]):
                if unit.get('subject') and 'JobPosting' in str(unit.get('schema_type') or unit.get('origin') or channel.get('name','')):names.add(unit['subject'])
    # Saved canonical request blocks use schema_subject on some older versions.
    for e in body.get('evidence',[]):
        if e.get('subject') and e.get('channel')=='structured':names.add(e['subject'])
    return next(iter(names)) if len(names)==1 else None

def source_contacts(body,identity):
    host=domain(identity.get('website') or '')
    if identity.get('identity_status')!='verified' or not host or host in PUBLISHERS:return []
    contacts=[]
    from .entity_scope import MULTI
    for c in identity.get('contacts',body.get('contacts',[])):
        # Publicly observed channel, not deliverability or permission to mail.
        if c.get('value') and c.get('url') and not MULTI.search(c['url']) and domain(c['url'])==host and c.get('checked_at') and c.get('type') in ('email','phone','form'):
            contacts.append({**c,'verification':'published_on_verified_company_site','not_delivery_verification':True})
    return contacts

def request_key(body,name=None):
    intent=body.get('commercial_intent') or {}
    quote=intent.get('request_clause') or next((e.get('quote') for e in body.get('evidence',[]) if e.get('quote') and e.get('kind')!='measurement'),None)
    if not quote:return None
    # Actor + request + date, not URL: syndication is not an independent request.
    return fingerprint([normalize(name or body.get('company')),normalize(quote),body.get('published_at') or None])

def build(body,documents=(),manual=None,as_of=None):
    identity=body.get('identity') or {};v=body.get('verification') or {};intent=body.get('commercial_intent') or {};fit=body.get('target_fit') or {};br=body.get('browser') or {}
    data_issues=[]
    if body.get('engine')=='WEBSITE_REBUILD' and documents:fit,data_issues=corrected_target(body,documents)
    outbound=body.get('engine')=='WEBSITE_REBUILD';publisher=domain(body.get('url') or '')
    from .target_fit import source_role,excluded_legal_form
    role=source_role(body.get('url') or '',(identity.get('name_fields') or {}).get('page_title') or identity.get('name') or body.get('title',''))
    invalid_owner=outbound and role in ('institution','multi_company_catalog')
    if invalid_owner:
        fit={**fit,'status':'NOT_SUITABLE','audit_allowed':False,'source_role':role}
        data_issues.append({'kind':'publisher_member_identity','message':'Fonte associativa o scheda di un membro: dati del titolare e dell’azienda citata non attribuibili allo stesso cliente. Stato storico conservato.'})
    third=publisher in PUBLISHERS or body.get('source_kind') in ('job_portal','aggregator') or bool(body.get('actor_attribution'))
    declared=declared_actor(body,documents)
    name=(declared if third else identity.get('name') or body.get('company'))
    verified=identity.get('identity_status')=='verified' and not identity.get('identity_conflicts') and not third and not invalid_owner
    # Third-party publication can only be trusted after explicit separate identity verification.
    if third and (body.get('actor_attribution') or {}).get('identity_verified') and identity.get('website') and domain(identity['website'])!=publisher and declared==identity.get('name'):verified=True
    official=identity.get('website') if verified else None
    contacts=source_contacts(body,identity) if verified else []
    quotes=[{'kind':'FACT','quote':e.get('quote'),'url':e.get('url'),'published_at':e.get('published_at'),'checked_at':e.get('checked_at')} for e in body.get('evidence',[]) if e.get('quote') and e.get('url') and e.get('kind')!='measurement']
    if not quotes:
        quotes=[{'kind':'FACT','quote':e.get('quote'),'url':body.get('url'),'published_at':body.get('published_at'),'checked_at':body.get('checked_at')} for e in intent.get('buyer_evidence',[]) if e.get('quote') and body.get('url')]
    if outbound and not quotes:
        quotes=[{'kind':'FACT',**e} for e in fit.get('offer_evidence',[]) if e.get('quote') and e.get('url')]
    clause=intent.get('request_clause')
    if clause and intent.get('buyer_evidence'):
        primary=next((e for e in quotes if clause in e['quote']),None)
        if primary:quotes=[primary]+[e for e in quotes if e is not primary]
        elif any(clause in e.get('quote','') for e in intent.get('buyer_evidence',[])):
            quotes.insert(0,{'kind':'FACT','quote':clause,'url':body.get('url'),'published_at':body.get('published_at'),'checked_at':body.get('checked_at')})
    if outbound:
        description=identity.get('description') or ''
        proven=next((d for d in documents if len(description)>40 and description in d.get('text','') and domain(d.get('url',''))==domain(official or '')),None)
        if proven:quotes.insert(0,{'kind':'FACT','quote':description,'url':proven['url'],'checked_at':proven.get('checked_at'),'published_at':None})
    generic_partner=bool(body.get('engine')=='AGENCIES' and body.get('classification')=='general_collaboration_policy' and body.get('partner_hint',{}).get('evidence'))
    technical=bool(intent.get('technical') and intent.get('buyer_evidence')) or bool(body.get('request_type') and declared and quotes)
    standing=body.get('classification')=='ongoing' or v.get('currentness')=='standing_invitation'
    current='not_applicable' if outbound else v.get('currentness') or 'unknown'
    now=as_of or datetime.now(timezone.utc);checked=date_value(body.get('checked_at'));published=date_value(body.get('published_at'))
    recent=bool(checked and 0<=(now-checked).total_seconds()<=30*86400)
    current_ok=bool(v.get('currently_open') and v.get('availability_verified')) or bool(standing and recent and v.get('checks',{}).get('temporal_basis'))
    missing=[];blocks=[]
    if outbound and excluded_legal_form(identity.get('name')):blocks.append('S.p.A. esclusa dal profilo commerciale configurato per questa ricerca.')
    if invalid_owner:blocks.append('Fonte associativa o profilo di terzi, non un prospect aziendale diretto verificato.')
    if not verified:missing.append('Identità e dominio ufficiale del committente da verificare.')
    if not contacts:missing.append('Canale di contatto pertinente non verificato.')
    if not outbound and not current_ok:missing.append('Disponibilità attuale da verificare; la pubblicazione non prova che la richiesta sia ancora aperta.')
    if not body.get('geography',{}).get('eligible'):missing.append('Area geografica da verificare.')
    if outbound and not br.get('completed'):missing.append('Audit tecnico non completo: nessun difetto del sito dimostrato.')
    if published and published>now:blocks.append('Data della richiesta futura.')
    relationship=body.get('relationship') or (body.get('actor_attribution') or {}).get('relationship') or {}
    external_verified=relationship.get('employment_relationship')=='EXTERNAL' or body.get('contract') in ('external','freelance')
    if not outbound and not external_verified:missing.append('Natura freelance o collaborazione esterna non verificata.')
    contract_conflict=relationship.get('employment_relationship')=='AMBIGUOUS'
    if contract_conflict:missing.append('Contratto discordante: prove di rapporto esterno e dipendente conservate; chiedere chiarimento.')
    other_conflicts=[c for c in intent.get('contradictions',[]) if not (contract_conflict and c.get('code')=='conflicting_contracts')]
    if identity.get('identity_conflicts') or other_conflicts:blocks.append('Prove contraddittorie sul soggetto o sulla richiesta.')
    if body.get('geography',{}).get('country')=='Estero':blocks.append('Fuori dall’area commerciale ammessa.')
    if manual and (manual.get('do_not_contact') or manual.get('company_dismissed') or manual.get('manual_state') in ('discarded','contacted')):blocks.append('Contatto già gestito o escluso: rispettare la decisione commerciale.')
    if body.get('state')=='REJECTED':blocks.append('Esclusione ufficiale conservata; consultare il motivo nel dossier.')
    if (intent.get('commercial_role') in ('SELLER','PARTNERSHIP_SELLER') and not generic_partner) or (intent.get('commercial_role')=='EMPLOYER' and not contract_conflict) or body.get('classification') in ('seller','no_request','irrelevant','hosted_incompatible') or (body.get('classification')=='contradictory_request' and not contract_conflict):blocks.append('Non è una richiesta tecnica esterna utilizzabile.')
    if not outbound and (v.get('currentness') in ('closed','historical','expired') or (body.get('freshness') or {}).get('priority_hint') in ('closed','historical')):blocks.append('Richiesta chiusa o storica.')
    state='NOT_ACTIONABLE';reason='Manca una motivazione commerciale documentata.';action='Consultare le prove e il motivo di esclusione.'
    kind='OUTBOUND_PROSPECT' if outbound else 'CONTINUING_PARTNERSHIP' if standing else 'EXTERNAL_REQUEST'
    if not blocks and outbound and fit.get('status')=='SUITABLE_FOR_AUDIT' and verified and quotes:
        state='WORTH_REVIEWING';reason='Attività e compatibilità documentate: prospect outbound, intenzione d’acquisto sconosciuta.';action='Valutare il sito e verificare un bisogno concreto prima di proporre un rifacimento.'
        measured=br.get('completed') and len(br.get('findings',[]))>=2 and body.get('state')=='POTENTIAL'
        if measured and contacts and recent and body.get('geography',{}).get('eligible'):
            state='READY_TO_CONTACT';reason='Prospect outbound con problemi misurati e contatto pubblico verificato; nessuna richiesta di rifacimento dichiarata.';action='Preparare una proposta basata sulle sole misure confermate.'
    elif not blocks and generic_partner and quotes:
        state='WORTH_REVIEWING' if verified else 'RESEARCH_REQUIRED';kind='CONTINUING_PARTNERSHIP'
        reason='Collaborazioni esterne dichiarate; nessuna richiesta tecnica specifica verificata.'
        missing.append('Competenze richieste, disponibilità e progetto da chiarire; budget sconosciuto.')
        action='Verificare se cercano supporto WordPress/frontend per progetti clienti.'
    elif not blocks and not outbound and technical and quotes:
        if verified:
            state='WORTH_REVIEWING';reason='Invito continuativo a collaborazioni tecniche.' if standing else 'Richiesta tecnica esterna nelle prove; disponibilità attuale da confermare.' if external_verified else 'Ricerca di un profilo tecnico; contratto e disponibilità attuale da verificare.';action='Verificare se la collaborazione è ancora aperta.'
            if external_verified and contacts and current_ok and recent and body.get('geography',{}).get('eligible') and not contract_conflict and body.get('classification') not in ('cofounder','equity'):
                state='READY_TO_CONTACT';action='Preparare una presentazione per la partnership, senza presumere una commessa.' if standing else 'Preparare una risposta riferita alla richiesta verificata.'
        elif declared or name:
            state='RESEARCH_REQUIRED';reason='Richiesta conservata da una fonte terza; il committente non è ancora verificato.' if third else 'Richiesta su un sito apparentemente aziendale; identità del titolare non ancora corroborata.';action='Verificare il titolare della fonte e confermare la richiesta.'
    if fit.get('status')=='LOW_PRIORITY':blocks.append('Target a bassa priorità: non equivale a una pista commerciale.');state='NOT_ACTIONABLE'
    demand=body.get('demand_assessment') or {}
    if demand.get('version')=='5.1' and not outbound:
        if demand.get('excluded'):
            state='NOT_ACTIONABLE';blocks.extend(demand.get('reasons',[]))
        elif state=='READY_TO_CONTACT' and demand.get('level')!='READY_TO_CONTACT':
            state='WORTH_REVIEWING' if demand.get('request_observed') else 'RESEARCH_REQUIRED'
        buyer=demand.get('actors',{}).get('buyer')
        if not buyer or demand.get('actors',{}).get('buyer_status')!='VERIFIED':
            contacts=[];official=None;verified=False
        name=buyer
    if blocks:reason=blocks[0]
    return {'version':'4.3','status':state,'label':LABELS[state],'priority':len(STATES)-STATES.index(state),'process':'OUTBOUND_PROSPECTING' if outbound else 'ACTIVE_DEMAND','opportunity_type':kind,
        'site_assessment':site_assessment(body,verified) if outbound else None,
        'relationship':relationship,'identity_fields':identity.get('name_fields'),'identity_original':identity.get('identity_original'),'identity_resolution':identity.get('resolution'),
        'company':name or 'Committente non identificato','official_domain':official,'engine':body.get('engine'),'official_state':body.get('state'),'reason':reason,'reason_kind':'INFERENCE' if outbound else 'FACT' if technical else 'UNKNOWN',
        'evidence':quotes[:3],'source_url':body.get('url'),'request_date':None if outbound else body.get('published_at'),'currentness':current,'region':body.get('geography',{}).get('regions',[]),'contacts':contacts,
        'missing':missing,'blockers':blocks,'audit_state':br.get('audit_state') or ('COMPLETE' if br.get('completed') else 'PARTIAL' if br.get('pages') else 'NOT_EXECUTED'),
        'next_action':action,'roles':{'PUBLISHER':publisher,'HIRING_ORGANIZATION':declared,'REQUESTING_ORGANIZATION':name,'MENTIONED_ORGANIZATION':None,'CONTACT_OWNER':identity.get('name') if contacts else None},
        'request_key':None if outbound or not technical or not quotes else request_key(body,name),'subject_key':normalize(official or name) if verified else None,'data_issues':data_issues,'decision_authority':'deterministic_advisory_only','budget':body.get('compensation',{}).get('amount')}

def site_assessment(body,verified):
    """Orthogonal facts: identity, hypothesis, measurements and buying request.

    Do not manufacture a B/C/D classification from an incomplete browser.
    Only attributed original request evidence can support the request field.
    """
    browser=body.get('browser') or {};verification=body.get('verification') or {}
    from .audit_summary import coverage
    measured=[f for f in browser.get('findings',[]) if browser.get('completed') and f.get('status','CONFIRMED')=='CONFIRMED']
    request=[e for e in body.get('evidence',[]) if verified and verification.get('request_verified') and e.get('kind')=='request' and e.get('attribution_status')=='verified_owner' and re.search(r'(?:rifacimento|rifare|nuovo sito|restyling)',e.get('quote',''),re.I)]
    hypothesis=[e for e in body.get('evidence',[]) if e.get('certainty')=='inference' and e.get('kind')=='digital_need' and e.get('quote') and e.get('url')]
    return {'company':'VERIFIED' if verified else 'UNKNOWN','improvement_hypothesis':hypothesis,
            'technical_findings':measured,'explicit_rebuild_request':request,
            'level':'D_EXPLICIT_REQUEST' if request else 'C_MEASURED_ISSUES' if measured else 'B_HYPOTHESIS' if hypothesis else 'A_COMPANY_ONLY' if verified else 'UNKNOWN',
            'label':'Richiesta di progetto documentata' if request else 'Problemi tecnici misurati' if measured else 'Ipotesi di miglioramento da verificare' if hypothesis else 'Azienda verificata, bisogno digitale non dimostrato' if verified else 'Identità aziendale da verificare',
            'availability':'UNKNOWN','full_rebuild_justified':None,'browser_coverage':coverage(browser) if browser else None,
            'limits':['Problemi tecnici e compatibilità di settore non dimostrano da soli la necessità di rifare il sito.','Budget e disponibilità all’acquisto sconosciuti.']}

def novelty(body,previous):
    key=request_key(body);own=domain((body.get('identity') or {}).get('website') or body.get('website') or '')
    matches=[]
    for row in previous:
        b=row['body'];other=domain((b.get('identity') or {}).get('website') or b.get('website') or '')
        same_source=b.get('url')==body.get('url') and b.get('engine')==body.get('engine')
        dated_new=bool(body.get('published_at') and b.get('published_at') and body['published_at']!=b['published_at'] and normalize((body.get('commercial_intent') or {}).get('request_clause'))!=normalize((b.get('commercial_intent') or {}).get('request_clause')))
        if dated_new:continue
        if (key and request_key(b)==key) or (body.get('engine')=='WEBSITE_REBUILD' and own and own==other and b.get('engine')==body.get('engine')) or same_source:
            matches.append(row)
    if not matches:return {'status':'NEW','previous_revision':None}
    last=max(matches,key=lambda r:r['id']);old=last['body']
    # Comparison excludes check timestamps, scores, rule versions and AI.
    facts=lambda b:fingerprint([b.get('published_at'),normalize((b.get('commercial_intent') or {}).get('request_clause')),sorted((e.get('url',''),normalize(e.get('quote'))) for e in b.get('evidence',[])),b.get('verification',{}).get('currentness')])
    changed=facts(body)!=facts(old)
    # A poorer extraction does not erase or refresh the earlier request.
    if len(body.get('evidence',[]))<len(old.get('evidence',[])) and not body.get('published_at'):changed=False
    reopened=changed and old.get('verification',{}).get('currentness') in ('closed','expired') and body.get('verification',{}).get('currently_open')
    return {'status':'REOPENED' if reopened else 'UPDATED' if changed else 'ALREADY_SEEN','previous_revision':last['id'],'previous_campaign':last.get('campaign_id')}

def metrics(items):
    views=[i['commercial_view'] for i in items];counts={s:sum(v['status']==s for v in views) for s in STATES}
    return {**counts,'new_subjects':len({v['subject_key'] for v in views if v.get('subject_new') and v['subject_key']}),
        'new_requests':len({v['request_key'] for v in views if v.get('novelty',{}).get('status')=='NEW' and v['request_key']}),
        'known_opportunities':sum(v.get('novelty',{}).get('status')=='ALREADY_SEEN' for v in views),'updated_opportunities':sum(v.get('novelty',{}).get('status') in ('UPDATED','REOPENED') for v in views),
        'verified_contacts':len({v['subject_key'] for v in views if v['contacts'] and v['subject_key']}),'active_requests':sum(v['opportunity_type']=='EXTERNAL_REQUEST' and v['status']=='READY_TO_CONTACT' for v in views),
        'continuing_partnerships':sum(v['opportunity_type']=='CONTINUING_PARTNERSHIP' and v['status']!='NOT_ACTIONABLE' for v in views),'outbound_prospects':sum(v['process']=='OUTBOUND_PROSPECTING' and v['status']!='NOT_ACTIONABLE' for v in views),
        'useful_audits':sum(v['audit_state']=='COMPLETE' for v in views),'time_to_first_ready_seconds':None,'time_basis':'not measurable here; excludes no pauses automatically','no_conversion_claim':True}

def corrected_target(body,documents):
    """Recheck historical workforce attribution in a read-only projection.

    Remove a counterproof only when every occurrence in its saved source
    explicitly belongs to another subject; missing originals do not clear it.
    """
    import copy
    from .entity_scope import owner_fact
    fit=copy.deepcopy(body.get('target_fit') or {});facts=fit.get('counterevidence',[]);retained=[];issues=[]
    for fact in facts:
        quote=fact.get('quote','');texts=[d.get('text','') for d in documents if d.get('url')==fact.get('url')]
        contexts=[line for text in texts for line in text.splitlines() if quote and quote in line]
        if fact.get('kind')=='documented_size' and contexts and all(not owner_fact(t,(body.get('identity') or {}).get('name')) for t in contexts):
            issues.append({'kind':'third_party_workforce','source_url':fact.get('url'),'quote':quote,'historical_actor':fact.get('actor')})
        else:retained.append(fact)
    if issues:
        fit['counterevidence']=retained
        if not any(f.get('employees',0)>=250 for f in retained):
            fit['reasons']=[r for r in fit.get('reasons',[]) if r!='documented_large_company_lower_priority']
            fit['size']={'status':'UNKNOWN','employees':None}
            fit['audit_allowed']=not fit['reasons'];fit['status']='SUITABLE_FOR_AUDIT' if fit['audit_allowed'] else 'INSUFFICIENT_EVIDENCE'
    return fit,issues
