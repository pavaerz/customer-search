"""Offline comparison against frozen Phase-2.1 decisions; no database or HTTP."""
import gzip,json
from pathlib import Path
from sales.commercial.discovery import assess,followup_allowed

def main():
    with gzip.open(Path(__file__).resolve().parents[1]/'tests/fixtures/commercial3a/campaign12.json.gz','rt') as f:fixture=json.load(f)
    rows=[]
    for r in fixture['results']:
        p=r['item'];decision=assess(p,r['engine'],p.get('origin',{}))
        after=followup_allowed(r['saved_parent'],{**p.get('origin',{}),'url':p['url']}) if p.get('depth') and r.get('saved_parent') else None if p.get('depth') else decision['decision']=='admit'
        rows.append({'task':r['task_id'],'url':p['url'],'scope':'followup' if p.get('depth') else 'discovery','before':r['phase21_admitted'],'after':after,'reason':decision['reason']})
    report={'scope':'Frozen campaign12 sample; offline rule comparison, not market precision or online discovery','rows':rows}
    for kind in ('discovery','followup'):
        subset=[r for r in rows if r['scope']==kind and r['after'] is not None]
        report[kind]={'n':len(subset),'before_admitted':sum(r['before'] for r in subset),'after_admitted':sum(r['after'] for r in subset)}
    Path('implementation-report/phase-3a-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print({k:v for k,v in report.items() if k!='rows'})

if __name__=='__main__':main()
