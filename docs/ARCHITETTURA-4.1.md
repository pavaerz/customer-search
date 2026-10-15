# CustomerSearch 4.1 — decisioni e criteri di accettazione

Backup prima delle modifiche: `data/backups/20261013T181253135811Z`, SQLite integrity_check, conteggi e SHA-256 verificati dal programma di backup. Ripristino: arrestare app e worker, recuperare database e codice dal backup privato.

## Diagnosi riprodotta sul pilota 4.0

La coda non rappresentava 8.306 aziende: 8.299 task erano URL candidati, di cui **8.223 da sitemap**, 41 collegamenti a soggetti citati, 18 da RSS e 17 da HTML; altri 7 task erano fonti. Sono presenti anche feed di commenti, sitemap di categorie, tag, autori e location. Tutti etichettati `change`. La discovery XML estraeva qualsiasi link/loc, senza selezione di articoli, data, rilevanza o gestione della pressione della coda.

Solo due query concluse: arredamento Veneto catalogo/export (10 URL) e nuova linea prodotti Veneto arredamento (2 URL). 349 query bloccate dopo gli errori dei provider. La generazione per settore esterno al ciclo delle strategie dava precedenza all'arredamento. Il pilota NON misura l'esaurimento del mercato o la produttività delle altre strategie.

21 valutazioni, 20 identità dopo riconciliazione, 9 scarti e 12 non verificabili; zero qualificati. Lettura di homepage e molte pagine, PDF non supportati e inferenza su ogni blocco di testo precedevano la decisione di pertinenza. Editori venivano risolti troppo tardi. L'archivio CRM era usato come fonte di nuovi candidati. L'attribuzione passava a correlazione appena esisteva una fonte esterna: non misurava fatti indipendenti. Un errore del modello con filtro progetto poteva diventare uno scarto commerciale.

Restano necessari: robots, indirizzi pubblici verificati, protezioni DNS/redirect/browser, timeout, limiti per documento, esclusioni, citazioni letterali, identità ufficiale, controllo delle soluzioni, budget sconosciuto e validazione finale. Non vanno allentati per ottenere risultati.

## Scelte

Schema additivo 41; candidati preliminari e transizioni separati dalle valutazioni definitive. Discovery rapida su pagina originale, senza modello; verifica approfondita assegnata solo quando emerge un segnale pertinente. I risultati preliminari non contano verso 50. La fonte editoriale resta fonte, mai cliente per la sola pubblicazione.

Frontiera persistente e coda esecutiva limitata, senza tetto cumulativo a query, candidati o durata. Riempimento progressivo, alternanza fra strategie e lavoro veloce/profondo. Fonti selezionate per titolo, URL, date e contenuto; feed commenti e archivi tassonomici esclusi. Fonti non accessibili conservano il motivo tecnico. Correlazione conserva strategia originaria e prove distinte.

Esperimento di 30 giorni: partenza Veneto, espansione configurabile nelle altre regioni già ammesse; mantenute le esclusioni geografiche esplicite precedenti. Metriche automatiche separate dagli esiti dichiarati manualmente. Nessuna deduzione delle cause delle mancate risposte. Partner separati dai clienti: una collaborazione generica non è una commessa qualificata.

## Accettazione prima della consegna

- Migrazioni ripetibili senza modificare storico o esclusioni; prova su copia e integrità verificata.
- Sitemap con migliaia di pagine non produce migliaia di task esecutivi; nessun articolo scambiato automaticamente per azienda.
- Tutte le strategie esplorate progressivamente, senza una strategia che monopolizzi la coda.
- Nessun modello chiamato per pagine senza segnale; errori tecnici separati dagli scarti.
- Stop invalida i risultati tardivi; ripresa mantiene frontiera e transizioni.
- Filtri, schede preliminari, metriche, feedback e tre voci di navigazione funzionanti su desktop e telefono.
- Pilota nuovo in database separato, fonti reali, copertura e limiti dichiarati, nessuna conversione inventata.

## Correzioni ulteriori dimostrate dal pilota

- Un indice o elenco storico può identificare imprese senza rendere attuale l'evento. Per gli elenchi pubblici nominativi si seguono i link espliciti, si conserva la fonte e si richiede comunque un bisogno attuale indipendente. La soglia temporale della qualificazione non cambia.
- La data di creazione di una homepage non è la data del suo processo operativo. Il filtro preliminare delle date si applica ad articoli e notizie; la qualificazione distingue evento datato e processo corrente osservabile.
- `Document.links` registra se il link proviene dalla navigazione: menu e crediti non diventano nuovi articoli o soggetti aziendali.
- Un nome suggerito dal modello deve esistere letteralmente nel testo. Una citazione errata non viene accettata: se il nome è presente, il contesto viene estratto deterministicamente dalla fonte; altrimenti l'identificazione resta incompleta. Questo non verifica automaticamente il dominio.
- Negli articoli multi-azienda, l'analisi usa l'estratto del soggetto identificato. Il documento originale completo rimane conservato: fatti relativi ad altre imprese non vengono attribuiti al candidato.
- La dichiarazione del titolare nelle pagine ufficiali può correggere uno slogan SEO usato al posto della ragione sociale. I recapiti trovati soltanto in pagine privacy/legal rimangono dati d'identità e non superano da soli il requisito del canale commerciale.
- Le query risolutive conservano soggetto, estratto e metodo di attribuzione; la correlazione non sovrascrive il canale originario.
- Le vecchie code 4.0, se riprese, vengono differite in frontiera mantenendo gli ID dei task; 48 lavori pronti al massimo. La pressione della coda non cancella lo storico e non arresta una campagna per un contatore cumulativo.
- Esiti manuali deduplicati per identità e attribuiti alla prima strategia osservata. Un contatto preliminare con identità verificata aggiorna la memoria commerciale anche prima della creazione di un dossier qualificato. “Non pertinente” evita la rivalutazione dello stesso contenuto senza cambiamenti; “Elimina” resta un'esclusione persistente fino a ripristino.

## Limiti implementativi espliciti

I controlli semantici del modello e le regole testuali non sono una ricerca commerciale perfetta. Gli estratti possono non contenere un bisogno latente; il sistema lo lascia sconosciuto. La discovery ha 11 famiglie di query e una strategia di correlazione, non 12 provider. Il catalogo iniziale è limitato; l'esplorazione di RSS, sitemap e fonti trovate dal motore non equivale a copertura nazionale completa. Le precedenti esclusioni regionali dell'utente rimangono valide.

Per le gare, verifica strutturata conservativa di scadenza, ammissibilità dei professionisti, requisiti e oneri; capitolati non leggibili o clausole non riconosciute restano incompleti. Il lettore PDF non è stato inventato. La rilevanza automatica dei recapiti personali/ruoli resta limitata alle dichiarazioni pubbliche; nessuna email viene costruita da un nome.

La revisione manuale della qualità commerciale rimane necessaria per misurare precisione e falsi negativi. Il sistema propone inferenze documentate; non può dimostrare una propensione all'acquisto non pubblicata.
