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


def search_receipt(payload, raw):
    """Persist request parameters and comparisons, never arbitrary provider data.

    Echoed values are untrusted: retain equality flags rather than arbitrary
    response fields that could contain credentials or unrelated content.
    Missing echoes remain unknown; a returned URL is not a relevance verdict.
    """
    echo=raw.get('searchParameters')
    echo=echo if isinstance(echo,dict) else {}
    fields=('q','gl','hl','num','page','tbs')
    return {'requested':{k:payload[k] for k in fields if k in payload},
            'provider_parameters_present':bool(echo),
            'parameter_matches':{k:echo[k]==payload.get(k) if k in echo else None
                                 for k in fields if k in payload},
            'basis':'provider_parameter_echo_not_result_relevance'}

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
    from .commercial.cache_policy import inspect_cache,record_use,archive_before_refresh
    cached,cache_policy=inspect_cache(store,key)
    cache_key=key
    if cached is None:
        legacy_key='serper:search:v1:'+digest(encode(payload))
        legacy,legacy_policy=inspect_cache(store,legacy_key)
        if legacy is not None:cached,cache_policy,cache_key=legacy,legacy_policy,legacy_key
    annotate(cache_policy=cache_policy)
    if cached is not None:
        record_use(store,cache_key,'REUSE')
        annotate(cache_hit=True,credits=0,network_attempted=False,engines=['google via Serper'])
        annotate(search_receipt=cached.get('search_receipt') or
                 {'requested':payload,'provider_parameters_present':False,'basis':'legacy_cache_echo_unavailable'})
        from .commercial.resources import received_results
        received_results(cached['results'])
        return cached,True
    credential=api_key(store)
    if not credential:raise ProviderConfigurationError('Chiave Serper mancante: inseriscila nelle impostazioni. Nessun motore alternativo attivato.')
    if not available(store,'serper'):raise ProviderDeferred('Serper in pausa tecnica fino a '+health(store,'serper')['retry_at'])
    check()
    # Count attempted calls before network, including uncertain failures; never auto-refund.
    from .commercial.resources import paid_request
    paid_request()
    store.reserve('serper');check()
    annotate(cache_hit=False,credits=1,credits_estimated=1,credits_actual=None,network_attempted=True,engines=['google via Serper'])
    try:
        raw=transport(credential,payload)
        if not isinstance(raw,dict) or not isinstance(raw.get('organic'),list):
            raise ValueError('Serper: risposta priva di risultati organici verificabili')
        receipt=search_receipt(payload,raw)
        annotate(search_receipt=receipt)
        if receipt['parameter_matches'].get('q') is False:
            raise QueryError('Serper: la query restituita non corrisponde a quella inviata. Risultati non utilizzati.')
        annotate(provider_raw_results=len(raw['organic']))
        result={'results':[{'url':r['link'],'title':r.get('title',''),'content':r.get('snippet',''),
                           'engines':['google via Serper'],**{k:r[k] for k in ('date','fileFormat','fileType','mimeType','contentType') if k in r}} for r in raw['organic']
                          if isinstance(r,dict) and isinstance(r.get('link'),str)],'unresponsive_engines':[],
                'search_receipt':receipt}
    except (InterruptedError,QueryError):raise
    except Exception as exc:
        if getattr(exc,'status',None) in (400,422):raise QueryError(str(exc)) from None
        record_health(store,'serper',exc)
        if getattr(exc,'status',None) in (401,402,403):
            raise CreditLimit(str(exc)+' Correggi l’account o la chiave, poi premi Riprendi.') from None
        raise
    from .commercial.resources import received_results
    received_results(result['results'])
    check()
    archive_before_refresh(store,key)
    store.cache_set(key,result);record_use(store,key,'REFRESH');record_health(store,'serper')
    return result,False


def status(store,campaign_id=None):
    from .discovery_control import health
    with store.connect() as c:
        used=c.execute("SELECT coalesce(sum(units),0) FROM api_usage WHERE provider='serper'").fetchone()[0]
        campaign=c.execute("SELECT coalesce(sum(json_extract(details,'$.credits')),0) FROM discovery_operations WHERE campaign_id=? AND (provider='serper' OR EXISTS (SELECT 1 FROM json_each(discovery_operations.details,'$.engines') WHERE value='google via Serper'))",(campaign_id,)).fetchone()[0]
    return {'configured':bool(api_key(store)),'enabled':store.settings()['provider']=='serper',
            'health':health(store,'serper'),'requests':used,'campaign_requests':campaign,
            'remaining_credits':None,'consumed_credits':None,
            'note':'Richieste tentate conteggiate localmente, inclusi errori; saldo e addebiti effettivi non disponibili dal provider.'}
