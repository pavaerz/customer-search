"""Browser checks on isolated data, with controlled source responses."""
import sys,tempfile,threading,json,time
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from sales import server
from sales.db import Store,now,encode
from sales.engines import EngineManager
class Process:
 pid=99999999
 def poll(self):return None
 def wait(self,timeout=None):return 0

def run():
 results=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(channel='chrome',headless=True)
  for width in (390,1440):
   with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
    store=Store(Path(tmp)/'test.db');store.init();http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
    for obj,key,value in [(server,'STORE',store),(server,'MANAGER',EngineManager(store)),(server,'PORT',http.server_port),(server,'ORIGIN',origin)]:stack.enter_context(patch.object(obj,key,value))
    stack.enter_context(patch('sales.grants.subprocess.Popen',return_value=Process()));stack.enter_context(patch('sales.grants.os.killpg'))
    threading.Thread(target=http.serve_forever,daemon=True).start();page=browser.new_page(viewport={'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    try:
     page.goto(origin);page.locator('[data-view=grants]').click();page.locator('[name=activity]').fill('Sviluppo siti web');page.locator('[name=province]').fill('Padova');page.locator('#grant-profile-form button[type=submit]').click();page.wait_for_function("()=>document.querySelector('#grant-save-status').textContent.includes('salvato')")
     page.locator('#grant-start').click();page.locator('#grant-stop').wait_for(state='visible');assert page.locator('#grant-start').is_disabled()
     page.locator('[name=investment]').fill('Software');page.wait_for_timeout(2300);assert page.locator('[name=investment]').input_value()=='Software'
     page.locator('#grant-stop').click();page.locator('#grant-stop').wait_for(state='hidden');assert page.locator('#grant-start').is_enabled()
     page.locator('[data-view=pipeline]').click();page.locator('[data-view=grants]').click();page.locator('#grant-start').wait_for();assert page.locator('[name=investment]').input_value()=='Software'
     assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'), 'horizontal overflow'
     icons=page.locator('.navitem svg path').evaluate_all('(els)=>els.map(e=>e.getAttribute("d"))');assert len(icons)==len(set(icons))
     # Seed synthetic evidence only in the temporary browser database.
     from sales.grant_eligibility import rule_key
     d={'id':'ui-document','url':'https://www.invitalia.it/test','title':'Bando di collaudo','checked_at':now(),'text':'Confermare di non aver distribuito utili.\nSono ammesse imprese con sede nel Lazio.\nStato incentivo o strumento\nAttivo'}
     r={'label':'Nessun utile distribuito','field':'declaration','operator':'fact','values':['yes'],'quote':'Confermare di non aver distribuito utili.','document_id':d['id'],'question':'Confermi che non sono stati distribuiti utili?'}
     excluded={**r,'field':'region','operator':'in','values':['Lazio'],'quote':'Sono ammesse imprese con sede nel Lazio.','label':'Sede nel Lazio','question':'Dove ha sede l’attività?'}
     with store.connect() as c:
      cid=c.execute('SELECT max(id) FROM grant_runs').fetchone()[0]
      for idx,rule in enumerate((r,excluded)):
       body={'deadlines':[],'benefit':[],'eligibility_bundle':{'documents':[d],'rules':[rule],'complete':True,'limitations':[]}}
       c.execute('INSERT INTO grant_items(run_id,url,title,body,checked_at) VALUES (?,?,?,?,?)',(cid,d['url']+str(idx),'Bando di collaudo '+str(idx),encode(body),now()))
     page.locator('[data-view=pipeline]').click();page.locator('[data-view=grants]').click();page.locator('[data-grant-answers]').wait_for()
     page.locator('[data-grant-answers] select').select_option('yes');page.locator('[data-grant-answers] button').click();page.locator('.grant-compatible').wait_for()
     page.locator('[data-grant-filter=excluded]').click();assert page.locator('.grant-excluded').count()==1;assert page.locator('.grant-compatible').count()==0
     page.locator('[data-grant-filter=compatible]').click();assert page.locator('.grant-compatible').count()==1
     page.locator('.grant-compatible summary').click();assert page.get_by_text('Leggi il requisito nella fonte').count()==2
     assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
     page.screenshot(path=f'/tmp/grants-{width}.png',full_page=True);assert not errors,errors
     results.append({'width':width,'profile_save':True,'start_stop':True,'draft_preserved':True,'unique_icons':True,'overflow':False,'js_errors':errors})
    finally:page.close();http.shutdown();http.server_close()
  browser.close()
 print(json.dumps(results,indent=2))
if __name__=='__main__':run()
