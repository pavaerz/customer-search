"""Offline desktop/mobile acceptance on a disposable DB; no live campaigns."""
import json
import sys
import tempfile
import threading
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from sales import server
from sales.db import Store,now
from sales.engines import EngineManager
from sales.campaigns import CampaignManager
from sales.research_store import ResearchStore
from sales.agent6 import memory
from sales.safe_proxy import SafeProxy
from test_agent6 import evaluated
from playwright.sync_api import sync_playwright,expect


def main():
    checks=[];errors=[]
    with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
        store=Store(Path(tmp)/'offline.db');store.init();rs=ResearchStore(store)
        campaign=rs.create({'agent_version':'6.0','commercial_engines':['AZIENDE','AGENCIES','STARTUPS'],'mode':'extended','commercial':{'ai':{'enabled':True,'provider':'MOCK'}}})
        body={**evaluated(),'checked_at':now(),'freshness':{'status':'RECENT','published_at':now()[:10],'basis':'synthetic_fixture'}}
        body['social_source']={'url':'https://mastodon.social/@alfa/123','status':'PUBLIC_POST_READ',
            'original_read':True,'published_at':now()[:10],'official_identity_link':{'verified':True}}
        body['news_correlation']={'source_url':'https://press.example/alfa','identity_linked':True,
            'published_at':now()[:10],'event_date':None,'event_current':True,
            'relation':'Ipotesi sintetica: nuova offerta e percorso catalogo interrotto.'}
        from sales.agent6.website_audit import audit
        body['website_audit']=audit([{'url':'https://alfa.example/','status':200,'checked_at':now(),
            'html':'<title>Alfa Srl</title><h1>Alfa Srl</h1><a href="https://shop.example/">Negozio online</a>'}])
        rid=memory.save_record(store,campaign,'AGENCIES',body)
        memory.save_record(store,campaign,'AGENCIES',{**body,'url':'https://alfa.example/second','state':'NEEDS_REVIEW'})
        rs.stop(campaign['id']);rs.paused(campaign['id'])
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
        for p in [patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),
                  patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin),
                  patch.object(CampaignManager,'launch',side_effect=AssertionError('No live campaign')),
                  patch('sales.agent6.ai.infer',side_effect=AssertionError('No inference')),
                  patch('sales.safe_proxy.public_addresses',side_effect=ValueError('External access forbidden'))]:stack.enter_context(p)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            with SafeProxy() as proxy,sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True,proxy={'server':proxy.url,'bypass':'127.0.0.1'},args=['--disable-quic'])
                try:
                    for width in (1440,390):
                        ctx=browser.new_context(viewport={'width':width,'height':1000},service_workers='block')
                        ctx.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin+'/') else route.abort())
                        page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(origin);expect(page.locator('h1')).to_have_text('Chi contattare oggi')
                        expect(page.locator('[data-agent7-count="review"]')).to_have_text('1')
                        if width==1440:
                            page.locator('[data-agent7-view="promising"]').click()
                            expect(page.locator('.agent7-card')).to_have_count(1)
                            expect(page.locator('.agent7-card')).to_contain_text('Pista promettente')
                            expect(page.locator('.agent7-card')).to_contain_text('Riscontri disponibili:')
                            page.locator('summary',has_text='Filtra per progetto').click()
                            page.locator('[data-agent8-filter="contact"]').check()
                            expect(page.locator('.agent7-card')).to_have_count(1)
                            page.locator('[data-agent8-filter="contact"]').uncheck()
                            page.locator('summary',has_text='Filtra per progetto').click()
                            page.locator('[data-agent7-view="ready"]').click()
                            expect(page.locator('.agent7-card')).to_contain_text('Alfa Srl')
                            expect(page.locator('.agent7-card')).to_contain_text('info@alfa.example')
                            page.locator('[data-agent6="dossier"]').click();expect(page.locator('#agent6-detail-'+str(rid))).to_contain_text('caratteri')
                            expect(page.locator('#agent6-detail-'+str(rid))).to_contain_text('2 richieste o segnali')
                            expect(page.locator('#agent6-detail-'+str(rid))).to_contain_text('Stesso dominio ufficiale verificato')
                            page.locator('[data-agent8-related]').click()
                            expect(page.locator('#agent6-detail-'+str(rid))).to_contain_text('Valutazione selezionata')
                            page.locator('[data-agent8-related]').click()
                            assert page.evaluate('new Set([...document.querySelectorAll("[id]")].map(e=>e.id)).size===document.querySelectorAll("[id]").length')
                            page.locator('[data-agent8-correct]').first.click()
                            page.locator('#agent8-edit-priority-'+str(rid)).select_option('low')
                            page.locator('#agent8-edit-note-'+str(rid)).fill('Fixture offline: priorità commerciale bassa, prove conservate.')
                            page.locator('[data-agent8-correction-save]').click()
                            expect(page.locator('.agent7-card')).to_contain_text('Valutazione corretta manualmente')
                            page.locator('summary',has_text='Filtra per progetto').click()
                            page.locator('[data-agent8-filter="priority"]').select_option('high')
                            expect(page.locator('.agent7-card')).to_have_count(0)
                            page.locator('[data-agent8-filter="priority"]').select_option('low')
                            expect(page.locator('.agent7-card')).to_have_count(1)
                            page.locator('[data-agent8-filter="priority"]').select_option('')
                            page.locator('[data-agent7-contact]').click()
                            expect(page.locator('[data-agent7-count="ready"]')).to_have_text('0')
                        page.locator('[data-agent7-view="contacted"]').click()
                        expect(page.locator('.agent7-card')).to_have_class(__import__('re').compile('is-contacted'))
                        expect(page.locator('.agent9-audit-warning')).to_contain_text('Audit incompleto')
                        page.locator('summary',has_text='Motivazioni e limiti della valutazione').click()
                        expect(page.locator('.agent7-card')).to_contain_text('Intenzione di acquisto')
                        expect(page.locator('.agent7-card')).to_contain_text('non la probabilità di ottenere il cliente')
                        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                        page.screenshot(path=f'/tmp/customersearch9-worklist-{width}.png',full_page=True)
                        page.evaluate('scrollTo(0,0)')
                        page.screenshot(path=f'/tmp/customersearch9-worklist-viewport-{width}.png')
                        page.locator('summary',has_text='Motivazioni e limiti della valutazione').click()
                        page.locator('.agent7-card summary',has_text='Audit del sito').click()
                        expect(page.locator('.agent7-card')).to_contain_text('Soluzioni esterne collegate dal sito')
                        expect(page.locator('.agent7-card')).to_contain_text('contenuto non verificato')
                        page.locator('.agent7-card summary',has_text='Verifica della fonte social').click()
                        expect(page.locator('.agent7-card')).to_contain_text('collegamento aziendale verificato')
                        page.locator('.agent7-card summary',has_text='Evento aziendale e verifica del sito').click()
                        expect(page.locator('.agent7-card')).to_contain_text('Data dell’evento: non verificata')
                        expect(page.locator('.agent7-card')).to_contain_text('Ipotesi sintetica: nuova offerta')
                        page.locator('#agent7-search').fill('missing company');expect(page.locator('.agent7-card')).to_have_count(0)
                        page.locator('#agent7-search').fill('Alfa');expect(page.locator('.agent7-card')).to_have_count(1)
                        page.locator('[data-agent6="review"]').click()
                        page.locator('#agent6-outcome-'+str(rid)).select_option('false_positive')
                        page.locator('#agent6-note-'+str(rid)).fill('Synthetic review: request attribution contested.')
                        page.locator('[data-agent6="feedback"]').click()
                        expect(page.locator('.agent7-warning')).to_contain_text('Qualifica contestata')
                        page.locator('[data-agent6="intelligence"]').click()
                        expect(page.locator('#agent6-intelligence')).to_contain_text('1 falsi positivi')
                        page.locator('[data-agent6="review"]').click()
                        page.locator('#agent6-outcome-'+str(rid)).select_option('quality_confirmed')
                        page.locator('#agent6-note-'+str(rid)).fill('Synthetic review: original evidence confirmed.')
                        page.locator('[data-agent6="feedback"]').click()
                        expect(page.locator('.agent7-warning')).to_have_count(0)
                        page.locator('[data-agent6="review"]').click()
                        page.locator('#agent6-outcome-'+str(rid)).select_option('replied')
                        page.locator('#agent6-note-'+str(rid)).fill('<script>window.bad=true</script>')
                        page.locator('[data-agent6="feedback"]').click()
                        page.locator('#agent7-view').select_option('replied');expect(page.locator('.agent7-card')).to_have_count(1)
                        page.locator('[data-agent6="intelligence"]').click();expect(page.locator('#agent6-intelligence')).to_contain_text('Memoria e apprendimento')
                        assert not page.evaluate('window.bad===true')
                        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                        page.screenshot(path=f'/tmp/customersearch7-worklist-{width}.png',full_page=True)
                        page.locator('[data-agent7-mode="RESEARCH"]').first.click()
                        expect(page.locator('#agent6-setup-title')).to_contain_text('Dove vuoi cercare')
                        expect(page.locator('[data-agent6-flow]')).to_have_count(5)
                        expect(page.locator('[data-agent6-flow="SOCIAL"]')).to_have_count(1)
                        page.locator('[data-agent6="preview"]').click();expect(page.locator('#agent6-preview')).to_contain_text('Riepilogo prima di avviare')
                        for checkbox in page.locator('[data-agent6-flow]').all():checkbox.uncheck()
                        expect(page.locator('[data-agent6="preview"]')).to_be_disabled()
                        page.locator('[data-agent6-flow="AGENCIES"]').focus();page.keyboard.press('Space')
                        expect(page.locator('[data-agent6="preview"]')).to_be_enabled()
                        page.evaluate("S.campaign.running=true;updateResearchState(S)")
                        expect(page.locator('[data-agent6="stop"]')).to_be_visible()
                        expect(page.locator('[data-agent6="preview"]')).to_be_disabled()
                        page.locator('#agent6-progress summary').click();page.evaluate('updateResearchState(S)')
                        expect(page.locator('#agent6-progress details')).to_have_attribute('open','')
                        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                        page.screenshot(path=f'/tmp/customersearch7-research-{width}.png',full_page=True)
                        page.locator('[data-agent7-mode="WORKLIST"]').click();page.locator('#agent7-view').select_option('replied')
                        expect(page.locator('.agent7-card')).to_have_count(1)
                        if width==1440:
                            # Retain the contacted state for the mobile scenario.
                            memory.feedback(store,rid,'contacted')
                        else:
                            page.locator('[data-agent7-delete]').click()
                            expect(page.locator('.agent7-card')).to_have_count(0)
                            # Preserve the existing company-wide manual exclusion.
                            page.locator('#agent7-view').select_option('excluded');expect(page.locator('.agent7-card')).to_have_count(1)
                        checks.append({'width':width,'passed':True});ctx.close()
                finally:browser.close()
        finally:http.shutdown();http.server_close()
        with store.connect() as c:
            assert c.execute('SELECT count(*) FROM campaigns').fetchone()[0]==1
            assert c.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0]==0
        assert not errors,errors
    print(json.dumps({'viewports':checks,'javascript_errors':errors,'paid_calls':0,'live_campaigns':0,'production_writes':0}))


if __name__=='__main__':main()
