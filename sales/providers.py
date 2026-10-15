"""Provider boundaries, reserved budgets, robots, cache and public-IP pinned GETs."""
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import time
import xml.etree.ElementTree as ET
from urllib import parse,request,robotparser,error
from .config import BLOCKED
from .db import digest,now
from .access_status import AccessIssue,retry_delay


def canonical(url):
    p=parse.urlsplit(url)
    if '\\' in p.netloc or '\\' in p.path:raise ValueError('URL ambiguo: separatore inverso nel dominio o nel percorso')
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.port not in (None,80,443): raise ValueError('URL pubblico HTTP/HTTPS richiesto')
    params=[(k,v) for k,v in parse.parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('gclid','fbclid')]
    return parse.urlunsplit((p.scheme,p.netloc.lower(),p.path or '/',parse.urlencode(sorted(params)),''))
def blocked(url):
    parts=parse.urlsplit(url);host=(parts.hostname or '').lower()
    if re.search(r'/(?:oauth2?|openid)(?:/|$)',parts.path,re.I):return True
    return any(host==d or host.endswith('.'+d) for d in BLOCKED) or bool(re.search(r'(^|\.)(freelancer|indeed|glassdoor)\.',host))
def api_json(url,payload=None,headers=None,timeout=30):
    h=dict(headers or {});data=None
    if payload is not None: data=json.dumps(payload).encode();h['Content-Type']='application/json'
    try:
        with request.urlopen(request.Request(url,data,headers=h),timeout=timeout) as r:
            raw=r.read(4000000)
            return json.loads(raw)
    except error.HTTPError as exc: raise ValueError(f'Provider non disponibile (HTTP {exc.code}); nessun aggiramento o acquisto automatico.') from None

class PageConnectionError(AccessIssue):
    """A single origin is unavailable; unrelated sources remain usable."""
    def __init__(self,url,technical):
        self.url=url;self.technical=str(technical)
        super().__init__('connection_interrupted','Connessione interrotta dal sito '+parse.urlsplit(url).hostname+'. Il controllo viene saltato; la ricerca continua sulle altre fonti. Nuovo accesso consentito tra 15 minuti.',retryable=True,delay=900,url=url)

class PublicWeb:
    allow_pdf=False
    def __init__(self,store,stop=lambda:None): self.store=store;self.stop=stop;self.rules={};self.last={}
    def _raw(self,url,redirects=4,policy=True):
        self.stop();url=canonical(url);p=parse.urlsplit(url)
        if blocked(url): raise ValueError('Fonte non autorizzata per l’estrazione automatica')
        if policy: self.policy(url)
        port=p.port or (443 if p.scheme=='https' else 80)
        ips=[a[4][0] for a in socket.getaddrinfo(p.hostname,port,type=socket.SOCK_STREAM)]
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips): raise ValueError('Accesso a reti private non consentito')
        conn=http.client.HTTPConnection(p.hostname,port,timeout=12);sock=socket.create_connection((ips[0],port),timeout=12)
        try:
            if p.scheme=='https': sock=ssl.create_default_context().wrap_socket(sock,server_hostname=p.hostname)
            conn.sock=sock
            conn.request('GET',parse.urlunsplit(('','',p.path or '/',p.query,'')),headers={'Host':p.netloc,'User-Agent':'CustomerSearch/4.0','Accept':'text/html,application/rss+xml,application/atom+xml,text/plain','Accept-Encoding':'identity'})
            response=conn.getresponse()
            if response.status in (301,302,303,307,308):
                if redirects<=0: raise ValueError('Redirect non verificabile')
                return self._raw(parse.urljoin(url,response.getheader('Location','')),redirects-1,policy)
            content_type=response.getheader('Content-Type','')
            if response.status==200 and not self.allow_pdf and 'application/pdf' in content_type.lower():
                raise ValueError('Contenuto non testuale: documento PDF escluso prima del download')
            size_limit=8000000 if self.allow_pdf else 1500000
            raw=response.read(size_limit+1)
            if len(raw)>size_limit: raise ValueError('Documento troppo grande: controllo non completato' if self.allow_pdf else 'Pagina oltre 1,5 MB: controllo non completato')
            if self.allow_pdf and response.status==200 and ('application/pdf' in content_type or raw.startswith(b'%PDF-')):
                from io import BytesIO
                from pypdf import PdfReader
                from html import escape
                reader=PdfReader(BytesIO(raw))
                if reader.is_encrypted or len(reader.pages)>80:raise ValueError('PDF cifrato o oltre 80 pagine: analisi non completata')
                parts=[]
                for page in reader.pages:
                    self.stop();parts.append(page.extract_text() or '')
                    if sum(map(len,parts))>300000:raise ValueError('PDF troppo esteso: analisi non completata')
                text='\n'.join(parts)
                if len(text.strip())<50:raise ValueError('PDF non leggibile: manca un livello testuale')
                return {'status':200,'html':'<pre>'+escape(text)+'</pre>','plain_text':text,'url':url,'checked_at':now(),'content_hash':digest(text),'content_type':content_type,'cached':False}
            if len(raw)>getattr(self,'html_size_limit',size_limit):raise ValueError('Pagina oltre 1,5 MB: controllo non completato')
            if not any(t in content_type for t in ('text/','xml','json')) and response.status==200: raise ValueError('Contenuto non testuale')
            charset=re.search(r'charset=([\w-]+)',content_type)
            text=raw.decode(charset.group(1) if charset else 'utf-8',errors='replace')
            return {'status':response.status,'html':text,'url':url,'checked_at':now(),'content_hash':digest(text),'content_type':content_type,'retry_after':response.getheader('Retry-After'),'cached':False}
        finally: conn.close();sock.close()
    def policy(self,url):
        self.stop();p=parse.urlsplit(url);origin=parse.urlunsplit((p.scheme,p.netloc,'','',''))
        if origin not in self.rules:
            failure_key='robots-failure:'+origin
            cached=self.store.cache_get(failure_key,24*365) if self.store else None
            if cached and cached['until']>time.time():
                raise AccessIssue(cached['code'],cached['message'],retryable=cached['retryable'],delay=max(1,cached['until']-time.time()),url=url)
            try:
                raw=self._raw(origin+'/robots.txt',redirects=3,policy=False)
                if raw['status'] not in (200,404,410):
                    transient=raw['status'] in (408,429) or raw['status']>=500
                    raise AccessIssue('robots_temporary' if transient else 'robots_unverifiable',
                        ('robots.txt temporaneamente indisponibile: HTTP ' if transient else 'robots.txt non verificabile: risposta di accesso HTTP ')+str(raw['status']),
                        retryable=transient,delay=retry_delay(raw.get('retry_after')) if transient else 86400,url=url)
                if raw['status']==200 and re.search(r'<(?:!doctype\s+html|html|body)\b',raw['html'],re.I):
                    raise AccessIssue('robots_unverifiable','robots.txt non verificabile: ricevuta una pagina HTML, non regole leggibili.',delay=86400,url=url)
                if raw['status']==200:
                    substantive='\n'.join(line for line in raw['html'].splitlines() if line.strip() and not line.lstrip().startswith('#'))
                    if substantive and not re.search(r'^\s*(?:user-agent|sitemap)\s*:',substantive,re.I|re.M):
                        raise AccessIssue('robots_unverifiable','robots.txt non verificabile: risposta senza direttive riconoscibili.',delay=86400,url=url)
            except (TimeoutError,ConnectionError,ssl.SSLEOFError,http.client.RemoteDisconnected) as exc:
                issue=AccessIssue('robots_temporary','robots.txt temporaneamente non raggiungibile: '+str(exc),retryable=True,delay=300,url=url)
                if self.store:self.store.cache_set(failure_key,{'code':issue.code,'message':str(issue),'retryable':True,'until':time.time()+300})
                raise issue from exc
            except AccessIssue as exc:
                if self.store:self.store.cache_set(failure_key,{'code':exc.code,'message':str(exc),'retryable':exc.retryable,'until':time.time()+exc.delay})
                raise
            if raw['status'] in (404,410): lines=[]
            elif raw['status']==200: lines=raw['html'].splitlines()
            rules=robotparser.RobotFileParser();rules.parse(lines);self.rules[origin]=rules
        rules=self.rules[origin]
        if not rules.can_fetch('CustomerSearch',url): raise AccessIssue('robots_denied','Accesso escluso da robots.txt: divieto esplicito per questa pagina.',url=url)
        delay=max(0.7,rules.crawl_delay('CustomerSearch') or 0)
        rate=rules.request_rate('CustomerSearch')
        if rate: delay=max(delay,rate.seconds/max(1,rate.requests))
        until=self.last.get(origin,0)+delay
        while time.monotonic()<until: self.stop();time.sleep(max(0,min(.2,until-time.monotonic())))
        self.last[origin]=time.monotonic()
    def get(self,url,refresh=False):
        url=canonical(url)
        if blocked(url): raise ValueError('Fonte esclusa: accesso automatico non abilitato')
        key='page:'+url
        cached=None if refresh else self.store.cache_get(key,self.store.settings()['cache_hours'])
        if cached: return {**cached,'cached':True}
        origin=parse.urlunsplit((parse.urlsplit(url).scheme,parse.urlsplit(url).netloc,'','',''))
        cooldown=self.store.cache_get('access-failure:'+origin,24*365)
        if cooldown and cooldown['until']>time.time():
            if cooldown['code']=='tls_certificate':raise ssl.SSLCertVerificationError(cooldown['message'])
            raise AccessIssue(cooldown['code'],cooldown['message'],retryable=True,delay=max(1,cooldown['until']-time.time()),url=url)
        failure_key='connection-failure:'+origin
        failure=self.store.cache_get(failure_key,0.25)
        if failure:raise PageConnectionError(url,failure['error'])
        for attempt in range(2):
            try:
                result=self._raw(url);break
            except ssl.SSLCertVerificationError as exc:
                self.store.cache_set('access-failure:'+origin,{'code':'tls_certificate','message':str(exc),'until':time.time()+21600})
                raise
            except TimeoutError as exc:
                message='Timeout della lettura: origine in pausa tecnica per 5 minuti.'
                self.store.cache_set('access-failure:'+origin,{'code':'timeout','message':message,'until':time.time()+300})
                raise AccessIssue('timeout',message,retryable=True,delay=300,url=url) from exc
            except (ssl.SSLEOFError,ConnectionResetError,http.client.RemoteDisconnected) as exc:
                self.stop()
                if attempt:
                    self.store.cache_set(failure_key,{'error':str(exc)})
                    raise PageConnectionError(url,exc) from exc
                # One retry of an interrupted read, with normal certificate checks.
                for _ in range(5):self.stop();time.sleep(.1)
        if result['status']==200:
            self.store.cache_set(key,result)
            if result['url']!=url:self.store.cache_set('page:'+result['url'],result)
        elif result['status'] in (429,503):
            delay=retry_delay(result.get('retry_after'))
            message='Fonte temporaneamente non disponibile: HTTP '+str(result['status'])+'. Nessuna nuova richiesta durante la pausa tecnica.'
            self.store.cache_set('access-failure:'+origin,{'code':'http_temporary','message':message,'until':time.time()+delay})
            raise AccessIssue('http_temporary',message,retryable=True,delay=delay,url=url)
        elif result['status'] in (401,403):
            raise AccessIssue('page_restricted','Pagina non accessibile: HTTP '+str(result['status'])+'. Nessun aggiramento dell’accesso.',url=url)
        return result

class SearchProvider:
    name='abstract'
    def search(self,query,config): raise NotImplementedError
class SearXNG(SearchProvider):
    name='SearXNG locale'
    def __init__(self,store): self.store=store
    def search(self,query,config):
        base=os.getenv('SEARXNG_URL','').rstrip('/');p=parse.urlsplit(base)
        if p.scheme!='http' or p.hostname not in ('localhost','127.0.0.1'): raise ValueError('SearXNG locale non configurato')
        key='searxng:'+digest(json.dumps([base,query,config['time_range'],config['results_per_query']]))
        cached=self.store.cache_get(key,6)
        if cached is not None:return cached
        self.store.reserve('searxng')
        try:
            result=api_json(base+'/search?'+parse.urlencode({'q':query,'format':'json','language':'it-IT','categories':'general','time_range':config['time_range']}))
        except (OSError,ValueError) as exc:
            raise ValueError('Ricerca gratuita SearXNG non disponibile: '+str(exc)+'. Verifica il servizio locale; Tavily è disattivato.') from None
        if not isinstance(result,dict) or not isinstance(result.get('results'),list):raise ValueError('Risposta SearXNG non valida')
        if not result['results'] and result.get('unresponsive_engines'):
            raise ValueError('SearXNG: i motori non hanno risposto. Riprova più tardi; Tavily è disattivato.')
        items=[];seen=set()
        for item in result['results']:
            if not isinstance(item,dict) or not isinstance(item.get('url'),str):continue
            try:url=canonical(item['url'])
            except ValueError:continue
            if url in seen or blocked(url):continue
            seen.add(url)
            engines=item.get('engines') or []
            sources=', '.join(e for e in engines if isinstance(e,str)) if isinstance(engines,list) else ''
            items.append({**item,'url':url,'discovery_provider':self.name+(' · '+sources if sources else '')})
            if len(items)>=config['results_per_query']:break
        self.store.cache_set(key,items)
        return items

class RSS:
    name='Feed RSS / Atom'
    def __init__(self,web): self.web=web
    def entries(self,url):
        page=self.web.get(url)
        if page['status']!=200: raise ValueError('Feed non accessibile')
        if '<!DOCTYPE' in page['html'].upper() or '<!ENTITY' in page['html'].upper(): raise ValueError('Feed con entità XML non ammesso')
        root=ET.fromstring(page['html']);out=[]
        for item in root.iter():
            if item.tag.split('}')[-1] not in ('item','entry'): continue
            fields={e.tag.split('}')[-1]:e for e in item}
            link=fields.get('link');href=(link.get('href') or link.text or '') if link is not None else ''
            if not href: continue
            title=fields.get('title');published=fields.get('pubDate',fields.get('published'))
            out.append({'url':canonical(parse.urljoin(url,href)),'title':title.text or '' if title is not None else '', 'feed_date':published.text if published is not None else None,'discovery_provider':self.name,'feed_url':url})
        return out[:50]

class Serper(SearchProvider):
    name='Serper · Google'
    def __init__(self,store):self.store=store
    def search(self,query,config):
        from .serper_provider import search
        result,_=search(self.store,query,period=config.get('time_range',''))
        items=[]
        for item in result['results']:
            try:url=canonical(item['url'])
            except ValueError:continue
            if blocked(url):continue
            items.append({**item,'url':url,'discovery_provider':self.name})
        return items[:config['results_per_query']]

def provider(store): return Serper(store) if store.settings()['provider']=='serper' else SearXNG(store)
