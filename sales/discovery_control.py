"""Persistent provider health and measured acquisition. No paid adapters are enabled."""
import json
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
from .db import now, encode, domain

_context = ContextVar('discovery_measurement', default=None)


def migrate(store):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('''CREATE TABLE IF NOT EXISTS discovery_provider_health(
          provider TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0,
          retry_at TEXT, error TEXT, checked_at TEXT, last_success TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS discovery_operations(
          id INTEGER PRIMARY KEY, campaign_id INTEGER REFERENCES campaigns(id), task_id INTEGER,
          strategy TEXT, kind TEXT, provider TEXT, status TEXT, seconds REAL,
          pages INTEGER NOT NULL DEFAULT 0, cached_pages INTEGER NOT NULL DEFAULT 0,
          unique_urls INTEGER NOT NULL DEFAULT 0, details TEXT NOT NULL, created_at TEXT NOT NULL)''')
        c.execute('CREATE INDEX IF NOT EXISTS discovery_ops_campaign ON discovery_operations(campaign_id,provider,strategy)')
        c.execute('''CREATE TABLE IF NOT EXISTS discovery_branches(
          campaign_id INTEGER REFERENCES campaigns(id), strategy TEXT, region TEXT,
          cursor INTEGER NOT NULL DEFAULT 0, dry_streak INTEGER NOT NULL DEFAULT 0,
          state TEXT NOT NULL DEFAULT 'active', last_query TEXT, reason TEXT,
          PRIMARY KEY(campaign_id,strategy,region))''')
        c.execute('''CREATE TABLE IF NOT EXISTS discovery_queries(
          campaign_id INTEGER REFERENCES campaigns(id), fingerprint TEXT, query TEXT,
          strategy TEXT, region TEXT, page INTEGER, status TEXT NOT NULL DEFAULT 'pending',
          urls TEXT NOT NULL DEFAULT '[]', new_urls INTEGER NOT NULL DEFAULT 0,
          decision TEXT, can_page INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
          PRIMARY KEY(campaign_id,fingerprint))''')
        if 'can_page' not in {r[1] for r in c.execute('PRAGMA table_info(discovery_queries)')}:
            c.execute('ALTER TABLE discovery_queries ADD COLUMN can_page INTEGER NOT NULL DEFAULT 1')
        c.execute('''CREATE TABLE IF NOT EXISTS discovery_source_profiles(
          url TEXT PRIMARY KEY, sector TEXT, topics TEXT NOT NULL DEFAULT '[]',
          reliability TEXT NOT NULL DEFAULT 'Da verificare', refresh_hours INTEGER NOT NULL DEFAULT 24,
          discovered_from TEXT, checked_at TEXT)''')
        c.execute('INSERT OR IGNORE INTO research_schema VALUES (42,?)', (now(),))
        if not c.execute('SELECT 1 FROM research_schema WHERE version=50').fetchone():
            # Explicit 5.0 instruction removes historical defaults, not custom user caps.
            for key,old in [('daily_api_limit',30),('monthly_api_limit',930)]:
                c.execute("UPDATE config SET value='null' WHERE key=? AND value=?",(key,encode(old)))
            c.execute('INSERT INTO research_schema VALUES (50,?)',(now(),))



def health(store, provider=None):
    provider=provider or store.settings()['provider']
    with store.connect() as c:
        r = c.execute('SELECT * FROM discovery_provider_health WHERE provider=?', (provider,)).fetchone()
    return dict(r) if r else {'provider': provider, 'failures': 0, 'retry_at': None, 'error': None}


def available(store, provider=None):
    h = health(store, provider)
    return not h['retry_at'] or h['retry_at'] <= now()


def record_health(store, provider, error=None):
    from .operation_outcomes import safe_error
    h = health(store, provider)
    failures = h['failures'] + 1 if error else 0
    # A successful empty result resets technical health. It says nothing about relevance.
    delay = min(900, 60 * 2 ** min(4, failures-1)) if error else 0
    retry = (datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat() if error else None
    with store.connect() as c:
        c.execute('''INSERT INTO discovery_provider_health(provider,failures,retry_at,error,checked_at,last_success)
          VALUES (?,?,?,?,?,?) ON CONFLICT(provider) DO UPDATE SET failures=excluded.failures,
          retry_at=excluded.retry_at,error=excluded.error,checked_at=excluded.checked_at,
          last_success=coalesce(excluded.last_success,discovery_provider_health.last_success)''',
          (provider, failures, retry, safe_error(error) if error else None, now(), None if error else now()))
    return retry


class QueryError(ValueError):
    pass


class ProviderConfigurationError(ValueError):
    pass


class ProviderDeferred(ValueError):
    pass


def free_search(store, request_fn, expected_engines=None):
    """The adapter receives a callable; paid credentials cannot enable a fallback."""
    if not available(store,'searxng'):
        raise ProviderDeferred('SearXNG in pausa tecnica fino a '+health(store,'searxng')['retry_at'])
    try:
        result = request_fn()
        if not isinstance(result, dict) or not isinstance(result.get('results'), list):
            raise ValueError('SearXNG: risposta non valida')
        failed_engines={e[0] for e in result.get('unresponsive_engines',[]) if isinstance(e,(list,tuple)) and e}
        working_engines=set(expected_engines or [])-failed_engines
        if not result['results'] and result.get('unresponsive_engines') and not working_engines:
            raise ValueError('SearXNG: nessun motore disponibile: '+encode(result['unresponsive_engines'])[:500])
    except InterruptedError:
        raise
    except Exception as exc:
        if getattr(exc,'status',getattr(exc,'code',None)) in (400,422):
            raise QueryError(str(exc)) from None
        record_health(store, 'searxng', exc)
        raise
    record_health(store, 'searxng')
    annotate(engines=sorted({str(e) for r in result['results'] if isinstance(r,dict) for e in r.get('engines',[])}), engine_errors=result.get('unresponsive_engines', []))
    return result


def annotate(**details):
    ctx = _context.get()
    if ctx is not None:
        ctx['details'].update(details)


def page_read(page, ctx=None):
    if ctx is None:ctx = _context.get()
    if ctx is not None:
        key = 'cached' if page.get('cached') else 'pages'
        if page.get('status') == 200: ctx[key].add(page['url'])


@contextmanager
def measure(rs, campaign, task):
    payload = task['payload']
    provider = rs.store.settings()['provider'] if task['kind']=='search' else 'public:'+domain(payload.get('url',''))
    ctx = {'pages': set(), 'cached': set(), 'details': {'outcome':'completed_without_decision','qualified':False,'execution':'started'}}
    token = _context.set(ctx); started = time.monotonic(); status = 'ok'
    try:
        yield
    except InterruptedError:
        status = 'interrupted'
        ctx['details'].update(outcome='interrupted',scope='operation')
        raise
    except Exception as exc:
        from .operation_outcomes import error_outcome,safe_error
        status = 'deferred' if isinstance(exc, ProviderDeferred) else 'error'
        ctx['details'].update(error_outcome(exc,task['kind']),error=safe_error(exc))
        raise
    finally:
        ctx['details']['execution']='completed' if status=='ok' else status
        _context.reset(token)
        with rs.store.connect() as c:
            c.execute('''INSERT INTO discovery_operations(campaign_id,task_id,strategy,kind,provider,status,seconds,pages,cached_pages,unique_urls,details,created_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (campaign['id'],task.get('id'),task['strategy'],task['kind'],provider,status,round(time.monotonic()-started,3),len(ctx['pages']),len(ctx['cached']),ctx['details'].get('new_urls',0),encode(ctx['details']),now()))


def diagnostics(rs, cid):
    from .research_quality import proposed_reviews,ranked_quality
    proposals=proposed_reviews(rs.store,cid)
    with rs.store.connect() as c:
        c.execute('BEGIN')
        ops = [dict(r) for r in c.execute('SELECT * FROM discovery_operations WHERE campaign_id=?', (cid,))]
        candidates = [dict(r) for r in c.execute('SELECT * FROM discovery_candidates WHERE campaign_id=?', (cid,))]
        from .research_funnel import candidate_selection
        company_source,company_args=candidate_selection({'campaign':cid,'company_only':1})
        companies=[dict(r) for r in c.execute('SELECT * FROM '+company_source,company_args)]
        branches = [dict(r) for r in c.execute('SELECT * FROM discovery_branches WHERE campaign_id=?', (cid,))]
        queries = [dict(r) for r in c.execute('SELECT * FROM discovery_queries WHERE campaign_id=?', (cid,))]
        sources = [dict(r) for r in c.execute('SELECT s.*,p.sector,p.topics,p.reliability,p.refresh_hours,p.discovered_from FROM research_sources s LEFT JOIN discovery_source_profiles p USING(url)')]
    def aggregate(key):
        groups = {}
        def group(name):
            return groups.setdefault(name, {'name':name,'queries':0,'pages':0,'cached_pages':0,'unique_urls':0,'errors':0,'seconds':0,'companies':set(),'promising':set(),'qualified':set(),'unverifiable':set(),'rejections':{},'engines':set(),'engine_errors':[],'credits':0,'cost_eur':0,'returned_urls':0,'prefiltered':0,'duplicates':0})
        for op in ops:
            g = group(op[key]); d=json.loads(op['details'])
            g['queries'] += int(op['kind']=='search' and op['status']!='deferred')
            for field in ('pages','cached_pages','unique_urls','seconds'):g[field]+=op[field]
            g['errors'] += int(op['status']=='error')
            g['credits'] += d.get('credits',0)
            for field in ('returned_urls','prefiltered','duplicates'):g[field]+=d.get(field,0)
            if g['credits']:g['cost_eur']=None  # Account credit origin/price is not available here.
            g['engines'].update(d.get('engines',[]))
            g['engine_errors'] += [e for e in d.get('engine_errors',[]) if e not in g['engine_errors']]
        for row in candidates:
            d=json.loads(row['details']); name=row['strategy'] if key=='strategy' else d.get('acquisition_provider')
            if not name:continue  # Historical records have no reliable acquisition attribution.
            g=group(name)
            if row['state']=='rejected':g['rejections'][row['reason']]=g['rejections'].get(row['reason'],0)+1
        # Commercial yield is the current company decision, not the union of
        # all past page states. Use the same eligible company rows as the cards.
        for row in companies:
            d=json.loads(row['details']); name=row['strategy'] if key=='strategy' else d.get('acquisition_provider')
            if not name:continue
            g=group(name); ident=d.get('identity',{}).get('legal_id') or row['domain'] or row['url']
            g['companies'].add(ident)
            if row['state'] in ('promising','qualified'):g[row['state']].add(ident)
            if row['state']=='unverifiable':g['unverifiable'].add(ident)
        for g in groups.values():
            for field in ('companies','promising','qualified','unverifiable'):g[field]=len(g[field])
            g['qualified_per_100_searches']=round(100*g['qualified']/g['queries'],2) if g['queries'] else None
            g['companies_per_100_searches']=round(100*g['companies']/g['queries'],2) if g['queries'] else None
            g.update(ranked_quality([r for r in proposals if r[key]==g['name']]))
            g['engines']=sorted(g['engines']);g['seconds']=round(g['seconds'],2)
            g['seconds_per_promising']=round(g['seconds']/g['promising'],2) if g['promising'] else None
        return list(groups.values())
    return {'providers':aggregate('provider'),'strategies':aggregate('strategy'),'branches':branches,'queries':{'measured':len(queries),'empty':sum(q['status']=='observed' and not json.loads(q['urls']) for q in queries),'unproductive':sum(q['decision']=='dry' for q in queries),'awaiting_verification':sum(q['status']=='observed' and not q['decision'] for q in queries)},'health':health(rs.store),'sources':sources,'paid':{p:{'enabled':rs.store.settings()['provider']==p,'credentials_present':bool(__import__('sales.search_trial',fromlist=['api_key']).api_key(rs.store)) if p=='serper' else bool(os.getenv(k)),'max_spend_eur':None if rs.store.settings()['provider']==p else 0,'daily_request_limit':rs.store.settings()['daily_api_limit'],'reason':'Consumi conteggiati prima della richiesta; nessun acquisto automatico.'} for p,k in [('tavily','TAVILY_API_KEY'),('serper','SERPER_API_KEY')]},'note':'URL scoperti e pagine lette non sono clienti. Aziende e risultati deduplicati per identità disponibile. Richieste Serper conteggiate; saldo e origine gratuita o acquistata dei crediti non deducibili localmente. Aziende attribuite alla riga corrente selezionata anche nell’elenco; vecchie pagine promettenti non contano dopo una valutazione successiva. Scarti conteggiati per URL. Righe storiche senza provenienza escluse dai conteggi per provider.'}


def search_capabilities(store, base):
    """Inspect the configured local instance; unavailable metadata never authorizes access."""
    from .providers import api_json
    from urllib.parse import urlsplit
    p=urlsplit(base)
    if p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost') or p.username or p.password:
        raise ValueError('Metadati ammessi solo dal SearXNG locale')
    key='discovery:capabilities:'+base
    cached=store.cache_get(key,1/12)
    if cached is not None:return cached
    try:
        config=api_json(base+'/config',timeout=5)
        engines=[e for e in config.get('engines',[]) if e.get('enabled') and 'general' in e.get('categories',[])]
        result={'paging':any(e.get('paging') for e in engines),'time_range':any(e.get('time_range_support') for e in engines),'engines':[e['name'] for e in engines]} if engines else {'paging':True,'time_range':True,'engines':[]}
        store.cache_set(key,result);return result
    except (OSError,ValueError,TypeError,AttributeError):return {'paging':True,'time_range':True,'engines':[]}
