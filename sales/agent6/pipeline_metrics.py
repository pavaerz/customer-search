"""Read-only accounting: actual attempts, saved work and unresolved dossiers."""
import json
from collections import Counter


def summarize(c,cid,records):
    calls=Counter();cache=0
    for row in c.execute('SELECT attempt,body,status FROM commercial_ai_executions WHERE campaign_id=?',(cid,)):
        b=json.loads(row['body'] or '{}')
        if row['attempt']==1:calls[b.get('purpose') or b.get('stage') or 'unattributed']+=1
        elif row['status']=='cache_hit':cache+=1
    campaign=c.execute('SELECT status FROM campaigns WHERE id=?',(cid,)).fetchone()
    terminal=campaign and campaign['status'] not in ('running','waiting','stopping')
    incomplete=Counter()
    from .completion import dossier
    for r in records:
        b=json.loads(r['body']) if isinstance(r['body'],str) else r['body']
        if dossier(b)['promising']:
            incomplete[b.get('technical_error') or ', '.join(b.get('missing',[])) or 'unresolved_commercial_checks']+=1
    return {'actual_ai_calls_by_purpose':dict(calls),'cache_hits':cache,
        'incomplete_promising_dossiers':sum(incomplete.values()),'incomplete_reasons':dict(incomplete),
        'left_incomplete_at_pause_or_end':sum(incomplete.values()) if terminal else None,
        'basis':'ledger_attempts_and_saved_decisions_not_estimated_sales',
        'historical_reclassification':False}
