# CustomerSearch — pulizia verificata

Data: 20 ottobre 2026. Inventario iniziale, stato Git, dipendenze dinamiche, baseline e backup verificato precedono le rimozioni.

## Operazioni eseguite

- **81 esportazioni storiche archiviate**, circa 24,86 MB di originali.
- **138 file temporanei rimossi**: bytecode Python e metadati Finder fuori da ambienti e dati.
- **557 membri dell'archivio verificati** contro il manifest interno.
- Ultime cinque campagne accessibili in `reports/recent/README.md`: **43, 42, 41, 40, 39**. La 42 è sospesa e non dispone di report finale: non ne è stato inventato uno.
- `.gitignore` aggiornato per cache, coverage, output Playwright e profiler.
- Test e fixture permanenti conservati. Nessun `git clean`, reset, commit o push.

Inventari e numeri esatti prima/dopo sono nel `CUSTOMERSEARCH-CLEANUP-MANIFEST.json`, sezione `inventory_summary`, con una decisione motivata per ciascun percorso. Il conteggio iniziale è **5.076 elementi**, di cui 15 link simbolici non attraversati, per **31.809.021.160 byte** censiti.

Snapshot finale: **4.913 elementi**; escludendo dati, backup, Git e ambienti, **954 → 787**. I due file auto-generati dell'inventario finale/manifest sono esclusi dal proprio snapshot per evitare checksum autoreferenziali. Gli originali eliminati definitivamente occupavano **2.257.335 byte**; quelli archiviati **24.864.091 byte**.

Il confronto dello spazio totale comprende il nuovo backup privato: non rappresenta soltanto il sorgente e può aumentare nonostante le rimozioni. Non sono stati cancellati gigabyte di backup, database o ambienti sulla base del nome della cartella. I byte archiviati sono recuperabili, non distrutti.

## Backup, archivio e ripristino

Backup privato verificato:

`data/backups/20261020T131251465523Z`

La verifica ha ripristinato su copie temporanee **1.468 file e due database**, controllando hash, integrità e conteggi. Il backup contiene anche configurazioni riservate: resta privato e non va condiviso come report.

Archivio delle analisi:

`archives/customersearch-analysis-archive.zip`

SHA-256:

`1df936dbd747cecd421ad4a711b720eefafd1489283444bcb37d39ca22daf24d`

Si è riutilizzato il formato del manifest e il lettore `scripts.analysis_archive`. Prima di rimuovere gli originali sono stati verificati tutti i membri ZIP. Il manifest di pulizia associa percorso originale, azione, motivo e archivio. Nessuna `.env`, chiave API, cookie o copia del database operativo è stata aggiunta allo ZIP delle analisi.

La lettura di un vecchio report tramite `scripts.analysis_archive.read_text(percorso)` verifica il contenuto archiviato. Per un ripristino del codice usare il backup verificato su una copia; non sovrascrivere automaticamente il database corrente e il CRM.

## Consolidamento e riduzione delle sovrapposizioni

| Area | Intervento |
|---|---|
| Canonical/HTML | Rimosso il parser duplicato in `website_audit`; usa `extract.Document` |
| Struttura JSON | Estratto e condiviso `schema.shape` invece di replicare il validator |
| Giudizio commerciale nuovo | Un contratto AI e una sola materializzazione in `decision.py` |
| Qualificazione/scoring/proiezione | Il ramo AI-first evita le successive reinterpretazioni commerciali legacy |
| Acquisizione e orchestrazione | Riutilizzati HTTP, browser, coda, scheduler, ledger e memoria esistenti |
| Report storici nei test | Due letture obsolete passano dal lettore ZIP verificato |

Tre moduli nuovi separano prove, decisione ed esecuzione dentro il package già esistente. Non sono stati aggiunti microservizi, classi astratte o un secondo coordinatore.

Non si dichiara eliminato tutto il codice storico. `qualification`, `completion`, `requirements`, `semantics`, `commercial_roles`, `commercial_score` e i percorsi precedenti restano **isolati dal nuovo percorso decisionale** e servono ancora a replay, compatibilità e ripresa delle campagne vecchie. Parti di questi moduli espongono anche estrattori condivisi: eliminare un file intero romperebbe chiamanti attivi.

Condizione di rimozione: validazione semantica del nuovo motore, compatibilità/rollback verificati e decisione esplicita sulle funzionalità storiche ancora utilizzabili. Non basta l'assenza di import statici.

## Elementi conservati e motivazione

- Database, evidenze, CRM, revisioni, memoria, configurazioni e credenziali: dati operativi.
- Backup: rollback ancora necessario; il modello nuovo non ha una prova commerciale indipendente.
- `.venv`, `.runtime`, dipendenze browser: componenti dell'avvio e del collaudo.
- Fixture e test: regressioni permanenti, anche quando descrivono vecchie campagne.
- Script CLI e artefatti storici ancora referenziati: non rimossi per evitare rotture operative; motivazione per percorso nel manifest.
- Modifiche locali pregresse e file non tracciati: non equiparati a file superflui.
- Un bytecode cambiato durante i controlli era inizialmente conservato; verificato che fosse cache rigenerata, è stato rimosso registrando anche il nuovo hash.

## Integrità e sicurezza

Controllo finale in sola lettura rispetto al backup iniziale:

- `sales.sqlite3`: `integrity_check=ok`, nessuna violazione FK, tutte le tabelle identiche.
- `customers.sqlite3`: `integrity_check=ok`, nessuna violazione FK, tutte le tabelle identiche.

La comparazione comprende righe e digest del contenuto di ogni tabella, non soltanto conteggi. Nessuna campagna storica, stato, budget, configurazione, CRM o memoria è stata alterata.

SQL parametrizzato, escaping UI, controlli Host/Origin/CSRF, client HTTP protetto, SSRF/redirect, robots, TLS, PDF, cancellazione e ledger vengono riutilizzati. I nuovi link AI sono solo proposte: l'acquisizione li rivalida. Nessuna protezione è stata disabilitata per ridurre la complessità.

Suite completa: **1.943 test OK**; ultime integrazioni: **91 OK**; hardening finale: **120 OK**. UI verificata offline a 1440 e 390 px. Log e limiti del benchmark sono descritti nel report di implementazione.

## Inventari verificabili

- `implementation-report/ai-first/inventory-before.json`
- `implementation-report/ai-first/inventory-after.json`
- `implementation-report/ai-first/git-status-before.txt`
- `implementation-report/ai-first/dynamic-entrypoints.txt`
- `implementation-report/ai-first/cleanup-actions.json`
- `implementation-report/ai-first/integrity-after.json`
- `CUSTOMERSEARCH-CLEANUP-MANIFEST.json`

La pulizia riguarda rimozioni dimostrate e un solo percorso decisionale nuovo. La validazione commerciale reale e il successivo ritiro del rollback restano attività esplicitamente aperte; non sono simulate da una suite verde.
