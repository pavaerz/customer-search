# CustomerSearch 4.0 — collaudo del 13 ottobre 2026

## Esito

Implementazione locale funzionante, con ricerca persistente, Stop/Riprendi, requisiti obbligatori, dossier, memoria e interfaccia unificata. **Qualità commerciale non ancora validata:** il pilota non ha prodotto opportunità qualificate. Non sono state inviate email, acquistati servizi o effettuate pubblicazioni.

## Backup e storico

Backup verificato prima delle modifiche: `data/backups/20261013T152552430651Z/`.

`scripts/verify_migration4.py` ha applicato due volte la migrazione su una copia, confrontato tutte le righe precedenti, verificato `integrity_check` e ripristinato archivio e database in una directory temporanea, ricontrollando gli hash. Risultati in [migration4.json](migration4.json).

Dopo l’avvio 4.0 sono state confrontate anche le tabelle commerciali reali con il backup: invariati aziende (15), schede (21), prove (69), interazioni (19), archivio (132), eliminazioni (1), esclusioni (5) e audit precedenti (6). Il collaudo HTTP reale ha aggiunto soltanto una campagna sospesa e relativa coda; nessun contatto automatico.

## Test automatici e browser

Suite precedente: 92 test. Suite finale: **141 test** (incluse le regressioni sulla preparazione interrotta della coda e sui processi figli che ignorano SIGTERM). Database temporanei per i test applicativi.

Copertura: richieste generiche e dipendenti; semplici aperture di sede; vecchio design, lentezza e ordini email; prove copiate; citazioni inesistenti; budget ignoto, del soggetto sbagliato o inferiore alla soglia, anche con simbolo € prima dell’importo; identità mancanti/omonime; shop esterni; web app con incognite critiche; deduplicazione, eliminazioni, categorie manuali; migrazione ripetibile; un’unica campagna attiva; Stop, risultati tardivi, ripresa e coda iniziale interrotta; provider e RSS indipendenti; IP privati IPv4/IPv6; protezioni HTTP e rifiuto dei modelli cloud.

`scripts/check_research_ui.py`, su Chrome con fixture isolate:

- Desktop 1440 px e telefono 390 px, senza overflow orizzontale né errori JavaScript.
- Filtri Aziende/Privati, ricerca per nome, campagna attuale/tutte, apertura dossier e revisione della qualità.
- Conferma contatto, card verde, eliminazione persistente e trascinamento nella pipeline.
- Avvia/Stop/Riprendi, salvataggio delle impostazioni.

La parte browser usa un avvio simulato del coordinatore per evitare rete nelle fixture; il processo reale è verificato separatamente dal pilota e dal collaudo HTTP sull’app avviata.

## Servizi locali e verifiche reali

**Ollama:** runtime ufficiale installato e hash verificato; `qwen2.5:7b`, 4.683.087.332 byte. Prima risposta strutturata di identificazione verificata in 8,31 secondi. Runtime gestito con cloud disabilitato e una inferenza alla volta. Modello e browser condividono anche un lock fra processi.

**SearXNG:** il test “arredamenti Padova sito ufficiale” ha restituito 10 risultati da DuckDuckGo; Brave risultava sospeso per troppe richieste. La query successiva sui nuovi prodotti ha incontrato CAPTCHA di DuckDuckGo e sospensione di Brave. Nessun aggiramento. Il pilota ha continuato su fonti territoriali, RSS/sitemap e candidati già trovati.

**Lighthouse reale**, mobile, sul sito dell’utente `https://designerdimontagna.it/`, tramite proxy con controllo delle destinazioni: test completato in 28 secondi. Prestazioni 75, accessibilità 100, buone pratiche 100, SEO 100. Misura locale di laboratorio, non dato di conversione o necessità di rifacimento. Risultato in `data/pilot4/lighthouse-smoke.json`; report originale nella relativa directory `site-reviews`.

**Stop reale:** misurazioni del coordinatore pilota 0,078 e 0,098 secondi; dal server HTTP dell’app 0,011 secondi. Ripresa con nuova generazione e coda conservata. Arresto entro cinque secondi confermato nei casi provati, inclusa interruzione durante la preparazione. Dettagli in [live-smoke4.json](live-smoke4.json).

## Ricerca pilota

Database separato: `data/pilot4/pilot.sqlite3`. Campagna con obiettivo 50, quattro regioni prioritarie, clienti diretti e agenzie. Avviata alle 15:49 UTC, fermata manualmente alle 16:16 UTC per la revisione del campione. **Non si è fermata per un limite di durata o di query.** La coda rimane conservata: 8.306 attività pendenti e 349 query sospese dal provider al momento del collaudo.

| Misura | Risultato |
|---|---:|
| Candidati unici esaminati dopo la deduplicazione corretta | 20 |
| Qualificati | 0 |
| Scartati | 9 |
| Non verificabili | 11 |
| Valutazioni storiche conservate | 21 |
| Documenti salvati | 102 |
| Parametri di query riuscite registrati | 2 |
| Fonti verificate disponibili / non disponibili, inclusi feed e sitemap | 12 / 1 |

Distribuzione del campione: cambiamenti 8, opportunità digitali 10, domanda esplicita 2. Processi e correlazione non hanno un campione autonomo sufficiente in questa esecuzione. I candidati comprendono anche editori e intermediari riconosciuti come inadatti, non venti imprese già verificate.

È stata svolta una **revisione documentale separata dell’assistente** su tutti i 20 candidati unici, leggendo pagine originali conservate, identità e tracce dei controlli. Non è una revisione di un esperto umano né un esperimento di acquisizione clienti. Esiti nominativi e motivazioni in [pilot4-review.json](pilot4-review.json).

Esempi:

- Tender e Understack offrono sviluppo web: questo non dimostra che cerchino un fornitore per una commessa.
- Deluxe Dreaming Milano: cambio sede e catalogo non documentano un progetto digitale. La sede legale è fuori dalle quattro regioni selezionate nel pilota.
- ArredissimA: servizi/configuratore presenti; uno sconto da 5.000 € sui mobili non è un budget per un sito.
- Business Matching di Assolombarda è un intermediario; la Camera di Commercio è una fonte istituzionale. Non devono diventare automaticamente clienti.
- Villevenete e Ambienti: dati aziendali leggibili, ma controlli commerciali inizialmente incompleti. L’incompletezza non è stata trasformata in una proposta qualificata.

## Difetti emersi e correzioni

1. **Indirizzi su più righe e sigle provinciali:** corretto il riconoscimento di Rosà/VI, Longare/VI e Bassano del Grappa, VI, IT. Controllo successivo su tre homepage reali conservate: tutte riconosciute in Veneto con identità verificata. “Via Firenze” non attribuisce la Toscana a un indirizzo napoletano.
2. **Identità provvisoria che diventa verificata:** rilevato un doppione. Riunite le identità senza cancellare valutazioni o ID: 21 conteggi provvisori diventano 20 candidati unici. Aggiunti test di transizione e riconciliazione.
3. **Editori, crediti del sito e collegamenti generici:** una società citata nel credito di sviluppo non attribuisce la forma S.p.A. al titolare della pagina. Rafforzati riconoscimento di fonti istituzionali/editoriali e abbinamento nome-link; endpoint OAuth e condivisioni social esclusi.
4. **Modello locale:** osservati riferimenti non validi e output troncati. Aggiunti limiti agli elenchi e ai testi, enum contenenti soltanto ID reali, contesto esplicito sui servizi digitali del freelance e separazione fra analisi completata e prova insufficiente. Nessuno di questi errori ha prodotto una qualifica.
5. **Interruzione durante il riempimento iniziale della coda:** introdotto un checkpoint persistente; la ripresa completa la preparazione in modo idempotente, senza perdere strategie non ancora inserite.
6. **Pausa HTTP al limite dell’intervallo:** corretto un intervallo di attesa che poteva diventare negativo. Immagini e link di condivisione non vengono scambiati per pagine commerciali necessarie.

Dopo le correzioni del modello, una nuova ispezione reale completa di Battocchio è terminata in 57 secondi con output valido: **analisi completata, nessun bisogno digitale documentato, nessuna qualifica**. Non ha proposto di acquistare mobili dall’azienda. La controverifica di Ambienti continua a evidenziare il catalogo PDF non leggibile dal componente HTML. Le verifiche successive sono regressioni mirate sugli stessi casi, non un campione indipendente di precisione commerciale.

## Criterio di qualità: non raggiunto né misurabile

Non ci sono qualificati da revisionare: **precisione non calcolabile**, non “100%” e non “zero falsi positivi dimostrati”. Mancano i 20 qualificati necessari per verificare la soglia del 90%. La revisione copre 9 scarti e 11 controlli incompleti, non 20 scarti definitivi.

Non è possibile stimare quante opportunità utili siano state perse: fonti bloccate, PDF e interpretazioni incomplete non consentono una verità di riferimento completa. Sono stati trovati errori tecnici e di classificazione, ma non una specifica commessa completa erroneamente scartata e poi verificata come utile.

Il motore resta **sperimentale dal punto di vista commerciale**. Il passo successivo è accumulare un campione indipendente dopo le correzioni, con fonti accessibili, quindi confrontare contatti, risposte e contratti reali. I requisiti non sono stati abbassati per riempire la shortlist.
