"""Structured access failures, with conservative access and bounded retries."""
import ssl
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta


def retry_delay(value, default=300):
    try:
        seconds=int(value) if str(value).isdigit() else parsedate_to_datetime(value).timestamp()-time.time()
        return max(default,seconds)
    except (ValueError,TypeError,OverflowError):return default


class AccessIssue(ValueError):
    def __init__(self, code, message, *, retryable=False, delay=0, url=None):
        super().__init__(message)
        self.code=code;self.retryable=retryable;self.delay=delay;self.url=url


def describe(error):
    if isinstance(error, AccessIssue):
        code=error.code;retry=error.retryable;delay=error.delay
    elif isinstance(error, ssl.SSLCertVerificationError) or 'CERTIFICATE_VERIFY_FAILED' in str(error):
        code='tls_certificate';retry=False;delay=21600
    elif isinstance(error, TimeoutError):code='timeout';retry=True;delay=300
    else:return None
    return {'code':code,'message':str(error),'retryable':retry,
            'retry_at':(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat() if retry else None,
            'next_action':'Cercare una fonte pubblica alternativa; nessun aggiramento di robots, autenticazione o certificati.'}
