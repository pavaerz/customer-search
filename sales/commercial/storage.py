"""Versioned opportunities on shared entities/documents; CRM actions stay manual."""
import json,re
from sales.db import encode,digest,now,domain
from sales.research_store import ResearchStore
from sales.evaluation_policy import stamp
from .catalog import ENGINES,STATES

def migrate(store):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('''CREATE TABLE IF NOT EXISTS commercial_engine_runs(campaign_id INTEGER REFERENCES campaigns(id),engine TEXT,cursor INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'pending',error TEXT,PRIMARY KEY(campaign_id,engine))''')
        c.execute('''CREATE TABLE IF NOT EXISTS commercial_opportunities(id INTEGER PRIMARY KEY,entity_id INTEGER REFERENCES research_entities(id),engine TEXT NOT NULL,opportunity_key TEXT NOT NULL,latest_revision INTEGER,manual_state TEXT NOT NULL DEFAULT '',prospect_id INTEGER REFERENCES prospects(id),created_at TEXT NOT NULL,UNIQUE(entity_id,engine,opportunity_key))''')
        c.execute('''CREATE TABLE IF NOT EXISTS commercial_revisions(id INTEGER PRIMARY KEY,opportunity_id INTEGER REFERENCES commercial_opportunities(id),campaign_id INTEGER REFERENCES campaigns(id),fingerprint TEXT NOT NULL,state TEXT NOT NULL,score INTEGER NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(opportunity_id,campaign_id,fingerprint))''')
        c.execute('CREATE INDEX IF NOT EXISTS commercial_campaign ON commercial_revisions(campaign_id,opportunity_id)')
        c.execute('INSERT OR IGNORE INTO research_schema VALUES (60,?)',(now(),))
        c.execute('CREATE TABLE IF NOT EXISTS commercial_resources(campaign_id INTEGER REFERENCES campaigns(id),engine TEXT,resource TEXT,used INTEGER NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(campaign_id,engine,resource))')
        c.execute('CREATE TABLE IF NOT EXISTS commercial_discovery(id INTEGER PRIMARY KEY,campaign_id INTEGER REFERENCES campaigns(id),engine TEXT,query TEXT,url TEXT,decision TEXT,body TEXT,created_at TEXT)')
        c.execute('CREATE INDEX IF NOT EXISTS commercial_discovery_campaign ON commercial_discovery(campaign_id,engine,query)')
        c.execute('INSERT OR IGNORE INTO research_schema VALUES (61,?)',(now(),))
        c.execute('''CREATE TABLE IF NOT EXISTS commercial_social_reviews(id INTEGER PRIMARY KEY,opportunity_id INTEGER NOT NULL REFERENCES commercial_opportunities(id),revision_id INTEGER NOT NULL REFERENCES commercial_revisions(id),status TEXT NOT NULL,notes TEXT NOT NULL,evidence_ids TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL)''')
        c.execute('CREATE INDEX IF NOT EXISTS commercial_social_review_opportunity ON commercial_social_reviews(opportunity_id,id)')
        c.execute('INSERT OR IGNORE INTO research_schema VALUES (62,?)',(now(),))
        from .ai import migrate as migrate_ai
        migrate_ai(c)
        from .cache_policy import migrate as migrate_cache
        migrate_cache(c)
        from .recommendation_store import migrate as migrate_recommendations
        migrate_recommendations(c)
        from sales.agent6.memory import migrate as migrate_agent
        migrate_agent(c)

class Opportunities:
    def __init__(self,store):self.store=store;self.rs=ResearchStore(store)
    def save(self,campaign,identity,documents,result):
        if not self.rs.active(campaign['id'],campaign['generation']):return None
        from sales.content_policy import require_non_pdf
        require_non_pdf(result)
        for doc in documents:require_non_pdf(doc)
        for proof in result.get('evidence',[]):require_non_pdf(proof)
        engine=result['engine']
        if engine not in ENGINES or result['state'] not in STATES:raise ValueError('Esito commerciale non valido')
        for proof in result['evidence']:
            if proof.get('kind')=='measurement':continue
            def matches(d):
                if d['url']!=proof['url']:return False
                if not proof.get('channel'):return proof['quote'] in d['text']
                source=d.get('evidence_channels',{}).get(proof['channel'])
                start,end=proof.get('start'),proof.get('end')
                return bool(source and type(start)==int and type(end)==int and 0<=start<end<=len(source['text'])
                            and source['hash']==proof.get('source_hash')==digest(source['text'])
                            and source['text'][start:end]==proof['quote'])
            if not any(matches(d) for d in documents):raise ValueError('Prova non riscontrata nel documento originale')
        entity=self.rs.entity(identity)
        key=digest(' '.join(re.findall(r'\w+',' '.join(p['quote'] for p in result['evidence'] if p.get('kind')!='measurement').casefold())) or result['url'])
        if engine!='WEBSITE_REBUILD' and result.get('published_at') and (result.get('verification',{}).get('checks',{}).get('temporal_basis')):
            key=digest(key+'|request-date:'+result['published_at'])
        if engine=='WEBSITE_REBUILD':key='site:'+domain(result['url'])
        if engine=='AGENCIES' and result.get('classification') in ('ongoing','no_collaboration','generic_availability','seller') and identity.get('identity_status')=='verified':key='partner:'+str(entity)
        policy={**stamp(campaign['filters']),'commercial_engine':engine,'engine_version':result['rule_version']}
        body={**result,'identity':identity,'document_ids':[d['id'] for d in documents],'policy':policy}
        suppressed=self.rs.suppressed(identity)
        if suppressed:body.update(state='REJECTED',reason=suppressed)
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(campaign['id'],campaign['generation'])).fetchone():return None
            previous=c.execute('''SELECT o.*,r.body FROM commercial_opportunities o JOIN commercial_revisions r ON r.id=o.latest_revision
              WHERE o.entity_id=? AND o.engine=? AND json_extract(r.body,'$.url')=? ORDER BY r.id DESC LIMIT 1''',(entity,engine,result['url'])).fetchone()
            # Keep the existing ID for an unchanged dated request, including pre-4.0 keys.
            if previous:
                old=json.loads(previous['body'])
                if old.get('published_at')==result.get('published_at') and old.get('evidence')==result.get('evidence') and result.get('evidence'):
                    key=previous['opportunity_key']
            # Repair an incomplete read in place; it is not a second opportunity.
            if previous and (not result['evidence'] or not json.loads(previous['body'])['evidence']):
                if result['evidence'] and not c.execute('SELECT 1 FROM commercial_opportunities WHERE entity_id=? AND engine=? AND opportunity_key=?',(entity,engine,key)).fetchone():
                    c.execute('UPDATE commercial_opportunities SET opportunity_key=? WHERE id=?',(key,previous['id']))
                else:key=previous['opportunity_key']
            c.execute('INSERT OR IGNORE INTO commercial_opportunities(entity_id,engine,opportunity_key,created_at) VALUES (?,?,?,?)',(entity,engine,key,now()))
            row=c.execute('SELECT * FROM commercial_opportunities WHERE entity_id=? AND engine=? AND opportunity_key=?',(entity,engine,key)).fetchone()
            if row['manual_state']=='discarded':body.update(state='REJECTED',reason='Opportunità scartata manualmente: decisione preservata.')
            if c.execute('''SELECT 1 FROM research_entities e LEFT JOIN companies co ON co.id=e.company_id WHERE e.id=? AND
              (co.do_not_contact=1 OR co.prior_contacted=1 OR EXISTS (SELECT 1 FROM dismissed_companies d JOIN research_domains rd ON rd.domain=d.domain WHERE rd.entity_id=e.id)
              OR EXISTS (SELECT 1 FROM prospects p WHERE p.company_id=co.id AND p.stage IN ('contacted','replied','proposal','won','lost')))''',(entity,)).fetchone():
                body.update(state='REJECTED',reason='Contatto già gestito o escluso: decisione commerciale preservata.')
            fingerprint=digest(encode([policy,[(d['id'],d.get('content_hash')) for d in documents],body['state'],body['evidence'],body.get('classification'),body['reason']]))
            # Record a revision, never overwrite evidence from an earlier campaign.
            for d in documents:c.execute('INSERT OR IGNORE INTO research_documents VALUES (?,?,?,?,?,?,?,?,?)',(d['id'],d['url'],d['content_hash'],d.get('title',''),d['text'],d.get('published_at'),d['checked_at'],d.get('provider','Fonte originale'),encode({k:v for k,v in d.items() if k!='text'})))
            c.execute('INSERT OR IGNORE INTO commercial_revisions(opportunity_id,campaign_id,fingerprint,state,score,body,created_at) VALUES (?,?,?,?,?,?,?)',(row['id'],campaign['id'],fingerprint,body['state'],body['score'],encode(body),now()))
            rev=c.execute('SELECT id FROM commercial_revisions WHERE opportunity_id=? AND campaign_id=? AND fingerprint=?',(row['id'],campaign['id'],fingerprint)).fetchone()[0]
            c.execute('UPDATE commercial_opportunities SET latest_revision=? WHERE id=?',(rev,row['id']))
        return row['id']
    def get(self,ident):
        with self.store.connect() as c:
            row=c.execute('SELECT o.*,r.body,r.state,r.score,r.campaign_id AS evaluation_campaign_id,r.created_at AS checked_at FROM commercial_opportunities o JOIN commercial_revisions r ON r.id=o.latest_revision WHERE o.id=?',(ident,)).fetchone()
            if not row:raise ValueError('Opportunità non trovata')
            body=json.loads(row['body']);result={**dict(row),'body':body}
            result['documents']=[{**dict(d),'details':json.loads(d['details'])} for d in c.execute('SELECT * FROM research_documents WHERE id IN (SELECT value FROM json_each(?))',(encode(body['document_ids']),))]
            result['revisions']=[dict(r) for r in c.execute('SELECT id,campaign_id,state,score,created_at FROM commercial_revisions WHERE opportunity_id=? ORDER BY id DESC',(ident,))]
        return self.workflow(result)
    def workflow(self,item,previous=None):
        # CRM changes must also appear on research cards, without rewriting history.
        from .ai import lookup
        item['ai_assessment']=lookup(self.store,item.get('evaluation_campaign_id'),item['id'],item['engine']) if item.get('evaluation_campaign_id') else None
        with self.store.connect() as c:
            row=c.execute('''SELECT co.do_not_contact,co.prior_contacted,
              EXISTS (SELECT 1 FROM dismissed_companies d WHERE d.domain=co.domain) AS dismissed,
              EXISTS (SELECT 1 FROM prospects p WHERE p.company_id=co.id AND p.stage IN ('contacted','replied','proposal','won','lost')) OR
              EXISTS (SELECT 1 FROM interactions i JOIN prospects p ON p.id=i.prospect_id WHERE p.company_id=co.id AND i.kind IN ('contacted','replied','proposal','won','lost')) AS contacted
              FROM research_entities e JOIN companies co ON co.id=e.company_id WHERE e.id=?''',(item['entity_id'],)).fetchone()
            reviews=[{**dict(r),'evidence_ids':json.loads(r['evidence_ids'])} for r in c.execute('SELECT * FROM commercial_social_reviews WHERE opportunity_id=? ORDER BY id DESC',(item['id'],))]
            item['social_reviews']=reviews;item['social_review']=reviews[0] if reviews else None
            from .presentation import history,lead_type
            rows=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('SELECT id,campaign_id,state,body FROM commercial_revisions WHERE opportunity_id=? AND campaign_id<=? ORDER BY id',(item['id'],item.get('evaluation_campaign_id') or 0))]
            item['evidence_history']=history(rows)
            item['lead_profile']=lead_type(item['body'])
        if row:
            item['do_not_contact']=bool(row['do_not_contact']);item['company_dismissed']=bool(row['dismissed'])
            if item['manual_state']!='discarded' and (row['contacted'] or row['prior_contacted']):item['manual_state']='contacted'
        from .opportunity_view import build,novelty
        documents=item.get('documents',())
        if not documents and item['body'].get('engine')=='WEBSITE_REBUILD':
            with self.store.connect() as c:documents=[dict(d) for d in c.execute('SELECT url,text FROM research_documents WHERE id IN (SELECT value FROM json_each(?))',(encode(item['body'].get('document_ids',[])),))]
        view=build(item['body'],documents,item)
        # A failed new read cannot erase the old request; it cannot renew its availability either.
        if view['status']=='NOT_ACTIONABLE' and not view['blockers'] and item['body'].get('classification')=='access_incomplete':
            useful=[(r,build(r['body'],manual=item)) for r in rows if r['body'].get('evidence')]
            useful=[(r,v) for r,v in useful if v['status'] in ('READY_TO_CONTACT','WORTH_REVIEWING','RESEARCH_REQUIRED')]
            if useful:
                old,view=useful[-1];view={**view,'status':'WORTH_REVIEWING' if view['official_domain'] else 'RESEARCH_REQUIRED','label':'Prova precedente da riconfermare','priority':2,'official_state':item['state'],
                    'retained_revision':old['id'],'next_action':'Ricontrollare la fonte: l’ultima lettura non è riuscita.',
                    'missing':view['missing']+['Richiesta conservata da una revisione precedente, non riconfermata dall’ultimo controllo.']}

        if previous is None:
            with self.store.connect() as c:
                previous=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('SELECT id,campaign_id,body FROM commercial_revisions WHERE campaign_id<? ORDER BY id',(item.get('evaluation_campaign_id') or 0,))]
        else:previous=[r for r in previous if r['campaign_id']<(item.get('evaluation_campaign_id') or 0)]
        view['novelty']=novelty(item['body'],previous)
        view['subject_new']=bool(view['subject_key']) and not any(__import__('sales.commercial.opportunity_view',fromlist=['normalize']).normalize((r['body'].get('identity') or {}).get('website'))==view['subject_key'] for r in previous)
        item['commercial_view']=view
        return item
    def listing(self,filters=None):
        f=filters or {};where=[];args=[]
        if f.get('source'):
            where.append("coalesce(json_extract(r.body,'$.discovery.source'),'web')=?");args.append(f['source'])
        if f.get('social_review'):
            where.append("(SELECT sr.status FROM commercial_social_reviews sr WHERE sr.opportunity_id=o.id ORDER BY sr.id DESC LIMIT 1)=?");args.append(f['social_review'])
        if f.get('state')=='review':
            where.append("r.state IN ('NEEDS_REVIEW','UNVERIFIABLE')");f={**f,'state':''}
        for key,column in [('engine','o.engine'),('state','r.state')]:
            if f.get(key):where.append(column+'=?');args.append(f[key])
        revision='o.latest_revision'
        if f.get('campaign'):
            revision='(SELECT max(cr.id) FROM commercial_revisions cr WHERE cr.opportunity_id=o.id AND cr.campaign_id=?)'
            args.insert(0,int(f['campaign']))
        if f.get('region'):where.append("EXISTS (SELECT 1 FROM json_each(r.body,'$.geography.regions') WHERE value=?)");args.append(f['region'])
        if f.get('priority'):where.append('r.score>=?');args.append(max(0,min(100,int(f['priority']))))
        if f.get('date'):where.append("json_extract(r.body,'$.published_at')>=?");args.append(f['date'])
        if f.get('search'):where.append("(json_extract(r.body,'$.company') LIKE ? OR json_extract(r.body,'$.website') LIKE ?)");args.extend(['%'+f['search']+'%']*2)
        if not f.get('include_discarded'):where.append("o.manual_state<>'discarded'")
        if f.get('useful')=='1':where.append("r.state IN ('VERIFIED','POTENTIAL')")
        limit=max(1,min(100,int(f.get('limit',20))));offset=max(0,int(f.get('offset',0)))
        source=' FROM commercial_opportunities o JOIN commercial_revisions r ON r.id='+revision+(' WHERE '+' AND '.join(where) if where else '')
        with self.store.connect() as c:
            advisory=bool(f.get('commercial_view')) or any(f.get(k) for k in ('commercial_status','novelty','opportunity_type','currentness','contact','audit'))
            if advisory:
                raw=c.execute('SELECT o.*,r.body,r.state,r.score,r.campaign_id AS evaluation_campaign_id,r.id AS selected_revision'+source+' ORDER BY r.id DESC',args).fetchall()
            total=c.execute('SELECT count(*)'+source,args).fetchone()[0]
            from .presentation import lead_type
            c.create_function('commercial_priority',1,lambda body:lead_type(json.loads(body))['priority'])
            rows=c.execute('SELECT o.*,r.body,r.state,r.score,r.campaign_id AS evaluation_campaign_id,r.id AS selected_revision'+source+' ORDER BY commercial_priority(r.body) DESC,r.score DESC,o.id DESC LIMIT ? OFFSET ?',(*args,limit,offset)).fetchall()
        if advisory:
            with self.store.connect() as c:
                prior=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('SELECT id,campaign_id,body FROM commercial_revisions ORDER BY id')]
            items=[self.workflow({**dict(r),'body':json.loads(r['body'])},prior) for r in raw]
            from .opportunity_view import metrics
            commercial_metrics=metrics(items)
            seen_requests={}
            for item in items:
                key=item['commercial_view']['request_key']
                if key:
                    item['commercial_view']['same_request_as']=seen_requests.get(key)
                    seen_requests.setdefault(key,item['id'])
            commercial_metrics['republished_requests']=sum(bool(i['commercial_view'].get('same_request_as')) for i in items)
            with self.store.connect() as c:
                cr=c.execute('SELECT created_at FROM campaigns WHERE id=?',(f.get('campaign'),)).fetchone() if f.get('campaign') else None
                times={r['id']:r['created_at'] for r in c.execute('SELECT id,created_at FROM commercial_revisions')}
            from .opportunity_view import date_value
            for label,status in [('ready','READY_TO_CONTACT'),('useful',None)]:
                selected=[i for i in items if (i['commercial_view']['status']==status if status else i['commercial_view']['status'] in ('READY_TO_CONTACT','WORTH_REVIEWING'))]
                stamps=[date_value(times.get(i.get('selected_revision') or i['latest_revision'])) for i in selected]
                stamps=[t for t in stamps if t]
                commercial_metrics['time_to_first_'+label+'_seconds']=(min(stamps)-date_value(cr[0])).total_seconds() if cr and stamps else None
            commercial_metrics['time_basis']='Read-only projection on saved revision time; wall-clock includes manual pauses, not active processing or contact conversion.'

            def matches(item):
                v=item['commercial_view'];status=f.get('commercial_status')
                return ((not status or (v['status']!='NOT_ACTIONABLE' if status=='actionable' else v['status']==status))
                    and (not f.get('novelty') or v['novelty']['status']==f['novelty'])
                    and (not f.get('opportunity_type') or v['opportunity_type']==f['opportunity_type'])
                    and (not f.get('currentness') or v['currentness']==f['currentness'])
                    and (not f.get('contact') or bool(v['contacts'])==(f['contact']=='available'))
                    and (not f.get('audit') or (v['audit_state']=='COMPLETE' if f['audit']=='complete' else v['audit_state']=='NOT_EXECUTED' if f['audit']=='none' else v['audit_state'] not in ('COMPLETE','NOT_EXECUTED'))))
            items=sorted((i for i in items if matches(i)),key=lambda i:(-i['commercial_view']['priority'],-i['score'],i['id']))
            return {'items':items[offset:offset+limit],'total':len(items),'offset':offset,'limit':limit,'commercial_metrics':commercial_metrics}
        return {'items':[self.workflow({**dict(r),'body':json.loads(r['body'])}) for r in rows],'total':total,'offset':offset,'limit':limit}
    def social_review(self,ident,request):
        """Append a human assessment; never mutate the qualification or identity."""
        statuses={'interesting','unavailable','identified','official_confirmed','inactive','irrelevant'}
        status=request.get('status');notes=request.get('notes','');ids=request.get('evidence_ids',[])
        if not isinstance(status,str) or status not in statuses:raise ValueError('Stato di revisione non valido')
        if not isinstance(notes,str) or not notes.strip() or len(notes)>4000:raise ValueError('Inserisci una nota di revisione (massimo 4000 caratteri)')
        if not isinstance(ids,list) or len(ids)>20 or any(not isinstance(x,str) for x in ids):raise ValueError('Riferimenti alle prove non validi')
        item=self.get(ident);body=item['body']
        if not body.get('social'):raise ValueError('La revisione è riservata agli indizi social')
        docs={d['id']:d for d in item['documents']}
        if any(x not in docs for x in ids):raise ValueError('Prova non presente nei documenti acquisiti per questo indizio')
        identity=body.get('identity',{})
        if status in ('identified','official_confirmed') and identity.get('identity_status')!='verified':
            raise ValueError('Identità non verificata nelle fonti: una nota manuale non la certifica')
        if status=='official_confirmed':
            official=[d for k,d in docs.items() if k in ids and d['details'].get('official') and domain(d['url'])==domain(identity.get('website','')) and domain(d['url']) not in ('instagram.com','linkedin.com','facebook.com')]
            if not any(p.get('kind')!='measurement' and p.get('quote') and p['quote'] in d['text'] and p.get('url')==d['url'] for d in official for p in body.get('evidence',[])):
                raise ValueError('Seleziona una fonte ufficiale acquisita con una prova della richiesta')
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            # Tie review to the exact revision read, even if a worker saves a newer one.
            c.execute('INSERT INTO commercial_social_reviews(opportunity_id,revision_id,status,notes,evidence_ids,actor,created_at) VALUES (?,?,?,?,?,?,?)',(ident,item['latest_revision'],status,notes.strip(),encode(list(dict.fromkeys(ids))),'local_user',now()))
        return self.get(ident)

    def action(self,ident,action):
        if action not in ('save','interesting','discard','restore','deal','contacted'):raise ValueError('Azione non valida')
        item=self.get(ident);body=item['body'];identity=body['identity']
        if action in ('discard','restore'):
            with self.store.connect() as c:c.execute('UPDATE commercial_opportunities SET manual_state=? WHERE id=?',('discarded' if action=='discard' else '',ident))
            if item['prospect_id']:self.store.update(item['prospect_id'],{'stage':'discarded' if action=='discard' else 'review'})
            return self.get(ident)
        if item['manual_state']=='discarded':raise ValueError('Ripristina prima l’opportunità scartata')
        if item['prospect_id']:
            with self.store.connect() as c:
                excluded=c.execute('SELECT co.do_not_contact,EXISTS (SELECT 1 FROM dismissed_companies d WHERE d.domain=co.domain) AS dismissed_at FROM companies co JOIN prospects p ON p.company_id=co.id WHERE p.id=?',(item['prospect_id'],)).fetchone()
            if excluded and (excluded['do_not_contact'] or excluded['dismissed_at']):raise ValueError('Contatto escluso: ripristinarlo manualmente dal CRM')
        if not item['prospect_id']:
            if identity.get('identity_status')!='verified':raise ValueError('Identità non verificata: completare la verifica prima del CRM')
            if reason:=self.rs.suppressed(identity):raise ValueError(reason)
            cid=self.store.company(identity['website'],identity['name'],location=identity.get('location'),contacts=identity.get('contacts'))
            self.store.classify_contact(cid,identity.get('group','direct'),'Identità nelle fonti della ricerca commerciale',identity['website'])
            evidence_ids=[];legacy={'FREELANCE':'A','AGENCIES':'B','STARTUPS':'C','WEBSITE_REBUILD':'D'}[item['engine']]
            for proof in body['evidence']:
                sid=self.store.source({'url':proof['url'],'title':body['title'],'published_at':proof.get('published_at'),'checked_at':proof['checked_at'],'excerpt':proof['quote']},cid)
                evidence_ids.append(self.store.add_evidence(cid,sid,legacy,'measurement' if item['engine']=='WEBSITE_REBUILD' else 'request','Prova '+item['engine']+' · '+str(ident)+' · '+digest(proof['quote'])[:12],proof['quote'],proof.get('published_at'),metadata={'commercial_opportunity':ident,'commercial_engine':item['engine']}))
            pid,_=self.store.prospect(cid,legacy,body['title'],', '.join(body['skills']) or 'Sito aziendale',body['score'],{k:v['points'] for k,v in body['score_detail'].items()},body['reason'],'Potenziale cliente; intenzione di acquisto non dimostrata.' if item['engine']=='WEBSITE_REBUILD' else body['classification'],body['limits'],evidence_ids,identity='v4:commercial:'+str(ident))
            with self.store.connect() as c:
                c.execute('UPDATE commercial_opportunities SET prospect_id=? WHERE id=?',(pid,ident))
                c.execute('UPDATE research_entities SET company_id=? WHERE id=?',(cid,item['entity_id']))
        else:pid=item['prospect_id']
        if action in ('deal','contacted'):
            self.store.update(pid,{'stage':'ready' if action=='deal' else 'contacted'})
        with self.store.connect() as c:c.execute('UPDATE commercial_opportunities SET manual_state=? WHERE id=?',(action,ident))
        return self.get(ident)


def discovery_listing(store,filters):
    where=[];args=[]
    for key,column in [('campaign','campaign_id'),('engine','engine'),('decision','decision')]:
        if filters.get(key):where.append(column+'=?');args.append(filters[key])
    for key,path in [('source','source'),('region','origin.region')]:
        if filters.get(key):where.append("json_extract(body,'$."+path+"')=?");args.append(filters[key])
    if filters.get('preliminary_priority'):
        where.append("json_extract(body,'$.priority')>=?");args.append(int(filters['preliminary_priority']))
    clause=(' WHERE '+' AND '.join(where)) if where else ''
    limit=max(1,min(100,int(filters.get('limit',20))));offset=max(0,int(filters.get('offset',0)))
    with store.connect() as c:
        total=c.execute('SELECT count(*) FROM commercial_discovery'+clause,args).fetchone()[0]
        rows=c.execute('SELECT * FROM commercial_discovery'+clause+' ORDER BY id DESC LIMIT ? OFFSET ?',(*args,limit,offset)).fetchall()
    return {'items':[{**dict(r),'body':json.loads(r['body'])} for r in rows],'total':total,'offset':offset,'limit':limit}
