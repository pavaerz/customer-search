"""Offline before/after query-order comparison. Never dispatches searches."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sales.company_research import PROFILES,company_queries
from sales.commercial_planner import EVENTS,queries
from sales.research_rules import ALLOWED_REGIONS


def run(backup):
    baseline={};hashes={}
    with zipfile.ZipFile(backup/'project.zip') as archive:
        for module in ('commercial_planner','company_research'):
            source=archive.read('sales/'+module+'.py')
            namespace={'__package__':'sales','__name__':'sales.baseline_'+module}
            exec(compile(source,module,'exec'),namespace)
            baseline[module]=namespace;hashes[module]=hashlib.sha256(source).hexdigest()
    comparisons=[]
    for profile in PROFILES:
        for region in ALLOWED_REGIONS:
            for strategy in ('companies',*EVENTS):
                if strategy=='companies':
                    before=list(baseline['company_research']['company_queries'](region,profile))
                    after=list(company_queries(region,profile))
                else:
                    before=list(baseline['commercial_planner']['queries'](strategy,region,profile))
                    after=list(queries(strategy,region,profile))
                assert set(before)==set(after),(profile,region,strategy)
                comparisons.append({'profile':profile,'region':region,'strategy':strategy,'queries':len(after),'same_query_set':True})
    before=list(baseline['commercial_planner']['queries']('change','Veneto','b2b'))[:8]
    after=list(queries('change','Veneto','b2b'))[:8]
    sectors=lambda values:sorted({s for s in PROFILES['b2b'][1] for q in values if q.startswith(s+' ')})
    report={'baseline_backup':str(backup.relative_to(ROOT)),'baseline_sha256':hashes,
            'search_requests':0,'model_calls':0,'comparisons':comparisons,
            'first_eight_change_queries':{'before':before,'after':after,'sectors_before':sectors(before),'sectors_after':sectors(after)},
            'limitation':'Misura della diversificazione delle query, non della pertinenza dei risultati o dell’efficacia commerciale.'}
    (ROOT/'docs/regression50-query-diversity.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'query_sets_preserved':len(comparisons),'sectors_before':len(sectors(before)),'sectors_after':len(sectors(after)),'search_requests':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--backup',type=Path,required=True)
    run(parser.parse_args().backup.resolve())
