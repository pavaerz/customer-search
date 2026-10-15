"""Read-only full-row comparison of retained data against a verified backup."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sales.db import Store,now


def compare(backup,current):
    report={'checked_at':now(),'backup':str(backup),'tables':{},'excluded_tables':[]}
    with closing(sqlite3.connect('file:'+str(backup.resolve())+'?mode=ro',uri=True)) as before,closing(sqlite3.connect('file:'+str(current.resolve())+'?mode=ro',uri=True)) as after:
        names=[r[0] for r in before.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for name in names:
            if name in ('cache','api_usage','provider_usage','daily_usage','settings') or name.startswith('discovery_'):
                report['excluded_tables'].append(name);continue
            query='SELECT * FROM "'+name.replace('"','""')+'" ORDER BY rowid'
            a=before.execute(query).fetchall();b=after.execute(query).fetchall()
            report['tables'][name]={'rows_before':len(a),'rows_after':len(b),'unchanged':a==b}
        report['integrity']=after.execute('PRAGMA integrity_check').fetchone()[0]
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/preservation50-current.json')
    args=parser.parse_args()
    report=compare(args.backup,Store().path)
    args.output.write_text(json.dumps(report,indent=2))
    changed=[k for k,v in report['tables'].items() if not v['unchanged']]
    print(json.dumps({'tables_checked':len(report['tables']),'changed':changed,'integrity':report['integrity']}))
    sys.exit(1 if changed or report['integrity']!='ok' else 0)
