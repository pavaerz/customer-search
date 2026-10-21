# CustomerSearch 9.2.2 — pulizia e hardening

Data: 20 ottobre 2026. Intervento completato sui sorgenti locali, con verifiche offline. Nessuna campagna avviata, nessuna chiamata Serper/OpenAI, nessun invio, nessun aumento di budget, nessun commit o push.

La 9.2.1 risultava completata e documentata prima dell'intervento. Il backend e il worker della Campagna 42 erano già attivi: sono rimasti intatti. Le modifiche verranno caricate al successivo riavvio esplicito. Il collaudo del nuovo backend è stato eseguito su una copia temporanea, senza chiavi e senza dati operativi.

## Risultato concreto

- **476 documenti** raccolti in uno ZIP verificato; **475 copie storiche** rimosse dai percorsi attivi. Il vecchio README è conservato nello ZIP e sostituito da istruzioni correnti.
- **Sei file sanificati** nell'archivio, compresi token di pianificazione/approvazione. Gli originali esatti restano nel backup privato.
- **312 file di cache rigenerabili** rimossi dopo backup e verifica; nessun test o fixture permanente eliminato.
- **Sei directory di rollback**, circa **1,8 GB**, spostate sotto `data/backups/legacy/`, con hash verificati prima e dopo. Sono conservate, non spazio liberato dal disco.
- Report storici attivi rimossi: 34.476.938 byte; cache rimosse: 4.909.508 byte. ZIP storico: 4.680.869 byte. Questi numeri non rappresentano il risparmio netto del disco: i backup di sicurezza restano presenti.
- README, ARCHITECTURE, SECURITY e OPERATIONS ora descrivono una sola versione corrente. `.env.example` non suggerisce più credenziali OAuth/Tavily o SearXNG come configurazione primaria.

## Precondizioni, inventario e conservazione

Database iniziale: `PRAGMA integrity_check = ok`. Non sono stati rilevati processi di test/sviluppo attivi al controllo iniziale; erano presenti backend e worker operativi. Gli hash dei sorgenti esistenti non mostrano modifiche concorrenti inattese durante il lavoro. Il contenuto non salvato negli editor non è ispezionabile da questi controlli: non è stato considerato né sovrascritto deliberatamente.

L'inventario iniziale comprende **6.252 elementi**, inclusi file e directory. Classificazione iniziale automatica, poi verifica dei candidati alla rimozione:

| Categoria | Elementi iniziali |
|---|---:|
| A — codice attivo | 301 |
| B — test permanenti | 235 |
| C — configurazione, ambienti e metadati Git | 3.790 |
| D — documentazione | 31 |
| E — dati operativi | 715 |
| F — report e metriche | 435 |
| G — temporanei/cache | 405 |
| H — archivio di codice storico | 22 |
| I — duplicati dimostrati rimovibili | 0 |
| J — segreti e backup privati | 150 |
| K — da classificare/verificare | 168 |

Questi conteggi non sono un giudizio di eliminabilità. I moduli `site_audit.py` e `technical_audit.py`, inizialmente incerti per posizione, sono confermati necessari e classificati attivi nell'inventario finale. Non sono emersi duplicati identici fra i file Python esaminati. Snapshot iniziale e finale:

- [Inventario iniziale privato](data/backups/customersearch922-preflight/inventory-before.json)
- [Inventario finale](implementation-report/customersearch922/inventory-after.json)
- [Dimensioni e moduli maggiori](implementation-report/customersearch922/architecture-inventory.json)
- [Manifest delle operazioni](CLEANUP-MANIFEST.json)

Sono conservati database, prove originali, CRM, memoria, migrazioni, test, fixture, runtime, configurazioni e backup. **114 riferimenti a file storici da script** sono stati conservati per non rompere replay e strumenti operativi; sono elencati nel manifest. Restano anche elementi incerti, codice storico già separato in `archive/`, runtime locale e backup precedenti: la loro inutilità non è dimostrata. Non viene dedotta dal solo fatto che non compaiano in un import.

## Ultime cinque campagne

Le ultime cinque campagne con task effettivamente registrati sono **42, 41, 40, 39, 38**, ordinate per ID e data reale. L'indice è [reports/recent/README.md](reports/recent/README.md).

I report/metriche 38–41 restano consultabili dalla radice; le configurazioni sanificate e i riferimenti agli ID delle prove si trovano nell'indice. La 42 risultava `running` alla fotografia: non è stato inventato un report finale. Le campagne precedenti sono nello ZIP. Report di implementazione, replay e simulazioni hanno categorie distinte nel manifest interno e non sono contati come campagne reali.

## Archivio e rollback verificati

Archivio: [customersearch-analysis-archive.zip](archives/customersearch-analysis-archive.zip).

SHA-256: `d458b6af149ad0d77e735b38a2604a3e47ddc6c716e9bfd9ea94ce68642d1936`.

Verificati CRC, estrazione in directory temporanea, elenco dei membri e hash di ogni file rispetto ad `ARCHIVE-MANIFEST.json`. Gli originali sono stati rimossi dai percorsi attivi solo dopo questa verifica e un nuovo confronto dell'hash. ZIP e report privati sono esclusi da Git; nessun `.env`, database o backup è incluso nell'archivio storico.

Backup iniziale: `data/backups/customersearch922-preflight/`, con **1.238 file** in `originals.zip`, manifest, inventario, stato Git e snapshot `sales.sqlite3`. La copia SQLite è stata ripristinata nuovamente in una directory temporanea: integrità `ok`. Le cache hanno un rollback separato `removed-caches.zip`. I rollback spostati sono descritti per file e hash nel manifest. Le istruzioni di ripristino selettivo sono in [OPERATIONS.md](OPERATIONS.md).

## Correzioni implementate

### Avvio senza effetti sul processo esistente

Prima, `sales/server.py` inizializzava/migrava SQLite, recuperava campagne e fermava gestori prima di tentare il bind HTTP. Un secondo avvio poteva quindi modificare lo stato e solo dopo fallire con “Address already in use”. Ora acquisisce prima il listener di loopback. Porta occupata: messaggio comprensibile ed uscita prima dell'inizializzazione. Errore durante l'inizializzazione: listener chiuso. La logica è separata in `initialize_runtime`, senza riscrivere routing o coordinatore.

### Backup coerente e memoria limitata

Prima, dopo una copia SQLite venivano confrontati i conteggi con il database vivo, che poteva già essere cambiato da un worker; inoltre database e file venivano letti interamente in memoria. Ora:

- sorgente SQLite aperta in sola lettura e conteggi riferiti allo snapshot verificato;
- hash/compressione a blocchi di 1 MiB, senza caricare l'intero database;
- ambienti e backup annidati esclusi durante la visita delle directory;
- file privati creati direttamente con permessi 0600, directory 0700;
- link simbolici ignorati; database operativo che è un symlink rifiutato;
- `verify_backup` prova estrazione e ripristino SQLite su copie temporanee, controllando manifest, hash, percorsi e conteggi.

### Isolamento dei test e compatibilità degli script

Il guardiano offline ora vive in `tests/offline_guard/sitecustomize.py`, non soltanto in una directory di output ignorata. Il vecchio percorso locale delega a quello permanente. Il controllo SQLite riconosce il percorso reale anche se la cartella del progetto cambia nome.

`scripts/analysis_archive.py` permette agli script di report storici dipendenti dalle campagne 23/29/30 di leggere il contenuto archiviato con verifica del checksum. Sono stati aggiornati i lettori, senza estrarre automaticamente report vecchi nella radice.

## Architettura, logica commerciale e sicurezza

L'analisi statica comprende **172 moduli backend**: nessun ciclo negli import di primo livello rilevati. Il controllo non copre ogni dipendenza dinamica o import ritardato. I moduli maggiori restano `research_analysis.py`, `agent6/coordinator.py` e `commercial/browser.py`: nessuna riscrittura generale o cancellazione di compatibilità senza beneficio dimostrato.

Le regole 9.2.1 sono preservate: email aziendale pubblica con attribuzione, qualifica distinta dal contatto, stack opzionale per agenzie, cofounder/equity separati dalle commesse, rifacimenti motivati da prove, niente budget o richieste inventati, errori crawler distinti da difetti del sito. I cinque flussi restano AZIENDE, AGENCIES, SOCIAL, STARTUPS e NEWS.

Controllati codice e regressioni su Host/Origin/CSRF, escaping, limiti input, SQL parametrizzato, TLS, SSRF/redirect, proxy browser, PDF, timeout, attribuzione AI, budget, Stop/Riprendi e memoria. Nessuna protezione disabilitata. `.env` è rimasto 0600 e byte per byte invariato.

La ricerca delle chiavi effettivamente configurate non ha trovato corrispondenze nel codice, nei testi controllati, nei report radice, nello ZIP o nelle **34 fixture compresse**. Nessun valore è stato stampato. Nessun `.env`, database, ambiente o runtime operativo risulta tracciato. Il controllo non certifica l'assenza di qualunque segreto sconosciuto nei dati originali privati.

Gli script storici che eseguono codice da backup sono conservati e segnalati: vanno usati solo su backup attendibili. Non sono chiamati dall'API applicativa. L'app resta locale e mono-operatore, senza autenticazione multiutente: non va pubblicata su Internet. Dettagli e limiti in [SECURITY.md](SECURITY.md).

## Test e verifiche

| Verifica | Esito |
|---|---|
| Suite completa `unittest discover -s tests -v` | **1.904 test passati**, 438,066 s |
| Verifiche finali hardening, HTTP e lifecycle | **32 test passati**; sovrapposizione con suite, non sommare |
| UI reale Chromium | 1440 e 390 px, zero errori JS e overflow |
| Osservazioni design browser | 390 e 1366 px, prove tipizzate, nessun rifacimento automatico |
| Cinque flussi isolati e combinati | Tutti pianificano/verificano; combinata 31 chiamate simulate entro 100 / 2 USD configurati |
| Copia pulita dei sorgenti, nuovo SQLite, entry point `app.py` | Avvio, pagina, state/worklist, Host/CSRF e arresto regolare verificati |
| SQLite operativo e copia di ripristino | Integrità `ok` |
| Preservazione | **20 tabelle/porzioni di tabelle identiche** al backup iniziale; storico fino alla 41, CRM e impostazioni inclusi |
| Dipendenze installate | `pip check`: nessuna incompatibilità |
| Archivio | CRC, estrazione e hash per file verificati |
| Git diff | Nessun errore di whitespace; nessun commit/push |

La simulazione usa aziende e risposte sintetiche: **zero opportunità reali** prodotte da questo collaudo. I 31 utilizzi simulati non sono chiamate a pagamento. Il primo collaudo di installazione era incompleto perché non copiava i moduli audit nella radice; è stato corretto il collaudo e ripetuto con successo.

Evidenze: [suite completa](implementation-report/customersearch922/full-tests.log), [test finali](implementation-report/customersearch922/final-targeted.log), [UI](implementation-report/customersearch922/ui.json), [cinque flussi](implementation-report/customersearch922/five-flows.json), [avvio pulito](implementation-report/customersearch922/fresh-install.json), [preservazione database](implementation-report/customersearch922/database-preservation.json).

## Limiti e questioni aperte

- La Campagna 42 era già avviata: nessuna interruzione o rivalutazione, nessuna certificazione dei suoi risultati con la 9.2.2.
- La nuova installazione è stata verificata come copia sorgente senza `.env`/database, usando le dipendenze Python già installate. Download/installazione da PyPI in un ambiente privo di dipendenze non verificati in questo collaudo offline.
- Non sono disponibili `pip-audit`/`safety` e una base CVE locale aggiornata: nessuna dichiarazione di assenza di vulnerabilità.
- L'archiviazione riduce il disordine del progetto attivo; runtime, prove e backup privati continuano a occupare spazio. Non eliminati per raggiungere un numero arbitrario di GB.
- Diversi moduli e script storici restano necessari o di utilità incerta; i loro input non sono stati cancellati indiscriminatamente.
- Il repository era già ampiamente modificato e con codice importante non tracciato, incluse parti del motore. Tutto è preservato. Un clone remoto non rappresenta necessariamente questi sorgenti finché non viene effettuata una pubblicazione deliberata, esclusa da questa richiesta.
- Disponibilità dei provider, qualità commerciale delle future ricerche e conversioni restano da misurare sul campo. Non vengono dedotte dai test offline.

## Struttura finale

`app.py` e i moduli audit nella radice; backend in `sales/`; frontend in `static/`; regressioni in `tests/`; strumenti in `scripts/`; quattro documenti correnti nella radice; ultimi report campagna nella radice con indice in `reports/recent/`; storico sanificato in `archives/`; collaudi in `implementation-report/customersearch922/`; dati e rollback privati in `data/`.

L'elenco completo delle operazioni, dei file preservati per dipendenza e dei percorsi di rollback è in [CLEANUP-MANIFEST.json](CLEANUP-MANIFEST.json).
