"""Replay a captured event investigation without search or production CRM writes."""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sales.db import Store,now
from sales.research_analysis import LocalResearcher
from sales.research_rules import qualify


if __name__=='__main__':
    meta=json.loads((ROOT/'docs/pilot50-event-plan.json').read_text())
    folder=ROOT/meta['directory']
    original=json.loads((folder/'deep.json').read_text())['result']
    store=Store(folder/'pilot.sqlite3');started=time.monotonic()
    signals,proposal,review,limits=LocalResearcher(store,progress=lambda m:print(m,flush=True)).analyze(original['identity'],original['documents'],original['assessment']['coverage'])
    assessment=qualify(original['identity'],original['documents'],signals,proposal,review,limits=limits,strategy='companies')
    report={'scope':'Development replay on the same captured pages, not independent evaluation',
            'checked_at':now(),'company':original['identity']['name'],
            'before_status':original['assessment']['status'],'after_status':assessment['status'],
            'limits':limits,'context_selection':review.get('context_selection'),'assessment':assessment,
            'api_requests':0,'seconds':round(time.monotonic()-started,2)}
    (ROOT/'docs/pilot50-event-recheck.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='assessment'},ensure_ascii=False))
