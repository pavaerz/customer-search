"""Offline campaign-13 replay. Frozen observations and synthetic plans stay separate.

No provider invocation, source reading or qualification is performed. SQLite
writes are confined to automatically removed temporary databases.
"""
import gzip
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import Mock

from sales.db import Store
from sales.research_store import ResearchStore
from sales.commercial.catalog import ENGINES, query_source
from sales.commercial.coordinator import Coordinator
from sales.commercial.discovery import assess, followup_allowed

ROOT=Path(__file__).resolve().parents[1]


def counts(items):
    return dict(sorted(Counter(items).items()))


def query_counts(rows):
    return {engine:{'queries':len(part), 'families':counts(r['family'] for r in part),
                    'sources':counts(query_source(r['query']) for r in part),
                    'regions':counts(r['region'] for r in part)}
            for engine in ENGINES for part in [[r for r in rows if r['engine']==engine]]}


def temporary_coordinator(directory):
    store=Store(Path(directory)/'replay.sqlite3');store.init()
    rs=ResearchStore(store)
    campaign=rs.create({'commercial_engines':list(ENGINES),'mode':'pilot'})
    worker=Coordinator(store,campaign);worker.initialize()
    return store,rs,campaign,worker


def planning():
    """Three empty mocked result pages per engine, not a new discovery run."""
    with tempfile.TemporaryDirectory(prefix='customersearch31-plan-') as tmp:
        store,rs,campaign,worker=temporary_coordinator(tmp)
        empty_provider=Mock(return_value=[]);rows=[]
        for turn in range(3):
            worker.tick()
            with store.connect() as db:
                tasks=[dict(r) for r in db.execute("SELECT * FROM research_tasks WHERE kind='search' AND state='pending' ORDER BY id")]
            for task in tasks:
                task['payload']=json.loads(task['payload']);p=task['payload']
                rows.append({'turn':turn+1,'engine':task['strategy'],**{k:p[k] for k in ('query','family','source','region','intent')}})
                worker.receive(task,empty_provider(p),lambda:None)
                rs.task_done(task['id'])
        worker.tick()
        with store.connect() as db:
            limits=[dict(r) for r in db.execute('SELECT engine,state,error FROM commercial_engine_runs ORDER BY engine')]
            resources=[dict(r) for r in db.execute('SELECT engine,resource,used FROM commercial_resources ORDER BY engine,resource')]
        assert len(rows)==12
        assert all(len({r['family'] for r in rows if r['engine']==e})==3 for e in ENGINES)
        assert {r['source'] for r in rows if r['engine']=='FREELANCE'}=={'web','instagram','linkedin'}
        return {'scope':'Synthetic scheduling only: mocked empty results. No LinkedIn or other new URL observed.',
                'queries':rows,'by_engine':query_counts(rows),'mock_calls':empty_provider.call_count,
                'real_provider_calls':0,'qualification_count':0,'limits_after_fourth_tick':limits,'resources':resources}


def receipt_replay(fixture,rows):
    """Replay the 98 known direct appearances through the actual receipt path."""
    by_query=defaultdict(list)
    for row in rows:
        by_query[(row['engine'],row['query'])].append(row['body'])
    tasks=sorted((r for r in fixture['tasks'] if r['kind']=='search'),key=lambda r:r['id'])
    with tempfile.TemporaryDirectory(prefix='customersearch31-receipts-') as tmp:
        store,rs,campaign,worker=temporary_coordinator(tmp)
        for previous in tasks:
            p=previous['payload'];engine=previous['strategy']
            worker.enqueue('search',engine,p,'replay-query:'+str(previous['id']))
            with store.connect() as db:
                task=dict(db.execute("SELECT * FROM research_tasks WHERE fingerprint=?",('replay-query:'+str(previous['id']),)).fetchone())
            task['payload']=json.loads(task['payload'])
            worker.receive(task,by_query[(engine,p['query'])],lambda:None)
            rs.task_done(task['id'])
        with store.connect() as db:
            records=[json.loads(r[0]) for r in db.execute('SELECT body FROM commercial_discovery ORDER BY id')]
            candidate_counts={r[0]:r[1] for r in db.execute("SELECT strategy,count(*) FROM research_tasks WHERE kind='candidate' GROUP BY strategy")}
            resources=[dict(r) for r in db.execute('SELECT engine,resource,used FROM commercial_resources ORDER BY engine,resource')]
        assert len(records)==len(rows)==98
        assert len({r['appearance_id'] for r in records})==98
        grouped=counts(r['decision'] for r in records)
        assert sum(grouped.values())==98
        return {'scope':'Actual receipt/queue code on 98 frozen direct appearances; empty commercial memory, Pilot candidate cap 15 per engine. No source downloaded.',
                'received':98,'traced':len(records),'decisions':grouped,'reasons':counts(r['reason'] for r in records),
                'candidates_queued':candidate_counts,'resources':resources,'reconciled':True,
                'missing_historical_appearances':2,'missing_urls_known':False,
                'qualification_and_browser_rerun':False}


def main():
    with gzip.open(ROOT/'tests/fixtures/commercial31/campaign13.json.gz','rt') as f:fixture=json.load(f)
    direct=[r for r in fixture['discovery'] if not r['body'].get('origin',{}).get('parent_task')]
    followups=[r for r in fixture['discovery'] if r not in direct]
    assert (len(direct),len(followups))==(98,2)
    observed_queries=[{'engine':t['strategy'],**{k:t['payload'][k] for k in ('query','family','region')}} for t in fixture['tasks'] if t['kind']=='search']
    observed_queries.sort(key=lambda r:(list(ENGINES).index(r['engine']),r['region']))
    before_revisions=[r['body'] for r in fixture['revisions']]
    compared=[]
    for row in fixture['discovery']:
        item=row['body'];after=assess(item,row['engine'],item.get('origin'))
        follow=bool(item.get('origin',{}).get('parent_task'));allowed=True
        if follow:
            origin=item['origin'];parent=next((r for r in before_revisions if r['url']==origin['parent'] and r['engine']==row['engine']),None)
            parent_hint=next((r for r in direct if r['url']==origin['parent'] and r['engine']==row['engine']),None)
            allowed=bool(parent and followup_allowed(parent,origin))
            if parent_hint and assess(parent_hint['body'],row['engine'],parent_hint['body']['origin'])['decision']=='exclude':allowed=False
        compared.append({'id':row['id'],'engine':row['engine'],'scope':'followup' if follow else 'direct','url':row['url'],
                         'before_decision':row['decision'],'before_reason':item['reason'],
                         'after_filter_decision':after['decision'],'after_reason':after['reason'],
                         'before_priority':item.get('priority',0),'after_priority':after['priority'],
                         'intent':after.get('commercial_intent',{}).get('intent'),
                         'parent_path_allowed':allowed if follow else None})
    sources=[]
    for scope in ('direct','followup'):
        part=[r for r in compared if r['scope']==scope]
        sources.append({'scope':scope,'appearances':len(part),'before_decisions':counts(r['before_decision'] for r in part),
                        'after_filter_decisions':counts(r['after_filter_decision'] for r in part),
                        'after_allowed_parent_paths':sum(r['parent_path_allowed'] for r in part) if scope=='followup' else None,
                        'before_prelim_relevant':sum(r['before_decision']=='admit' and r['before_priority']>=55 for r in part),
                        'after_prelim_relevant':sum(r['after_filter_decision']=='admit' and r['after_priority']>=55 for r in part),
                        'new_exclusions':sum(r['before_decision']=='admit' and r['after_filter_decision']=='exclude' for r in part)})
    operations=[r for r in fixture['operations'] if r['kind']=='search' and r['provider']=='serper']
    observed={'provider_appearances':sum(r['details'].get('returned_urls',0) for r in operations),
              'direct_traces':len(direct),'followup_traces':len(followups),'untraced_direct_appearances':2,
              'queries':observed_queries,'query_distribution':query_counts(observed_queries),
              'candidate_tasks':counts(t['strategy'] for t in fixture['tasks'] if t['kind']=='candidate'),
              'candidate_task_states':counts(t['state'] for t in fixture['tasks'] if t['kind']=='candidate'),
              'qualifications':counts(r['state'] for r in before_revisions),
              'by_engine':{e:counts(r['state'] for r in before_revisions if r['engine']==e) for e in ENGINES},
              'unverifiable':sum(r['state']=='UNVERIFIABLE' for r in before_revisions),
              'social_unverifiable':sum(r['state']=='UNVERIFIABLE' and 'instagram.com' in r['url'] for r in before_revisions),
              'browser_attempted':sum(bool(r.get('browser')) for r in before_revisions),
              'browser_completed':sum(bool(r.get('browser',{}).get('completed')) for r in before_revisions),
              'browser_outcomes':counts(r.get('browser_outcome','unknown') for r in before_revisions if r.get('browser')),
              'serper_calls':len(operations),'serper_credits_estimated':sum(r['details'].get('credits_estimated',0) for r in operations),
              'serper_credits_actual':None,'resources':fixture['resources']}
    report={'scope':'Offline frozen campaign-13 replay; filter changes and synthetic planning are not market precision, new opportunities or observed LinkedIn results.',
            'historical_observations_unchanged':observed,'filter_comparison':sources,
            'filter_comparison_note':'Independent prefilter output does not reproduce memory, deduplication or qualification. Receipt replay below applies queue/budget/deduplication.',
            'decisions':compared,'receipt_replay':receipt_replay(fixture,direct),'synthetic_planner':planning(),
            'limits':['The two missing historical appearances have no saved direct trace and are not reconstructed or replaced.',
                      'No saved site is revisited. Browser timeout observations remain 2 attempts / 0 complete; browser repairs require separate local-server tests.',
                      'No new qualification or accessibility outcome is inferred from the filter replay.',
                      'Original campaign/resources/qualifications remain unchanged; all executable queue/planner tests use temporary databases.']}
    output=ROOT/'implementation-report/phase-3a1-replay.json';output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'filter_comparison':sources,'receipt_replay':report['receipt_replay'],'synthetic_planner_by_engine':report['synthetic_planner']['by_engine']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
