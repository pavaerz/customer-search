"""Replay original captures against a backed-up baseline; no search or model calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sales.company_investigation import linked_brand_solutions
from sales.research_analysis import identity_from


def run(backup,captures):
    old={'__package__':'sales'}
    with zipfile.ZipFile(backup/'project.zip') as archive:
        exec(compile(archive.read('sales/company_investigation.py'),'baseline','exec'),old)
    rows=[]
    for filename in sorted(captures.glob('*.json')):
        page=json.loads(filename.read_text());identity=identity_from([page])
        rows.append({'url':page['url'],'capture':str(filename.relative_to(ROOT)),
                     'sha256':hashlib.sha256(filename.read_bytes()).hexdigest(),
                     'identity_status':identity['identity_status'],
                     'before':old['linked_brand_solutions']([page],identity),
                     'after':linked_brand_solutions([page],identity)})
    if not rows:raise ValueError('No original captures found')
    report={'baseline_backup':str(backup.relative_to(ROOT)),
            'sample':'Pagine originali già raccolte: confronto di recupero link, non precisione commerciale. Tecnova è un caso di sviluppo.',
            'serper_requests':0,'pages':len(rows),
            'changes':[r for r in rows if r['before']!=r['after']],'rows':rows}
    (ROOT/'docs/regression50-linked-sites.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'pages':len(rows),'changed_pages':len(report['changes']),'serper_requests':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--captures',type=Path,required=True)
    args=parser.parse_args()
    run(args.backup.resolve(),args.captures.resolve())
