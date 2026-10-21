"""Central PDF exclusion for commercial discovery, HTTP and stored evidence.

Grant readers explicitly opting into PDF keep their existing behaviour.
"""
import re
from urllib.parse import unquote, urlsplit, parse_qsl

class ExcludedPDF(ValueError):
    code='excluded_pdf'
    def __init__(self,url=''):
        self.url=url
        super().__init__('excluded_pdf: contenuto non testuale, documento PDF escluso dalla ricerca commerciale')

def is_pdf(value):
    item=value if isinstance(value,dict) else {'url':str(value or '')}
    url=str(item.get('url') or item.get('link') or '')
    for _ in range(2):url=unquote(url)
    try:
        p=urlsplit(url)
        if re.search(r'\.pdf(?:$|[/;])',p.path,re.I):return True
        if any(re.search(r'\.pdf(?:$|[?#])',v,re.I) or (k.lower() in ('format','filetype','type','output') and v.lower()=='pdf') for k,v in parse_qsl(p.query)):return True
    except ValueError:pass
    for k in ('content_type','contentType','mime','mimeType','mime_type','filetype','fileType','fileFormat','format'):
        v=str(item.get(k) or '').lower()
        if re.search(r'application/(?:x-)?pdf|\bpdf\b',v):return True
    return bool(re.match(r'^\s*\[PDF\]',str(item.get('title','')),re.I))

def require_non_pdf(value):
    if is_pdf(value):raise ExcludedPDF(value.get('url','') if isinstance(value,dict) else value)

def search_query(query):
    return query if re.search(r'(?:^|\s)-filetype:pdf(?:\s|$)',query,re.I) else query.rstrip()+' -filetype:pdf'

def note_pdf(url):
    """Log skipped ancillary documents without creating company evaluations."""
    from .commercial.resources import _context
    current=_context.get()
    if current:
        from .providers import canonical
        from .db import now,encode
        import json
        key=canonical(url) or url;task_id=getattr(current,'task_id',None)
        with current.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute("SELECT 1 FROM campaigns WHERE id=? AND generation=? AND status IN ('running','waiting')",(current.cid,current.generation)).fetchone():return
            row=c.execute("SELECT id,details FROM research_events WHERE campaign_id=? AND kind='excluded_pdf' AND url=? AND json_extract(details,'$.aggregation_version')=1 AND json_extract(details,'$.task_id') IS ? AND json_extract(details,'$.engine')=?",(current.cid,key,task_id,current.engine)).fetchone()
            if row:
                details=json.loads(row['details']);details['occurrences']+=1;details['last_seen']=now()
                c.execute('UPDATE research_events SET details=? WHERE id=?',(encode(details),row['id']))
            else:
                details={'engine':current.engine,'scope':'ancillary','task_id':task_id,'aggregation_version':1,'occurrences':1,'last_seen':now()}
                c.execute('INSERT INTO research_events(campaign_id,kind,message,url,details,created_at) VALUES (?,?,?,?,?,?)',(current.cid,'excluded_pdf','PDF escluso',key,encode(details),now()))

def skip_pdf(value):
    if not is_pdf(value):return False
    note_pdf(value.get('url','') if isinstance(value,dict) else value)
    return True
