"""Small, feedback-driven query frontier; decisions rely on original-page triage."""
import json
import re
import unicodedata
from .db import digest, encode, now, domain
from .research_strategies import TEMPLATES, SECTORS, PATTERNS
from .research_funnel import Funnel

# Bound pagination per formulation; the finite variant frontier is a separate budget.
MAX_QUERY_PAGES = 10


def query_key(payload):
    text=unicodedata.normalize('NFKC',payload['query']).casefold()
    text=re.sub(r'e[ -]?commerce','ecommerce',text)
    text=re.sub(r'\s+',' ',text).strip()
    # Quoted phrases and site restrictions remain atomic; sector/territory are retained.
    tokens=re.findall(r'"[^"]+"|\S+',text)
    return digest(encode([sorted(set(tokens)),payload.get('period',''),payload.get('page',1)]))


def searchable_query(payload):
    """Do not fill Google's first page with sources our reader cannot access.

    Keep exact identity/domain lookups intact. The effective query is persisted
    and displayed normally; exclusions are never hidden transport parameters.
    """
    query=payload['query']
    if payload.get('subject') or re.search(r'(?:^|\s)site:',query,re.I):return query
    from .config import BLOCKED
    for host in ('facebook.com','instagram.com','youtube.com'):
        operator='-site:'+host
        if host in BLOCKED and operator not in query.lower():query+=' '+operator
    for host in ('paginegialle.it','paginebianche.it','firmania.it','europages.it','confindustriavenest.it'):
        operator='-site:'+host
        if operator not in query.lower():query+=' '+operator
    if payload.get('strategy') in ('partner','explicit'):
        for operator in ('-site:indeed.com','-site:addlance.com','-filetype:pdf'):
            if operator not in query.lower():query+=' '+operator
    return query


def company_yield(rows):
    """One vote per verified company; a final review outranks old triage flags."""
    groups={}
    for row in rows:
        details=json.loads(row['details'])
        if details.get('publisher'):continue
        identity=details.get('identity',{})
        verified=identity.get('identity_status')=='verified'
        key=(identity.get('legal_id') or domain(identity.get('website',''))) if verified else None
        groups.setdefault(key or row['url'],[]).append((row,details))
    outcomes=[]
    for group in groups.values():
        reviewed=[pair for pair in group if pair[0].get('assessment_id')]
        if reviewed:
            row,details=max(reviewed,key=lambda pair:pair[0]['assessment_id'])
            state=row.get('assessment_status') or row['state']
            useful=state=='qualified'
        else:
            row,details=max(group,key=lambda pair:pair[0].get('updated_at',''))
            state=row['state']
            useful=state not in ('rejected','unverifiable') and (state in ('promising','qualified') or details.get('company_ready',False))
        identity=details.get('identity',{});collaboration=details.get('collaboration') or {}
        contactable=bool(state=='promising' and identity.get('identity_status')=='verified'
                         and identity.get('contacts') and collaboration.get('quote') and collaboration.get('checked_at')
                         and domain(collaboration.get('url',''))==domain(identity.get('website',''))
                         and domain(identity.get('website','')))
        outcomes.append({'state':state,'useful':bool(useful),'contactable':contactable})
    return outcomes


def variants(strategy, region, profile="b2b"):
    if strategy == "companies":
        from .company_research import company_queries
        yield from company_queries(region, profile)
        return
    from .commercial_planner import EVENTS, queries
    if strategy in EVENTS:
        yield from queries(strategy,region,profile)
        return
    # Generated on demand. First try different wording, then sectors if evidence warrants it.
    from .company_research import regional_sectors
    sectors=regional_sectors(region,profile)
    seen=set()
    if strategy=='partner':
        from .research_rules import REGION_CITIES
        # An agency vacancy usually names a town, not the administrative region.
        places=[region]+re.findall(r'La Spezia|Reggio Emilia|[A-ZÀ-Ý][a-zà-ÿ]+',REGION_CITIES.get(region,''))
        for place in places:
            for query in (f'"lavora con noi" WordPress freelance {place}',f'agenzia {place} "cerchiamo" freelance WordPress',f'"collabora con noi" WordPress freelance {place}',f'inurl:jobs WordPress freelance {place}',f'inurl:careers frontend freelance {place}'):
                seen.add(query_key({'query':query}));yield query
    for index in range(max(len(sectors),len(TEMPLATES[strategy]))):
      for relaxed in (False,True):
        for offset in range(len(TEMPLATES[strategy])):
            sector=sectors[index%len(sectors)]
            template=TEMPLATES[strategy][(index+offset)%len(TEMPLATES[strategy])]
            exact=template.format(area=region,sector=sector)
            for query in (exact.replace('"','') if relaxed else exact,):
                fp=query_key({'query':query})
                if fp not in seen:
                    seen.add(fp);yield query


class CommercialIntelligencePlanner:
    def __init__(self,rs):self.rs=rs;self.store=rs.store;self.funnel=Funnel(rs)
    def restore_company_reviews(self,campaign):
        """Resume investigations for businesses identified before this route existed."""
        from .company_research import company_verification
        with self.store.connect() as c:
            rows=c.execute("SELECT url,details FROM discovery_candidates WHERE campaign_id=? AND json_extract(details,'$.company_ready')=1 AND assessment_id IS NULL",(campaign['id'],)).fetchall()
        added=0
        for row in rows:
            d=json.loads(row['details'])
            if self.rs.suppressed(d.get('identity',{})):continue
            p=company_verification({'url':row['url'],'filters':campaign['filters']},{'details':d})
            if p:added+=int(self.funnel.offer(campaign['id'],'verify','companies',p,'company-review:'+digest(p['company_key']+p.get('evidence_revision',''))))
        return added
    def adopt(self,campaign):
        """Retain historical IDs; retire only unstarted generic legacy search combinations."""
        cid=campaign['id']
        from .prospect_scope import apply_scope
        apply_scope(self.rs,campaign)
        with self.store.connect() as c:
            if c.execute('SELECT 1 FROM discovery_branches WHERE campaign_id=?',(cid,)).fetchone():
                # Old two-query pauses must not strand the unexplored frontier on Resume.
                c.execute("UPDATE discovery_branches SET state='active',reason=NULL,dry_streak=0 WHERE campaign_id=? AND state='paused' AND reason='Due formulazioni senza riscontri pertinenti nelle pagine originali.'",(cid,))
                c.execute("UPDATE discovery_branches SET state='active',reason=NULL WHERE campaign_id=? AND state='paused' AND reason='Fonti non verificabili: ramo sospeso, nessuna conclusione sul mercato.'",(cid,))
                from .company_research import selected_strategies
                allowed=selected_strategies(campaign['filters'])
                for b in c.execute("SELECT strategy,region FROM discovery_branches WHERE campaign_id=?",(cid,)).fetchall():
                    if b['strategy'] not in allowed:c.execute("UPDATE discovery_branches SET state='retired' WHERE campaign_id=? AND strategy=? AND region=?",(cid,b['strategy'],b['region']))
                # New hypotheses have their own work; historical retired queries stay preserved.
                for region in campaign['filters'].get('regions') or ['Veneto']:
                    for strategy in allowed:
                        c.execute('INSERT OR IGNORE INTO discovery_branches(campaign_id,strategy,region) VALUES (?,?,?)',(cid,strategy,region))
                        c.execute("UPDATE discovery_branches SET state='active',last_query=NULL,reason=NULL WHERE campaign_id=? AND strategy=? AND region=? AND state='retired'",(cid,strategy,region))
                return
            c.execute('BEGIN IMMEDIATE')
            legacy_queries={template.format(area=region,sector=sector) for templates in TEMPLATES.values() for template in templates for region in campaign['filters'].get('regions') or ['Veneto'] for sector in SECTORS}
            legacy_queries.update(template.format(area=region,sector=sector) for template in ('"cerchiamo" "nuovo sito" {area}','"nuova linea" "prodotti" {area} {sector}','"espansione" "azienda" {area} {sector}','"nuovo marchio" {area}','{sector} {area} "ordini" "Excel"','{sector} {area} "configurazione" "preventivo"','{sector} {area} "prenotazioni" "modulo"','"studio grafico" "partner" "sviluppo" {area}','"consulenza marketing" "collaborazione" "sviluppatore" {area}','"agenzia SEO" "partner tecnico" {area}') for region in campaign['filters'].get('regions') or ['Veneto'] for sector in SECTORS)
            for table in ('research_tasks','discovery_frontier'):
                attempts=' AND attempts=0' if table=='research_tasks' else ''
                rows=c.execute("SELECT id,payload FROM "+table+" WHERE campaign_id=? AND kind='search' AND state IN ('pending','deferred','blocked')"+attempts,(cid,)).fetchall()
                for row in rows:
                    payload=json.loads(row['payload'])
                    if payload.get('subject') or payload.get('query_key') or payload.get('page',1)!=1 or payload.get('query') not in legacy_queries:continue
                    c.execute("UPDATE "+table+" SET state='superseded' WHERE id=?",(row['id'],))
        self.initialize(campaign)
        self.rs.event(cid,'planner','Query generiche non iniziate sostituite dal piano progressivo; candidati, query di identità e storico conservati.')
    def initialize(self,campaign):
        with self.store.connect() as c:
            for region in campaign['filters'].get('regions') or ['Veneto']:
                from .company_research import selected_strategies
                for strategy in selected_strategies(campaign['filters']):
                    c.execute('INSERT OR IGNORE INTO discovery_branches(campaign_id,strategy,region) VALUES (?,?,?)',(campaign['id'],strategy,region))
        self.tick(campaign)
    def offer_query(self,campaign,strategy,payload):
        from .discovery_relevance import subject_exclusion
        reason=subject_exclusion(payload.get('subject',''),payload.get('source_documents',[])) if payload.get('subject') and not payload.get('company_host') else None
        if reason:
            self.rs.event(campaign['id'],'acquisition_filter',reason,details={'subject':payload['subject'],'query':payload['query']})
            return None
        payload={**payload,'query':searchable_query({**payload,'strategy':strategy}),'direct_channels':True}
        fp=query_key(payload);cid=campaign['id']
        from .commercial_planner import hypothesis
        payload={**payload,'query_key':fp}
        payload.setdefault('root_query_key',fp)
        payload.setdefault('hypothesis',hypothesis(strategy,payload.get('region',''),campaign['filters'].get('target','b2b'),campaign['filters'].get('projects')))
        payload.setdefault('research_intent','company' if strategy=='companies' else 'signal')
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(cid,campaign['generation'])).fetchone():return None
            if c.execute('SELECT 1 FROM discovery_queries WHERE campaign_id=? AND fingerprint=?',(cid,fp)).fetchone():return fp
            if payload.get('alternative_source') and c.execute("""SELECT 1 FROM discovery_frontier
                WHERE campaign_id=? AND kind='search' AND json_extract(payload,'$.alternative_source') IS NOT NULL
                AND lower(json_extract(payload,'$.subject'))=lower(?)
                AND coalesce(json_extract(payload,'$.root_query_key'),'')=?""",
                (cid,payload.get('subject',''),payload.get('root_query_key') or '')).fetchone():return None
            c.execute('INSERT INTO discovery_queries(campaign_id,fingerprint,query,strategy,region,page,created_at) VALUES (?,?,?,?,?,?,?)',(cid,fp,payload['query'],strategy,payload.get('region'),payload.get('page',1),now()))
            # Atomic with query memory: a crash cannot strand a query before enqueue.
            c.execute('INSERT OR IGNORE INTO discovery_frontier(campaign_id,kind,strategy,payload,fingerprint,created_at) VALUES (?,\'search\',?,?,?,?)',(cid,strategy,encode(payload),'adaptive:'+fp,now()))
        return fp
    def observed(self,campaign,task,urls,new_count,can_page=True,result_kind=None):
        p=task['payload'];fp=p.get('query_key')
        if not fp:return
        with self.store.connect() as c:c.execute("UPDATE discovery_queries SET status='observed',urls=?,new_urls=?,can_page=? WHERE campaign_id=? AND fingerprint=?",(encode(list(dict.fromkeys(urls))),new_count,int(can_page),campaign['id'],fp))
        if result_kind:
            with self.store.connect() as c:c.execute('UPDATE discovery_queries SET decision=? WHERE campaign_id=? AND fingerprint=?',(result_kind,campaign['id'],fp))
    def resolve_pending_subjects(self,campaign):
        """One distinct trading-name formulation after an unsuccessful exact-name lookup.

        Pending reads must finish first. Technical failures do not justify spending
        another search credit. Query memory makes repeated coordinator ticks safe.
        """
        cid=campaign['id'];added=0
        if not self.rs.active(cid,campaign['generation']):return 0
        with self.store.connect() as c:
            queries=[dict(r) for r in c.execute("SELECT q.*,f.payload FROM discovery_queries q JOIN discovery_frontier f ON f.campaign_id=q.campaign_id AND json_extract(f.payload,'$.query_key')=q.fingerprint WHERE q.campaign_id=? AND q.status='observed' AND q.decision IS NULL AND f.kind='search' AND json_extract(f.payload,'$.subject') IS NOT NULL AND json_extract(f.payload,'$.company_host') IS NULL",(cid,))]
        for q in queries:
            p=json.loads(q['payload']);urls=json.loads(q['urls'])
            with self.store.connect() as c:
                rows=[dict(r) for r in c.execute('SELECT state,details FROM discovery_candidates WHERE campaign_id=? AND url IN (SELECT value FROM json_each(?))',(cid,encode(urls)))]
            if len(rows)<len(urls) or any(r['state'] in ('discovered','verifying') for r in rows):continue
            resolved=any(json.loads(r['details']).get('company_ready') for r in rows)
            technical=bool(rows) and all(r['state']=='unverifiable' for r in rows)
            decision='identity_resolved' if resolved else 'technical' if technical else 'identity_unresolved'
            if not resolved and not technical and not p.get('identity_variant') and not p.get('alternative_source'):
                from .source_identity import alternate_identity_query
                next_payload={**p,'query':alternate_identity_query(p['subject'],p.get('region')),'page':1,'period':'','identity_variant':'trading_name'}
                if query_key(next_payload)!=q['fingerprint']:
                    if self.offer_query(campaign,q['strategy'],next_payload):
                        added+=1;decision='identity_alternative'
                        self.rs.event(cid,'planner','Nome completo non risolto: cerco le parole distintive dell’impresa, mantenendo il controllo di identità.',details={'subject':p['subject'],'query':next_payload['query']})
                    else:decision='subject_excluded'
            with self.store.connect() as c:c.execute('UPDATE discovery_queries SET decision=? WHERE campaign_id=? AND fingerprint=?',(decision,cid,q['fingerprint']))
        return added

    def query_evidence(self,campaign,query):
        """Credit a source for the companies reached through it, never the publisher.

        Wait for scheduled identity and commercial reviews. Finding a real company
        is not commercial productivity after a negative review. Legacy candidates
        retain their direct URL association.
        """
        cid=campaign['id'];fp=query['fingerprint'];urls=json.loads(query['urls'])
        with self.store.connect() as c:
            rows=[dict(r) for r in c.execute("SELECT d.*,a.status AS assessment_status FROM discovery_candidates d LEFT JOIN research_assessments a ON a.id=d.assessment_id WHERE d.campaign_id=? AND (d.url IN (SELECT value FROM json_each(?)) OR json_extract(d.details,'$.root_query_key')=?)",(cid,encode(urls),fp))]
            pending=c.execute("""SELECT 1 FROM discovery_frontier f
                LEFT JOIN research_tasks t ON t.campaign_id=f.campaign_id AND t.fingerprint=f.fingerprint
                WHERE f.campaign_id=? AND (json_extract(f.payload,'$.root_query_key')=?
                     OR EXISTS (SELECT 1 FROM json_each(f.payload,'$.review_inputs') i
                                WHERE json_extract(i.value,'$.root_query_key')=?))
                AND (f.kind IN ('candidate','source','verify')
                     OR (f.kind='search' AND json_extract(f.payload,'$.query_key')<>?))
                AND (f.state='pending' OR (f.state='assigned' AND t.state IN ('pending','working','deferred')))
                LIMIT 1""",(cid,fp,fp,fp)).fetchone()
        seen={r['url'] for r in rows}
        return rows,bool(pending or set(urls)-seen or any(r['state'] in ('discovered','verifying') for r in rows))

    def tick(self,campaign):
        from .discovery_control import available
        cid=campaign['id']
        if not self.rs.active(cid,campaign['generation']) or not available(self.store):return 0
        self.resolve_pending_subjects(campaign)
        with self.store.connect() as c:
            branches=[dict(r) for r in c.execute("SELECT * FROM discovery_branches WHERE campaign_id=? AND state='active' ORDER BY CASE WHEN strategy='companies' THEN 0 ELSE 1 END,cursor,rowid",(cid,))]
            pending=c.execute("SELECT count(*) FROM discovery_queries WHERE campaign_id=? AND status='pending'",(cid,)).fetchone()[0]
        added=0
        for b in branches:
            if pending>=len(TEMPLATES):break  # Fair scheduling window, replenished continuously.
            dry=b['dry_streak'];following=None
            if b['last_query']:
                with self.store.connect() as c:
                    q=c.execute('SELECT * FROM discovery_queries WHERE campaign_id=? AND fingerprint=?',(cid,b['last_query'])).fetchone()
                    if not q or q['status']!='observed':continue
                rows,resolving=self.query_evidence(campaign,q)
                if resolving:continue
                outcomes=company_yield(rows)
                useful=[r for r in outcomes if r['useful']]
                # One actual contact/opportunity earns further exploration.
                # Do not discard it because many other results were irrelevant.
                healthy=any(r['state']=='qualified' or r['contactable'] for r in outcomes) or (bool(useful) and len(useful)/max(1,len(outcomes))>=.25)
                # Inaccessibility is a technical gap, not evidence of commercial failure.
                inaccessible=bool(outcomes) and all(r['state']=='unverifiable' for r in outcomes)
                known=q['decision'] in ('known_results','query_error') and not outcomes
                decision='technical' if inaccessible else 'productive' if healthy else q['decision'] if known or (not outcomes and q['decision']=='empty') else 'dry'
                dry=0 if healthy else dry if inaccessible or known else dry+1
                with self.store.connect() as c:c.execute('UPDATE discovery_queries SET decision=? WHERE campaign_id=? AND fingerprint=?',(decision,cid,q['fingerprint']))
                if inaccessible:
                    self.rs.event(cid,'branch','Fonti della query non verificabili: continuo con la variante successiva, senza concludere che manchino opportunità.',details={'strategy':b['strategy'],'region':b['region'],'scope':'url','outcome':'unverifiable'})
                if dry>=2:
                    # Two noisy queries say nothing about all the remaining sectors.
                    # The finite deduplicated frontier bounds work without pretending exhaustion.
                    dry=0
                    self.rs.event(cid,'branch','Formulazioni senza riscontri: passo a un altro bisogno o settore, mantenendo i requisiti.',details={'strategy':b['strategy'],'region':b['region']})
                # Pagination is earned by original-page relevance, not new snippets alone.
                if healthy and q['new_urls'] and q['can_page'] and q['page'] < MAX_QUERY_PAGES:
                    following={'query':q['query'],'page':q['page']+1,'period':'' if b['strategy'] in ('companies','gap','process','partner','sources') else 'year','region':b['region']}
            cursor=b['cursor']
            if following is None:
                choices=list(variants(b['strategy'],b['region'],campaign['filters'].get('target','b2b')))
                period='' if b['strategy'] in ('companies','gap','process','partner','sources') else 'year'
                with self.store.connect() as c:
                    issued={r[0] for r in c.execute('SELECT fingerprint FROM discovery_queries WHERE campaign_id=?',(cid,))}
                # The cursor remains a scheduling counter, not a position in a
                # particular release's query list. Reordering must neither replay
                # paid searches nor skip unvisited hypotheses after an upgrade.
                for query in choices:
                    candidate={'query':query,'page':1,'period':period,'region':b['region']}
                    candidate['query']=searchable_query({**candidate,'strategy':b['strategy']})
                    if query_key(candidate) not in issued:
                        following=candidate;break
                if following is None:
                    with self.store.connect() as c:c.execute("UPDATE discovery_branches SET state='exhausted',reason='Formulazioni disponibili esplorate' WHERE campaign_id=? AND strategy=? AND region=?",(cid,b['strategy'],b['region']))
                    continue
                cursor+=1
            fp=self.offer_query(campaign,b['strategy'],following)
            if fp:
                with self.store.connect() as c:c.execute('UPDATE discovery_branches SET cursor=?,dry_streak=?,last_query=? WHERE campaign_id=? AND strategy=? AND region=?',(cursor,dry,fp,cid,b['strategy'],b['region']))
                added+=1;pending+=1
        return added
    def follow_company(self,campaign,payload,result):
        details=result.get('details',{});identity=details.get('identity',{})
        if details.get('company_ready'):
            from .company_research import research_tasks
            candidates,queries=research_tasks(payload,result)
            for child in candidates:
                self.funnel.offer(campaign['id'],'candidate',child['strategy'],child,'company-page:'+digest(child['url']))
            for query in queries:self.offer_query(campaign,query['strategy'],query)
            from .company_research import company_verification
            verification=company_verification(payload,result)
            if verification:
                self.funnel.offer(campaign['id'],'verify','companies',verification,'company-review:'+digest(verification['company_key']+verification.get('evidence_revision','')))
            return
        if result['state']!='promising' or identity.get('identity_status')!='verified' or payload.get('followup_depth',0)>=1:return
        host=domain(identity.get('website',''));doc=details.get('document',{})
        if not host or not doc.get('text'):return
        # Use terms actually observed in the original document, not LLM-invented facts.
        strategy=payload.get('strategy','change');pattern=PATTERNS.get(strategy)
        terms=re.search(pattern,doc['text'],re.I) if pattern else None
        if not terms:return
        query='site:'+host+' '+terms[0]+' '+('portale ordini' if strategy=='process' else 'progetto digitale')
        self.offer_query(campaign,strategy,{'query':query,'page':1,'period':'','region':identity.get('region'),'followup_depth':1,'company_host':host,'subject':identity['name'],'subject_quote':doc['text'][max(0,terms.start()-100):terms.end()+300],'source_documents':[doc],'official_link':True,'evidence_url':doc['url']})


# Compatibility for existing workers, tools and tests.
Planner = CommercialIntelligencePlanner
