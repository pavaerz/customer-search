"""Test-only child bootstrap. It is never imported by application code."""
import http.client
import io
import json
import sys
from urllib.parse import urlsplit, urljoin
from unittest.mock import patch

from sales.commercial.browser_worker import main
from sales.commercial.resources import reserve
from sales.content_policy import require_non_pdf
from sales.providers import PublicWeb


def run():
    payload=json.load(sys.stdin)
    origin=payload['pages'][0]['url'].rsplit('/',1)[0]
    def local_raw(web,url,redirects=4,policy=True):
        parsed=urlsplit(url)
        if not url.startswith(origin+'/'):raise ValueError('Offline fixture: private/external destination denied')
        if parsed.path=='/tls.css':raise ValueError('TLS handshake timed out (simulated offline)')
        if parsed.path=='/blocked.css':raise ValueError('Accesso escluso da robots.txt: divieto esplicito (simulated offline)')
        require_non_pdf(url);reserve('http_reads')
        conn=http.client.HTTPConnection(parsed.hostname,parsed.port,timeout=web.request_timeout())
        try:
            conn.request('GET',parsed.path);response=conn.getresponse()
            if response.status in (301,302):
                if redirects<=0:raise ValueError('Redirect limit')
                return local_raw(web,urljoin(url,response.getheader('Location')),redirects-1)
            kind=response.getheader('Content-Type','text/plain');require_non_pdf({'url':url,'content_type':kind})
            return {'url':url,'status':response.status,'body':response.read(1500000),'content_type':kind}
        finally:conn.close()
    if payload['pages'][0]['url'].endswith('/earlyclose'):
        from playwright.async_api import Page
        original=Page.goto
        async def close_after_navigation(page,*args,**kwargs):
            response=await original(page,*args,**kwargs);await page.close();return response
        patch.object(Page,'goto',close_after_navigation).start()
    sys.stdin=io.StringIO(json.dumps(payload))
    with patch.object(PublicWeb,'_raw',local_raw),patch('sales.safe_proxy.public_addresses',side_effect=ValueError('Offline egress forbidden')):
        main()


if __name__=='__main__':run()
