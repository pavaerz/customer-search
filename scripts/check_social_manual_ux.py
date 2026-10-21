"""Offline browser check: manual links only; never launches a campaign."""
import json
import tempfile
import threading
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright,expect
from sales import server
from sales.db import Store
from sales.engines import EngineManager
from sales.campaigns import CampaignManager
from sales.safe_proxy import SafeProxy


def main():
    errors=[];checks=[]
    with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
        store=Store(Path(tmp)/'ui.db');store.init()
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        origin=f'http://127.0.0.1:{http.server_port}'
        for replacement in (
            patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),
            patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin),
            patch.object(CampaignManager,'launch',side_effect=AssertionError('No campaign')),
            patch('sales.agent6.ai.infer',side_effect=AssertionError('No model')),
            patch('sales.safe_proxy.public_addresses',side_effect=ValueError('No external access')),
        ):stack.enter_context(replacement)
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
                        page.goto(origin)
                        page.locator('[data-agent7-mode="RESEARCH"]').first.click()
                        field=page.locator('#agent6-social-urls')
                        expect(field).to_have_value('')
                        expect(page.locator('[data-agent6-flow="SOCIAL"]')).not_to_be_checked()
                        field.fill('https://www.instagram.com/p/ExampleRequest/?igsh=viewer')
                        expect(page.locator('[data-agent6-flow="SOCIAL"]')).to_be_checked()
                        page.locator('[data-agent6="preview"]').click()
                        expect(page.locator('#agent6-preview')).to_contain_text('1 link social')
                        expect(page.locator('[data-agent6="start"]')).to_have_count(1)
                        field.fill('https://www.linkedin.com/jobs/view/123456789/')
                        expect(page.locator('#agent6-preview')).to_be_empty()
                        expect(page.locator('[data-agent6="start"]')).to_have_count(0)
                        # Changing views keeps unsent input, but refresh starts a
                        # fresh form. Neither interaction starts backend work.
                        page.locator('[data-agent7-mode="WORKLIST"]').first.click()
                        page.locator('[data-agent7-mode="RESEARCH"]').first.click()
                        expect(field).to_have_value('https://www.linkedin.com/jobs/view/123456789/')
                        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                        page.screenshot(path=f'/tmp/customersearch-social-manual-{width}.png',full_page=True)
                        page.reload()
                        page.locator('[data-agent7-mode="RESEARCH"]').first.click()
                        expect(field).to_have_value('')
                        checks.append({'width':width,'selects_social':True,'preview_invalidated':True,
                                       'refresh_clears_unsent_urls':True,'overflow':False})
                        context.close()
                finally:browser.close()
        finally:http.shutdown();http.server_close()
        with store.connect() as db:
            for table in ('campaigns','research_tasks','commercial_ai_executions','prospects'):
                assert db.execute('SELECT count(*) FROM '+table).fetchone()[0]==0,table
        assert not errors,errors
    print(json.dumps({'viewports':checks,'javascript_errors':errors,'external_calls':0,
                      'campaigns_started':0,'production_writes':0}))


if __name__=='__main__':main()
