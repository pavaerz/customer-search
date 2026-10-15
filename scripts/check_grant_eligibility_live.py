"""Real official-source comparison on an isolated database; no applications sent."""
import sys,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.db import Store
from sales.grants import DEFAULT
from sales.grant_documents import GrantWeb,collect
from sales.grant_eligibility import explicit_exclusions,evaluate,GrantAnalyst
from sales.db import now

def run():
 with tempfile.TemporaryDirectory() as temp:
  store=Store(Path(temp)/'pilot.db');store.init();web=GrantWeb(store)
  page=web.get('https://www.invitalia.it/incentivi-e-strumenti/ON-nuove-imprese-tasso-zero',refresh=True)
  docs,limits=collect(web,page)
  b={'documents':docs,'rules':explicit_exclusions(docs),'complete':False,'limitations':limits}
  ev=evaluate(b,{**DEFAULT,'legal_form':'sole_trader','tax_regime':'forfettario'})
  report={'real_source_case':{'status':ev['status'],'reason':ev['reason'],'checked_at':ev['checked_at'],'documents':len(docs),'exclusions':[c for c in ev['checks'] if c['result']=='fail'],'limitations':limits},'model_fixture':None}
  # A synthetic fully bounded rule checks the real local extraction/reviewer,
  # separate from the live-source case and explicitly labelled as synthetic.
  fixture={'id':'model-fixture','url':'https://www.invitalia.it/test-fixture','title':'Test sintetico del confronto','text':'Bando sintetico di collaudo, non un incentivo reale. Requisiti integrali: possono partecipare esclusivamente le ditte individuali con sede in Veneto. Non sono previsti altri requisiti né allegati. Stato incentivo o strumento\nAttivo','checked_at':now()}
  try:
   extracted=GrantAnalyst(store).extract([fixture]);result=evaluate({**extracted,'documents':[fixture]},{**DEFAULT,'legal_form':'sole_trader'})
   report['model_fixture']={'status':result['status'],'rules':extracted['rules'],'complete':extracted['complete'],'limitations':extracted['limitations']}
  except Exception as exc:report['model_fixture']={'error':str(exc)}
  Path('docs/grant-eligibility-pilot.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':run()
