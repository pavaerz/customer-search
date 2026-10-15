"""Frozen historical claim-type replay, independent of development company Almas.

This measures interpretation of literal quotations only. It is not prospect
Precision@20, acquisition quality or a benchmark of model extraction recall.
"""
import json,hashlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.claim_grounding import grounded_kind
from sales.research_rules import normalize
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'data/benchmarks50/grounding-evaluation.json';rows=json.loads(p.read_text())
# Reviewed after freezing the sample, without changing grounding rules on it.
# Index 9 describes a publication procedure in a digital portal (not inefficiency).
# Others describe manufacturing, marketing CTAs, generic problems or planned tools,
# and do not support their originally assigned request/process/gap type.
supported={9}
report={'scope':'Support for originally assigned need/request/digital-process type, not need for a full project.',
        'sampling':'First 20 unique quotations by SHA256(grounding-holdout-v1 + quotation hash); Almas, Picello and Stox excluded before sampling.',
        'sample_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':len(rows),'reviewer':'Development assistant, not an independent human reviewer',
        'rows':[],'results':{},'limits':['19 negative examples, only one supported process label: insufficient positive recall sample.','Publication procedure in a portal does not imply inefficiency or that the named entity owns it.','The evidence and entity linkage are not re-qualified by this classifier.','No new API requests or model calls; no claim of acquisition effectiveness.']}
for i,row in enumerate(rows):
    report['rows'].append({'url':row['url'],'quote':row['quote'],'original_type':row['kind'],'after_type':grounded_kind(row['kind'],row['quote']),
                           'original_type_supported':i in supported,'literal_in_original':normalize(row['quote']) in normalize(row['text'])})
for label in ('before','after'):
    retained=[r for r in report['rows'] if label=='before' or r['after_type']==r['original_type']]
    report['results'][label]={'retained':len(retained),'unsupported_retained':sum(not r['original_type_supported'] for r in retained),'supported_retained':sum(r['original_type_supported'] for r in retained),'supported_discarded':sum(r['original_type_supported'] and r not in retained for r in report['rows'])}
(ROOT/'docs/benchmark50-grounding.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report['results']))
