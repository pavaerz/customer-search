"""Real local Chromium against a temporary database populated from saved fixtures."""
import sys,json,tempfile,threading,os,hashlib
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_commercial40 import load
from sales import server
from sales.db import Store,encode
from sales.engines import EngineManager
from sales.research_store import ResearchStore
from sales.campaigns import CampaignManager
from sales.commercial.catalog import ENGINES
from sales.safe_proxy import SafeProxy
from playwright.sync_api import sync_playwright,expect

def main():
    out=Path('implementation-report');errors=[];checks=[];x=load()
    with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
        store=Store(Path(temp)/'ux.db');store.init();rs=ResearchStore(store);campaign=rs.create({'commercial_engines':list(ENGINES)})
        for r in sorted(x['commercial_revisions'],key=lambda r:r['id']):
            b=r['body'];entity=rs.entity(b['identity'])
            with store.connect() as c:
                c.execute('INSERT OR IGNORE INTO commercial_opportunities(id,entity_id,engine,opportunity_key,created_at) VALUES (?,?,?,?,?)',(r['opportunity_id'],entity,b['engine'],str(r['opportunity_id']),r['created_at']))
                c.execute('INSERT INTO commercial_revisions VALUES(?,?,?,?,?,?,?,?)',(r['id'],r['opportunity_id'],campaign['id'],r['fingerprint'],r['state'],r['score'],encode(b),r['created_at']))
                c.execute('UPDATE commercial_opportunities SET latest_revision=? WHERE id=?',(r['id'],r['opportunity_id']))
        for d in x['documents']:
            with store.connect() as c:c.execute('INSERT OR IGNORE INTO research_documents VALUES (?,?,?,?,?,?,?,?,?)',(d['id'],d['url'],d['content_hash'],d['title'],d['text'],d['published_at'],d['checked_at'],d['provider'],encode(d['details'])))
        rs.stop(campaign['id']);rs.paused(campaign['id'])
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
        for p in [patch.dict(os.environ,{'SERPER_API_KEY':'','CUSTOMERSEARCH_AI_API_KEY':''}),patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin),patch.object(CampaignManager,'launch',side_effect=AssertionError('No campaign permitted')),patch('sales.safe_proxy.public_addresses',side_effect=ValueError('Offline UI')),patch('sales.commercial.ai.infer',side_effect=AssertionError('No inference'))]:stack.enter_context(p)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            with SafeProxy() as proxy,sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True,proxy={'server':proxy.url,'bypass':'127.0.0.1'},args=['--disable-quic'])
                try:
                    for width in (1440,390):
                        ctx=browser.new_context(viewport={'width':width,'height':950},service_workers='block');ctx.route('**/*',lambda r:r.continue_() if r.request.url.startswith(origin+'/') else r.abort())
                        p=ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)));p.goto(origin);p.wait_for_selector('.commercial-first')
                        expect(p.locator('.commercial-first').filter(has_text='Apiceweb')).to_have_count(1)
                        expect(p.locator('.commercial-first').filter(has_text='Parklab')).to_have_count(1)
                        pacer=p.locator('.commercial-first').filter(has_text='Pacer');expect(pacer).to_have_count(1);expect(pacer).to_contain_text('Dominio ufficiale da verificare');expect(pacer).not_to_contain_text('support@');expect(pacer).not_to_contain_text('BEBEE PLATFORM SL')
                        expect(p.locator('.commercial-first').filter(has_text='Olivi')).to_have_count(1);expect(p.locator('.commercial-first').filter(has_text='Olivi')).to_contain_text('bisogno digitale non dimostrato');expect(p.locator('.commercial-first').filter(has_text='Olivi')).to_contain_text('Problemi tecnici confermati: 0')
                        assert not p.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                        p.screenshot(path=str(out/f'phase43-cards-{width}.png'),full_page=True)
                        pacer.locator('[data-commercial-detail]').click();p.wait_for_selector('#detail[open]');expect(p.locator('#detail-title')).to_have_text('Pacer');assert not p.evaluate('document.documentElement.scrollWidth>innerWidth+1');p.locator('[data-close]').click()
                        p.locator('[data-commercial-filter="commercial_status"]').select_option('NOT_ACTIONABLE');expect(p.locator('.commercial-first').filter(has_text='Apiceweb')).to_have_count(0)
                        p.locator('[data-commercial-filter="commercial_status"]').select_option('READY_TO_CONTACT');expect(p.locator('.commercial-first')).to_have_count(1);expect(p.locator('.commercial-first')).to_contain_text('Parklab')
                        p.locator('[data-commercial-filter="commercial_status"]').select_option('actionable');p.locator('[data-commercial-filter="opportunity_type"]').select_option('OUTBOUND_PROSPECT');expect(p.locator('.commercial-first').filter(has_text='Olivi')).to_have_count(1);expect(p.locator('.commercial-first').filter(has_text='Olivi')).to_contain_text('bisogno digitale non dimostrato');expect(p.locator('.commercial-first').filter(has_text='Olivi')).to_contain_text('Problemi tecnici confermati: 0');expect(p.locator('.commercial-first').filter(has_text='Apiceweb')).to_have_count(0)
                        p.locator('[data-commercial-filter="opportunity_type"]').select_option('');p.locator('[data-commercial-filter="state"]').select_option('NEEDS_REVIEW');expect(p.locator('.commercial-first')).to_have_count(5)
                        p.locator('[data-commercial-filter="state"]').select_option('');p.locator('[data-commercial-filter="commercial_status"]').select_option('READY_TO_CONTACT')
                        expect(p.locator('.commercial-first')).to_have_count(1)
                        checks.append({'width':width,'passed':True,'checks':['default useful advisory cards','PACER distinct from publisher','outbound without audit','official status preserved','filters','dossier','explicit company/need/technical evidence distinction']});ctx.close()
                finally:browser.close()
        finally:http.shutdown();http.server_close();thread.join()
    assert not errors,errors
    result={'checks':checks,'javascript_errors':errors,'external_calls':0,'production_writes':0,'real_campaigns':0,'real_ai_calls':0,'scope':'saved fixtures loaded into temporary DB; local browser only'}
    (out/'phase43-ux.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
