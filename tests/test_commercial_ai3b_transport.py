"""Real LOCAL adapter process against an ephemeral loopback JSON fixture only."""
import json
import multiprocessing
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from sales.commercial import ai_provider
from sales.commercial.ai import validate_config
from sales.commercial.ai_schema import unknown_output


class Handler(BaseHTTPRequestHandler):
    delay=0;requests=[]
    def log_message(self,*args):pass
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).requests.append(request)
        if type(self).delay:time.sleep(type(self).delay)
        payload=json.loads(request['messages'][1]['content'])
        data=json.dumps({'message':{'content':json.dumps(unknown_output(payload))},'prompt_eval_count':10,'eval_count':20}).encode()
        try:
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass


class Transport(unittest.TestCase):
    def setUp(self):
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        Handler.requests=[];Handler.delay=0
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.cfg=validate_config({'enabled':True,'provider':'LOCAL','model':'fixture','endpoint':'http://127.0.0.1:'+str(self.server.server_port)+'/api/chat','timeout':2})
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def test_actual_local_adapter_json_process(self):
        response=ai_provider.infer({'candidate_id':'7','evidence':[]},self.cfg,lambda:None)
        self.assertEqual(json.loads(response['output'])['candidate_id'],'7');self.assertEqual(response['usage']['input_tokens'],10)
        self.assertFalse(Handler.requests[0]['stream']);self.assertNotIn('tools',Handler.requests[0]);self.assertIn('format',Handler.requests[0])
    def test_stop_terminates_owned_provider_process(self):
        Handler.delay=3;start=time.monotonic()
        def check():
            if time.monotonic()-start>.2:raise InterruptedError('stop')
        with self.assertRaises(InterruptedError):ai_provider.infer({'candidate_id':'7','evidence':[]},self.cfg,check)
        self.assertLess(time.monotonic()-start,1.5)
        self.assertFalse([p for p in multiprocessing.active_children() if p.is_alive()])
    def test_timeout_terminates_owned_provider_process(self):
        Handler.delay=3;self.cfg['timeout']=1;start=time.monotonic()
        with self.assertRaises(TimeoutError):ai_provider.infer({'candidate_id':'7','evidence':[]},self.cfg,lambda:None)
        self.assertLess(time.monotonic()-start,2)
        self.assertFalse([p for p in multiprocessing.active_children() if p.is_alive()])
    def test_remote_dns_private_is_blocked(self):
        with patch('sales.commercial.ai_provider.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),patch('sales.commercial.ai_provider.socket.create_connection') as connection:
            with self.assertRaisesRegex(ValueError,'non_public'):ai_provider._PinnedHTTPS('api.example').connect()
            connection.assert_not_called()
    def test_remote_tls_connect_pins_resolved_address(self):
        connection=ai_provider._PinnedHTTPS('api.example')
        with patch('sales.commercial.ai_provider.socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]),patch('sales.commercial.ai_provider.socket.create_connection') as create,patch.object(connection._context,'wrap_socket') as wrap:
            connection.connect();self.assertEqual(create.call_args.args[0],('8.8.8.8',443));self.assertEqual(wrap.call_args.kwargs['server_hostname'],'api.example')
    def test_remote_api_key_missing_is_local_failure(self):
        config=validate_config({'enabled':True,'provider':'REMOTE','model':'fixture','endpoint':'https://api.example/chat'})
        with patch.dict('os.environ',{},clear=True),patch.object(ai_provider._PinnedHTTPS,'request') as request:
            with self.assertRaisesRegex(ValueError,'remote_api_key_missing'):ai_provider._request(config,{'candidate_id':'7'})
            request.assert_not_called()

if __name__=='__main__':unittest.main()
