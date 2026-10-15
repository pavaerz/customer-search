# Revisione grafica e funzionale — 13 ottobre 2026

## Intervento

Revisione di panoramica, Aziende, Privati, trattative, esiti commerciali, storico contatti, ricerche e fonti, archivio, impostazioni e dossier. Tema chiaro, tipografia e controlli coerenti; nessuna modifica ai criteri di qualificazione o ai dati commerciali.

- Filtri di ricerca: sei campi nella stessa griglia, altezze uniformi, tre colonne desktop, due su schermi intermedi e una sui telefoni stretti. Regioni selezionabili con i nomi esatti usati dal motore; azzeramento dei filtri e recupero degli errori di caricamento.
- Ricerca: pannello più compatto, Riprendi come azione principale quando la campagna è sospesa, progresso leggibile, preferenze e dettagli secondari separati. La tab Tutti è selezionata correttamente all’ingresso.
- Aggiornamenti: avanzamento e contatori si aggiornano senza ricostruire i campi. Selezione del testo, focus, preferenze aperte, note e impostazioni non salvate restano intatti durante il polling. Risposte obsolete dei filtri annullate o ignorate; richieste di polling non sovrapposte.
- Trattative: schede compatte, riepiloghi limitati visivamente con dossier completo disponibile, nomi leggibili, colonne con scorrimento interno, intestazioni persistenti e frecce per lo scorrimento orizzontale. Drag con mouse, touch e selezione dello stato conservati.
- Dossier: spaziature uniformi, titoli lunghi adattivi, chiusura con Escape e ritorno del focus alla scheda. Conferma contatto aggiornata anche nella finestra aperta, pulsante Elimina riabilitato correttamente dopo il salvataggio; eliminare dal dossier chiude la finestra. Notifiche visibili sopra lo sfondo modale.
- Archivio: ricerca e pagine da 25 record; tutti i record originali restano disponibili. Errori di archivio e campagne mostrano un comando Riprova.
- Esiti commerciali: distinzione dai risultati della ricerca; dettagli per motore e strategia richiudibili. Impostazioni con modello locale nei dettagli e spaziature regolari.
- Connessione: indicazione visibile delle interruzioni e recupero automatico; caricamento iniziale ripetibile senza ricaricare l’intera app.

## Verifica

- **141 test Python superati** (`.venv/bin/python -m unittest discover -s tests -q`).
- Controllo sintattico JavaScript di `static/app.js` e `static/research.js` superato.
- `scripts/check_research_ui.py`: filtri, dossier, revisione, card verde, eliminazione, Avvia/Stop/Riprendi, drag con mouse e salvataggio impostazioni su database temporaneo.
- `scripts/check_visual_quality.py`: **54 combinazioni** di nove schermate e larghezze **320, 390, 768, 1024, 1440 e 1920 px**. Verificate anche tabelle espanse, nomi lunghi e cinque sezioni del dossier a 390 e 1440 px.
- Nessun errore JavaScript e nessuna fuoriuscita orizzontale della pagina nei casi provati. Tabelle e pipeline mantengono il proprio scorrimento orizzontale intenzionale.
- Verificati: allineamento effettivo dei controlli; aggiornamento durante la digitazione con cursore e selezione conservati; errore HTTP e Riprova; perdita e recupero della connessione; paginazione; conferma ed eliminazione dal dossier; tastiera e ritorno del focus; note e impostazioni non salvate; trascinamento con eventi touch reali di Chrome e cambio stato tramite select.
- Ispezione visiva degli screenshot prima/dopo e delle schede su desktop e telefono. Collaudo con Chrome; Safari e Firefox non inclusi in questa sessione. Le verifiche responsive non sostituiscono un test su dispositivi fisici.
- Nessuna richiesta esterna nei test browser isolati, nessuna email inviata, nessuna ricerca commerciale avviata dall’audit sull’app reale.

Risultati strutturati in [UI-AUDIT-4.0.json](UI-AUDIT-4.0.json). Screenshot riproducibili con lo script, salvati in `/tmp/customersearch-ui-audit/`.

## Conservazione e utilizzo

Backup verificato prima delle modifiche: `data/backups/20261013T173545818936Z/` (integrità SQLite, hash archivio e database). Confronto finale con il backup: invariati aziende, fonti, prove, schede, interazioni, ricerche precedenti, archivio, audit, esclusioni, eliminazioni e categorie manuali. Integrità del database: `ok`.

L’app in esecuzione serve già i file aggiornati. Aprire `http://127.0.0.1:8765` e ricaricare la pagina. Nessuna migrazione o configurazione aggiuntiva richiesta.
