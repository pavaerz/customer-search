"""Bounded private troubleshooting excerpts; never used as commercial proof."""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, urlunsplit

RETENTION_DAYS=7
MAX_ROWS=200
MAX_CHARS=8000


def scrub(value):
    text=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,default=lambda _: '[unsupported]')
    for name,secret in os.environ.items():
        if len(secret)>=4 and re.search(r'key|token|secret|password|credential',name,re.I):
            text=text.replace(secret,'[secret]').replace(json.dumps(secret,ensure_ascii=False)[1:-1],'[secret]')
    text=re.sub(r'(?i)\bBearer\s+[^\s"\\,}]+','Bearer [secret]',text)
    text=re.sub(r'\bsk-[A-Za-z0-9_-]+','[secret]',text)
    text=re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|password|authorization|secret)["\s]*[:=]\s*["\s]*)[^\s",}]+',r'\1[secret]',text)
    def url(match):
        try:
            u=urlsplit(match[0]);host=u.hostname or ''
            return urlunsplit((u.scheme,host,u.path,'',''))
        except ValueError:return '[url]'
    text=re.sub(r'https?://[^\s"<>]+',url,text)
    text=re.sub(r'(?<![\w.+%-])[\w.+%-]{1,256}@[\w.-]{1,256}\.[A-Za-z]{2,63}','[email]',text)
    return text[:MAX_CHARS]


def purge(c):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=RETENTION_DAYS)).isoformat()
    c.execute('DELETE FROM agent7_diagnostics WHERE created_at<?',(cutoff,))


def retain(c,execution_id,campaign_id,task,raw,errors):
    stamp=datetime.now(timezone.utc);purge(c)
    if raw is None:return False
    c.execute('INSERT OR REPLACE INTO agent7_diagnostics(execution_id,campaign_id,task,excerpt,errors,created_at) VALUES (?,?,?,?,?,?)',
        (execution_id,campaign_id,task,scrub(raw),scrub(errors),stamp.isoformat()))
    c.execute('DELETE FROM agent7_diagnostics WHERE execution_id NOT IN (SELECT execution_id FROM agent7_diagnostics ORDER BY created_at DESC,execution_id DESC LIMIT ?)',(MAX_ROWS,))
    return True
