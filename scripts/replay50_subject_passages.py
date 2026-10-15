"""Re-evaluate the frozen Plastica LG investigation with full named passages.

No search calls or external HTTP. The only live service used is local Ollama;
all web pages must exist in the original capture. Development regression only.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store,now
from sales.research_analysis import ResearchWeb,inspect_candidate,document
from sales.research_triage import triage
from sales.company_research import company_verification

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/pilot50-source-mix'

def run():
    baseline=json.loads((DATA/'plastica-recheck.json').read_text())
    pages=json.loads((DATA/'plastica-pages.json').read_text())
    articles=json.loads((DATA/'article-pages.json').read_text())
    payload=baseline['resolved']['discovered'][0].copy()
    payload['source_documents']=[document(articles[d['url']],d['provider']) for d in payload['source_documents']]
    payload.update(company_stage='identify',strategy='companies',region='Piemonte')
    store=Store(DATA/'sources.sqlite3')
    def frozen(web,url,refresh=False):
        if url not in pages:raise ValueError('Missing frozen response: '+url)
        return pages[url]
    report={'started_at':now(),'scope':'development frozen replay; not independent commercial precision','serper_requests':0}
    with patch.object(ResearchWeb,'get',frozen):
        triaged=triage(store,payload,lambda:None)
        report['triage']=triaged
        verification=company_verification(payload,triaged)
        if verification:
            report['investigation']=inspect_candidate(store,verification,lambda:None,lambda msg:print(msg,flush=True))
    report['finished_at']=now()
    (DATA/'subject-passages-recheck.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    before=baseline['investigation'];after=report['investigation']
    def result(r):
        external=[d for d in r['documents'] if not d['official']]
        return {'state':r['assessment']['status'],'project':r['assessment']['project'],'budget':r['assessment']['budget'],
                'editorial_characters':sum(len(d['research_text']) for d in external),
                'passages':sum(len(d.get('subject_passages',[])) for d in external),
                'editorial_signals':[s for s in r['assessment']['signals'] if not s['official']]}
    comparison={'before':result(before),'after':result(after),'serper_requests':0,'independent_precision':None}
    (ROOT/'docs/regression50-subject-passages.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2))
    print(json.dumps({k:{field:value for field,value in v.items() if field!='editorial_signals'} for k,v in comparison.items() if isinstance(v,dict)},ensure_ascii=False),flush=True)

if __name__=='__main__':run()
