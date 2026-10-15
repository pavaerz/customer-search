"""Responsive and interaction audit on an isolated local database. No external requests or CRM edits."""
import json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_research import sample
from sales import server
from sales.db import Store,encode
from sales.research_store import ResearchStore
from sales.research_rules import qualify
from sales.campaigns import CampaignManager
from sales.engines import EngineManager
from playwright.sync_api import sync_playwright

OUTPUT=Path('/tmp/customersearch-ui-audit')

def go(page,view):
 if view in ['agencies','direct']:
  page.locator('.sidebar [data-view=overview]').click();page.locator(f'.result-tabs [data-view="{view}"]').click()
 elif view in ['legacy','results']:
  page.locator('.sidebar [data-view=pipeline]').click();page.locator(f'.workspace-tabs [data-view="{view}"]').click()
 elif view=='activity':
  page.locator('.sidebar [data-view=overview]').click()
  page.locator('.research-advanced').evaluate('e=>e.open=true');page.locator('[data-view=activity]').click()
 else:page.locator(f'.sidebar [data-view="{view}"]').click()

def run():
 OUTPUT.mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory() as tmp:
  store=Store(Path(tmp)/'visual.sqlite3');store.init();rs=ResearchStore(store);campaign=rs.create()
  for n in range(23):
   args=sample();args[0].update(name=('Laboratorio artigianale di progettazione e produzione internazionale '+str(n)) if n==0 else f'Impresa dimostrativa {n:02}',website=f'https://azienda{n}.example/',legal_id='IT'+str(12345678900+n),group='agencies' if n%3==0 else 'direct')
   rs.save(campaign['id'],campaign['generation'],None,args[0],args[1],qualify(*args))
  rs.stop(campaign['id']);rs.paused(campaign['id'])
  with store.connect() as c:
   for n in range(31):c.execute('INSERT INTO legacy_records VALUES (?,?,?)',('leads',n,encode({'company_name':f'Azienda archivio {n:02}','url':f'https://originale{n}.example/','notes':'Dettaglio conservato. '*20})))
   c.execute('UPDATE prospects SET draft=?',(encode({'subject':'Progetto digitale da approfondire','email':'Bozza da revisionare manualmente.','proposal':'Perimetro da concordare.','followup':'Da valutare.'}),))
  http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);origin=f'http://127.0.0.1:{http.server_port}'
  patches=[patch.object(server,'STORE',store),patch.object(server,'MANAGER',EngineManager(store)),patch.object(server,'PORT',http.server_port),patch.object(server,'ORIGIN',origin),patch.object(CampaignManager,'launch',lambda m,c:m.rs.campaign(c['id']))]
  for p in patches:p.start()
  thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
  report={'widths':[320,390,768,1024,1440,1920],'screens':[],'checks':[],'errors':[],'external_requests':[],'real_data_modified':False}
  try:
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport={'width':1440,'height':1000},has_touch=True);page.on('pageerror',lambda e:report['errors'].append(str(e)))
    page.on('request',lambda req:report['external_requests'].append(req.url) if not req.url.startswith(origin) else None)
    page.goto(origin);page.wait_for_selector('[data-opportunity-id]');page.wait_for_function("() => document.querySelector('#research-results').getAttribute('aria-busy')==='false'")
    assert page.locator('.result-tabs .active').inner_text().startswith('Tutti')
    controls=page.locator('.research-filters input,.research-filters select').evaluate_all('(els)=>els.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})')
    assert len(controls)==6 and len(set(round(x['h']) for x in controls))==1
    assert len(set(round(x['y']) for x in controls))==2,controls
    for i in range(3):assert abs(controls[i]['x']-controls[i+3]['x'])<1
    report['checks'].append('Six aligned filters, equal heights, three desktop columns')
    # Background polling must preserve element identity, caret, filters, and expanded preferences.
    page.locator('.research-advanced > summary').click();page.locator('#campaign-project').select_option('ecommerce')
    page.locator('[data-research-filter="search"]').fill('dimostrativa');page.wait_for_timeout(350)
    page.evaluate("window.testField=document.querySelector('[data-research-filter=search]');testField.setSelectionRange(3,5)")
    with store.connect() as c:c.execute("UPDATE campaigns SET message='Controllo di avanzamento della fixture' WHERE id=?",(campaign['id'],))
    page.evaluate('pollState()')
    assert page.evaluate("testField===document.activeElement && testField.selectionStart===3 && testField.selectionEnd===5")
    assert page.locator('.research-advanced').get_attribute('open') is not None
    assert page.locator('#campaign-project').input_value()=='ecommerce'
    assert page.locator('[data-campaign-message]').inner_text()=='Controllo di avanzamento della fixture'
    report['checks'].append('Polling preserves focused field, selection, preferences and open disclosure')
    page.locator('[data-research-reset]').first.click();page.wait_for_selector('[data-opportunity-id]')
    page.locator('[data-research-page="next"]').click();page.wait_for_function("() => document.querySelectorAll('[data-opportunity-id]').length===3")
    page.locator('[data-research-page="previous"]').click();page.wait_for_function("() => document.querySelectorAll('[data-opportunity-id]').length===20")
    report['checks'].append('Results pagination and filter reset')
    page.route('**/api/opportunities?*',lambda route:route.fulfill(status=503,json={'error':'Servizio temporaneamente non disponibile'}))
    page.locator('[data-research-filter="region"]').select_option('Veneto');page.wait_for_selector('[data-research-retry]')
    page.unroute('**/api/opportunities?*');page.locator('[data-research-retry]').click();page.wait_for_selector('[data-opportunity-id]')
    page.route('**/api/state',lambda route:route.abort());page.evaluate('pollState()');assert page.locator('.live.offline').count()==1
    page.unroute('**/api/state');page.evaluate('pollState()');assert page.locator('.live.offline').count()==0
    report['checks'].append('Recoverable results errors and visible connection loss/recovery')
    # Every route across six widths, with populated cards and original history.
    for width in report['widths']:
     page.set_viewport_size({'width':width,'height':900 if width>760 else 844})
     for view in ['overview','agencies','direct','pipeline','results','legacy','activity','settings']:
      go(page,view)
      if view in ['overview','agencies','direct']:page.wait_for_function("() => document.querySelector('#research-results').getAttribute('aria-busy')==='false'")
      elif view=='activity':page.wait_for_selector('#campaign-history details')
      elif view=='archive':page.wait_for_selector('#legacy-list table')
      if view in ['results','activity']:page.locator('#main details').evaluate_all('(els)=>els.forEach(e=>e.open=true)')
      assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,view,'page overflow')
      assert page.locator('#main h1').count()==1,(width,view,'heading')
      assert page.locator('.sidebar .navitem').count()==3
      assert page.locator('.sidebar .navitem.active').count()==1
      paths=page.locator('.sidebar .nav-icon path').evaluate_all("els=>els.map(e=>e.getAttribute('d'))");assert len(set(paths))==3
      assert page.evaluate('window.scrollY<2'),(width,view,'navigation scroll')
      if width in [390,1440]:page.screenshot(path=str(OUTPUT/f'{width}-{view}.png'),full_page=True)
      report['screens'].append({'width':width,'view':view,'page_overflow':False})
    # Region values are all readable on a phone; native select text must fit.
    page.set_viewport_size({'width':390,'height':844});page.locator('.sidebar [data-view="overview"]').click()
    page.locator('[data-research-filter="region"]').select_option('Friuli-Venezia Giulia')
    assert page.locator('[data-research-filter="region"]').evaluate("e=>{let s=getComputedStyle(e),c=document.createElement('canvas').getContext('2d');c.font=s.font;return c.measureText(e.selectedOptions[0].text).width<e.clientWidth-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight)}")
    page.locator('[data-research-reset]').first.click();page.wait_for_selector('[data-opportunity-id]')
    # Dossier contact actions must refresh the open dossier and keep toasts above the backdrop.
    page.locator('[data-research-open]').first.click();page.wait_for_selector('#detail[open]')
    assert page.evaluate("document.querySelector('#detail').scrollWidth<=document.querySelector('#detail').clientWidth+1")
    page.locator('#detail [data-action="confirm-contact"]').click();page.wait_for_selector('#detail .contact-status')
    assert page.locator('#detail #toast.show').count()==1
    page.locator('#detail [data-action="dismiss-proposal"]').click();page.wait_for_selector('#detail',state='hidden')
    report['checks'].append('Research dossier confirms contact live, visible modal toast, deletion closes dossier')
    for width in [390,1440]:
     page.set_viewport_size({'width':width,'height':900});go(page,'legacy');page.locator('[data-open]').first.click();page.wait_for_selector('#detail[open]')
     for tab in ['summary','evidence','audit','draft','manage']:
      page.locator('.tabs [data-tab="'+tab+'"]').click()
      assert page.evaluate("document.querySelector('#detail').scrollWidth<=document.querySelector('#detail').clientWidth+1"),(width,tab)
      page.screenshot(path=str(OUTPUT/f'{width}-dialog-{tab}.png'))
     page.locator('#manage-form [name="notes"]').fill('Nota non ancora salvata: non perdere durante gli aggiornamenti.')
     page.evaluate('pollState()');assert page.locator('#manage-form [name="notes"]').input_value().startswith('Nota non ancora')
     page.keyboard.press('Escape');page.wait_for_selector('#detail',state='hidden')
     assert page.evaluate("document.activeElement.hasAttribute('data-open')")
    report['checks'].append('Five dossier tabs at desktop/mobile, unsaved notes survive polling, Escape restores focus')
    page.locator('.sidebar [data-view="pipeline"]').click();page.locator('[data-board-scroll="1"]').click();page.wait_for_timeout(450);assert page.locator('.board').evaluate('e=>e.scrollLeft')>200
    report['checks'].append('Pipeline horizontal navigation and bounded columns')
    page.set_viewport_size({'width':1440,'height':1000});page.locator('.sidebar [data-view="pipeline"]').click()
    mover=page.locator('[data-stage="review"] [data-move-id]').first;ident=mover.get_attribute('data-move-id');mover.select_option('ready');page.wait_for_selector(f'[data-stage="ready"] [data-card-id="{ident}"]')
    # Real Chrome touch events exercise pointer capture and the dedicated drag grip.
    grip=page.locator('[data-stage="review"] .drag-grip').first;card_id=grip.locator('..').get_attribute('data-card-id');grip.scroll_into_view_if_needed();src=grip.bounding_box();dst=page.locator('[data-stage="ready"]').bounding_box()
    sx,sy=src['x']+src['width']/2,src['y']+src['height']/2;dx,dy=dst['x']+dst['width']/2,dst['y']+85
    cdp=page.context.new_cdp_session(page)
    cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':sx,'y':sy}]})
    for step in range(1,6):cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':sx+(dx-sx)*step/5,'y':sy+(dy-sy)*step/5}]})
    cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});page.wait_for_selector(f'[data-stage="ready"] [data-card-id="{card_id}"]')
    report['checks'].append('Pipeline select and real touch drag persist the new stage')
    page.locator('.sidebar [data-view="settings"]').click();page.locator('#settings-form [name="name"]').fill('Nome non ancora salvato');page.evaluate('pollState()');assert page.locator('#settings-form [name="name"]').input_value()=='Nome non ancora salvato'
    report['checks'].append('Unsaved settings preserved')
    assert not report['errors'],report['errors'];assert not report['external_requests'],report['external_requests']
    browser.close()
  finally:
   http.shutdown();http.server_close();thread.join()
   for p in patches:p.stop()
   (OUTPUT/'report.json').write_text(json.dumps(report,indent=2))
  print(json.dumps({'responsive_screens':len(report['screens']),'interaction_checks':report['checks'],'javascript_errors':report['errors'],'external_requests':report['external_requests'],'report':str(OUTPUT/'report.json')}))
if __name__=='__main__':run()
