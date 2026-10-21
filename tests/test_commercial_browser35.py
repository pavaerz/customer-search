"""Real Chromium on loopback. TLS/robots transport faults explicitly simulated."""
import subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from sales.db import Store,now
from sales.commercial.browser import review
import test_commercial_browser32 as baseline
class Assets(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        self.server.seen.append(self.path)
        if self.path.startswith('/slow'):time.sleep(.9)
        body=b'window.fixtureReady=true;' if self.path.endswith('.js') else b'body{margin:0} main{max-width:100%}'
        self.send_response(200);self.send_header('Content-Type','text/javascript' if self.path.endswith('.js') else 'text/css');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
class Browser35(unittest.TestCase):
    assert_closed=baseline.Browser32Tests.assert_closed
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(Path(self.tmp.name)/'test.db');self.store.init()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Assets);self.server.daemon_threads=True;self.server.seen=[]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.shutdown)
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
    def shutdown(self):self.server.shutdown();self.server.server_close();self.thread.join(2)
    def render(self,extra='',level='STANDARD',body=baseline.TEXT):
        p={'url':self.origin+'/','status':200,'checked_at':now(),'html':'<!doctype html><title>Local company</title><meta name="viewport" content="width=device-width">'+body+extra}
        def launch(source,output,errors):return subprocess.Popen([sys.executable,'-m','browser35_harness'],stdin=source,stdout=output,stderr=errors,start_new_session=True,close_fds=True)
        with patch('sales.commercial.browser._launch_worker',launch):
            r=review(self.store,[p],capture=level!='BASIC',limits={'browser_audit_level':level,'browser_total_seconds':8,'browser_timeout_ms':1000,'browser_render_timeout_ms':1000,'browser_resource_timeout_ms':200,'browser_max_resources':60})
        self.assert_closed(r);return r
    def test_basic_real_complete(self):
        r=self.render('<link rel="stylesheet" href="/fast.css">',level='BASIC');self.assertTrue(r['completed'],r);self.assertEqual(r['completed_level'],'BASIC');self.assertEqual(len(r['pages']),1);self.assertEqual(r['pages'][0]['measurements']['title'],'Local company');self.assertEqual(r['screenshots'],[])
    def test_standard_real_mobile_overflow(self):
        r=self.render('<style>main{width:1000px}</style>');self.assertTrue(r['completed'],r);self.assertEqual(r['completed_level'],'STANDARD');self.assertEqual(len(r['screenshots']),2);self.assertTrue(any(o['status']=='CONFIRMED' for o in r['observations']))
    def test_optional_tracker_omitted_without_external_request(self):
        r=self.render('<script src="https://www.google-analytics.com/analytics.js"></script><link rel="stylesheet" href="/fast.css">');self.assertTrue(r['completed'],r);self.assertEqual(r['ignored_resources'][0]['role'],'TRACKING');self.assertEqual(self.server.seen,['/fast.css'])
    def test_slow_critical_script_partial(self):
        r=self.render('<script src="/slow.js"></script>');self.assertFalse(r['completed']);self.assertTrue(r['missing_resources']);self.assertTrue(all(m['role']=='CRITICAL' for m in r['missing_resources']));self.assertEqual(r['findings'],[])
    def test_incomplete_css_overflow_not_confirmed(self):
        r=self.render('<style>main{width:1000px}</style><link rel="stylesheet" href="/slow.css">');self.assertFalse(r['completed']);self.assertTrue(r['observations']);self.assertTrue(all(o['status']=='UNVALIDATED' for o in r['observations']));self.assertEqual(r['findings'],[])
    def test_simulated_tls_in_real_browser(self):
        r=self.render('<link rel="stylesheet" href="/tls.css">');self.assertFalse(r['completed']);self.assertIn('tls_error',r['failure_codes']);self.assertNotIn('/tls.css',self.server.seen)
    def test_simulated_robots_denial_in_real_browser(self):
        r=self.render('<link rel="stylesheet" href="/blocked.css">');self.assertFalse(r['completed']);self.assertIn('robots',r['failure_codes']);self.assertNotIn('/blocked.css',self.server.seen)
