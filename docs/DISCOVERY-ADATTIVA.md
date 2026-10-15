# CustomerSearch — Discovery progressiva e provider

Intervento del 13 ottobre 2026 sul motore esistente. CRM, criteri di qualificazione, bozze, esclusioni e invii manuali restano invariati. Backup precedente: `data/backups/20261013T185956503392Z`, con archivi, hash e integrità SQLite verificati; migrazione e ripristino provati su copie.

## Diagnosi verificata

- La discovery preparava subito il prodotto di territori, settori e formule. Il limite di 48 task pronti nascondeva una frontiera molto più grande; non decideva se una query meritasse ulteriori pagine.
- La paginazione dipendeva da nuovi URL, anche quando le pagine originali erano irrilevanti.
- Tre errori di ricerca bloccavano tutte le query fino a Riprendi, senza distinguere il problema tecnico dalla qualità commerciale della strategia.
- SearXNG aveva Brave e DuckDuckGo attivi; Google e Bing erano presenti ma disabilitati. Le prove iniziali hanno rilevato Brave 429, DuckDuckGo CAPTCHA, Google access denied. Bing ha restituito 10 risultati in una prova, poi risposte vuote ed errori di connessione: disponibilità intermittente, non risolta definitivamente.
- Non esistono adattatori attivi Tavily/Serper nel percorso di ricerca. La presenza di chiavi nella configurazione non abilita quei servizi; i valori non sono stati esposti.
- La sezione CNA Startup propone molti articoli storici. Una fonte leggibile non è automaticamente produttiva. Il sito Confindustria Veneto Est supera il limite protettivo di 1,5 MB nella pagina indice.
- Nel pilota, un articolo di Confartigianato era preliminarmente marcato come azienda promettente. Corretto il riconoscimento dell'associazione/editore; aggiunto test. Non era un risultato qualificato. Corretta anche la risoluzione dei vecchi avvisi di premi: solo nomi con collegamenti esterni coerenti aprono il percorso di elenco aziendale.

## Architettura applicata

1. `discovery_planner.py` conserva un ramo per strategia e territorio, con cursore, ultima query, esito e motivo di pausa. Prepara al massimo una finestra di 11 query in attesa, oltre alle fonti; il lavoro viene reintegrato dopo i riscontri. Non è un limite cumulativo della campagna.
2. Le varianti cambiano formulazione, virgolette, obiettivo e settore. Le formule iniziali restano deterministiche e ispezionabili; le ricerche successive su un'impresa usano dominio verificato e termini realmente presenti nella pagina originale. La profondità dei follow-up aziendali è uno: nessuna catena ricorsiva incontrollata.
3. Query equivalenti per ordine dei termini, spazi, maiuscole e forma di e-commerce condividono una chiave. Frasi tra virgolette, restrizioni `site:`, periodo e pagina restano distinti. È una normalizzazione conservativa, non un modello di comprensione semantica universale.
4. Prima di paginare si attende la lettura originale dei candidati. Serve almeno il 25% di riscontri preliminari utili; due formulazioni improduttive sospendono quel ramo. Un insieme interamente inaccessibile produce una pausa tecnica, non un giudizio sul mercato. Tre pagine sono il massimo di profondità di una formulazione; poi si cambia query. Le condizioni sono euristiche iniziali da misurare, non prove di assenza di altre opportunità.
5. `discovery_control.py` conserva salute del provider, tentativi, tempi, errori, cache, pagine effettivamente lette e provenienza. Backoff persistente: 60, 120, 240 secondi e crescita fino a 15 minuti. Nessuna chiamata al provider durante la pausa. Dopo ripetuti errori le query sono sospese, mentre fonti e candidati proseguono; la campagna dichiara il blocco se non resta lavoro eseguibile. Riprendi rispetta i tempi del provider.
6. I metadati dell'istanza SearXNG determinano se richiedere filtri temporali e paginazione. Bing nell'istanza locale non li dichiara supportati. La cache delle ricerche considera anche l'endpoint; risposte tecnicamente fallite non vengono salvate come ricerche vuote. Documentazione: [API SearXNG](https://docs.searxng.org/dev/search_api.html), [configurazione motori](https://docs.searxng.org/admin/settings/settings_engines.html).
7. RSS, Atom, sitemap e pagine editoriali restano indipendenti dalla ricerca web. I sommari dei feed servono a scegliere pagine da leggere, mai come prove per qualificare. Corretti gli URL relativi. Un indice troppo grande può lasciare in coda le sitemap dichiarate nei suoi robots; questo fallback non si applica a divieti, login, CAPTCHA o accesso negato.
8. Tre feed territoriali verificati sono aggiunti al catalogo: CNA Veneto, Veneto Economia, Confartigianato Vicenza. I profili conservano argomenti osservati, origine, controllo e frequenza indicativa; settore e affidabilità commerciale rimangono da verificare quando ignoti. I filtri societari, geografici e commerciali si applicano dopo la discovery.
9. Le campagne precedenti mantengono task e ID. Solo le combinazioni generiche riconoscibili del vecchio generatore, mai iniziate, vengono marcate `superseded`; query manuali, identità da risolvere, paginazioni già avviate e candidati vengono conservati. Nessuna cancellazione automatica della coda.

La scelta progettuale principale è premiare il contributo di una ricerca alle prove, non il numero di URL. Questo consente di misurare separatamente problemi di accesso, fonti irrilevanti e verifiche ancora incomplete.

## Misurazione e interfaccia

**Preferenze e attività → Come sta andando la ricerca** apre una diagnostica secondaria. Mostra query, pagine lette/cache, URL acquisiti, identità verificate, promettenti attuali, qualificati, errori, tempi, motivi degli scarti e pause dei rami. Endpoint: `GET /api/campaigns/{id}/diagnostics`.

I dati per provider attribuiscono i candidati alla prima fonte nota e separano il provider di acquisizione dalle successive letture sul dominio aziendale. I risultati commerciali sono deduplicati per identità disponibile. I record storici senza provenienza non ricevono un'attribuzione inventata. Il tempo per promettente è descrittivo, non una previsione; le righe del provider di lettura possono non avere candidati attribuiti. La diagnostica si aggiorna all'apertura.

I costi attuali sono zero; i provider a pagamento sono chiusi con limite zero anche in presenza di credenziali. Il confine di adattamento è separato dalle regole commerciali. Un futuro adattatore dovrà avere autorizzazione esplicita, prenotazione atomica della spesa prima della chiamata, contabilità delle risposte e fallback gratuito. **Questa release non implementa né simula consumi, listini o integrazioni a pagamento.**

## Confronto riproducibile

`docs/discovery-comparison.json` confronta il codice discovery estratto dal backup con quello nuovo, sugli stessi tre obiettivi e con un massimo uguale di nove richieste nel protocollo. È un replay sintetico dichiarato: HTML controllati con nomi, domini e identità attese. Non è un esperimento di conversione o un benchmark rappresentativo del mercato.

| Misura | Prima | Dopo |
|---|---:|---:|
| Frontiera iniziale, Veneto e medesimo catalogo fonti | 152 | 18 |
| Query eseguite nel replay | 9 | 8 |
| Pagine originali esaminate | 9 | 7 |
| Candidati preliminari pertinenti | 6 | 6 |
| Identificazioni corrette sui 6 controlli | 6 | 6 |
| Pagine aggiuntive di una query irrilevante | 2 | 0 |

Tempo del replay: circa 0,20 s prima e 0,27 s dopo, cioè circa 0,033/0,044 s per promettente. Il controllo persistente aggiunge overhead locale: **non si dichiara una maggiore velocità CPU**. Si riducono letture inutili mantenendo i controlli positivi del campione. Qualificati e fallimenti della verifica approfondita sono `null`: quella fase non è stata eseguita nel replay e non va simulata con numeri.

## Pilota reale e limiti

Rapporto: `docs/discovery-live-pilot.json`; database separato in `data/discovery-pilots/`. Tre obiettivi di query e cinque fonti; massimo dodici letture preliminari nel protocollo, non un limite operativo dell'app.

Nell'ultima esecuzione SearXNG ha fallito con un errore di connessione di Bing. Le due richieste successive sono state differite dal circuito, senza altri tentativi di rete. Quattro fonti sono state lette; Confindustria Veneto Est è risultata troppo grande. Dodici articoli restano da approfondire e identificare, **nessuna azienda qualificata è stata prodotta da questo pilota**. La verifica approfondita completa non è stata eseguita: non è possibile stimarne tasso di successo o falsi negativi.

La revisione degli estratti e il replay delle pagine originali registrate (`docs/discovery-pilot-review.json`, 12 pagine, nessuna chiamata di rete) hanno mostrato soprattutto editori/associazioni, notizie di eventi e archivi di premi. Il caso Confartigianato è stato corretto e controllato nuovamente. Un articolo su Carron resta una fonte da cui identificare e filtrare il soggetto, non un cliente accettato; le S.p.A. rimangono escluse dalle regole. Gli articoli CNA datati non sono segnali attuali: possono soltanto aiutare a individuare nomi da verificare.

**Risultato dimostrato:** meno attività predisposte, paginazione improduttiva evitata nel replay, provider differito invece di chiamato ripetutamente, fonti indipendenti lette, separazione editore/azienda migliorata. **Non dimostrato:** maggiore copertura commerciale sul mercato, precisione della shortlist reale, un cliente acquisito. Il campione reale è insufficiente.

Un provider a pagamento potrebbe rendere più affidabile l'accesso all'indice di ricerca; non risolverebbe automaticamente qualità delle fonti o intenzione d'acquisto. Prima di autorizzarlo serve un confronto separato, con costo massimo concordato e identici obiettivi. Nessun acquisto o servizio a pagamento è stato attivato.

## File e verifiche

- Nuovi `sales/discovery_planner.py` e `sales/discovery_control.py`: pianificazione, salute, telemetria, schema additivo.
- `research_discovery.py`: query misurate, RSS/sitemap e provenienza; `research_worker.py`: integrazione, backoff, ripresa.
- `research_store.py`, `research_funnel.py`: migrazioni, catalogo, attribuzione e gestione della frontiera. `research_analysis.py`: misura delle letture anche nei thread. `research_triage.py`: distinzione associazione/editore.
- `sales/server.py`, `static/research.js`: diagnostica protetta nella UI. `searxng/config/settings.yml`: Bing attivo; motori con accesso negato/CAPTCHA sospesi, senza eludere i blocchi.
- Test aggiornati e `tests/test_discovery_control.py`; script di confronto, pilota, migrazione e verifiche browser.

Suite: **193 test superati**. Chrome a 390 e 1440 px: filtri, paginazione, esiti, diagnostica, Cerca clienti, errori di avvio, doppio clic, Stop/Riprendi e preferenze. Nessun errore JavaScript rilevato. Worker reale: Stop circa 0,014 s e 0,017 s dopo ripresa, su database temporaneo. Migrazione eseguita due volte, righe precedenti conservate, integrità/FK valide, ripristino e hash verificati (`docs/discovery-migration.json`).

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/benchmark_discovery.py
.venv/bin/python scripts/check_funnel_ui.py
.venv/bin/python scripts/check_search_button.py
.venv/bin/python scripts/smoke_worker41.py
.venv/bin/python scripts/pilot_discovery_control.py
```

L'ultimo comando consulta fonti reali e salva un nuovo database isolato. Gli altri controlli usano fixture o processi locali, senza inserire risultati di prova nel CRM.

## Utilizzo

L'app aggiornata è su `http://127.0.0.1:8765`. Ricarica con ⌘R, premi Avvia ricerca e consulta anche Candidati promettenti/Tutta la discovery. Lo stato spiega gli impedimenti; nessun risultato incompleto conta tra i 50. Ferma ricerca conserva il lavoro; Riprendi conserva la stessa campagna. Per riavviare manualmente: `docker compose up -d searxng` e `.venv/bin/python app.py`.
