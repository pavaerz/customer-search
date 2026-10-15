"""Small public sector directories, verified as discovery sources, not prospects.

Access and terms are checked again by the normal public reader/resolver. A
successful fetch never means that all listed companies are relevant or qualified.
"""
from .db import digest,now
from .research_funnel import Funnel
from .commercial_planner import hypothesis

DIRECTORIES=(
    ('Veneto','b2b','meccanica','https://www.meccanicanetwork.it/regione/veneto'),
    ('Veneto','b2b','alimentare','https://www.confindustria.vicenza.it/aziende/alimentari-e-bevande'),
    ('Veneto','b2b','alimentare','https://italmopa.com/elenco-aziende-associate-veneto/'),
    ('Lombardia','b2b','meccanica','https://www.meccanicanetwork.it/regione/lombardia'),
    ('Piemonte','b2b','meccanica','https://www.meccanicanetwork.it/regione/piemonte'),
    ('Toscana','b2b','meccanica','https://www.meccanicanetwork.it/regione/toscana'),
)

# Entry points followed from the publishers' own pages and read on 2026-10-14.
# Access/robots/linked terms are still checked at runtime; no static permission.
BUSINESS_SOURCES=(
    ('Veneto','html','https://www.venetoeconomia.it/pmi-e-imprese/'),
    ('Lombardia','rss','https://lombardia.italiaeconomy.it/feed/'),
    ('Piemonte','rss','https://piemonte.italiaeconomy.it/feed/'),
)
DEFERRED_BUSINESS_SOURCES=(
    ('Toscana','html','https://www.toscanaeconomy.it/primo-piano/dalle-imprese-toscane/',
     'Verifica 14/10/2026: i sei articoli aziendali campionati risalgono al 2024. Archivio sospeso come fonte di eventi attuali; serve una nuova verifica prima della riattivazione.'),
)


def seed_business_sources(rs,campaign):
    filters=campaign['filters'];added=0
    from .company_research import selected_strategies
    if 'change' not in selected_strategies(filters) or not rs.active(campaign['id'],campaign['generation']):return 0
    for region,kind,url,reason in DEFERRED_BUSINESS_SOURCES:
        if region in (filters.get('regions') or ['Veneto']):
            with rs.store.connect() as c:
                c.execute("INSERT INTO research_sources(url,region,kind,state,reason,checked_at) VALUES (?,?,?,'paused',?,?) ON CONFLICT(url) DO UPDATE SET state='paused',reason=excluded.reason,checked_at=excluded.checked_at",(url,region,kind,reason,'2026-10-14T09:33:18.795148+00:00'))
    for region,kind,url in BUSINESS_SOURCES:
        if region not in (filters.get('regions') or ['Veneto']):continue
        payload={'url':url,'kind':kind,'depth':0,'region':region,'publisher':True,
                 'source_scope':'business_news','research_intent':'signal',
                 'hypothesis':hypothesis('change',region,filters.get('target','b2b'),filters.get('projects'))}
        if kind=='rss':payload['access_page']=url.removesuffix('feed/')
        added+=int(Funnel(rs).offer(campaign['id'],'source','change',payload,'source:'+digest(url)))
        with rs.store.connect() as c:
            c.execute('INSERT OR IGNORE INTO research_sources(url,region,kind) VALUES (?,?,?)',(url,region,kind))
    if added:rs.event(campaign['id'],'source',f'{added} fonti territoriali accodate: articoli e imprese citate da verificare, nessuna opportunità automatica.')
    return added


def seed_directories(rs,campaign):
    filters=campaign['filters'];added=0
    if filters.get('groups')==['agencies']:return 0
    for region,profile,sector,url in DIRECTORIES:
        if region not in (filters.get('regions') or ['Veneto']) or profile!=filters.get('target','b2b'):continue
        payload={'url':url,'region':region,'strategy':'companies','company_stage':'identify','publisher':True,
                 'directory':True,'directory_depth':0,'filters':filters,'source_url':url,
                 'provider':'Elenco settoriale pubblico','acquisition_provider':'directory',
                 'research_intent':'company','hypothesis':{**hypothesis('companies',region,profile,filters.get('projects')),'sector':sector}}
        added+=int(Funnel(rs).offer(campaign['id'],'candidate','companies',payload,'candidate-url:'+digest(url)))
        with rs.store.connect() as c:c.execute("INSERT OR IGNORE INTO research_sources(url,region,kind) VALUES (?,?,'directory')",(url,region))
    if added:rs.event(campaign['id'],'source',f'{added} elenchi settoriali da verificare: le imprese elencate non sono opportunità automatiche.')
    return added
