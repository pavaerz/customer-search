"""Local read views, explicit feedback and cost preview; no external calls."""
import json
from collections import Counter
from sales.db import encode,domain
from . import FLOWS,STATES,config,VERSION,canonical_flow,flow_label
from . import memory

def validate_start(store,filters):
    cfg=filters['commercial']['ai']
    if not cfg['enabled'] or cfg['provider']=='DISABLED':raise ValueError('L’agente 6.0 richiede AI abilitata. Configurala nelle impostazioni prima di avviare.')
    if store.settings()['provider']!='serper' and cfg['provider']!='MOCK':raise ValueError('L’agente 6.0 usa Serper: selezionalo nelle impostazioni.')

def preview(store,filters):
    from sales.commercial.catalog import options
    from sales.commercial.ai_settings import campaign_config
    from sales.commercial.search_intelligence import approval_token
    if not isinstance(filters,dict):raise ValueError('Filtri non validi')
    f={**filters,'agent_version':'6.0','decision_engine':'ai_first_1','discovery_triage_version':1,'continuation_version':1}
    from .social_seeds import validate_filters
    if 'social_urls' in f:f['social_urls']=validate_filters(f)
    config(f.get('agent_settings'));flows,limits=options(f);a=campaign_config(store,f)['ai']
    return {'social_urls':f.get('social_urls',[]),'version':VERSION,'flows':{k:flow_label(k) for k in flows},'limits_per_flow':limits,'ai':a,'max_serper_requests':len(flows)*min(limits['max_provider_requests'],limits['max_serper_credits']),'approval_token':approval_token(f,limits,a),'strategy':'Query AI, proposte salvate e alternative controllate dopo esiti improduttivi: stessi controlli prima della ricerca. Nessuna chiamata eseguita in anteprima.','exploration':config(f.get('agent_settings'))['exploration_percent'],'warning':'Massimi autorizzati, non una previsione di spesa. I limiti AI sono condivisi tra i flussi. AI-first valuta gli originali; i controlli validano prove e sicurezza. La modalità Shadow configurata non esegue un confronto parallelo con il legacy.'}

def listing(store,params=None):
    p=params or {};cid=int(p['campaign']) if p.get('campaign') else None;flow=p.get('flow') or None;state=p.get('state') or None
    if flow and canonical_flow(flow) not in FLOWS or state and state not in STATES:raise ValueError('Filtro non valido')
    alias='LINKEDIN' if canonical_flow(flow)=='SOCIAL' else flow
    flow=canonical_flow(flow)
    offset=max(0,int(p.get('offset',0)));limit=min(100,max(1,int(p.get('limit',25))))
    where="(? IS NULL OR r.campaign_id=?) AND (? IS NULL OR EXISTS (SELECT 1 FROM json_each(json_extract(r.body,'$.flows')) WHERE value IN (?,?))) AND (? IS NULL OR r.state=?)";args=(cid,cid,flow,flow,alias,state,state)
    if str(p.get('include_excluded','0'))!='1':where+=" AND coalesce((SELECT kind FROM agent6_feedback f WHERE f.record_id=r.id AND kind IN ('not_interesting','restore') ORDER BY id DESC LIMIT 1),'')<>'not_interesting'"
    where+=" AND json_extract(r.body,'$.canonical_record_id') IS NULL"
    with store.connect() as c:
        total=c.execute('SELECT count(*) FROM agent6_records r WHERE '+where,args).fetchone()[0]
        rows=c.execute('SELECT r.*,(SELECT kind FROM agent6_feedback f WHERE f.record_id=r.id ORDER BY f.id DESC LIMIT 1) feedback FROM agent6_records r WHERE '+where+" ORDER BY CASE r.state WHEN 'VERIFIED' THEN 0 WHEN 'POTENTIAL' THEN 1 WHEN 'RELEVANT' THEN 2 WHEN 'NEEDS_REVIEW' THEN 3 ELSE 4 END,r.id DESC LIMIT ? OFFSET ?",(*args,limit,offset)).fetchall()
    return {'total':total,'offset':offset,'limit':limit,'items':[{**dict(r),'body':json.loads(r['body'])} for r in rows]}

def dossier(store,rid):
    with store.connect() as c:
        r=c.execute('SELECT * FROM agent6_records WHERE id=?',(rid,)).fetchone()
        if not r:raise ValueError('Scheda non trovata')
        revisions=[json.loads(x[0]) for x in c.execute('SELECT body FROM agent6_record_revisions WHERE record_id=? ORDER BY id',(rid,))]
        feedback=[dict(x) for x in c.execute('SELECT * FROM agent6_feedback WHERE record_id=? ORDER BY id',(rid,))]
        rows=[{**dict(x),'body':json.loads(x['body'])} for x in c.execute('SELECT * FROM agent6_records')]
    from .entities import index,dossier as company_dossier
    from .annotations import read as read_annotations,latest as latest_annotations
    annotations=read_annotations(store)
    from .followups import read as read_resolutions
    return {**dict(r),'body':json.loads(r['body']),'revisions':revisions,'feedback':feedback,
        'research_resolution':read_resolutions(store,rows).get(rid),
        'manual_corrections':latest_annotations(annotations).get(r['request_key'],{}),
        'correction_history':[{k:a[k] for k in ('id','record_id','changes','note','created_at')} for a in annotations if a['request_key']==r['request_key']],
        'company_dossier':company_dossier(index(rows),rid)}

def counts(store,cid):
    from sales.commercial.ai import summary
    from sales.commercial.catalog import options
    from sales.commercial.resources import availability
    with store.connect() as c:
        f=json.loads(c.execute('SELECT filters FROM campaigns WHERE id=?',(cid,)).fetchone()[0]);flows,limits=options(f)
        rows=c.execute("SELECT r.* FROM agent6_records r WHERE campaign_id=? AND coalesce((SELECT kind FROM agent6_feedback f WHERE f.record_id=r.id AND kind IN ('not_interesting','restore') ORDER BY id DESC LIMIT 1),'')<>'not_interesting'",(cid,)).fetchall()
        tasks=c.execute('SELECT kind,state,count(*) n FROM research_tasks WHERE campaign_id=? GROUP BY kind,state',(cid,)).fetchall()
        runs=[dict(r) for r in c.execute('SELECT * FROM commercial_engine_runs WHERE campaign_id=?',(cid,))]
        resources=[dict(r) for r in c.execute('SELECT * FROM commercial_resources WHERE campaign_id=?',(cid,))]
        discovered=c.execute("SELECT count(*) FROM commercial_discovery WHERE campaign_id=? AND coalesce(json_extract(body,'$.reason'),'')<>'excluded_pdf'",(cid,)).fetchone()[0]
    with store.connect() as c:
        unique_urls=c.execute("SELECT count(DISTINCT url) FROM commercial_discovery WHERE campaign_id=? AND coalesce(json_extract(body,'$.reason'),'')<>'excluded_pdf'",(cid,)).fetchone()[0]
        duplicates=c.execute("SELECT count(*) FROM commercial_discovery WHERE campaign_id=? AND decision='duplicate'",(cid,)).fetchone()[0]
    rows=[r for r in rows if not json.loads(r['body']).get('canonical_record_id')]
    totals={s:sum(r['state']==s for r in rows) for s in STATES}
    for run in runs:run['counts']={s:sum(r['state']==s and run['engine'] in json.loads(r['body']).get('flows',[]) for r in rows) for s in STATES}
    useful={r['entity_key'] for r in rows if r['state'] in ('VERIFIED','POTENTIAL') and r['entity_key']}
    metrics=summary(store,cid)
    from .activity import measures
    activity=measures([{**dict(r),'body':json.loads(r['body'])} for r in rows],tasks)
    from .pipeline_metrics import summarize as pipeline_metrics
    with store.connect() as c:activity['pipeline']=pipeline_metrics(c,cid,rows)
    ai_config=f['commercial']['ai']
    activity['ai_capacity']={'calls_remaining':max(0,ai_config['max_calls_per_campaign']-metrics['calls']),
        'estimated_usd_remaining':max(0,ai_config['max_estimated_cost']-metrics['estimated_cost']),
        'basis':'configured_campaign_limits_not_provider_balance'}
    return {'activity':activity,'unique_urls':unique_urls,'duplicates':duplicates,'false_positives':None,'manual_precision':None,'technical_errors':sum(bool(json.loads(r['body']).get('technical_error')) for r in rows),'cost_per_useful':metrics['estimated_cost']/len(useful) if useful else None,'cost_per_verified':metrics['estimated_cost']/totals['VERIFIED'] if totals['VERIFIED'] else None,'agent_version':'6.0','commercial':True,'commercial_counts':totals,'engine_runs':runs,'resources':resources,'resource_limits':limits,'ai':metrics,'examined':sum(json.loads(r['body']).get('original',False) for r in rows),'identified_companies':len({r['entity_key'] for r in rows if r['entity_key']}),'discovered':discovered,'search_results':discovered,'qualified':totals['VERIFIED'],'potential':totals['POTENTIAL'],'useful_companies':len(useful),'rejected':totals['REJECTED'],'needs_review':totals['NEEDS_REVIEW'],'unverifiable':totals['UNVERIFIABLE'],'verifying':sum(t['n'] for t in tasks if t['state']=='working'),'promising':totals['RELEVANT']+totals['NEEDS_REVIEW'],**availability(store,cid,limits,flows)}

def save_contact(store,rid):
    b=dossier(store,rid)['body']
    from .quality import latest as quality_reviews
    if quality_reviews(store).get(b['request_key'],{}).get('kind')=='false_positive':raise ValueError('Qualifica contestata: completa una nuova revisione delle prove prima di salvare il contatto.')
    with store.connect() as c:
        old=c.execute('SELECT id FROM prospects WHERE identity=?',('agent6:'+b['request_key'],)).fetchone()
    if old:return {'prospect_id':old[0],'message':'Scheda già presente nei contatti; note e stato conservati.'}
    if b['state'] not in ('VERIFIED','POTENTIAL') or not b.get('identity_verified'):raise ValueError('Identità e qualificazione necessarie per salvare il contatto')
    from .entities import commercial_hold
    with store.connect() as c:hold=commercial_hold(c,b)
    if hold:raise ValueError(hold)
    from sales.research_store import ResearchStore
    if ResearchStore(store).suppressed({'website':b['official_domain']}):raise ValueError('Contatto escluso o già gestito')
    cid=store.company(b['official_domain'],b['entity_name'],contacts=b['contacts'])
    ids=[]
    for f in b['facts']:
        sid=store.source({'url':f['url'],'excerpt':f['quote']},cid)
        ids.append(store.add_evidence(cid,sid,'A','fact',f['field'],f['quote'],confidence='interpretation',metadata=f))
    pid,_=store.prospect(cid,'A',b['title'],b.get('service') or 'website',0,{},b['reason'],b['hypothesis'],b['missing'],ids,identity='agent6:'+b['request_key'])
    return {'prospect_id':pid,'message':'Salvato nei contatti. Nessun messaggio inviato.'}


def intelligence(store):
    from sales.commercial.ai import summary
    result=memory.history(store)
    with store.connect() as c:
        campaigns=[dict(r) for r in c.execute('SELECT id,status,filters,created_at FROM campaigns ORDER BY id DESC LIMIT 8')]
        models=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute("SELECT * FROM agent6_memory WHERE kind IN ('plan','verification') ORDER BY id DESC LIMIT 12")]
    comparison=[]
    for row in campaigns:
        f=json.loads(row['filters'])
        if f.get('agent_version')=='6.0':
            data=counts(store,row['id']);states=data['commercial_counts'];companies=data['identified_companies']
        else:
            with store.connect() as c:
                states=dict(c.execute('SELECT state,count(*) FROM commercial_revisions WHERE campaign_id=? GROUP BY state',(row['id'],)).fetchall())
            companies=None
        a=summary(store,row['id']);comparison.append({'campaign':row['id'],'version':f.get('runtime_version') or f.get('agent_version') or f.get('demand_version') or 'legacy','status':row['status'],'states':states,'identified_companies':companies,'ai_calls':a['calls'],'ai_cost_estimated':a['estimated_cost'],'note':'Valutazioni automatiche; nessuna misura di conversione.'})
    from .quality import summary as quality_summary
    return {**result,'campaign_comparison':comparison,'recent_actions':models,'quality':quality_summary(store)}
