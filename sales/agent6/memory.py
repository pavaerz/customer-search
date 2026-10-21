"""Additive, append-only research memory. Feedback outranks model interpretations."""
import json,re,math
from datetime import datetime,timezone,timedelta
from collections import defaultdict,Counter
from sales.db import encode,digest,now,domain
from . import STATES
from .semantics import decision_metadata

def migrate(c):
    statements=[
      'CREATE TABLE IF NOT EXISTS agent6_memory(id INTEGER PRIMARY KEY,campaign_id INTEGER,flow TEXT,kind TEXT,key TEXT,body TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(campaign_id,flow,kind,key))',
      'CREATE INDEX IF NOT EXISTS agent6_memory_lookup ON agent6_memory(kind,flow,key)',
      'CREATE TABLE IF NOT EXISTS agent6_records(id INTEGER PRIMARY KEY,campaign_id INTEGER NOT NULL,flow TEXT NOT NULL,request_key TEXT NOT NULL,entity_key TEXT,state TEXT NOT NULL,body TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(campaign_id,request_key))',
      'CREATE TABLE IF NOT EXISTS agent6_record_revisions(id INTEGER PRIMARY KEY,record_id INTEGER NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL)',
      'CREATE TABLE IF NOT EXISTS agent6_feedback(id INTEGER PRIMARY KEY,record_id INTEGER NOT NULL,kind TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL)',
      'CREATE TABLE IF NOT EXISTS agent6_entities(key TEXT PRIMARY KEY,name TEXT,domain TEXT,verified INTEGER NOT NULL,body TEXT NOT NULL,updated_at TEXT NOT NULL)',
      'CREATE TABLE IF NOT EXISTS agent6_cache(key TEXT PRIMARY KEY,body TEXT NOT NULL,created_at TEXT NOT NULL)',
      'CREATE TABLE IF NOT EXISTS agent7_diagnostics(execution_id INTEGER PRIMARY KEY,campaign_id INTEGER NOT NULL,task TEXT NOT NULL,excerpt TEXT NOT NULL,errors TEXT NOT NULL,created_at TEXT NOT NULL)',
    ]
    for stmt in statements:c.execute(stmt)
    c.execute('INSERT OR IGNORE INTO research_schema VALUES (600,?)',(now(),))
    c.execute('INSERT OR IGNORE INTO research_schema VALUES (700,?)',(now(),))
    from .annotations import migrate as migrate_annotations
    migrate_annotations(c)
    from .diagnostics import purge
    purge(c)

def active(c,campaign):return c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(campaign['id'],campaign['generation'])).fetchone()
def event(store,campaign,flow,kind,key,body):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not active(c,campaign):raise InterruptedError('Campagna sospesa')
        c.execute('INSERT OR IGNORE INTO agent6_memory(campaign_id,flow,kind,key,body,created_at) VALUES (?,?,?,?,?,?)',(campaign['id'],flow,kind,key,encode(body),now()))

def normalized(query):return ' '.join(re.findall(r'[\w]+',query.casefold().replace('-filetype:pdf','')))
def seen_query(store,flow,query,hours=24):
    from . import canonical_flow
    alias="LINKEDIN" if canonical_flow(flow)=="SOCIAL" else flow
    flow=canonical_flow(flow)
    cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat();words=set(normalized(query).split())
    with store.connect() as c:
        rows=c.execute("SELECT key FROM agent6_memory WHERE flow IN (?,?) AND kind='query' AND created_at>? ORDER BY id DESC LIMIT 1000",(flow,alias,cutoff)).fetchall()
    for row in rows:
        previous=set(row[0].split());union=words|previous
        if row[0]==normalized(query) or union and len(words&previous)/len(union)>=.9:return True
    return False

def request_key(body):
    from sales.commercial.recommendations import canonical_url as canonical
    if body.get('decision_engine')=='ai_first_1':
        if body.get('evidence_unit_id') and not body['evidence_unit_id'].endswith(':page'):
            return digest('unit:'+body['url']+body['evidence_unit_id'])
        return digest('url:'+canonical(body['url']))
    # Explicit role codes join syndications without joining all jobs of a company.
    match=re.search(r'\bI[ -]CPT[ -](\d{4,})\b',body.get('title',''),re.I)
    subject=body.get('entity_name')
    if match and subject:return digest('role:'+subject.casefold()+':'+match[1])
    if body.get('identity_verified') and body.get('kind') in ('COMPANY_SIGNAL','EDITORIAL'):
        return digest('company-signal:'+body['entity_key'])
    return digest('url:'+canonical(body['url']))

def save_record(store,campaign,flow,body,documents=()):
    if body['state'] not in STATES:raise ValueError('Stato agente non valido')
    from .commercial_view import enrich
    from sales.research_store import ResearchStore
    reason=ResearchStore(store).suppressed({'website':body.get('official_domain') or body['url']})
    if reason:body={**body,'state':'REJECTED','reason':reason,'suppressed':True}
    if body.get('decision_engine')!='ai_first_1':
        body={**body,**decision_metadata(body)}
    key=request_key(body);entity=body.get('entity_key')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not active(c,campaign):raise InterruptedError('Campagna sospesa')
        if not body.get('original'):
            # Rediscovery of an already-linked URL must not resurrect an
            # unfinished trace or overwrite its canonical original evaluation.
            linked=c.execute("SELECT json_extract(body,'$.canonical_record_id') FROM agent6_records WHERE campaign_id=? AND request_key=?",(campaign['id'],key)).fetchone()
            if linked and linked[0]:
                target=c.execute('SELECT request_key FROM agent6_records WHERE campaign_id=? AND id=?',(campaign['id'],linked[0])).fetchone()
                if target:key=target[0]
        from .entities import commercial_hold
        hold=commercial_hold(c,body)
        if hold:body={**body,'state':'REJECTED','reason':hold,'suppressed':True}
        excluded=c.execute("SELECT f.kind FROM agent6_feedback f JOIN agent6_records r ON r.id=f.record_id WHERE (r.request_key=? OR (? IS NOT NULL AND r.entity_key=?)) AND f.kind IN ('not_interesting','contacted','replied','proposal','won','lost','restore') ORDER BY f.id DESC LIMIT 1",(key,entity,entity)).fetchone()
        if excluded and excluded[0] in ('not_interesting','contacted','replied','proposal','won','lost'):body={**body,'state':'REJECTED','reason':'Esito commerciale già registrato: '+excluded[0],'suppressed':True}
        for d in documents:
            c.execute('INSERT OR IGNORE INTO research_documents VALUES (?,?,?,?,?,?,?,?,?)',(d['id'],d['url'],d['content_hash'],d.get('title',''),d['text'],d.get('published_at'),d['checked_at'],d.get('provider','Pagina pubblica'),encode({k:v for k,v in d.items() if k!='text'})))
        previous=c.execute('SELECT id,body FROM agent6_records WHERE campaign_id=? AND request_key=?',(campaign['id'],key)).fetchone()
        if previous:
            old=json.loads(previous['body']);body['flows']=sorted(set(old.get('flows',[flow]))|{flow})
            body['source_aliases']=sorted(set(old.get('source_aliases',[]))|set(body.get('source_aliases',[])))
            body['linked_discovery_ids']=sorted(set(old.get('linked_discovery_ids',[]))|set(body.get('linked_discovery_ids',[])))
            # A weak syndicated snippet must not replace an original source evaluation.
            if (old.get('original') or old.get('workflow_state')=='ORIGINAL_READ_FAILED') and not body.get('original'):
                # A later flow rediscovering a snippet cannot erase an actual
                # original-read attempt or its access diagnostic.
                body={**old,'flows':body['flows']}
            elif (body.get('decision_engine')=='ai_first_1' and old.get('validation_status')=='ACCEPTED'
                  and body.get('validation_status') in ('PENDING','MODEL_INVALID')
                  and old.get('evidence_packet',{}).get('document_id')
                  and old['evidence_packet']['document_id']==body.get('evidence_packet',{}).get('document_id')):
                # Replaying the same snapshot cannot erase a completed decision
                # merely because the next inference is pending/technically invalid.
                # A different original is deliberately NOT covered by this guard.
                body={**old,'flows':body['flows'],'latest_research_attempt':{
                    'validation_status':body.get('validation_status'),
                    'technical_error':body.get('technical_error'),'checked_at':now()}}
        else:body['flows']=[flow]
        if hold:body={**body,'state':'REJECTED','reason':hold,'suppressed':True}
        if body.get('decision_engine')=='ai_first_1' and (reason or excluded and excluded[0] in ('not_interesting','contacted','replied','proposal','won','lost')):
            body={**body,'state':'REJECTED','reason':reason or 'Esito commerciale già registrato: '+excluded[0],'suppressed':True}
        body=enrich(body)
        body['request_key']=key;entity=body.get('entity_key')
        c.execute('INSERT INTO agent6_records(campaign_id,flow,request_key,entity_key,state,body,updated_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(campaign_id,request_key) DO UPDATE SET entity_key=excluded.entity_key,state=excluded.state,body=excluded.body,updated_at=excluded.updated_at',(campaign['id'],flow,key,entity,body['state'],encode(body),now()))
        rid=c.execute('SELECT id FROM agent6_records WHERE campaign_id=? AND request_key=?',(campaign['id'],key)).fetchone()[0]
        c.execute('INSERT INTO agent6_record_revisions(record_id,body,created_at) VALUES (?,?,?)',(rid,encode(body),now()))
        from .canonical_records import link
        link(c,campaign['id'],rid,body)
        if entity:
            known=c.execute('SELECT body FROM agent6_entities WHERE key=?',(entity,)).fetchone()
            proofs=(json.loads(known[0]).get('evidence',[]) if known else [])+body.get('facts',[])
            merged=list({digest(encode([f.get('url'),f.get('quote'),f.get('field')])):f for f in proofs}.values())
            c.execute('INSERT INTO agent6_entities VALUES (?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET name=CASE WHEN excluded.verified=1 THEN excluded.name ELSE coalesce(agent6_entities.name,excluded.name) END,domain=CASE WHEN excluded.verified=1 THEN excluded.domain ELSE coalesce(agent6_entities.domain,excluded.domain) END,verified=max(agent6_entities.verified,excluded.verified),body=excluded.body,updated_at=excluded.updated_at',(entity,body.get('entity_name'),body.get('official_domain'),int(body.get('identity_verified',False)),encode({'evidence':merged,'last_campaign':campaign['id'],'contacts':body.get('contacts',[]),'aliases':sorted(set(json.loads(known[0]).get('aliases',[]) if known else [])|{body.get('entity_name') or ''})}),now()))
    event(store,campaign,flow,'decision',str(rid)+':'+digest(encode(body)),{'record_id':rid,'request_key':key,'original':bool(body.get('original')),'query':body.get('query'),'strategy':body.get('strategy'),'domain':domain(body['url']),'state':body['state'],'kind':body.get('kind'),'reason':body.get('reason'),'basis':'objective' if body.get('counterevidence') else 'validated_interpretation','technical_error':body.get('technical_error'),**decision_metadata(body)})
    return rid

FEEDBACK={'restore','interesting','not_interesting','contacted','replied','proposal','won','lost','quality_confirmed','false_positive'}
def feedback(store,rid,kind,note=''):
    if not isinstance(kind,str) or kind not in FEEDBACK or not isinstance(note,str) or len(note)>2000:raise ValueError('Feedback non valido')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        record=c.execute('SELECT state,body FROM agent6_records WHERE id=?',(rid,)).fetchone()
        if not record:raise ValueError('Risultato non trovato')
        if kind in ('quality_confirmed','false_positive'):
            body=json.loads(record['body'])
            if record['state'] not in ('VERIFIED','POTENTIAL') or not body.get('original') or not body.get('identity_verified'):
                raise ValueError('La revisione di qualità riguarda proposte qualificate con fonte originale e identità verificata.')
            if not note.strip():raise ValueError('Indica quali prove confermano o smentiscono la qualifica.')
        c.execute('INSERT INTO agent6_feedback(record_id,kind,note,created_at) VALUES (?,?,?,?)',(rid,kind,note,now()))
    return {'saved':True,'action':'record_only_no_message_sent'}

def query_receipts(store,campaign_id,flow):
    """Current-campaign observations only; technical failures are not zero hits."""
    with store.connect() as c:
        return [{**json.loads(r['body']),'campaign_id':campaign_id} for r in c.execute(
            "SELECT body FROM agent6_memory WHERE campaign_id=? AND flow=? AND kind='query' ORDER BY id DESC",
            (campaign_id,flow))]

def planning_feedback(store,campaign_id,flow):
    """Operational repair/stop advice belongs only to its campaign and flow.

    Cross-campaign commercial outcomes remain in history(). An old exhausted
    budget is neither a current stop instruction nor evidence of no demand.
    Read directly so a busy history cannot hide this campaign's repair advice.
    """
    from . import canonical_flow
    flow=canonical_flow(flow)
    alias='LINKEDIN' if flow=='SOCIAL' else flow
    with store.connect() as c:
        rows=c.execute("SELECT kind,body,created_at FROM agent6_memory WHERE campaign_id=? "
            "AND flow IN (?,?) AND kind IN ('plan_feedback','next_strategy') ORDER BY id DESC LIMIT 30",
            (campaign_id,flow,alias)).fetchall()
    return {key:[{**json.loads(r['body']),'campaign_id':campaign_id,'at':r['created_at']}
                 for r in rows if r['kind']==kind][:3]
            for key,kind in (('plan_feedback','plan_feedback'),('next_strategies','next_strategy'))}

def history(store,flow=None):
    from . import canonical_flow
    alias="LINKEDIN" if canonical_flow(flow)=="SOCIAL" else flow
    flow=canonical_flow(flow)
    with store.connect() as c:
        rows=c.execute('SELECT * FROM agent6_memory WHERE (? IS NULL OR flow IN (?,?)) ORDER BY id DESC LIMIT 4000',(flow,flow,alias)).fetchall()
        reviews=c.execute('SELECT f.*,r.flow,r.body FROM agent6_feedback f JOIN agent6_records r ON r.id=f.record_id WHERE (? IS NULL OR r.flow IN (?,?)) ORDER BY f.id',(flow,flow,alias)).fetchall()
        record_bodies={r['id']:json.loads(r['body']) for r in c.execute('SELECT id,body FROM agent6_records WHERE (? IS NULL OR flow IN (?,?))',(flow,flow,alias))}
        selection_count=c.execute("SELECT count(*) FROM agent6_memory WHERE kind='query' AND (? IS NULL OR flow IN (?,?))",(flow,flow,alias)).fetchone()[0]
    # Read manually changed CRM stages without rewriting the research feedback ledger.
    with store.connect() as c:
        crm=[dict(r) for r in c.execute("SELECT r.id record_id,r.flow,r.body,p.stage kind,p.updated_at created_at FROM prospects p JOIN agent6_records r ON p.identity='agent6:'||r.request_key WHERE r.id=(SELECT max(x.id) FROM agent6_records x WHERE x.request_key=r.request_key) AND p.stage IN ('contacted','replied','proposal','won','lost') AND (? IS NULL OR r.flow IN (?,?))",(flow,flow,alias))]
    reviews=sorted([dict(r) for r in reviews]+crm,key=lambda r:r['created_at'])
    stats=defaultdict(lambda:{'queries':0,'relevant':0,'verified':0,'rejected':0,'technical_errors':0,'semantic_conflicts':0,'scope_exclusions':0,'uncertain_decisions':0,'feedback_weight':0,'human_reviews':0,'domains':Counter(),'estimated_ai_cost':0.0,'model_errors':0})
    query_memory=[];source_memory=defaultdict(lambda:Counter());decisions_seen=set()
    for row in rows:
        b=json.loads(row['body']);strategy=b.get('strategy') or 'unattributed';s=stats[(row['flow'],strategy)]
        if row['kind']=='model':
            s['estimated_ai_cost']+=b.get('estimated_cost') or 0
            s['model_errors']+=int(b.get('status') in ('invalid','error','timeout') or bool(b.get('validation_errors')))
        if row['kind']=='query':
            s['rejected']+=len(b.get('policy_rejections',[]))
            for item in b.get('policy_rejections',[]):
                # AI-first/older receipts may retain the URL without a domain
                # column. Read compatibly; never rewrite historical memory.
                host=item.get('domain') or domain(item.get('url') or '')
                if host:source_memory[(row['flow'],host)]['rejected']+=1
            s['queries']+=1;query_memory.append({'flow':row['flow'],'query':b.get('query'),'at':row['created_at'],'strategy':strategy})
        if row['kind']=='decision':
            if b.get('record_id') in decisions_seen:continue
            decisions_seen.add(b.get('record_id'))
            source=source_memory[(row['flow'],b.get('domain'))]
            if b.get('technical_error'):s['technical_errors']+=1;source['technical_errors']+=1;continue
            if b.get('semantic_conflict'):
                s['semantic_conflicts']+=1;source['semantic_conflicts']+=1
            if b.get('scope_exclusion'):
                s['scope_exclusions']+=1;source['scope_exclusions']+=1
            if b.get('semantic_conflict') or b.get('scope_exclusion'):continue
            from .learning import contradicted_negative
            record=record_bodies.get(b.get('record_id'),{})
            if record.get('decision_engine')!='ai_first_1' and contradicted_negative(record):
                s['semantic_conflicts']+=1;source['semantic_conflicts']+=1;continue
            if b['state'] in ('RELEVANT','POTENTIAL','VERIFIED'):s['relevant']+=1;source['relevant']+=1
            if b['state']=='VERIFIED':s['verified']+=1;source['verified']+=1
            if b['state']=='REJECTED':
                if b.get('negative_feedback_reliable'):
                    s['rejected']+=1;source['rejected']+=1
                else:s['uncertain_decisions']+=1;source['uncertain_decisions']+=1
    # Latest feedback per record counts once; prior feedback remains in the ledger.
    latest={r['record_id']:r for r in reviews}
    weights={'interesting':3,'not_interesting':-4,'contacted':1,'replied':5,'proposal':7,'won':10,'lost':-2,'restore':0,'quality_confirmed':3,'false_positive':-4}
    for row in latest.values():
        b=json.loads(row['body']);s=stats[(row['flow'],b.get('strategy') or 'unattributed')];s['feedback_weight']+=weights[row['kind']];s['human_reviews']+=1
    out=[]
    for (f,key),s in stats.items():
        n=s['queries'];automatic=(s['relevant']+2*s['verified']-.5*s['rejected'])/max(1,n)
        adjustment=max(-3,min(3,automatic)) if n>=3 else 0
        out.append({'flow':f,'strategy':key,**s,'priority_adjustment':round(adjustment+2*s['feedback_weight']/max(1,s['human_reviews']),3),'sample_sufficient':n>=3,'precision':None,'basis':'descriptive_counts_and_human_feedback_not_prediction'})
    from .learning import summarize
    from .annotations import read as annotations_read,learning as annotations_learning,latest as annotations_latest
    annotation_rows=[r for r in annotations_read(store) if flow is None or canonical_flow(r['flow'])==flow]
    corrections=annotations_learning(annotation_rows)
    groups=summarize(rows,reviews,record_bodies,annotations_latest(annotation_rows))
    for group in groups:
        correction=next((r for r in corrections if r['strategy_id']==group['strategy_id']),None)
        if correction:
            group['annotation_adjustment']=correction['priority_adjustment']
            group['priority_adjustment']=round(max(-5,min(5,group['priority_adjustment']+correction['priority_adjustment'])),3)
    return {'flow':flow,'strategy_groups':groups,'manual_corrections':corrections,'selection_count':selection_count,'strategies':out,'recent_queries':query_memory[:30],'sources':[{'flow':f,'domain':d,**s} for (f,d),s in source_memory.items()],'feedback_count':len(reviews),'precision_measured':None,'legacy_context':legacy_context(store,flow),'shared_companies':shared_companies(store),'plan_feedback':[json.loads(r['body']) for r in rows if r['kind']=='plan_feedback'][:6],'next_strategies':[json.loads(r['body']) for r in rows if r['kind']=='next_strategy'][:3]}

def choose(queries,memory,round_index,exploration_percent):
    if not queries:return None
    if 'strategy_groups' in memory and all(q.get('query') for q in queries):
        from .learning import strategy_id
        groups={s['strategy_id']:s for s in memory['strategy_groups']}
        key=lambda q:strategy_id(q['query'],memory.get('flow'))
        def info(q):return groups.get(key(q),{})
        # The exploration schedule continues across campaigns and Resume.
        index=memory.get('selection_count',round_index)
        explore=((index+1)*exploration_percent//100)>(index*exploration_percent//100)
        selected=min(queries,key=lambda q:info(q).get('queries',0)) if explore else max(queries,key=lambda q:info(q).get('priority_adjustment',0))
        return {**selected,'strategy_id':key(selected),'selection':'exploration' if explore else 'exploitation',
                'memory_adjustment':info(selected).get('priority_adjustment',0),'memory_samples':info(selected).get('queries',0),
                'ranking_basis':'stable_strategy_family_observed_outcomes','selection_index':index}
    score={v['strategy']:v['priority_adjustment'] for v in memory['strategies']}
    # Deterministic accumulator: exactly the configured quota over 100 decisions.
    explore=((round_index+1)*exploration_percent//100)>(round_index*exploration_percent//100)
    selected=min(queries,key=lambda q:sum(h['strategy']==q['strategy'] for h in memory['recent_queries'])) if explore else max(queries,key=lambda q:score.get(q['strategy'],0))
    return {**selected,'selection':'exploration' if explore else 'exploitation','memory_adjustment':score.get(selected['strategy'],0)}


def shared_companies(store):
    with store.connect() as c:
        rows=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('SELECT * FROM agent6_records ORDER BY updated_at DESC,id DESC')]
    from .entities import index,dossier
    graph=index(rows);out=[]
    for group in graph['groups'].values():
        verified=[r for r in group if r['body'].get('identity_verified')]
        if not verified:continue
        r=verified[0];d=dossier(graph,r['id'])
        out.append({'name':r['body'].get('entity_name'),'domain':r['body'].get('official_domain'),
            'domains':d['domains'],'verified':True,'last_checked':r['body'].get('checked_at'),
            'evidence':d['evidence'][:3],'flows':d['flows'],'entity_view_key':d['key'],
            'request_count':len(d['signals']),'basis':d['basis']})
        if len(out)>=12:break
    return out

def legacy_context(store,flow):
    """Read-only bridge: historical classifications are observations, not ground truth."""
    aliases={'AZIENDE':'FREELANCE','AGENCIES':'AGENCIES','STARTUPS':'STARTUPS','LINKEDIN':'FREELANCE','SOCIAL':'FREELANCE','NEWS':'STARTUPS'}
    with store.connect() as c:
        rows=c.execute("SELECT campaign_id,query,decision,body FROM commercial_discovery WHERE (? IS NULL OR engine=?) ORDER BY id DESC LIMIT 250",(flow,aliases.get(flow,flow))).fetchall()
    queries={}
    for r in rows:
        if not r['query']:continue
        q=queries.setdefault(r['query'],{'query':r['query'],'campaign':r['campaign_id'],'observed_decisions':{},'reasons':[],'basis':'historical_automatic_not_manual_truth'})
        q['observed_decisions'][r['decision']]=q['observed_decisions'].get(r['decision'],0)+1
        reason=json.loads(r['body']).get('reason')
        if reason and reason not in q['reasons'] and len(q['reasons'])<3:q['reasons'].append(reason)
    return list(queries.values())[:8]
