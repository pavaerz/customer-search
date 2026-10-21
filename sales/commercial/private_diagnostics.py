"""Private, bounded validation metadata. Raw replies are never retained."""
import json,os,re,time
from pathlib import Path

def retain(store,execution_id,diagnostic,retention_hours=None):
    try:hours=float(os.environ.get('CUSTOMERSEARCH_AI_DIAGNOSTIC_HOURS','24')) if retention_hours is None else float(retention_hours)
    except ValueError:hours=24
    hours=max(0,min(hours,168));folder=store.path.parent/'ai-validation-private'
    if hours==0:return
    folder.mkdir(mode=0o700,exist_ok=True);folder.chmod(0o700)
    for f in sorted(folder.glob('validation-*.json'),key=lambda f:f.stat().st_mtime,reverse=True)[127:]:f.unlink()
    for f in folder.glob('validation-*.json'):
        if f.stat().st_mtime<time.time()-hours*3600:f.unlink()
    allowed_codes=lambda v:isinstance(v,str) and bool(re.fullmatch(r'[A-Za-z_]{1,80}',v))
    data={k:v for k,v in diagnostic.items() if k in ('code','diagnosis','reason') and allowed_codes(v)}
    data['fields']=[v for v in diagnostic.get('fields',[]) if allowed_codes(v)][:8]
    data['evidence_ids']=[v for v in diagnostic.get('evidence_ids',[]) if isinstance(v,str) and re.fullmatch(r'EVIDENCE_[a-f0-9]{20}',v)][:24]
    for k in ('response_hash','contested_fingerprint'):
        if re.fullmatch(r'[a-f0-9]{64}',str(diagnostic.get(k,''))):data[k]=diagnostic[k]
    data.update(raw_response_retained=False,created_at=time.time(),expires_at=time.time()+hours*3600)
    # Numeric app-generated execution ID; no provider-controlled filenames.
    p=folder/('validation-'+str(int(execution_id))+'.json')
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(data,f)
    p.chmod(0o600)
