"""Verifiable commercial hypotheses. Discovery intent, never evidence of demand."""

HYPOTHESES = {
    'companies': ('Presenza commerciale', 'website', 'Un’impresa del segmento può avere un’offerta non rappresentata adeguatamente online.',
                  'Identità, attività e mercati effettivi; discrepanza documentata e perimetro completo.', 'Sito già adeguato; intervento risolvibile con aggiornamenti di contenuto.'),
    'change': ('Nuovi mercati e offerta', 'website', 'Un cambiamento dell’offerta o del mercato può richiedere un progetto digitale completo.',
               'Evento recente riferito all’impresa e lacuna pertinente verificata sul sito.', 'Evento già rappresentato; traduzione o pagina aggiuntiva sufficienti.'),
    'investment': ('Investimento commerciale', 'ecommerce', 'Un investimento nella distribuzione può accompagnare un nuovo canale digitale.',
                   'Beneficiario identificato, investimento effettivo e progetto digitale ancora irrisolto.', 'Bando aperto senza beneficiari; investimento non digitale o progetto già consegnato.'),
    'startup': ('Nuova iniziativa', 'website', 'Un nuovo marchio o impresa può avere un progetto digitale ancora da realizzare.',
                'Impresa attiva identificata, lancio attuale, ambito e soluzione esistente verificati.', 'Startup fuori target, sito già completo, semplice annuncio di costituzione.'),
    'hiring': ('Sviluppo commerciale digitale', 'ecommerce', 'Un ruolo digital può segnalare un cambiamento da verificare insieme agli strumenti esistenti.',
               'Datore effettivo e responsabilità digitali; bisogno di progetto distinto dall’assunzione.', 'Offerta dipendente scambiata per commessa; portale già operativo.'),
    'process': ('Processo articolato', 'webapp', 'Un processo pubblico complesso può giustificare uno strumento operativo circoscritto.',
                'Procedura osservabile, complessità e limite documentati; integrazioni e sicurezza delimitate.', 'Email da sola; volumi immaginati; gestionale già adeguato o sistema critico.'),
    'explicit': ('Progetto richiesto', 'website', 'Un committente identificabile cerca un fornitore per un progetto completo.',
                 'Richiesta attuale, committente reale, perimetro e contatto verificati.', 'Annuncio dipendente, offerta di un’agenzia, manutenzione, fornitore già scelto.'),
    'partner': ('Collaborazioni web documentate', 'website', 'Un’agenzia che cerca competenze web esterne può essere un contatto pertinente.',
                'Ruolo web, condizioni freelance, identità e contatto verificati; progetto completo e budget richiedono una qualifica separata.', 'Semplice elenco di servizi, contratto dipendente o P.IVA riferita a un altro ruolo.'),
}
PORTALS = {
    'Veneto': ('venetoeconomia.it', 'nordesteconomia.gelocal.it', 'confindustriavenest.it'),
    'Lombardia': ('lombardia.italiaeconomy.it', 'assolombarda.it'),
    'Piemonte': ('piemonte.italiaeconomy.it', 'ui.torino.it'),
    'Toscana': ('confindustriatoscanacentroecosta.it',),
}
EVENTS = {
    'change': ('nuova linea prodotti', 'espansione mercati esteri', 'lancio nuovo marchio', 'nuova rete distributori', 'nuova divisione'),
    'investment': ('ha investito distribuzione', 'ha ottenuto finanziamento vendita online'),
    'startup': ('nuovo marchio lancio', 'nuova impresa produzione'),
    'hiring': ('cerca responsabile ecommerce', 'ricerca responsabile marketing'),
    'process': ('configurazione su misura preventivo', 'rivenditori multilistino ordini', 'procedura ordini configurabili'),
}


def hypothesis(strategy, region, profile='b2b', projects=None):
    region=region or ''  # Alternative sources may not establish a territory yet.
    label, project, premise, required, contrary = HYPOTHESES.get(strategy,HYPOTHESES['companies'])
    projects=projects or ['website','ecommerce','webapp']
    # This is an avenue to investigate, never a claim that any particular firm needs it.
    return {'id':strategy+':'+profile+':'+region, 'label':label,'territory':region,'segment':profile,
            'project':project if project in projects else projects[0], 'premise':premise,
            'required_evidence':required,'counterevidence':contrary,
            'exclusions':['S.p.A. e grandi gruppi','Aree escluse','Interventi minori','Identità non verificata'],
            'sources':['Siti ufficiali di aziende e agenzie','Richieste di fornitori','Annunci freelance indicizzati su LinkedIn, da verificare'],
            'status':'hypothesis'}


def queries(strategy,region,profile):
    from .company_research import regional_sectors
    sectors=regional_sectors(region,profile)
    portals=PORTALS.get(region,());seen=set()
    # Keep the business event together. The provider already applies a rolling
    # time filter; a literal year attracted grants/laws instead of company news.
    phrases={'nuova linea prodotti':'"nuova linea" prodotti',
             'espansione mercati esteri':'"mercati esteri" espansione',
             'lancio nuovo marchio':'"nuovo marchio"',
             'nuova rete distributori':'"distributori" "nuova rete"'}
    events=EVENTS[strategy]
    # Explore different businesses and events before exhausting all formulations
    # for the first sector. Keep every pair, with deterministic ordering on Resume.
    for round_index in range(len(events)):
        for sector_index,sector in enumerate(sectors):
            event_index=(round_index+sector_index)%len(events)
            event=events[event_index]
            terms=phrases.get(event,'"'+event+'"' if strategy=='change' else event)
            choices=[f'{sector} {region} {terms} -agenzia -"come fare"']
            if portals:
                portal=portals[(sector_index+event_index)%len(portals)]
                # Alternate open web and a territorial source immediately.
                # Do not force every portal article to mention our first sector.
                choices.append(f'site:{portal} {terms}')
            for query in choices:
                if query not in seen:seen.add(query);yield query


def source_payload(payload):
    """Retain the planning contract across queue stages and provenance."""
    return {k:payload[k] for k in ('hypothesis','research_intent','source_role','root_query_key','investigation_question','alternative_source','direct_channels','search_hint') if k in payload}
