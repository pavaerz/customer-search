"""Real source-only discovery pilot. No search calls, no production CRM writes.

Use --replay to reprocess frozen original responses without any network access.
The catalog was selected during development; this is not an independent sales
precision benchmark. An offered article is neither a company nor a qualified lead.
"""
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,now,digest
from sales.research_store import ResearchStore
from sales.source_catalog import seed_business_sources
from sales.research_discovery import inspect_source
from sales.research_analysis import ResearchWeb

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'data/pilot50-source-mix'


def run(replay=False):
    DEST.mkdir(exist_ok=True,mode=0o700)
    temporary=tempfile.TemporaryDirectory(prefix='customersearch-source-replay-') if replay else None
    db=Path(temporary.name)/'replay.sqlite3' if replay else DEST/'sources.sqlite3'
    if db.exists():raise ValueError('Pilot DB already exists: preserve it; choose a new destination.')
    with closing(sqlite3.connect(ROOT/'data/sales.sqlite3')) as src,closing(sqlite3.connect(db)) as dst:
        src.backup(dst)
        dst.execute("UPDATE campaigns SET status='paused',worker_pid=NULL WHERE status IN ('running','waiting','stopping')");dst.commit()
    os.chmod(db,0o600)
    store=Store(db);store.init();rs=ResearchStore(store)
    campaign=rs.create({'target':'b2b','regions':['Veneto','Lombardia','Piemonte','Toscana'],'projects':['website'],'groups':['direct']})
    pages=json.loads((DEST/'source-captures.json').read_text()) if replay else {}
    original=ResearchWeb.get
    def capture(web,url,refresh=False):
        if replay:
            if url not in pages:raise ValueError('Missing frozen response: '+url)
            return pages[url]
        page=original(web,url,refresh);pages[url]=page
        (DEST/'source-captures.json').write_text(json.dumps(pages,ensure_ascii=False))
        return page
    report={'started_at':now(),'split':'development','replay':replay,'serper_requests':0,'sources':[]}
    if replay:
        # Replay the recorded plan, even if a source was later suspended after
        # examining its articles. Do not silently compare a different catalog.
        saved=json.loads((DEST/'source-report.json').read_text())
        plan=saved.get('source_plan')
        if plan is None:
            with closing(sqlite3.connect(f'file:{DEST / "sources.sqlite3"}?mode=ro',uri=True)) as c:
                plan=[json.loads(r[0]) for r in c.execute("SELECT payload FROM discovery_frontier WHERE campaign_id=(SELECT max(id) FROM campaigns) AND kind='source' AND coalesce(json_extract(payload,'$.depth'),0)=0 ORDER BY id")]
        tasks=[{'payload':json.dumps(payload)} for payload in plan]
    else:
        seed_business_sources(rs,campaign)
        with store.connect() as c:tasks=[dict(r) for r in c.execute("SELECT * FROM discovery_frontier WHERE campaign_id=? AND kind='source'",(campaign['id'],))]
    report['source_plan']=[json.loads(t['payload']) for t in tasks]
    with patch.object(ResearchWeb,'get',capture):
        for task in tasks:
            task['payload']=json.loads(task['payload']);row={'url':task['payload']['url'],'region':task['payload']['region']}
            try:inspect_source(rs,campaign,task,lambda:None);row['status']='read'
            except Exception as exc:row.update(status='unavailable',reason=str(exc))
            report['sources'].append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    with store.connect() as c:
        report['candidates']=[json.loads(r[0]) for r in c.execute("SELECT payload FROM discovery_frontier WHERE campaign_id=? AND kind='candidate'",(campaign['id'],))]
        report['events']=[dict(r) for r in c.execute("SELECT kind,message,url,details FROM research_events WHERE campaign_id=?",(campaign['id'],))]
    report.update(finished_at=now(),pages_captured=len(pages),qualified=None,
                  limitation='Source discovery only. Candidates require original article and company verification; no precision or sales efficacy claim.',
                  capture_hashes={u:digest(p['html']) for u,p in pages.items()})
    rs.stop(campaign['id']);rs.paused(campaign['id'])
    name='source-replay.json' if replay else 'source-report.json'
    (DEST/name).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'articles_offered':len(report['candidates']),'source_pages':len(pages),'serper_requests':0}),flush=True)
    if temporary:temporary.cleanup()


if __name__=='__main__':run('--replay' in sys.argv)
