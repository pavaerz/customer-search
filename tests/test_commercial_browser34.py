"""Real local Chromium over a synthetic delayed-CSS fixture; no external sites."""
import subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from sales.db import Store,now
from sales.commercial.browser import review
import test_commercial_browser32 as baseline

class DelayedCSS(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        self.server.seen.append(self.path);time.sleep(.95)
        body=b'body{color:#123;background:white}'
        self.send_response(200);self.send_header('Content-Type','text/css');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass

class Browser34(unittest.TestCase):
    assert_closed=baseline.Browser32Tests.assert_closed
    def test_backlog_borrows_phase_time_within_unchanged_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db');store.init()
            server=ThreadingHTTPServer(('127.0.0.1',0),DelayedCSS);server.daemon_threads=True;server.seen=[]
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                origin='http://127.0.0.1:'+str(server.server_port)
                html='<!doctype html><html><body>'+baseline.TEXT+''.join('<link rel="stylesheet" href="/asset-%d.css">'%i for i in range(24))+'</body></html>'
                p={'url':origin+'/','status':200,'checked_at':now(),'html':html}
                def launch(source,output,errors):return subprocess.Popen([sys.executable,'-m','browser32_harness'],stdin=source,stdout=output,stderr=errors,start_new_session=True,close_fds=True)
                with patch('sales.commercial.browser._launch_worker',launch):
                    r=review(store,[p],capture=True,limits={'browser_total_seconds':20,'browser_timeout_ms':1000,'browser_resource_timeout_ms':3000,'browser_max_resources':60})
                self.assertTrue(r['completed'],r);self.assertEqual(r['audit_state'],'COMPLETE');self.assert_closed(r)
                self.assertEqual(len(server.seen),24);self.assertLessEqual(r['resource_requests'],60)
                self.assertEqual({p['viewport'] for p in r['pages']},{390,1366});self.assertEqual(len(r['screenshots']),2)
                render=[d for d in r['diagnostics'] if d['phase']=='rendering' and d['status']=='completed']
                self.assertTrue(any(d['limit_ms']>5000 for d in render),render)
                self.assertLess(r['elapsed_ms'],r['total_limit_ms']+300)
            finally:server.shutdown();server.server_close();thread.join(2)
