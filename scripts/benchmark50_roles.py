"""Replay only publisher identification on frozen original HTML; no API/model calls."""
import json,re,sys,hashlib,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.extract import parse_page,nodes,types
from sales.research_analysis import text_with_legal
from sales.db import domain
from sales.source_roles import publisher_identity
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'data/benchmarks50/source-role-evaluation.json'
with zipfile.ZipFile(ROOT/'data/backups/20261014T071804567249Z/project.zip') as z:
    code=z.read('sales/research_triage.py').decode()
# Exact historical expression, read from the verified baseline rather than hand-reimplemented.
pattern=re.search(r'PUBLISHER=re.compile\((.+)\)',code)[1]
PUBLISHER=eval('re.compile('+pattern+')',{'re':re,'__builtins__':{}})
expression=next(l.strip().split('publisher=',1)[1] for l in code.splitlines() if l.strip().startswith('publisher=bool('))
sample=json.loads(source.read_text())
companies={0,3,6,7,8,9,10,12,13,16,19};unrelated={4,11}
rows=[]
for n,item in enumerate(sample):
    page=item['page'];parsed=parse_page(page)
    before=eval(expression,{'__builtins__':{},'bool':bool,'any':any,'str':str,'types':types,'nodes':nodes,'PUBLISHER':PUBLISHER,'domain':domain,'text_with_legal':text_with_legal,'payload':{},'parsed':parsed,'page':page})
    after=publisher_identity(page)
    rows.append({'url':item['url'],'reviewed_role':'company' if n in companies else 'unrelated' if n in unrelated else 'publisher_or_public_source','before_publisher':before,'after_publisher':after})
report={'scope':'Publisher identity only, not qualification or buying intent. Sources include blogs and public institutions. False means not identified as publisher, not verified company.',
        'sample_selection':'First 20 domains by SHA256(source-role-evaluation-v1 + domain) from 143 cached historical domains. Five development domains excluded before sampling.',
        'sample_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'baseline_sha256':hashlib.sha256(code.encode()).hexdigest(),
        'sample_size':len(rows),'businesses':len(companies),'public_sources':len(rows)-len(companies)-len(unrelated),'rows':rows,'results':{}}
for label in ('before','after'):
    report['results'][label]={'companies_wrongly_flagged_as_publishers':sum(r[label+'_publisher'] for r in rows if r['reviewed_role']=='company'),
                             'public_sources_recognized':sum(r[label+'_publisher'] for r in rows if r['reviewed_role']=='publisher_or_public_source'),
                             'qualified_opportunities':None,'precision_at_10':None,'precision_at_20':None,'api_requests':0}
report['limits']=['Role labels reviewed by the development assistant from the frozen originals, not an independent human reviewer.','This tests a narrow classifier; missing publisher recognition and unknown identity must still be caught downstream.','No commercial precision or conversion claim; qualification not run.']
(ROOT/'docs/benchmark50-roles.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report['results']))
