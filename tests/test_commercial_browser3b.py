"""Real Chromium, realistic local resource load; no company/network/AI fixture."""
import json
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
import test_commercial_browser32 as baseline
from test_commercial_browser32 import Fixtures, TEXT


class RealisticFixtures(Fixtures):
    def do_GET(self):
        path=self.path
        if not path.startswith(('/asset-', '/font-slow', '/async-', '/persistent-css')):
            return super().do_GET()
        self.server.seen.append(path)
        with self.server.mutex:
            self.server.active+=1;self.server.peak=max(self.server.peak,self.server.active)
        try:
            delay=2 if path.startswith(('/font-slow','/persistent-css')) else .12 if path.startswith('/async-') else .08
            time.sleep(delay)
            if path.endswith('.js'):
                body=('document.body.innerHTML='+json.dumps(TEXT+'<h2>Contenuto dopo script</h2>')+';').encode();kind='application/javascript'
            elif path.endswith('.woff2'):body=b'fixture-invalid-font';kind='font/woff2'
            elif path.endswith('.svg'):
                body=b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" fill="blue"/></svg>';kind='image/svg+xml'
            else:body=b'body { color: #123; }';kind='text/css'
            self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        finally:
            with self.server.mutex:self.server.active-=1


class Browser3BTests(unittest.TestCase):
    # Reuse the exact isolated process/bootstrap assertions, not a fake browser.
    render=baseline.Browser32Tests.render
    assert_closed=baseline.Browser32Tests.assert_closed
    assert_partial=baseline.Browser32Tests.assert_partial
    shutdown=baseline.Browser32Tests.shutdown
    def setUp(self):
        import tempfile
        from sales.db import Store
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.db');self.store.init()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),RealisticFixtures)
        self.server.daemon_threads=True;self.server.seen=[];self.server.active=0;self.server.peak=0;self.server.mutex=threading.Lock()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.shutdown)
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
    def test_many_css_images_async_script_early_checkpoint_and_bounded_reads(self):
        assets=''.join('<link rel="stylesheet" href="/asset-%s.css">'%i for i in range(12))
        assets+=''.join('<img src="/asset-%s.svg" width="40" height="40">'%i for i in range(12))
        assets+='<script async src="/async-content.js"></script>'
        r=self.render(assets,limits={'browser_resource_timeout_ms':1000,'browser_render_timeout_ms':1800})
        self.assertTrue(r['completed'],r);self.assert_closed(r)
        self.assertEqual({p['viewport'] for p in r['pages']},{390,1366})
        self.assertGreater(r['peak_resource_reads'],1);self.assertLessEqual(r['peak_resource_reads'],4)
        self.assertLessEqual(self.server.peak,4)
        early=r['dom_checkpoints'][0];self.assertTrue(early['text_excerpt']);self.assertGreater(early['pending_resources'],0)
        self.assertFalse(early['layout_evidence'])
        self.assertEqual(len([p for p in self.server.seen if p.startswith('/asset-')]),24)  # reused on second viewport
        diagnostics=r['diagnostics'];early_i=next(i for i,d in enumerate(diagnostics) if d.get('stage')=='early' and d['status']=='completed')
        self.assertTrue(any(d['phase']=='resource' and d['status']=='completed' for d in diagnostics[early_i+1:]))
    def test_font_exceeds_render_deadline_but_dom_checkpoint_survives(self):
        r=self.render('<style>@font-face{font-family:slow;src:url(/font-slow.woff2)}body{font-family:slow}</style>',
            limits={'browser_resource_timeout_ms':1500,'browser_render_timeout_ms':300})
        self.assert_partial(r);self.assertTrue(r['dom_checkpoints'],r)
        self.assertTrue(r['pages']);self.assertIn('Prodotti e servizi',r['pages'][0]['measurements']['text_excerpt'])
        self.assertFalse(any(p['complete'] for p in r['pages']))
    def test_dom_created_only_after_async_script(self):
        r=self.render('<script async src="/async-content.js"></script>',body='',limits={'browser_resource_timeout_ms':500,'browser_render_timeout_ms':1000})
        self.assertTrue(r['completed'],r);self.assert_closed(r)
        self.assertTrue(all('Contenuto dopo script' in p['measurements']['headings'] for p in r['pages']))
    def test_unstyled_early_overflow_never_becomes_a_site_defect(self):
        r=self.render('<style>main{width:2000px}</style><link rel="stylesheet" href="/persistent-css.css">',
                      limits={'browser_resource_timeout_ms':1500,'browser_render_timeout_ms':300})
        self.assert_partial(r);self.assertTrue(r['pages']);self.assertFalse(r['findings'])
        self.assertTrue(all(c['layout_evidence'] is False for c in r['dom_checkpoints']))
    def test_resource_count_bound_with_concurrent_callbacks(self):
        r=self.render(''.join('<link rel="stylesheet" href="/asset-%s.css">'%i for i in range(12)),
                      limits={'browser_max_resources':3,'browser_resource_timeout_ms':500,'browser_render_timeout_ms':1000})
        self.assert_partial(r);self.assertEqual(len(self.server.seen),3)
        self.assertEqual(r['resource_requests'],3)
    def test_mixed_persistent_and_blocked_resources_preserve_partial_dom(self):
        r=self.render('<script>new EventSource("/events")</script><img src="http://127.0.0.1/private"><link rel="stylesheet" href="/asset-valid.css">',
                      limits={'browser_resource_timeout_ms':500,'browser_render_timeout_ms':1000})
        self.assert_partial(r);self.assertTrue(r['dom_checkpoints']);self.assertNotIn('/events',self.server.seen)
        self.assertIn('/asset-valid.css',self.server.seen)
    def test_concurrent_resource_reads_cannot_exceed_http_ledger(self):
        from sales.research_store import ResearchStore
        from sales.commercial.catalog import BUDGETS
        from sales.commercial.resources import Budget,BudgetExceeded
        c=ResearchStore(self.store).create({'commercial_engines':['WEBSITE_REBUILD']})
        budget=Budget(self.store,c,'WEBSITE_REBUILD',{**BUDGETS,'max_http_reads':4})
        with budget.task(lambda:None),self.assertRaises(BudgetExceeded):
            self.render(''.join('<link rel="stylesheet" href="/asset-%s.css">'%i for i in range(12)),
                        limits={'browser_resource_timeout_ms':500,'browser_render_timeout_ms':1000})
        self.assertEqual(budget.used('http_reads'),4);self.assertLessEqual(len(self.server.seen),4)
