"""Small, privacy-conscious outcome vocabulary; transport success is not a lead."""
import re
from .access_status import describe


def safe_error(value):
    text=str(value)
    text=re.sub(r'https?://[^\s<>]+',lambda m:re.sub(r'//[^/@]+@','//[redacted]@',m[0].split('?')[0].split('#')[0]),text)
    text=re.sub(r'(?i)((?:api[_-]?key|token|password|authorization)\s*[:=]\s*)\S+',r'\1[redacted]',text)
    text=re.sub(r'[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}','[email]',text)
    return text[:900]


def error_outcome(error,kind):
    from .discovery_control import ProviderDeferred, ProviderConfigurationError, QueryError
    from .commercial.resources import BudgetExceeded
    if isinstance(error,BudgetExceeded):return {'outcome':'not_executed','scope':'budget','resource':error.resource,'retryable':False}
    from .serper_provider import CreditLimit
    if isinstance(error,QueryError):return {'outcome':'permanent_error','scope':'query','retryable':False}
    if isinstance(error,InterruptedError):return {'outcome':'interrupted','scope':'operation','retryable':False}
    if isinstance(error,ProviderDeferred):return {'outcome':'not_executed','scope':'provider','retryable':True}
    if isinstance(error,(CreditLimit,ProviderConfigurationError)):return {'outcome':'not_executed','scope':'provider','retryable':False}
    issue=describe(error)
    retry=issue['retryable'] if issue else bool(re.search(r'timeout|timed out|tempor|429|502|503|connection',str(error),re.I))
    scope='provider' if kind=='search' else 'domain' if issue and issue['code'].startswith(('robots','tls')) else 'url'
    return {'outcome':'temporary_error' if retry else 'permanent_error','scope':scope,'retryable':retry}


def decision(state,identity=None):
    return {'outcome':{'qualified':'valid','promising':'valid','needs_review':'unverifiable',
                      'unverifiable':'unverifiable','rejected':'not_relevant'}.get(state,'pending'),
            'commercial_status':state,'qualified':state=='qualified',
            'identity_verified':(identity or {}).get('identity_status')=='verified'}
