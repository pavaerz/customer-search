# Pulizia del progetto — 15 ottobre 2026

Pulizia richiesta dall'utente dopo la diagnosi in sola lettura. I report in `analysis-report/` descrivono la situazione **prima** della pulizia e non sono stati riscritti. I percorsi degli artefatti eliminati non sono più disponibili.

## Spazio recuperato

| Area | Prima | Dopo | Recuperato netto |
| --- | ---: | ---: | ---: |
| data | 11,646 GB | 2,901 GB | 8,745 GB |
| Runtime e modelli locali | 8,561 GB | 5,237 GB | 3,324 GB |

Unità decimali, somma delle dimensioni logiche dei file. Circa **12,07 GB netti** complessivi, più circa 2 MB di bytecode e metadati fuori da queste aree. Non è una misurazione dei blocchi fisici APFS o dello spazio trattenuto dagli snapshot del sistema.

373 file eliminati mediante un elenco esplicito, verificando percorso, dimensione, modifica e inode prima della cancellazione. Nessuna cancellazione ricorsiva indiscriminata.

## Eliminato

- Backup intermedi superati, per circa 7,20 GB. Sostituiti da un backup attuale compresso e verificato; mantenute cinque basi storiche usate dagli script.
- Copie SQLite di esperimenti e piloti concluse, per circa 1,66 GB. I report e le pagine catturate restano disponibili. Quegli esperimenti eliminati non sono più riprendibili dal loro vecchio database.
- Vecchio snapshot isolato precedente alla revisione.
- Modello sperimentale `qwen3.5:4b-q4_K_M` e soltanto i suoi componenti esclusivi, circa 3,32 GB. Non era il modello configurato nell'app e non risultava caricato. I risultati dei confronti sono conservati; per ripeterli con questo modello occorre reinstallarlo esplicitamente.
- Bytecode Python rigenerabile e metadati Finder.

## Conservato e perché

- `data/sales.sqlite3` e `data/customers.sqlite3`: dati, storico, prove, cache operative, impostazioni, esiti e soppressioni. Nessuna riga cancellata, nessun VACUUM o migrazione.
- Credenziali e configurazioni, incluso il file Serper. Verificati tramite hash senza mostrarne il contenuto.
- Codice, test, script, documentazione, report di analisi, audit Lighthouse, screenshot e pagine originali utili alla diagnosi.
- Ambiente Python e runtime Ollama; modello attivo `qwen2.5:7b`, circa 4,68 GB, necessario all'analisi locale.
- Cinque backup storici richiesti da `verify_migration4.py`, `verify_migration41.py`, `benchmark_discovery.py`, `benchmark50_roles.py` e `check_direct_demand.py`. Non sono copie usate dall'app quotidianamente: servono a confrontare il comportamento e verificare migrazioni storiche.
- Nove database sperimentali richiamati dai replay su aziende, identità, prove e trial. Rimuoverli senza adattare gli script renderebbe quei controlli non riproducibili. Elenco nel manifest della pulizia.

## Backup attuale

`data/backups/cleanup-20261015T090037Z/restore.zip` — circa 116 MB.

Contiene snapshot coerenti dei due database operativi, codice, configurazioni e credenziali. **Archivio privato: non condividerlo o pubblicarlo.** Directory con permessi 0700, archivio e manifest 0600. Runtime scaricabili, vecchi backup e database sperimentali eliminati non sono contenuti in questo archivio.

Verificati CRC e SHA-256 dei membri; entrambi i database estratti in una directory temporanea e controllati con `PRAGMA integrity_check`. Il ripristino di prova è terminato correttamente. I database reali non sono stati sostituiti.

Per ripristinare in futuro: fermare app e worker, verificare l'archivio rispetto al manifest, estrarlo prima in una cartella separata e ripristinare solo i file necessari. I percorsi nell'archivio sono relativi alla radice del progetto, compresi `data/sales.sqlite3` e `data/customers.sqlite3`. Non sovrascrivere database in uso e non copiare vecchi WAL/SHM sopra uno snapshot.

## Verifiche finali

- SHA-256 dei database operativi e delle credenziali protette invariati.
- Integrità SQLite: `ok` per entrambi.
- Conservati 7 campagne, 1.379 candidati e 177 assessment.
- 112 file Python inventariati: hash invariati rispetto all'audit.
- Manifest e componenti del modello attivo completi, dimensioni corrette.
- Nessuna ricerca avviata, richiesta esterna, consumo di crediti o invio email.

Nessun test applicativo completo eseguito: il codice non è stato modificato. Le verifiche hanno riguardato integrità, conservazione dei dati, ripristino e dipendenze rimaste. La pulizia non corregge i difetti del motore documentati nell'analisi.

[Manifest della pulizia](cleanup-20261015T090037Z.json) — file eliminati, motivazioni, dimensioni, elementi conservati e controlli.

Non è stata introdotta una cancellazione automatica futura dei backup: il comando esistente continua a creare copie. I suoi effetti su disco restano espliciti.
