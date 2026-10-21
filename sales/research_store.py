"""Versioned research state. Commercial history stays in the existing CRM tables."""
import json
import secrets
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from .db import now, encode, digest, domain

ACTIVE=('running','waiting','stopping')
SERVICES={'website':'Sito aziendale completo','ecommerce':'E-commerce / migrazione','webapp':'Web app'}
SEEDS=[
 ('Veneto','https://www.confindustriavenest.it/stampa-e-media/comunicati-stampa'),
 ('Veneto','https://venetoup.com/'),
 ('Veneto','https://cnaveneto.it/startup/'),
 ('Veneto','https://venetosviluppo.it/index.php/news'),
 ('Lombardia','https://www.assolombarda.it/media/comunicati-stampa'),
 ('Piemonte','https://cms.ui.torino.it/'),
 ('Toscana','https://confindustriatoscanacentroecosta.it/notizie/press/'),
]

PUBLIC_FEEDS=[('Veneto','https://cnaveneto.it/feed/'),('Veneto','https://www.venetoeconomia.it/feed/'),('Veneto','https://www.confartigianatovicenza.it/feed/')]

def migrate(store):
    # executescript is not used: DDL and version marker commit together.
    statements=[
     'CREATE TABLE IF NOT EXISTS research_schema(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)',
     '''CREATE TABLE IF NOT EXISTS campaigns(id INTEGER PRIMARY KEY,status TEXT NOT NULL,target INTEGER NOT NULL,filters TEXT NOT NULL,generation TEXT NOT NULL,message TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,worker_pid INTEGER,next_retry TEXT,finished_at TEXT)''',
     "CREATE UNIQUE INDEX IF NOT EXISTS one_active_campaign ON campaigns((1)) WHERE status IN ('running','waiting','stopping')",
     '''CREATE TABLE IF NOT EXISTS research_tasks(id INTEGER PRIMARY KEY,campaign_id INTEGER NOT NULL REFERENCES campaigns(id),kind TEXT NOT NULL,strategy TEXT NOT NULL,payload TEXT NOT NULL,fingerprint TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,available_at TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,error TEXT,UNIQUE(campaign_id,fingerprint))''',
     'CREATE INDEX IF NOT EXISTS task_queue ON research_tasks(campaign_id,state,available_at,id)',
     '''CREATE TABLE IF NOT EXISTS research_entities(id INTEGER PRIMARY KEY,identity_key TEXT UNIQUE NOT NULL,name TEXT NOT NULL,website TEXT,legal_id TEXT,region TEXT,contact_group TEXT NOT NULL DEFAULT 'direct',identity_status TEXT NOT NULL DEFAULT 'unknown',details TEXT NOT NULL DEFAULT '{}',company_id INTEGER REFERENCES companies(id),created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''',
     'CREATE TABLE IF NOT EXISTS research_domains(domain TEXT PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES research_entities(id),basis TEXT NOT NULL)',
     '''CREATE TABLE IF NOT EXISTS research_documents(id TEXT PRIMARY KEY,url TEXT NOT NULL,content_hash TEXT NOT NULL,title TEXT NOT NULL,text TEXT NOT NULL,published_at TEXT,checked_at TEXT NOT NULL,provider TEXT NOT NULL,details TEXT NOT NULL)''',
     '''CREATE TABLE IF NOT EXISTS research_assessments(id INTEGER PRIMARY KEY,campaign_id INTEGER NOT NULL REFERENCES campaigns(id),entity_id INTEGER NOT NULL REFERENCES research_entities(id),task_id INTEGER REFERENCES research_tasks(id),status TEXT NOT NULL,score INTEGER NOT NULL,project TEXT,body TEXT NOT NULL,evidence_fingerprint TEXT NOT NULL,prospect_id INTEGER REFERENCES prospects(id),created_at TEXT NOT NULL,UNIQUE(campaign_id,entity_id,evidence_fingerprint))''',
     'CREATE INDEX IF NOT EXISTS assessments_entity ON research_assessments(entity_id,id)',
     '''CREATE TABLE IF NOT EXISTS research_signals(id INTEGER PRIMARY KEY,entity_id INTEGER NOT NULL REFERENCES research_entities(id),assessment_id INTEGER NOT NULL REFERENCES research_assessments(id),document_id TEXT NOT NULL REFERENCES research_documents(id),kind TEXT NOT NULL,quote TEXT NOT NULL,event_key TEXT NOT NULL,details TEXT NOT NULL)''',
     '''CREATE TABLE IF NOT EXISTS research_events(id INTEGER PRIMARY KEY,campaign_id INTEGER NOT NULL REFERENCES campaigns(id),kind TEXT NOT NULL,message TEXT NOT NULL,url TEXT,details TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL)''',
     '''CREATE TABLE IF NOT EXISTS research_reviews(id INTEGER PRIMARY KEY,assessment_id INTEGER NOT NULL REFERENCES research_assessments(id),verdict TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL)''',
     '''CREATE TABLE IF NOT EXISTS research_sources(url TEXT PRIMARY KEY,region TEXT,kind TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',reason TEXT NOT NULL DEFAULT 'Da verificare',last_success TEXT,checked_at TEXT,policy_url TEXT)''',
     '''CREATE TABLE IF NOT EXISTS research_query_memory(fingerprint TEXT PRIMARY KEY,query TEXT NOT NULL,last_checked TEXT NOT NULL,result_hash TEXT NOT NULL,new_urls INTEGER NOT NULL)''',
     '''CREATE TABLE IF NOT EXISTS research_visited(url TEXT PRIMARY KEY,first_seen TEXT NOT NULL,last_seen TEXT NOT NULL)''',
    ]
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        for sql in statements:c.execute(sql)
        for region,url in SEEDS:c.execute('INSERT OR IGNORE INTO research_sources(url,region,kind) VALUES (?,?,?)',(url,region,'html'))
        for region,url in PUBLIC_FEEDS:c.execute('INSERT OR IGNORE INTO research_sources(url,region,kind) VALUES (?,?,?)',(url,region,'rss'))
        c.execute('INSERT OR IGNORE INTO research_schema VALUES (4,?)',(now(),))
    from .research_funnel import migrate as migrate_funnel
    migrate_funnel(store)
    from .discovery_control import migrate as migrate_discovery
    migrate_discovery(store)
    from .grants import migrate as migrate_grants
    migrate_grants(store)
    from .commercial.storage import migrate as migrate_commercial
    migrate_commercial(store)

class ResearchStore:
    def __init__(self,store):self.store=store
    def event(self,cid,kind,message,url=None,details=None):
        with self.store.connect() as c:c.execute('INSERT INTO research_events(campaign_id,kind,message,url,details,created_at) VALUES (?,?,?,?,?,?)',(cid,kind,message[:1200],url,encode(details or {}),now()))
    def create(self,filters=None,target=50):
        filters=filters or {}
        if type(target)!=int or not 1<=target<=50:raise ValueError('Obiettivo compreso tra 1 e 50 aziende')
        if not isinstance(filters,dict) or set(filters)-{'projects','regions','groups','target','commercial_engines','work_budget','mode','commercial','max_job_age_days','deep_authorized','deep_plan_token','agent_version','agent_settings','runtime_version','decision_engine','social_urls','discovery_triage_version','continuation_version'}:raise ValueError('Filtri campagna non validi')
        if 'discovery_triage_version' in filters and (
                type(filters['discovery_triage_version']) is not int or filters['discovery_triage_version']!=1 or
                filters.get('decision_engine')!='ai_first_1' or filters.get('agent_version')!='6.0'):
            raise ValueError('Versione selezione fonti non valida')
        if 'continuation_version' in filters and (
                type(filters['continuation_version']) is not int or filters['continuation_version']!=1 or
                filters.get('decision_engine')!='ai_first_1' or filters.get('agent_version')!='6.0'):
            raise ValueError('Versione continuità ricerca non valida')
        if 'social_urls' in filters:
            from .agent6.social_seeds import validate_filters
            filters={**filters,'social_urls':validate_filters(filters)}
        if 'decision_engine' in filters and (filters['decision_engine']!='ai_first_1' or filters.get('agent_version')!='6.0'):
            raise ValueError('Motore decisionale non valido')
        if 'agent_version' in filters:
            if filters['agent_version']!='6.0' or not filters.get('commercial_engines'):raise ValueError('Versione agente non valida')
            from .agent6 import config,VERSION
            filters={**filters,'agent_settings':config(filters.get('agent_settings')),'runtime_version':VERSION}
        elif 'agent_settings' in filters or 'runtime_version' in filters:raise ValueError('Configurazione riservata all’agente commerciale')
        from .research_rules import ALLOWED_REGIONS
        if 'commercial_engines' in filters:
            from .commercial.catalog import options
            from .commercial.geography import REGIONS
            engines,budget=options(filters)
            if filters.get('mode')=='deep' and filters.get('deep_authorized') is not True:raise ValueError('Conferma esplicitamente i limiti del piano Deep prima di avviare.')
            from .commercial.ai_settings import campaign_config
            filters={**filters,'commercial':campaign_config(self.store,filters)}
            if filters.get('agent_version')=='6.0':
                from .agent6.api import validate_start
                validate_start(self.store,filters)
            if filters.get('mode')=='deep':
                from .commercial.search_intelligence import approval_token
                if filters.get('deep_plan_token')!=approval_token(filters,budget,filters['commercial']['ai']):raise ValueError('Piano Deep mancante o impostazioni cambiate: aggiorna l’anteprima e conferma i massimi.')
            filters={**filters,'commercial_engines':engines,'work_budget':budget,'regions':filters.get('regions') or list(REGIONS),'search_version':'5.0','demand_version':'5.1'}
            ALLOWED_REGIONS=REGIONS
        elif 'work_budget' in filters or 'commercial' in filters or 'max_job_age_days' in filters:raise ValueError('Impostazioni riservate ai motori commerciali')
        from .company_research import PROFILES
        if not isinstance(filters.get('target','all'),str) or filters.get('target','all') not in PROFILES:raise ValueError('Segmento aziendale non valido')
        filters={'target':'all',**filters}
        for key,allowed in [('projects',set(SERVICES)),('regions',set(ALLOWED_REGIONS)),('groups',{'agencies','direct'})]:
            if key in filters and (not isinstance(filters[key],list) or not filters[key] or any(not isinstance(x,str) or x not in allowed for x in filters[key])):raise ValueError('Filtro non valido: '+key)
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT 1 FROM campaigns WHERE status IN ('running','waiting','stopping')").fetchone():raise ValueError('Una ricerca è già in corso')
            ident=c.execute('INSERT INTO campaigns(status,target,filters,generation,message,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',('running',target,encode(filters),secrets.token_hex(12),'Preparazione della ricerca',now(),now())).lastrowid
        return self.campaign(ident)
    def include_all_segments(self,cid):
        """Explicit user scope change; preserve completed work and query memory."""
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT filters,status FROM campaigns WHERE id=?',(cid,)).fetchone()
            if not row:raise ValueError('Campagna non trovata')
            if row['status'] in ('running','waiting','stopping'):raise ValueError('Sospendere la ricerca prima di aggiornare i settori')
            filters={**json.loads(row['filters']),'target':'all'}
            c.execute('UPDATE campaigns SET filters=?,updated_at=? WHERE id=?',(encode(filters),now(),cid))
            for table in ('research_tasks','discovery_frontier'):
                for task in c.execute('SELECT id,payload FROM '+table+" WHERE campaign_id=? AND state IN ('pending','deferred','blocked','failed')",(cid,)).fetchall():
                    payload=json.loads(task['payload'])
                    payload['filters']={**payload.get('filters',filters),'target':'all'}
                    c.execute('UPDATE '+table+' SET payload=? WHERE id=?',(encode(payload),task['id']))
            c.execute("UPDATE discovery_branches SET state='active',last_query=NULL,reason=NULL WHERE campaign_id=? AND state='exhausted' AND strategy IN ('companies','partner','explicit')",(cid,))
        self.event(cid,'preferences','Ricerca estesa a produttori/B2B, negozi/marchi e servizi/professionisti; inclusi annunci freelance e pagine aziendali di lavoro.')
        return self.campaign(cid)
    def campaign(self,ident=None):
        with self.store.connect() as c:
            row=c.execute('SELECT * FROM campaigns WHERE id=?',(ident,)).fetchone() if ident is not None else c.execute("SELECT * FROM campaigns ORDER BY CASE WHEN status IN ('running','waiting','stopping') THEN 0 ELSE 1 END,updated_at DESC,id DESC LIMIT 1").fetchone()
            if not row:
                if ident is not None:raise ValueError('Campagna non trovata')
                return None
            data=dict(row);data['filters']=json.loads(data['filters']);cid=data['id']
            data['tasks']={r['state']:r['n'] for r in c.execute('SELECT state,count(*) n FROM research_tasks WHERE campaign_id=? GROUP BY state',(cid,))}
            work=c.execute("SELECT strategy,payload FROM research_tasks WHERE campaign_id=? AND state='working' ORDER BY id LIMIT 1",(cid,)).fetchone()
            data['active_research']={'strategy':work['strategy'],**{k:v for k,v in json.loads(work['payload']).items() if k in ('query','hypothesis','url')}} if work else None
            data['serper_requests']=c.execute("SELECT coalesce(sum(json_extract(details,'$.credits')),0) FROM discovery_operations WHERE campaign_id=? AND (provider='serper' OR EXISTS (SELECT 1 FROM json_each(discovery_operations.details,'$.engines') WHERE value='google via Serper'))",(cid,)).fetchone()[0]

            # One latest decision per entity, not one count per page or engine.
            rows=c.execute('''SELECT a.* FROM research_assessments a WHERE a.campaign_id=? AND a.id=(SELECT max(b.id) FROM research_assessments b WHERE b.campaign_id=a.campaign_id AND b.entity_id=a.entity_id)''',(cid,)).fetchall()
            counts={'examined':len(rows),'qualified':0,'rejected':0,'needs_review':0,'unverifiable':0}
            for r in rows:
                status=r['status']
                if status=='qualified' and c.execute('SELECT 1 FROM research_entities e LEFT JOIN companies co ON co.id=e.company_id WHERE e.id=? AND (co.do_not_contact=1 OR EXISTS (SELECT 1 FROM research_domains rd JOIN dismissed_companies dc ON rd.domain=dc.domain WHERE rd.entity_id=e.id))',(r['entity_id'],)).fetchone():status='rejected'
                counts[status]+=1
            data.update(counts)
            data['funnel']={r['state']:r['n'] for r in c.execute('SELECT state,count(*) n FROM discovery_candidates WHERE campaign_id=? GROUP BY state',(cid,))}
            from .research_funnel import candidate_selection
            source,args=candidate_selection({'campaign':cid,'company_only':1})
            data['company_funnel']={r[0]:r[1] for r in c.execute('SELECT state,count(*) FROM '+source+' GROUP BY state',args)}
            data['target_companies']=sum(data['company_funnel'].values())
            data['discovered']=sum(data['funnel'].values())
            data['promising']=data['company_funnel'].get('promising',0)
            data['verifying']=data['company_funnel'].get('verifying',0)
            data['events']=[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT * FROM research_events WHERE campaign_id=? ORDER BY id DESC LIMIT 30',(cid,))]
            data['sources']=[dict(r) for r in c.execute('SELECT * FROM research_sources')]
        data['running']=data['status'] in ('running','waiting','stopping')
        if data['filters'].get('commercial_engines'):
            from .commercial.coordinator import campaign_counts
            data.update(campaign_counts(self.store,cid))
        return data
    def active(self,cid,generation):
        with self.store.connect() as c:return bool(c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(cid,generation)).fetchone())
    def progress(self,cid,generation,message,status='running',next_retry=None):
        with self.store.connect() as c:c.execute("UPDATE campaigns SET message=?,status=?,next_retry=?,updated_at=? WHERE id=? AND generation=? AND status IN ('running','waiting')",(message,status,next_retry,now(),cid,generation))
    def finish(self,cid,generation,status,message):
        with self.store.connect() as c:c.execute("UPDATE campaigns SET status=?,message=?,updated_at=?,finished_at=? WHERE id=? AND generation=? AND status IN ('running','waiting')",(status,message,now(),now(),cid,generation))
    def stop(self,cid):
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM campaigns WHERE id=?',(cid,)).fetchone()
            if not row:raise ValueError('Campagna non trovata')
            if row['status'] in ('running','waiting','stopping'):
                c.execute("UPDATE campaigns SET status='stopping',generation=?,message='Arresto delle operazioni in corso',updated_at=? WHERE id=?",(secrets.token_hex(12),now(),cid))
        return self.campaign(cid)
    def paused(self,cid):
        with self.store.connect() as c:
            for row in c.execute("SELECT id,details,assessment_id FROM discovery_candidates WHERE campaign_id=? AND state='verifying'",(cid,)).fetchall():
                status='needs_review' if json.loads(row['details']).get('publisher') else 'promising'
                reason='Verifica sospesa; verrà ripresa dal lavoro salvato.'
                saved=c.execute('SELECT status FROM research_assessments WHERE id=?',(row['assessment_id'],)).fetchone() if row['assessment_id'] else None
                if saved:
                    status=saved['status'];reason='Nuova verifica sospesa; conservato l’ultimo esito salvato.'
                c.execute('UPDATE discovery_candidates SET state=?,reason=?,updated_at=? WHERE id=?',(status,reason,now(),row['id']))
                c.execute('INSERT INTO discovery_transitions(candidate_id,state,reason,created_at) VALUES (?,?,?,?)',(row['id'],status,reason,now()))
            c.execute("UPDATE research_tasks SET state='pending',updated_at=? WHERE campaign_id=? AND state='working'",(now(),cid))
            c.execute("UPDATE campaigns SET status='paused',message='Ricerca sospesa. Risultati conservati; puoi riprendere.',worker_pid=NULL,updated_at=? WHERE id=? AND status='stopping'",(now(),cid))
    def resume(self,cid):
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT status FROM campaigns WHERE id=?',(cid,)).fetchone()
            if not row or row['status'] not in ('paused','blocked','error'):raise ValueError('Questa campagna non è riprendibile')
            if c.execute("SELECT 1 FROM campaigns WHERE status IN ('running','waiting','stopping')").fetchone():raise ValueError('Una ricerca è già in corso')
            saved=json.loads(c.execute('SELECT filters FROM campaigns WHERE id=?',(cid,)).fetchone()[0])
            if saved.get('commercial_engines'):
                from .commercial.resources import availability
                from .commercial.catalog import options
                engines,limits=options(saved)
                info=availability(self.store,cid,limits,engines)
                if not info['resume_available']:raise ValueError(info['resume_reason'])
            c.execute("UPDATE campaigns SET status='running',generation=?,message='Ripresa della ricerca',updated_at=?,finished_at=NULL WHERE id=?",(secrets.token_hex(12),now(),cid))
            c.execute("UPDATE discovery_frontier SET state='pending' WHERE campaign_id=? AND state='blocked'",(cid,))
            attempts='attempts' if saved.get('agent_version')=='6.0' else '0'
            c.execute("UPDATE research_tasks SET state='pending',attempts="+attempts+",available_at=?,updated_at=? WHERE campaign_id=? AND state IN ('working','failed','blocked')",(now(),now(),cid))
        return self.campaign(cid)
    def enqueue(self,cid,kind,strategy,payload,key=None):
        fp=key or digest(encode([kind,strategy,payload]))
        with self.store.connect() as c:
            if not c.execute("SELECT 1 FROM campaigns WHERE id=? AND status IN ('running','waiting')",(cid,)).fetchone():return False
            changed=c.execute('INSERT OR IGNORE INTO research_tasks(campaign_id,kind,strategy,payload,fingerprint,available_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',(cid,kind,strategy,encode(payload),fp,now(),now(),now())).rowcount
        return bool(changed)
    def claim(self,cid,generation):
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            campaign=c.execute("SELECT filters FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(cid,generation)).fetchone()
            if not campaign:return None
            filters=json.loads(campaign['filters'])
            turns=c.execute('SELECT coalesce(sum(attempts),0) FROM research_tasks WHERE campaign_id=?',(cid,)).fetchone()[0]
            preferred=('candidate','search','candidate','source','verify','candidate')[turns%6]
            # Compare like work: reading a directory must not count as a paid
            # company search and starve that strategy behind explicit ads.
            row=c.execute("SELECT * FROM research_tasks WHERE campaign_id=? AND state='pending' AND available_at<=? ORDER BY CASE WHEN kind=? THEN 0 ELSE 1 END,CASE WHEN kind='verify' THEN -coalesce(json_extract(payload,'$.verification_priority'),0) ELSE 0 END,(SELECT count(*) FROM research_tasks done WHERE done.campaign_id=research_tasks.campaign_id AND done.strategy=research_tasks.strategy AND done.kind=research_tasks.kind AND (research_tasks.kind<>'candidate' OR coalesce(json_extract(done.payload,'$.publisher'),0)=coalesce(json_extract(research_tasks.payload,'$.publisher'),0)) AND done.state IN ('done','failed')),CASE WHEN kind='search' AND strategy='companies' THEN 0 ELSE 1 END,-coalesce(json_extract(payload,'$.discovery.priority'),0),id LIMIT 1",(cid,now(),preferred)).fetchone()
            if filters.get('agent_version')=='6.0':
                from .agent6.scheduling import choose
                tid,decision=choose(c,{'id':cid,'filters':filters},now())
                row=c.execute('SELECT * FROM research_tasks WHERE id=?',(tid,)).fetchone() if tid else None
                if decision:
                    c.execute('INSERT INTO research_events(campaign_id,kind,message,details,created_at) VALUES (?,?,?,?,?)',
                        (cid,'agent_schedule','Priorità: completare le prove e distribuire il lavoro tra i flussi.',encode(decision),now()))
            if not row:return None
            c.execute("UPDATE research_tasks SET state='working',attempts=attempts+1,updated_at=? WHERE id=?",(now(),row['id']))
        return {**dict(row),'attempts':row['attempts']+1,'payload':json.loads(row['payload'])}
    def task_done(self,tid,error=None,retry=False,retry_at=None):
        with self.store.connect() as c:
            row=c.execute('SELECT * FROM research_tasks WHERE id=?',(tid,)).fetchone()
            if not row:return
            retry=retry and row['attempts']<3
            later=(datetime.now(timezone.utc)+timedelta(seconds=30*2**row['attempts'])).isoformat() if retry else now()
            if retry and retry_at:later=max(later,retry_at)
            c.execute('UPDATE research_tasks SET state=?,available_at=?,error=?,updated_at=? WHERE id=?',('pending' if retry else 'failed' if error else 'done',later,error,now(),tid))
    def entity(self,identity):
        website=identity.get('website');host=domain(website or '')
        key='legal:'+identity['legal_id'] if identity.get('legal_id') and identity.get('identity_status')=='verified' else 'domain:'+host if host else 'unresolved:'+digest(identity.get('name','')+'|'+identity.get('source_url',''))
        with self.store.connect() as c:
            known=c.execute('SELECT entity_id FROM research_domains WHERE domain=?',(host,)).fetchone() if host else None
            if not known and identity.get('legal_id') and identity.get('identity_status')=='verified':known=c.execute("SELECT id FROM research_entities WHERE legal_id=? AND identity_status='verified' ORDER BY id LIMIT 1",(identity['legal_id'],)).fetchone()
            if not known and host:known=c.execute('SELECT id FROM research_entities WHERE identity_key=?',('domain:'+host,)).fetchone()
            if known:
                existing=c.execute('SELECT * FROM research_entities WHERE id=?',(known[0],)).fetchone()
                if identity.get('legal_id') and existing['legal_id'] and identity['legal_id']!=existing['legal_id']:raise ValueError('Identità societarie in conflitto sullo stesso dominio')
                key=existing['identity_key']
                if existing['identity_status']=='verified' and identity.get('identity_status')!='verified':identity=json.loads(existing['details']);website=identity.get('website')
            company=c.execute('SELECT id FROM companies WHERE domain=?',(host,)).fetchone() if host else None
            c.execute('''INSERT INTO research_entities(identity_key,name,website,legal_id,region,contact_group,identity_status,details,company_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(identity_key) DO UPDATE SET name=excluded.name,website=coalesce(excluded.website,research_entities.website),legal_id=coalesce(excluded.legal_id,research_entities.legal_id),region=coalesce(excluded.region,research_entities.region),identity_status=excluded.identity_status,details=excluded.details,updated_at=excluded.updated_at''',(key,identity.get('name') or host or 'Identità da verificare',website,identity.get('legal_id'),identity.get('region'),identity.get('group','direct'),identity.get('identity_status','unknown'),encode(identity),company[0] if company else None,now(),now()))
            ident=c.execute('SELECT id FROM research_entities WHERE identity_key=?',(key,)).fetchone()[0]
            if host and identity.get('identity_status')=='verified':c.execute('INSERT OR IGNORE INTO research_domains VALUES (?,?,?)',(host,ident,identity.get('basis','Fonte ufficiale')))
        return ident
    def suppressed(self,identity):
        urls=[identity.get('website') or '']
        if domain(urls[0]) and domain(urls[0])==domain(self.store.settings().get('portfolio','')):return 'È il tuo sito portfolio, non un potenziale cliente.'
        with self.store.connect() as c:
            if identity.get('legal_id'):
                urls += ['https://'+r[0]+'/' for r in c.execute('SELECT rd.domain FROM research_domains rd JOIN research_entities e ON e.id=rd.entity_id WHERE e.legal_id=?',(identity['legal_id'],))]
            for url in urls:
                if not url:continue
                if c.execute("SELECT 1 FROM commercial_outcomes o JOIN discovery_candidates d ON d.id=o.candidate_id WHERE o.kind='not_relevant' AND (d.domain=? OR d.url=?)",(domain(url),url)).fetchone():return 'Contatto escluso esplicitamente dall’utente.'
                excluded=self.store.target_exclusion(url)
                if excluded:return excluded['reason']
                row=c.execute('''SELECT c.* FROM companies c WHERE c.domain=?''',(domain(url),)).fetchone()
                if row and (row['do_not_contact'] or row['prior_contacted'] or c.execute("SELECT 1 FROM interactions i JOIN prospects p ON p.id=i.prospect_id WHERE p.company_id=? AND i.kind IN ('contacted','replied','proposal','won')",(row['id'],)).fetchone() or c.execute("SELECT 1 FROM prospects WHERE company_id=? AND stage IN ('contacted','replied','proposal','won','lost')",(row['id'],)).fetchone()):return 'Contatto già gestito o escluso: aggiornare lo storico, non proporre un nuovo contatto.'
        return None
    def save(self,cid,generation,tid,identity,documents,assessment):
        if not self.active(cid,generation):return None
        from .company_queue import evidence_key
        from .evaluation_policy import stamp
        policy=stamp(self.campaign(cid)['filters'])
        assessment={**assessment,'evaluation_policy':policy,'examined_documents':sorted({evidence_key(d) for d in documents})}
        eid=self.entity(identity)
        fp=digest(encode([policy,sorted((d['id'],d.get('content_hash','')) for d in documents),assessment.get('status'),assessment.get('validation'),assessment.get('missing')]))
        # A semantic fingerprint ignores changes to navigation, footers and fetching dates.
        meaningful=digest(encode(sorted((s['kind'],' '.join(s['quote'].lower().split())) for s in assessment.get('signals',[]))))
        with self.store.connect() as c:
            previous=c.execute('SELECT * FROM research_assessments WHERE entity_id=? ORDER BY id DESC LIMIT 1',(eid,)).fetchone()
            previous_body=json.loads(previous['body']) if previous else {}
            # Repaired access/coverage is allowed to complete an unfinished review
            # even when the original business facts have not changed. Technical
            # failures and open questions are not remembered as commercial refusals.
            final_states={'qualified','rejected'}
            repeat_final=bool(previous and previous['status'] in final_states
                              and previous_body.get('analysis_status')=='completed'
                              and assessment.get('status') in final_states
                              and assessment.get('analysis_status')=='completed')
            if repeat_final and previous_body.get('evaluation_policy')==policy and previous['campaign_id']!=cid and previous_body.get('signal_fingerprint')==meaningful:
                assessment={**assessment,'status':'rejected','reasons':['Già analizzata: nessun nuovo segnale significativo.'],'score':0,'campaign_only':True}
        assessment['signal_fingerprint']=meaningful
        assessment['original_status']=assessment['status']
        suppressed=self.suppressed(identity)
        if suppressed:assessment={**assessment,'status':'rejected','reasons':[suppressed],'score':0,'campaign_only':suppressed.startswith('Contatto già gestito')}
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            campaign=c.execute("SELECT * FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(cid,generation)).fetchone()
            if not campaign:return None
            # Recheck the user's exclusion inside the commit transaction.
            host=domain(identity.get('website') or '')
            blocked=c.execute('SELECT 1 FROM dismissed_companies WHERE domain=? OR domain IN (SELECT domain FROM research_domains WHERE entity_id=?)',(host,eid)).fetchone()
            if c.execute("SELECT 1 FROM commercial_outcomes o JOIN discovery_candidates d ON d.id=o.candidate_id WHERE o.kind='not_relevant' AND (d.domain=? OR d.url=?)",(host,identity.get('website'))).fetchone():blocked=True
            company=c.execute('SELECT * FROM companies WHERE domain=? OR id=(SELECT company_id FROM research_entities WHERE id=?)',(host,eid)).fetchone()
            if company and (company['do_not_contact'] or company['prior_contacted'] or c.execute("SELECT 1 FROM interactions i JOIN prospects p ON p.id=i.prospect_id WHERE p.company_id=? AND i.kind IN ('contacted','replied','proposal','won')",(company['id'],)).fetchone() or c.execute("SELECT 1 FROM prospects WHERE company_id=? AND stage IN ('contacted','replied','proposal','won','lost')",(company['id'],)).fetchone()):blocked=True
            if blocked:assessment={**assessment,'status':'rejected','reasons':['Proposta eliminata manualmente'],'score':0}
            assessment['original_status']=assessment['status']
            for d in documents:c.execute('INSERT OR IGNORE INTO research_documents VALUES (?,?,?,?,?,?,?,?,?)',(d['id'],d['url'],d['content_hash'],d.get('title',''),d['text'],d.get('published_at'),d['checked_at'],d.get('provider','Pagina pubblica'),encode({k:v for k,v in d.items() if k!='text'})))
            c.execute('INSERT OR IGNORE INTO research_assessments(campaign_id,entity_id,task_id,status,score,project,body,evidence_fingerprint,created_at) VALUES (?,?,?,?,?,?,?,?,?)',(cid,eid,tid,assessment['status'],assessment['score'],assessment.get('project'),encode(assessment),fp,now()))
            row=c.execute('SELECT * FROM research_assessments WHERE campaign_id=? AND entity_id=? AND evidence_fingerprint=?',(cid,eid,fp)).fetchone();aid=row['id']
            for s in assessment.get('signals',[]):
                if not c.execute('SELECT 1 FROM research_signals WHERE assessment_id=? AND document_id=? AND quote=?',(aid,s['document_id'],s['quote'])).fetchone():c.execute('INSERT INTO research_signals(entity_id,assessment_id,document_id,kind,quote,event_key,details) VALUES (?,?,?,?,?,?,?)',(eid,aid,s['document_id'],s['kind'],s['quote'],s['event_key'],encode(s)))
            if row['status']=='qualified' and not row['prospect_id'] and host:
                # Bridge to CRM atomically: no qualified result can be lost between tables.
                company_id=c.execute('SELECT company_id FROM research_entities WHERE id=?',(eid,)).fetchone()[0]
                if not company_id:
                    c.execute('INSERT OR IGNORE INTO companies(domain,name,website,sector,location,contacts,created_at) VALUES (?,?,?,?,?,?,?)',(host,identity['name'],identity['website'],identity.get('sector'),identity.get('region'),encode(identity.get('contacts',[])),now()))
                    company_id=c.execute('SELECT id FROM companies WHERE domain=?',(host,)).fetchone()[0]
                c.execute('UPDATE research_entities SET company_id=? WHERE id=?',(company_id,eid))
                saved_contacts=json.loads(c.execute('SELECT contacts FROM companies WHERE id=?',(company_id,)).fetchone()[0])
                merged={(v['type'],v['value']):v for v in saved_contacts+identity.get('contacts',[])}
                c.execute('UPDATE companies SET contacts=? WHERE id=?',(encode(list(merged.values())),company_id))
                key='v4:'+str(eid)
                c.execute('''INSERT INTO prospects(company_id,engine,title,service,score,score_detail,reason,hypothesis,missing,identity,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET score=excluded.score,score_detail=excluded.score_detail,reason=excluded.reason,hypothesis=excluded.hypothesis,missing=excluded.missing,updated_at=excluded.updated_at''',(company_id,'E',assessment.get('why','Opportunità verificata'),SERVICES.get(assessment.get('project'),'Progetto digitale'),assessment['score'],encode({k:v['points'] for k,v in assessment['score_detail'].items()}),assessment.get('why',''),assessment.get('proposal',''),encode(assessment.get('missing',[])),key,now(),now()))
                pid=c.execute('SELECT id FROM prospects WHERE identity=?',(key,)).fetchone()[0]
                c.execute('UPDATE research_assessments SET prospect_id=? WHERE id=?',(pid,aid))
                bydoc={d['id']:d for d in documents}
                for signal in assessment.get('signals',[]):
                    d=bydoc[signal['document_id']]
                    c.execute('INSERT OR IGNORE INTO sources(url,title,provider,source_type,published_at,checked_at,content_hash,excerpt,company_id) VALUES (?,?,?,?,?,?,?,?,?)',(d['url'],d.get('title',''),d.get('provider','Verifica 4.0'),'Pagina originale',d.get('published_at'),d['checked_at'],d['content_hash'],d['text'][:6000],company_id))
                    sid=c.execute('SELECT id FROM sources WHERE url=?',(d['url'],)).fetchone()[0]
                    kind='request' if signal['kind']=='request' else 'signal' if signal['kind']=='event' else 'fact'
                    efp=digest('v4:'+str(eid)+signal['id'])
                    c.execute('INSERT OR IGNORE INTO evidence(company_id,source_id,engine,kind,label,detail,confidence,published_at,checked_at,metadata,fingerprint) VALUES (?,?,?,?,?,?,?,?,?,?,?)',(company_id,sid,'E',kind,'Riscontro verificato 4.0',signal['quote'],'direct',d.get('published_at'),d['checked_at'],encode({'research_signal_id':signal['id'],'kind':signal['kind']}),efp))
                    evid=c.execute('SELECT id FROM evidence WHERE fingerprint=?',(efp,)).fetchone()[0]
                    c.execute('INSERT OR IGNORE INTO prospect_evidence VALUES (?,?)',(pid,evid))
                c.execute('INSERT OR IGNORE INTO contact_groups VALUES (?,?,?,?,0)',(company_id,identity.get('group','direct'),'Categoria verificata durante la ricerca 4.0',identity['website']))
        self.event(cid,'decision','; '.join(assessment.get('reasons',[])) or assessment.get('why','Valutazione salvata'),identity.get('website'),{'assessment_id':aid,'status':assessment['status'],'strategy':assessment.get('strategy')})
        return aid
    def opportunities(self,filters=None,offset=0,limit=50):
        filters=filters or {};scope=' AND b.campaign_id=a.campaign_id' if filters.get('campaign') else " AND coalesce(json_extract(b.body,'$.campaign_only'),0)=0" if filters.get('status')=='qualified' else ''
        clauses=['a.id=(SELECT max(b.id) FROM research_assessments b WHERE b.entity_id=a.entity_id'+scope+')'];args=[]
        for field,col in [('status','a.status'),('project','a.project'),('region','e.region'),('campaign','a.campaign_id')]:
            if filters.get(field):clauses.append(col+'=?');args.append(filters[field])
        if filters.get('search'):clauses.append('(e.name LIKE ? OR e.website LIKE ?)');args.extend(['%'+str(filters['search'])[:200]+'%']*2)
        # User edits to client category remain authoritative.
        if filters.get('stage'):
            clauses.append('EXISTS (SELECT 1 FROM prospects p WHERE p.company_id=e.company_id AND p.stage=?)');args.append(filters['stage'])
        if filters.get('status')=='qualified':
            clauses.append("NOT EXISTS (SELECT 1 FROM dismissed_companies d JOIN research_domains rd ON rd.domain=d.domain WHERE rd.entity_id=e.id)")
            clauses.append('NOT EXISTS (SELECT 1 FROM companies c WHERE c.id=e.company_id AND c.do_not_contact=1)')
        sql=' FROM research_assessments a JOIN research_entities e ON e.id=a.entity_id WHERE '+' AND '.join(clauses)
        with self.store.connect() as c:
            c.execute('BEGIN')
            group_expr="coalesce((SELECT category FROM contact_groups cg WHERE cg.company_id=e.company_id),e.contact_group)"
            group_counts={r[0]:r[1] for r in c.execute('SELECT '+group_expr+',count(*)'+sql+' GROUP BY '+group_expr,args)}
            if filters.get('group'):sql+=' AND '+group_expr+'=?';args.append(filters['group'])
            total=c.execute('SELECT count(*)'+sql,args).fetchone()[0]
            rows=c.execute('SELECT a.*,e.name,e.website,e.region,e.company_id,coalesce((SELECT category FROM contact_groups cg WHERE cg.company_id=e.company_id),e.contact_group) contact_group,e.identity_status,e.details'+sql+' ORDER BY a.score DESC,a.id DESC LIMIT ? OFFSET ?',(*args,max(1,min(100,limit)),max(0,offset))).fetchall()
        return {'items':[self.unpack(r) for r in rows],'total':total,'offset':offset,'limit':limit,'group_counts':group_counts}
    @staticmethod
    def unpack(row):
        value=dict(row);value['assessment']=json.loads(value['body'])
        if 'details' in value:value['identity']=json.loads(value.pop('details'))
        return value
    def opportunity(self,ident):
        with self.store.connect() as c:
            row=c.execute('SELECT a.*,e.name,e.website,e.region,e.company_id,coalesce((SELECT category FROM contact_groups cg WHERE cg.company_id=e.company_id),e.contact_group) contact_group,e.identity_status,e.details FROM research_assessments a JOIN research_entities e ON e.id=a.entity_id WHERE a.id=?',(ident,)).fetchone()
            if not row:raise ValueError('Valutazione non trovata')
            item=self.unpack(row)
            ids={s['document_id'] for s in item['assessment'].get('signals',[])}|set(item['assessment'].get('document_ids',[]))
            item['documents']=[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT * FROM research_documents WHERE id IN ('+','.join('?' for _ in ids)+')',tuple(ids))] if ids else []
            item['reviews']=[dict(r) for r in c.execute('SELECT * FROM research_reviews WHERE assessment_id=? ORDER BY id DESC',(ident,))]
        return item
    def review(self,ident,verdict,reason):
        self.opportunity(ident)
        if verdict not in ('confirmed','false_positive','missed_opportunity') or not isinstance(reason,str) or not 5<=len(reason)<=3000:raise ValueError('Indica un esito e una motivazione di almeno 5 caratteri')
        with self.store.connect() as c:
            c.execute('INSERT INTO research_reviews(assessment_id,verdict,reason,created_at) VALUES (?,?,?,?)',(ident,verdict,reason,now()))
            if verdict=='false_positive':
                r=c.execute('SELECT body FROM research_assessments WHERE id=?',(ident,)).fetchone();body=json.loads(r[0]);body.setdefault('original_status',body['status']);body['status']='rejected';body['reasons']=['Revisione: '+reason]
                c.execute("UPDATE research_assessments SET status='rejected',body=? WHERE id=?",(encode(body),ident))
        return self.opportunity(ident)

def reconcile_entities(store):
    """Repair provisional-to-verified aliases, preserving every assessment and CRM record."""
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE');groups={};merged=0
        for row in c.execute("SELECT * FROM research_entities WHERE identity_status!='merged' ORDER BY id"):
            host=domain(row['website'] or '')
            if host:groups.setdefault(host,[]).append(dict(row))
        for host,rows in groups.items():
            if len(rows)<2:continue
            legal={r['legal_id'] for r in rows if r['legal_id'] and r['identity_status']=='verified'}
            if len(legal)>1:continue  # Conflicting ownership is not silently reconciled.
            canonical=min(rows,key=lambda r:(r['identity_status']!='verified',r['id']))
            for old in rows:
                if old['id']==canonical['id']:continue
                assessments=c.execute('SELECT id,campaign_id,evidence_fingerprint FROM research_assessments WHERE entity_id=?',(old['id'],)).fetchall()
                for a in assessments:
                    fp=a['evidence_fingerprint']
                    if c.execute('SELECT 1 FROM research_assessments WHERE campaign_id=? AND entity_id=? AND evidence_fingerprint=?',(a['campaign_id'],canonical['id'],fp)).fetchone():fp=digest(fp+'|retained-assessment:'+str(a['id']))
                    c.execute('UPDATE research_assessments SET entity_id=?,evidence_fingerprint=? WHERE id=?',(canonical['id'],fp,a['id']))
                c.execute('UPDATE research_signals SET entity_id=? WHERE entity_id=?',(canonical['id'],old['id']))
                c.execute('UPDATE research_domains SET entity_id=? WHERE entity_id=?',(canonical['id'],old['id']))
                details=json.loads(old['details']);details['merged_into']=canonical['id']
                c.execute("UPDATE research_entities SET identity_key=?,identity_status='merged',details=? WHERE id=?",('merged:'+str(old['id']),encode(details),old['id']))
                merged+=1
            if canonical['identity_status']=='verified':c.execute('INSERT OR REPLACE INTO research_domains VALUES (?,?,?)',(host,canonical['id'],'Identità ufficiale verificata; record provvisori riuniti senza cancellare le valutazioni.'))
    return merged
