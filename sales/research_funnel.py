"""Persistent discovery frontier, preliminary evidence and manual commercial outcomes."""
import json
from datetime import datetime,timezone,timedelta
from .db import now,encode,digest,domain
from .research_strategies import STRATEGIES

STATES=('discovered','needs_review','promising','verifying','qualified','unverifiable','rejected')
FEEDBACK={'interesting':'Interessante','not_relevant':'Non pertinente','contacted':'Contattato','no_reply':'Nessuna risposta','negative_reply':'Risposta negativa','positive_reply':'Risposta positiva','conversation':'Conversazione avviata','quote':'Preventivo richiesto','won':'Cliente acquisito'}

def candidate_selection(filters):
    """Shared selection for cards and counts; filter states after company dedupe."""
    clauses=['1=1'];args=[]
    if filters.get('campaign'):clauses.append('campaign_id=?');args.append(filters['campaign'])
    company_only=str(filters.get('company_only',''))=='1'
    if company_only:
        from .prospect_scope import NON_BUYERS
        clauses.extend(["identity_status='verified'", "coalesce(json_extract(details,'$.publisher'),0)=0", "coalesce(domain,'')<>''"])
        clauses.append("(json_extract(details,'$.company_ready')=1 OR state='qualified' OR (contact_group='agencies' AND state IN ('promising','verifying')))")
        for host in NON_BUYERS:
            clauses.append('(domain<>? AND domain NOT LIKE ?)');args.extend([host,'%.'+host])
    source='discovery_candidates WHERE '+' AND '.join(clauses)
    if company_only:
        source="""(SELECT *,row_number() OVER (
            PARTITION BY coalesce(nullif(json_extract(details,'$.identity.legal_id'),''),domain)
            ORDER BY (state='verifying') DESC,(assessment_id IS NOT NULL) DESC,
                     assessment_id DESC,updated_at DESC,id DESC
            ) AS company_row FROM """+source+") WHERE company_row=1"
    # Filters must not resurrect stale pages of an already reviewed company.
    source='(SELECT * FROM '+source+') WHERE 1=1'
    for key,col in [('state','state'),('strategy','strategy'),('group','contact_group'),('region','region')]:
        if filters.get(key):source+=' AND '+col+'=?';args.append(filters[key])
    if filters.get('search'):
        source+=' AND (name LIKE ? OR url LIKE ?)';args.extend(['%'+str(filters['search'])[:200]+'%']*2)
    return source,args


def migrate(store):
    statements=[
      '''CREATE TABLE IF NOT EXISTS discovery_frontier(id INTEGER PRIMARY KEY,campaign_id INTEGER NOT NULL REFERENCES campaigns(id),kind TEXT NOT NULL,strategy TEXT NOT NULL,payload TEXT NOT NULL,fingerprint TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL,UNIQUE(campaign_id,fingerprint))''',
      'CREATE INDEX IF NOT EXISTS frontier_ready ON discovery_frontier(campaign_id,state,strategy,id)',
      '''CREATE TABLE IF NOT EXISTS discovery_candidates(id INTEGER PRIMARY KEY,campaign_id INTEGER NOT NULL REFERENCES campaigns(id),url TEXT NOT NULL,name TEXT NOT NULL DEFAULT '',domain TEXT,identity_status TEXT NOT NULL DEFAULT 'unknown',contact_group TEXT NOT NULL DEFAULT 'direct',region TEXT,strategy TEXT NOT NULL,state TEXT NOT NULL,reason TEXT NOT NULL,details TEXT NOT NULL,assessment_id INTEGER REFERENCES research_assessments(id),created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(campaign_id,url))''',
      '''CREATE TABLE IF NOT EXISTS discovery_transitions(id INTEGER PRIMARY KEY,candidate_id INTEGER NOT NULL REFERENCES discovery_candidates(id),state TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL)''',
      '''CREATE TABLE IF NOT EXISTS commercial_outcomes(id INTEGER PRIMARY KEY,candidate_id INTEGER REFERENCES discovery_candidates(id),assessment_id INTEGER REFERENCES research_assessments(id),kind TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL)''',
      'CREATE INDEX IF NOT EXISTS candidates_campaign ON discovery_candidates(campaign_id,state,strategy)',
    ]
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        for sql in statements:c.execute(sql)
        c.execute('INSERT OR IGNORE INTO research_schema VALUES (41,?)',(now(),))

class Funnel:
    def __init__(self,rs):self.rs=rs;self.store=rs.store
    def offer(self,cid,kind,strategy,payload,key=None):
        key=key or digest(encode([kind,strategy,payload]))
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM campaigns WHERE id=? AND status IN ('running','waiting')",(cid,)).fetchone():return False
            if kind=='verify':
                from .evaluation_policy import stamp
                filters=json.loads(c.execute('SELECT filters FROM campaigns WHERE id=?',(cid,)).fetchone()[0])
                payload={**payload,'evaluation_policy':stamp(filters)}
                prior=c.execute('SELECT payload FROM discovery_frontier WHERE campaign_id=? AND fingerprint=?',(cid,key)).fetchone()
                if prior and json.loads(prior[0]).get('evaluation_policy')!=payload['evaluation_policy']:
                    key+=':policy:'+digest(encode(payload['evaluation_policy']))
                from .company_queue import coalesce,review_budget
                payload,reason=review_budget(c,cid,payload)
                if reason:
                    c.execute('INSERT INTO research_events(campaign_id,kind,message,url,details,created_at) VALUES (?,?,?,?,?,?)',
                        (cid,'review_budget',reason,payload.get('url'),encode({'outcome':'not_executed','scope':'subject'}),now()))
                    return False
                handled=coalesce(c,cid,payload,key)
                if handled is not None:return handled
            return bool(c.execute('INSERT OR IGNORE INTO discovery_frontier(campaign_id,kind,strategy,payload,fingerprint,created_at) VALUES (?,?,?,?,?,?)',(cid,kind,strategy,encode(payload),key,now())).rowcount)
    def constrain_legacy_queue(self,campaign):
        """Defer old 4.0 pending work without deleting task IDs or evidence."""
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(campaign['id'],campaign['generation'])).fetchone():return
            rows=c.execute("SELECT * FROM research_tasks WHERE campaign_id=? AND state='pending' ORDER BY id LIMIT -1 OFFSET 48",(campaign['id'],)).fetchall()
            for r in rows:
                c.execute("INSERT OR IGNORE INTO discovery_frontier(campaign_id,kind,strategy,payload,fingerprint,created_at) VALUES (?,?,?,?,?,?)",(r['campaign_id'],r['kind'],r['strategy'],r['payload'],r['fingerprint'],r['created_at']))
                c.execute("UPDATE research_tasks SET state='deferred' WHERE id=?",(r['id'],))
    def fill(self,campaign):
        """At most 48 runnable jobs, fair round robin. This is backpressure, not a total budget."""
        cid=campaign['id']
        from .research_api import commercial_feedback
        preferred=commercial_feedback(self.store)['preferred']
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(cid,campaign['generation'])).fetchone():return 0
            n=c.execute("SELECT count(*) FROM research_tasks WHERE campaign_id=? AND state IN ('pending','working')",(cid,)).fetchone()[0]
            added=0
            turn=c.execute('SELECT count(*) FROM research_tasks WHERE campaign_id=?',(cid,)).fetchone()[0]
            while n<48:
                bonus=preferred if (turn+added)%5==4 else ''
                rows=c.execute("""SELECT f.* FROM discovery_frontier f WHERE f.campaign_id=? AND f.state='pending'
                ORDER BY CASE f.kind WHEN 'verify' THEN 0 WHEN 'candidate' THEN 1 WHEN 'source' THEN 2 ELSE 3 END,CASE WHEN f.strategy=? THEN 0 ELSE 1 END,(SELECT count(*) FROM research_tasks t WHERE t.campaign_id=f.campaign_id AND t.strategy=f.strategy AND t.kind=f.kind AND (f.kind<>'candidate' OR coalesce(json_extract(t.payload,'$.publisher'),0)=coalesce(json_extract(f.payload,'$.publisher'),0))),CASE WHEN f.kind='search' AND f.strategy='companies' THEN 0 ELSE 1 END,f.id LIMIT 1""",(cid,bonus)).fetchall()
                if not rows:break
                r=rows[0]
                from .discovery_control import available
                blocked=r['kind']=='search' and not available(self.store) and c.execute("SELECT 1 FROM research_tasks WHERE campaign_id=? AND kind='search' AND state='blocked'",(cid,)).fetchone()
                if blocked:
                    c.execute("UPDATE discovery_frontier SET state='blocked' WHERE campaign_id=? AND kind='search' AND state='pending'",(cid,));continue
                c.execute('INSERT OR IGNORE INTO research_tasks(campaign_id,kind,strategy,payload,fingerprint,available_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',(cid,r['kind'],r['strategy'],r['payload'],r['fingerprint'],now(),now(),now()))
                c.execute("UPDATE research_tasks SET state='pending' WHERE campaign_id=? AND fingerprint=? AND state='deferred'",(cid,r['fingerprint']))
                c.execute("UPDATE discovery_frontier SET state='assigned' WHERE id=?",(r['id'],));n+=1;added+=1
        return added
    def transition(self,campaign,payload,state,reason,details=None,assessment_id=None):
        if state not in STATES:raise ValueError('Stato preliminare non valido')
        url=payload['url'];details=details or {};identity=details.get('identity',{})
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(campaign['id'],campaign['generation'])).fetchone():return None
            old=c.execute('SELECT * FROM discovery_candidates WHERE campaign_id=? AND url=?',(campaign['id'],url)).fetchone()
            merged={**(json.loads(old['details']) if old else {}),**details}
            from .evaluation_policy import stamp
            if payload.get('reevaluation') and payload['reevaluation'] not in merged.get('evaluation_history',[]):
                merged['evaluation_history']=merged.get('evaluation_history',[])+[payload['reevaluation']]
            merged['evaluation_policy']=stamp(payload.get('filters') or campaign.get('filters'))
            for clock_key in ('elapsed_seconds','deep_seconds'):
                if clock_key in details and old:merged[clock_key]=json.loads(old['details']).get(clock_key,0)+details[clock_key]
            provenance=list(dict.fromkeys(merged.get('strategies',[])+[payload.get('strategy','change')]))
            merged.setdefault('acquisition_provider',payload.get('acquisition_provider'));merged.setdefault('query_key',payload.get('query_key'))
            merged.update(__import__('sales.commercial_planner',fromlist=['source_payload']).source_payload(payload))
            merged['strategies']=provenance;merged.setdefault('provider',payload.get('provider'));merged.setdefault('source_url',payload.get('source_url'))
            from .discovery_relevance import visit_purpose
            merged.setdefault('visit_purpose',visit_purpose(payload))
            for field in ('query','query_page','subject','company_host','alternative_source'):
                if payload.get(field) is not None:merged.setdefault(field,payload[field])
            c.execute('''INSERT INTO discovery_candidates(campaign_id,url,name,domain,identity_status,contact_group,region,strategy,state,reason,details,assessment_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
             ON CONFLICT(campaign_id,url) DO UPDATE SET name=CASE WHEN excluded.name!='' THEN excluded.name ELSE discovery_candidates.name END,domain=coalesce(excluded.domain,discovery_candidates.domain),identity_status=CASE WHEN excluded.identity_status='verified' THEN 'verified' ELSE discovery_candidates.identity_status END,contact_group=excluded.contact_group,region=coalesce(excluded.region,discovery_candidates.region),state=excluded.state,reason=excluded.reason,details=excluded.details,assessment_id=coalesce(excluded.assessment_id,discovery_candidates.assessment_id),updated_at=excluded.updated_at''',
             (campaign['id'],url,identity.get('name') or payload.get('title',''),domain(identity.get('website','')) or None,identity.get('identity_status','unknown'),identity.get('group',merged.get('group','direct')),identity.get('region'),payload.get('strategy','change'),state,reason,encode(merged),assessment_id,now(),now()))
            ident=c.execute('SELECT id FROM discovery_candidates WHERE campaign_id=? AND url=?',(campaign['id'],url)).fetchone()[0]
            if not old or old['state']!=state or old['reason']!=reason:c.execute('INSERT INTO discovery_transitions(candidate_id,state,reason,created_at) VALUES (?,?,?,?)',(ident,state,reason,now()))
        from .discovery_control import annotate
        from .operation_outcomes import decision
        annotate(**decision(state,identity))
        return ident
    def listing(self,filters=None):
        filters=filters or {}
        offset=max(0,int(filters.get('offset',0)));limit=max(1,min(100,int(filters.get('limit',20))))
        source,args=candidate_selection(filters)
        group_source,group_args=candidate_selection({k:v for k,v in filters.items() if k!='group'})
        with self.store.connect() as c:
            c.execute('BEGIN')  # Cards and counts share the same SQLite snapshot.
            group_counts={r[0]:r[1] for r in c.execute('SELECT contact_group,count(*) FROM '+group_source+' GROUP BY contact_group',group_args)}
            total=c.execute('SELECT count(*) FROM '+source,args).fetchone()[0]
            rows=c.execute('SELECT * FROM '+source+" ORDER BY CASE state WHEN 'promising' THEN 0 WHEN 'verifying' THEN 1 ELSE 2 END,id DESC LIMIT ? OFFSET ?",(*args,limit,offset)).fetchall()
            items=[]
            for r in rows:
                outcomes=[dict(x) for x in c.execute('SELECT kind,note,created_at FROM commercial_outcomes WHERE candidate_id=? ORDER BY id DESC LIMIT 10',(r['id'],))]
                items.append({**dict(r),'details':json.loads(r['details']),'outcomes':outcomes})
        return {'items':items,'total':total,'offset':offset,'limit':limit,'group_counts':group_counts}
    def outcome(self,kind,note='',candidate_id=None,assessment_id=None):
        if kind not in FEEDBACK or not isinstance(note,str) or len(note)>3000:raise ValueError('Esito commerciale non valido')
        if not candidate_id and not assessment_id:raise ValueError('Azienda da indicare')
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if candidate_id:
                row=c.execute('SELECT * FROM discovery_candidates WHERE id=?',(candidate_id,)).fetchone()
                if not row:raise ValueError('Candidato non trovato')
                assessment_id=row['assessment_id']
                if kind=='contacted' and row['identity_status']=='verified' and row['domain']:
                    identity=json.loads(row['details']).get('identity',{})
                    c.execute('''INSERT INTO companies(domain,name,website,prior_contacted,created_at) VALUES (?,?,?,1,?) ON CONFLICT(domain) DO UPDATE SET prior_contacted=1''',(row['domain'],row['name'],identity.get('website') or row['url'],now()))
            if assessment_id and not c.execute('SELECT 1 FROM research_assessments WHERE id=?',(assessment_id,)).fetchone():raise ValueError('Valutazione non trovata')
            c.execute('INSERT INTO commercial_outcomes(candidate_id,assessment_id,kind,note,created_at) VALUES (?,?,?,?,?)',(candidate_id,assessment_id,kind,note,now()))
            # CRM stages remain user actions; no send or automatic conversion is inferred.
            stage={'contacted':'contacted','negative_reply':'lost','positive_reply':'replied','conversation':'replied','quote':'proposal','won':'won'}.get(kind)
            if assessment_id and stage:
                row=c.execute('SELECT prospect_id FROM research_assessments WHERE id=?',(assessment_id,)).fetchone()
                if row and row[0]:
                    c.execute('UPDATE prospects SET stage=?,updated_at=? WHERE id=?',(stage,now(),row[0]))
                    c.execute('INSERT INTO interactions(prospect_id,kind,detail,created_at) VALUES (?,?,?,?)',(row[0],stage,FEEDBACK[kind]+(': '+note if note else ''),now()))
        return {'ok':True}
    def metrics(self,cid):
        groups={key:{'strategy':key,'label':label,'discovered':0,'companies':0,'promising':0,'qualified':0,'rejected':0,'unverifiable':0,'sources':0,'seconds':0,'contacted':0,'replied':0,'positive_reply':0,'conversation':0,'quote':0,'won':0,'no_reply':0} for key,label in STRATEGIES.items()}
        with self.store.connect() as c:
            rows=c.execute('SELECT * FROM discovery_candidates WHERE campaign_id=? ORDER BY id',(cid,)).fetchall();seen={};attribution={};companies={key:set() for key in groups};manual={key:{} for key in groups}
            for r in rows:
                g=groups.get(r['strategy'],groups['change']);g['discovered']+=1;detail=json.loads(r['details']);g['seconds']+=detail.get('elapsed_seconds',0)+detail.get('deep_seconds',0)
                if r['identity_status']=='verified' and r['domain']:companies[g['strategy']].add(r['domain'])
                decision_key=(g['strategy'],r['domain'] or r['url'],r['state'])
                if r['state'] in ('qualified','rejected','unverifiable') and decision_key not in seen:g[r['state']]+=1;seen[decision_key]=True
                if c.execute("SELECT 1 FROM discovery_transitions WHERE candidate_id=? AND state='promising'",(r['id'],)).fetchone():g['promising']+=1
                identity=detail.get('identity',{}).get('legal_id') or r['domain'] or r['url']
                first_strategy=attribution.setdefault(identity,g['strategy'])
                events={v[0] for v in c.execute('SELECT kind FROM commercial_outcomes WHERE candidate_id=? OR (assessment_id IS NOT NULL AND assessment_id=?)',(r['id'],r['assessment_id']))}
                if r['assessment_id']:
                    events|={v[0] for v in c.execute('SELECT i.kind FROM interactions i JOIN prospects p ON p.id=i.prospect_id JOIN research_assessments a ON a.prospect_id=p.id WHERE a.id=?',(r['assessment_id'],))}
                manual[first_strategy].setdefault(identity,set()).update(events)
            for g in groups.values():
                g['sources']=len({json.loads(r['details']).get('document',{}).get('url') for r in rows if r['strategy']==g['strategy'] and json.loads(r['details']).get('document',{}).get('url')})
            for row in c.execute("SELECT strategy,count(DISTINCT json_extract(payload,'$.url')) n FROM research_tasks WHERE campaign_id=? AND kind='source' AND state='done' GROUP BY strategy",(cid,)):
                groups.get(row['strategy'],groups['sources'])['sources']+=row['n']
            frontier={r[0]:r[1] for r in c.execute('SELECT state,count(*) FROM discovery_frontier WHERE campaign_id=? GROUP BY state',(cid,))}
            created=c.execute('SELECT created_at FROM campaigns WHERE id=?',(cid,)).fetchone()
        for key,g in groups.items():
            g['companies']=len(companies[key]);g['seconds']=round(g['seconds'],1)
            for events in manual[key].values():
                for kind in ('contacted','positive_reply','conversation','quote','won','no_reply'):g[kind]+=int(kind in events)
                g['replied']+=int(bool(events&{'replied','negative_reply','positive_reply','conversation','quote','won'}))
            g['sufficient']=g['contacted']>=max(10,self.store.settings()['minimum_sample'])
        return {'strategies':list(groups.values()),'frontier':frontier,'experiment_days':30,'ends_at':(datetime.fromisoformat(created[0])+timedelta(days=30)).isoformat() if created else None,'note':'Scoperti = pagine candidate; aziende = domini con identità verificata. Esiti commerciali registrati manualmente, attribuiti alla prima strategia osservata. Nessuna previsione di vendita.'}
