"""Isolated browser acceptance; disallow campaigns and all external routes."""
import json,sys,tempfile,threading,os
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from sales import server
from sales.db import Store
from sales.engines import EngineManager
from sales.campaigns import CampaignManager
from sales.research_store import ResearchStore
from sales.agent6 import memory
from test_agent6 import evaluated
from sales.safe_proxy import SafeProxy
from playwright.sync_api import sync_playwright,expect

def main():
 errors=[];checks=[];out=Path('implementation-report')
 with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
  store=Store(Path(tmp)/'ux.db');store.init();rs=ResearchStore(store)
  campaign=rs.create({'agent_version':'6.0','commercial_engines':['AZIENDE','AGENCIES','STARTUPS'],'mode':'extended','commercial':{'ai':{'enabled':True,'provider':'MOCK'}}})
  rid=memory.save_record(store,campaign,'AZIENDE',evaluated());rs.stop(campaign['id']);rs.paused(campaign['id'])
  http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
  for p in [patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin),patch.object(CampaignManager,'launch',side_effect=AssertionError('No real campaign')),patch('sales.agent6.ai.infer',side_effect=AssertionError('Offline')),patch('sales.safe_proxy.public_addresses',side_effect=ValueError('External access forbidden in UI test'))]:stack.enter_context(p)
  threading.Thread(target=http.serve_forever,daemon=True).start()
  try:
   with SafeProxy() as proxy,sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True,proxy={'server':proxy.url,'bypass':'127.0.0.1'},args=['--disable-quic'])
    try:
     for width in (1440,390):
      ctx=browser.new_context(viewport={'width':width,'height':950},service_workers='block');ctx.route('**/*',lambda r:r.continue_() if r.request.url.startswith(origin+'/') else r.abort())
      page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(origin);page.wait_for_selector('#agent6-root');page.locator('[data-agent7-mode="RESEARCH"]').first.click();expect(page.locator('.agent6-card')).to_contain_text('Alfa Srl')
      page.screenshot(path=str(out/f'customersearch6-dashboard-{width}.png'),full_page=True)
      page.locator('[data-agent6="preview"]').click();expect(page.locator('#agent6-preview')).to_contain_text('Riepilogo prima di avviare')
      page.locator('[data-agent6="dossier"]').click();expect(page.locator('#agent6-detail-'+str(rid))).to_contain_text('caratteri')
      page.locator('[data-agent6="review"]').click();page.locator('#agent6-outcome-'+str(rid)).select_option('contacted');page.locator('#agent6-note-'+str(rid)).fill('<script>not executable</script>');page.locator('[data-agent6="feedback"]').click();expect(page.locator('.agent6-card')).to_have_class(__import__('re').compile('is-contacted'))
      page.locator('#agent6-filter-state').select_option('REJECTED');expect(page.locator('#agent6-results')).to_contain_text('Nessuna scheda');page.locator('#agent6-filter-state').select_option('');expect(page.locator('.agent6-card')).to_be_visible()
      page.locator('[data-agent6="intelligence"]').click();expect(page.locator('#agent6-intelligence')).to_contain_text('Memoria e apprendimento')
      assert page.locator('script:not([src])').count()==0
      assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
      page.screenshot(path=str(out/f'customersearch6-{width}.png'),full_page=True)
      page.locator('[data-agent6="legacy"]').click();expect(page.locator('#commercial-root')).to_be_visible();page.locator('[data-agent6="return"]').click();expect(page.locator('#agent6-root')).to_be_visible()
      # Polling must retain expanded details and expose Stop without starting work.
      page.evaluate("S.campaign.running=true;S.campaign.status='running';updateResearchState(S)")
      expect(page.locator('[data-agent6="stop"]')).to_be_visible()
      expect(page.locator('[data-agent6="preview"]')).to_be_disabled()
      page.locator('#agent6-progress summary').click()
      page.evaluate('updateResearchState(S)')
      expect(page.locator('#agent6-progress details')).to_have_attribute('open','')
      # No campaign: understandable empty state, selection validation and keyboard access.
      page.evaluate("S.campaign=null;renderAgent6()")
      expect(page.locator('#agent6-results')).to_contain_text('La tua prossima ricerca')
      for checkbox in page.locator('[data-agent6-flow]').all(): checkbox.uncheck()
      expect(page.locator('[data-agent6="preview"]')).to_be_disabled()
      page.locator('[data-agent6-flow="AGENCIES"]').focus();page.keyboard.press('Space')
      expect(page.locator('#agent6-selection-summary')).to_contain_text('1 categoria selezionata')
      expect(page.locator('[data-agent6="preview"]')).to_be_enabled()
      page.locator('[data-agent6="preview"]').click()
      expect(page.locator('#agent6-preview')).to_contain_text('Riepilogo prima di avviare')
      page.locator('[data-agent6-flow="STARTUPS"]').check()
      expect(page.locator('#agent6-preview')).to_be_empty()
      page.locator('[data-agent6-flow="AZIENDE"]').check()
      page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(250)
      page.screenshot(path=str(out/f'customersearch6-empty-{width}.png'),full_page=True)
      assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
      checks.append({'width':width,'passed':True,'checks':['new dashboard','cost preview','cited dossier','manual feedback','contact green','filters','intelligence','legacy access','no overflow','escaped text','empty state','keyboard selection','zero selections disabled','preview invalidation','running stop control','polling preserves details']});ctx.close()
    finally:browser.close()
  finally:http.shutdown();http.server_close()
 assert not errors,errors
 result={'checks':checks,'javascript_errors':errors,'external_calls':0,'live_campaigns':0,'production_writes':0};(out/'customersearch6-ux.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
