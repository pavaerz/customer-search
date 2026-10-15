# CustomerSearch 5.0 — lavoro in corso

## Audit del 14 ottobre 2026

Backup verificato prima delle modifiche: `data/backups/20261014T071804567249Z/` (integrità SQLite, archivio e hash nel manifest).

Percorso attuale: `Planner` → `discovery_frontier` → `research_tasks` → Serper → `acquisition_exclusion` → `triage` → identificazione/risoluzione editore → `inspect_candidate` → citazioni locali → `qualify` → valutazioni e CRM. Worker separato, generazione della campagna e coda persistente proteggono Stop/Riprendi; queste protezioni restano.

Evidenze iniziali:

- La campagna 3 è bloccata dal vecchio limite Serper, non dall'esaurimento del mercato. Configurazione: 30/giorno, 930/mese.
- `selected_strategies` consente soltanto `companies` ai clienti diretti; `apply_scope` ritira gli altri rami e tutte le fonti pubbliche.
- `excluded_url` scarta interi domini editoriali, anche articoli su aziende identificabili. Questo impedisce l'estrazione del soggetto già implementata in `resolve_publisher`.
- Le query aziendali cercano contatti per settore e provincia, non un'ipotesi commerciale. La verifica successiva cerca novità soltanto nel dominio già identificato.
- `research_tasks` e `company_verification` perdono i documenti editoriali del candidato risolto, sostituendoli con le sole pagine ufficiali; così si può perdere il fatto che motivava la ricerca.
- Il modello locale richiede citazioni letterali: alcuni piloti precedenti sono incompleti per citazioni invalide. Non è lecito risolverlo promuovendo risultati senza prove.
- Storico complessivo: 48 indici editoriali, 39 pagine datate, 34 pagine senza segnali pertinenti, 29 gare senza progetto digitale e 22 notizie su strumenti finanziari senza beneficiari tra le ragioni più frequenti. Sono conteggi di pagine, non aziende o precisione.

## Decisioni

1. Riabilitare percorsi mirati verso notizie economiche e portali di settore, distinguendo fonti, protagonisti e clienti. Homepage editoriali, forum e bandi generici restano esclusi.
2. Pianificare query con ipotesi, servizio, prove necessarie e controprove salvate nel lavoro. Nessuna ipotesi assegna automaticamente una qualifica.
3. Rimuovere i tetti obbligatori Serper; limiti volontari opzionali, zero come blocco esplicito. Saldo remoto sconosciuto distinto dalle richieste locali.
4. Conservare e collegare le prove originali attraverso la risoluzione del dominio, senza accettare un'omonimia come identità verificata.
5. Separare regressioni sintetiche, replay storico e pilota nuovo. Nessuna dichiarazione di efficacia commerciale senza dati reali.

## Consegna ancora da verificare

Il documento è un registro di avanzamento, non una dichiarazione di completamento. Restano da collaudare confronto prima/dopo su campioni separati, pilota reale, copertura degli intenti, metriche di revisione, interfaccia, ripresa della campagna e precisione commerciale. Nessuna email o acquisto automatico.

## Implementazione e verifiche di questo passaggio

- `CommercialIntelligencePlanner` conserva ipotesi, territorio, servizio, prove necessarie e controprove in ogni query; `Planner` resta un alias compatibile. Per i clienti diretti vengono riaperti i percorsi cambiamenti, nuove iniziative e domanda esplicita; e-commerce aggiunge investimenti/assunzioni, web app aggiunge processi. Query su portali mirati e feed configurati sono fonti, mai clienti automatici.
- Rimossi i default obbligatori 30/930 con migrazione 50 ripetibile. Limiti personalizzati preservati. Campo vuoto nell'interfaccia salva `null`, zero mantiene un blocco volontario. Le richieste sono serializzate fra processi, con attesa cancellabile e cache equivalente; errori di chiave/credito bloccano senza acquisti o fallback.
- Prove editoriali conservate nel passaggio all'impresa, dopo controllo del nome e della coerenza territoriale. Nuove prove originali cambiano la chiave della verifica, evitando che una vecchia indagine impedisca di esaminare un nuovo evento.
- Nomi legali e soggetti strutturati possono essere estratti senza modello, ma restano da verificare sul dominio. Ruoli editoriali e istituzionali non attribuiti sulla sola presenza di «Comune di» nell'indirizzo.
- Stato Serper, richieste locali totali e della campagna, saldo dichiarato sconosciuto, ipotesi attiva e diagnostica «Perché non sto trovando clienti?» disponibili nell'interfaccia.

### Test

`python -m unittest discover -s tests`: **319 test superati** (usare `.venv/bin/python`). `scripts/check_research_ui.py`: desktop/mobile, filtri, dossier/revisione, conferma contatto e verde, eliminazione, avvio/Stop/Riprendi, drag and drop e salvataggio dei limiti facoltativi: superati, nessun errore JavaScript. Sintassi JS e compilazione Python controllate.

App avviata su `http://127.0.0.1:8765`; stato verificato via API: Serper attivo, chiave presente, nessun tetto locale, campagna non in esecuzione. Nessuna ripartenza nascosta. SearXNG non riattivato. Confronto integrale delle righe di sette tabelle commerciali con il backup: nessuna modifica (`preservation50.json`).

### Confronto e pilota: risultati non sufficienti per dichiarare successo

1. Regressioni di sviluppo su originali storici: Elle Meccanica e Lavorazione Lamiera non vengono più scambiate per editori. Officine Dall’Alba, nella pagina scelta, non riproduceva il problema: non conteggiata come correzione (`regression50-source-roles.json`).
2. Campione separato congelato: 20 domini selezionati tramite hash da 143 domini storici con HTML disponibile, escludendo i cinque domini di sviluppo. Il confronto riguarda SOLO il riconoscimento dell'editore, non l'intera selezione: 0 imprese erroneamente classificate come editori sia prima sia dopo; fonti pubbliche riconosciute **3 prima, 2 dopo**. Il riconoscimento di blog/enti non ancora coperti è quindi un limite da affrontare; questo campione NON dimostra un aumento di precisione (`benchmark50-roles.json`). Etichette revisionate dall'assistente, non da un revisore umano indipendente.
3. Pilota reale controllato: 3 richieste Serper addebitabili conteggiate nel registro reale, 9 pagine campionate, 7 pagine acquisite, nessuna impresa verificata nel segmento in questa passata preliminare. Nessuna qualificazione approfondita eseguita: `qualified=null`, non un tasso di qualifica pari a zero. Cinque errori nel protocollo iniziale, di cui due erano social già esclusi dalla pipeline reale: lo script del pilota è stato allineato al prefiltro della produzione. Gli altri includono timeout, robots non verificabile e connessione interrotta. Non sono scarti commerciali (`pilot50-latest.json`).
4. La revisione del pilota ha scoperto 6 collegamenti a calendari erroneamente estratti da CNA Padova come possibili aziende. Correzione verificata sulle stesse pagine, senza nuove API: **6 → 0**; nessuna azienda inventata. È una regressione sul campione di sviluppo, non una misura indipendente di efficacia (`pilot50-calendar-replay.json`). Un nome estratto dalla notizia su SMACT resta soltanto da verificare, non un cliente qualificato.

Per ripetere il confronto del classificatore: `.venv/bin/python scripts/benchmark50_roles.py`. I due campioni sono in `data/benchmarks50/`. Il pilota è ripetibile con `.venv/bin/python scripts/pilot50.py`: tre query, usando i crediti Serper effettivi quando non in cache. Questo limite riguarda il collaudo, non la ricerca nell'app.

## Audit di completamento: obiettivo ancora attivo

| Requisiti del testo 5.0 | Stato ed evidenza / lavoro restante |
|---|---|
| 1–2, audit e obiettivo commerciale | Audit documentato; campione reale insufficiente per dimostrare opportunità utili. |
| 3, Serper | Limiti facoltativi, consumo, cache, errori e stato collaudati. Saldo remoto non disponibile. |
| 4–6, planner, strategie e query | Contratti di ipotesi implementati. Generazione ancora basata su formulazioni controllate; validare produttività per servizio e territorio, ricerca di nuove fonti e copertura di tutti gli intenti. |
| 7–8, filtraggio ed entità | Correzioni e regressioni verificate; restano blog/enti non riconosciuti e qualità dei nomi estratti da portali. Non tutte le entità sono risolvibili. |
| 9, ciclo autonomo | Coda, rotazione, paginazione condizionata, Stop/Riprendi mantenuti. Occorre collaudo reale prolungato della nuova frontiera. |
| 10–11, analisi e qualificazione | Regole severe preservate; nessun campione nuovo sufficiente di verifiche approfondite. Ridurre errori di estrazione locale senza accettare citazioni inventate. |
| 12–13, risorse e metriche | Contatori e rapporti per 100 query disponibili. Precision@10/20 rimane null: serve un campione ordinato revisionato. Nessuna previsione inventata. |
| 14, interfaccia | Nuovi dati e limiti verificati nel browser desktop/mobile. |
| 15, confronto | Replay ristretto su campione separato eseguito e limiti riportati. Manca benchmark completo di identità, qualificazione, duplicati e costo su nuovo campione indipendente. |
| 16, implementazione e preservazione | Backup, test, UI, app avviata e confronto dello storico verificati. |
| 17, risultato finale | Non dimostrato: non ci sono ancora dati sufficienti su opportunità utili, conversazioni, preventivi e clienti. |

Prossima azione: approfondire la classificazione delle fonti senza riaprire gli indici generici, risolvere e verificare imprese reali da elenchi affidabili e comunicati specifici; collaudare su un nuovo campione distinto da quelli usati per le correzioni. Non acquistare altri servizi e non abbassare i requisiti per riempire i risultati.

## Secondo passaggio del 14 ottobre: portali, attribuzione e prove

Backup successivi verificati: `data/backups/20261014T073333456182Z/` e `data/backups/20261014T075536675688Z/`. Gli archivi contengono codice e configurazioni; snapshot SQLite, conteggi, integrità e hash sono nei manifest privati.

### Correzioni basate sui casi osservati

- Sei nuove ricerche esplorative hanno mostrato che formulazioni su nuovi marchi/prodotti riportano ancora grandi marchi e articoli generici. Gli elenchi settoriali sono una via complementare per identificare imprese, non una prova di bisogno (`data/pilot50-next/search.json`).
- Aggiunti sei elenchi pubblici verificati, su tre portali: MeccanicaNetwork nelle quattro regioni prioritarie, Confindustria Vicenza alimentari e Italmopa Veneto. Si attivano soltanto per territorio e segmento selezionati. Le tre nuove pagine regionali hanno restituito 24, 24 e 23 profili rispettivamente in Lombardia, Piemonte e Toscana: sono profili da verificare, NON opportunità (`data/pilot50-next/regional-directories.json`). Accesso, robots e condizioni sono ricontrollati dal lettore normale.
- Profili con collegamenti solo sulle immagini vengono riconosciuti se nome visibile, dati strutturati e URL effettivo concordano. Le voci interne «azienda/storia» non trasformano un produttore in una directory. Nei portali i profili aziendali hanno priorità sui collegamenti all'editore; nomi S.p.A. esclusi. Eliminata la troncatura a tre nomi per elenco: il lavoro passa nella coda persistente.
- Una ricerca esatta senza identità risolta può provare il nome commerciale senza suffisso societario. L'identità completa e la fonte rimangono obbligatorie. Nessun nuovo tentativo per sole letture fallite, nessuna ripetizione dell'alternativa e nessuna ricerca dopo Stop. Due query di sviluppo hanno recuperato i siti di Alessandrin e Newpharm (`data/pilot50-next/identity-alternatives.json`); gli snippet non verificano il dominio.
- Il planner attende i lavori di identificazione discendenti da una fonte prima di giudicarla improduttiva. `root_query_key` conserva il legame anche attraverso profili, ricerche del nome e indagini sul sito. Una fonte può risultare produttiva per aver identificato un'impresa, senza attribuirle una qualifica. Regressione riproducibile: prima il ramo avanzava prematuramente; dopo attende la risoluzione. Una società trovata da un'altra query non dà credito alla fonte sbagliata.
- Il modello sceglie ID di estratti realmente presenti: il programma ricostruisce le citazioni, controllando gli offset. Non può aggiungere una frase inventata come prova. Controlli semantici separati correggono richieste, processi e lacune erroneamente attribuiti a slogan o lavorazioni industriali; le citazioni restano conservate come contesto aziendale.
- Corretta l'identità con CAP alla fine della riga e comune/provincia immediatamente sotto; riconosciuta la dicitura combinata «P.iva/Cod. Fisc.» e le email del dominio pubblicate come testo. Un indirizzo successivo non correlato non viene aggiunto, né vengono presi i contatti del fornitore del sito.
- Abilitato anche nella ricerca commerciale il lettore PDF testuale già usato per i bandi: limite 8 MB/80 pagine/300.000 caratteri, controlli di rete e robots invariati. L'HTML conserva il limite di 1,5 MB. Scansioni senza testo, cifratura e limiti superati restano verifiche incomplete. La politica aziendale PDF di Alessandrin era prima un errore «Contenuto non testuale»: viene ora letta senza saltarla.

### Risultati misurati e limiti

Il pilota iniziale degli elenchi ha esaminato sei soggetti da tre fonti, con sei richieste Serper, 11 pagine preliminari, due imprese verificate (Almas e Molino Rachello) e una verifica commerciale completa (Almas): **zero qualificati**. AR Costruzioni Meccaniche è stata poi recuperata sullo stesso campione correggendo il falso riconoscimento di directory. Questo è sviluppo, non valutazione indipendente (`pilot50-directory-latest.json`, `directory50-recheck.json`). Il campionamento dello script è stato allineato all'ordinamento della produzione dopo la prova iniziale; non si attribuisce retroattivamente quel miglioramento ai risultati del pilota.

Il replay dei nomi alternativi (`pilot50-identity-recovery.json`) usa le due query già salvate: nessuna nuova richiesta API. Alessandrin viene verificata come impresa; Newpharm richiede la correzione dell'indirizzo e dei dati societari. Gli esiti successivi alla correzione sono conservati separatamente in `pilot50-identity-recheck.json`, senza sovrascrivere il risultato precedente.

Il secondo replay è completato: **entrambe le identità verificate, due indagini commerciali complete, zero qualificati**. Alessandrin passa da `unverifiable` a `needs_review` grazie alla lettura del PDF; Newpharm passa da identità sconosciuta a verificata grazie a indirizzo e dati societari. Nessuno dei due siti offre ancora prove sufficienti per un progetto completo. Un ulteriore controllo sulla risposta `project=none` elimina gli elenchi di incognite su software mai proposti: stessi esiti commerciali, zero requisiti tecnici inventati nei due replay in cache (`pilot50-no-project-recheck.json`). Non si spendono inferenze per revisionare una proposta assente; eventuali vere limitazioni di lettura restano registrate.

Benchmark separato sul significato di 20 citazioni storiche, congelate per hash prima del confronto ed escludendo i casi di sviluppo Almas/Picello/Stox (`benchmark50-grounding.json`): **19 etichette di bisogno/processo/richiesta prive di supporto prima, zero dopo**. L'unico processo supportato resta riconosciuto. È un controllo delle etichette, non precision@20 delle aziende e non una misura di opportunità acquisite. Il campione ha un solo caso positivo ed è stato revisionato dall'assistente: non dimostra capacità di recuperare tutti i bisogni reali. Ripetibile con `.venv/bin/python scripts/benchmark50_grounding.py`.

Resta aperto il problema commerciale più importante: gli elenchi migliorano l'identificazione, ma molte imprese identificate non presentano ancora una ragione documentata per un progetto completo. La classificazione delle lacune è prudente e basata su dichiarazioni letterali: il collegamento tra un evento e una discrepanza digitale osservata, senza dichiarazione esplicita del bisogno, richiede ancora un percorso di verifica più efficace. Non si può sostituirlo con deduzioni dall'assenza di informazioni. Occorre un nuovo campione indipendente di indagini complete, con controprove, prima di dichiarare raggiunto l'obiettivo 5.0. Nessuna modifica delle soglie per riempire la shortlist.

### Collaudo e preservazione del secondo passaggio

Il report aggiornato è `validation50-current.json`. Il collaudo browser su database isolato passa desktop/mobile, filtri, dossier, revisione, conferma contatto/verde, eliminazione, Avvia/Stop/Riprendi, pipeline trascinabile e salvataggio delle impostazioni; nessun errore JavaScript. La suite completa include ora i nuovi casi di attribuzione dei portali, indirizzi multilinea, PDF e assenza di requisiti senza progetto.

Confrontate integralmente **38 tabelle**, comprese campagne e dati commerciali, con il backup delle 07:55 UTC: tutte identiche, integrità SQLite `ok` (`preservation50-current.json`). Cache e dati di servizio esclusi dal confronto sono distinti nel relativo script di verifica; i piloti commerciali usano copie isolate. Server riavviato, HTTP 200 su `/api/state`, provider Serper, nessuna ripartenza della campagna. L'obiettivo 5.0 resta aperto.

## Terzo passaggio: indagine guidata dall'evento

Backup verificato prima delle modifiche: `data/backups/20261014T081046277239Z/`.

L'indagine sull'impresa identificata usava sempre tre query generiche. Inoltre, passando alle pagine successive, sostituiva le fonti editoriali originali con la sola descrizione aziendale. Ora `company_investigation.plan` produce domande e controlli contrari a partire da citazioni originali, riferite alla società verificata e pubblicate negli ultimi 180 giorni. Le query cercano l'offerta, il marchio o il mercato effettivamente citati. Date sconosciute/future, vecchie notizie, omonimi e fonti non attribuite non creano un piano riferito all'azienda. È una priorità di indagine, mai un punteggio o un bisogno automaticamente attribuito.

I documenti originali rimangono collegati ai lavori successivi. Si approfondisce prima il fatto più recente di ciascuna famiglia commerciale, evitando query equivalenti su ogni articolo dello stesso archivio. Se la fonte collega già la pagina dell'offerta citata, quella pagina viene letta direttamente e la query per ritrovarla non viene eseguita; rimane la ricerca di controprove. Il dossier mostra domande, citazione, data e fonte dentro «Ipotesi da verificare a partire dalle fonti», con etichetta esplicita di ipotesi.

Corretto anche un errore di selezione delle pagine: prima venivano valutate quasi esclusivamente le parole nell'URL, perdendo la funzione descritta dal testo del collegamento. Ora «Prodotti Essentials» viene letto anche se il percorso è soltanto `/essentials/`. I collegamenti all'offerta nominata nella fonte hanno precedenza; i collegamenti esterni continuano a passare dal lettore protetto e dalla verifica delle soluzioni esistenti.

### Prova reale e risultati

Quattro query Serper, quattro richieste registrate, tre fonti originali lette (`pilot50-events-review.json`):

- Remor, annuncio del 24 settembre 2026 su Remor Essentials: identità S.r.l., dominio e sede in Veneto verificati. L'annuncio contiene già collegamenti alla pagina dedicata e al catalogo. Questa presenza è una controprova da leggere prima di proporre un nuovo sito.
- Cuoieria Fiorentina: articolo del 17 febbraio 2026, oltre la finestra di 180 giorni; la fonte descrive anche un negozio online e una rete distributiva già esistenti. Non è un nuovo cliente qualificato.
- PiemonteIS: marchio collettivo regionale, senza un committente privato identificato per un progetto digitale. Non va trasformato nell'impresa da contattare.

Replay di sviluppo su Remor: **tre query generiche prima, una query di controprove dopo**, più lettura diretta della pagina già collegata (`regression50-event-plan.json`). È un confronto del lavoro pianificato sul medesimo caso, non un aumento dimostrato di precisione. La verifica approfondita usa otto pagine e nessuna nuova ricerca API. I dati del pilota restano in una copia privata del database, senza inserimenti nel CRM reale.

La prova ha evidenziato due problemi ulteriori. La pulizia dei banner poteva far unire blocchi non contigui nell'originale, causando errori di citazione anche quando il modello selezionava soltanto ID esistenti. `grounded_units` ora ricostruisce frammenti contigui senza cambiare il controllo sulle citazioni: **8 unità non riscontrabili prima, zero dopo**, sulle otto pagine del caso di sviluppo (`regression50-literal-spans.json`). Non è una misura di qualità commerciale.

Il secondo problema era il limite di 24 riscontri applicato indiscriminatamente anche a molte descrizioni generiche dell'attività. Ora la correlazione conserva tutte le richieste, lacune, controprove, rischi e indicazioni economiche; per il solo contesto descrittivo usa un estratto per documento. Anche una citazione classificata dal modello come semplice attività resta integrale se menziona strumenti digitali, progetto, fornitore selezionato, rischi o budget. Tutte le citazioni rimangono nel dossier e la selezione del contesto è registrata. Se le prove decisionali superano la capacità del modello, resta uno stato incompleto esplicito: nessun taglio silenzioso che consenta una qualifica.

Il confronto della valutazione commerciale aggiornata viene salvato separatamente in `pilot50-event-recheck.json` ed è ripetibile con `.venv/bin/python scripts/replay50_event.py`. Non usa Serper e non modifica il CRM; può chiamare il modello locale se manca una risposta in cache. Campione di sviluppo, non valutazione indipendente.

Replay concluso: Remor passa da `unverifiable` a `needs_review`, con **zero limitazioni tecniche**, mantenendo tutte le 11 prove decisionali nel contesto. Undici descrizioni generiche aggiuntive restano nel dossier e non sono ripetute nell'input di correlazione. L'analisi non documenta un progetto completo proponibile: **zero nuovi qualificati**. Il miglioramento dimostrato riguarda l'eliminazione di errori interni di analisi, non la capacità di acquisire clienti.

### Verifiche e limiti ancora aperti

**355 test superati**, browser desktop/mobile superato, compreso il nuovo riquadro e l'escaping delle citazioni. La suite segnala ancora un `ResourceWarning` SQLite, conservato nel log, senza test falliti. `preservation50-events.json`: 37 tabelle commerciali/configurazione/campagne identiche al backup e integrità `ok`. Il registro `api_usage` è escluso esplicitamente dal confronto delle tabelle immutate perché deve registrare le quattro richieste reali del pilota.

Server locale riavviato dopo il collaudo, nessun avvio automatico della campagna; la configurazione rimane Serper senza tetti locali obbligatori. Log e metadati: `tests50-events.txt`, `validation50-events.json`.

La nuova indagine migliora raccolta e continuità delle prove e impedisce di saltare una soluzione già pubblicata. **Non dimostra ancora un aumento delle opportunità qualificate né dell'acquisizione clienti.** Restano da verificare la produttività su un campione indipendente, il collegamento tra eventi e lacune effettivamente osservate senza annunci espliciti e l'adattamento della ricerca in campagne prolungate. L'obiettivo completo resta attivo.

## Quarto passaggio: usare gli esiti commerciali, senza memorizzare errori come rifiuti

Backup verificato: `data/backups/20261014T083536879012Z/`. Nessuna modifica a soglie, servizi, credenziali o criteri di promozione.

Problemi riscontrati nel codice e nel dossier Remor:

- Il modello concludeva `project=none`, ma l'azienda restava `needs_review` e la prossima azione chiedeva di completare verifiche senza indicare una concreta indagine residua. Ora il rifiuto commerciale è registrato soltanto dopo una correlazione esplicitamente conclusa senza progetto, identità verificata, copertura di identità/offerta/contatto/soluzioni, almeno due URL ufficiali distinti e nessuna limitazione. Il motivo riguarda le **fonti esaminate**, non afferma che l'azienda non abbia alcun bisogno. Estrazione vuota o pagine mancanti non bastano più a scartare automaticamente.
- Il planner riconosceva `company_ready` anche dopo uno scarto approfondito. Ora attende le verifiche già accodate, conta ogni impresa verificata una volta e usa la valutazione finale più recente al posto dei vecchi indicatori preliminari. Un esito negativo fa cambiare formulazione invece di guadagnare paginazione. Un editore risolto non trasforma un errore tecnico dell'azienda in uno scarto commerciale.
- La memoria inter-campagna bloccava una verifica riuscita se le citazioni erano le stesse di una precedente verifica incompleta. Ora la soppressione per prove immutate richiede esiti commerciali definitivi e analisi completate. Una verifica HTTP riparata o una copertura completata possono quindi qualificare le stesse prove. Rimangono le esclusioni manuali, i contatti già gestiti e la protezione dalle riproposizioni di risultati definitivi.

### Confronto riproducibile e verifica

`.venv/bin/python scripts/replay50_commercial_feedback.py data/backups/20261014T083536879012Z` confronta il codice conservato nel backup con quello aggiornato sulle otto pagine già acquisite per Remor. Le chiamate HTTP del modello sono esplicitamente bloccate: vengono usate le risposte in cache. Nessun credito Serper, nessun dato commerciale di produzione modificato. Report: `regression50-commercial-feedback.json`.

Esito: `needs_review` → `rejected`, con motivazione limitata alle fonti lette e prossima azione «passare ad altre aziende; rivalutare con nuovi elementi». Stesse 30 citazioni conservate, budget sconosciuto, nessuna limitazione tecnica e **zero qualificati in entrambi i casi**. È una regressione di sviluppo sullo stesso caso; non una misura indipendente della precisione o del recupero di opportunità.

Suite completa: **362 test superati** (`tests50-commercial-feedback.txt`). Il controllo successivo della memoria, con fixture di copertura effettivamente incompleta anziché stato assegnato a mano, passa tutti i 37 test del relativo modulo (`tests50-feedback-persistence.txt`). I nuovi casi verificano attesa della revisione, cambio di query, un'impresa con otto URL, distinzione fra errori tecnici e scarti, lettura parziale, estrazione vuota e ripresa fra campagne. Il ResourceWarning SQLite già noto rimane nel log completo.

Confronto integrale con il backup prima del riavvio: **47 tabelle identiche, nessuna tabella esclusa, integrità SQLite `ok`** (`preservation50-commercial-feedback.json`). Non sono stati aggiornati retroattivamente i dossier commerciali dell'utente. Il miglioramento è attivo nelle nuove verifiche.

Rimane aperto il lavoro principale sulla qualità: costruire e verificare collegamenti fra eventi e discrepanze digitali osservabili, senza dipendere soltanto da carenze dichiarate esplicitamente; collaudare poi su nuove aziende con un campione indipendente. Queste correzioni evitano sprechi e scarti impropri, ma non dimostrano ancora un aumento dei potenziali clienti utili. Obiettivo 5.0 ancora attivo.

## Quinto passaggio: confronto dei fatti e nuova prova su Google

Backup verificato prima delle modifiche: `data/backups/20261014T084739450038Z/`. Non sono cambiati soglia 70, requisiti economici, esclusioni, invii o servizi a pagamento.

### Percorso per un bisogno inferito

Rimosso dall'analisi il ritorno anticipato che impediva la correlazione quando non erano presenti una richiesta, una carenza dichiarata o un processo. Il modello deve valutare anche una combinazione di fatti aziendali e soluzioni esistenti; ciò può concludersi con nessun progetto.

Primo percorso verificabile in `commercial_inference.py`: evento recente attribuito all'impresa + condizione dichiarata del canale riferita al pubblico, per esempio catalogo riservato ai rivenditori rispetto a un nuovo pubblico privato. La condizione rimane un fatto neutro, non viene rinominata «problema». Per qualificare il collegamento servono due citazioni distinte, riferimenti nella proposta e nella revisione, attualità, fonti originali attribuite correttamente, motivazione del progetto completo e valutazione esplicita delle alternative minori. Il revisore può dichiarare il collegamento non dimostrato. Email/Excel, lingua, recesso, catalogo generico o slogan non attivano questo percorso. Tutti gli altri requisiti continuano ad applicarsi; budget sconosciuto rimane sconosciuto.

Il dossier mostra «Come abbiamo collegato i fatti», le citazioni, il nesso proposto, perché un progetto completo e quali alternative minori sono state valutate. L'etichetta dichiara che si tratta di inferenza commerciale, non richiesta o intenzione di acquisto. Questo è un percorso circoscritto: non risolve qualsiasi bisogno implicito né autorizza deduzioni dall'assenza di contenuti.

La lettura non salta più pagine di prodotto/marchio perché prive di parole come «web» o «problema». Le offerte aziendali diventano contesto, non richieste al freelance; gli estratti devono privilegiare eventi, condizioni e controprove rispetto agli slogan. Gli eventi letterali già riconosciuti dal piano rimangono fra le prove anche quando il modello li omette. Le pagine di marchi esterni collegate esplicitamente dall'impresa sono lette come soluzioni da controllare, senza attribuirne automaticamente proprietà o adeguatezza.

### Ricerca reale, fonti e scarti

**10 richieste Serper e 18 pagine originali raccolte**, con database isolato per le verifiche. Due query sono state confrontate prima/dopo escludendo Facebook, Instagram, LinkedIn e YouTube, già non consultabili dalla policy dell'app: **10 risultati su 20 esclusi per accesso prima; zero su 20 dopo**. Non significa che i venti risultati siano clienti pertinenti. Le esclusioni vengono salvate nella query effettiva e sono visibili; ricerche di identità e per dominio restano specifiche. Tra i nuovi risultati sono emersi Mital e AG Metal.

Revisione delle fonti del campione:

- Restel/Tomezzoli: storia PSR del 2022 e investimento in macchinari. Non è un evento attuale né un budget per il sito.
- SCF Flooring&Furniture: annuncio del luglio 2025. Non dimostra un bisogno digitale tempestivo.
- Castel/EVIC: annuncio che descrive un lancio del novembre 2025, pagina pubblicata a gennaio 2026. Anche qui nessun nuovo progetto qualificato.
- Pegaso: acquisto tramite modulo Excel/email; la procedura non dimostra da sola inefficienza o necessità di rifacimento. Non promosso sulla base dello snippet.
- Vitevis, fonte WineCouture: investimento in imbottigliamento e automazione produttiva. Non confuso con una commessa software o sito web.
- **Mital Srl, Veneto**: identità e canali commerciali verificati; offerta e catalogo letti. Il modello ha ipotizzato un sito sulla base del rinnovo dell'identità visiva, ma il revisore ha segnalato l'assenza di un bisogno digitale documentato. Stato `needs_review`, priorità 10, non qualificato.
- **AG Metal, Lazio**: identità verificata e intervista dell'8 ottobre 2026; controllato anche il sito collegato `agmetaldesign.it`. La nuova offerta dispone già di una presenza dedicata; il lancio originale risale inoltre ad agosto 2025. Esito finale `rejected`, nessun progetto completo giustificato dalle fonti lette.

Due difetti trovati durante la prova sono stati corretti: la provincia prima del CAP ora è riconosciuta (Civita Castellana VT 01033); gli indirizzi esplicitamente attribuiti all'organizzazione prevalgono sugli indirizzi non attribuiti nella privacy, evitando che la sede del Garante a Roma cancelli la sede di Mital in Veneto. Indirizzi propri discordanti continuano a richiedere verifica. La data `time itemprop=datePublished` dell'articolo è riconosciuta anche quando sono presenti date degli articoli correlati; non viene trasformata nella data certa dell'evento.

Report: `pilot50-inference.json`. Il primo esito completo e le pagine sono conservati in `data/pilot50-next/implicit/`; `replay50_implicit.py` rivaluta solo le pagine congelate, senza Serper e senza letture web, usando il modello locale. `report50_implicit.py` ricostruisce contatori, confronto delle query e hash. Campione di sviluppo, rivisto dall'assistente: **zero qualificati, precision@20 non misurabile**, nessun risultato immesso nel CRM reale e nessun contatto inviato.

### Collaudo e limiti

**375 test superati** (`tests50-inference.txt`), più il controllo finale del modulo dopo la normalizzazione dei nomi nelle fonti editoriali (`tests50-inference-final.txt`). Browser desktop/mobile superato: pannello inferenze, citazioni, escaping, filtri, contatto verde, eliminazione, pipeline, Avvia/Stop/Riprendi e impostazioni (`browser50-inference.txt`). Il ResourceWarning SQLite già noto resta nel log della suite.

Il confronto con il codice del backup su una fixture controllata senza richiesta esplicita passa da `needs_review` a `qualified` (`regression50-inference-contract.json`). È una verifica del nuovo percorso di codice con una revisione simulata, **non una nuova azienda trovata né un benchmark di precisione**. L'integrazione con il modello locale reale è registrata separatamente in `model50-inference-integration.json`, sempre su esempio fittizio: Qwen estrae evento e condizione e produce la revisione strutturata senza errori tecnici, ma lascia `needs_review`, con ambito e fattibilità sconosciuti e collegamento non stabilito. Non dimostra quindi una promozione riuscita con il modello reale.

Preservazione: **44 tabelle immutate**, integrità SQLite `ok`; cache, registro di consumo (+10 richieste) e stato operativo Serper sono distinti esplicitamente (`preservation50-inference.json`). Il confronto iniziale che rilevava anche l'aggiornamento dello stato provider è conservato in `preservation50-inference-all.json`. Nessuna modifica retroattiva ai dossier o allo storico dell'utente.

Il progresso dimostrato riguarda fonti consultabili, riconoscimento dell'impresa, lettura delle controprove e disponibilità del percorso di inferenza. **Manca ancora la validazione su casi reali positivi e su un campione indipendente sufficiente.** Non è dimostrata efficacia nell'acquisire clienti e l'obiettivo complessivo rimane incompleto.

## Sesto passaggio: fonti territoriali, articoli e contesto aziendale

Backup verificato: `data/backups/20261014T092322909810Z/`. Il passaggio precedente costituisce progresso: codice, verifiche e dati del pilota sono cambiati; nessun processo precedente è stato rilanciato per un semplice timeout di osservazione.

### Diagnosi verificata e modifiche

Le prime query su impiantistica, regione, nuova linea e anno restituivano soprattutto norme e bandi. Le fonti territoriali arrivavano soltanto dopo più formulazioni settoriali. Ora le formulazioni aperte alternano subito una ricerca su portale, mantengono unite alcune espressioni commerciali e usano il filtro temporale Serper senza imporre l'anno come parola. Il confronto non dimostra che tutte le nuove query siano migliori: una variante iniziale con «nuova divisione» attirava annunci dipendenti e non è stata mantenuta come prima formulazione. La versione finale sullo stesso evento restituisce dieci URL in Lombardia e zero in Piemonte. Non vengono contati come aziende pertinenti sulla sola base degli snippet.

Le letture reali dei siti hanno mostrato che `lombardiaeconomy.it` e `piemonteeconomy.it` rimandano ai sottodomini `lombardia.italiaeconomy.it` e `piemonte.italiaeconomy.it`: aggiornati i domini delle query. Nei due confronti con la stessa frase, vecchio e nuovo dominio hanno comunque restituito zero URL. La correzione è verificata dai redirect, **non da un aumento misurato della resa di quelle query**.

La scoperta diretta ora accoda sezioni e feed realmente collegati dai portali: PMI e Imprese di Veneto Economia, feed Lombardia Economy e Piemonte Economy. Regione selezionata, ipotesi e provenienza accompagnano gli articoli; il feed non diventa un cliente. La lettura resta indipendente dal motore di ricerca e controlla robots, pagina di accesso e condizioni collegate. Le sezioni curate non avviano la scansione delle sitemap dell'intero editore. Ripresa e avvio conservano deduplicazione e controllo Stop.

È stata provata anche la sezione imprese di Toscana Economy: tutti i sei articoli aziendali campionati erano del 2024. È quindi conservata in diagnostica ma sospesa come fonte di eventi attuali; rimangono le altre strategie, directory e ricerche in Toscana. Le nuove divisioni e i nuovi brand sono riconosciuti come temi da verificare, senza trasformarli in bisogni digitali.

La lettura degli articoli ha rivelato contenuti correlati e anteprime riservate mescolati al testo principale. Il lettore ora seleziona il corpo visibile esplicitamente marcato dell'articolo, quando univoco; in caso di ambiguità non sceglie arbitrariamente la prima scheda. Il testo integrale resta conservato. Le dichiarazioni e gli avvisi espliciti di accesso riservato producono `unverifiable`, fermano la risoluzione dell'impresa e non alimentano l'analisi del modello. Nessun aggiramento delle restrizioni. Citazioni suggerite fuori dal corpo selezionato non possono recuperare un'azienda dalla barra laterale.

Nel caso Plastica LG il modello aveva restituito una citazione valida ma composta solo dal nome: 11 caratteri. La risoluzione ora cerca nel corpo originale un paragrafo letterale che nomini l'impresa; conserva un contesto di 156 caratteri sull'espansione produttiva. Un dominio stampato come testo del collegamento non viene più usato come ragione sociale. La correzione non inventa un progetto o un budget.

### Prova reale e confronto riproducibile

Artefatti in `data/pilot50-source-mix/`. **23 richieste Serper effettive** complessive, registrate nel contatore reale; una query del confronto è stata riutilizzata dalla cache. Nessun acquisto, invio o inserimento di proposte nel CRM di produzione.

- Quattro fonti territoriali lette nel pilota iniziale, sette risposte originali conservate incluse le pagine di accesso. **23 articoli individuati senza richieste Serper**. La riproduzione sulle risposte congelate restituisce gli stessi candidati; l'archivio toscano è stato sospeso dopo la verifica.
- Tutti i 23 articoli hanno attraversato il triage. Su 17 è disponibile un corpo esplicito; due anteprime per abbonati passano da proposta di risoluzione a fonte non verificabile. Gli instradamenti verso la risoluzione passano da 18 a 16. Sono misure intermedie, non opportunità qualificate o precisione commerciale.
- Una verifica aziendale completa: **Plastica LG**, dominio ufficiale, P.IVA, sede a Moncalvo e email aziendale verificati, cinque documenti considerati. Il confronto sul medesimo caso rimane `rejected` prima e dopo il recupero del contesto. Budget sconosciuto. Il modello conserva l'espansione come contesto aziendale; manca una necessità documentata di progetto completo. Nessuna conclusione che l'azienda non possa avere bisogni non osservati.

Report ricostruibile con `.venv/bin/python scripts/report50_business_sources.py`: `pilot50-business-sources.json`. Il pilota sorgenti è in `scripts/pilot50_business_sources.py`; `--replay` usa esclusivamente le catture e il piano originali, con un database temporaneo nuovo a ogni esecuzione. I confronti delle query, inclusa la variante non scelta, restano nei JSON `paired-*`. Campione di sviluppo, non indipendente: **zero qualificati nella verifica aziendale completata, precision@20 non misurabile**. Non è stata completata la verifica aziendale di tutti gli articoli.

### Validazione e lavoro rimanente

**391 test superati**, suite completa nel file `tests50-business-sources.txt`; copre nuove fonti, limitazioni di accesso, ambiguità degli articoli, citazioni, condizioni d'uso, deduplicazione, API e Stop. Il frontend non è stato modificato. Preservazione verificata: **44 tabelle commerciali identiche**, integrità SQLite `ok`; distinte cache, consumo (+23 richieste) e salute operativa del provider (`preservation50-business-sources.json`).

Rimane da dimostrare il risultato commerciale richiesto. In particolare: valutare casi reali positivi, conservare e correlare contesti aziendali più completi senza attribuire fatti di altre imprese, misurare il recupero delle opportunità e la precisione su un campione indipendente. Le nuove fonti e le correzioni riducono errori osservati; non dimostrano ancora un aumento dei clienti acquisibili o acquisiti.

## Settimo passaggio: non perdere i fatti dopo aver identificato l’impresa

Backup verificato: `data/backups/20261014T094753293906Z/`. Il sesto passaggio ha prodotto modifiche e nuove prove verificabili; questo passaggio prosegue un difetto dimostrato nel caso reale, senza riavviare processi già terminati.

Il campo `subject_quote` serviva correttamente a collegare l’azienda all’articolo, ma diventava anche l’unico testo passato alla verifica commerciale. Il secondo controllo in `inspect_candidate` duplicava la logica e poteva restringere di nuovo il contesto. Ora il collegamento nome/dominio/sede usa lo stesso verificatore sia nel triage sia nell’analisi approfondita. Dopo quel controllo, conserva la citazione e i paragrafi letterali del corpo selezionato che nominano il soggetto. Paragrafi che nominano anche altre ragioni sociali non vengono aggiunti automaticamente; i paragrafi adiacenti senza il nome e le barre laterali non vengono attribuiti per vicinanza.

Il documento conserva testo integrale, passaggi selezionati e metodo di delimitazione. Ripetere il controllo non restringe nuovamente i passaggi alla sola citazione iniziale. Gli estratti dati al modello devono comunque comparire come frammenti contigui nella fonte originale: unire passaggi distanti non crea una citazione nuova. Budget, fattibilità, identità e soglia di qualificazione restano invariati.

Confronto sul caso Plastica LG, con le medesime pagine congelate: **156 → 1.797 caratteri editoriali, quattro passaggi conservati**. La rianalisi locale produce tre citazioni di contesto invece di una. Il modello non documenta un progetto digitale completo: esito `rejected` sia prima sia dopo, budget sconosciuto, **zero qualificati e zero richieste Serper**. Questo risultato dimostra il recupero del contesto, non una migliore precisione commerciale o l’assenza di qualsiasi bisogno non osservato dell’impresa.

Comando riproducibile: `.venv/bin/python scripts/replay50_subject_passages.py`. Le letture web sono sostituite da risposte originali conservate; URL mancanti producono un errore esplicito. Viene utilizzato soltanto il modello locale reale, con database del pilota separato. Report: `regression50-subject-passages.json`; dettagli in `data/pilot50-source-mix/subject-passages-recheck.json`. Il confronto è sul caso di sviluppo, non su un campione indipendente.

**397 test superati** (`tests50-subject-passages.txt`), compresi passaggi di aziende diverse, omonimie, contesto inventato, contenuti laterali, verifica ripetuta e citazioni contigue. Confronto del database di produzione con il backup: tutte le **47 tabelle identiche**, nessuna esclusione, integrità `ok` (`preservation50-subject-passages.json`). Nessuna proposta o decisione precedente è stata riscritta.

Restano aperti la risoluzione verificabile dei riferimenti indiretti nell’articolo, la qualità del ragionamento commerciale del modello e soprattutto la validazione di opportunità reali positive su un campione indipendente. Non è completato l’obiettivo complessivo CustomerSearch 5.0.

## Ottavo passaggio: verifica operativa del coordinatore e lavoro ripetuto

Backup verificati: `data/backups/20261014T095434856351Z/` prima della prova; `data/backups/20261014T095920085543Z/` prima delle correzioni. Il pilota `scripts/pilot50_cycle.py` esegue il vero worker su una copia privata del database. Soltanto cache e contatore Serper usano il database operativo; non invia contatti e non inserisce aziende nel CRM reale. I confini dichiarati del campione (20 richieste, 120 attività o 6 imprese verificate) appartengono allo strumento di collaudo, non alla ricerca dell’app.

La prova è stata fermata anticipatamente dopo aver riprodotto un difetto: **tre verifiche approfondite di Automazione Veneto**, avviate da pagine diverse e allargate ogni volta al sito. Risultati prima della correzione: **6 richieste Serper, 33 attività completate, una fallita, 17 pagine candidate, una sola impresa con valutazioni approfondite completate, zero qualificati**. L’errore registrato riguarda la connessione a un PDF di Tespi; nessun errore Serper nel campione. Il passaggio da richiesta di Stop a conclusione del processo pilota ha impiegato circa 0,51 secondi. La coda residua è conservata, non dichiarata esaurita. Report: `pilot50-cycle-diagnosis.json`; catture e database in `data/cycle50/2026-10-14T09-55-19.001780+00-00/`.

### Decisioni e modifiche

- **Unire il lavoro in attesa, conservando le prove.** `company_queue.py` unisce verifiche con la stessa chiave aziendale e lo stesso dominio ufficiale. Transazione SQLite serializzata contro assegnazione e Stop; ID già assegnati conservati. Restano tutti i documenti, gli URL da leggere, le domande e le query di origine. Il pianificatore attende il controllo aggregato e l’esito viene associato alle pagine di provenienza. Un lavoro già in esecuzione o completato non viene riscritto.
- **Non rianalizzare fonti invariate già esaminate.** Le valutazioni conservano le impronte dei documenti effettivamente letti, inclusi testo selezionato, date e restrizioni. Solo i follow-up automatici della stessa campagna possono riutilizzare un esito completato, dopo una nuova lettura preliminare che confermi le medesime prove. Nuovi contenuti, altre identità, nuove fonti, controlli incompleti o precedenti campagne richiedono una verifica. Le vecchie valutazioni senza queste impronte non vengono considerate riutilizzabili.
- **Distinguere sezioni e notizie.** Anteprime datate con parole come “legalità”, “azienda” o “servizi” facevano scegliere vecchi articoli come pagine legali o di offerta. Ora le sezioni e le notizie hanno selezioni separate. Le date delle anteprime servono a ordinare letture, non a certificare eventi. Si aprono anche annunci di consegna di strumenti digitali degli ultimi due anni come controprove e sviluppi commerciali degli ultimi 180 giorni. Nessuna promozione automatica o modifica della soglia.
- **Misurare anche richieste fallite.** Il contatore del pilota ora intercetta le prenotazioni effettive del provider, anche quando il trasporto fallisce. Cache e chiamate bloccate prima della prenotazione non consumano il campione. Il consumo operativo dell’app era già registrato prima dell’invio; il difetto riguardava soltanto il rapporto del pilota. I sei tentativi di questa prova coincidono con la differenza del contatore reale.

### Confronto sulle fonti reali e limiti

`scripts/replay50_company_queue.py` riproduce le prime due verifiche che erano contemporaneamente in attesa, riutilizzando le pagine originali conservate e il modello locale reale. **Due lavori diventano uno**, con entrambi gli URL iniziali conservati. Dodici pagine lette, delle quali dieci congelate e due nuove letture protette del sito ufficiale: annuncio del nuovo sito ed espansione europea. **Zero richieste Serper**. Una pagina originale invariata riutilizza poi correttamente la valutazione completata senza altra analisi del modello. Report: `regression50-company-queue.json`; dossier completo nella directory indicata dal rapporto.

L’esito rimane **scartato per assenza di un progetto completo documentato**, budget sconosciuto. L’annuncio del nuovo sito viene finalmente acquisito come pagina originale, ma il modello non ne estrae nel campione una citazione specifica classificata come controprova: questo limite interpretativo resta aperto. Non equiparare la presenza del documento a comprensione completa del suo contenuto. Sono state riutilizzate cache locali; non è un confronto valido dei tempi a freddo. Il campione è diagnostico e di regressione, **non indipendente e senza opportunità positive**: precision@20 e miglioramento commerciale restano non misurabili.

**405 test superati** (`tests50-company-queue.txt`), incluse unione delle prove, omonimie, isolamento dei lavori già in esecuzione, Stop/Riprendi, attesa delle query collegate, lettura dei nuovi URL, fonti invariate, esclusioni e conteggio dei tentativi falliti. Preservazione: **44 tabelle identiche** rispetto al backup iniziale, SQLite `ok`; escluse soltanto cache, contatore e salute operativa del provider (`preservation50-company-queue.json`). Server riavviato, `/` e `/api/campaigns` rispondono HTTP 200; nessuna campagna di produzione riavviata automaticamente. Frontend invariato.

Il lavoro successivo deve verificare soprattutto la scelta e comprensione dei fatti commerciali sulle fonti originali, l’equilibrio tra imprese e query esplicite e un campione più ampio di aziende diverse. Le correzioni riducono sprechi dimostrati; non completano ancora l’obiettivo di trovare opportunità commerciali utili con qualità misurata.

## Nono passaggio: prove perse e falsi candidati nel ciclo reale

Il passaggio precedente è stato **progresso**: modifiche al motore, 405 test e confronto reale verificato. Il lavoro continua sullo stesso obiettivo, senza ridurlo al superamento dei test. Specifica 5.0 riletta. Backup verificato prima delle nuove modifiche: `data/backups/20261014T101053718022Z/`.

### Errore dimostrato nella deduplicazione

L’annuncio del nuovo sito di Automazione Veneto era stato letto e il modello aveva selezionato estratti, ma **tutti gli estratti di quella pagina erano stati eliminati**. Il confronto sul testo integrale considerava pagina e archivio copie dello stesso contenuto, a causa di menu e notizie laterali condivise. La deduplicazione eliminava poi ogni citazione con la medesima origine, anche se conteneva un fatto completamente diverso: nel caso osservato, una citazione cancellata aveva sovrapposizione lessicale zero con quella mantenuta.

Ora le citazioni distinte restano disponibili, incluse le controprove. L’identità di origine limita invece i requisiti di indipendenza, il relativo bonus e la confidenza: più frasi dello stesso comunicato copiato non creano più riscontri indipendenti. Il confronto lessicale è simmetrico, così una frase generica breve non cancella una dichiarazione più specifica. Per confrontare i documenti si usa il corpo commerciale selezionato, mantenendo sempre il testo originale per verificare le citazioni.

Il lettore supporta anche il corpo CMS `#editor` **solo quando segue nello stesso contenitore un H1 corrispondente all’Article principale**. Editor in moduli, barre laterali, prima del titolo o modificabili non vengono selezionati. Le entità HTML nel titolo strutturato vengono decodificate per il confronto con il titolo visibile. Testo originale e pagina completa rimangono archiviati.

Confronto congelato: delle **50 citazioni proposte identiche**, prima ne restavano **39**, ora **47**. Il corpo dell’annuncio passa da 8.305 caratteri con contorni a **1.705 caratteri dell’articolo**. La rianalisi con il modello locale reale conserva **quattro citazioni della pagina**, contro zero nel dossier precedente. Sono ancora classificate come contesto aziendale, non tutte come controprove: la comprensione commerciale resta da migliorare. Esito invariato `rejected`, budget sconosciuto, nessun errore di citazione e **zero richieste web o Serper** nel replay.

Artefatti: `regression50-evidence-origins.json`; comando `.venv/bin/python scripts/replay50_evidence_origins.py`. Il manifest `evidence-origin-baseline.json` fissa directory e hash di **14 file** della baseline. I replay non si spostano sul nuovo pilota quando cambia il puntatore “latest”. Questo è un confronto di sviluppo, non una misura di precisione su dati indipendenti.

### Secondo pilota operativo e correzioni derivate

Il nuovo ciclo reale, con CRM isolato, è terminato al confine dichiarato del campione: **9 query eseguite, 3 richieste Serper non in cache, 43 attività completate e 3 fallite**. Sono state lette 23 pagine candidate. Nessuna opportunità qualificata. Rapporto: `pilot50-evidence-routing.json`; directory `data/cycle50/2026-10-14T10-15-46.907683+00-00/`.

La correzione della coda applicata all’avvio confronta attività dello stesso tipo. La prima query è diventata una ricerca diretta di imprese; nelle prime sette query **due ricerche aziendali contro zero** nel precedente pilota. Non equivale a una crescita delle opportunità. Il successivo controllo ha mostrato che anche le letture di directory venivano conteggiate come verifiche di imprese: ora i due ruoli sono separati nella coda. Quest’ultima correzione è verificata con test di schedulazione, non con l’intero pilota già avviato.

Il limite “tre imprese verificate” del pilota ha contato tre identità memorizzate; la revisione manuale mostra che **non erano tre aziende compatibili**:

- **Automazione Veneto:** impresa reale, nessun progetto completo documentato.
- **SIPA Solutions:** approfondimento inutile. Nella pagina “Chi siamo” è dichiarata **SIPA S.P.A.**, ma il suffisso commerciale “Solutions” impediva l’associazione. Ora il controllo riconosce la base letterale prima della forma legale, coerente con il dominio e presente in una pagina aziendale o in un contesto legale. Nomi parzialmente simili, clienti e autori del sito non bastano. La pagina congelata ora viene scartata nel triage, prima dell’analisi locale.
- **VeneziaToday:** editore erroneamente trattato come impresa. Il proprio schema WebSite lo descrive come servizio di notizie territoriali; ora questa dichiarazione ne stabilisce il ruolo di fonte. Non basta che un articolo menzioni un giornale. Anche la dichiarazione di periodico iscritto al Registro della stampa è riconosciuta, correggendo **Padovanews**. Quando la homepage identifica un editore che l’articolo non rendeva riconoscibile, il controllo passa alla risoluzione delle aziende citate.

Due altri casi reali sono stati corretti sulle stesse risposte originali:

- **Hile:** sede operativa esplicita a Curtarolo, filiale a Pordenone. L’identità era verificata ma il territorio rimaneva ignoto. Ora la sede dichiarata prevale sulle filiali; una sede legale o l’indirizzo societario strutturato mantengono la precedenza. Senza un’indicazione esplicita, indirizzi discordanti restano incerti. Hile può proseguire l’indagine come impresa veneta; non è qualificata automaticamente.
- **Adnkronos:** attributo HTML `class` senza valore provocava un’eccezione nel parser. Il replay della stessa pagina ora restituisce 3.129 caratteri leggibili. L’accessibilità tecnica non rende pertinente l’impresa citata, che rimane fuori target nel caso del grande gruppo esaminato.

Le correzioni emerse durante il pilota sono state verificate dopo l’acquisizione sui documenti congelati. `.venv/bin/python scripts/replay50_target_routing.py` riproduce quattro casi con **zero richieste web, modello o Serper**, senza cambiare il database del pilota. Report: `regression50-target-routing.json`, con i rapporti specifici `regression50-primary-office.json`, `regression50-legal-brand.json` e `regression50-html-attributes.json`. Nessuno di questi quattro casi viene promosso.

### Collaudo, preservazione e lavoro aperto

**420 test superati**, suite completa in `tests50-evidence-origins.txt`. Comprende prove distinte da una stessa origine, controprove che non devono sparire, nessun bonus dalle copie, confidenza, corpi ambigui, attributi incompleti, sedi multiple, editori e denominazioni legali. Il test dell’advisor con risposta simulata non prende più il lock del modello reale; le protezioni del modello nell’app rimangono invariate.

Confronto con il backup: **44 tabelle identiche**, integrità SQLite `ok`, **3 richieste Serper** registrate; escluse dal confronto solo cache, contatore e salute operativa del provider (`preservation50-evidence-origins.json`). Nessun contatto inviato, nessuna proposta inserita nel CRM reale. Server locale riavviato dopo il collaudo. Frontend invariato.

La revisione dimostra difetti di instradamento e perdita di prove, non il raggiungimento della qualità commerciale. Non esiste ancora un campione indipendente di 20 opportunità qualificate né dati di conversione. Il prossimo ciclo deve misurare l’intero motore aggiornato su aziende diverse, distinguendo imprese compatibili, fonti editoriali e opportunità effettive; migliorare inoltre la lettura delle controprove, senza forzare qualifiche per raggiungere un numero.

## Decimo passaggio — verificare le imprese prima di cambiare modello

Backup verificato: `data/backups/20261014T103335203043Z/`, 596 file e due database, hash e integrità ricontrollati. Nessuna nuova richiesta Serper in questo passaggio.

### Screening dei risultati Google già acquisiti

`.venv/bin/python scripts/pilot50_existing_companies.py` legge le pagine originali usando le stesse protezioni HTTP e lo stesso triage dell’app, in una copia privata del CRM. Il campione comprende tutti i risultati delle tre query aziendali del precedente pilota: **30 URL, 27 domini unici**, settore impiantistica industriale, Veneto/Lombardia/Piemonte. Non è un nuovo campione indipendente di opportunità.

Esito originario: **16 imprese identificabili**, **5 identità da approfondire**, **1 scarto**, **5 errori di accesso** (due DNS, tre robots.txt non verificabili). I limiti delle fonti non sono stati aggirati. `pilot50-existing-companies.json` punta al rapporto completo con tempi, motivi e pagine conservate. Queste sedici imprese non sono opportunità qualificate: lo screening verifica identità, attività e territorio, senza modello né valutazione del bisogno.

La revisione ha individuato tre difetti riproducibili:

- **Bertolino Impianti:** “Torino e in provincia” nel titolo veniva interpretato come ente pubblico. Rimossa la ricerca indiscriminata di termini istituzionali dai titoli concatenati; la verifica dell’identità editoriale o istituzionale della homepage resta attiva. La partita IVA stampata come `p. i.v.a.` ora viene letta.
- **Fullservice:** l’indirizzo `35020 – Legnaro – PD C.Fisc.…` era conservato ma la regione rimaneva ignota. Il parser riconosce CAP, comune e provincia separati, anche con trattini tipografici e un’etichetta fiscale successiva. Non deduce la regione da una via o da un codice isolato.
- **Radar Impianti:** `Part. IVA IT` non veniva riconosciuto; ora l’identità include il numero letterale, utile anche alla deduplicazione.

Il replay delle stesse pagine porta Bertolino e Fullservice al successivo approfondimento aziendale e completa Radar. **Due candidati recuperati, nessuna qualifica automatica.** Non abbiamo rietichettato il conteggio del pilota come se fosse una nuova ricerca. Comando `.venv/bin/python scripts/replay50_identity_formats.py`; risultati e hash delle pagine in `regression50-identity-formats.json`.

### Confronto locale: esperimenti non adottati

Installato separatamente il modello gratuito `qwen3.5:4b-q4_K_M`; l’app mantiene **Qwen2.5 7B**. Il runtime locale dichiara supporto a thinking, disattivato soltanto nel confronto per produrre direttamente le risposte strutturate entro i limiti tecnici esistenti. Nessuna inferenza cloud o modifica delle impostazioni di produzione.

`.venv/bin/python scripts/compare50_local_models.py` usa il prompt effettivo dell’app, due pagine originali congelate della stessa impresa e quattro controlli esplicitamente sintetici. Input, schemi, risposte, citazioni validate e tempi restano in `data/model-comparison/`. È una diagnostica dell’estrazione, non una misura di precisione commerciale. Gli esiti dei controlli multi-fatto dipendono anche dalla possibilità di attribuire più categorie allo stesso passaggio; non sono probabilità di vendita.

Run della baseline: `2026-10-14T10-41-59.199317+00-00` per Qwen2.5 e `2026-10-14T10-43-18.520283+00-00` per Qwen3.5. Entrambi non identificano correttamente come controprova l’annuncio del sito già rifatto. Una variante con citazioni separate per frase è stata confrontata su entrambi (`2026-10-14T10-44-49.225365+00-00`): migliora alcuni controlli sintetici con Qwen3.5, ma resta errata sulla pagina del sito concluso e peggiora altri casi. **Variante ritirata e tre file sperimentali ripristinati dalla baseline verificata.** Il log `tests50-sentence-evidence.txt` riguarda l’esperimento ritirato, non la versione consegnata. `model50-comparison.json` conserva l’ultimo confronto sperimentale, non descrive il comportamento installato.

### Verifica della versione consegnata

**425 test superati** (`tests50-identity-formats.txt`), inclusi enti reali, titoli territoriali, varianti della partita IVA, numeri senza etichetta e province non dimostrate. Il controllo iniziale nel sandbox non poteva usare porte locali e `ps`; la suite finale è stata eseguita con i permessi tecnici necessari. **47 tabelle di produzione identiche al backup**, comprese configurazioni, cache e contatori; integrità SQLite `ok` (`preservation50-identity-formats.json`).

Rimane aperto il problema principale: distinguere bene il bisogno commerciale e le soluzioni già presenti. Questo passaggio recupera imprese erroneamente fermate e documenta un confronto locale sfavorevole, ma non dimostra ancora nuove opportunità qualificate, precisione su venti casi indipendenti o capacità di acquisire clienti.

## Undicesimo passaggio — controprove prima della proposta

Backup verificato: `data/backups/20261014T105028824051Z/`. Il modello dell’app rimane Qwen2.5 7B. Gli esperimenti non sostituiscono le impostazioni di produzione.

### Problema e soluzione integrata

La classificazione generale in dieci categorie continuava a interpretare male l’annuncio di un sito già rifatto. Esplicitare lo schema JSON e usare un prompt più breve non ha risolto il caso. Il confronto Qwen3.5 con thinking attivo ha prodotto una risposta troncata dopo circa 108 secondi; è stato interrotto durante il secondo caso e registrato come diagnostica parziale, non come sei prove completate. Gli input effettivi e i risultati sono conservati in `data/model-comparison/`; le varianti sono riproducibili con `scripts/compare50_local_models.py`, scegliendo `--mode schema`, `--mode extractor` oppure `--mode thinking`.

Un compito più circoscritto ha invece riconosciuto le dichiarazioni del sito completato. `sales/solution_evidence.py`, integrato in `LocalResearcher.analyze`, domanda quali estratti descrivano strumenti digitali già disponibili. La selezione preliminare delle unità serve solo a evitare inferenze su testi estranei: non assegna automaticamente etichette o punti. Il modello può restituire soltanto ID di estratti originali, ricostruiti e verificati localmente. La proposta riceve queste controprove insieme agli altri riscontri.

La stessa citazione può avere più ruoli, per esempio evento e soluzione già consegnata, oppure richiesta e budget. La deduplicazione conserva i ruoli diversi ma mantiene la stessa origine: nessun bonus di indipendenza o confidenza dalla duplicazione delle etichette.

Corretto anche un veto troppo ampio: un sito già online non dimostra che sia adeguato al rifacimento richiesto o a un progetto diverso. Restano obbligatori bisogno documentato, perimetro completo, revisione delle soluzioni e delle alternative minori. Fornitore già selezionato, richiesta chiusa o progetto dichiarato concluso restano controprove bloccanti. Nessuna qualifica deriva dalla sola disponibilità o indisponibilità di uno strumento.

### Confronto sul dossier completo

`comparison50-solutions.json` confronta gli stessi **12 documenti originali**, verificando uguaglianza di URL, contenuti, corpo analizzato e date. Nell’articolo del nuovo sito di Automazione Veneto, prima restavano quattro citazioni classificate come contesto; ora arrivano alla correlazione anche **due controprove letterali del sito realizzato**. L’esito rimane `rejected`, il budget sconosciuto e non compaiono limiti di verifica. Il nuovo passaggio non genera un’opportunità per riempire la shortlist.

Replay reale con modello locale: circa 91 secondi, **zero richieste web o Serper**. Cache diverse impediscono di ricavare da questo tempo un miglioramento di produttività. Rapporto `regression50-focused-solutions.json`, directory `data/evidence-origin-replay/2026-10-14T11-04-01.450550+00-00/`. Riproduzione: chiamare `scripts.replay50_evidence_origins.run('regression50-focused-solutions.json')`.

### Verifica separata ed errore trovato

Il primo controllo comprende due pagine reali di una stessa impresa e otto esempi sintetici: dieci esiti conformi alle attese (`probe50-solutions.json`). Non è una misura di precisione commerciale.

Una verifica successiva usa quattro altre imprese e quattro nuovi controlli. La prima esecuzione del banco di prova passava al modello tutte le unità, anziché il sottoinsieme effettivamente usato dall’app: ha mostrato attribuzioni errate di impianti fisici a soluzioni digitali (`validation50-solutions.json`). La ripetizione con la selezione esatta dell’app ha eliminato quelle attribuzioni ma ha individuato **un errore sul portale dichiarato sospeso per guasto** (`validation50-solutions-scoped.json`). Non viene nascosto né contato come successo.

Correzione: una citazione che dichiara indisponibilità, sospensione o disponibilità futura non sostiene l’etichetta di strumento operativo. Il controllo deterministico conserva il testo come contesto, con tipo originale e nota diagnostica; non lo trasforma automaticamente in una lacuna commerciale o in un progetto da proporre. Il replay delle risposte già registrate conferma la correzione (`validation50-solutions-grounded.json`). Questo campione ha informato la modifica ed è quindi **dato di sviluppo**, non prova indipendente finale. I riscontri del dossier completo precedente sono stati ricontrollati e non cambiano con questa regola.

Resta un limite osservato: una menzione di “sito dedicato”, come nella pagina Tecnova, richiede anche la visita del collegamento per verificare cosa offra effettivamente. Il nuovo passaggio raccoglie dichiarazioni, non certifica funzionalità, adeguatezza o proprietà di un dominio esterno.

### Ricerca mirata sulle fonti

Tre richieste Serper controllate, con registrazione dei consumi: prima portale lombardo e arredamento veneto, poi ampliamento dopo risultati improduttivi. La terza query con `srl` ha attirato guide giuridiche e footer editoriali: la forma legale non viene introdotta come vincolo obbligatorio nelle query del planner. I social sono stati usati soltanto per scartare URL dalla lettura; nessun accesso automatizzato a quelle piattaforme.

Due risultati sono stati letti nelle fonti originali: **Motocross Marketing**, annuncio TwinAir dell’8 maggio 2026 e homepage con prodotti/prezzi; **V2K Group**, articolo del 16 febbraio 2026 su un gruppo già strutturato. Il primo non documenta un progetto digitale irrisolto; il secondo è oltre la finestra temporale e non dichiara un bisogno digitale. Nessuna promozione. `pilot50-new-brands.json` documenta decisioni e limiti; fonti in `data/event-search/2026-10-14T10-52-53.691453+00-00/`.

### Collaudo e stato

**433 test superati** (`tests50-focused-solutions.txt`). I nuovi controlli coprono citazioni e ID inventati, recupero delle controprove nella correlazione, più ruoli senza indipendenza artificiale, budget letterale, progetto già assegnato, revisione dell’adeguatezza ancora obbligatoria e strumenti sospesi/futuri. Timeout, lock del modello, Stop/Riprendi, sicurezza e CRM restano verificati dalla suite.

**44 tabelle identiche al backup**, integrità SQLite `ok`; cambiano soltanto cache, consumo Serper (**3 richieste**) e salute operativa del provider (`preservation50-focused-solutions.json`). Nessun contatto inviato, acquisto o opportunità inserita nel CRM reale.

Il lavoro migliora la raccolta delle controprove e rimuove uno scarto automatico ingiustificato. Non dimostra ancora un campione indipendente di opportunità qualificate né efficacia nell’acquisizione di clienti. Restano prioritari la scoperta di bisogni concreti su aziende diverse e il controllo delle soluzioni collegate.

## Chiusura del controllo dei siti collegati — 14 ottobre 2026

Corretto un limite osservato su Tecnova: il sito ufficiale dichiara “Visita il nostro sito dedicato!”, ma il link porta soltanto l’etichetta “Scopri di più”. Il controllo precedente ignorava la destinazione. `sales/linked_sites.py` riconosce un richiamo esplicito in un blocco HTML circoscritto con una sola destinazione, escludendo contesti ambigui, sezioni distinte, footer, citazioni e contenuti nascosti. Non assegna proprietà, adeguatezza o punteggi al dominio collegato.

L’analisi approfondita riconsidera i collegamenti anche dopo la lettura delle pagine aziendali: l’identità può diventare verificabile soltanto nei contatti. Le destinazioni vengono lette con `ResearchWeb`, conservando robots.txt, protezioni di rete, cancellazione e limite complessivo di tre destinazioni esterne per controllo. Una destinazione bloccata o oltre la copertura disponibile impedisce di dichiarare completa la verifica. Le pagine finali dopo redirect conservano il ruolo `linked_solution`, senza diventare automaticamente fonti ufficiali.

**Risultato misurato:** confronto identico prima/dopo su 81 pagine originali già raccolte, una pagina con un collegamento aggiuntivo recuperato, nessun altro cambiamento nella selezione. Rapporto `regression50-linked-sites.json`, con hash e percorso di ogni cattura. Tecnova è un caso di sviluppo: questo dato non misura precisione commerciale indipendente.

Riproduzione offline, senza Serper o inferenze:

```bash
.venv/bin/python scripts/check50_linked_sites.py --backup data/backups/20261014T113627182351Z --captures data/company-screening/2026-10-14T10-40-33.965496+00-00/pages
```

La destinazione reale è stata poi letta con il client protetto in un database isolato: HTTP 200, descrizione degli impianti Tecnova, prodotti, applicazioni e contatti aziendali. Questa fonte contraddice l’ipotesi di offerta non rappresentata online; non dimostra un bisogno attuale di nuovo sito. Nessuna opportunità è stata promossa. Cattura in `data/linked-site-verification/`, revisione e limiti in `verification50-linked-site.json`.

**439 test superati** in 11,930 secondi (`tests50-linked-sites.txt`), inclusi lettura dopo risoluzione dell’identità, redirect, ambiguità, mancata copertura, Stop e limiti alle destinazioni. Nessuna modifica al frontend in questo passaggio. Backup verificato: `data/backups/20261014T113627182351Z/`. Nessuna richiesta Serper, inferenza a pagamento, invio o opportunità inserita nel CRM. Il pilota da 12 richieste precedentemente fermato dal limite Codex non è stato rilanciato.

La correzione è conclusa e verificata. L’obiettivo commerciale complessivo resta non dimostrato: mancano ancora il campione indipendente di 20 opportunità qualificate e dati di contatti, risposte e contratti. Non si confondono test verdi o una controprova recuperata con clienti trovati.

Dopo il riavvio, homepage e API campagne rispondono HTTP 200. Tutte le righe delle **47 tabelle sales e 12 tabelle legacy** sono identiche al backup; integrità SQLite `ok` per entrambi i database (`preservation50-linked-sites.json`). Le campagne mantengono gli stati precedenti: una bloccata e due sospese. Nessuna ripartenza automatica.

## Indicazione operativa dell’utente — 14 ottobre 2026

L’utente avvia le ricerche reali nell’app. Lo sviluppo prosegue su criteri, test automatici e prove già raccolte: nessun nuovo pilota, consumo Serper o consultazione di siti esterni senza istruzione esplicita. Questa indicazione sostituisce l’autorizzazione precedente ai piloti autonomi.

Il pilota `data/cycle50/2026-10-14T11-41-04.639979+00-00/` è stato interrotto e il processo è terminato (exit 130). Lo stato salvato è sospeso; non verrà ripreso automaticamente. Hile e Radar hanno completato il controllo con esito negativo e nessun bisogno documentato; il campione è incompleto e non misura la precisione del sistema. Il rapporto conserva le attività e il motivo dell’arresto.

Confermati `daily_api_limit=null` e `monthly_api_limit=null` sia nell’app sia nella copia di prova. Rimosso il tetto predefinito del banco di prova, aggiunta ripresa dalla stessa copia e verificati i tre test del conteggio richieste. Queste funzioni non autorizzano l’avvio di nuove ricerche. Dettagli in `serper-unlimited-confirmed.json`.

## Diversificazione dei criteri, collaudo esclusivamente offline

Il generatore precedente iniziava tutte le regioni con impiantistica industriale e consumava le formulazioni dei cambiamenti sul primo settore prima di passare al successivo. Questo era coerente con la concentrazione dei casi già raccolti, ma riduceva la varietà delle ipotesi esplorate all’inizio.

Ora i settori iniziali ruotano in modo deterministico fra le regioni. Nelle ricerche per eventi si alternano settori e cambiamenti: nuova offerta, nuovi mercati, marchio, distribuzione e divisione. Le query su portali territoriali restano intercalate. Nessun settore o evento viene eliminato e i criteri di qualifica non cambiano.

La ripresa usa le impronte delle query già registrate, anziché interpretare il cursore come posizione nella lista di una specifica versione. Un aggiornamento dell’ordine non ripete query pagate e non salta combinazioni inesplorate. Paginazione, attesa delle verifiche e sospensione per errori tecnici restano separate dall’esaurimento delle formulazioni.

Confronto offline riproducibile contro il backup `data/backups/20261014T114731966935Z/`: **180 insiemi di query conservati integralmente** (profili, regioni e strategie). Nelle prime otto query `change / Veneto / B2B`, i settori esplicitamente cercati passano da **1 a 4**. Questo misura la varietà dell’esplorazione, non la pertinenza dei risultati né una maggiore conversione commerciale. Rapporto: `regression50-query-diversity.json`.

```bash
.venv/bin/python scripts/check50_query_diversity.py --backup data/backups/20261014T114731966935Z
```

**443 test superati**, compresi nuovi controlli su varietà iniziale, conservazione delle combinazioni e ripresa da un cursore precedente senza duplicati. Registro: `tests50-query-diversity.txt`. Nessuna richiesta Serper, inferenza locale o consultazione di siti esterni durante questo intervento. La ricerca reale resta a iniziativa dell’utente.

## Verifica dei requisiti: precisione sulle proposte ordinate

Il controllo del requisito 13 ha rilevato un segnaposto: `precision_at_10` e `precision_at_20` erano sempre null, anche in presenza delle revisioni necessarie. Ora `research_quality.py` calcola la percentuale di conferme sulle prime 10/20 proposte, con queste condizioni:

- Ultima proposta qualificata per azienda; ordinamento per punteggio e ID decrescenti, come nella lista.
- Una proposta demossa a falso positivo resta nel campione attraverso `original_status`; non migliora artificialmente il risultato sparendo dal denominatore.
- Tutte le prime K proposte devono esistere ed essere revisionate. Una conferma su un risultato inferiore in classifica non sostituisce una revisione mancante.
- La revisione più recente prevale, senza moltiplicare aziende o conteggi. Dossier mai proposti come qualificati e opportunità mancate non diventano conferme.
- Ogni misura espone numero disponibile, numero revisionato, conferme, falsi positivi e ID del campione. Il confronto è descrittivo, non un benchmark indipendente o una probabilità di vendita.

Le misure sono disponibili nella qualità complessiva, nelle diagnostiche per strategia/provider quando la provenienza è registrata e nella vista Risultati. Il riepilogo non conta più come falso positivo di una proposta un dossier mai qualificato. I dati reali attuali hanno zero proposte qualificate da revisionare: entrambe le percentuali restano null, correttamente.

**447 test superati** (`tests50-ranked-quality.txt`). I nuovi casi controllano 9 conferme e 1 falso positivo = 90%, campione incompleto, impossibilità di sostituire una revisione mancante con una conferma più in basso, duplicati e isolamento fra campagne. Browser desktop/mobile superato senza errori JavaScript (`ui50-ranked-quality.json`); durante il test tutte le destinazioni esterne al server locale fittizio sono bloccate. Nessun accesso web reale o consumo Serper. Backup verificato `data/backups/20261014T115118691960Z/`.

### Stato del completamento dopo le ultime correzioni

| Requisiti | Evidenza attuale | Limite restante |
|---|---|---|
| 1–2: obiettivo e audit | Percorso del motore e problemi osservati documentati in questo registro, campioni e catture conservati | L’utilità commerciale su nuovi risultati non è dimostrata |
| 3: Serper | Limiti null confermati, cache/dedup/rate limit/errori testati, contatori e stato disponibili | Saldo remoto non disponibile; non viene inventato |
| 4–6: ipotesi, strategie, query | Contratti del planner, fonti territoriali, 180 insiemi di query preservati con maggiore varietà iniziale | Produttività del nuovo ordine da misurare nell’uso reale |
| 7–8: filtri e identità | Regole di ruolo, fonti originali, controlli delle omonimie e regressioni su catture reali | Nessuna garanzia di risoluzione per ogni fonte o azienda |
| 9, 12: ciclo e risorse | Frontiera persistente, memoria delle query, adattamento, Stop/Riprendi e concorrenza coperti dai test | Nuove campagne lunghe saranno avviate dall’utente |
| 10–11: ragionamento e qualificazione | Citazioni vincolate alle fonti, controprove, inferenze esplicite, criteri obbligatori e controlli incompleti distinti | Campione indipendente di opportunità valide ancora insufficiente |
| 13: metriche | Conteggi, tassi descrittivi, esiti e precisione sulle prime K ora calcolabili dalle revisioni | Nessuna revisione reale sufficiente o conversione da dichiarare |
| 14: interfaccia | Preferenze, dossier, pipeline, comandi e metriche collaudati su desktop/mobile | Nessuna efficacia commerciale deducibile dalla UI |
| 15: benchmark | Confronti riproducibili su dati congelati; separazione dichiarata fra sviluppo e valutazione | Manca confronto completo su un nuovo campione indipendente qualificato |
| 16: implementazione e conservazione | Backup, test e verifiche dello storico disponibili; nessun invio o acquisto automatico | Le nuove ricerche reali richiedono l’avvio dell’utente, come richiesto |
| 17: risultati commerciali | Strumenti pronti per raccogliere e revisionare risultati ed esiti | Conversazioni, preventivi e clienti non dimostrati |

Il prossimo dato utile deve provenire dall’uso dell’app da parte dell’utente. Non si rilanciano autonomamente piloti e non si considera completato l’obiettivo commerciale sulla sola base dei test.
