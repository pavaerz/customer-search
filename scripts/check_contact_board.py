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
   first=f'[data-card-id="{ids[0]}"]'
   page.locator(first+' [data-action="confirm-contact"]').click()
   page.wait_for_selector(first+'.contacted-card')
   assert store.detail(ids[0])['stage']=='contacted'
   assert store.detail(ids[0])['contacted_at']
   assert page.locator(first+' [data-action="confirm-contact"]').count()==0
   page.reload();page.wait_for_selector(first+'.contacted-card')
   page.locator(first+' [data-open]').click()
   page.wait_for_selector('#detail[open]')
   assert page.locator('[data-tab="advisor"]').count()==0
   assert page.locator('.contact-banner.is-contacted').is_visible()
   page.locator('[data-close="detail"]').click()
   page.locator('.navitem[data-view="pipeline"]').click()
   second=f'[data-card-id="{ids[1]}"]'
   page.locator(second+' .drag-grip').drag_to(page.locator('.column[data-stage="contacted"] > h3'))
   page.wait_for_selector('.column[data-stage="contacted"] '+second+'.contacted-card')
   assert store.detail(ids[1])['stage']=='contacted'
   # Moving back keeps actual contact history and its green indicator.
   page.locator(second+' [data-move-id]').select_option('ready')
   page.wait_for_selector('.column[data-stage="ready"] '+second+'.contacted-card')
   assert store.detail(ids[1])['stage']=='ready'
   third=f'[data-card-id="{ids[2]}"]'
   # Failed writes must not move the card or invent a contact.
   page.route('**/api/prospects/'+str(ids[2])+'/update',lambda route:route.fulfill(status=400,content_type='application/json',body='{"error":"Errore di prova"}'))
   page.locator(third+' .drag-grip').drag_to(page.locator('.column[data-stage="contacted"] > h3'))
   page.wait_for_function("() => document.querySelector('#toast').textContent==='Errore di prova'")
   assert page.locator('.column[data-stage="review"] '+third).count()==1
   assert not store.detail(ids[2])['contacted_at']
   page.unroute('**/api/prospects/'+str(ids[2])+'/update')
   # A won deal needs its contract value; drag opens the right field without saving early.
   page.locator(third+' [data-move-id]').select_option('won')
   page.wait_for_selector('#manage-form')
   assert page.locator('#manage-form [name="stage"]').input_value()=='won'
   assert store.detail(ids[2])['stage']=='review'
   page.locator('#manage-form [name="contract_value"]').fill('2500')
   page.locator('#manage-form [type="submit"]').click()
   page.wait_for_function("() => document.querySelector('#toast').textContent==='Scheda aggiornata'")
   assert store.detail(ids[2])['stage']=='won'
   page.locator('[data-close="detail"]').click()
   page.screenshot(path='/tmp/customersearch-contact-board.png',full_page=True)
   # Same-column native drop is a no-op.
   before=len(store.detail(ids[1])['interactions'])
   page.locator(second+' .drag-grip').drag_to(page.locator('.column[data-stage="ready"] > h3'))
   assert len(store.detail(ids[1])['interactions'])==before
   assert not errors,errors
   # Dismissal hides the company in every work view and survives a reload.
   page.locator('.navitem[data-view="direct"]').click()
   endpoint='**/api/prospects/'+str(ids[0])+'/dismiss'
   page.route(endpoint,lambda route:route.fulfill(status=500,content_type='application/json',body='{"error":"Eliminazione non salvata"}'))
   page.locator(first+' [data-action="dismiss-proposal"]').click()
   page.wait_for_function("() => document.querySelector('#toast').textContent==='Eliminazione non salvata'")
   assert page.locator(first).count()==1
   assert not store.company_detail(ids[0])['dismissed_at']
   page.unroute(endpoint)
   page.locator(first+' [data-action="dismiss-proposal"]').click()
   page.wait_for_selector(first,state='detached')
   assert store.company_detail(ids[0])['dismissed_at']
   page.reload();page.wait_for_selector('.card')
   assert page.locator(first).count()==0
   page.locator('.navitem[data-view="pipeline"]').click()
   assert page.locator(first).count()==0
   page.locator('.navitem[data-view="direct"]').click()
   page.locator('[data-filter="stage"]').select_option('deleted')
   page.wait_for_selector(first)
   assert page.locator('.card').count()==1
   page.locator(first+' [data-open]').click();page.wait_for_selector('#detail[open]')
   page.locator('#detail [data-action="restore-proposal"]').click()
   page.wait_for_selector('#detail[open]',state='detached')
   assert not store.company_detail(ids[0])['dismissed_at']
   assert store.company_detail(ids[0])['stage']=='contacted'
   page.locator('[data-action="clear-filters"]').click()
   assert page.locator(first+'.contacted-card').count()==1
   # Touch: grip captures the finger while the board scrolls to the next column.
   mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
   phone=mobile.new_page();phone.on('pageerror',lambda e:errors.append(str(e)))
   phone.goto(origin);phone.locator('.navitem[data-view="pipeline"]').click()
   phone.locator(second+' .drag-grip').scroll_into_view_if_needed()
   grip=phone.locator(second+' .drag-grip');box=grip.bounding_box();x=box['x']+25;y=box['y']+15
   cdp=mobile.new_cdp_session(phone)
   cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
   cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':365,'y':y}]})
   phone.wait_for_timeout(650)
   target=phone.locator('.column[data-stage="contacted"]').bounding_box()
   target_x=min(350,max(25,target['x']+25));target_y=max(y,target['y']+30)
   cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':target_x,'y':target_y}]})
   cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
   phone.wait_for_selector('.column[data-stage="contacted"] '+second)
   assert store.detail(ids[1])['stage']=='contacted'
   assert phone.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
   assert not errors,errors
   print(json.dumps({'browser_errors':errors,'confirm_persists_after_reload':True,'advisor_removed':True,'mouse_drag_and_drop':True,'keyboard_select':True,'touch_drag_and_auto_scroll':True,'failed_drop_keeps_state':True,'contract_required_for_won':True,'dismissal_reload_filters_restore':True,'failed_dismissal_keeps_card':True,'real_data_modified':False}))
   browser.close()
 finally:
  http.shutdown();http.server_close();thread.join()
  for p in patches:p.stop()
