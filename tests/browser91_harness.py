"""Synthetic protected-resource latency; real Chrome, no external requests."""
import io,json,sys,time
from unittest.mock import patch
from sales.commercial.browser_worker import main
from sales.providers import PublicWeb
from sales.commercial.resources import reserve

payload=json.load(sys.stdin)
origin=payload['pages'][0]['url']

def raw(web,url,**kwargs):
    from urllib.parse import urlsplit,parse_qs
    if not url.startswith(origin+'dependency.js'):
        raise AssertionError('Only the isolated fixture resource is allowed')
    params=parse_qs(urlsplit(url).query)
    until=time.monotonic()+float(params['delay'][0])
    while time.monotonic()<until:
        web.stop();time.sleep(.01)
    reserve('http_reads')
    if params.get('fail'):raise ValueError('Fixture: critical dependency unavailable')
    return {'url':url,'status':200,'content_type':'application/javascript',
            'body':b'document.body.innerHTML="<main><h1>Azienda di prova locale</h1><p>Prodotti e servizi industriali documentati nella pagina locale di test.</p></main>";'}

sys.stdin=io.StringIO(json.dumps(payload))
with patch.object(PublicWeb,'_raw',raw),patch('sales.safe_proxy.public_addresses',side_effect=AssertionError('No external transport')):
    main()
