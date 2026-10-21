# CustomerSearch — sintesi decisionale AI-first

20 ottobre 2026. Fase 1 completata: analisi, progettazione e verifiche offline. Il nuovo sistema **non è stato implementato**.

## Perché oggi il sistema non produce opportunità utilizzabili

Il problema dimostrato non è che manchino clienti. CustomerSearch trova anche segnali pertinenti, ma spesso non riesce a trasformarli in una valutazione commerciale utile.

Due esempi concreti nelle prove salvate: **Kondividi e NHW Consulting invitano professionisti esterni a collaborare** e presentano un canale pubblico di contatto. Sono piste sensate per proporre le competenze di Diego, anche senza una commessa dichiarata. L'app continua però a richiedere una data recente di pubblicazione per qualificarle. Nel replay attuale NHW recupera identità e contatto, ma rimane bloccata proprio sulla data.

Questo non dimostra che le due agenzie abbiano incarichi disponibili: dimostra che l'app confonde una collaborazione aperta con un annuncio per una posizione specifica.

Ci sono altri tre problemi strutturali:

- **Troppa AI prima delle prove originali.** Nella Campagna 43, su 100 chiamate, 66 appartengono allo screening, 21 a pianificazione/ripianificazione e 13 alla verifica, inclusi recuperi e completamenti. NEWS consuma 40 chiamate senza arrivare a record con fonte originale.
- **Attribuzione fragile.** Un dettaglio di ilGiornale.it è stato collegato a Elice Group; una directory può diventare il soggetto analizzato invece dell'azienda cercata. Citare parole realmente presenti non basta se appartengono al soggetto sbagliato.
- **Date e ruoli interpretati male.** Annunci del 2015 restano con data sconosciuta; un produttore alimentare può essere classificato come istituzione per una notizia accessoria sul sito.

Le campagne 37, 38, 39, 41 e 43 hanno tutte zero opportunità qualificate. La 42 usa invece il percorso precedente: è sospesa e non va trattata come un test equivalente del nuovo agente.

## La soluzione proposta

Conservare l'app locale e i cinque flussi, ma dare all'AI un compito commerciale esplicito: **INTERESTING, NOT_INTERESTING oppure NEEDS_RESEARCH**, motivato sulle prove originali.

Il software continua a controllare fonti, identità, citazioni, budget, sicurezza e autorizzazioni. Il modello non può inventare un contatto, trasformare un'inferenza in una richiesta dichiarata o eseguire liberamente strumenti.

Il percorso diventa: individuare una pista, leggere le prove pertinenti, capire soggetto e richiesta, valutarla, fare solo gli approfondimenti capaci di cambiare la decisione, salvare un dossier comprensibile.

Le schede distinguono **commesse, collaborazioni aperte, candidature spontanee, proposte proattive ed equity**. Interesse commerciale, solidità delle prove e possibilità di contatto restano separati. Budget e data sconosciuti non diventano né informazioni inventate né esclusioni automatiche.

Una parte maggiore della capacità AI viene riservata alla valutazione degli originali. Le quote proposte sono ipotesi da verificare: nessun budget è stato modificato.

## Quanto cambia e cosa rimane

È un intervento significativo sul coordinamento della ricerca e sulla qualificazione, non una riscrittura completa. Restano Python, SQLite, provider, protezioni di rete, CRM, memoria, documenti originali, campagne, esclusioni manuali e cinque flussi.

Le nuove decisioni avrebbero dati versionati e migrazioni additive, con test su copie e rollback. Lo storico manterrebbe i propri giudizi; nessuna rivalutazione riscriverebbe retroattivamente i risultati delle campagne.

## Cosa abbiamo verificato e cosa manca

Sono passati **92 test offline di regressione**. Il benchmark aggiunto comprende **13 casi reali** e **12 sonde diagnostiche**: nove conformi, tre lacune temporali riproducibili. Le due piste di collaborazione annotate come interessanti non emergono come qualificate nella proiezione dello stato storico: richiamo 0/2 su questo piccolo campione selezionato.

Questi numeri non misurano la qualità di un nuovo modello: non sono state eseguite nuove inferenze. Il benchmark non contiene un classificatore che restituisce le risposte attese.

Restano da dimostrare la qualità semantica del futuro decisore, la tenuta su aziende mai viste, i costi reali del nuovo percorso e l'effettiva disponibilità dei contatti. Più schede INTERESTING, da sole, non dimostrano miglioramento commerciale.

## Come decidere se funziona

Prima del rilascio: casi critici corretti e un campione indipendente di almeno 50 casi, con revisione umana. Obiettivi iniziali proposti: almeno 90% di conferme su almeno 20 risultati interessanti revisionati, almeno 85% di richiamo sui positivi noti e nessuna attribuzione critica inventata.

La misura di prodotto sarà il numero di opportunità uniche, pertinenti e realmente utilizzabili da Diego. Il CRM dovrà poi registrare contatti, risposte, conversazioni, preventivi e clienti paganti. **Due clienti al mese resta l'obiettivo, non una previsione supportata dai dati attuali.**

## Primo passo concreto

La mia raccomandazione è approvare questa separazione fra giudizio commerciale e validazione delle prove. La prima milestone implementativa sarà formalizzare i contratti, provarne lo schema su una copia e correggere estrazione/attribuzione sui casi congelati; poi integrare il decisore e verificarlo su casi nuovi. Una nuova campagna viene dopo questa validazione.

Documenti per la decisione:

- [Audit: fatti, cause e moduli coinvolti](CUSTOMERSEARCH-AI-FIRST-AUDIT.md).
- [Architettura: contratti, dati, AI, sicurezza e UI](CUSTOMERSEARCH-AI-FIRST-ARCHITECTURE.md).
- [Benchmark: casi, risultati misurati e soglie proposte](CUSTOMERSEARCH-AI-FIRST-BENCHMARK.md).
- [Piano di implementazione: ordine, dipendenze e rollback](CUSTOMERSEARCH-AI-FIRST-IMPLEMENTATION-PLAN.md).

Durante questa fase non sono state avviate campagne, consumate API a pagamento, inviate email o applicate modifiche operative. Non sono stati eseguiti commit o push.
