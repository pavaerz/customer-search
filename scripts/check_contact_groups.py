import json,tempfile,threading,sys
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales import server
from sales.db import Store,now
from sales.engines import EngineManager
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 store=Store(Path(tmp)/'ui.db');store.init()
 ids=[]
 for n in range(3):
  cid=store.company(f'https://example{n}.org',f'Azienda di prova {n+1}')
  sid=store.source({'url':f'https://example{n}.org/jobs'},cid)
  eid=store.add_evidence(cid,sid,'A','request','Richiesta pubblica','Cerchiamo un collaboratore WordPress freelance.',now())
  ids.append(store.prospect(cid,'A','Collaborazione','WordPress',60,{},'Richiesta di un collaboratore WordPress.','Da confermare',[],[eid])[0])
 http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
 patches=[patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin)]
 for p in patches:p.start()
 thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(origin);page.wait_for_selector('.card')
   store.classify_contact(store.detail(ids[1])['company_id'],'agencies','Categoria della fixture',manual=True)
   page.reload();page.wait_for_selector('.result-tabs')
   assert page.locator('.navitem[data-view="agencies"] .count').inner_text()=='1'
   assert page.locator('.navitem[data-view="direct"] .count').inner_text()=='2'
   page.locator('.navitem[data-view="agencies"]').click()
   assert page.locator('.card').count()==1
   assert page.locator(f'[data-card-id="{ids[1]}"]').count()==1
   page.locator('.result-tabs [data-view="direct"]').click()
   assert page.locator('.card').count()==2
   page.locator('[data-filter="search"]').fill('prova 1')
   assert page.locator('.card').count()==1
   page.locator('[data-action="clear-filters"]').click()
   assert page.locator('.card').count()==2
   page.locator(f'[data-open="{ids[0]}"]').click()
   page.locator('.tabs [data-tab="manage"]').click()
   page.locator('[name="contact_group"]').select_option('agencies')
   page.locator('#manage-form [type="submit"]').click()
   page.wait_for_function("() => document.querySelector('#toast').textContent==='Scheda aggiornata'")
   page.locator('[data-close="detail"]').click()
   assert page.locator('.card').count()==1
   page.reload();page.wait_for_selector('.result-tabs')
   page.locator('.navitem[data-view="agencies"]').click()
   assert page.locator('.card').count()==2
   page.locator('.navitem[data-view="settings"]').click()
   assert page.locator('[name="provider"]').input_value()=='searxng'
   assert page.locator('[name="daily_api_limit"]').count()==0
   page.locator('#settings-form [type="submit"]').click()
   page.wait_for_function("() => document.querySelector('#toast').textContent==='Impostazioni salvate'")
   assert store.settings()['provider']=='searxng'
   page.locator('.navitem[data-view="direct"]').click()
   page.screenshot(path='/tmp/customersearch-groups-desktop.png',full_page=True)
   page.set_viewport_size({'width':390,'height':844})
   assert page.locator('.navitem[data-view="agencies"]').is_visible()
   assert page.locator('.navitem[data-view="direct"]').is_visible()
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   page.screenshot(path='/tmp/customersearch-groups-mobile.png',full_page=True)
   page.locator('.result-tabs [data-view="agencies"]').click()
   assert page.locator('.card').count()==2
   assert not errors,errors
   print(json.dumps({'menu_counts_filters':True,'category_save_reload':True,'free_provider_settings_saved':True,'mobile_no_overflow':True,'browser_errors':errors,'real_data_modified':False}))
   browser.close()
 finally:
  http.shutdown();http.server_close();thread.join()
  for p in patches:p.stop()
