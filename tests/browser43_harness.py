"""Synthetic slow-policy dependency, no external transport, real Chromium."""
import io,json,sys,time
from unittest.mock import patch
from sales.commercial.browser_worker import main
from sales.providers import PublicWeb
from sales.commercial.resources import reserve
payload=json.load(sys.stdin);origin=payload['pages'][0]['url']
def raw(web,url,**kwargs):
 if url!=origin+'phase43slow.js':raise AssertionError('No external retrieval in fixture')
 # Cancellable authorization latency, deliberately crossing first render phase.
 until=time.monotonic()+1.3
 while time.monotonic()<until:web.stop();time.sleep(.01)
 reserve('http_reads')
 return {'url':url,'status':200,'body':b'document.body.insertAdjacentHTML("beforeend","<h2>Dipendenza completata</h2>");','content_type':'application/javascript'}
sys.stdin=io.StringIO(json.dumps(payload))
with patch.object(PublicWeb,'_raw',raw),patch('sales.safe_proxy.public_addresses',side_effect=AssertionError('Offline')):
 main()
