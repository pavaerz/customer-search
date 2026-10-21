"""Search cache freshness metadata and append-only acquired versions."""
import json
from sales.db import now, encode


def migrate(c):
    c.execute('''CREATE TABLE IF NOT EXISTS commercial_search_cache_usage(
        cache_key TEXT PRIMARY KEY, acquired_at TEXT NOT NULL,
        last_used_at TEXT NOT NULL, decision TEXT NOT NULL, ttl_seconds INTEGER NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS commercial_search_cache_history(
        cache_key TEXT NOT NULL, acquired_at TEXT NOT NULL, body TEXT NOT NULL,
        PRIMARY KEY(cache_key,acquired_at))''')
    c.execute('INSERT OR IGNORE INTO research_schema VALUES (64,?)', (now(),))


def inspect_cache(store, key, ttl_seconds=21600):
    from .planner import cache_decision
    with store.connect() as c:
        row=c.execute('SELECT created_at,body FROM cache WHERE key=?', (key,)).fetchone()
        use=c.execute('SELECT last_used_at FROM commercial_search_cache_usage WHERE cache_key=?',(key,)).fetchone()
    acquired=row['created_at'] if row else None
    policy=cache_decision(acquired,use['last_used_at'] if use else None,ttl_seconds)
    return (json.loads(row['body']) if row and policy['decision']=='REUSE' else None),policy


def record_use(store, key, decision, ttl_seconds=21600):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT created_at,body FROM cache WHERE key=?',(key,)).fetchone()
        if not row:return
        c.execute('INSERT OR IGNORE INTO commercial_search_cache_history VALUES (?,?,?)',(key,row['created_at'],row['body']))
        c.execute('''INSERT INTO commercial_search_cache_usage VALUES (?,?,?,?,?)
          ON CONFLICT(cache_key) DO UPDATE SET acquired_at=excluded.acquired_at,
          last_used_at=excluded.last_used_at,decision=excluded.decision,ttl_seconds=excluded.ttl_seconds''',
          (key,row['created_at'],now(),decision,ttl_seconds))


def archive_before_refresh(store, key):
    # Preserve the prior body before the existing cache pointer is replaced.
    with store.connect() as c:
        row=c.execute('SELECT created_at,body FROM cache WHERE key=?',(key,)).fetchone()
        if row:c.execute('INSERT OR IGNORE INTO commercial_search_cache_history VALUES (?,?,?)',(key,row['created_at'],row['body']))
