"""Extensible commercial strategies. Catalog metadata is not market evidence."""
SEGMENTS=(
 ('metal','carpenteria metallica lavorazioni'),('furniture','falegnameria arredamento su misura'),
 ('technical','servizi tecnici B2B progettazione'),('serramenti','serramenti su misura laboratorio'),
 ('cnc','officina lavorazioni CNC conto terzi'),
 ('machinery','costruzione macchinari speciali'),('components','componenti meccanici produzione specializzata'),
 ('plants','impiantistica industriale servizi tecnici'),('packaging','packaging imballaggi produzione'),
 ('food','produzione alimentare laboratorio artigianale'),('hospitality','albergo indipendente agriturismo prenotazioni'),
 ('retail','negozio specializzato attrezzature professionali'),
)
STRATEGIES={
 'WEBSITE_REBUILD':{'target':'Imprese specializzate con offerta e contatti verificabili','sources':['official_company'],
  'positive':['offerta propria','dominio ufficiale','canale aziendale'],'negative':['directory','grande gruppo documentato','nuova piattaforma già realizzata'],
  'admission':'Impresa candidata, non editore o intermediario','deepening':'Target fit documentato prima del browser','stop':'Controprove, target incompatibile o budget conservato'},
 'FREELANCE':{'target':'Committenti che cercano competenze web esterne','sources':['official_careers','linkedin_job','public_post'],
  'positive':['ruolo web richiesto','rapporto esterno'],'negative':['servizi offerti','ruoli correlati','venditore commerciale'],
  'admission':'Domanda nel ruolo principale o ambiguità specifica','deepening':'Committente, contratto, fonte e attualità','stop':'Rapporto incompatibile, chiusura o quota'},
 'AGENCIES':{'target':'Agenzie con richiesta o pratica tecnica esterna dichiarata','sources':['official_collaboration','official_careers','public_post'],
  'positive':['invito a freelance','policy tecnica esterna'],'negative':['solo servizi','contatto commerciale generico'],
  'admission':'Richiesta tecnica o invito a esterni; non servizi venduti ai freelance','deepening':'Pagina collaborazioni/lavoro pertinente','stop':'Sola offerta senza segnale o quota'},
 'STARTUPS':{'target':'Startup con bisogno tecnico esplicito','sources':['official_project','individual_hosted_job','public_post'],
  'positive':['MVP commissionato','partner tecnico cercato'],'negative':['biografia CTO','governance','fornitore alle startup'],
  'admission':'Domanda tecnica attribuibile','deepening':'Richiedente distinto da editore; compenso e rapporto','stop':'Cofondatore full-time non compatibile, richiesta chiusa o quota'},
}
FAMILIES={
 'FREELANCE':(
 ('wordpress_request','WordPress (cerchiamo OR ricerchiamo) freelance {area}','direct'),
 ('external_frontend','frontend (cerchiamo OR ricerchiamo) "partita IVA" {area}','official_careers'),
 ('commission_ecommerce','WooCommerce sviluppatore (cerco OR cerchiamo) {area}','direct'),
 ('linkedin_external','site:linkedin.com/jobs/view/ WordPress freelance Italia','linkedin_job'),
 ('public_request','site:linkedin.com/posts/ "cerchiamo" sviluppatore freelance Italia','public_post'),
 ('remote_italy','WordPress developer freelance remote Italy','official_careers'),
 ('remote_europe','frontend contractor remote Europe','official_careers'),
 ('ecommerce_contract','e-commerce developer contract Italia','direct')),
 'AGENCIES':(
 ('agency_open','agenzia "cerchiamo" sviluppatore WordPress freelance {area}','direct'),
 ('agency_policy','"diventa partner" "sviluppatori web" {area}','official_collaboration'),
 ('agency_careers','"lavora con noi" WordPress "partita IVA" {area}','official_careers'),
 ('agency_outsource','"cerchiamo" "partner di sviluppo" web {area}','direct'),
 ('agency_development','"cerchiamo collaboratori" sviluppatori freelance {area}','official_collaboration'),
 ('agency_wordpress','"siamo alla ricerca" web developer freelance {area}','official_careers'),
 ('agency_outsourcing','agenzia "cerchiamo" fornitore sviluppo e-commerce {area}','direct'),
 ('agency_support','"collaboriamo con" "sviluppatori" freelance {area}','official_collaboration'),
 ('agency_post','site:linkedin.com/posts/ agenzia "cerchiamo" sviluppatore freelance Italia','exploration')),
 'STARTUPS':(
 ('startup_paid','startup "cerchiamo" sviluppatore freelance {area}','direct'),
 ('startup_commission','startup "cerchiamo" "sviluppatore freelance" piattaforma MVP {area}','official_project'),
 ('startup_partner','startup "cerchiamo un partner" sviluppo piattaforma {area}','direct'),
 ('startup_supplier','startup cerchiamo fornitore sviluppo MVP {area}','official_project'),
 ('startup_external','startup "cerchiamo" sviluppatore esterno piattaforma web {area}','direct'),
 ('startup_prototype','startup "cerchiamo" sviluppatore prototipo web freelance {area}','direct'),
 ('startup_post','site:linkedin.com/posts/ startup "cerchiamo" sviluppatore freelance Italia','exploration'),
 ('startup_cofounder','startup cerchiamo cofounder tecnico compenso {area}','exploration')),
}

def plans(engine,regions):
    if engine=='WEBSITE_REBUILD':
        families=[('specialist_'+key,words+' sito ufficiale contatti {area}','official_company',key) for key,words in SEGMENTS]
    else:families=[(*f,None) for f in FAMILIES[engine]]
    return [{'engine':engine,'query':template.format(area=region+' Italia'),'region':region,'page':1,
      'family':family,'search_geography_scope':'remote_italy_eligibility' if family in ('remote_italy','remote_europe') else 'national_discovery_selected_regions_checked_on_company' if '{area}' not in template else 'selected_region','segment':segment,'source_preference':source,'source':('linkedin' if 'site:linkedin.com' in template else 'instagram' if 'site:instagram.com' in template else 'web'),
      'intent':STRATEGIES[engine]['target'],'strategy_version':'4.5' if engine=='FREELANCE' else '4.3','exploration':source=='exploration',
      'sector_group':({'metal':'manufacturing','cnc':'manufacturing','machinery':'manufacturing','components':'manufacturing','serramenti':'construction','plants':'construction','furniture':'furniture','technical':'professional','packaging':'packaging','food':'food','hospitality':'tourism','retail':'specialist_trade'}.get(segment)),
      'site_complexity':'UNKNOWN','official_site':'TO_VERIFY'}
      for region in regions for family,template,source,segment in families]
