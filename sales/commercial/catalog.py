"""Finite, distinct discovery plans; scores are priorities, never probabilities."""
ENGINES={'FREELANCE':'Freelance','AGENCIES':'Agenzie','STARTUPS':'Startup','WEBSITE_REBUILD':'Siti da rifare'}
STATES=('VERIFIED','POTENTIAL','NEEDS_REVIEW','REJECTED','UNVERIFIABLE')
# New admission/geography/target-fit rules must not reuse old rejected decisions.
VERSIONS={engine:(15 if engine=='WEBSITE_REBUILD' else 17) for engine in ENGINES}
from .strategies import FAMILIES,SEGMENTS
QUERIES={e:tuple(f[1] for f in families) for e,families in FAMILIES.items()}
QUERIES['WEBSITE_REBUILD']=tuple(words+' "catalogo" {area}' for _,words in SEGMENTS)

def query_source(template):
    return 'instagram' if 'site:instagram.com' in template else 'linkedin' if 'site:linkedin.com' in template else 'web'

BUDGETS={'max_pages':3,'max_reads':6,'max_browser_pages':3,'max_candidates_per_engine':500,'browser_sample_percent':25,'browser_timeout_ms':20000,'browser_total_seconds':120,'browser_max_resources':60,'max_queries_per_engine':24,'max_provider_requests':60,'max_serper_credits':60,'max_http_reads':600,'max_followups':50,'max_browser_runs':20,'max_runtime_seconds':3600}
PILOT={'max_queries_per_engine':3,'max_pages':1,'max_provider_requests':7,'max_serper_credits':7,'max_http_reads':200,'max_followups':4,'max_candidates_per_engine':15,'max_browser_runs':2,'max_runtime_seconds':600}

EXTENDED={**PILOT,'max_queries_per_engine':10,'max_candidates_per_engine':40,'max_provider_requests':15,'max_serper_credits':15,'max_http_reads':350,'max_followups':8,'max_browser_runs':4,'max_runtime_seconds':1200}
PROFILES={'pilot':{**BUDGETS,**PILOT},'extended':{**BUDGETS,**EXTENDED},'standard':BUDGETS}

# Opt-in proposal. Existing profile dictionaries and persisted budgets unchanged.
DEEP_PROFILE={**PROFILES['extended'],'max_queries_per_engine':24,'max_pages':2,
 'max_provider_requests':36,'max_serper_credits':36,'max_candidates_per_engine':60,
 'max_http_reads':450,'max_followups':12,'max_runtime_seconds':1800}

def options(filters):
    from .job_activity import window
    window(filters.get('max_job_age_days',14))
    from sales.agent6 import FLOWS,canonical_flow
    allowed=set(FLOWS)|{'LINKEDIN'} if filters.get('agent_version')=='6.0' else ENGINES
    engines=filters.get('commercial_engines')
    if not isinstance(engines,list) or not engines or any(not isinstance(e,str) or e not in allowed for e in engines):raise ValueError('Motori commerciali non validi')
    if filters.get('agent_version')=='6.0' and len({canonical_flow(e) for e in engines})!=len(set(engines)):
        raise ValueError('SOCIAL e LINKEDIN indicano lo stesso canale: selezionalo una sola volta.')
    if not isinstance(filters.get('work_budget',{}),dict):raise ValueError('Budget operativo non valido')
    profiles={**PROFILES,'deep':DEEP_PROFILE}
    if filters.get('mode','standard') not in profiles:raise ValueError('Modalità non valida')
    budgets={**profiles[filters.get('mode','standard')],**filters.get('work_budget',{})}
    maxima={'max_pages':10,'max_reads':12,'max_browser_pages':5,'max_candidates_per_engine':10000,'browser_sample_percent':100,'browser_timeout_ms':60000,'browser_total_seconds':300,'browser_max_resources':200,'max_queries_per_engine':1000,'max_provider_requests':10000,'max_serper_credits':10000,'max_http_reads':50000,'max_followups':10000,'max_browser_runs':1000,'max_runtime_seconds':86400}
    if set(budgets)!=set(BUDGETS) or any(type(v)!=int or not (0 if k=='browser_sample_percent' else 1)<=v<=maxima[k] for k,v in budgets.items()):raise ValueError('Budget operativo non valido')
    return list(dict.fromkeys(engines)),budgets

def plan(engine):
    from .geography import REGIONS
    from .strategies import plans
    return plans(engine,REGIONS)
