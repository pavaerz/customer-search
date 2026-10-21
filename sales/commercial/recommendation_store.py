"""Read-only projections and additive manual job reviews, separate from CRM."""
import json
from datetime import datetime, timezone
from sales.db import now
from .recommendations import rank
from .job_activity import evaluate,window,utc,observation

REVIEW_STATES={'to_review','interesting','not_interesting','reviewed'}

def migrate(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS commercial_job_reviews(
      id INTEGER PRIMARY KEY, opportunity_id INTEGER NOT NULL REFERENCES commercial_opportunities(id),
      revision_id INTEGER NOT NULL REFERENCES commercial_revisions(id), status TEXT NOT NULL,
      created_at TEXT NOT NULL)''')
    connection.execute('CREATE INDEX IF NOT EXISTS commercial_job_review_latest ON commercial_job_reviews(opportunity_id,id)')
    connection.execute('INSERT OR IGNORE INTO research_schema VALUES (65,?)',(now(),))
    connection.execute('''CREATE TABLE IF NOT EXISTS commercial_job_observations(
      id INTEGER PRIMARY KEY, opportunity_id INTEGER NOT NULL REFERENCES commercial_opportunities(id),
      revision_id INTEGER NOT NULL REFERENCES commercial_revisions(id), body TEXT NOT NULL, created_at TEXT NOT NULL)''')
    connection.execute('CREATE INDEX IF NOT EXISTS commercial_job_observations_subject ON commercial_job_observations(opportunity_id,id)')
    connection.execute('INSERT OR IGNORE INTO research_schema VALUES (66,?)',(now(),))

def listing(store,filters=None,as_of=None):
    f=filters or {};args=[];revision='o.latest_revision'
    days=window(f.get('max_job_age_days',14));category=f.get('category','recent')
    if category not in ('recent','verify','archived','all'):raise ValueError('Categoria annunci non valida')
    if f.get('campaign'):
        revision='(SELECT max(cr.id) FROM commercial_revisions cr WHERE cr.opportunity_id=o.id AND cr.campaign_id=?)';args.append(int(f['campaign']))
    with store.connect() as c:
        # Rank/deduplicate before engine filtering so a cross-engine copy never
        # reappears. CRM exclusions prevail without rewriting historical bodies.
        rows=c.execute('''SELECT o.id,o.engine,o.manual_state,r.state,r.id AS selected_revision,r.body,
          co.do_not_contact,co.prior_contacted,
          EXISTS(SELECT 1 FROM dismissed_companies d WHERE d.domain=co.domain) AS company_dismissed,
          (EXISTS(SELECT 1 FROM prospects p WHERE p.company_id=co.id AND p.stage IN ('contacted','replied','proposal','won','lost')) OR
           EXISTS(SELECT 1 FROM interactions i JOIN prospects p ON p.id=i.prospect_id WHERE p.company_id=co.id AND i.kind IN ('contacted','replied','proposal','won','lost'))) AS contacted
          FROM commercial_opportunities o JOIN commercial_revisions r ON r.id='''+revision+'''
          LEFT JOIN research_entities e ON e.id=o.entity_id LEFT JOIN companies co ON co.id=e.company_id''',args).fetchall()
        items=[{**dict(r),'body':json.loads(r['body'])} for r in rows]
        for i in items:
            if i['contacted'] or i['prior_contacted']:i['manual_state']='contacted'
        exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='commercial_job_reviews'").fetchone()
        reviews={r['opportunity_id']:dict(r) for r in c.execute('SELECT * FROM commercial_job_reviews ORDER BY id')} if exists else {}
        has_observations=c.execute("SELECT 1 FROM sqlite_master WHERE name='commercial_job_observations'").fetchone()
        observations={}
        if has_observations:
            for row in c.execute('SELECT * FROM commercial_job_observations ORDER BY id'):
                observations.setdefault(row['opportunity_id'],[]).append({**json.loads(row['body']),'observation_id':row['id'],'revision_id':row['revision_id']})
        social={r['opportunity_id']:r['status'] for r in c.execute('SELECT opportunity_id,status FROM commercial_social_reviews ORDER BY id')}
        for i in items:
            if social.get(i['id']) in ('inactive','irrelevant'):i['manual_state']='discarded'
    clock=as_of or datetime.now(timezone.utc)
    assessed=rank(items,clock,include_inactive=True);byid={r['id']:r for r in assessed};bodies={i['id']:i['body'] for i in items}
    totals={'recent':0,'verify':0,'archived':0}
    # Reviews follow duplicates too: use the latest explicit decision among
    # member IDs, without changing either underlying opportunity.
    for r in assessed:
        if r['duplicate_of'] is not None:continue
        members=[r['id']]+[s['id'] for s in assessed if s['duplicate_of']==r['id']]
        decisions=[reviews[k] for k in members if k in reviews]
        latest=max(decisions,key=lambda d:d['id']) if decisions else None
        r['review_status']=latest['status'] if latest else 'to_review';r['related_ids']=members
    selected=[]
    for r in assessed:
        if not r['recommended']:continue
        # Employment remains consultable explicitly; never takes the default
        # freelance shortlist space. No historical classification is rewritten.
        employee=r.get('relationship',{}).get('type') in ('EMPLOYEE','EMPLOYMENT','INTERNSHIP')
        employment=f.get('employment','freelance')
        if employment not in ('freelance','employment','all'):raise ValueError('Rapporto non valido')
        if employment=='freelance' and (employee or r.get('relationship',{}).get('type')=='UNPAID_OR_EQUITY'):continue
        if employment=='employment' and not employee:continue
        if f.get('engine') and not any(byid[k]['engine']==f['engine'] for k in r['related_ids']):continue
        manual=[e for k in r['related_ids'] for e in observations.get(k,[])]
        # Copy duplicate observations only when they refer to this exact URL;
        # cross-portal identity alone does not establish publication equivalence.
        activity=evaluate(bodies[r['id']],r['engine'],clock,manual,days)
        r['activity']=activity;r['manual_observations']=observations.get(r['id'],[])
        if activity['category']=='not_applicable':activity['category']='verify'
        status=f.get('review','');decision=r['review_status']
        if status=='high' and r['tier']!='HIGH':continue
        if status in REVIEW_STATES and decision!=status:continue
        if not status and decision=='not_interesting':continue
        if f.get('search') and f['search'].casefold() not in (r['title']+' '+str(r['company']['value'] or '')).casefold():continue
        totals[activity['category']]+=1
        if category!='all' and activity['category']!=category:continue
        selected.append(r)
    if category=='recent':selected.sort(key=lambda r:(r['activity']['geographic_priority']!='HIGH',-r['compatibility_score'],r['id']))
    limit=max(1,min(100,int(f.get('limit',20))));offset=max(0,int(f.get('offset',0)))
    return {'items':selected[offset:offset+limit],'total':len(selected),'limit':limit,'offset':offset,
            'category_counts':totals,'max_job_age_days':days,'rank_version':'4.5','not_commercial_qualification':True,
            'duplicates':sum(r['duplicate_of'] is not None for r in assessed)}

def review(store,ident,request):
    status=request.get('status');revision=request.get('revision_id')
    if not isinstance(status,str) or status not in REVIEW_STATES:raise ValueError('Stato annuncio non valido')
    if type(revision)!=int:raise ValueError('Valutazione dell’annuncio richiesta')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute("SELECT 1 FROM commercial_revisions r JOIN commercial_opportunities o ON o.id=r.opportunity_id WHERE r.id=? AND o.id=? AND o.engine<>'WEBSITE_REBUILD'",(revision,ident)).fetchone():raise ValueError('Annuncio o valutazione non trovati')
        c.execute('INSERT INTO commercial_job_reviews(opportunity_id,revision_id,status,created_at) VALUES(?,?,?,?)',(ident,revision,status,now()))
    return {'id':ident,'review_status':status,'commercial_state_changed':False}


def record_observation(store,ident,request,as_of=None):
    """Append a user's dated observation; never infer the observed date."""
    clock=utc(as_of or now());seen=utc(request.get('observed_at'))
    if not seen or seen>clock:raise ValueError('Data e ora di osservazione valide richieste (non future)')
    revision=request.get('revision_id');kind=request.get('kind');note=request.get('note','')
    if type(revision)!=int or not isinstance(note,str) or len(note)>2000:raise ValueError('Osservazione non valida')
    allowed={'closed','open','too_old','geo_incompatible','publication_date'}
    if kind not in allowed:raise ValueError('Tipo di osservazione non valido')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT r.body FROM commercial_revisions r JOIN commercial_opportunities o ON o.id=r.opportunity_id WHERE r.id=? AND o.id=? AND o.engine<>'WEBSITE_REBUILD'",(revision,ident)).fetchone()
        if not row:raise ValueError('Annuncio o revisione non trovati')
        body=json.loads(row[0]);url=body['url']
        fields={'closed':('application','CLOSED_CONFIRMED'), 'open':('application','OPEN_CONFIRMED'),
                'too_old':('publication',None),'geo_incompatible':('geography',note)}
        if kind=='publication_date':
            date=utc(request.get('published_at'))
            if not date or date>seen:raise ValueError('Data di pubblicazione non valida')
            fields[kind]=('publication',date.isoformat())
        if kind=='geo_incompatible' and not note.strip():raise ValueError('Indica la restrizione osservata nella nota')
        k,value=fields[kind]
        e=observation(k,value,url,seen.isoformat(),note,'MANUAL_OBSERVATIONS',
          method='manual_too_old' if kind=='too_old' else 'manual_publication' if kind=='publication_date' else 'manual_review',
          manual_kind=kind,note=note,max_age_days_at_observation=window(request.get('max_job_age_days',14)))
        if kind=='geo_incompatible':e['manual_geo_incompatible']=True
        c.execute('INSERT INTO commercial_job_observations(opportunity_id,revision_id,body,created_at) VALUES(?,?,?,?)',(ident,revision,json.dumps(e,ensure_ascii=False),clock.isoformat()))
    return {'id':ident,'saved':True,'commercial_state_changed':False}


def saved_activity_filter(store,payload,engine,as_of):
    """Known negative observations stop retries before network/AI; no mutation."""
    with store.connect() as c:
        rows=c.execute('''SELECT o.id,r.body FROM commercial_opportunities o
          JOIN commercial_revisions r ON r.id=o.latest_revision
          WHERE o.engine=? AND json_extract(r.body,'$.url')=?''',(engine,payload['url'])).fetchall()
        has=c.execute("SELECT 1 FROM sqlite_master WHERE name='commercial_job_observations'").fetchone()
        for row in rows:
            manual=[json.loads(x[0]) for x in c.execute('SELECT body FROM commercial_job_observations WHERE opportunity_id=?',(row['id'],))] if has else []
            a=evaluate(json.loads(row['body']),engine,as_of,manual,payload.get('max_job_age_days',14))
            if a['category']=='archived' and not a['conflicts']:return a
    return None
