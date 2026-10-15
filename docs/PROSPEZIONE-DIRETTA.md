# Correzione della ricerca clienti — 14 ottobre 2026

Aggiornamento successivo: su richiesta dell’utente il provider attivo è ora soltanto Serper. Il collaudo Yahoo descritto qui è storico. Vedi [passaggio a Serper](SOLO-SERPER.md).

## Problema riscontrato

Le pagine segnalate dall'utente non erano clienti. L'ispezione dei dati locali ha evidenziato due cause distinte:

- Bing, interrogato tramite SearXNG, mescolava risultati pertinenti con pagine Baidu e forum estranei alla query. La provenienza è registrata nei risultati memorizzati.
- Aggiungere una strategia di ricerca delle imprese non aveva rimosso l'avvio dei feed generalisti. Le campagne continuavano a leggere notiziari e bandi, fino a interpretare come segnali anche articoli sportivi.

Inoltre la schermata «Tutta la discovery» presentava fonti editoriali e identità sconosciute insieme ai potenziali clienti. Questo rendeva i risultati ancora meno comprensibili.

## Decisione e implementazione

Per i clienti diretti si cercano prima imprese per attività e territorio, iniziando dai produttori e dalle piccole aziende B2B del Veneto. Le agenzie, se selezionate, mantengono la ricerca di progetti concreti. I bandi rimangono una funzione separata.

1. **Acquisizione:** Bing disabilitato nella configurazione locale. Dopo il riavvio, `/config` conferma Yahoo come unico motore generalista attivo. Le richieste specificano i motori attivi e usano una nuova versione della cache. Nessuna attivazione di Serper.
2. **Pertinenza:** forum, enciclopedie, portali editoriali noti e pagine di bandi vengono esclusi prima della lettura. Un secondo controllo sulle pagine originali esclude gli editori non ancora noti. Un elenco pubblico di imprese può servire per identificare un'azienda, ma non diventa un cliente.
3. **Identificazione:** dominio, attività, territorio ed esclusioni vengono verificati. Budget e bisogno restano sconosciuti quando non dimostrati.
4. **Indagine:** ogni impresa compatibile ottiene una verifica commerciale del sito, anche se non dichiara di cercare un fornitore e non contiene parole chiave di cambiamento. Una sola verifica iniziale per identità nella campagna, più le indagini su eventuali prove successive. Le ricerche complementari restano circoscritte al dominio aziendale.
5. **Qualificazione:** restano necessari progetto completo, bisogno documentato, controprove, fattibilità e canale di contatto. Identificare un'impresa non basta per proporla come opportunità. Modello e misure tecniche non possono inventare l'intenzione d'acquisto.
6. **Presentazione:** «Aziende esaminate» mostra identità verificate, deduplicate per identità legale o dominio. Fonti, errori e decisioni storiche restano disponibili nella diagnostica. Nessuna cancellazione di dati commerciali.

All'avvio e alla ripresa si ritirano dalla coda i lavori generalisti non iniziati; non basta cambiare le nuove query. Si ripristina anche la verifica commerciale delle imprese già identificate prima della correzione. Lo Stop e i controlli di generazione impediscono assegnazioni tardive.

L'accesso HTTP mantiene robots.txt, controlli di rete, verifica dei certificati e timeout. Un sito bloccato o inaccessibile resta non verificabile: non è una prova che l'azienda abbia bisogno di un nuovo sito. Se il motore è indisponibile, non si riempiono i risultati usando feed estranei.

## Conservazione e collaudo

Backup precedente alle modifiche: `data/backups/20261013T224212862138Z/`, archivio e database verificati. Il confronto successivo conferma l'integrità SQLite e la conservazione delle tabelle commerciali e delle 43 valutazioni precedenti: [rapporto](company-focused-preservation.json).

Test di regressione: i tre URL segnalati, rifiuto prima del fetch, editori sconosciuti, rispetto del motore abilitato, nessun feed generalista nelle nuove campagne, ripresa delle code, conservazione dello storico, verifica senza annunci, deduplicazione e paginazione della vista aziende. I test precedenti che imponevano l'avvio di rami generalisti sono aggiornati alla nuova politica; i lettori RSS rimangono testati separatamente.

I collaudi Playwright su 390 e 1440 px verificano schede, paginazione, esiti, focus durante gli aggiornamenti, filtri, dossier, pipeline, conferma contatto, eliminazione e Avvia/Stop/Riprendi. Nessun errore JavaScript rilevato.

Suite completa finale: **301 test superati** (`.venv/bin/python -m unittest discover -s tests`). Durante il pilota il test che simula il modello attendeva il lock della vera inferenza locale: attesa verificata, non chiamata esterna del test. [Risultati del collaudo](company-focused-verification.json).

## Prova reale e limiti

[Primo campione](company-focused-pilot.json): query gratuite su impiantistica, ingegneria e lavorazioni meccaniche in Veneto. Sei domini nuovi rispetto alla memoria commerciale: tre imprese identificate, un elenco di imprese e due fonti non verificabili. Imprese identificate: Italmeccanica, Tornitura Ri.Gal. e Stox. Nessuna di queste viene qualificata per la sola appartenenza al settore.

La memoria delle URL già viste limita i risultati nuovi del campione; i sei domini non rappresentano tutti i risultati grezzi del motore. Questa prima esecuzione precede l'aggiunta della verifica automatica anche senza parole chiave e non contiene valutazioni commerciali approfondite. Il secondo campione su Padova usa il percorso completo aggiornato.

[Secondo campione, Padova](company-focused-pilot-padova.json): nove domini esaminati, quattro imprese identificate (NET, Picello, Tornitura Ri.Gal. e Mimo), una verifica commerciale approfondita, nessuna opportunità qualificata. La revisione delle schede distingue i siti aziendali dall'università esclusa, dalle identità incomplete e dai siti non accessibili. Ri.Gal. compare in entrambi i campioni: non si sommano i due conteggi come se fossero aziende tutte diverse.

Il caso Picello ha evidenziato anche una lettura impropria dell'informativa privacy da parte dell'estrattore di prove. La correzione esclude quelle pagine dal contesto commerciale, mantenendole eventualmente per i dati societari. La [ripetizione sullo stesso caso](company-focused-recheck.json), usando la copia e la cache, resta **non verificabile**, senza bisogno digitale documentato e con citazioni del modello non validate. Non è una nuova osservazione indipendente e non viene presentata come scarto commerciale certo. Le citazioni non riscontrate impediscono la qualifica.

La campagna locale 3 è stata ripresa dopo il riavvio del server, con le code aggiornate. I contatti precedenti non vengono reinseriti come nuovi lead; l'inserimento tra i qualificati rimane subordinato alle prove.

Queste prove verificano la pertinenza della ricerca e il corretto instradamento. Non misurano risposte, contratti o probabilità di acquisizione. Non c'è ancora evidenza sufficiente per dichiarare una precisione commerciale del 90%.

## Uso

Avvio locale: `.venv/bin/python app.py`, poi `http://127.0.0.1:8765`. Selezionare clienti diretti, produttori/piccole aziende B2B, siti aziendali e il territorio desiderato. «Riprendi» conserva la campagna esistente e usa il percorso aggiornato. Consultare «Opportunità qualificate» per le proposte che superano i controlli e «Aziende esaminate» per seguire la verifica delle imprese.
