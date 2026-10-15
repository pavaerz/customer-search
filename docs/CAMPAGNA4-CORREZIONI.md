# Discovery e verifiche — correzioni del 14 ottobre 2026

## Diagnosi basata sulla campagna 4

La fotografia finale è successiva alla segnalazione dei 141 risultati: contiene 193 URL candidati, 42 ricerche eseguite e 48 task di ricerca registrati, di cui 6 senza una risposta Serper salvata. Nessuna nuova ricerca è stata avviata durante questa correzione. Il processo della campagna avviata dall’utente era rimasto attivo dopo la chiusura del server; è stato messo in pausa prima del collaudo finale.

Le cause riscontrate:

- La query `"Stellantis" sito ufficiale Veneto` ha accettato concessionari e convenzioni. La risoluzione dell’identità non controllava sufficientemente che il risultato appartenesse al soggetto cercato. La fonte principale riguardava investimenti da 60 miliardi, incompatibili con il segmento di piccole imprese.
- Lo stesso articolo ha generato indagini su Dongfeng e Leapmotor, citati come partner. Il motore estendeva la ricerca dalla protagonista alla rete di aziende menzionate.
- `"Aquaopti" sito ufficiale Veneto` ha prodotto prodotti Aqua Optima, marketplace, archive.org e un PDF dell’Archivio Studi Adriatici. La fonte originaria descriveva Aquaopti come una gamma di prodotti Ferroli, non come un’impresa autonoma.
- `"Sigit" sito ufficiale Veneto` ha prodotto pagine del processo tributario SIGIT; `"SIGIT S.p.A."` non avrebbe dovuto essere pianificata nel segmento selezionato. Anche il MIMIT era stato trattato come nome aziendale.
- Alcuni template di articoli non venivano riconosciuti: il testo commerciale comprendeva altre notizie e componenti editoriali. Le pagine originali restano conservate integralmente.
- Il limite di 180 giorni bloccava sia i segnali commerciali sia la scoperta delle identità, anche in RSS. Sono due operazioni diverse.
- Gli errori registrati comprendevano 18 messaggi generici su robots, 2 errori di certificato sullo stesso dominio e 3 timeout sullo stesso PDF storico. I vecchi messaggi robots non conservano lo stato HTTP: non è possibile riclassificarli retroattivamente con certezza.

Nello storico ci sono **20 candidati passati per “promettente”**, ma nessuno rimasto promettente dopo i successivi controlli. Il contatore corrente non misura quante proposte preliminari sono state scartate in seguito. Nessuna opportunità qualificata è stata aggiunta artificialmente.

## Implementazione

### Pertinenza e identità

`sales/discovery_relevance.py` applica controlli di instradamento prima del download e della pianificazione delle ricerche sul nome. Considera nome, URL, titolo, snippet e contesto originale. Gli snippet non diventano prove per qualificare.

Scarta corrispondenze con soggetti differenti, omonimie tributarie, reti di rivenditori scambiate per il dominio della marca, archivi storici e PDF chiaramente estranei. Cataloghi aziendali e capitolati digitali restano leggibili, anche se il nome del file contiene un anno passato. Gli scarti vengono registrati con motivo; non diventano esclusioni commerciali manuali permanenti.

La risoluzione editoriale distingue prodotti, persone, enti, forme S.p.A. e grandi gruppi quando la fonte lo documenta. Quando il titolo identifica la protagonista, non apre automaticamente altre ricerche sulle aziende secondarie. Una piccola impresa fornitrice di un grande gruppo non viene esclusa solo per quella relazione.

Il riconoscimento dei corpi degli articoli include i template osservati nelle pagine salvate e rimuove riquadri esplicitamente marcati come altre notizie. Non usa contenuti nascosti per aggirare paywall. Date di pubblicazione e testo originale sono preservati. Una fonte storica può condurre all’identità; il bisogno deve comunque superare i controlli di attualità e tutte le altre condizioni.

### Accesso, errori e alternative

Gli errori di accesso hanno codici distinti: divieto esplicito robots, robots temporaneamente indisponibile, robots non verificabile, certificato TLS, timeout, pagina riservata e HTTP temporaneo. Una risposta HTML/login al posto di robots non autorizza il download.

Gli errori temporanei mettono in pausa l’origine; il retry del task rispetta tale pausa e `Retry-After`, anche in formato data. Restano al massimo tre tentativi di task; i PDF non superano due tentativi. Una verifica robots non interpretabile è sospesa per 24 ore; un errore di certificato non viene riprovato subito sulle altre pagine dello stesso dominio, con pausa di 6 ore.

La verifica dei certificati e del nome host resta obbligatoria. Il trust store locale contiene 149 CA e usa `/opt/homebrew/etc/openssl@3/cert.pem`. I due errori salvati riportano `unable to get local issuer certificate`: senza una nuova connessione non è possibile stabilire se manchi una CA specifica o se il server presenti una catena incompleta. Non sono stati cambiati certificati, disabilitata TLS o inventata una diagnosi del sito remoto.

Quando esiste un soggetto documentato, un accesso non riuscito può pianificare una sola ricerca alternativa su quel soggetto, escludendo il dominio bloccato. La ricerca alternativa è deduplicata e non genera ricorsivamente altre alternative. Senza identità ancorata a una fonte, il motore non inventa un nome da cercare. Questi lavori partiranno solo quando l’utente riprenderà la campagna.

### Velocità e arresto

Nella fotografia finale, le verifiche approfondite hanno assorbito 2.378,4 secondi, le prime letture 491,2 e le query 61: il collo di bottiglia non era Serper.

- Riferimenti alle prove abbreviati soltanto nel trasporto verso il modello e ricondotti agli ID originali prima della validazione; citazioni e fonti non cambiano.
- Cache compatibile con quella precedente, riutilizzabile quando cambia l’impronta della pagina ma gli estratti e il contesto inviati sono identici.
- Nessuna inferenza per proporre un progetto se tutti i riscontri raccolti sono soltanto descrizioni, budget o strumenti già presenti. Eventi, condizioni, processi, richieste e lacune conservano l’analisi completa.
- Se pagine necessarie risultano tecnicamente inaccessibili, si conservano i documenti raccolti e si rinvia l’analisi locale fino a poter completare l’accesso. Il candidato resta incompleto, non qualificato.
- Tempi del modello, attese, token e riusi della cache registrati nelle misure dei task per le prossime campagne.
- Un controllo indipendente arresta il worker se il server proprietario scompare; coda e risultati restano recuperabili. Il test con un processo proprietario ucciso bruscamente verifica la pausa entro cinque secondi.

Su 119 pagine già salvate, il confronto della serializzazione riduce dati+schema da 669.932 a 621.196 caratteri. Una risposta sintetica con le stesse selezioni passa complessivamente da 44.093 a 32.823 caratteri. **Non è una misura di velocità reale né di qualità del modello.** Il guadagno di durata della prossima campagna rimane da misurare, senza avviare ricerche autonome.

### Percorso verificabile

In **Perché non sto trovando clienti? → Percorso dei risultati**, una vista paginata mostra query, fonte di partenza, informazione cercata, classificazione, decisione, eventuale azienda e qualificazione. Include gli URL esclusi prima del download. API: `GET /api/campaigns/{id}/paths?offset=0&limit=20`.

Le schede nuove riportano il motivo della visita e la query. Lo storico viene ricostruito dai dati disponibili; ciò che le vecchie versioni non hanno registrato rimane indicato come sconosciuto. Un errore tecnico non viene presentato come assenza di bisogno commerciale.

## Confronto e verifica

Replay offline delle **42 risposte Serper salvate**: 239 risultati, inclusi duplicati tra query. Il filtro precedente ne ammetteva 236 alla lettura; quello nuovo ne ammette 145. **91 instradamenti aggiuntivi vengono fermati prima del download**. Questo confronto non simula nuove opportunità e non dimostra conversioni commerciali.

La pagina Industria Italiana esaminata passa da 13.256 a 6.185 caratteri di testo per l’analisi, conservando il testo originale; la pagina Corriere passa da 15.524 a 11.473. I controlli di fonte e identità non sono sostituiti da queste riduzioni.

- **471 test superati**, compresi omonimie, imprese fornitrici di grandi gruppi, PDF pertinenti/estranei, vecchie fonti, robots, certificati, retry, riferimenti inventati, cache, arresto e ripresa.
- Collaudo browser desktop e telefono: percorsi, escaping, filtri, dossier, contatto, eliminazione, pipeline e avvio/stop/ripresa su dati isolati; nessun errore JavaScript. Tutte le navigazioni esterne bloccate nel collaudo.
- Backup iniziale verificato: `data/backups/20261014T124833059329Z/`. Fotografia aggiuntiva dopo la pausa: `data/backups/20261014T125750387579Z/`.
- **59 tabelle confrontate** con la fotografia successiva alla pausa: contenuti identici e integrità SQLite verificata. Credenziali, contatti, esclusioni e storico preservati.
- Nessun limite Serper aggiunto; nessuna ricarica, invio o pubblicazione.

Artefatti: [replay completo](campaign4-corrections.json), [test](tests50-discovery-corrections.txt), [browser](ui50-discovery-corrections.json), [conservazione dati](preservation50-discovery-corrections.json), [trasporto modello](performance50-transport.json).

Per ripetere il confronto senza rete:

```bash
.venv/bin/python scripts/check_campaign4_corrections.py --backup data/backups/20261014T124833059329Z
```

Avvio: `.venv/bin/python app.py`, poi `http://127.0.0.1:8765`. La campagna 4 resta **in pausa**; premere **Riprendi** per usare le correzioni sulla coda conservata. Il contatore dello storico non viene azzerato né reinterpretato come nuovi clienti.
# Correzione aggiuntiva: link Freddo, 14 ottobre 2026

La cache contiene `https://freddo.it/contatti/` con HTTP 200, consultato alle
12:15:22 UTC. Nei due loghi del sito il markup è `<a href="\" class="logo …">`.
La risoluzione Python del riferimento produceva `/contatti/\` invece della
homepage, causando un 404 su un URL diverso dalla pagina contatti. Il controllo
considerava poi questo collegamento una pagina necessaria per via del percorso.

I separatori nei percorsi dei link HTML vengono ora normalizzati prima della
risoluzione relativa. Query, frammenti e percent-encoding restano intatti;
autorità ambigue vengono rifiutate, senza indebolire i controlli di rete.
Replay offline su 11 pagine Freddo in cache: nessun percorso con separatore
inverso residuo. Nessuna nuova richiesta a Freddo o Serper per questo controllo.
Le valutazioni storiche non sono state riscritte e Freddo non è stato promosso.

Durante il controllo è emerso anche un arresto del coordinatore: una fonte
alternativa con `region=None` causava un TypeError nella costruzione dell'ipotesi.
La regione assente resta sconosciuta e non impedisce più di accodare la fonte.
Il server è stato riavviato; la ricerca resta da riprendere manualmente.

Backup verificato: `data/backups/20261014T134612620307Z/`.
Suite finale: **476 test superati**, inclusi risoluzione dei link, ispezione senza
404 artificiale, autorità ambigue e fonte alternativa senza regione.
Log: `docs/tests50-link-resolution.txt`.

# Correzione aggiuntiva: condivisioni social e ricerche alternative

Il 14 ottobre, il ramo originato dall'articolo ViPiù su Fresenius Kabi aveva
generato 5 attività di ricerca e 24 candidati con soggetto WhatsApp al momento
dell'analisi. Il resolver deterministico aveva letto il pulsante di condivisione
come nome aziendale: la parola compariva vicino al testo della nuova linea
produttiva e il nome corrispondeva al dominio `api.whatsapp.com`. Il percorso
rapido dei collegamenti precedeva l'analisi dei protagonisti dell'articolo.

Un secondo difetto amplificava la deviazione: `alternative_source` non veniva
trasmesso dalla query ai risultati. Ogni nuovo errore di accesso poteva quindi
generare un'altra ricerca alternativa con un diverso `-site:`.

Correzioni: riconoscimento dei domini social/messaggistica e dei controlli di
condivisione in entrambe le risoluzioni dei link; esclusione dei nomi di tali
piattaforme anche se suggeriti dal modello; propagazione di `alternative_source`;
deduplicazione transazionale delle ricerche alternative per soggetto e indagine
originale, senza introdurre limiti globali di query o crediti. Le aziende che
usano WhatsApp non vengono escluse per questo motivo.

La campagna è stata messa in pausa. Sono state ritirate 19 righe di lavoro
ancora eseguibili nelle code, senza eliminare lo storico; nessuna attività con
soggetto WhatsApp resta eseguibile. Il server è stato riavviato senza riprendere
la ricerca. Backup verificato: `data/backups/20261014T141221864900Z/`.

Verifica: 481 test nella suite, più due nuovi casi successivi; tutti i 7 test
specifici sono passati (`tests50-discovery-lineage*.txt`). Replay offline della
pagina originale in cache: nessuna estrazione del pulsante come impresa. Per
isolare il resolver, il modello è stato sostituito con una risposta vuota;
questo replay non misura la qualità dell'estrazione AI. Un test separato
verifica che anche una proposta del modello con soggetto WhatsApp sia esclusa.
Nessuna nuova ricerca Serper o richiesta alla fonte durante il collaudo.

# Canali diretti: aziende, agenzie e richieste freelance

Su indicazione di Diego, la discovery clienti non avvia più elenchi di imprese,
RSS o comunicati territoriali. Le strategie attive sono `companies`, `explicit`
e, quando le agenzie sono incluse, `partner`. Restano disponibili le analisi
dei bisogni e dei processi sulle aziende individuate; non cambia la qualifica.
I parser delle vecchie fonti restano per compatibilità e storico, ma non sono
alimentati dall'avvio o dalla ripresa di una campagna clienti.

Query per nomi/settori e domini ufficiali, richieste di fornitori e collaborazioni
frontend/WordPress sostituiscono le query su elenchi e notizie macroeconomiche.
Directory note e portali istituzionali/editoriali vengono esclusi prima della
lettura; un editore non riconosciuto dall'URL viene scartato dopo la lettura
senza ampliare la ricerca alle imprese citate. Le vecchie attività ancora in coda
vengono ritirate con conservazione dello storico. Le fonti dei bandi non sono
state modificate.

LinkedIn: le query Google tramite Serper possono trovare singoli post e annunci
con richiesta esplicita di competenze web e freelance/partita IVA. Risultati
dipendenti, profili, autopromozione e piccoli interventi riconoscibili sono esclusi.
LinkedIn rimane bloccato al crawler: nessuna automazione di login o aggiramento.
Titolo e snippet sono salvati come `search_hint`, esplicitamente non verificato,
senza creare documenti probatori o qualificare opportunità. Quando il titolo
attribuisce il post/annuncio a un nome, si accoda la ricerca del sito ufficiale:
identità, località, attualità, ambito e domanda richiedono riscontri originali.
Se l'attribuzione manca, la segnalazione resta da approfondire. Non viene
garantita la verifica automatica di un annuncio accessibile soltanto su LinkedIn.

Campagna 4: gruppi aggiornati a clienti diretti e agenzie come richiesto; Veneto,
servizio e soglie conservati. Ritirate 14 righe delle code dei precedenti percorsi.
La campagna resta in pausa; nessuna nuova ricerca o richiesta Serper avviata.
Backup completo verificato: `data/backups/20261014T142256040532Z/` (il primo
tentativo durante la ricerca attiva non aveva superato il confronto conteggi;
il backup valido è stato rifatto dopo la pausa, prima delle modifiche).

Collaudo: 491 test superati, inclusi otto casi sui nuovi canali. Le aspettative
dei test dei vecchi feed sono state aggiornate per verificarne l'esclusione dalla
discovery clienti. Report: `tests50-direct-channels.txt`; collaudo browser con
database isolato: `ui50-direct-channels.json`. Nessun risultato commerciale o
incremento di conversione è stato misurato con questa modifica.

## Coerenza dei conteggi — campagna 5, 14 ottobre 2026

Il riepilogo riportava sei pagine promettenti mentre l'elenco mostrava una sola
azienda ammissibile: tre pagine di Fusion Work, due di Digitalia e una di
Metaltech. Le prime cinque non superavano il filtro delle schede aziendali.
Le categorie mostravano invece i soli risultati qualificati (zero), anche
quando era selezionata la fase dei candidati promettenti.

Riepilogo ed elenco ora condividono la selezione e la deduplicazione aziendale.
I conteggi delle categorie seguono fase, campagna e filtri, indipendentemente
dalla paginazione. Cambiare categoria o aggiornare lo stato non ripristina la
fase qualificati. URL scoperti/scartati sono etichettati come URL, distinti
dalle aziende. Stop conserva l'ultimo esito approfondito salvato: una verifica
incompleta non viene trasformata in un candidato promettente.

Sui dati della campagna 5 sospesa: 142 URL, sette aziende identificate, una
promettente e zero qualificate. Nessun dato commerciale cancellato o promosso.
Backup verificato prima delle modifiche: `data/backups/20261014T161155549946Z/`.
Validazione: 496 test superati (`tests50-counts.txt`) e collaudo browser desktop
e mobile, compresi conteggi, cambio categoria e aggiornamenti periodici
(`ui50-counts.json`), su database isolato. Nessuna ricerca Serper avviata.

