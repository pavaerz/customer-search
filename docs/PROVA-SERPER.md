# Confronto esplorativo Serper / SearXNG

Il provider della ricerca ordinaria resta SearXNG. Serper è disponibile esclusivamente nella prova esplicita in **Impostazioni → Prova sul campo**. Nessun fallback a pagamento, acquisto o invio commerciale. Tavily rimane disattivato.

## Avvio

Avvia l'app con `.venv/bin/python app.py`, apri `http://127.0.0.1:8765` e scegli Impostazioni. La chiave già presente in `SERPER_API_KEY` viene riconosciuta senza mostrarla. Puoi sostituirla nel campo password: viene salvata in un file locale con permessi 0600, separato dalle impostazioni pubbliche. Il salvataggio non avvia richieste.

Controlla i crediti nel pannello Serper, conferma almeno dodici crediti gratuiti e premi **Avvia confronto**. L'app non ha una fonte affidabile per distinguere crediti gratuiti e acquistati: la conferma si basa sul saldo verificato dall'utente. Nessuna ricarica automatica. Il limite cumulativo locale è 100 richieste Serper e non si azzera cambiando chiave, fermando la prova o riavviando l'app.

**Ferma confronto** invalida la generazione prima di terminare il processo posseduto dall'app. Le operazioni già riservate rimangono conteggiate anche in caso di errore o Stop, perché potrebbero essere state ricevute dal provider. Le risposte tardive non diventano valutazioni salvate. Al riavvio le prove interrotte vengono fermate, mai riavviate automaticamente. Un nuovo Avvia crea un nuovo campione e consuma fino ad altre dodici richieste; non è una ripresa gratuita.

## Protocollo v2 e correzioni della verifica

Sei query iniziali per settore/bisogno, identiche sui due provider. Per le fonti editoriali si seguono i collegamenti aziendali riscontrati nel corpo dell’articolo; se mancano, si cercano i nomi verificati nella fonte. Massimo sei query aggiuntive e quattro siti derivati per provider, senza ricorsione. Tutte le richieste Serper, incluse quelle di identità, concorrono al tetto cumulativo di 100. Gli snippet non sono prove e il sito trovato deve superare identità, concordanza del nome/territorio, contatti e requisiti commerciali. Le fonti con identità irrisolta rimangono da approfondire.

Le righe derivate conservano fonte, soggetto citato e metodo di acquisizione. Le aziende raggiunte da entrambi i provider sono lette una volta e attribuite a entrambi. I risultati rimangono isolati dal CRM. Il protocollo cambia query e verifica: il confronto con v1 **non misura il solo effetto del provider**.

Correzioni applicate anche alla ricerca ordinaria:

- Homepage e pagine Chi siamo/Contatti conservano la data del metadato separatamente; non viene usata come data del cambiamento. Una data WebPage generica non data un evento. La pubblicazione di un articolo resta distinta da una data evento verificata.
- Indirizzi e partite IVA nei corpi di directory, articoli e annunci non identificano il titolare del dominio. Si usano dati societari coerenti, footer e organizzazioni strutturate collegate al dominio. Località ambigue restano sconosciute.
- Le assunzioni sono riconosciute prima del modello, comprese quelle cercate dalla strategia assunzioni. Rimangono segnali complementari, non commesse.
- Informative di consenso marcate nel HTML sono escluse dall’input commerciale; l’originale resta conservato. Contenuti identici e destinazioni uguali dopo redirect non causano analisi duplicate. Citazioni estratte dal modello devono comparire anche nell’estratto effettivamente ricevuto.
- Le varianti cambiano bisogno/settore prima di ripetere una query senza virgolette. Due query senza riscontri non esauriscono una strategia: si continua sulla frontiera finita e deduplicata. Le pause per problemi tecnici rimangono operative.
- Unioncamere è riconosciuta come fonte editoriale/associativa, non come cliente.

Backup verificato prima di queste modifiche: `data/backups/20261013T210929825458Z/`. Nessuna nuova migrazione necessaria e nessuna cancellazione di dati commerciali.

[Regressione sulle cinque fonti reali della prima prova](serper-evidence-regression.json): i tre metadati delle pagine permanenti non datano più gli eventi; le due località dei rivenditori non vengono più attribuite al produttore. Verifica eseguita sulle pagine originali conservate, senza nuove richieste API. Non è una misura di conversione né una certificazione generale dell’estrazione.

## Protocollo v1

- Sei query identiche per entrambi i provider, in Veneto: domanda esplicita, prodotti, showroom, assunzioni e-commerce, processi per rivenditori, collaborazioni su progetti. Parametri Italia/italiano, prima pagina, dieci risultati al massimo, nessun filtro temporale. La recenza viene verificata sulle fonti originali.
- Nessuna cache delle query nella prova. Ordine dei provider alternato. Nessun retry automatico: un errore sospende quel provider per il resto del campione, l'altro continua. I fallimenti parziali dei motori SearXNG sono mostrati separatamente.
- Selezione alternando le query: al massimo 24 URL distinti per provider. L'unione viene letta attraverso gli stessi controlli HTTP/robots e la stessa selezione preliminare dell'app. Gli URL comuni sono verificati una volta, con attribuzione a entrambi.
- Fino a quattro candidati promettenti o articoli da risolvere per provider vengono approfonditi con `inspect_candidate`, comprese le regole commerciali, le citazioni e il modello locale. Il limite rende misurabile questo esperimento: non modifica la ricerca continua ordinaria.
- Le fonti editoriali senza identità aziendali risolte non sono clienti. Il primo protocollo conserva i soggetti/collegamenti proposti dal risolutore, ma non esegue ulteriori query di identificazione: la relativa verifica resta incompleta, esplicitamente. Il confronto non misura l'intera capacità della discovery multistadio.
- Stessa copia iniziale dello storico e delle esclusioni per entrambi i provider, stesso lettore e cache delle pagine. I tempi della lettura condivisa non sono confrontabili come velocità dei provider.
- La tabella separa URL, pagine esaminate, identità verificate, promettenti, approfondimenti, aziende qualificate e revisioni. Aziende deduplicate per identità legale disponibile, altrimenti dominio. La categoria «promettente» è solo preliminare.
- Nessun numero di link viene tradotto in efficacia commerciale. Il budget ignoto resta ignoto. Costo per opportunità non calcolato senza dati di costo affidabili e risultati revisionati.

## Revisione

Alla fine o dopo Stop, apri ogni candidato: fonte originale, motivo, date, prove, eventuale progetto e controlli mancanti. Registra una motivazione specifica: opportunità confermata/falso positivo per i qualificati, qualificazione non giustificata/opportunità persa per gli altri.

Il giudizio va registrato dopo una revisione separata delle prove; un voto del modello non è revisione indipendente. Non viene dichiarato un vincitore automaticamente. Obiettivo di qualità successivo: almeno 20 qualificati revisionati e almeno 90% di conferme, senza errori critici di identità o prove. Questa piccola prima prova può individuare problemi, non certificare acquisizione, risposte o vendite.

## Dati e sicurezza

Schema aggiuntivo 44: `search_trials`, `search_trial_requests`, `search_trial_reviews`. Migrazione ripetibile, senza modifiche alle tabelle commerciali. Report incrementale con prove originali e date in SQLite. La UI omette il testo integrale dei documenti e non restituisce mai la chiave. Endpoint HTTP sotto le protezioni Host, Origin e CSRF già esistenti.

Il worker separato usa una copia SQLite in `data/search-trials/trial-N.sqlite3`, permessi 0600, conservando esclusioni e configurazioni. Non inserisce contatti nel CRM. Il report rimane nel database principale; i campioni precedenti restano conservati, mentre il pannello mostra l'ultimo.

Richieste Serper soltanto a `https://google.serper.dev/search`, TLS verificato, niente redirect, header segreto escluso da log/report, risposta limitata a 2 MB. Nessuna trasmissione del profilo fiscale: sono inviate soltanto query commerciali e, nel protocollo 2, nomi aziendali già riscontrati nelle fonti pubbliche.

Backup precedente: `data/backups/20261013T203018291161Z/`, archivi e hash verificati con `scripts/backup.py`. Anche le nuove credenziali locali saranno incluse nei successivi archivi privati, mai serviti dal server.

## Collaudo

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_search_trial_ui.py
```

I test coprono limite atomico tra processi concorrenti, errori conteggiati, Stop e risposte tardive, assenza di retry, chiavi private, nessun redirect della chiave, normalizzazione, campionamento bilanciato, separazione tra pagine e aziende, isolamento dal CRM, revisioni e protezioni HTTP. Browser su 390 e 1440 px: avvio/arresto, revisione, modulo preservato durante polling, nessun overflow e nessun errore JavaScript. Le fixture di collaudo sono isolate dai dati reali.

Verifica del ripristino e della migrazione: [rapporto](serper-migration-check.json), 43 tabelle preesistenti preservate integralmente. Collaudo finale: 244 test superati; browser 390/1440 px senza overflow o errori JavaScript.

## Primo pilota reale — 13 ottobre 2026

[Report misurato](serper-live-pilot.json) · [Note della revisione tecnica](serper-review-notes.json).

| Misura | Serper | SearXNG |
|---|---:|---:|
| Query identiche eseguite | 6 | 6 |
| Errori del provider | 0 | 0 |
| URL utilizzabili restituiti | 23 | 49 |
| Pagine del campione controllate | 23 | 24 |
| Identità riconosciute automaticamente, preliminari | 9 | 4 |
| Candidati passati alla verifica approfondita | 4 | 4 |
| Aziende qualificate | 0 | 0 |

Il consumo registrato è di **6 richieste Serper**. Nessun acquisto. Durata osservata 1325 secondi, comprendente attesa del modello condiviso con una ricerca bandi avviata durante il pilota e successivamente fermata dall'utente. Lettura dello stato HTTP dell'app: 26 ms in una misura durante il lavoro; non un benchmark statistico. Nessuna modifica alle righe di aziende, proposte, interazioni, eliminazioni o categorie commerciali rispetto al backup.

Revisione tecnica separata di 20 pagine non qualificate, eseguita da Codex sui testi acquisiti: 15 giudizi di non promozione sostenuti dalle prove disponibili e 5 errori nei dati o nella motivazione (date di homepage/Chi siamo e indirizzi di rivenditori attribuiti all'editore). Non è una revisione umana e non certifica assenza di opportunità non osservate. Nessuna opportunità qualificata da revisionare: la soglia 90% su 20 qualificati **non è verificabile**. Non attribuire significato positivo a zero falsi positivi su zero qualificati.

Serper ha restituito pagine tematicamente più coerenti; SearXNG ha incluso dizionari e assistenza YouTube. Questo è un riscontro esplorativo sul campione, non una superiorità generale. Entrambi hanno risposto tecnicamente. Nessuno ha prodotto una shortlist commercialmente validata in questa prova.

Problemi da affrontare prima di acquistare crediti:

1. Query su eventi senza vincolo temporale recuperano annunci vecchi. La domanda esplicita troppo vincolata può restituire zero risultati.
2. Separare meglio committenti, venditori di servizi e intermediari già nella selezione preliminare; un'assunzione non è una commessa.
3. Collegare indirizzi e dati societari al soggetto corretto; non usare la data di creazione di una homepage per datare tutti i fatti presenti.
4. Evitare di ripetere al modello le stesse informative e pagine equivalenti dopo redirect, mantenendo gli originali come prove.
5. Migliorare l'estrazione delle citazioni: il modello ha prodotto citazioni respinte e interpretazioni errate di testi di servizio. Le protezioni hanno impedito promozioni senza prove; non significa che l'analisi sia efficiente o completa.

Esempi: Amerigo presenta già un catalogo con carrello; la pagina dell'inaugurazione Triumph porta a un indice di notizie; l'annuncio NECTED riguarda un dipendente per un committente non identificato; Bega descrive vendite online già attive in otto mercati. Sono motivi per approfondire o non proporre il progetto ipotizzato, non contatti da inserire per riempire un numero.


## Prove successive e collaudo delle correzioni

### Campione 2: query troppo vincolate

[Report originale, conservato](serper-pilot-v2.json) · [Rivalutazione offline](serper-pilot-v2-recheck.json).

Sei nuove richieste Serper, 27 URL restituiti contro 29 SearXNG; 47 pagine uniche lette. Prova interrotta intenzionalmente prima di completare gli approfondimenti: prevalenza di guide, editori e fornitori, compresa Unioncamere inizialmente non riconosciuta come associazione. Non costituisce un confronto completo della qualificazione.

Le correzioni sono state verificate separatamente sulle stesse pagine conservate, senza rete e senza riscrivere il report originale: i candidati preliminarmente promettenti passano da 14 a 6. Le esclusioni aggiunte riconoscono guide, forum/portfolio, date esplicite con virgola e fonti associative. «Assunzione al bilancio» non viene più confusa con un’assunzione di personale. È una regressione tecnica sul campione che ha originato le correzioni, non un test indipendente della qualità commerciale.

### Campione 3: formulazioni naturali, non una soglia più permissiva

[Report misurato](serper-pilot-v3.json) · [20 revisioni tecniche](serper-pilot-v3-reviews.json) · [Rilettura offline](serper-pilot-v3-recheck.json).

Query meno vincolate, con l’anno corrente per gli eventi. La presenza dell’anno nella query non prova l’attualità: le date si controllano nelle fonti. Requisiti commerciali e punteggio invariati.

| Misura | Serper | SearXNG |
|---|---:|---:|
| Query iniziali | 6 | 6 |
| Query aggiuntive di identità | 0 | 0 |
| Errori di ricerca | 0 | 0 |
| URL utilizzabili restituiti | 53 | 53 |
| Pagine esaminate, incluse derivate | 25 | 24 |
| Valutazioni approfondite attribuite al provider | 6 | 4 |
| Opportunità qualificate | 0 | 0 |

Sono 47 pagine uniche (46 iniziali più un collegamento derivato) e 8 valutazioni approfondite uniche: le righe dei provider includono pagine comuni e non si sommano. Alcuni controlli restano non verificabili per restrizioni delle fonti o limiti tecnici. Il completamento indica che il protocollo del campione è terminato, non che ogni sito sia stato interamente verificato.

Revisione tecnica Codex di 20 non qualificati: 19 mancate promozioni sostenute dagli estratti e un errore nel collegamento della fonte. Il risolutore aveva seguito «la Regione», dal Bollettino regionale al dominio principale, come se fosse un’impresa. Non è stata qualificata. Questo non valida la risoluzione di un’azienda reale: dimostra il percorso tecnico, evidenziando un errore. Correzione successiva: istituzioni e collegamenti interni tra dominio e sottodomini sono esclusi; verificata con un test automatico e sul collegamento reale conservato ([regressione](serper-publisher-link-regression.json)). I collegamenti commerciali legittimi restano coperti dalle fixture; non dichiariamo una risoluzione aziendale positiva in questo campione.

Il campione contiene ancora fornitori di servizi, guide ai bandi e notizie macroeconomiche, che non sono segnali di acquisto delle aziende. Nessuna misura di efficacia commerciale o superiorità generale del provider. Nessun qualificato da revisionare: la soglia 90% su 20 qualificati resta non misurabile. Nessuna soglia abbassata per produrre risultati.

Consumo complessivo: **18 richieste Serper**, di cui 6 della prova iniziale e 12 nelle due prove successive. Nessun acquisto o invio. La ricerca ordinaria usa ancora SearXNG; Serper resta una prova esplicita entro 100 richieste cumulative.

### Verifiche finali

- **264 test superati**: regressioni su date, identità, rivenditori, annunci dipendenti, guide, citazioni, domini degli editori, ripresa e prosecuzione delle strategie; flusso articolo → ricerca identità → sito → qualificazione provato anche con fixture controllate.
- Browser 390/1440 px: avvio/arresto del confronto, revisione, testo conservato durante polling, nessun overflow o errore JavaScript. Pannello delle prove con origine del collegamento e distinzione tra discovery e query di identificazione.
- Schermata ordinaria desktop/mobile: filtri, dossier, revisione, contatto verde, eliminazione, Avvia/Stop/Riprendi, pipeline trascinabile, impostazioni.
- [Integrità e conservazione dei dati commerciali](serper-data-preservation.json): confronto integrale delle righe con il backup, non solo conteggi; SQLite integro. Nessun nuovo cliente inserito dalla prova.

Rivalutazione riproducibile senza rete:

```bash
.venv/bin/python scripts/recheck_trial_evidence.py --run 3 --output /tmp/serper-recheck.json
```

Il comando usa una copia temporanea dello snapshot e le pagine HTML già conservate, senza query, modello, nuove qualifiche o modifiche ai report originali.
