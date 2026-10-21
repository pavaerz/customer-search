"""3B.3 local Chromium acceptance. Synthetic MOCK only, temporary DB, no real workers."""
import sys,json,tempfile,threading,os
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
from sales.commercial.ai import analyze,summary
from sales.commercial.ai_schema import unknown_output
from sales.commercial.ai_settings import read as read_ai
from sales.safe_proxy import SafeProxy
from playwright.sync_api import sync_playwright,expect


def main():
    output=Path('implementation-report');errors=[];results=[]
    with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
        store=Store(Path(temp)/'ux.db');store.init();rs=ResearchStore(store);repo=Opportunities(store)
        campaign=rs.create({'commercial_engines':list(ENGINES)})
        with patch('sales.commercial.inspection.ResearchWeb.get',lambda web,url:fixture('Cerchiamo sviluppatore WordPress freelance per progetto web.',url=url,date=False)):
            found=inspect(store,{'commercial_engine':'FREELANCE','url':'https://alfa.example/collabora-con-noi'})
        ident=repo.save(campaign,found['identity'],found['documents'],found['result'])
        assert repo.get(ident)['state']=='NEEDS_REVIEW'
        with patch('sales.commercial.inspection.ResearchWeb.get',lambda web,url:fixture('Siamo una web agency. Cerchiamo sviluppatore WordPress freelance per progetto web.',url=url)):
            agency=inspect(store,{'commercial_engine':'AGENCIES','url':'https://alfa.example/collabora-con-noi'})
        agency_id=repo.save(campaign,agency['identity'],agency['documents'],agency['result'])
        assert repo.get(agency_id)['state']=='VERIFIED'
        def mock(payload,config,check):
            o=unknown_output(payload);o['explanation']='Fixture AI sintetica <img src=x onerror=alert(1)>: prova temporale mancante.'
            return {'output':o}  # Provider cost remains UNKNOWN, never fabricated 0.
        advice=analyze(store,campaign,'FREELANCE',ident,found['result'],found['documents'],provider=mock,config={'enabled':True,'provider':'MOCK','mode':'shadow','model':'<img src=x onerror=alert(1)>'})
        assert advice['status']=='completed',advice
        from sales.commercial.rebuild import evaluate as rebuild,screen
        pages=[fixture('Produciamo componenti industriali.',url='https://alfa.example/')]
        rb=rebuild(found['identity'],pages,found['result']['geography'],screen(pages,[]),{'completed':True,'executed':True,'outcome':'completed','findings':[{'code':'mobile_content','severity':'major','quote':'Misura sintetica: contenuto tagliato a 390 px.','url':'https://alfa.example/','viewport':390},{'code':'obstructed_controls','severity':'major','quote':'Misura sintetica: controlli coperti a 390 px.','url':'https://alfa.example/contatti','viewport':390}],'links':[]})
        rb['identity']=found['identity'];repo.save(campaign,found['identity'],[],rb)
        rs.stop(campaign['id']);rs.paused(campaign['id'])
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin='http://127.0.0.1:'+str(http.server_port)
        for p in [patch.dict(os.environ,{'SERPER_API_KEY':'','CUSTOMERSEARCH_AI_API_KEY':''}),patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin),patch.object(CampaignManager,'launch',lambda manager,c:manager.rs.campaign(c['id'])),patch('sales.safe_proxy.public_addresses',side_effect=ValueError('Offline UI audit')),patch('sales.commercial.ai.infer',side_effect=AssertionError('No inference during UI save'))]:stack.enter_context(p)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            with SafeProxy() as proxy,sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True,proxy={'server':proxy.url,'bypass':'127.0.0.1'},args=['--disable-quic','--force-webrtc-ip-handling-policy=disable_non_proxied_udp'])
                try:
                    for width in (1440,390):
                        context=browser.new_context(viewport={'width':width,'height':950},service_workers='block')
                        context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin+'/') else route.abort())
                        p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));p.goto(origin);p.wait_for_selector('#commercial-root')
                        p.locator('.navitem[data-view="settings"]').click();form=p.locator('#commercial-ai-settings-form');expect(form).to_be_visible()
                        expect(form.locator('[name="enabled"]')).not_to_be_checked();expect(form.locator('[name="provider"]')).to_have_value('DISABLED')
                        assert form.locator('[name*="key"],input[type="password"]').count()==0
                        expect(p.locator('.commercial-ai-usage')).to_contain_text('Costo dichiarato: non disponibile')
                        assert not p.evaluate('document.documentElement.scrollWidth>innerWidth+1'),('settings overflow',width)
                        p.screenshot(path=str(output/f'phase-3b3-settings-{width}.png'),full_page=True)
                        # Save DISABLED, then MOCK, then LOCAL: no inference dispatch.
                        form.get_by_role('button',name='Salva impostazioni AI').click();expect(form.get_by_role('button')).to_be_enabled()
                        form.locator('[name="enabled"]').check();form.locator('[name="provider"]').select_option('MOCK')
                        with p.expect_response(lambda r:r.url.endswith('/api/commercial/ai-settings') and r.request.method=='POST') as response:form.get_by_role('button').click()
                        assert response.value.status==200;assert read_ai(store)['provider']=='MOCK'
                        form.locator('[name="provider"]').select_option('LOCAL');form.locator('[name="model"]').fill('fixture-model-not-installed')
                        form.locator('[name="endpoint"]').fill('http://127.0.0.1:11434/api/chat')
                        with p.expect_response(lambda r:r.url.endswith('/api/commercial/ai-settings') and r.request.method=='POST') as response:form.get_by_role('button').click()
                        assert response.value.status==200;assert read_ai(store)['provider']=='LOCAL';assert summary(store,campaign['id'])['calls']==1
                        form.locator('summary').click();form.locator('[name="timeout"]').fill('0');assert not form.evaluate('(f)=>f.checkValidity()')
                        form.locator('[name="timeout"]').fill('30')
                        invalid=p.evaluate("""async()=>{const r=await fetch('/api/commercial/ai-settings',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':S.csrf},body:JSON.stringify({enabled:false,provider:'DISABLED',max_concurrent_requests:0})});return {status:r.status,body:await r.json()}}""")
                        assert invalid['status']==400,invalid;assert read_ai(store)['provider']=='LOCAL'
                        form.locator('[name="enabled"]').uncheck();form.locator('[name="provider"]').select_option('DISABLED');form.locator('[name="model"]').fill('');form.locator('[name="endpoint"]').fill('')
                        with p.expect_response(lambda r:r.url.endswith('/api/commercial/ai-settings') and r.request.method=='POST') as response:form.get_by_role('button').click()
                        assert response.value.status==200;assert not read_ai(store)['enabled']
                        p.locator('.navitem[data-view="overview"]').click();p.wait_for_selector('#commercial-root')
                        p.locator('[data-commercial-filter="state"]').select_option('NEEDS_REVIEW');expect(p.locator('.commercial-card')).to_have_count(1)
                        p.locator('[data-commercial-detail]').first.click();p.wait_for_selector('#detail[open]')
                        ai=p.locator('.commercial-ai-assessment');expect(ai).to_contain_text('Decisione ufficiale: Da verificare');expect(ai).to_contain_text('Valutazione AI · Shadow');expect(ai).to_contain_text('Risposta simulata');expect(ai).to_contain_text('Controllo delle prove: VALID');expect(ai).to_contain_text('Prove inviate all’AI')
                        expect(ai).to_contain_text('<img src=x onerror=alert(1)>');assert ai.locator('img').count()==0
                        ai.get_by_text('Evidenze e differenze',exact=True).click();expect(ai).to_contain_text('Evidenze e differenze');assert not p.evaluate('document.documentElement.scrollWidth>innerWidth+1'),('detail overflow',width)
                        p.screenshot(path=str(output/f'phase-3b3-ai-{width}.png'),full_page=True)
                        p.locator('#detail [data-close]').click()
                        # Existing qualified lead continues through the same CRM.
                        p.locator('[data-commercial-filter="state"]').select_option('VERIFIED');expect(p.locator('.commercial-card')).to_have_count(1)
                        p.locator('.commercial-card [data-commercial-action="save"]').click();expect(p.locator('.commercial-card')).to_contain_text('Salvata nei contatti')
                        if width==1440:p.locator('.commercial-card [data-commercial-action="contacted"]').click();p.wait_for_selector('.commercial-card.is-contacted')
                        p.locator('.commercial-card [data-commercial-action="discard"]').click();p.wait_for_selector('.empty')
                        p.locator('[data-commercial-filter="include_discarded"]').check();p.wait_for_selector('[data-commercial-action="restore"]');p.locator('.commercial-card [data-commercial-action="restore"]').click();p.wait_for_selector('[data-commercial-action="discard"]')
                        assert repo.get(ident)['state']=='NEEDS_REVIEW';assert summary(store,campaign['id'])['calls']==1
                        p.locator('[data-commercial-filter="state"]').select_option('POTENTIAL');expect(p.locator('.commercial-card')).to_have_count(1)
                        p.locator('[data-commercial-detail]').first.click();p.wait_for_selector('#detail[open]')
                        website=p.locator('#detail .commercial-website-summary');expect(website).to_contain_text('dominio verificato');expect(website).to_contain_text('Valutazione commerciale consultiva:');expect(website).to_contain_text('Non modifica lo stato ufficiale.')
                        assert not p.evaluate('document.documentElement.scrollWidth>innerWidth+1'),('website detail overflow',width)
                        p.screenshot(path=str(output/f'phase-3b3-website-{width}.png'),full_page=True);p.locator('#detail [data-close]').click()
                        results.append({'width':width,'passed':True,'overflow':False,'checks':['AI default disabled','settings DISABLED/MOCK/LOCAL saved without inference','client/server limits validation','no API key field','unknown provider cost distinct from zero','official NEEDS_REVIEW vs MOCK shadow','AI HTML escaped','CRM save/contact/discard/restore','verified domain visible','consultative commercial labels separated from official state','website dossier without overflow']});context.close()
                finally:browser.close()
        finally:http.shutdown();http.server_close();thread.join()
    assert not errors,errors
    report={'checks':results,'javascript_errors':errors,'external_network':'Denied by proxy + route guard','real_workers':False,'mock_inferences':1,'real_ai_inferences':0}
    (output/'phase-3b3-ux.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
