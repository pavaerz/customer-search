"""Phase 3A.2 real Chromium + loopback fixtures through isolated public review."""
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from sales.commercial.browser import review
from sales.db import Store,now

TEXT='<main><h1>Impresa locale</h1><p>Prodotti e servizi industriali per i nostri clienti, con informazioni complete, verificabili e comprensibili.</p></main>'

class Fixtures(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        self.server.seen.append(self.path)
        if self.path=='/redirect.css':
            self.send_response(302);self.send_header('Location','/fast.css');self.end_headers();return
        if self.path in ('/slow.css','/never'):time.sleep(2)
        if self.path=='/close':self.connection.close();return
        if self.path=='/error.css':self.send_error(503);return
        kind='application/pdf' if self.path=='/hidden-document' else 'text/css' if self.path.endswith('.css') else 'text/html'
        body=b'%PDF-test fixture' if kind=='application/pdf' else b'body{color:#123}' if kind=='text/css' else TEXT.encode()
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass

class Browser32Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.db');self.store.init()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Fixtures);self.server.daemon_threads=True;self.server.seen=[]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.shutdown)
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
    def shutdown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
    def render(self,extra='',*,path='/',body=TEXT,status=200,limits=None,check=lambda:None):
        p={'url':self.origin+path,'status':status,'checked_at':now(),'html':'<!doctype html><html><body>'+body+extra+'</body></html>'}
        def launch(source,output,errors):
            return subprocess.Popen([sys.executable,'-m','browser32_harness'],stdin=source,stdout=output,stderr=errors,start_new_session=True,close_fds=True)
        with patch('sales.commercial.browser._launch_worker',launch):
            return review(self.store,[p],capture=False,check=check,limits={'browser_total_seconds':8,'browser_timeout_ms':800,'browser_render_timeout_ms':500,'browser_resource_timeout_ms':100,**(limits or {})})
    def assert_closed(self,r):
        self.assertTrue(r['worker_reaped'],r);self.assertTrue(r['resources_closed'],r)
        self.assertLess(r['elapsed_ms'],r['total_limit_ms']+300,r)
        # Real browser PIDs, not a stubbed success response.
        self.assertTrue(r.get('owned_browser_pids'),r)
        for pid in [*r['owned_browser_pids'],*([r['owned_driver_pid']] if r.get('owned_driver_pid') else [])]:
            for _ in range(20):
                try:os.kill(pid,0)
                except ProcessLookupError:break
                time.sleep(.01)
            else:self.fail('Owned Chromium process remains alive: '+str(pid))
    def assert_partial(self,r):
        self.assertFalse(r['completed'],r);self.assertFalse(r['findings'],r);self.assert_closed(r)
    def test_01_simple_html(self):
        r=self.render();self.assertTrue(r['completed'],r);self.assert_closed(r)
        self.assertEqual({p['viewport'] for p in r['pages']},{390,1366})
        self.assertTrue({'startup','navigation','dom','evidence','cleanup'}<={x['phase'] for x in r['diagnostics']})
        self.assertTrue(all('limit_ms' in x and 'elapsed_ms' in x and 'error' in x for x in r['diagnostics']))
    def test_02_javascript(self):
        r=self.render('<script>document.addEventListener("DOMContentLoaded",()=>document.body.insertAdjacentHTML("beforeend","<h2>JavaScript completato</h2>"))</script>')
        self.assertTrue(r['completed'],r);self.assertTrue(all('JavaScript completato' in p['measurements']['headings'] for p in r['pages']));self.assert_closed(r)
    def test_03_redirect(self):
        r=self.render('<link rel="stylesheet" href="/redirect.css">');self.assertTrue(r['completed'],r)
        self.assertIn('/redirect.css',self.server.seen);self.assertIn('/fast.css',self.server.seen);self.assert_closed(r)
    def test_04_slow_resources(self):
        r=self.render('<link rel="stylesheet" href="/slow.css">');self.assert_partial(r);self.assertTrue(r['pages'])
    def test_05_persistent_requests(self):
        r=self.render('<script>new EventSource("/events")</script>');self.assert_partial(r)
        self.assertNotIn('/events',self.server.seen)
    def test_06_incomplete_html(self):
        r=self.render('<section><p>Testo lasciato aperto senza chiusura del tag');self.assertTrue(r['completed'],r);self.assert_closed(r)
    def test_07_http_error(self):
        r=self.render(status=503);self.assert_partial(r)
        self.assertTrue(any('503' in d.get('message','') for d in r['diagnostics']))
    def test_08_navigation_never_finishes(self):
        r=self.render('<script>location.href="/never"</script>');self.assert_partial(r)
    def test_09_slow_rendering_hard_deadline(self):
        r=self.render('<script>const until=Date.now()+10000;while(Date.now()<until){}</script>',limits={'browser_total_seconds':2})
        self.assert_partial(r);self.assertIn(r.get('termination_reason'),('inspection_timeout','rendering_timeout','dom_timeout'))
        # A subsequent task still completes after a renderer that never yielded.
        following=self.render();self.assertTrue(following['completed'],following);self.assert_closed(following)
    def test_10_dynamic_elements(self):
        r=self.render('<script>setTimeout(()=>document.body.insertAdjacentHTML("beforeend","<h2>Elemento dinamico</h2>"),40)</script>')
        self.assertTrue(r['completed'],r);self.assertTrue(all('Elemento dinamico' in p['measurements']['headings'] for p in r['pages']));self.assert_closed(r)
    def test_11_blocked_resource(self):
        r=self.render('<img src="http://127.0.0.1/private">');self.assert_partial(r)
        self.assertTrue(any('denied' in x for x in r['limits']))
    def test_12_early_page_close(self):
        r=self.render(path='/earlyclose');self.assert_partial(r)
    def test_pdf_extension_and_mime_excluded_before_body(self):
        r=self.render('<iframe src="/document.pdf"></iframe><iframe src="/hidden-document"></iframe>')
        self.assert_partial(r);self.assertNotIn('/document.pdf',self.server.seen)
        self.assertIn('/hidden-document',self.server.seen)
    def test_dom_level_does_not_run_advanced_paths(self):
        r=self.render('<a href="/contatti">Contatti</a>',limits={'browser_advanced':False})
        self.assertTrue(r['completed'],r);self.assertEqual(r['levels']['BROWSER_ADVANCED']['status'],'not_requested')
        self.assertFalse(r['path_checks']);self.assertNotIn('/contatti',self.server.seen);self.assert_closed(r)
    def test_cancellation_interrupts_hung_renderer_and_reaps_child(self):
        begin=time.monotonic();children=[]
        def launch(source,output,errors):
            p=subprocess.Popen([sys.executable,'-m','browser32_harness'],stdin=source,stdout=output,stderr=errors,start_new_session=True,close_fds=True);children.append(p);return p
        def check():
            if time.monotonic()-begin>1.5:raise InterruptedError('Stop')
        p={'url':self.origin+'/','status':200,'html':TEXT+'<script>while(true){}</script>'}
        with patch('sales.commercial.browser._launch_worker',launch),self.assertRaises(InterruptedError):
            review(self.store,[p],check=check,capture=False,limits={'browser_total_seconds':8})
        self.assertLess(time.monotonic()-begin,2.2);self.assertTrue(children);self.assertIsNotNone(children[0].poll())
    def test_child_http_debits_same_budget_and_browser_reserved_once(self):
        from sales.research_store import ResearchStore
        from sales.commercial.catalog import BUDGETS
        from sales.commercial.resources import Budget
        c=ResearchStore(self.store).create({'commercial_engines':['WEBSITE_REBUILD']})
        budget=Budget(self.store,c,'WEBSITE_REBUILD',BUDGETS)
        with budget.task(lambda:None):r=self.render('<link rel="stylesheet" href="/fast.css">')
        self.assertTrue(r['completed'],r);self.assertEqual(budget.used('http_reads'),1);self.assertEqual(budget.used('browser_runs'),1)
    def test_child_http_budget_exhaustion_propagates_without_bypass(self):
        from sales.research_store import ResearchStore
        from sales.commercial.catalog import BUDGETS
        from sales.commercial.resources import Budget,BudgetExceeded
        c=ResearchStore(self.store).create({'commercial_engines':['WEBSITE_REBUILD']})
        budget=Budget(self.store,c,'WEBSITE_REBUILD',{**BUDGETS,'max_http_reads':1})
        with budget.task(lambda:None),self.assertRaises(BudgetExceeded) as caught:
            self.render('<link rel="stylesheet" href="/fast.css"><link rel="stylesheet" href="/other.css">')
        self.assertEqual(caught.exception.resource,'http_reads');self.assertEqual(budget.used('http_reads'),1)
    def test_failed_resource_not_retried_on_second_viewport(self):
        r=self.render('<link rel="stylesheet" href="/slow.css">');self.assert_partial(r)
        self.assertEqual(self.server.seen.count('/slow.css'),1)
        self.assertTrue(any(d['status']=='not_retried' or d.get('wait_until')=='reuse_pending_document' for d in r['diagnostics']))

    def test_unconfirmed_cleanup_cannot_report_completed(self):
        import json
        result={'completed':True,'resources_closed':False,'pages':[], 'findings':[{'code':'unsupported'}],
                'diagnostics':[],'limits':[], 'levels':{'DOM':{'status':'completed'},'BROWSER_ADVANCED':{'status':'completed'}}}
        def launch(source,output,errors):
            code='import json;print('+repr(json.dumps({'type':'result','result':result}))+',flush=True)'
            return subprocess.Popen([sys.executable,'-c',code],stdin=source,stdout=output,stderr=errors,start_new_session=True)
        with patch('sales.commercial.browser._launch_worker',launch),patch('sales.commercial.browser._terminate_owned',return_value=(False,[],{'remaining_pids':[],'signal_errors':[{'error':'fixture'}]})):
            r=review(self.store,[{'url':self.origin+'/','html':TEXT}],capture=False)
        self.assertFalse(r['completed']);self.assertFalse(r['findings']);self.assertEqual(r['termination_reason'],'cleanup_error')
