"""Read-only projections: observed commercial facts, never conversion estimates."""
from collections import Counter

def engine_metrics(revisions,traces,tasks,resources):
    from .catalog import ENGINES
    result={}
    for engine in ENGINES:
        rs=[r for r in revisions if r.get('engine')==engine];ds=[d for d in traces if (d.get('engine') or d.get('origin',{}).get('engine'))==engine]
        ts=[t for t in tasks if t['strategy']==engine]
        count=lambda kind,state:sum(t.get('n',1) for t in ts if t['kind']==kind and t['state']==state)
        identities=[r.get('identity',{}) for r in rs]
        result[engine]={
          'discovery':{'queries_completed':count('search','done'),'resolutions_completed':count('resolve','done'),'appearances':len(ds),'metadata_relevant':sum(d.get('decision')=='admit' and d.get('priority',0)>=55 for d in ds),'exclusions':dict(Counter(d.get('reason') for d in ds if d.get('decision')=='exclude'))},
          'identity':{'evaluated_records':len(rs),'verified':sum(i.get('identity_status')=='verified' for i in identities),'ambiguous':sum(i.get('identity_status')!='verified' for i in identities),'attribution_conflicts':sum(bool(i.get('identity_conflicts')) for i in identities)},
          'commercial':{'explicit_requests':sum(bool(r.get('request_blocks')) for r in rs),'attributable_requests':sum(bool(r.get('verification',{}).get('request_verified')) for r in rs),'verified_currentness':sum(bool(r.get('verification',{}).get('currently_open')) for r in rs),'contact_channels_available':sum(bool(r.get('contacts')) for r in rs),'official_states':dict(Counter(r['state'] for r in rs))},
          'website':{'official_domains':sum(i.get('identity_status')=='verified' for i in identities) if engine=='WEBSITE_REBUILD' else 0,'screenings_recorded':sum(bool(r.get('screening')) for r in rs),'browser_started':sum(bool(r.get('browser')) and r['browser'].get('executed',True) for r in rs),'browser_completed':sum(bool(r.get('browser',{}).get('completed')) for r in rs),'verified_issues':sum(len([e for e in r.get('evidence',[]) if e.get('kind')=='measurement']) for r in rs),'commercially_plausible':sum(r.get('commercial_advisory',{}).get('status') in ('COMMERCIALLY_PLAUSIBLE','CONTACT_READY') for r in rs)},
          'resources':{'ledger':resources.get(engine,{}),'tasks_stopped_by_quota':sum(t.get('n',1) for t in ts if t['state']=='budget'),'accounting':'query/candidate allocations are reservations; HTTP/provider are attempted network operations; runtime is a refunded lease; no external balance known'}}
    return result
