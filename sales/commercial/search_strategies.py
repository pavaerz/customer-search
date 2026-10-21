"""5.0 strategy catalog: sparse intent/skill/source/market combinations.

No provider calls. These are search hypotheses, never company evidence.
Legacy catalog stays available for campaigns created before 5.0.
"""
from .planner import query_key

# Each row uses authored language-specific intents rather than mechanical
# translations or a Cartesian product of skills, regions and source domains.
SPECS=(
 ('direct_freelance','FREELANCE','Domanda freelance diretta','DIRECT_REQUEST','official_company',90,
  [('it','Cerchiamo sviluppatore WordPress freelance {geo}'),('en','looking for freelance WordPress developer {geo}')],['WordPress']),
 ('wordpress_projects','FREELANCE','Progetti WordPress','PROJECT_REQUEST','project_marketplace',88,
  [('it','"cerco" "sito WordPress" "sviluppo" {geo}'),('en','"need" "custom WordPress" developer project {geo}')],['WordPress','PHP']),
 ('woocommerce_projects','FREELANCE','Progetti WooCommerce','PROJECT_REQUEST','official_company',88,
  [('it','"cerchiamo" WooCommerce migrazione integrazione {geo}'),('en','"seeking" WooCommerce developer checkout integration {geo}')],['WooCommerce']),
 ('frontend_contracts','FREELANCE','Contratti frontend','CONTRACT','official_careers',90,
  [('it','frontend React sviluppatore "partita IVA" {geo}'),('en','hiring JavaScript React Next.js frontend contractor {geo}')],['JavaScript','React','Next.js']),
 ('website_creation','FREELANCE','Realizzazione nuovo sito','PROJECT_REQUEST','social_post',87,
  [('it','"cerchiamo professionista" "nuovo sito" {geo}'),('en','"need a new business website" developer {geo}')],['HTML','CSS','WordPress']),
 ('explicit_rebuild','FREELANCE','Richieste esplicite rifacimento','REBUILD_REQUEST','official_company',89,
  [('it','"dobbiamo rifare" "sito" professionista {geo}'),('en','"looking for" "website redesign" developer {geo}')],['WordPress','frontend']),
 ('remote_contracts','FREELANCE','Contratti remoti accessibili dall’Italia','CONTRACT','job_board',85,
  [('en','WordPress frontend independent contractor {geo}'),('en','WooCommerce React contract developer {geo}')],['WordPress','React']),
 ('agency_collaborations','AGENCIES','Collaborazioni continuative agenzie','STANDING_COLLABORATION','agency_partnership',90,
  [('it','agenzia "cerchiamo collaboratori" WordPress freelance {geo}'),('en','agency "looking for" "white label" development partner {geo}')],['WordPress','frontend']),
 ('official_careers','AGENCIES','Pagine ufficiali lavoro e partner','EXTERNAL_VACANCY','official_careers',85,
  [('it','"lavora con noi" "collaboratori esterni" sviluppo web {geo}'),('en','agency careers frontend freelance contractor {geo}')],['frontend','WooCommerce']),
 ('agency_projects','AGENCIES','Commesse di agenzie a fornitori','PROJECT_REQUEST','official_company',87,
  [('it','agenzia "cerchiamo fornitore" sviluppo ecommerce {geo}'),('en','agency "seeking" WooCommerce development contractor {geo}')],['WooCommerce','WordPress']),
 ('startup_projects','STARTUPS','MVP e progetti startup retribuiti','PAID_PROJECT','official_company',90,
  [('it','startup "cerchiamo" sviluppatore freelance MVP retribuito {geo}'),('en','startup hiring freelance web developer paid MVP {geo}')],['React','frontend']),
 ('startup_frontend','STARTUPS','Collaborazioni frontend startup','CONTRACT','official_careers',87,
  [('it','startup frontend "collaboratore esterno" {geo}'),('en','startup Next.js frontend contractor {geo}')],['React','Next.js']),
 ('startup_website','STARTUPS','Siti ed ecommerce per startup','PROJECT_REQUEST','social_post',85,
  [('it','startup "cerchiamo" realizzazione sito ecommerce {geo}'),('en','startup "looking for" website WooCommerce developer {geo}')],['WordPress','WooCommerce']),
 ('outbound_specialists','WEBSITE_REBUILD','Imprese specializzate da investigare','OUTBOUND','official_company',65,
  [('it','produttore componenti industriali sito ufficiale contatti {geo}'),('it','falegnameria arredamento su misura sito ufficiale {geo}')],[]),
 ('outbound_services','WEBSITE_REBUILD','Servizi B2B e marchi indipendenti','OUTBOUND','official_company',60,
  [('it','servizi tecnici B2B laboratorio sito ufficiale contatti {geo}'),('it','marchio artigianale produzione sito ufficiale {geo}')],[]),
)

def catalog():
    return [dict(id=id,engine=e,objective=title,demand_type=demand,source_family=source,
      query_family=id,skills=skills,languages=sorted({v[0] for v in variants}),
      geography=['TIER_1'] if demand=='OUTBOUND' else ['TIER_1','TIER_2','TIER_3'],
      time_policy='not_applicable' if demand=='OUTBOUND' else 'standing' if demand=='STANDING_COLLABORATION' else 'verify_original_14_days',
      minimum_admission='Identità da approfondire e offerta propria' if demand=='OUTBOUND' else 'Richiesta coerente o indizio specifico da verificare',
      positive=['richiedente distinto dal fornitore','competenza richiesta nel ruolo principale'],
      negative=['vendita servizi','ruolo incompatibile','fonte editoriale senza richiesta'],
      priority=priority,max_query_share=.6,minimum_exploration=True,
      metrics=['queries','credits','plausible_requests','verified_requests','duplicates','access_errors'])
      for id,e,title,demand,source,priority,variants,skills in SPECS]

def plans(engine,regions,days=14):
    from .job_activity import window
    days=window(days);regions=list(dict.fromkeys(regions));out=[];seen=set()
    preferred=('Veneto','Lombardia','Piemonte','Toscana')
    regions=sorted(regions,key=lambda r:preferred.index(r) if r in preferred else len(preferred))
    for spec in SPECS:
        id,e,title,demand,source,priority,variants,skills=spec
        if e!=engine:continue
        # Five controlled lanes; each intent gets a meaningful Italian and
        # English market variant. Outbound alone follows selected territories.
        lanes=[('it','Padova Veneto','TIER_1'),('it','Italia','TIER_1'),
               ('en','remote Italy','TIER_2'),('en','remote Europe','TIER_2'),('en','remote worldwide','TIER_3')]
        if demand=='OUTBOUND':lanes=[('it',r+' Italia','TIER_1') for r in regions for _ in variants]
        if id in ('direct_freelance','frontend_contracts'):lanes.append(('en','remote Europe','TIER_2'))
        if id=='remote_contracts':lanes=[('en','remote Italy','TIER_2'),('en','remote EU','TIER_2'),('en','remote worldwide','TIER_3')]
        for n,(lang,geo,tier) in enumerate(lanes):
            templates=[t for l,t in variants if l==lang]
            if not templates:continue
            template=templates[n%len(templates)];q=template.format(geo=geo)
            # One original public-post lane, not authenticated social scraping.
            if source=='social_post' and n==1:q='site:linkedin.com/posts/ '+q
            if id in ('direct_freelance','frontend_contracts') and n==5:q='site:linkedin.com/jobs/view/ '+q
            if source=='official_careers' and n==4:q='inurl:careers '+q
            key=query_key(q)
            if key in seen:continue
            seen.add(key)
            out.append(dict(engine=e,query=q,page=1,region=geo if demand!='OUTBOUND' else geo.removesuffix(' Italia'),
              strategy_id=id,family=id,strategy_version='5.0',intent=title,demand_type=demand,
              source_preference=source,source='linkedin' if 'site:linkedin.com' in q else 'web',
              language=lang,geography_tier=tier,search_geography_scope='selected_region' if demand=='OUTBOUND' else 'national_or_verified_remote_italy',
              discovery_period='' if demand in ('OUTBOUND','STANDING_COLLABORATION') else 'week' if days<=7 else 'month' if days<=31 else 'year',
              skills=skills,priority=priority,exploration=True,max_query_share=.6,
              segment='specialist' if demand=='OUTBOUND' else None,sector_group=id if demand=='OUTBOUND' else None))
    # Interleave territories/languages so Pilot isn't a run of local synonyms.
    buckets={id:[p for p in out if p['strategy_id']==id] for id in dict.fromkeys(p['strategy_id'] for p in out)}
    ordered=[]
    for i in range(max((len(v) for v in buckets.values()),default=0)):
        for n,v in enumerate(buckets.values()):
            # Different families start in different lanes; every lane is retained.
            if i<len(v):ordered.append(v[(i+n)%len(v)])
    return ordered
