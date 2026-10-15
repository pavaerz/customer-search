"""Explicit Serper acquisition, shared cache and persisted consumption limits."""
import fcntl
import os
import time
from contextlib import contextmanager
from .db import digest, encode
from .search_trial import api_key, transport


class CreditLimit(ValueError):
    pass


# Shared across worker processes; one paid dispatch at a time, cancellable waits.
MIN_INTERVAL = 1.0

@contextmanager
def dispatch_slot(store, check):
    path=store.path.with_suffix('.serper-dispatch.lock')
    fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600)
    with os.fdopen(fd,'r+') as lock:
        while True:
            check()
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:time.sleep(.05)
        try:
            try:last=float(lock.read() or 0)
            except ValueError:last=0
            while time.time()<last+MIN_INTERVAL:check();time.sleep(.05)
            check()
            yield
        finally:
            lock.seek(0);lock.truncate();lock.write(str(time.time()));lock.flush()
            fcntl.flock(lock,fcntl.LOCK_UN)


def search(store, query, page=1, period='', check=lambda:None):
    # The cache check must happen under the shared dispatch lock, so concurrent
    # equivalent calls do not both spend a credit. Lock ownership dies with worker.
    with dispatch_slot(store,check):
        return _search(store,query,page,period,check)


def _search(store, query, page=1, period='', check=lambda:None):
    from .discovery_control import annotate, available, health, record_health, ProviderDeferred, ProviderConfigurationError, QueryError
    if store.settings()['provider']!='serper':raise ProviderConfigurationError('Serper non attivato nelle impostazioni')
    check()
    payload={'q':query,'gl':'it','hl':'it','num':10,'page':page}
    if period in ('week','month','year'):payload['tbs']='qdr:'+{'week':'w','month':'m','year':'y'}[period]
    from .discovery_planner import query_key
    key='serper:search:v2:'+query_key({'query':query,'page':page,'period':period})
    cached=store.cache_get(key,6)
    if cached is None:cached=store.cache_get('serper:search:v1:'+digest(encode(payload)),6)
    if cached is not None:
        annotate(cache_hit=True,credits=0,network_attempted=False,engines=['google via Serper'])
        return cached,True
    credential=api_key(store)
    if not credential:raise ProviderConfigurationError('Chiave Serper mancante: inseriscila nelle impostazioni. Nessun motore alternativo attivato.')
    if not available(store,'serper'):raise ProviderDeferred('Serper in pausa tecnica fino a '+health(store,'serper')['retry_at'])
    check()
    # Count attempted calls before network, including uncertain failures; never auto-refund.
    store.reserve('serper');check()
    annotate(cache_hit=False,credits=1,network_attempted=True,engines=['google via Serper'])
    try:
        raw=transport(credential,payload);check()
        if not isinstance(raw,dict) or not isinstance(raw.get('organic'),list):
            raise ValueError('Serper: risposta priva di risultati organici verificabili')
        annotate(provider_raw_results=len(raw['organic']))
        result={'results':[{'url':r['link'],'title':r.get('title',''),'content':r.get('snippet',''),
                           'engines':['google via Serper']} for r in raw['organic']
                          if isinstance(r,dict) and isinstance(r.get('link'),str)],'unresponsive_engines':[]}
    except InterruptedError:raise
    except Exception as exc:
        if getattr(exc,'status',None) in (400,422):raise QueryError(str(exc)) from None
        record_health(store,'serper',exc)
        if getattr(exc,'status',None) in (401,402,403):
            raise CreditLimit(str(exc)+' Correggi l’account o la chiave, poi premi Riprendi.') from None
        raise
    store.cache_set(key,result);record_health(store,'serper')
    return result,False


def status(store,campaign_id=None):
    from .discovery_control import health
    with store.connect() as c:
        used=c.execute("SELECT coalesce(sum(units),0) FROM api_usage WHERE provider='serper'").fetchone()[0]
        campaign=c.execute("SELECT coalesce(sum(json_extract(details,'$.credits')),0) FROM discovery_operations WHERE campaign_id=? AND provider='serper'",(campaign_id,)).fetchone()[0]
    return {'configured':bool(api_key(store)),'enabled':store.settings()['provider']=='serper',
            'health':health(store,'serper'),'requests':used,'campaign_requests':campaign,
            'remaining_credits':None,'consumed_credits':None,
            'note':'Richieste tentate conteggiate localmente, inclusi errori; saldo e addebiti effettivi non disponibili dal provider.'}
