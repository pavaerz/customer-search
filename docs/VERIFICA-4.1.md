# CustomerSearch 4.1 — verifica del 13 ottobre 2026

## Stato della consegna

App locale aggiornata, migrazione additiva, discovery preliminare separata dalla qualificazione, frontiera persistente, metriche e feedback commerciale. Nessun invio, acquisto o pubblicazione. La produzione resta vuota come richiesto nella pulizia precedente; tutti i campioni sono in database separati.

**Non è ancora dimostrata l'efficacia commerciale.** Il pilota non produce una shortlist da contattare. La nuova discovery riesce però a passare dalle fonti editoriali a un campione di 20 siti aziendali esplicitamente collegati da un elenco pubblico, anche quando SearXNG non è utilizzabile. Non sono 20 opportunità qualificate.

## Backup, dati e ripristino

Backup precedente alle modifiche: `data/backups/20261013T181253135811Z/`. `scripts/verify_migration41.py` applica due volte lo schema su una copia, confronta tutte le righe precedenti, controlla integrità e chiavi esterne, verifica gli hash dell'archivio e ripristina un database identico. Esito: superato, [manifest](migration41.json).

Dopo l'avvio reale: tabelle companies, prospects, interactions, dismissed_companies, target_exclusions, workspace_archive e workspace_resets identiche al backup. Configurazioni, credenziali e memoria dei contatti preservate. Il campione 4.0 non è stato riutilizzato come nuova discovery.

## Collaudo tecnico

- **172 test automatici superati**: qualificazione precedente, migrazione, HTTP, privacy dei backup, stop e risultati tardivi, ripresa, source filtering, frontiera limitata e fair scheduling, conservazione degli ID delle vecchie code, budget finanziamento diverso da budget progetto, gare, memoria dei contatti preliminari, esiti ripetuti deduplicati, elenco storico, citazioni inventate, homepage datata, link di menu e attribuzione di articoli multi-azienda.
- Browser: **48 combinazioni** di otto viste e sei larghezze (320, 390, 768, 1024, 1440, 1920), senza overflow della pagina né errori JavaScript. Verificati filtri, focus durante polling, note non salvate, errori recuperabili, conferma contatto, eliminazione, cinque tab del dossier e drag and drop touch della pipeline.
- Nuove funzioni 4.1 a 390 e 1440 px: tre fasi, conteggi, paginazione, esiti manuali, conservazione del campo in modifica e metriche delle 12 strategie. [Rapporto browser](UI-AUDIT-4.1.json).
- Coordinatore reale su DB temporaneo: primo Stop **0,034 s**, Stop dopo ripresa **0,014 s**, generazione cambiata, task conservati, coda pronta entro 48. [Misurazione](live-smoke41.json).
- Server reale risponde `version=4.1`, zero schede e nessuna campagna di produzione attiva. Tavily disattivato, modello locale.

## Diagnosi 4.0

Riprodotta dal database precedente, non stimata: 8.223 dei task pendenti provenivano dalle sitemap. Due query completate, 349 bloccate, 20 identità esaminate dopo riconciliazione. I limiti sono di copertura, generazione della coda, riconoscimento dei soggetti e verifica; non dimostrano un mercato privo di opportunità. Dettagli in [architettura](ARCHITETTURA-4.1.md).

## Pilota 4.1: fasi e limiti

### Query e fonti indipendenti

`scripts/pilot41.py` ha tentato una query per ciascuna delle 11 famiglie; la correlazione non è un provider né una query. Tutte le query di questo campione hanno incontrato errori dei motori SearXNG: Brave sospeso/429 e DuckDuckGo crash/CAPTCHA. Non aggirati. Pertanto **la copertura reale per ciascuna strategia non è validata**, benché scheduling e routing siano verificati nei test.

Fonti provate attraverso lo stesso lettore protetto dell'app:

- [VenetoUP](https://venetoup.com/): pagina pubblica disponibile; `/feed/` restituisce HTML, non viene presentato come RSS funzionante.
- [Veneto Sviluppo](https://venetosviluppo.it/index.php/news): notizie, RSS e Atom dichiarati disponibili. Avvisi di reclutamento e strumenti finanziari generici non diventano commesse.
- [CNA Veneto — Startup](https://cnaveneto.it/startup/): pagina, feed generale, feed di categoria e indice sitemap disponibili.
- [Confindustria Veneto Est](https://www.confindustriavenest.it/stampa-e-media/comunicati-stampa): risposta oltre il limite tecnico di 1,5 MB, conservato. Fonte non verificata con successo da questo lettore.

I campioni iniziali da dieci pagine contenevano ancora comunicati generici, menu e avvisi di lavoro. Sono stati corretti filtro della navigazione, riconoscimento dei bandi non commerciali, decodifica `&amp;` degli URL RSS e separazione editore/azienda. Le ripetizioni sugli stessi URL sono regressioni, **non campioni indipendenti che aumentano la precisione**. Tracce in `data/pilot41*/pilot-discovery.json` e `pilot-qualify.json`.

### Nuovo campione nominativo

L'[elenco CNA delle imprese Nord-Est](https://cnaveneto.it/cambiamenti-imprese-nord-est/) ha permesso di seguire **20 link nominativi a siti distinti**, senza ricercare domini inventati o dipendere dal motore bloccato. La notizia di marzo è datata: viene usata come elenco di identità, non come prova di bisogno attuale.

`scripts/pilot41_directory.py` ha letto le 20 pagine originali e approfondito tre candidati preliminari. Prima esecuzione: circa 150 secondi, 11 identità riconosciute dai controlli deterministici, 7 passaggi preliminari a promettente, **0 qualificati**. I sette non sono sette occasioni di vendita: indicano solo passaggi alla fase successiva. Tre verifiche approfondite sono rimaste incomplete.

La revisione ha individuato errori ulteriori: data di creazione della homepage usata come data dell'evento, slogan al posto della ragione sociale di ELSA S.r.l., recapiti privacy impropri e necessità di circoscrivere il contesto degli articoli multi-azienda. Correzioni coperte da test e ripetute sul medesimo campione. Ripetizione finale: 20 siti, 11 identità riconosciute; 7 scartati, 3 non verificabili, 3 da approfondire, 7 ancora promettenti, zero qualificati. Dei tre controlli approfonditi, ELSA S.r.l. termina l’analisi senza superare i requisiti; Behavix e DICEtech restano non verificabili. Il tempo automatico totale registrato è circa 130 secondi. Risultati finali dettagliati e revisione in [pilot41-review.json](pilot41-review.json); questa ripetizione non aggiunge nuove aziende al campione.

### Cosa impedisce la qualifica

- Behavix: nel campione mancano elementi d'identità/località e canale sufficienti; una pagina collegata restituisce 404. Un'offerta SaaS non dimostra una richiesta di sviluppo.
- Ciao Elsa / ELSA S.r.l.: servizi e prenotazioni già presenti; contatti raccolti inizialmente dalla privacy. Nessun bisogno di progetto completo verificato.
- DICEtech: identità/località insufficientemente documentate nelle pagine esaminate e ambito medicale che richiede una fattibilità specifica; non una web app semplice dedotta dal settore.
- Alcune imprese dell'elenco Nord-Est sono fuori Veneto, filtro scelto per il campione; non vengono attribuite al Veneto perché presenti nella directory.
- Gli altri casi non approfonditi rimangono preliminari. Cataloghi, prodotti innovativi, premi e startup non dimostrano un bisogno digitale irrisolto.

Non è stato individuato un caso documentato di commessa compatibile erroneamente scartata e poi confermata. Ciò **non misura il tasso di falsi negativi**. Il campione non fornisce una verità di riferimento completa sul mercato.

## Riproduzione

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/verify_migration41.py
.venv/bin/python scripts/check_visual_quality.py
.venv/bin/python scripts/check_funnel_ui.py
.venv/bin/python scripts/smoke_worker41.py
.venv/bin/python scripts/pilot41.py --database data/mio-pilota/pilot.sqlite3
.venv/bin/python scripts/pilot41.py --phase qualify --database data/mio-pilota/pilot.sqlite3
.venv/bin/python scripts/pilot41_directory.py --database data/mio-pilota-directory/pilot.sqlite3
```

Il pilota usa campioni proporzionati (una query per strategia, fino a tre URL per strategia, fino a tre verifiche approfondite della directory). Sono limiti del protocollo di collaudo, **non limiti dell'app**. La ricerca normale continua fino a 50 qualificati, Stop, impedimento tecnico o copertura disponibile terminata.

## Validazione commerciale ancora necessaria

Zero qualificati: precisione della shortlist non calcolabile, criterio 90% su 20 qualificati non verificato. Nessuna risposta, conversazione o conversione inventata. Serve un campione più ampio, fonti accessibili e gli esiti dei contatti reali. Il [programma di 30 giorni](ESPERIMENTO-30-GIORNI.md) è pronto nell'app attraverso metriche e feedback, ma l'esperimento di acquisizione deve ancora essere svolto dall'utente.

## Correzione del pulsante Cerca clienti

Il collegamento dalle viste dei contatti richiamava una funzione che navigava alla ricerca e spostava il focus senza creare una campagna. Ora usa la stessa azione del pulsante principale: avvia in assenza di una campagna, riprende quella sospesa e mostra l’avanzamento se è già attiva. Il comando Nuova ricerca rimane disponibile esplicitamente. Un messaggio immediato segnala avvio, ripresa e arresto; richieste ripetute durante l’attesa vengono ignorate e gli errori restano visibili con possibilità di riprovare.

Verifica dedicata: `.venv/bin/python scripts/check_search_button.py`, Chrome a 390 e 1440 px, API reale su database temporaneo e lancio worker sostituito solo nel test UI. Controllati creazione persistente, errore e successivo tentativo, doppi clic, campagna già attiva, Stop/Riprendi senza duplicazioni e preferenze della nuova ricerca. Il test separato `scripts/smoke_worker41.py` verifica il processo reale, sempre su database temporaneo. Nessun risultato di prova inserito nell’app dell’utente.
