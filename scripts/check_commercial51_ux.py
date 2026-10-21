"""Offline Chromium, temporary SQLite, all external routes blocked."""
import sys,json,tempfile,threading,os
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from sales import server
from sales.db import Store
from sales.engines import EngineManager
from sales.campaigns import CampaignManager
from sales.safe_proxy import SafeProxy
from playwright.sync_api import sync_playwright,expect

def main():
 out=Path('implementation-report');errors=[];checks=[]
 with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
  store=Store(Path(tmp)/'ux.db');store.init()
  http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
  for p in [patch.dict(os.environ,{'SERPER_API_KEY':'','CUSTOMERSEARCH_AI_API_KEY':''}),patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin),patch.object(CampaignManager,'launch',side_effect=AssertionError('No campaign permitted')),patch('sales.safe_proxy.public_addresses',side_effect=ValueError('Offline UI')),patch('sales.commercial.ai.infer',side_effect=AssertionError('No inference'))]:stack.enter_context(p)
  thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
  try:
   with SafeProxy() as proxy,sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True,proxy={'server':proxy.url,'bypass':'127.0.0.1'},args=['--disable-quic'])
    try:
     for width in (1440,390):
      ctx=browser.new_context(viewport={'width':width,'height':950},service_workers='block');ctx.route('**/*',lambda r:r.continue_() if r.request.url.startswith(origin+'/') else r.abort())
      page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(origin);page.wait_for_selector('[data-search-plan]')
      page.locator('[data-search-plan]').click();expect(page.locator('#search-plan-result')).to_contain_text('PILOT: 12 query')
      page.locator('.commercial-setup > summary').click();page.locator('#commercial-mode').select_option('deep')
      expect(page.locator('#search-plan-result')).to_contain_text('Piano da aggiornare')
      page.locator('[data-search-plan]').click();expect(page.locator('#search-plan-result')).to_contain_text('144 crediti Serper')
      auth=page.locator('#commercial-deep-authorization');expect(auth).not_to_be_checked();auth.check()
      page.locator('#search-plan-result details').first.locator('summary').click()
      expect(page.locator('.search-plan-queries')).to_contain_text('remote')
      assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
      page.locator('[data-search-plan]').scroll_into_view_if_needed();page.screenshot(path=str(out/f'phase51-planner-{width}.png'),full_page=False)
      page.locator('#commercial-mode').select_option('pilot');page.locator('#commercial-mode').select_option('deep');page.locator('[data-search-plan]').click();expect(auth).not_to_be_checked()
      page.locator('[data-commercial-view="recommended"]').click();expect(page.locator('[data-job-filter="employment"]')).to_have_value('freelance');page.locator('[data-job-filter="employment"]').select_option('employment')
      assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
      page.evaluate("""() => {
        const host=document.createElement('section');host.id='demand-test';
        host.innerHTML=commercialDemandDetails({demand_assessment:{page_type:'STANDING_COLLABORATION',actors:{publisher:'alfa.example',buyer:null},geography:{status:'GEO_UNKNOWN'},original_available:true,evidence_level:3,evidence:{request_quote:'<script>unsafe</script> Cerchiamo WordPress freelance.'}}})+commercialCandidateStages({candidate_stages:{policy:'deep_review_quota',RAW_RESULTS:40,SCREENED_RESULTS:40,ADMITTED_CANDIDATES:3,DEEP_REVIEW_CANDIDATES:1}});
        document.querySelector('main').append(host);
      }""")
      expect(page.locator('#demand-test')).to_contain_text('Committente: Non identificato')
      expect(page.locator('#demand-test')).to_contain_text('Approfondimenti avviati: 1')
      assert page.locator('#demand-test script').count()==0
      assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
      page.locator('#demand-test').scroll_into_view_if_needed();page.screenshot(path=str(out/f'phase51-demand-{width}.png'))
      checks.append({'width':width,'passed':True,'checks':['read-only preview','deep limits and explicit checkbox','authorization invalidated on settings change','query list','employment separation','escaped demand dossier','separate budget counters','no overflow']});ctx.close()
    finally:browser.close()
   with store.connect() as c:assert c.execute('select count(*) from campaigns').fetchone()[0]==0
  finally:http.shutdown();http.server_close();thread.join()
 assert not errors,errors
 r={'checks':checks,'javascript_errors':errors,'external_calls':0,'production_writes':0,'campaigns_started':0}
 (out/'phase51-ux.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
if __name__=='__main__':main()
