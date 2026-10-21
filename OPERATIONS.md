# Operazioni locali

## Percorso AI-first e compatibilità

Le nuove campagne HTTP devono passare dall'anteprima agente e dichiarare i flussi;
il server assegna `decision_engine=ai_first_1`. Una richiesta generica alla vecchia
API non può più avviare implicitamente il motore precedente. Il modulo
`ResearchStore.create` conserva il formato precedente per replay isolati e
compatibilità; non è una seconda scelta nella UI di avvio.

Stop/Riprendi delle campagne storiche usa lo snapshot originale: non migra la
campagna a metà ricerca. I nuovi campi vivono nei JSON versionati di campagne,
documenti e revisioni già esistenti. Nessuna migrazione del database operativo è
stata eseguita durante questa implementazione.

Le risposte del nuovo task `COMMERCIAL_DECISION_1` sono decisioni commerciali
validate. Il valore storico `mode=shadow` viene conservato nella configurazione,
ma **non significa confronto parallelo fra due motori**. L'anteprima lo chiarisce;
nessun invio viene eseguito.

Rollback: verificare il backup indicato in `CUSTOMERSEARCH-CLEANUP-MANIFEST.json`,
fermare prima eventuale lavoro, ripristinare **su copia** il codice salvato.
Non sovrascrivere il DB corrente con un vecchio snapshot: campagne e revisioni
create dopo il backup andrebbero perse. Il percorso precedente rimane nel
codice finché benchmark semantico indipendente e prova autorizzata non consentono
di ritirarlo; non rimuoverlo solo perché ha meno chiamanti statici.

La retention verificata è eseguibile con `scripts/cleanup_ai_first.py` (anteprima)
e `--apply` (solo con preflight e backup verificato). L'archivio si legge con
`scripts.analysis_archive.read_text`; il comando verifica checksum prima di
rimuovere gli originali. Non include database, ambiente o credenziali.

## Avvio e riavvio

Dalla radice: `.venv/bin/python app.py`, poi http://127.0.0.1:8765. Se la porta è occupata, non avviare una seconda copia. Identifica il processo con `lsof -nP -iTCP:8765 -sTCP:LISTEN`; ferma soltanto il PID verificato di CustomerSearch, preferibilmente con `Ctrl+C` nel suo Terminale o `kill -TERM PID`. Non usare `killall python`.

Prima di riavviare durante una ricerca, usa Stop e attendi lo stato fermo. Refresh aggiorna il browser, non il backend. La 9.2.2 non ha riavviato il processo già impegnato nella Campagna 42: le modifiche saranno caricate al successivo riavvio esplicito.

## Campagne e budget

Prepara un'anteprima, controlla flussi/regioni/modalità e autorizza l'avvio dall'interfaccia. Le impostazioni AI vengono copiate nelle nuove campagne; cambiare i default non aggiorna una campagna esistente. Stop conserva risultati e contatori; Riprendi non azzera il costo. Un budget locale esaurito non indica che il saldo Serper o OpenAI sia esaurito.

Controlla separatamente URL scoperti, aziende identificate, richieste verificate, potenziali e candidati da approfondire. Una collaborazione generica non è una commessa; equity non è un budget. I risultati si valutano con le prove e successivamente con risposte/contratti reali.

## Backup completo

```bash
.venv/bin/python -B scripts/backup.py
```

Il comando produce una directory privata in `data/backups/`: snapshot SQLite, `project.zip` e manifest con checksum/conteggi. Può contenere segreti. Usa la SQLite backup API, verifica integrità e legge i file a blocchi. Le prove operative restano incluse nei file del progetto; ambienti, `.git`, link simbolici e backup annidati vengono esclusi.

Verifica un ripristino senza toccare l'app (sostituisci il percorso):

```bash
.venv/bin/python -B -c "from scripts.backup import verify_backup; print(verify_backup('data/backups/NOME_BACKUP'))"
```

Per un ripristino operativo: ferma prima backend e worker; conserva un nuovo backup dello stato attuale; verifica lo snapshot scelto; estrai `project.zip` in una cartella separata; copia lo snapshot SQLite come `data/sales.sqlite3` della copia. Ricrea `.venv` dalle dipendenze e prova lì il backend. Solo dopo verifica sostituisci l'installazione desiderata. Non sovrascrivere un database aperto e non mescolare suoi file WAL/SHM con uno snapshot diverso. Non estrarre ZIP non attendibili nel progetto.

## Archivio e rollback della pulizia

`archives/customersearch-analysis-archive.zip` contiene analisi storiche separate per categoria e un `ARCHIVE-MANIFEST.json`. Il checksum esterno è nel file `.sha256`. Gli originali esatti anteriori alla pulizia sono in `data/backups/customersearch922-preflight/originals.zip`; la copia SQLite e il manifest stanno nella stessa directory privata. Questo backup di preflight ha un formato diverso dal backup operativo `project.zip` e va verificato con il suo manifest.

`CLEANUP-MANIFEST.json` elenca ogni archiviazione, spostamento e cache rimossa, con hash e percorso di rollback. Per ripristinare un singolo file estrailo prima in una cartella temporanea e confronta l'hash; non sovrascrivere successive modifiche. I vecchi rollback sono raccolti in `data/backups/legacy/`, con corrispondenze nel manifest. La pulizia non elimina backup o prove per raggiungere una dimensione arbitraria.

Le ultime cinque campagne effettivamente avviate sono elencate in `reports/recent/README.md`. La 42 era attiva al momento del controllo: una fotografia intermedia non è un report finale. Gli script storici che leggono report archiviati usano `scripts.analysis_archive`; quelli dipendenti da altri output locali conservano i propri input. Prima di eseguire vecchi script pilot, verifica se effettuano richieste live.

## Diagnostica e test

Esegui i comandi offline nel README. I risultati della 9.2.2 sono in `implementation-report/customersearch922/`. Per testare un checkout nuovo, servono Python, i pacchetti di `requirements.txt` e il browser Playwright. I test su copie non devono usare `.env` o il database originale. Nessun test offline attesta che un provider esterno sia disponibile o che una query produca clienti.
