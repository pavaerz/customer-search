"""Isolated desktop/mobile checks. No Serper requests or real credentials submitted."""
import json,sys,tempfile,threading
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from sales import server
from sales.db import Store,encode
from sales.engines import EngineManager

class Process:
    pid=99999999
    def poll(self):return None
    def wait(self,timeout=None):return 0

def run():
    report=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome',headless=True)
        for width in (390,1440):
            with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
                store=Store(Path(tmp)/'test.db');store.init()
                http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
                for obj,key,value in [(server,'STORE',store),(server,'MANAGER',EngineManager(store)),(server,'PORT',http.server_port),(server,'ORIGIN',origin)]:stack.enter_context(patch.object(obj,key,value))
                stack.enter_context(patch('sales.search_trial.subprocess.Popen',return_value=Process()));stack.enter_context(patch('sales.search_trial.os.killpg'));stack.enter_context(patch('sales.search_trial.api_key',return_value='fixture-key'))
                threading.Thread(target=http.serve_forever,daemon=True).start()
                page=browser.new_page(viewport={'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                try:
                    page.goto(origin);page.locator('[data-view=settings]').click();page.get_by_text('Chiave configurata · valore nascosto').wait_for()
                    assert page.locator('#trial-start').is_disabled()
                    page.locator('#trial-free').check();page.locator('#trial-start').click();page.locator('#trial-stop').wait_for(state='visible')
                    assert page.locator('#trial-start').is_disabled()
                    page.locator('#trial-stop').click();page.locator('#trial-stop').wait_for(state='hidden')
                    with store.connect() as c:
                        row=c.execute('SELECT * FROM search_trials').fetchone();body=json.loads(row['report'])
                        body['candidates']=[{'url':'https://example.org/prova','title':'Campione di collaudo','providers':['serper'],'identity':{'name':'Azienda di collaudo'},'triage':{'state':'rejected','reason':'Nessun bisogno digitale documentato'}}]
                        c.execute('UPDATE search_trials SET report=? WHERE id=?',(encode(body),row['id']))
                    page.get_by_text('Campione di collaudo',exact=False).count()
                    page.wait_for_function("()=>document.querySelector('#trial-report').textContent.includes('Azienda di collaudo')")
                    page.locator('[data-trial-details="candidates"] > summary').click()
                    page.locator('[data-trial-details="https://example.org/prova"] summary').click()
                    page.locator('[data-trial-review] textarea').fill('Nessun progetto completo nella fonte ufficiale')
                    page.wait_for_timeout(3300)
                    assert page.locator('[data-trial-review] textarea').input_value().startswith('Nessun progetto')
                    page.locator('[data-trial-review] button').click();page.get_by_text('Revisione: Qualificazione non giustificata',exact=False).wait_for()
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    assert not errors,errors
                    page.screenshot(path=f'/tmp/search-trial-{width}.png',full_page=True)
                    report.append({'width':width,'start_stop':True,'review_saved':True,'draft_preserved':True,'overflow':False,'js_errors':errors})
                finally:page.close();http.shutdown();http.server_close()
        browser.close()
    print(json.dumps(report,indent=2))
if __name__=='__main__':run()
