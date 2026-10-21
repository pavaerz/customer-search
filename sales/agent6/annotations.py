"""Append-only human corrections, separate from machine evidence and CRM state."""
import json
from sales.db import now,encode
from .commercial_view import TYPES

FIELDS={'opportunity_type':set(TYPES),'priority':{'high','medium','low'},
        'relevance':{'relevant','irrelevant','uncertain'},'commercial_fit':{'high','medium','low','unknown'}}


def migrate(c):
    c.execute('CREATE TABLE IF NOT EXISTS agent8_annotations(id INTEGER PRIMARY KEY,record_id INTEGER NOT NULL,changes TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL)')
    c.execute('CREATE INDEX IF NOT EXISTS agent8_annotations_record ON agent8_annotations(record_id,id)')
    c.execute('INSERT OR IGNORE INTO research_schema VALUES (800,?)',(now(),))


def save(store,rid,changes,note):
    if not isinstance(changes,dict) or not changes or set(changes)-set(FIELDS):raise ValueError('Correzioni non valide')
    for key,value in changes.items():
        if value is not None and (not isinstance(value,str) or value not in FIELDS[key]):raise ValueError('Valore di correzione non valido')
    if not isinstance(note,str) or not note.strip() or len(note)>2000:raise ValueError('Descrivi il motivo della correzione (massimo 2000 caratteri).')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM agent6_records WHERE id=?',(rid,)).fetchone():raise ValueError('Scheda non trovata')
        c.execute('INSERT INTO agent8_annotations(record_id,changes,note,created_at) VALUES (?,?,?,?)',(rid,encode(changes),note.strip(),now()))
    return {'saved':True,'action':'manual_correction_only_no_promotion_or_message'}


def read(store):
    with store.connect() as c:
        # Read-only access remains compatible with a backend not migrated yet.
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='agent8_annotations'").fetchone():return []
        return [{**dict(r),'changes':json.loads(r['changes']),'body':json.loads(r['body'])} for r in c.execute('SELECT a.*,r.request_key,r.flow,r.campaign_id,r.body FROM agent8_annotations a JOIN agent6_records r ON r.id=a.record_id ORDER BY a.id')]


def latest(rows):
    out={}
    for row in rows:
        current=out.setdefault(row['request_key'],{})
        for field,value in row['changes'].items():
            if value is None:current.pop(field,None)
            else:current[field]={'value':value,'note':row['note'],'created_at':row['created_at'],'annotation_id':row['id'],'record_id':row['record_id']}
    return out


def apply(body,corrections):
    # Explicitly expose both interpretations; a human label cannot turn a
    # source into proof or invent demand/identity/budget/currentness.
    b={**body,'manual_corrections':corrections}
    b['automatic_opportunity_type']=body.get('opportunity_type')
    b['automatic_priority']=body.get('priority')
    for field in ('opportunity_type','priority','relevance','commercial_fit'):
        if field in corrections:b[field]=corrections[field]['value']
    if 'opportunity_type' in corrections:b['opportunity_type_label']=TYPES[b['opportunity_type']]+' · indicato da te'
    return b


def learning(rows):
    """One current relevance decision per request, inspectable denominators."""
    from .learning import strategy_id
    values=latest(rows);records={r['request_key']:r for r in rows};groups={}
    for request,fields in values.items():
        row=records[request];b=row['body']
        if not b.get('query'):continue
        family=strategy_id(b['query'],row['flow'])
        group=groups.setdefault(family,{'strategy_id':family,'reviewed_requests':0,'relevant':0,'irrelevant':0,'uncertain':0,'annotation_ids':[]})
        if 'relevance' not in fields:continue
        f=fields['relevance'];group['reviewed_requests']+=1;group[f['value']]+=1;group['annotation_ids'].append(f['annotation_id'])
    for g in groups.values():
        g['sample_sufficient']=g['reviewed_requests']>=3
        g['priority_adjustment']=round((g['relevant']-g['irrelevant'])/g['reviewed_requests'],3) if g['sample_sufficient'] else 0
        g['basis']='manual_relevance_per_distinct_request_not_conversion_prediction'
    return list(groups.values())
