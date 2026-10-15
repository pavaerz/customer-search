"""Local development probe for a focused existing-solution check, no web calls."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.compare50_local_models import cases
from sales.db import Store,now,digest
from sales.research_analysis import LocalResearcher
from sales.claim_selection import grounded_units
from sales.solution_evidence import TASK,schema,materialize_solutions,eligible_units
from sales.research_rules import validate_signals

ROOT=Path(__file__).resolve().parents[1]


def development_cases():
    corpus=cases()
    for case in corpus:case['expect_solution']=case['id']=='completed_site'
    for key,text,expected in [
        ('future_site','Il nostro nuovo sito web sarà disponibile il mese prossimo. Stiamo ancora cercando un fornitore per completare il progetto.',False),
        ('supplier_service','Realizziamo siti web completi per i nostri clienti. Contattaci per un preventivo personalizzato.',False),
        ('operating_shop','Il nostro negozio online è già operativo e consente di acquistare tutti i prodotti del marchio.',True),
        ('broken_site','Il nostro sito web non è disponibile. Il portale attuale non funziona e non consente di inviare ordini.',False),
    ]:
        corpus.append({'id':key,'company':'Esempio Srl','split':'synthetic control',
            'expect_solution':expected,'document':{'id':digest(text),'text':text,'research_text':text,
                'url':'https://example.invalid/'+key,'checked_at':now(),'official':True}})
    return corpus


def run(corpus=None,report_name='probe50-solutions.json'):
    corpus=development_cases() if corpus is None else corpus
    dest=ROOT/'data/solution-probe'/now().replace(':','-');dest.mkdir(parents=True,mode=0o700)
    store=Store(dest/'probe.sqlite3');store.init();store.configure({'ollama_model':'qwen2.5:7b'})
    report={'started_at':now(),'directory':str(dest.relative_to(ROOT)),'task':TASK,'results':[],
            'selection_mode':'Same eligible spans as the application; no inference when none match.',
            'limitation':'Development check of evidence retrieval, not commercial qualification or independent precision.',
            'search_requests':0,'web_requests':0}
    (dest/'inputs.json').write_text(json.dumps(corpus,ensure_ascii=False,indent=2))
    for case in corpus:
        d=case['document'];text=d['research_text'];assert len(text)<=9500
        units=eligible_units(grounded_units(d['id'],text,d['text']));start=time.monotonic()
        item={'case':case['id'],'expected':case['expect_solution'],'eligible_units':[u['id'] for u in units]}
        try:
            response=LocalResearcher(store).call(TASK,{'document_id':d['id'],'company':case['company'],'url':d['url'],
                 'units':[{'id':u['id'],'text':u['text']} for u in units]},schema(units)) if units else {'existing_solution_ids':[]}
            claims,errors=materialize_solutions(d['id'],text,units,response)
            signals,invalid=validate_signals(claims,[d]);errors+=invalid
            selected=[s for s in signals if s['kind']=='counterevidence']
            item.update(response=response,claims=claims,signals=signals,errors=errors,
                        passed=bool(selected)==case['expect_solution'] and not errors)
        except Exception as exc:item.update(error=str(exc),passed=False)
        item['seconds']=round(time.monotonic()-start,2);report['results'].append(item)
        (dest/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({k:v for k,v in item.items() if k not in ('claims','response')},ensure_ascii=False),flush=True)
    report['finished_at']=now()
    (dest/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (ROOT/'docs'/report_name).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(dest,flush=True)


if __name__=='__main__':run()
