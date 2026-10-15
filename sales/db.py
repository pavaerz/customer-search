import hashlib
import json
import math
import os
import sqlite3
from contextlib import contextmanager,closing
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from .config import DATA, DEFAULTS, ENGINES, STAGES
from .selection import digital_project, commercially_qualified, GROWTH_REJECTION


def now(): return datetime.now(timezone.utc).isoformat()
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def domain(url): return (urlsplit(url).hostname or '').lower().removeprefix('www.')
def encode(value): return json.dumps(value,ensure_ascii=False)

class Store:
    def __init__(self,path=None): self.path=path or DATA/'sales.sqlite3'
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.path,timeout=20); c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            with c: yield c
        finally: c.close()
    def init(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS dismissed_companies(domain TEXT PRIMARY KEY,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS target_exclusions(domain TEXT PRIMARY KEY,reason TEXT NOT NULL,url TEXT NOT NULL,checked_at TEXT NOT NULL,code TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY,domain TEXT UNIQUE NOT NULL,name TEXT NOT NULL,website TEXT NOT NULL,sector TEXT,location TEXT,contacts TEXT NOT NULL DEFAULT '[]',prior_contacted INTEGER NOT NULL DEFAULT 0,do_not_contact INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS contact_groups(company_id INTEGER PRIMARY KEY REFERENCES companies(id),category TEXT NOT NULL,basis TEXT NOT NULL,url TEXT NOT NULL,manual INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY,url TEXT UNIQUE NOT NULL,title TEXT NOT NULL,provider TEXT NOT NULL,source_type TEXT NOT NULL,published_at TEXT,checked_at TEXT NOT NULL,content_hash TEXT,excerpt TEXT NOT NULL,company_id INTEGER REFERENCES companies(id));
            CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL REFERENCES companies(id),source_id INTEGER NOT NULL REFERENCES sources(id),engine TEXT NOT NULL,kind TEXT NOT NULL,label TEXT NOT NULL,detail TEXT NOT NULL,confidence TEXT NOT NULL,published_at TEXT,checked_at TEXT NOT NULL,metadata TEXT NOT NULL DEFAULT '{}',fingerprint TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS prospects(id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL REFERENCES companies(id),engine TEXT NOT NULL,title TEXT NOT NULL,service TEXT NOT NULL,score INTEGER NOT NULL,score_detail TEXT NOT NULL,reason TEXT NOT NULL,hypothesis TEXT NOT NULL,missing TEXT NOT NULL,stage TEXT NOT NULL DEFAULT 'review',notes TEXT NOT NULL DEFAULT '',contract_value REAL,paid_value REAL NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,identity TEXT UNIQUE NOT NULL,contact_basis TEXT NOT NULL DEFAULT '',draft TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS prospect_evidence(prospect_id INTEGER NOT NULL REFERENCES prospects(id),evidence_id INTEGER NOT NULL REFERENCES evidence(id),PRIMARY KEY(prospect_id,evidence_id));
            CREATE TABLE IF NOT EXISTS interactions(id INTEGER PRIMARY KEY,prospect_id INTEGER NOT NULL REFERENCES prospects(id),kind TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,engine TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT,status TEXT NOT NULL,stats TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS run_items(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL REFERENCES runs(id),url TEXT,query TEXT,disposition TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS api_usage(day TEXT NOT NULL,provider TEXT NOT NULL,units INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(day,provider));
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,body TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS legacy_records(kind TEXT NOT NULL,old_id INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(kind,old_id));
            CREATE TABLE IF NOT EXISTS audits(company_id INTEGER PRIMARY KEY REFERENCES companies(id),payload TEXT NOT NULL,checked_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS evidence_company ON evidence(company_id);
            ''')
            c.execute("INSERT OR IGNORE INTO config VALUES (?,?)",('provider',encode(DEFAULTS['provider'])))
            c.execute("UPDATE runs SET status='interrupted',finished_at=? WHERE status='running'",(now(),))
        from .research_store import migrate,reconcile_entities
        migrate(self);reconcile_entities(self)
        os.chmod(self.path,0o600)
    def settings(self):
        with self.connect() as c: values={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM config')}
        if values.get('provider') not in ('searxng','serper'):values['provider']='searxng'
        return {**DEFAULTS,**values}
    def configure(self,values):
        limits={'queries_per_engine':(1,10),'results_per_query':(1,20),'daily_api_limit':(0,100000),'monthly_api_limit':(0,1000000),'cache_hours':(1,168),'minimum_sample':(5,100),'minimum_budget':(0,100000),'technical_limit':(1,10),'min_priority':(0,100)}
        for key,val in values.items():
            if key not in DEFAULTS: raise ValueError('Impostazione non riconosciuta')
            if key in ('daily_api_limit','monthly_api_limit') and val is None:continue
            if key in limits and (type(val)!=int or not limits[key][0]<=val<=limits[key][1]): raise ValueError('Valore non valido: '+key)
            if key in ('preferred_locations','excluded_locations') and (not isinstance(val,list) or len(val)>50 or any(not isinstance(v,str) or not 2<=len(v)<=80 for v in val)):raise ValueError('Località non valide')
            if key=='provider' and val not in ('searxng','serper'): raise ValueError('Motore di ricerca non supportato.')
            if key=='time_range' and val not in ('','month','week','year'): raise ValueError('Periodo non valido')
            if key=='queries' and (not isinstance(val,dict) or set(val)!=set(DEFAULTS['queries']) or any(not isinstance(v,list) or not 1<=len(v)<=30 or any(not isinstance(q,str) or not 5<=len(q)<=350 for q in v) for v in val.values())): raise ValueError('Query non valide')
            if key=='rss_feeds' and (not isinstance(val,list) or len(val)>15 or any(not isinstance(v,str) or urlsplit(v).scheme!='https' for v in val)): raise ValueError('Inserisci URL HTTPS di feed autorizzati')
            if key in ('name','location','portfolio','ollama_model') and (not isinstance(val,str) or len(val)>300): raise ValueError('Testo non valido')
            if key=='ollama_model' and (':cloud' in val or '/' in val or '://' in val):raise ValueError('Usa un modello installato localmente, senza servizi cloud')
            if key=='portfolio' and (urlsplit(val).scheme!='https' or not urlsplit(val).hostname): raise ValueError('Portfolio HTTPS richiesto')
        with self.connect() as c:
            for k,v in values.items(): c.execute('INSERT OR REPLACE INTO config VALUES (?,?)',(k,encode(v)))
    def migrate_legacy(self,path):
        # An explicit workspace reset must not silently import the old results again.
        with self.connect() as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspace_resets'").fetchone() and c.execute('SELECT 1 FROM workspace_resets').fetchone():return
        if not path.exists(): return
        with closing(sqlite3.connect(f'file:{path}?mode=ro',uri=True)) as old,self.connect() as c:
            old.row_factory=sqlite3.Row
            for table in ('leads','opportunities'):
                if not old.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',(table,)).fetchone(): continue
                for row in old.execute('SELECT * FROM '+table):
                    c.execute('INSERT OR IGNORE INTO legacy_records VALUES (?,?,?)',(table,row['id'],encode(dict(row))))
            # Keep previous API consumption; creating a new database cannot reset budgets.
            if old.execute("SELECT 1 FROM sqlite_master WHERE name='search_usage'").fetchone():
                for r in old.execute('SELECT * FROM search_usage'):
                    c.execute("INSERT INTO api_usage VALUES (?,'tavily',?) ON CONFLICT(day,provider) DO UPDATE SET units=max(units,excluded.units)",(r['day'],r['requests']))
    def legacy(self):
        with self.connect() as c: return [{'kind':r['kind'],'id':r['old_id'],'data':json.loads(r['payload'])} for r in c.execute('SELECT * FROM legacy_records ORDER BY old_id DESC')]
    def target_exclusion(self,url):
        with self.connect() as c:
            dismissed=c.execute('SELECT * FROM dismissed_companies WHERE domain=?',(domain(url),)).fetchone()
            if dismissed:
                return {'domain':domain(url),'reason':'Proposta eliminata manualmente: non riproporre questa azienda.','url':url,'checked_at':dismissed['created_at'],'code':'user_dismissed'}
            row=c.execute('SELECT * FROM target_exclusions WHERE domain=?',(domain(url),)).fetchone()
        return dict(row) if row else None
    def exclude_target(self,url,finding):
        host=domain(url)
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO target_exclusions VALUES (?,?,?,?,?)',(host,finding['reason'],finding['url'],finding['checked_at'],finding['code']))
            rows=c.execute("SELECT p.id,p.notes FROM prospects p JOIN companies c ON c.id=p.company_id WHERE c.domain=? AND p.stage IN ('review','ready')",(host,)).fetchall()
            for row in rows:
                note=finding['reason']+' · Fonte: '+finding['url']
                c.execute("UPDATE prospects SET stage='discarded',notes=?,updated_at=? WHERE id=?",((row['notes']+'\n'+note).strip(),now(),row['id']))
                c.execute('INSERT INTO interactions(prospect_id,kind,detail,created_at) VALUES (?,?,?,?)',(row['id'],'discarded',note,now()))

    def company(self,url,name=None,sector=None,location=None,contacts=None):
        host=domain(url)
        if not host: raise ValueError('Azienda senza dominio')
        with self.connect() as c:
            prior=blocked=False
            for r in c.execute("SELECT payload FROM legacy_records WHERE kind='leads'"):
                old=json.loads(r['payload'])
                if (old.get('domain','').removeprefix('www.')==host or domain(old.get('url',''))==host):
                    prior |= bool(old.get('sent_at') or old.get('status') in ('sent','sending','uncertain','gmail_pending'))
                    blocked |= old.get('outcome')=='do_not_contact'
            c.execute('INSERT OR IGNORE INTO companies(domain,name,website,created_at,prior_contacted,do_not_contact) VALUES (?,?,?,?,?,?)',(host,name or host,url,now(),int(prior),int(blocked)))
            row=c.execute('SELECT * FROM companies WHERE domain=?',(host,)).fetchone()
            known=json.loads(row['contacts']); merged={x['value']:x for x in known}
            for contact in contacts or []: merged[contact['value']]=contact
            c.execute('UPDATE companies SET name=?,sector=coalesce(?,sector),location=coalesce(?,location),contacts=? WHERE id=?',(name or row['name'],sector,location,encode(list(merged.values())),row['id']))
            return row['id']
    def classify_contact(self,cid,category,basis,url='',manual=False):
        if category not in ('agencies','direct'):raise ValueError('Categoria contatto non valida')
        with self.connect() as c:
            c.execute('INSERT INTO contact_groups VALUES (?,?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET category=excluded.category,basis=excluded.basis,url=excluded.url,manual=excluded.manual WHERE contact_groups.manual=0 OR excluded.manual=1',(cid,category,basis,url,int(manual)))
    def source(self,record,company_id=None):
        with self.connect() as c:
            c.execute('''INSERT INTO sources(url,title,provider,source_type,published_at,checked_at,content_hash,excerpt,company_id) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET title=excluded.title,checked_at=excluded.checked_at,content_hash=excluded.content_hash,excerpt=excluded.excerpt,published_at=excluded.published_at,company_id=coalesce(excluded.company_id,sources.company_id)''',(record['url'],record.get('title',''),record.get('provider','Pagina pubblica'),record.get('source_type','Sito aziendale'),record.get('published_at'),record.get('checked_at',now()),record.get('content_hash'),record.get('excerpt','')[:6000],company_id))
            return c.execute('SELECT id FROM sources WHERE url=?',(record['url'],)).fetchone()[0]
    def add_evidence(self,cid,sid,engine,kind,label,detail,published=None,confidence='direct',metadata=None):
        fp=digest(f'{cid}|{sid}|{engine}|{kind}|{label}')
        with self.connect() as c:
            c.execute('''INSERT INTO evidence(company_id,source_id,engine,kind,label,detail,confidence,published_at,checked_at,metadata,fingerprint) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(fingerprint) DO UPDATE SET detail=excluded.detail,checked_at=excluded.checked_at,published_at=excluded.published_at,metadata=excluded.metadata''',(cid,sid,engine,kind,label,detail[:6000],confidence,published,c.execute('SELECT checked_at FROM sources WHERE id=?',(sid,)).fetchone()[0],encode(metadata or {}),fp))
            return c.execute('SELECT id FROM evidence WHERE fingerprint=?',(fp,)).fetchone()[0]
    def evidences(self,cid):
        with self.connect() as c:
            rows=c.execute('''SELECT e.*,s.url,s.title AS source_title,s.provider,s.source_type FROM evidence e JOIN sources s ON s.id=e.source_id WHERE e.company_id=? ORDER BY e.id DESC''',(cid,)).fetchall()
        return [{**dict(r),'metadata':json.loads(r['metadata'])} for r in rows]
    def prospect(self,cid,engine,title,service,score,breakdown,reason,hypothesis,missing,evidence_ids,identity=None):
        with self.connect() as c:
            company=c.execute('SELECT website FROM companies WHERE id=?',(cid,)).fetchone()
        excluded=self.target_exclusion(company['website'])
        if excluded:raise ValueError(excluded['reason'])
        key=identity or f'{cid}:{engine}'
        stamp=now()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM dismissed_companies WHERE domain=?',(domain(company['website']),)).fetchone():
                raise ValueError('Proposta eliminata manualmente: non riproporre questa azienda.')
            prior=c.execute('SELECT id FROM prospects WHERE identity=?',(key,)).fetchone()
            c.execute('''INSERT INTO prospects(company_id,engine,title,service,score,score_detail,reason,hypothesis,missing,created_at,updated_at,identity) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET title=excluded.title,service=excluded.service,score=excluded.score,score_detail=excluded.score_detail,reason=excluded.reason,hypothesis=excluded.hypothesis,missing=excluded.missing,updated_at=excluded.updated_at''',(cid,engine,title,service,score,encode(breakdown),reason,hypothesis,encode(missing),stamp,stamp,key))
            ident=c.execute('SELECT id FROM prospects WHERE identity=?',(key,)).fetchone()[0]
            for eid in evidence_ids: c.execute('INSERT OR IGNORE INTO prospect_evidence VALUES (?,?)',(ident,eid))
            return ident,prior is None
    def list(self):
        with self.connect() as c:
            rows=[dict(r) for r in c.execute('''SELECT p.*,c.name,c.domain,c.website,c.sector,c.location,c.contacts,c.prior_contacted,c.do_not_contact,
                (SELECT MIN(i.created_at) FROM interactions i JOIN prospects contacted ON contacted.id=i.prospect_id
                 WHERE contacted.company_id=c.id AND i.kind='contacted') AS contacted_at
                FROM prospects p JOIN companies c ON c.id=p.company_id ORDER BY p.score DESC,p.updated_at DESC''')]
        for row in rows:
            for k in ('contacts','score_detail','missing','draft'): row[k]=json.loads(row[k])
            with self.connect() as c:
                ids={r[0] for r in c.execute('SELECT evidence_id FROM prospect_evidence WHERE prospect_id=?',(row['id'],))}
            row['evidence']=[e for e in self.evidences(row['company_id']) if e['id'] in ids]
            dates=[e['published_at'] for e in row['evidence'] if e['published_at']]
            row['latest_date']=max(dates) if dates else None
            row['source_count']=len({e['url'] for e in row['evidence']})
            row['source_domains']=len({domain(e['url']) for e in row['evidence']})
            row['matched_engines']=sorted({row['engine']}|({e['engine'] for e in row['evidence']} if row['engine'] in ('A','B') else set()))
            row['explicit']=any(e['kind']=='request' for e in row['evidence'])
            row['qualification_rejected']=False if row['identity'].startswith('v4:') else not commercially_qualified(row['engine'],row['evidence'])
            row['incomplete']=any(e['kind']=='limitation' for e in row['evidence'])
            row['target_exclusion']=self.target_exclusion(row['website'])
            row['dismissed_at']=row['target_exclusion']['checked_at'] if row['target_exclusion'] and row['target_exclusion']['code']=='user_dismissed' else None
            row['priority_cap']=None
            if not row['identity'].startswith('v4:') and not dates and row['engine'] in ('A','B','C','E'):
                row['score']=min(row['score'],49); row['priority_cap']='Data del segnale non disponibile'
            elif dates:
                try:
                    age=(datetime.now(timezone.utc).date()-datetime.fromisoformat(max(dates)[:10]).date()).days
                    if age>90: row['score']=min(row['score'],35);row['priority_cap']='Segnale più vecchio di 90 giorni'
                except ValueError: pass
        return sorted(rows,key=lambda r:(-r['score'],r['id']))
    def company_list(self):
        """One stable company card; keep original opportunities and provenance intact."""
        groups={}
        with self.connect() as c:
            categories={r['company_id']:dict(r) for r in c.execute('SELECT * FROM contact_groups')}
            placeholders=','.join('?' for _ in STAGES)
            workflow={r[0]:r[1] for r in c.execute(f'SELECT prospect_id,MAX(created_at) FROM interactions WHERE kind IN ({placeholders}) GROUP BY prospect_id',tuple(STAGES))}
        for row in self.list():groups.setdefault(row['company_id'],[]).append(row)
        result=[]
        for rows in groups.values():
            eligible=[r for r in rows if not r['qualification_rejected']]
            members=eligible or rows
            primary=max(members,key=lambda r:(workflow.get(r['id'],''),-r['id']))
            # The latest manually managed record owns workflow; otherwise use the earliest.
            # Research can add evidence without resetting this workflow or changing its id.
            ranked=sorted(members,key=lambda r:(r['explicit'],r['score']),reverse=True)
            best=ranked[0]
            item={**primary}
            for key in ('title','service','score','score_detail','reason','hypothesis','priority_cap'):
                item[key]=best[key]
            item['member_ids']=[r['id'] for r in members]
            item['all_member_ids']=[r['id'] for r in rows]
            item['recorded_revenue']=sum(r['paid_value'] or 0 for r in rows)
            item['recorded_contracts']=sum(r['contract_value'] or 0 for r in rows if r['stage']=='won')
            if not eligible:
                item['score']=0;item['reason']=GROWTH_REJECTION;item['hypothesis']='Nessuna esigenza web attuale dimostrata dalle fonti conservate.'
            item['evidence']=list({e['id']:e for r in members for e in r['evidence']}.values())
            item['matched_engines']=sorted({k for r in members for k in r['matched_engines']})
            item['source_count']=len({e['url'] for e in item['evidence']})
            item['explicit']=any(r['explicit'] for r in members)
            dates=[e['published_at'] for e in item['evidence'] if e['published_at'] and e['kind'] in ('request','signal')]
            item['latest_date']=max(dates) if dates else None
            item['missing']=list(dict.fromkeys(v for r in members for v in r['missing']))
            category=categories.get(item['company_id'])
            if not category:
                agency='B' in item['matched_engines'] or item.get('sector')=='Agenzia / servizi digitali'
                category={'category':'agencies' if agency else 'direct','basis':'Categoria suggerita dai riscontri raccolti; puoi correggerla in Stato e note.','url':'','manual':0}
            item['contact_group']=category['category']
            item['contact_group_basis']=category['basis']
            item['contact_group_url']=category['url']
            item['contact_group_manual']=bool(category['manual'])
            result.append(item)
        return sorted(result,key=lambda r:(-r['score'],r['id']))
    def company_detail(self,ident):
        item=next((r for r in self.company_list() if ident in r['all_member_ids']),None)
        if not item:raise ValueError('Azienda non trovata')
        original=self.detail(item['id'])
        item['audit']=original['audit']
        with self.connect() as c:
            item['interactions']=[dict(r) for r in c.execute('SELECT i.* FROM interactions i JOIN prospects p ON p.id=i.prospect_id WHERE p.company_id=? ORDER BY i.id DESC',(item['company_id'],))]
            item['previous_records']=[dict(r) for r in c.execute('SELECT id,engine,stage,notes,contract_value,paid_value,draft FROM prospects WHERE company_id=? AND id!=? ORDER BY id',(item['company_id'],item['id']))]
        return item
    def set_dismissed(self,ident,dismissed=True):
        item=self.company_detail(ident)
        with self.connect() as c:
            if dismissed:
                changed=c.execute('INSERT OR IGNORE INTO dismissed_companies(domain,created_at) VALUES (?,?)',(item['domain'],now())).rowcount
            else:
                changed=c.execute('DELETE FROM dismissed_companies WHERE domain=?',(item['domain'],)).rowcount
            if changed:
                text='Proposta eliminata manualmente. Azienda esclusa dalle ricerche future.' if dismissed else 'Proposta ripristinata manualmente.'
                c.execute('INSERT INTO interactions(prospect_id,kind,detail,created_at) VALUES (?,?,?,?)',(item['id'],'dismissed' if dismissed else 'restored',text,now()))
        return self.company_detail(item['id'])
    def update_company(self,ident,body):
        item=self.company_detail(ident)
        if item['dismissed_at']:raise ValueError('Ripristina la proposta prima di aggiornarla.')
        self.update(item['id'],body)
        return self.company_detail(item['id'])
    def requalify_growth(self):
        """Withdraw old location-only signals without deleting sources or user history."""
        changed=[]
        with self.connect() as c:
            for e in c.execute("SELECT * FROM evidence WHERE engine='C' AND kind='signal'").fetchall():
                if digital_project(e['detail']):continue
                meta=json.loads(e['metadata']);meta['selection_rejected']=GROWTH_REJECTION
                c.execute("UPDATE evidence SET kind='limitation',label=?,metadata=? WHERE id=?",('Segnale escluso: nessuna esigenza web dichiarata',encode(meta),e['id']))
        for row in self.list():
            if not row['qualification_rejected']:continue
            if row['stage'] not in ('review','ready'):continue
            self.update(row['id'],{'stage':'discarded','interaction':'Selezione corretta: '+GROWTH_REJECTION})
            changed.append(row['id'])
        return changed
    def detail(self,ident):
        item=next((r for r in self.list() if r['id']==ident),None)
        if not item: raise ValueError('Opportunità non trovata')
        with self.connect() as c:
            item['interactions']=[dict(r) for r in c.execute('SELECT * FROM interactions WHERE prospect_id=? ORDER BY id DESC',(ident,))]
            audit=c.execute('SELECT payload FROM audits WHERE company_id=?',(item['company_id'],)).fetchone()
            item['audit']=json.loads(audit[0]) if audit else None
        return item
    def update(self,ident,body):
        item=self.detail(ident)
        allowed=('stage','notes','contract_value','paid_value','contact_basis')
        values={k:body.get(k,item[k]) for k in allowed}
        if 'contact_group' in body and body['contact_group'] not in ('agencies','direct'):raise ValueError('Categoria contatto non valida')
        if values['stage'] not in STAGES: raise ValueError('Stato non valido')
        if not isinstance(values['notes'],str) or len(values['notes'])>15000: raise ValueError('Note non valide')
        if values['contact_basis'] not in ('','request','consent','existing_relationship','other_documented'): raise ValueError('Presupposto di contatto non valido')
        for k in ('contract_value','paid_value'):
            v=values[k]
            if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or v<0 or v>100000000): raise ValueError('Importo non valido')
        if values['stage']=='won' and not values['contract_value']: raise ValueError('Registra il valore del contratto acquisito')
        if values['paid_value'] is None: values['paid_value']=0
        with self.connect() as c:
            c.execute('UPDATE prospects SET stage=?,notes=?,contract_value=?,paid_value=?,contact_basis=?,updated_at=? WHERE id=?',(*values.values(),now(),ident))
            if values['stage']!=item['stage']:
                c.execute('INSERT INTO interactions(prospect_id,kind,detail,created_at) VALUES (?,?,?,?)',(ident,values['stage'],'Stato aggiornato manualmente: '+STAGES[values['stage']],now()))
            if body.get('interaction'):
                text=body['interaction']
                if not isinstance(text,str) or len(text)>5000: raise ValueError('Nota interazione non valida')
                kind='conversation' if body.get('conversation') is True else 'note'
                c.execute('INSERT INTO interactions(prospect_id,kind,detail,created_at) VALUES (?,?,?,?)',(ident,kind,text,now()))
            if 'contact_group' in body:
                category=body['contact_group']
                c.execute('INSERT INTO contact_groups VALUES (?,?,?,?,1) ON CONFLICT(company_id) DO UPDATE SET category=excluded.category,basis=excluded.basis,url=excluded.url,manual=1',(item['company_id'],category,'Categoria scelta manualmente da te.',''))
            if 'do_not_contact' in body:
                if type(body['do_not_contact'])!=bool: raise ValueError('Preferenza non valida')
                c.execute('UPDATE companies SET do_not_contact=? WHERE id=?',(int(body['do_not_contact']),item['company_id']))
        return self.detail(ident)
    def save_draft(self,ident,draft):
        self.detail(ident)
        if not isinstance(draft,dict) or set(draft)-{'subject','email','proposal','followup','rationale','mode','generated_at'}: raise ValueError('Bozza non valida')
        if any(not isinstance(v,str) or len(v)>18000 for v in draft.values()): raise ValueError('Bozza non valida')
        with self.connect() as c: c.execute('UPDATE prospects SET draft=?,updated_at=? WHERE id=?',(encode(draft),now(),ident))
    def cache_get(self,key,hours=24):
        with self.connect() as c: row=c.execute('SELECT * FROM cache WHERE key=?',(key,)).fetchone()
        if row and datetime.fromisoformat(row['created_at'])>datetime.now(timezone.utc)-timedelta(hours=hours): return json.loads(row['body'])
    def cache_set(self,key,body):
        with self.connect() as c: c.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)',(key,encode(body),now()))
    def reserve(self,provider='tavily'):
        config=self.settings();today=datetime.now(timezone.utc).date().isoformat()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            month=c.execute('SELECT coalesce(sum(units),0) FROM api_usage WHERE provider=? AND day LIKE ?',(provider,today[:7]+'%')).fetchone()[0]
            day=c.execute('SELECT coalesce(sum(units),0) FROM api_usage WHERE provider=? AND day=?',(provider,today)).fetchone()[0]
            over_limit=any(cap is not None and used>=cap for used,cap in ((day,config['daily_api_limit']),(month,config['monthly_api_limit'])))
            if provider=='serper' and over_limit:
                from .serper_provider import CreditLimit
                raise CreditLimit('Limite di consumo Serper raggiunto. Aumenta il tetto nelle impostazioni oppure attendi il nuovo periodo e premi Riprendi. Nessuna ricarica automatica.')
            if provider=='tavily' and over_limit: raise ValueError('Quota Tavily raggiunta. Nessun credito acquistato; risultati già letti conservati.')
            c.execute('INSERT INTO api_usage VALUES (?,?,1) ON CONFLICT(day,provider) DO UPDATE SET units=units+1',(today,provider))
    def usage(self):
        today=datetime.now(timezone.utc).date().isoformat()
        with self.connect() as c: rows=[dict(r) for r in c.execute('SELECT provider,sum(units) AS units FROM api_usage WHERE day=? GROUP BY provider',(today,))];month=c.execute("SELECT coalesce(sum(units),0) FROM api_usage WHERE provider='tavily' AND day LIKE ?",(today[:7]+'%',)).fetchone()[0]
        with self.connect() as c:serper_month=c.execute("SELECT coalesce(sum(units),0) FROM api_usage WHERE provider='serper' AND day LIKE ?",(today[:7]+'%',)).fetchone()[0]
        return {'today':{r['provider']:r['units'] for r in rows},'tavily_month':month,'serper_month':serper_month}
    def log(self,run_id,disposition,reason,url=None,query=None):
        with self.connect() as c: c.execute('INSERT INTO run_items(run_id,url,query,disposition,reason,created_at) VALUES (?,?,?,?,?,?)',(run_id,url,query,disposition,reason[:1000],now()))
    def history(self):
        with self.connect() as c:
            runs=[{**dict(r),'stats':json.loads(r['stats'])} for r in c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 40')]
            for r in runs: r['items']=[dict(x) for x in c.execute('SELECT * FROM run_items WHERE run_id=? ORDER BY id',(r['id'],))]
        return runs
    def stats(self):
        items=self.company_list();minimum=self.settings()['minimum_sample'];result=[]
        with self.connect() as c: events=[dict(r) for r in c.execute('SELECT prospect_id,kind FROM interactions')]
        canonical={member:i['id'] for i in items for member in i['all_member_ids']}
        events=[{**e,'prospect_id':canonical.get(e['prospect_id'],e['prospect_id'])} for e in events]
        for engine in ENGINES:
            group=[i for i in items if i['engine']==engine];ids={i['id'] for i in group}
            reached={stage:{e['prospect_id'] for e in events if e['prospect_id'] in ids and e['kind']==stage} for stage in (*STAGES,'conversation')}
            contacted=len(reached['contacted'])
            replied=len(reached['replied'])
            won=len(reached['won']);qualified=len(set.union(*(reached[k] for k in ('ready','contacted','replied','proposal','won','lost'))))
            result.append({'engine':engine,'found':len(group),'qualified':qualified,'contacted':contacted,'replied':replied,'conversations':len(reached['conversation']),'proposals':len(reached['proposal']),'accepted':won,'customers':len({i['company_id'] for i in group if i['id'] in reached['won']}),'contract_value':sum(i['recorded_contracts'] for i in group),'revenue':sum(i['recorded_revenue'] for i in group),'reply_rate':round(100*len(reached['replied'] & reached['contacted'])/contacted,1) if contacted>=minimum else None,'win_rate':round(100*len(reached['won'] & reached['contacted'])/contacted,1) if contacted>=minimum else None,'sample_sufficient':contacted>=minimum})
        eligible=[r for r in result if r['sample_sufficient']]
        recommendation=('Campione insufficiente: registra contatti ed esiti reali. Nessun canale è ancora dimostrato efficace.' if not eligible else 'Da approfondire: motore '+max(eligible,key=lambda r:(r['revenue'],r['customers'],r['reply_rate']))['engine']+'. Il confronto è descrittivo, non prova causalità; confronta anche tempo impiegato e dimensione del campione.')
        return {'engines':result,'recommendation':recommendation,'minimum_sample':minimum,'attribution':'Per azienda, attribuita al motore della scheda di gestione. Le fonti aggiunte dagli altri motori non duplicano contatti o clienti. Ricavi = incassi registrati manualmente; contratti = valore dichiarato.'}
