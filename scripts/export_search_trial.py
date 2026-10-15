"""Export the latest measured trial, with no keys or full page bodies."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store
from sales.search_trial import state

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('docs/serper-live-pilot.json'));args=parser.parse_args()
    report=state(Store())
    if not report['run']:raise SystemExit('Nessuna prova eseguita')
    report.pop('configured',None)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'path':str(args.output),'state':report['run']['state'],'requests':report['used'],'metrics':report['run']['metrics']},ensure_ascii=False))
