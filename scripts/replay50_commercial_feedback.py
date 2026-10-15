"""Frozen Remor replay before/after: no HTTP, Serper or production CRM writes."""
import argparse
import json
from pathlib import Path
import sys
import types
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sales.db import Store,now
from sales.research_analysis import LocalResearcher
from sales.research_rules import qualify


def archived_module(archive,path,name):
    module=types.ModuleType('sales.'+name)
    module.__package__='sales'
    exec(compile(archive.read(path),str(path),'exec'),module.__dict__)
    return module


def run(backup):
    metadata=json.loads((ROOT/'docs/pilot50-event-plan.json').read_text())
    folder=ROOT/metadata['directory']
    frozen=json.loads((folder/'deep.json').read_text())['result']
    store=Store(folder/'pilot.sqlite3')
    with zipfile.ZipFile(backup/'project.zip') as archive:
        old_analysis=archived_module(archive,'sales/research_analysis.py','feedback_before_analysis')
        old_rules=archived_module(archive,'sales/research_rules.py','feedback_before_rules')
    results={}
    for version,model,rules in [('before',old_analysis.LocalResearcher,old_rules.qualify),('after',LocalResearcher,qualify)]:
        with patch('sales.research_analysis.api_json',side_effect=AssertionError('Replay must use cached evidence/model output')),patch.object(old_analysis,'api_json',side_effect=AssertionError('No network in baseline')):
            signals,proposal,review,limits=model(store).analyze(frozen['identity'],frozen['documents'],frozen['assessment']['coverage'])
        assessment=rules(frozen['identity'],frozen['documents'],signals,proposal,review,limits=limits)
        results[version]={'status':assessment['status'],'limits':limits,'next_action':assessment['next_action'],
                          'reason':assessment['reasons'],'qualified':assessment['status']=='qualified',
                          'signal_count':len(signals),'budget':assessment['budget']}
    report={'checked_at':now(),'scope':'Development replay on a previously inspected company. Not an independent quality benchmark.',
            'backup':str(backup),'company':frozen['identity']['name'],
            'source_urls':[d['url'] for d in frozen['documents']],
            'api_requests':0,'model_network_requests':0,'results':results}
    (ROOT/'docs/regression50-commercial-feedback.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup',type=Path)
    run(parser.parse_args().backup)
