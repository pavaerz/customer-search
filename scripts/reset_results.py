"""Run only on explicit user request, with the HTTP server stopped and a verified backup."""
import argparse,hashlib,json,sys,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store
from sales.workspace import reset_results

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--backup',required=True,type=Path);args=parser.parse_args()
    manifest=json.loads((args.backup/'manifest.json').read_text());saved=args.backup/'sales.sqlite3'
    assert hashlib.sha256(saved.read_bytes()).hexdigest()==manifest['files']['sales.sqlite3'],'Backup non verificato'
    with sqlite3.connect(saved) as c:assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    print(json.dumps(reset_results(Store(),args.backup.resolve()),indent=2))
if __name__=='__main__':main()
