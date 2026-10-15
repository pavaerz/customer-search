"""4.1 browser checks against isolated discovery fixtures."""
import json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from sales import server
from sales.db import Store,now
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.research_strategies import STRATEGIES
from sales.engines import EngineManager
from playwright.sync_api import sync_playwright

def run():
 with tempfile.TemporaryDirectory() as tmp:
  store=Store(Path(tmp)/'ui.sqlite3');store.init();rs=ResearchStore(store);campaign=rs.create();f=Funnel(rs)
  for n in range(25):
   payload={'url':f'https://azienda{n}.example/','strategy':'change'}
   f.transition(campaign,payload,'promising','Nuova attività dichiarata: bisogno ancora da verificare.',{'company_ready':True,'identity':{'name':f'Azienda pilota {n}','website':payload['url'],'region':'Veneto','group':'direct','identity_status':'verified'},'excerpts':['Annunciamo una nuova linea di prodotti.'],'published_at':now(),'checked_at':now()})
  http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
  patches=[patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin)]
  for p in patches:p.start()
  threading.Thread(target=http.serve_forever,daemon=True).start();errors=[];report={'checks':[]}
  try:
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True);page=browser.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    for width in (390,1440):
     page.set_viewport_size({'width':width,'height':900});page.goto(origin);page.wait_for_selector('[data-funnel-view]')
     assert page.locator('[data-counter=qualified]').inner_text()=='0 / 50'
     assert page.locator('[data-counter=promising]').inner_text()=='25'
     page.locator('[data-funnel-view=promising]').click();page.wait_for_selector('#discovery-results .card')
     assert page.locator('#discovery-results .card').count()==20
     page.locator('[data-funnel-page=next]').click();page.wait_for_function("() => document.querySelectorAll('#discovery-results .card').length===5")
     page.locator('[data-funnel-page=previous]').click();page.wait_for_function("() => document.querySelectorAll('#discovery-results .card').length===20")
     page.locator('#discovery-results details > summary').first.click()
     form=page.locator('.commercial-outcome-form').first;form.locator('[name=kind]').select_option('conversation');form.locator('[name=note]').fill('Discussione reale del perimetro, registrata manualmente.')
     page.evaluate('pollState()');assert form.locator('[name=note]').input_value().startswith('Discussione reale')
     form.locator('button').click();page.wait_for_function("() => document.querySelector('.outcome-status').textContent.includes('salvato')")
     assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
     page.locator('.research-advanced > summary').click();page.locator('[data-discovery-metrics]').click();page.wait_for_selector('#detail[open] table')
     assert page.locator('#detail tbody tr').count()==len(STRATEGIES)
     assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
     page.screenshot(path=f'/tmp/customersearch-funnel-{width}.png',full_page=False)
     page.locator('[data-close=detail]').click()
     page.locator('[data-discovery-diagnostics]').click();page.wait_for_selector('#detail[open]')
     assert page.locator('#detail-title').inner_text()=='Come sta andando la ricerca'
     assert 'Tavily e Serper disattivati' in page.locator('#detail').inner_text()
     assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
     page.locator('[data-close=detail]').click();report['checks'].append(f'{width}px: phases, counters, pagination, feedback, focus, strategy metrics, no overflow')
    assert not errors,errors;browser.close()
  finally:
   http.shutdown();http.server_close()
   for p in patches:p.stop()
  report['javascript_errors']=errors;Path('docs/UI-AUDIT-4.1.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':run()
