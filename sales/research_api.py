"""Read adapters for the existing CRM and the new research dossier."""
import json
from .research_store import ResearchStore

def annotate(store,items):
    with store.connect() as c:
        rows=c.execute('''SELECT a.*,e.company_id FROM research_assessments a JOIN research_entities e ON e.id=a.entity_id WHERE a.id=(SELECT max(b.id) FROM research_assessments b WHERE b.entity_id=a.entity_id AND coalesce(json_extract(b.body,'$.campaign_only'),0)=0) AND e.company_id IS NOT NULL''').fetchall()
    bycompany={r['company_id']:r for r in rows}
    for item in items:
        row=bycompany.get(item['company_id'])
        item['qualification']='legacy';item['qualification_label']='Non ancora validata con i criteri 4.0'
        if row:
            assessment=json.loads(row['body']);item['qualification']=row['status'];item['opportunity_id']=row['id'];item['research_assessment']=assessment
            item['qualification_label']={'qualified':'Qualificata 4.0','rejected':'Esclusa dalla shortlist','needs_review':'Da approfondire','unverifiable':'Non verificabile'}[row['status']]
            if row['status']=='qualified':
                item['score']=row['score'];item['reason']=assessment['why'];item['hypothesis']=assessment['proposal'];item['missing']=assessment['missing'];item['qualification_rejected']=False
    from .commercial.catalog import ENGINES
    with store.connect() as c:
        commercial={r['prospect_id']:r for r in c.execute('SELECT o.id,o.prospect_id,o.engine,r.state FROM commercial_opportunities o JOIN commercial_revisions r ON r.id=o.latest_revision WHERE o.prospect_id IS NOT NULL')}
    for item in items:
        if row:=commercial.get(item['id']):
            item.update(commercial_opportunity_id=row['id'],commercial_engine=row['engine'],qualification='commercial',qualification_label=ENGINES[row['engine']]+' · '+{'VERIFIED':'Collaborazione verificata','POTENTIAL':'Potenziale cliente','NEEDS_REVIEW':'Da verificare','REJECTED':'Scartata','UNVERIFIABLE':'Non verificabile'}[row['state']])
            item['qualification_rejected']=row['state'] in ('REJECTED','UNVERIFIABLE')
    # 6.0 records remain separate from historical qualification revisions.
    with store.connect() as c:
        agent={r['prospect_id']:r for r in c.execute("SELECT p.id prospect_id,r.id record_id,r.state FROM prospects p JOIN agent6_records r ON p.identity='agent6:'||r.request_key WHERE r.id=(SELECT max(x.id) FROM agent6_records x WHERE x.request_key=r.request_key)")}
    for item in items:
        if row:=agent.get(item['id']):
            item.update(agent6_record_id=row['record_id'],qualification='agent6',qualification_label='6.0 · '+row['state'],qualification_rejected=row['state'] in ('REJECTED','UNVERIFIABLE'))
    return items

def quality_report(store):
    from .research_quality import proposed_reviews,ranked_quality
    with store.connect() as c:
        rows=c.execute('''SELECT a.status,a.body,r.verdict FROM research_reviews r JOIN research_assessments a ON a.id=r.assessment_id WHERE r.id=(SELECT max(x.id) FROM research_reviews x WHERE x.assessment_id=r.assessment_id)''').fetchall()
    proposed=[r for r in rows if json.loads(r['body']).get('original_status',r['status'])=='qualified']
    confirmed=sum(r['verdict']=='confirmed' for r in proposed);false=sum(r['verdict']=='false_positive' for r in proposed)
    total=confirmed+false
    return {'reviewed':len(rows),'confirmed':confirmed,'false_positives':false,'missed':sum(r['verdict']=='missed_opportunity' for r in rows),'precision':round(100*confirmed/total,1) if total else None,'sufficient':total>=20,'note':'Revisione delle prove, non efficacia commerciale. Campione minimo: 20 opportunità proposte.',**ranked_quality(proposed_reviews(store))}

def commercial_feedback(store):
    """Descriptive cohorts. No inferred sends, attribution duplication or predictive model."""
    from .research_rules import STRATEGIES
    minimum=max(10,store.settings()['minimum_sample']);companies={};groups={k:{'strategy':k,'label':v,'contacted':0,'replied':0,'won':0} for k,v in STRATEGIES.items()}
    with store.connect() as c:
        rows=c.execute('SELECT a.body,e.company_id FROM research_assessments a JOIN research_entities e ON e.id=a.entity_id WHERE a.status=\'qualified\' AND e.company_id IS NOT NULL ORDER BY a.id').fetchall()
        for row in rows:
            cid=row['company_id']
            if cid in companies:continue
            strategy=json.loads(row['body']).get('strategy','change')
            events={r[0] for r in c.execute('SELECT i.kind FROM interactions i JOIN prospects p ON p.id=i.prospect_id WHERE p.company_id=?',(cid,))}
            companies[cid]={'strategy':strategy,'events':events}
        # Promising collaborations have no qualified assessment or CRM prospect.
        # Their manually recorded outcomes must still inform discovery. Merge
        # pages/campaigns with the same company and never infer that mail was sent.
        candidates=c.execute("""SELECT d.id,d.domain,d.strategy,co.id AS company_id
            FROM discovery_candidates d LEFT JOIN companies co ON co.domain=d.domain
            WHERE d.identity_status='verified' AND coalesce(d.domain,'')<>''
            AND coalesce(json_extract(d.details,'$.publisher'),0)=0
            AND EXISTS (SELECT 1 FROM commercial_outcomes o WHERE o.candidate_id=d.id)
            ORDER BY d.created_at,d.id""").fetchall()
        for row in candidates:
            key=row['company_id'] or 'domain:'+row['domain']
            entry=companies.setdefault(key,{'strategy':row['strategy'],'events':set()})
            events={r[0] for r in c.execute('SELECT kind FROM commercial_outcomes WHERE candidate_id=?',(row['id'],))}
            entry['events'].update(events)
            if events & {'negative_reply','positive_reply','conversation','quote'}:entry['events'].add('replied')
    for entry in companies.values():
        events=entry['events']
        if 'contacted' not in events:continue
        g=groups.get(entry['strategy'],groups['change'])
        for kind in ('contacted','replied','won'):g[kind]+=int(kind in events)
    for g in groups.values():
        g['sufficient']=g['contacted']>=minimum;g['reply_rate']=round(g['replied']/g['contacted']*100,1) if g['sufficient'] else None
    eligible=[g for g in groups.values() if g['sufficient']]
    return {'minimum_sample':minimum,'strategies':list(groups.values()),'preferred':max(eligible,key=lambda g:(g['won']/g['contacted'],g['replied']/g['contacted']))['strategy'] if len(eligible)>=2 and any(g['won'] or g['replied'] for g in eligible) else None,'note':'Priorità descrittive dagli esiti registrati; nessuna modifica ai requisiti e nessuna previsione di acquisizione.'}
