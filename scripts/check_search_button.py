"""Exercise every search entry point with the real API and an isolated database."""
import json
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from sales import server
from sales.campaigns import CampaignManager
from sales.db import Store
from sales.engines import EngineManager
from sales.research_store import ResearchStore


def launch(manager, campaign):
    # Keep HTTP persistence real, without contacting outside companies in a UI test.
    time.sleep(.4)
    return manager.rs.campaign(campaign['id'])


def run():
    checks = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        for width in (390, 1440):
            with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
                store = Store(Path(tmp) / 'buttons.sqlite3')
                store.init()
                rs = ResearchStore(store)
                http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
                origin = f'http://127.0.0.1:{http.server_port}'
                for obj, key, value in [(server, 'STORE', store), (server, 'MANAGER', EngineManager(store)), (server, 'PORT', http.server_port), (server, 'ORIGIN', origin), (CampaignManager, 'launch', launch)]:
                    stack.enter_context(patch.object(obj, key, value))
                threading.Thread(target=http.serve_forever, daemon=True).start()
                page = browser.new_page(viewport={'width': width, 'height': 900})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                try:
                    page.goto(origin)
                    page.wait_for_selector('[data-research-action=start]')
                    page.locator('[data-view=legacy]').first.click()
                    # An API error must be visible and allow a retry.
                    page.route('**/api/campaigns', lambda route: route.fulfill(status=400, content_type='application/json', body=json.dumps({'error': 'Avvio non disponibile: prova di errore'})), times=1)
                    page.get_by_role('button', name='Cerca clienti').click()
                    page.wait_for_function("() => document.querySelector('#toast').textContent.includes('prova di errore')")
                    assert rs.campaign() is None
                    assert page.locator('[data-research-action=start]').is_enabled()
                    # A single click from Contacts must create a campaign, not just focus.
                    page.locator('[data-view=legacy]').first.click()
                    page.get_by_role('button', name='Cerca clienti').click()
                    page.wait_for_function("() => document.querySelector('#toast').textContent==='Avvio della ricerca…'")
                    assert page.locator('[data-research-action=start]').is_disabled()
                    # A repeated request during the pending start cannot release the guard.
                    page.evaluate("() => { researchDialog(); runCampaignAction('start'); }")
                    page.wait_for_selector('[data-research-action=stop]:enabled')
                    cid = rs.campaign()['id']
                    assert rs.campaign()['running']
                    with store.connect() as conn:
                        assert conn.execute('SELECT count(*) FROM campaigns').fetchone()[0] == 1
                    # Same entry point while running shows progress, without a second start.
                    page.locator('[data-view=legacy]').first.click()
                    page.get_by_role('button', name='Cerca clienti').click()
                    assert page.locator('[data-campaign-status]').inner_text() == 'Ricerca in corso'
                    assert rs.campaign()['id'] == cid
                    page.locator('[data-research-action=stop]').click()
                    page.wait_for_selector('[data-research-action=resume]:enabled')
                    page.locator('[data-view=legacy]').first.click()
                    page.get_by_role('button', name='Cerca clienti').click()
                    page.wait_for_selector('[data-research-action=stop]:enabled')
                    assert rs.campaign()['id'] == cid
                    page.locator('[data-research-action=stop]').click()
                    page.wait_for_selector('[data-research-action=resume]:enabled')
                    # Explicit New search retains the chosen preferences.
                    page.locator('.research-advanced > summary').click()
                    page.locator('#campaign-region').select_option('priority')
                    page.locator('#campaign-project').select_option('ecommerce')
                    page.locator('[data-research-action=start]').click()
                    page.wait_for_selector('[data-research-action=stop]:enabled')
                    campaign = rs.campaign()
                    assert campaign['id'] != cid
                    assert campaign['filters']['projects'] == ['ecommerce']
                    assert campaign['filters']['regions'] == ['Veneto', 'Lombardia', 'Piemonte', 'Toscana']
                    page.locator('[data-research-action=stop]').click()
                    page.wait_for_selector('[data-research-action=resume]:enabled')
                    assert not errors, errors
                    checks.append({'width': width, 'start_resume_stop_errors_double_click_preferences': 'passed'})
                finally:
                    page.close()
                    http.shutdown()
                    http.server_close()
        browser.close()
    print(json.dumps({'checks': checks, 'production_data_modified': False}))


if __name__ == '__main__':
    run()
