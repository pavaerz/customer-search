"""Offline Phase 3A.1 browser acceptance: temporary DB/server; all workers mocked.

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
        from sales.commercial.coordinator import Coordinator
        Coordinator(store,campaign).offer('FREELANCE',{'url':'https://instagram.com/p/fixture/','title':'Cerchiamo sviluppatore web freelance'},{'query':'fixture offline','provider':'serper','region':'Veneto'})
        from sales.commercial.social import inspect_social
        with patch('sales.commercial.social.PublicSocialWeb.get',side_effect=ValueError('robots: accesso vietato')):
            social=inspect_social(store,{'commercial_engine':'FREELANCE','url':'https://instagram.com/p/fixture/','social':'instagram'})
        social['result']['discovery']={'source':'instagram','title':'Alfa: cerchiamo sviluppatore freelance','snippet':'Collaborazione con partita IVA · fixture sintetica','query':'fixture offline Instagram'}
        social_id=Opportunities(store).save(campaign,social['identity'],social['documents'],social['result'])
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
                        projection=p.evaluate("""() => {
                            const statuses=['running','waiting','stopping'];
                            const stops=statuses.map(status=>campaignActions({commercial:true,status,resume_available:false}).includes('data-research-action="stop"'));
                            const saved=S.campaign;
                            S.campaign={...saved,commercial:true,status:'paused',resume_available:false,resume_reason:'Quote esaurite: nuova campagna necessaria.',message:'Ricerca sospesa: puoi riprendere.'};
                            const projected= commercialProgress();
                            const action=campaignActions(S.campaign);
                            const old={...S,campaign:saved};updateResearchState(old);
                            const updated=document.querySelector('#commercial-progress').textContent;
                            S.campaign=saved;updateResearchState({...S,campaign:{...saved,status:'paused',resume_available:false}});
                            const fixture={planner_coverage:[{engine:'FREELANCE',total_families:3,tried_families:1,remaining_families:['site:linkedin.com/jobs/ freelance {region}','<img src=x onerror=alert(1)>'],sources_tried:['web'],sources_remaining:['instagram','linkedin']} ]};
                            const coverage=document.createElement('div');coverage.innerHTML=commercialCoverage(fixture);
                            return {stops,projected,updated,action,remaining:coverage.textContent,images:coverage.querySelectorAll('img').length,list:coverage.querySelectorAll('.commercial-query-families li').length};
                        }""")
                        assert all(projection['stops']),projection
                        assert 'puoi riprendere' not in projection['projected'] and 'Quote esaurite' in projection['updated'],projection
                        assert 'data-research-action="resume"' not in projection['action'],projection
                        assert '2 ancora da esplorare' in projection['remaining'] and projection['images']==0 and projection['list']==2,projection
                        overflow=p.evaluate('document.documentElement.scrollWidth>innerWidth+1');assert not overflow,('overflow',width)
                        p.locator('[data-commercial-view="discovery"]').click();expect(p.locator('.commercial-card')).to_have_count(1)
                        expect(p.locator('.commercial-card')).to_contain_text('Non è una qualifica commerciale')
                        p.locator('[data-commercial-filter="source"]').select_option('linkedin');p.wait_for_selector('.empty')
                        p.locator('[data-commercial-filter="source"]').select_option('instagram');expect(p.locator('.commercial-card')).to_have_count(1)
                        p.locator('[data-commercial-filter="source"]').select_option('');p.locator('[data-commercial-view="opportunities"]').click();expect(p.locator('.commercial-card')).to_have_count(3)
                        p.locator('[data-commercial-filter="state"]').select_option('review')
                        p.locator('[data-commercial-filter="source"]').select_option('instagram');expect(p.locator('.commercial-card')).to_have_count(1)
                        p.locator('[data-commercial-detail]').first.click();p.wait_for_selector('#detail[open]')
                        expect(p.locator('.commercial-social-review')).to_contain_text('Collaborazione con partita IVA')
                        p.locator('#commercial-review-status').select_option('interesting');p.locator('#commercial-review-notes').fill('Nota di revisione sintetica: approfondire la fonte ufficiale.')
                        p.locator('[data-commercial-social-save]').click();expect(p.locator('.commercial-social-review')).to_contain_text('Storico delle revisioni manuali')
                        assert Opportunities(store).get(social_id)['state']=='UNVERIFIABLE'
                        p.locator('#detail [data-close]').click()
                        p.locator('[data-commercial-filter="social_review"]').select_option('interesting');expect(p.locator('.commercial-card')).to_have_count(1)
                        p.locator('[data-commercial-filter="social_review"]').select_option('');p.locator('[data-commercial-filter="source"]').select_option('');p.locator('[data-commercial-filter="state"]').select_option('useful');expect(p.locator('.commercial-card')).to_have_count(3)
                        p.locator('.commercial-activity > summary').click()
                        p.get_by_text('Copertura delle strategie e tracciamento',exact=True).click()
                        p.get_by_text('Limiti della campagna e consumo per motore',exact=True).click()
                        expect(p.locator('#commercial-activity')).to_contain_text('Non rappresentano il saldo')
                        assert not p.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                        p.locator('.commercial-activity > summary').click()
                        p.locator('.commercial-setup summary').click()
                        for checkbox in p.locator('[data-commercial-region]').all():
                            if checkbox.get_attribute('data-commercial-region') not in ('Veneto','Lombardia'):checkbox.uncheck()
                        p.locator('#commercial-mode').select_option('pilot')
                        p.locator('.commercial-setup summary').click()
                        p.screenshot(path=str(output/f'phase-3a1-{width}.png'),full_page=True)
                        p.locator('[data-commercial-engine="AGENCIES"]').click();expect(p.locator('.commercial-card')).to_have_count(1)
                        p.locator('[data-commercial-detail]').click();p.wait_for_selector('#detail[open]');p.locator('#detail [data-close]').click();assert not p.locator('#detail').evaluate('(e)=>e.open')
                        p.locator('[data-commercial-action="save"]').click();expect(p.locator('.commercial-card')).to_contain_text('Salvata nei contatti')
                        p.locator('[data-commercial-detail]').click();p.wait_for_selector('[data-commercial-crm]');p.locator('[data-commercial-crm]').click();p.wait_for_selector('#detail [data-tab="manage"]');p.locator('#detail [data-close]').click()
                        if width==1440:
                            p.locator('[data-commercial-action="contacted"]').click();p.wait_for_selector('.commercial-card.is-contacted')
                        p.locator('[data-commercial-action="discard"]').click();p.wait_for_selector('.empty')
                        p.locator('[data-commercial-filter="include_discarded"]').check();p.wait_for_selector('[data-commercial-action="restore"]');p.locator('[data-commercial-action="restore"]').click();p.wait_for_selector('[data-commercial-action="discard"]')
                        p.locator('[data-commercial-filter="search"]').fill('nessun-risultato-fixture');p.wait_for_selector('.empty');p.locator('[data-commercial-filter="search"]').fill('');p.wait_for_selector('.commercial-card')
                        p.locator('[data-research-action="start"]').click();p.wait_for_selector('[data-research-action="stop"]');assert len(rs.campaign()['filters']['commercial_engines'])==4;assert rs.campaign()['filters']['regions']==['Veneto','Lombardia'];assert rs.campaign()['filters']['mode']=='pilot'
                        p.locator('[data-research-action="stop"]').click();p.wait_for_selector('[data-research-action="resume"]');p.locator('[data-research-action="resume"]').click();p.wait_for_selector('[data-research-action="stop"]');p.locator('[data-research-action="stop"]').click();p.wait_for_selector('[data-research-action="resume"]')
                        p.locator('[data-commercial-legacy]').click();p.wait_for_selector('.campaign-panel');p.locator('[data-commercial-return]').click();p.wait_for_selector('#commercial-root')
                        for destination in ('pipeline','grants','settings','overview'):
                            p.locator('.navitem[data-view="'+destination+'"]').click();p.wait_for_timeout(200)
                        assert p.locator('#commercial-root').count()==1
                        results.append({'width':width,'overflow':False,'flow':'social review/evidence/history/filter, coverage, budgets, filters, dossier, CRM, contact, discard/restore, start/stop/resume, legacy, navigation','passed':True});context.close()
                finally:browser.close()
        finally:http.shutdown();http.server_close();thread.join()
    assert not errors,errors
    report={'checks':results,'javascript_errors':errors,'external_network':'Denied by proxy + route guard','real_workers':False}
    (output/'phase-3a1-ux.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
