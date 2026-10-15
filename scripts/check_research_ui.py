"""Browser/API integration against isolated fixtures; never changes commercial records."""
import json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_research import sample
from test_commercial_inference import inference_sample
from sales import server
from sales.db import Store
from sales.research_store import ResearchStore
from sales.research_rules import qualify
from sales.campaigns import CampaignManager
from sales.engines import EngineManager
from playwright.sync_api import sync_playwright

def main():
 with tempfile.TemporaryDirectory() as tmp:
  store=Store(Path(tmp)/'ui.sqlite3');store.init();store.configure({'provider':'serper'});rs=ResearchStore(store);campaign=rs.create()
  ids=[]
  for n in range(3):
   args=inference_sample() if n==0 else sample();args[0].update(name='Azienda di prova '+str(n),website=f'https://alfa{n}.example/',legal_id='IT'+str(12345678900+n),group='agencies' if n==1 else 'direct')
   assessment=qualify(*args)
   if n==0:assessment['need_inference']['reason']+=' <script>unsafe</script>'
   assessment['investigation_plan']=[{'question':'La nuova offerta è già rappresentata?','quote':'Alfa <script>test</script> presenta una nuova divisione.',
       'url':'https://alfa.example/notizia','published_at':'2026-10-01','countercheck':'Una pagina aggiuntiva può bastare.',
       'limit':'Ipotesi da verificare.'}]
   ids.append(rs.save(campaign['id'],campaign['generation'],None,args[0],args[1],assessment))
  from sales.research_funnel import Funnel
  funnel=Funnel(rs);trace_payload={'url':'https://alfa0.example/','query':'produttori Padova <script>prova</script>','strategy':'companies','subject':'Azienda di prova 0'}
  funnel.offer(campaign['id'],'candidate','companies',trace_payload,'ui-trace')
  funnel.transition(campaign,trace_payload,'qualified','Prove verificate nella fixture.',{'identity':{'name':'Azienda di prova 0','website':'https://alfa0.example/','identity_status':'verified'}},ids[0])
  for n,group in enumerate(('direct','agencies')):
   identity={'name':'Promettente '+str(n),'website':f'https://promising{n}.example/','identity_status':'verified','group':group,'contacts':[{'type':'email','value':'collaborazioni@promising1.example'}]}
   details={'identity':identity,'company_ready':True}
   if group=='agencies':details['collaboration']={'kind':'standing_invitation','quote':'Accettiamo collaborazioni frontend freelance <script>unsafe</script>','url':identity['website']+'lavora-con-noi','checked_at':'2026-10-14T12:00:00+00:00','budget':None}
   for path in ('servizi','contatti'):
    funnel.transition(campaign,{'url':identity['website']+path,'strategy':'companies'},'promising','Prima selezione, verifica incompleta.',details)
  rs.finish(campaign['id'],campaign['generation'],'completed','Campagna di prova completata')
  http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
  patches=[patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin),patch.object(CampaignManager,'launch',lambda manager,c:manager.rs.campaign(c['id']))]
  for p in patches:p.start()
  thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
  try:
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin+'/') else route.abort())
    page.goto(origin);page.wait_for_selector('[data-opportunity-id]')
    assert page.locator('[data-opportunity-id]').count()==3
    page.locator('[data-funnel-view="promising"]').click()
    page.wait_for_function("() => document.querySelectorAll('#discovery-results .card').length===2")
    assert page.locator('[data-counter="promising"]').inner_text()=='2'
    assert page.locator('.result-tabs [data-view="all"] .count').inner_text()=='2'
    page.locator('.result-tabs [data-view="agencies"]').click()
    page.wait_for_function("() => document.querySelectorAll('#discovery-results .card').length===1")
    assert 'active' in page.locator('[data-funnel-view="promising"]').get_attribute('class')
    assert page.locator('.result-tabs [data-view="agencies"] .count').inner_text()=='1'
    assert 'collaborazioni@promising1.example' in page.locator('#discovery-results').inner_text()
    assert 'Ambito e compenso da concordare' in page.locator('#discovery-results').inner_text()
    assert 'Partner disponibile · da contattare' in page.locator('#discovery-results').inner_text()
    assert 'nessuna commessa aperta verificata' in page.locator('#discovery-results').inner_text()
    assert page.locator('#discovery-results script').count()==0
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.set_viewport_size({'width':1440,'height':1000})
    page.evaluate('updateResearchState(S)')
    assert page.locator('.result-tabs [data-view="all"] .count').inner_text()=='2'
    page.locator('.result-tabs [data-view="all"]').click()
    page.wait_for_function("() => document.querySelectorAll('#discovery-results .card').length===2")
    page.locator('[data-funnel-view="qualified"]').click()
    page.wait_for_function("() => document.querySelector('.result-tabs [data-view=all] .count').textContent==='3'")
    page.evaluate('discoveryDiagnostics()');page.wait_for_selector('#detail[open]')
    page.locator('[data-research-paths="0"]').click();page.wait_for_function("() => document.querySelector('#research-paths')?.innerText.includes('Ricostruzione')")
    page.locator('#research-paths details').filter(has_text='alfa0.example').locator('summary').click()
    assert 'produttori Padova <script>prova</script>' in page.locator('#research-paths').inner_text()
    assert page.locator('#research-paths script').count()==0
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.set_viewport_size({'width':1440,'height':1000});page.locator('[data-close="detail"]').click()

    page.locator('.result-tabs [data-view="agencies"]').click();page.wait_for_function("() => document.querySelectorAll('[data-opportunity-id]').length===1")
    page.locator('.result-tabs [data-view="direct"]').click();page.wait_for_function("() => document.querySelectorAll('[data-opportunity-id]').length===2")
    page.locator('[data-research-filter="search"]').fill('prova 0');page.wait_for_function("() => document.querySelectorAll('[data-opportunity-id]').length===1")
    page.locator('[data-research-open]:visible').click();page.wait_for_selector('#detail[open]')
    assert 'Le prove' in page.locator('#detail').inner_text()
    assert 'sconosciuto' in page.locator('#detail').inner_text()
    assert page.locator('[data-commercial-inference]').count()==1
    assert 'Alternative più piccole valutate' in page.locator('[data-commercial-inference]').inner_text()
    assert page.locator('[data-commercial-inference] a').count()==2
    page.get_by_text('Ipotesi da verificare a partire dalle fonti',exact=True).click()
    assert 'La nuova offerta è già rappresentata?' in page.locator('#detail').inner_text()
    assert page.locator('#detail script').count()==0
    page.locator('[data-close="detail"]').click()
    page.locator('#main [data-action="confirm-contact"]').click();page.wait_for_selector('.contacted-card')
    page.locator('#main [data-action="dismiss-proposal"]').click();page.wait_for_function("() => document.querySelectorAll('[data-opportunity-id]').length===0")
    page.locator('[data-research-filter="search"]').fill('');page.wait_for_selector('[data-opportunity-id]')
    page.locator('[data-research-open]:visible').click();page.wait_for_selector('#detail[open]')
    page.get_by_text('Registra una revisione della qualità',exact=True).click()
    page.locator('#quality-review-form [name="reason"]').fill('Fonti della fixture controllate separatamente.')
    page.locator('#quality-review-form [type="submit"]').click();page.wait_for_function("() => document.querySelector('#toast').textContent==='Revisione registrata'")
    page.locator('[data-close="detail"]').click()
    assert page.locator('#campaign-target').count()==0
    assert 'Negozi e marchi propri' in page.locator('#campaign-segments').text_content()
    assert 'Servizi e professionisti' in page.locator('#campaign-segments').text_content()
    assert page.locator('#campaign-project').input_value()=='website'
    assert page.locator('#campaign-group').input_value()==''  # Companies and agencies by default.
    page.locator('.research-advanced > summary').click()
    page.locator('#campaign-group').select_option('')
    page.evaluate('render()')
    assert page.locator('#campaign-group').input_value()==''
    page.locator('#campaign-group').select_option('direct')
    page.locator('[data-research-action="start"]').click();page.wait_for_selector('[data-research-action="stop"]')
    assert rs.campaign()['filters']=={'target':'all','projects':['website'],'groups':['direct'],'regions':['Veneto']}
    page.locator('[data-research-action="stop"]').click();page.wait_for_selector('[data-research-action="resume"]')
    page.locator('[data-research-action="resume"]').click();page.wait_for_selector('[data-research-action="stop"]')
    page.locator('[data-research-action="stop"]').click();page.wait_for_selector('[data-research-action="resume"]')
    page.screenshot(path='/tmp/customersearch4-desktop.png',full_page=True)
    page.locator('[data-view="pipeline"]').click();page.wait_for_selector('[draggable="true"]')
    card=page.locator('[draggable="true"]').first
    target=page.locator('[data-stage="ready"]')
    if not target.count():target=page.locator('[data-drop-stage="ready"]')
    if not target.count():raise AssertionError('Colonna destinazione drag and drop non trovata')
    card.drag_to(target);page.wait_for_timeout(500)
    page.locator('[data-view="settings"]').click();page.locator('#settings-form [type="submit"]').click();page.wait_for_function("() => document.querySelector('#toast').textContent==='Impostazioni salvate'")
    assert store.settings()['provider']=='serper'
    assert page.locator('#settings-form [name=daily_api_limit]').input_value()==''
    assert store.settings()['daily_api_limit'] is None
    page.locator('#settings-form [name=daily_api_limit]').fill('45')
    page.locator('#settings-form [type=submit]').click();page.wait_for_timeout(400)
    assert store.settings()['daily_api_limit']==45
    page.locator('#settings-form [name=daily_api_limit]').fill('')
    page.locator('#settings-form [type=submit]').click();page.wait_for_timeout(400)
    assert store.settings()['daily_api_limit'] is None
    page.wait_for_function("() => document.querySelector('#trial-start').hidden===true")
    page.evaluate("navigate('results')")
    assert 'Prime 10 proposte · da verificare' in page.locator('#main').inner_text()
    assert 'Prime 20 proposte · da verificare' in page.locator('#main').inner_text()
    assert 'Non è un benchmark indipendente' in page.locator('#main').inner_text()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.locator('[data-view="overview"]').click();page.locator('[data-research-scope]').select_option('all');page.wait_for_selector('[data-opportunity-id]')
    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(200)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path='/tmp/customersearch4-mobile.png',full_page=True)
    assert not errors,errors
    print(json.dumps({'phase_counts_and_category_switch':True,'discovery_paths':True,'company_preferences':True,'desktop_mobile':True,'filters_dossier_review':True,'contact_green_delete':True,'start_stop_resume':True,'pipeline_drag_drop':True,'settings_save':True,'browser_errors':errors,'real_data_modified':False}))
    browser.close()
  finally:
   http.shutdown();http.server_close();thread.join()
   for p in patches:p.stop()
if __name__=='__main__':main()
