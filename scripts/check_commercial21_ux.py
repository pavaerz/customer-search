"""Offline Phase 2.1 browser acceptance: temporary DB/server; all workers mocked.

Run with the implementation-report/offline-test-guard on PYTHONPATH.
Chromium external traffic is denied by SafeProxy, including background traffic.
"""
import sys,json,tempfile,threading
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_commercial_engines import page as fixture
from sales import server
from sales.db import Store
from sales.engines import EngineManager
from sales.research_store import ResearchStore
from sales.campaigns import CampaignManager
from sales.commercial.storage import Opportunities
from sales.commercial.inspection import inspect
from sales.commercial.catalog import ENGINES
from sales.safe_proxy import SafeProxy
from playwright.sync_api import sync_playwright,expect

def main():
    output=Path('implementation-report');errors=[];results=[]
    with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
        store=Store(Path(temp)/'ux.db');store.init();rs=ResearchStore(store);campaign=rs.create({'commercial_engines':list(ENGINES)})
        with patch('sales.commercial.inspection.ResearchWeb.get',lambda web,url:fixture('Siamo una web agency e startup. Cerchiamo partner tecnico WordPress freelance per MVP retribuito.',url=url)):
            for engine in ('FREELANCE','AGENCIES','STARTUPS'):
                found=inspect(store,{'commercial_engine':engine,'url':'https://alfa.example/collabora-con-noi'})
                Opportunities(store).save(campaign,found['identity'],found['documents'],found['result'])
        rs.stop(campaign['id']);rs.paused(campaign['id'])
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin='http://127.0.0.1:'+str(http.server_port)
        for p in [patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin),patch.object(CampaignManager,'launch',lambda manager,c:manager.rs.campaign(c['id'])),patch('sales.safe_proxy.public_addresses',side_effect=ValueError('Offline audit'))]:stack.enter_context(p)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            with SafeProxy() as proxy,sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True,proxy={'server':proxy.url,'bypass':'127.0.0.1'},args=['--disable-quic','--force-webrtc-ip-handling-policy=disable_non_proxied_udp'])
                try:
                    for width in (1440,390):
                        context=browser.new_context(viewport={'width':width,'height':950},service_workers='block')
                        context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin+'/') else route.abort())
                        p=context.new_page();p.on('pageerror',lambda error:errors.append(str(error)))
                        p.goto(origin);p.wait_for_selector('.commercial-card');assert p.locator('.commercial-card').count()==3
                        assert p.locator('[data-commercial-engine]').count()==4
                        expect(p.locator('#commercial-progress')).to_contain_text('URL candidati')
                        expect(p.locator('#commercial-progress')).to_contain_text('Verifiche incomplete')
                        overflow=p.evaluate('document.documentElement.scrollWidth>innerWidth+1');assert not overflow,('overflow',width)
                        p.screenshot(path=str(output/f'phase-2.1-{width}.png'),full_page=True)
                        p.locator('[data-commercial-engine="AGENCIES"]').click();expect(p.locator('.commercial-card')).to_have_count(1)
                        p.locator('[data-commercial-detail]').click();p.wait_for_selector('#detail[open]');p.locator('#detail [data-close]').click();assert not p.locator('#detail').evaluate('(e)=>e.open')
                        p.locator('[data-commercial-action="save"]').click();expect(p.locator('.commercial-card')).to_contain_text('Salvata nei contatti')
                        p.locator('[data-commercial-detail]').click();p.wait_for_selector('[data-commercial-crm]');p.locator('[data-commercial-crm]').click();p.wait_for_selector('#detail [data-tab="manage"]');p.locator('#detail [data-close]').click()
                        if width==1440:
                            p.locator('[data-commercial-action="contacted"]').click();p.wait_for_selector('.commercial-card.is-contacted')
                        p.locator('[data-commercial-action="discard"]').click();p.wait_for_selector('.empty')
                        p.locator('[data-commercial-filter="include_discarded"]').check();p.wait_for_selector('[data-commercial-action="restore"]');p.locator('[data-commercial-action="restore"]').click();p.wait_for_selector('[data-commercial-action="discard"]')
                        p.locator('[data-commercial-filter="search"]').fill('nessun-risultato-fixture');p.wait_for_selector('.empty');p.locator('[data-commercial-filter="search"]').fill('');p.wait_for_selector('.commercial-card')
                        p.locator('[data-research-action="start"]').click();p.wait_for_selector('[data-research-action="stop"]');assert len(rs.campaign()['filters']['commercial_engines'])==4
                        p.locator('[data-research-action="stop"]').click();p.wait_for_selector('[data-research-action="resume"]');p.locator('[data-research-action="resume"]').click();p.wait_for_selector('[data-research-action="stop"]');p.locator('[data-research-action="stop"]').click();p.wait_for_selector('[data-research-action="resume"]')
                        p.locator('[data-commercial-legacy]').click();p.wait_for_selector('.campaign-panel');p.locator('[data-commercial-return]').click();p.wait_for_selector('#commercial-root')
                        for destination in ('pipeline','grants','settings','overview'):
                            p.locator('.navitem[data-view="'+destination+'"]').click();p.wait_for_timeout(200)
                        assert p.locator('#commercial-root').count()==1
                        results.append({'width':width,'overflow':False,'flow':'filters, dossier, CRM, contact, discard/restore, start/stop/resume, legacy, navigation','passed':True});context.close()
                finally:browser.close()
        finally:http.shutdown();http.server_close();thread.join()
    assert not errors,errors
    report={'checks':results,'javascript_errors':errors,'external_network':'Denied by proxy + route guard','real_workers':False}
    (output/'phase-2.1-ux.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
