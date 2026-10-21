"""Actual Chromium against loopback fixtures; no real-company/network access."""
import http.client
import ssl
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.parse import urlsplit, urljoin

from sales.db import Store, now
from sales.commercial.browser import _review as review, error_code
from sales.commercial.rebuild import evaluate
from sales.providers import PublicWeb
from test_commercial_engines import page
from sales.commercial.attribution import identity_from
from sales.commercial.geography import locate

TEXT='<main><h1>Impresa locale</h1><p>Prodotti e servizi industriali per i nostri clienti, con informazioni commerciali complete e verificabili.</p></main>'

class FixtureServer(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/redirect.css':
            self.send_response(302);self.send_header('Location','/fast.css');self.end_headers();return
        if self.path=='/error.css':self.send_error(503);return
        if self.path in ('/slow.css','/never.css'):time.sleep(.5)
        body=(b'body{color:#123}' if self.path.endswith('.css') else TEXT.encode())
        self.send_response(200);self.send_header('Content-Type','text/css' if self.path.endswith('.css') else 'text/html');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass

class Browser31Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.db');self.store.init()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),FixtureServer)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close_server)
        self.origin='http://127.0.0.1:'+str(self.server.server_port);self.seen=[]
    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
    def render(self,html,limits=None):
        # Only the transport is replaced to allow this server. Browser egress stays
        # denied by SafeProxy; the fixture transport explicitly rejects all other hosts.
        seen=self.seen;origin=self.origin
        def local_raw(web,url,redirects=4,policy=True):
            if not url.startswith(origin+'/'):raise AssertionError('External URL forbidden')
            seen.append(url);parts=urlsplit(url)
            conn=http.client.HTTPConnection(parts.hostname,parts.port,timeout=web.request_timeout())
            try:
                conn.request('GET',parts.path);response=conn.getresponse()
                if response.status==302:
                    if redirects<=0:raise ValueError('Redirect limit')
                    return local_raw(web,urljoin(url,response.getheader('Location')),redirects-1)
                return {'url':url,'status':response.status,'body':response.read(),'content_type':response.getheader('Content-Type')}
            finally:conn.close()
        p={'url':origin+'/','status':200,'checked_at':now(),'html':'<!doctype html><html><body>'+TEXT+html+'</body></html>'}
        with patch('sales.heavy.DATA',Path(self.tmp.name)),patch('sales.safe_proxy.public_addresses',side_effect=ValueError('Offline egress forbidden')),patch.object(PublicWeb,'_raw',local_raw):
            return review(self.store,[p],capture=False,limits={'browser_total_seconds':8,'browser_timeout_ms':1000,'browser_render_timeout_ms':500,'browser_resource_timeout_ms':100,**(limits or {})})
    def test_fast_local_site_closes_browser_and_reports_phases(self):
        r=self.render('<link rel="stylesheet" href="/fast.css">')
        self.assertTrue(r['completed'],r);self.assertTrue(r['resources_closed']);self.assertEqual(r['outcome'],'completed')
        self.assertEqual({p['viewport'] for p in r['pages']},{390,1366})
        self.assertTrue({'startup','navigation','rendering','resource','cleanup'}<={d['phase'] for d in r['diagnostics']})
        self.assertTrue(any(d.get('wait_until')=='commit' for d in r['diagnostics']))
    def test_slow_blocking_resource_yields_partial_evidence_not_defect(self):
        r=self.render('<link rel="stylesheet" href="/slow.css">')
        self.assertFalse(r['completed']);self.assertEqual(r['outcome'],'partial');self.assertTrue(r['pages']);self.assertEqual(r['findings'],[])
        self.assertIn('rendering_timeout',r['failure_codes']);self.assertTrue(r['resources_closed']);self.assertLess(r['elapsed_ms'],8000)
    def test_resource_redirect_preserves_final_resource(self):
        r=self.render('<link rel="stylesheet" href="/redirect.css">')
        self.assertTrue(r['completed'],r);self.assertTrue(any(u.endswith('/redirect.css') for u in self.seen));self.assertTrue(any(u.endswith('/fast.css') for u in self.seen))
    def test_persistent_event_stream_not_waited_for(self):
        r=self.render('<script>new EventSource("/events")</script>')
        self.assertFalse(r['completed']);self.assertEqual(r['outcome'],'partial');self.assertEqual(r['findings'],[])
        self.assertFalse(any(u.endswith('/events') for u in self.seen));self.assertTrue(r['resources_closed'])
    def test_nonterminating_resource_is_bounded(self):
        r=self.render('<script src="/never.css"></script>')
        self.assertFalse(r['completed']);self.assertTrue(r['resources_closed']);self.assertLess(r['elapsed_ms'],8000)
        self.assertEqual(r['findings'],[])
    def test_partial_malformed_html_remains_observable(self):
        r=self.render('<section><p>Testo incompleto senza chiusura del tag')
        self.assertTrue(r['pages']);self.assertTrue(r['resources_closed']);self.assertFalse(r['findings'])
    def test_http_error_resource_not_site_defect(self):
        r=self.render('<link rel="stylesheet" href="/error.css">')
        self.assertEqual(r['outcome'],'partial');self.assertFalse(r['completed']);self.assertEqual(r['findings'],[])
        self.assertIn('access_error',r['failure_codes'])
    def test_diagnostic_codes_and_partial_never_qualifies(self):
        self.assertEqual(error_code(TimeoutError(),'navigation'),'navigation_timeout')
        self.assertEqual(error_code(TimeoutError(),'rendering'),'rendering_timeout')
        self.assertEqual(error_code(ssl.SSLCertVerificationError('certificate failed'),'resource'),'tls_error')
        self.assertEqual(error_code(ValueError('robots.txt denied'),'resource'),'robots')
        p=page('Azienda con prodotti e servizi completi.');identity=identity_from([p])
        r=evaluate(identity,[p],locate([p],identity),{'promising':True,'findings':[],'status':'indicators'},
                   {'completed':False,'outcome':'partial','pages':[{'measurements':{'text':100}}],
                    'findings':[{'code':'invented','severity':'major'}],'limits':['Risorsa non accessibile']})
        self.assertEqual(r['state'],'UNVERIFIABLE');self.assertEqual(r['browser_outcome'],'partial');self.assertEqual(r['evidence'],[])
    def test_public_web_timeout_hook_retains_smaller_cap(self):
        web=PublicWeb(self.store);web.request_timeout=lambda:.1
        response=MagicMock();response.status=200;response.getheader.return_value='text/html';response.read1.side_effect=[b'<html',b'>test</html>',b'']
        with patch.object(web,'policy'),patch('sales.providers.socket.getaddrinfo',return_value=[(None,None,None,None,('8.8.8.8',80))]),patch('sales.providers.socket.create_connection') as sock,patch('sales.providers.http.client.HTTPConnection') as conn:
            conn.return_value.getresponse.return_value=response
            web._raw('http://public.example/')
            self.assertEqual(sock.call_args.kwargs['timeout'],.1);self.assertEqual(conn.call_args.kwargs['timeout'],.1)

    def test_navigation_timeout_has_no_fabricated_partial_page(self):
        from playwright.async_api import Page
        with patch.object(Page,'goto',side_effect=TimeoutError('Navigation timeout')):
            r=self.render('')
        self.assertFalse(r['completed']);self.assertEqual(r['outcome'],'navigation_timeout')
        self.assertFalse(r['pages']);self.assertFalse(r['findings']);self.assertTrue(r['resources_closed'])
    def test_navigation_error_closes_resources(self):
        from playwright.async_api import Page
        with patch.object(Page,'goto',side_effect=ValueError('net::ERR_CONNECTION_REFUSED')):
            r=self.render('')
        self.assertIn('navigation_error',r['failure_codes']);self.assertFalse(r['completed'])
        self.assertTrue(r['resources_closed']);self.assertFalse(r['findings'])
    def test_resource_stream_rechecks_deadline_between_chunks(self):
        web=PublicWeb(self.store);web.request_timeout=MagicMock(side_effect=[.1,.1,TimeoutError('phase deadline')])
        response=MagicMock();response.status=200;response.getheader.return_value='text/html';response.read1.return_value=b'<html'
        with patch.object(web,'policy'),patch('sales.providers.socket.getaddrinfo',return_value=[(None,None,None,None,('8.8.8.8',80))]),patch('sales.providers.socket.create_connection') as sock,patch('sales.providers.http.client.HTTPConnection') as conn:
            conn.return_value.getresponse.return_value=response
            with self.assertRaisesRegex(TimeoutError,'phase deadline'):web._raw('http://public.example/')
            self.assertEqual(response.read1.call_count,1);sock.return_value.close.assert_called_once()
