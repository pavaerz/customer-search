"""Desktop/mobile UI, temporary SQLite and blocked workers/network only."""
import json,tempfile,threading,os
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from sales import server
from sales.db import Store
from sales.engines import EngineManager
from sales.research_store import ResearchStore
from sales.campaigns import CampaignManager
from sales.safe_proxy import SafeProxy
from playwright.sync_api import sync_playwright,expect

def main():
 errors=[];checks=[];out=Path('implementation-report')
 for width in (1440,390):
  with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
   store=Store(Path(tmp)/'ux.db');store.init();rs=ResearchStore(store)
   http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
   launch=stack.enter_context(patch.object(CampaignManager,'launch'))
   for p in [patch.dict(os.environ,{'SERPER_API_KEY':'','CUSTOMERSEARCH_AI_API_KEY':''}),patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin),patch('sales.safe_proxy.public_addresses',side_effect=ValueError('Offline UI')),patch('sales.commercial.ai.infer',side_effect=AssertionError('No inference'))]:stack.enter_context(p)
   thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
   try:
    with SafeProxy() as proxy,sync_playwright() as pw:
     browser=pw.chromium.launch(channel='chrome',headless=True,proxy={'server':proxy.url,'bypass':'127.0.0.1'},args=['--disable-quic'])
     try:
      ctx=browser.new_context(viewport={'width':width,'height':950},service_workers='block');ctx.route('**/*',lambda r:r.continue_() if r.request.url.startswith(origin+'/') else r.abort())
      p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));p.goto(origin);p.wait_for_selector('#commercial-root')
      p.locator('.commercial-setup summary').click();expect(p.locator('#commercial-profile-preview')).to_contain_text('28 crediti Serper')
      p.locator('#commercial-mode').select_option('extended');expect(p.locator('#commercial-profile-preview')).to_contain_text('60 crediti Serper');expect(p.locator('#commercial-profile-preview')).to_contain_text('40 candidati');expect(p.locator('#commercial-profile-preview')).to_contain_text('4 audit browser')
      selfstate=rs.campaign();assert selfstate is None;launch.assert_not_called()
      assert not p.evaluate('document.documentElement.scrollWidth>innerWidth+1');p.screenshot(path=str(out/f'phase42-extended-{width}.png'))
      p.locator('[data-research-action="start"]').click();p.wait_for_function("() => S.campaign?.filters?.mode==='extended'")
      launch.assert_called_once();c=rs.campaign();assert c['filters']['mode']=='extended';assert c['filters']['work_budget']['max_serper_credits']==15
      assert not p.evaluate('document.documentElement.scrollWidth>innerWidth+1')
      checks.append({'width':width,'passed':True,'selection_does_not_start':True,'manual_start_payload_extended':True,'pilot_serper_total':28,'extended_serper_total':60,'horizontal_overflow':False});ctx.close()
     finally:browser.close()
   finally:http.shutdown();http.server_close();thread.join()
 assert not errors,errors
 result={'scope':'local temporary DB / workers mocked','checks':checks,'javascript_errors':errors,'external_calls':0,'production_writes':0,'real_campaigns':0}
 (out/'phase42-ux.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
