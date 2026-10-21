"""Read-only commercial inbox across campaigns, separated from discovery.

No network calls or migrations. Dynamic freshness never rewrites a historical
decision. Explicit exclusions and CRM outcomes outrank automatic evaluations.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sales.db import domain
from . import FLOWS,canonical_flow

COMMERCIAL={'contacted','replied','proposal','won','lost'}
VIEWS={'ready','verified','potential','promising','review','resolved','new','contacted','replied','proposal','won','lost','excluded','all'}
LABELS={'ready':'Da contattare','verified':'Verificate','potential':'Potenziali','promising':'Promettenti da verificare','review':'Da approfondire',
        'resolved':'Approfondimenti conclusi','new':'Nuove piste','contacted':'Contattati','replied':'Risposte ricevute','proposal':'Preventivi inviati',
        'won':'Clienti acquisiti','lost':'Opportunità perse','excluded':'Eliminate','all':'Tutte'}


def days_since(value,at):
    if not value:return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
        days=(at-parsed).total_seconds()/86400
        return days if days>=0 else None
    except (ValueError,TypeError):return None


from .record_views import current_original


def listing(store,params=None,at=None):
    p=params or {};view=p.get('view') or 'ready';flow=p.get('flow') or '';term=(p.get('q') or '').casefold().strip()
    grouping=p.get('group','request')
    if grouping not in ('company','request'):raise ValueError('Raggruppamento non valido')
    from .commercial_view import enrich,TYPES
    if p.get('type') and p['type'] not in TYPES:raise ValueError('Tipo di opportunità non valido')
    if p.get('priority') and p['priority'] not in ('high','medium','low'):raise ValueError('Priorità non valida')
    if view not in VIEWS or flow and canonical_flow(flow) not in FLOWS:raise ValueError('Filtro worklist non valido')
    if len(term)>200:raise ValueError('Ricerca troppo lunga')
    offset=max(0,int(p.get('offset',0)));limit=min(100,max(1,int(p.get('limit',25))))
    at=at or datetime.now(timezone.utc)
    with store.connect() as c:
        rows=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('SELECT * FROM agent6_records ORDER BY updated_at DESC,id DESC')]
        feedback=[dict(r) for r in c.execute('SELECT f.*,r.request_key,r.entity_key FROM agent6_feedback f JOIN agent6_records r ON r.id=f.record_id ORDER BY f.created_at,f.id')]
        prospects=[dict(r) for r in c.execute('SELECT p.*,c.domain,c.do_not_contact,c.prior_contacted FROM prospects p JOIN companies c ON c.id=p.company_id ORDER BY p.updated_at,p.id')]
        companies={r['domain']:dict(r) for r in c.execute('SELECT * FROM companies')}
        old_exclusions={r[0] for r in c.execute("SELECT d.domain FROM commercial_outcomes o JOIN discovery_candidates d ON d.id=o.candidate_id WHERE o.kind='not_relevant'")}
        filters={r['id']:json.loads(r['filters']) for r in c.execute('SELECT id,filters FROM campaigns')}
    from .entities import index,group_worklist
    graph=index(rows)
    from .followups import read as read_resolutions
    resolved=read_resolutions(store,rows)
    from .annotations import read as read_annotations,latest as latest_annotations,apply as apply_annotations
    corrections=latest_annotations(read_annotations(store))
    # Request identity preserves two distinct roles at the same company.
    by_request=defaultdict(list)
    for r in rows:by_request[r['request_key']].append(r)
    exclusions={};outcomes={};preferences={}
    from .quality import latest as quality_reviews
    quality=quality_reviews(store)
    for f in feedback:
        for key in (('request',f['request_key']),('entity',f['entity_key']),('company',graph['record_keys'].get(f['record_id']))):
            if not key[1]:continue
            if f['kind'] in ('not_interesting','restore'):exclusions[key]=f
            if f['kind'] in COMMERCIAL:outcomes[key]=f
            preferences[key]=f
    crm_request={};crm_domain={}
    for r in prospects:
        if r['identity'].startswith('agent6:'):crm_request[r['identity'][7:]]=r
        if r['stage'] in COMMERCIAL:crm_domain[r['domain']]=r
    suppressed_cache={};items=[]
    for key,versions in by_request.items():
        # A new weak snippet cannot erase a verified original. A newer original
        # (including a closed request) does supersede the old decision.
        r,analysis_failure=current_original(versions)
        if r['body'].get('canonical_record_id'):continue
        b=apply_annotations(enrich(r['body']),corrections.get(key,{}));host=domain(b.get('official_domain') or b['url'])
        if analysis_failure:b['later_analysis_failure']=analysis_failure
        lookup=(('request',key),('entity',r['entity_key']),('company',graph['record_keys'][r['id']]))
        def latest(mapping):return max((mapping[k] for k in lookup if k in mapping),key=lambda v:(v['created_at'],v.get('id',0)),default={})
        exclusion=latest(exclusions);company_outcome=latest(outcomes);manual=outcomes.get(('request',key),{});preference=latest(preferences)
        crm=crm_request.get(key);company_crm=crm_domain.get(host);company=companies.get(host,{})
        linked_rows=graph['groups'][graph['record_keys'][r['id']]]
        company_domains={graph['links'][v['id']]['domain'] for v in linked_rows}-{None}
        company_domains.add(host)
        linked_companies=[companies.get(h,{}) for h in company_domains]
        stage=manual.get('kind')
        if crm and crm['stage'] in COMMERCIAL and crm['updated_at']>=manual.get('created_at',''):stage=crm['stage']
        managed_elsewhere=not stage and bool(company_outcome or company_crm or any(c.get('prior_contacted') for c in linked_companies) or any(h in crm_domain for h in company_domains))
        for h in company_domains:
            if h not in suppressed_cache:suppressed_cache[h]=store.target_exclusion('https://'+h) if h else None
        excluded=bool(exclusion.get('kind')=='not_interesting' or any(c.get('do_not_contact') for c in linked_companies) or any(suppressed_cache[h] or h in old_exclusions for h in company_domains))
        age=days_since(b.get('checked_at'),at);window=filters.get(r['campaign_id'],{}).get('max_job_age_days',14)
        if b.get('decision_engine')=='ai_first_1' and b.get('relationship') in ('OPEN_FREELANCE_COLLABORATION','SPONTANEOUS_APPLICATION'):
            window=30
        published=(b.get('freshness') or {}).get('published_at');publication_age=days_since(published,at)
        if b.get('decision_engine')=='ai_first_1' and b.get('freshness',{}).get('status') in ('STANDING_INVITATION','CURRENT_OBSERVATION'):
            publication_age=None
        warning=None;state=r['state']
        if state in ('VERIFIED','POTENTIAL'):
            if not b.get('original') or not b.get('identity_verified'):
                warning='La qualifica salvata non ha una fonte originale e un’identità verificate.'
            elif age is None or age>window or publication_age is not None and publication_age>window:
                warning='Verifica di nuovo la disponibilità: le prove non sono abbastanza recenti.'
            elif versions[0]['body'].get('workflow_state')=='ORIGINAL_READ_FAILED' and versions[0]['id']!=r['id']:
                warning='L’ultimo tentativo di consultare la fonte non è riuscito: ricontrolla la disponibilità.'
            if warning:state='NEEDS_REVIEW'
        if managed_elsewhere and state in ('VERIFIED','POTENTIAL','RELEVANT','NEEDS_REVIEW'):
            warning='Questa azienda è già gestita per un’altra richiesta: consulta lo storico prima di ricontattarla.'
            state='NEEDS_REVIEW'
        if quality.get(key,{}).get('kind')=='false_positive':
            state='NEEDS_REVIEW';warning='Qualifica contestata nella revisione delle prove: '+quality[key]['note']
        if b.get('manual_corrections',{}).get('relevance',{}).get('value')=='irrelevant' and not excluded and stage not in COMMERCIAL:
            state='NEEDS_REVIEW';warning='Hai indicato questa proposta come non pertinente: '+b['manual_corrections']['relevance']['note']
        resolution=resolved.get(r['id']) if not (preference or crm or managed_elsewhere or corrections.get(key) or quality.get(key)) else None
        if resolution:b['research_resolution']=resolution
        if excluded:bucket='excluded'
        elif stage in COMMERCIAL:bucket=stage
        elif resolution:bucket='resolved'
        elif state=='VERIFIED':bucket='verified'
        elif state=='POTENTIAL':bucket='potential'
        elif state in ('NEEDS_REVIEW','RELEVANT'):bucket='review'
        elif b.get('verification_hold') and b.get('facts'):
            bucket='review';warning='Il controllo richiesto non è concluso; questa scheda non è pronta da contattare.'
        elif b.get('workflow_state') in ('SCREENING_FAILED_RECOVERABLE','ORIGINAL_READ_PENDING','ORIGINAL_READ_FAILED','VERIFICATION_PENDING') and b.get('facts'):bucket='new'
        else:continue  # Unscreened URLs, ordinary rejections and unknowns are not leads.
        from .alignment import dimensions
        b['commercial_alignment']=dimensions({**b,'state':'REJECTED' if excluded else state})
        if stage in COMMERCIAL or managed_elsewhere:
            b['commercial_alignment']['READY_FOR_OUTREACH']=False
        facts=b.get('facts',[])
        request=next((f for f in facts if f['field']=='request'),None)
        signal=next((f for f in facts if f['field'] in ('signal','digital_gap')),None)
        primary=request or signal
        secondary=next((f['url'] for f in facts if primary and f.get('original') and f['url']!=primary['url']),None)
        next_action=({'contacted':'Attendi o registra la risposta; consulta lo storico prima di ricontattare.',
            'replied':'Leggi la risposta e chiarisci il perimetro del progetto.',
            'proposal':'Aggiorna l’esito del preventivo nei contatti.',
            'won':'Gestisci il progetto e conserva l’esito commerciale.',
            'lost':'Conserva il motivo della mancata collaborazione.',
            'excluded':'Proposta esclusa: ripristinala esplicitamente prima di contattare.',
            'resolved':'Consulta l’esito dell’approfondimento collegato. Questo percorso non ha dimostrato un’opportunità.'}.get(bucket)
            or ('Consulta la richiesta e prepara un contatto personalizzato.' if state=='VERIFIED' else
                'Conferma gli aspetti mancanti prima di proporre una collaborazione.' if state=='POTENTIAL' else
                warning or b.get('next_verification') or 'Verifica committente, richiesta e disponibilità sulla fonte originale.'))
        if state in ('VERIFIED','POTENTIAL') and not b['commercial_alignment']['CONTACT_AVAILABLE'] and not excluded and stage not in COMMERCIAL:
            next_action='Opportunità qualificata: cercare un canale pubblico attribuito all’azienda prima di preparare il contatto.'
        flows=sorted({f for v in versions for f in v['body'].get('flows',[v['flow']])})
        if flow and canonical_flow(flow) not in {canonical_flow(f) for f in flows}:continue
        if p.get('type') and b['opportunity_type']!=p['type']:continue
        if p.get('priority') and b['priority']!=p['priority']:continue
        if p.get('state') and state!=p['state']:continue
        if p.get('region') and p['region'].casefold() not in str(b.get('region') or b.get('identity',{}).get('region') or '').casefold():continue
        if p.get('sector') and p['sector'].casefold() not in str(b.get('sector') or '').casefold():continue
        if p.get('source') and p['source'].casefold() not in ' '.join(f.get('url','') for f in facts).casefold():continue
        if p.get('complete')=='1' and state not in ('VERIFIED','POTENTIAL'):continue
        if p.get('contacted')=='1' and not (stage in COMMERCIAL or managed_elsewhere):continue
        if p.get('contact')=='1' and not b['commercial_alignment']['CONTACT_AVAILABLE']:continue
        if b.get('automatic_opportunity_type')=='OPPORTUNITA_PROATTIVA' and state in ('VERIFIED','POTENTIAL'):
            next_action='Proponi un confronto sui problemi osservati e sul progetto ipotizzato; interesse e budget restano da confermare.'
        if term and term not in ' '.join(str(b.get(k) or '') for k in ('entity_name','official_domain','url','title')).casefold():continue
        items.append({**r,'body':{**b,'flows':flows},'state':state,'saved_state':r['state'],
            'feedback':'not_interesting' if excluded else stage or (preference.get('kind') if preference.get('kind') not in COMMERCIAL else None),
            'worklist':{'bucket':bucket,'label':LABELS[bucket],'campaigns':sorted({v['campaign_id'] for v in versions}),
                'crm_id':crm['id'] if crm else None,'source':primary['url'] if primary else b['url'],'secondary_source':secondary,
                'request':request['quote'] if request else None,'signal':signal['quote'] if signal else None,
                'date':published,'checked_at':b.get('checked_at'),'age_days':round(age,1) if age is not None else None,
                'warning':warning,'next_action':next_action,'excluded':excluded,'contacts':b['commercial_alignment']['public_channels'],
                'ranking_basis':['stato commerciale','qualità delle prove','contatto disponibile','freschezza della verifica']}})
    counts=Counter(i['worklist']['bucket'] for i in items)
    def ready(i):return i['worklist']['bucket'] in ('verified','potential') and i['body']['commercial_alignment']['READY_FOR_OUTREACH']
    counts['ready']=sum(ready(i) for i in items);counts['all']=len(items)-counts['excluded']
    def promising(i):return i['worklist']['bucket'] in ('review','new') and i['body'].get('completion_queue',{}).get('promising',False)
    counts['promising']=sum(promising(i) for i in items)
    eligible=[i for i in items if i['worklist']['bucket']==view or view=='promising' and promising(i) or view=='ready' and ready(i) or view=='all' and i['worklist']['bucket']!='excluded']
    if grouping=='company':
        grouped_counts=defaultdict(set)
        for i in items:
            key=graph['record_keys'][i['id']];bucket=i['worklist']['bucket']
            grouped_counts[bucket].add(key)
            if ready(i):grouped_counts['ready'].add(key)
            if promising(i):grouped_counts['promising'].add(key)
            if bucket!='excluded':grouped_counts['all'].add(key)
        counts={k:len(grouped_counts[k]) for k in LABELS}
        eligible=group_worklist(eligible,graph,view)
    priority={'VERIFIED':0,'POTENTIAL':1,'RELEVANT':2,'NEEDS_REVIEW':3}
    eligible.sort(key=lambda i:(priority.get(i['state'],4),{'high':0,'medium':1,'low':2}.get(i['body']['priority'],2),{'HIGH_AFFINITY':0,'POSSIBLE_AFFINITY':1,'UNKNOWN_AFFINITY':2,'CLEARLY_UNRELATED':3}.get(i['body']['commercial_alignment']['affinity']['value'],2),not bool(i['worklist']['contacts']),i['worklist']['age_days'] if i['worklist']['age_days'] is not None else float('inf'),-i['id']))
    return {'total':len(eligible),'offset':offset,'limit':limit,'items':eligible[offset:offset+limit],
        'counts':{key:counts[key] for key in LABELS},'view':view,'group':grouping,'count_unit':'companies' if grouping=='company' else 'requests',
        'count_basis':'Unique subjects per view; companies with distinct requests can appear in multiple views.' if grouping=='company' else 'Distinct requests',
        'mode':'WORKLIST','generated_at':at.isoformat(),
        'basis':'saved_originals_manual_feedback_and_crm_no_new_research'}
