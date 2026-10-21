# CustomerSearch 9.2.1 — Commercial Qualification Alignment

Data: 20 ottobre 2026. Implementazione e verifiche offline completate.

La qualifica commerciale è ora distinta dalla disponibilità del contatto. Le agenzie non devono dichiarare uno stack coincidente; le proposte da cofounder ed equity-only sono separate dalle commesse remunerate. Il percorso proattivo può valutare un nuovo sito completo anche in assenza di errori tecnici, sulla base di osservazioni specifiche di contenuti e UX.

**652 test automatici superati, zero fallimenti nella suite finale. Nessuna chiamata reale Serper/OpenAI, nessun invio, nessuna modifica dei budget e nessuna campagna avviata da questa implementazione.**

**Attività concorrente rilevata:** durante il lavoro è comparsa la Campagna 42, creata alle 09:34:40 del 20 ottobre (Europe/Rome), successivamente rilevata in esecuzione. Non è stata avviata, interrotta o modificata dai comandi di questo intervento. L’origine non è determinabile dai soli dati letti. Non viene presentata come collaudo della 9.2.1: nei suoi filtri non risulta un `runtime_version`. I suoi eventuali consumi non fanno parte dei test offline.

## Regole precedenti e nuove

| Aspetto | Prima | Ora |
|---|---|---|
| Qualifica e contatto | Un contatto assente poteva impedire la qualifica | Requisiti separati: `OPPORTUNITY_QUALIFIED`, `CONTACT_AVAILABLE`, `READY_FOR_OUTREACH` |
| Email generica | Il canale non aveva una dimensione autonoma coerente nella Worklist | `info@`, `hello@`, `commerciale@`, `office@` e `contatti@` sono validi con provenienza pubblica attribuita |
| Provenienza del contatto | Contatti nell’identità | Canale ammesso solo con identità e originale verificati, URL pubblico del soggetto oppure prova originale di attribuzione |
| Contatto assente | Poteva nascondere una pista interessante | Qualifica conservata; contatto segnalato come mancante; scheda esclusa da “Da contattare” |
| Agenzia senza stack | `technical` era obbligatorio | Stack opzionale, usato per affinità e ordinamento |
| Agenzia con tecnologie diverse | Rischio di blocco per mancata compatibilità puntuale | `POSSIBLE_AFFINITY` o `UNKNOWN_AFFINITY`; nessuna whitelist rigida |
| Invito generico | Poteva ereditare requisiti di progetto | Collaborazione riconoscibile; termini, incarichi, compenso e volumi non presunti |
| Progetto specifico di un’agenzia | Doveva avere perimetro chiarito | Requisito preservato: non si applica l’eccezione degli inviti generici |
| Cofounder / equity-only | Esclusione o blocco legato alla remunerazione | Opportunità imprenditoriale distinta; mai valore economico dell’equity o fatturato potenziale |
| Rifacimento | Rilievi tecnici e verifica dei sistemi esterni potevano diventare prerequisiti | Contenuti/UX documentati ammessi; sistemi esistenti sono contesto, non requisito obbligatorio |
| Piccole correzioni | Non sufficienti per un progetto completo | Protezione conservata |

Le tre dimensioni indipendenti sono `COMMERCIAL_INTEREST`, `EVIDENCE_CONFIDENCE` e `CONTACT_READINESS`. Non esprimono probabilità di vendita.

### Richieste e collaborazioni

Una richiesta verificata può restare `VERIFIED` senza email. La vista “Da contattare” richiede sia qualifica sia canale pubblico verificato; le viste “Verificate”, “Potenziali” e “Tutte” conservano le opportunità senza contatto.

Non si generano indirizzi. Un URL di provenienza mancante o attribuito a un altro soggetto non basta. Un indirizzo su un dominio email diverso può essere valido se pubblicato sul sito ufficiale: conta la fonte, non una corrispondenza inventata tra dominio aziendale e casella.

Per un invito generico di una web agency verificata, “collaboratori” può indicare interesse da approfondire senza dedurre un rapporto freelance già concordato. La mancanza dei termini rimane esplicita. Le richieste esclusivamente dipendenti, le attività chiaramente estranee e gli inviti chiusi restano esclusi.

Competenze di riferimento: HTML, PHP, SCSS, CSS, JavaScript, jQuery, React, Next.js, WordPress, WooCommerce, e-commerce, frontend, web app e MVP. PHP e jQuery sono riconosciuti anche nella validazione delle prove tecniche. I livelli di affinità sono `HIGH_AFFINITY`, `POSSIBLE_AFFINITY`, `UNKNOWN_AFFINITY` e `CLEARLY_UNRELATED`.

L’assenza di uno stack non certifica la compatibilità tecnica: evita soltanto un’esclusione ingiustificata. La data e l’attualità dell’invito restano verifiche distinte. Nessuna disponibilità di incarichi viene dedotta da una pagina “Lavora con noi”.

### Rifacimenti completi e qualità del sito

Il nuovo audit mantiene separati:

- `OBSERVED_TECHNICAL_ISSUE`: difetti misurati;
- `OBSERVED_UX_ISSUE`: rilievi specifici sui percorsi o sulla fruizione;
- `CONTENT_ASSESSMENT`: interpretazione motivata della struttura dei contenuti;
- `DESIGN_ASSESSMENT`: valutazione circoscritta della gerarchia tipografica renderizzata;
- `COMMERCIAL_HYPOTHESIS`: proposta commerciale da discutere, non domanda dichiarata.

Sono implementati due nuovi controlli di contenuto/navigazione: presentazioni estese dell’offerta senza suddivisione in sezioni e almeno quattro collegamenti con identica etichetta generica verso destinazioni diverse. Le prove conservano URL, data, hash del documento, estratti o destinazioni osservate. I limiti sono dichiarati: etichette lette isolatamente e struttura dell’HTML acquisito, non giudizi sull’intero sito.

Il browser misura inoltre dimensione, peso e colore di un campione di titoli e paragrafi visibili. Solo un rendering completato può produrre la valutazione di gerarchia tipografica. La somiglianza degli stili non dimostra illeggibilità: spaziatura e altri segnali visivi rimangono da valutare. Questo rilievo moderato non qualifica da solo un rifacimento.

La valutazione commerciale richiede ancora prove su più pagine e dimensioni, attività aziendale documentata e spiegazione del perché una piccola correzione non basti. Identità, territorio, browser completo nel percorso proattivo, homepage acquisita e controlli di sicurezza restano applicati. Il modello seleziona soltanto ID di osservazioni e fatti disponibili.

Il controllo obbligatorio di uno shop esterno è rimosso anche dal percorso notizie. Un sistema non consultato resta sconosciuto: non si può dichiarare assente o inadeguato. Una notizia richiede comunque evento attuale e collegamento documentato tra evento e proposta.

**Limite:** non è stata implementata una valutazione estetica generale tramite modello visivo. Attualità dello stile, qualità artistica e coerenza del marchio non vengono dedotte automaticamente. Le valutazioni nuove sono circoscritte a quanto effettivamente osservato.

### Startup

Tipi distinti: `PAID_DEVELOPMENT_OPPORTUNITY`, `FREELANCE_COLLABORATION`, `TECHNICAL_COFOUNDER_OPPORTUNITY`, `EQUITY_ONLY_OPPORTUNITY`, `UNCLEAR_ARRANGEMENT`.

Le proposte imprenditoriali hanno categoria e filtro dedicati nella Worklist. Eventuali importi citati vicino a una proposta equity-only sono conservati come dichiarazioni, senza diventare budget di una commessa o valore dell’equity. Condizioni economiche contraddittorie restano da chiarire. Un lavoro gratuito senza ruolo imprenditoriale non viene trasformato in opportunità remunerata.

Il dossier espone idea, problema, prodotto, fase, founder, modello di business, utenti/clienti, investimenti e impegno quando presenti nelle prove originali selezionate e con etichette esplicite. Altrimenti mostra `UNKNOWN`. L’estrazione di queste voci è conservativa e può non riconoscere formulazioni libere: gli estratti originali restano disponibili. Per un progetto web app effettivamente definito, requisiti critici sconosciuti su sicurezza, integrazioni e manutenzione continuano a impedire la qualifica.

## File modificati

Elenco verificato tramite hash rispetto al backup di inizio intervento: [CHANGES.json](implementation-report/customersearch921/CHANGES.json).

| Area | File |
|---|---|
| Nuove dimensioni e audit | `sales/agent6/alignment.py`, `qualitative_audit.py` — nuovi |
| Qualifica e dossier | `sales/agent6/qualification.py`, `requirements.py`, `commercial_roles.py`, `completion.py` |
| Ricerca e interpretazione | `sales/agent6/strategies.py`, `commercial_policy.py`, `schema.py`, `proactive.py`, `website_review.py`, `news_review.py`, `website_audit.py` |
| Worklist e priorità | `sales/agent6/commercial_view.py`, `commercial_score.py`, `worklist.py`, `static/worklist.js` |
| Misure e competenze | `sales/commercial/browser.py`, `sales/commercial/demand.py` |
| Versione e documentazione | `sales/agent6/__init__.py`, `README.md`, questo report |
| Test e replay | `tests/test_agent921.py` — nuovo; aggiornati `test_agent92.py`, `test_agent8_startups.py`, `test_agent8_proactive.py`, `test_agent7_lifecycle.py`; `scripts/replay_agent92.py` |
| Collaudo locale | `scripts/check_agent921_ux.py`, `scripts/check_agent921_design.py` — nuovi |

Nessuna modifica a schema SQLite, credenziali, impostazioni persistenti, budget o massimi delle campagne.

## Verifiche eseguite

| Suite finale | Esito |
|---|---:|
| `test_agent*.py`, inclusi 23 nuovi test 9.2.1 | 435/435 |
| Regressioni commerciali mirate | 203/203 |
| Protezioni/API HTTP | 14/14 |
| Totale automatico | **652/652** |
| Worklist/CRM desktop e mobile | Pass |
| Nuove dimensioni, contatto assente e filtro equity a 1440/390 px | Pass |
| Browser reale su pagine locali funzionanti, overflow e timeout | Pass |
| Stili tipografici reali a 390/1366 px | Pass |
| Sintassi JavaScript | Pass |

Log e risultati: [cartella verifiche](implementation-report/customersearch921/), [metriche](implementation-report/customersearch921/METRICS.json).

Durante lo sviluppo sono emerse aspettative obsolete nei test NHW, equity-only e shop esterno: sono state aggiornate alle regole richieste, preservando gli altri vincoli. È stata anche rilevata una regressione reale: l’eccezione per inviti generici rimuoveva il requisito di perimetro da una commessa specifica. Corretta e verificata dal test `test_named_project_cannot_discard_scope_as_standing_partnership`.

La revisione finale ha corretto la Worklist affinché prove scadute o contatti già gestiti non risultino pronti per un nuovo contatto e affinché una scheda qualificata non mostri il titolo “verifiche da completare”. Nessun messaggio viene inviato dai controlli CRM.

### Replay e flussi

Il replay usa gli originali e gli output AI salvati della Campagna 41, senza nuove inferenze. NHW mantiene identità verificata e canale pubblico; lo stack non è più obbligatorio. Resta `NEEDS_REVIEW` perché l’attualità dell’invito non è dimostrata. L’etichetta di menu “E-commerce & API” non viene trasformata in competenza richiesta. Punto Infissi mantiene la correzione dell’attribuzione dei gruppi della 9.2; non viene qualificata senza audit disponibile.

I cinque flussi `AZIENDE`, `AGENCIES`, `SOCIAL`, `STARTUPS`, `NEWS` sono stati eseguiti in simulazioni separate e combinate su database temporanei. La simulazione combinata completa tutti i flussi con 31 chiamate simulate entro i massimi della fixture, senza attività pendenti. Gli esiti positivi sintetici verificano il codice, **non sono opportunità reali**. Post social indicizzati restano distinti dagli originali; le notizie non diventano richieste di acquisto.

Riproduzione offline:

```bash
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B -m unittest discover -s tests -p 'test_agent*.py' -q
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B -m unittest test_commercial43 test_commercial41 test_commercial40 test_commercial42_live_regression test_commercial50 test_commercial_discovery3b4 test_commercial_reliability3b5 -q
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B -m unittest test_sales_http -q
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/replay_agent92.py
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/simulate_agent92.py
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/check_agent921_ux.py
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/check_agent921_design.py
```

Il guard dei test impedisce accessi al database di produzione e ai servizi esterni. Browser e test HTTP richiedono server locali e Chrome; usano database temporanei.

## Database e conservazione

Prima delle modifiche: archivio sorgenti verificato con `ZipFile.testzip`, manifest degli hash e conteggi delle 66 tabelle, `PRAGMA integrity_check = ok`, in `data/backups/customersearch921-preflight/`. Non sono necessarie migrazioni. Il backup SQLite completo verificato della 9.2 resta disponibile e non è stato sovrascritto.

Il primo confronto globale ha rilevato differenze dovute alla Campagna 42 concorrente. **Non sarebbe corretto dichiarare invariato l’intero database.** Il confronto successivo, in sola lettura e su snapshot SQLite, ha verificato:

- tutte le 17 tabelle con riferimenti diretti alle campagne, limitate alle campagne fino alla 41, identiche riga per riga al backup;
- dati CRM e feedback invariati;
- integrità SQLite `ok`;
- `.env` invariato;
- nuove righe e aggiornamenti nelle cache condivise associati all’attività concorrente, documentati senza cancellarli o ripristinarli.

Risultati completi: [PRESERVATION.json](implementation-report/customersearch921/PRESERVATION.json). Non sono stati effettuati commit o push.

## Stato operativo e limiti commerciali

La 9.2.1 è pronta nel codice e verificata offline. Il backend non è stato riavviato durante questo intervento, anche per non interferire con la ricerca concorrente. Un aggiornamento della pagina non carica il nuovo backend.

Una volta terminata e arrestata in sicurezza la ricerca in corso, il comando locale rimane:

```bash
.venv/bin/python app.py
```

Prima di avviarlo, deve essere terminato il precedente processo che occupa la porta. Le nuove campagne registreranno `runtime_version=9.2.1`; non usare una campagna storica o quella già in corso come prova controllata della nuova versione.

La richiesta di non avviare la Campagna 42 è stata rispettata dai comandi di questo intervento. La campagna rilevata indipendentemente non è stata usata per attribuire efficacia commerciale alle modifiche.

**Non sono stati misurati nuovi clienti, risposte, contratti o rendimento commerciale.** Il comportamento del modello su nuove fonti, la precisione delle valutazioni qualitative e il numero di opportunità realmente utili richiedono una futura prova autorizzata, seguita da revisione delle evidenze. Nessun aumento automatico dei budget è previsto.
