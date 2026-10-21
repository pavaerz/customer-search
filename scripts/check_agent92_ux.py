"""Local UI acceptance using saved NHW evidence; no real campaign or network."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.replay_agent92 import load,replay
from sales import server
from sales.db import Store
from sales.engines import EngineManager
from sales.campaigns import CampaignManager
from sales.research_store import ResearchStore
from sales.agent6 import FLOWS,memory
from sales.safe_proxy import SafeProxy
from playwright.sync_api import sync_playwright,expect


def main():
    fixture=load();checks=[];errors=[]
    with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
        store=Store(Path(tmp)/'offline.db');store.init();rs=ResearchStore(store)
        c=rs.create({'agent_version':'6.0','commercial_engines':list(FLOWS),'mode':'extended',
                     'commercial':{'ai':{'enabled':True,'provider':'MOCK'}}})
        b=replay(fixture['cases'][0],fixture['configuration']['regions'])
        rid=memory.save_record(store,c,'AGENCIES',b)
        rs.stop(c['id']);rs.paused(c['id'])
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
        for p in (patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),
            patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin),
            patch.object(CampaignManager,'launch',side_effect=AssertionError('No campaign')),
            patch('sales.agent6.ai.infer',side_effect=AssertionError('No model')),
            patch('sales.safe_proxy.public_addresses',side_effect=ValueError('No external access'))):stack.enter_context(p)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            with SafeProxy() as proxy,sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True,
                    proxy={'server':proxy.url,'bypass':'127.0.0.1'},args=['--disable-quic'])
                try:
                    for width in (1440,390):
                        context=browser.new_context(viewport={'width':width,'height':1000},service_workers='block')
                        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(origin+'/') else r.abort())
                        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(origin);expect(page.locator('h1')).to_have_text('Chi contattare oggi')
                        page.locator('[data-agent7-view="promising"]').click()
                        card=page.locator('.agent7-card');expect(card).to_have_count(1)
                        expect(card).to_contain_text('NHW Consulting')
                        expect(card).to_contain_text('Pista promettente')
                        expect(card).to_contain_text('incarico attivo, compenso e volume di lavoro non confermati')
                        expect(card).to_contain_text('Non dichiarato, non obbligatorio')
                        expect(card).to_contain_text('info@nhwconsulting.it')
                        page.locator('[data-agent6="dossier"]').click()
                        expect(page.locator('#agent6-detail-'+str(rid))).to_contain_text('Cerchiamo collaboratori')
                        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                        page.screenshot(path=f'/tmp/customersearch92-nhw-{width}.png',full_page=True)
                        checks.append({'width':width,'saved_original_dossier':True,'honest_incomplete_lead':True,'overflow':False})
                        context.close()
                finally:browser.close()
        finally:http.shutdown();http.server_close()
        with store.connect() as db:
            assert db.execute('select count(*) from prospects').fetchone()[0]==0
            assert db.execute('select count(*) from commercial_ai_executions').fetchone()[0]==0
        assert not errors,errors
    print(json.dumps({'viewports':checks,'javascript_errors':errors,'external_calls':0,'production_writes':0}))


if __name__=='__main__':main()
