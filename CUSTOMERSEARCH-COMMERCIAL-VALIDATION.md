# CustomerSearch — validazione commerciale AI-first

Data: 20 ottobre 2026. **GO alla preparazione di una prova reale controllata, dopo il riavvio del backend.** Nessuna nuova campagna viene avviata da questa validazione.

I blocchi riprodotti nell'acquisizione delle prove e nella loro trasmissione al modello sono stati corretti. Questo GO non certifica che il modello riconosca autonomamente tutti i casi, né che il prodotto generi due clienti paganti al mese: non sono state eseguite inferenze o ricerche nuove. La validazione commerciale indipendente e le conversioni restano da misurare.

## 1. Percorso effettivamente collegato

| Passaggio | Chiamante e componente utilizzati | Riscontro |
|---|---|---|
| Creazione | `static/agent6.js` → `POST /api/campaigns` → `sales/server.py` | Il server imposta `decision_engine=ai_first_1`; test HTTP su database temporaneo |
| Pianificazione | `AgentCoordinator.planning` → `ai.call` → `query_pipeline.prepare(ai_first=True)` | Ipotesi, fonte attesa, domanda e arresto; ledger comune, non un agente parallelo |
| Discovery | `AgentCoordinator._execute` → `research.search` → `commercial.coordinator.acquire` | Deduplicazione, ricevute, esclusione PDF; nessuno screening AI pagato degli snippet |
| Originale | `research.read` → `CompanyWeb.get` → `source_access.require_content` | Client protetto e checkpoint prima dell'inferenza; nei test la rete restituisce l'HTML congelato |
| Metadati e identità | `evidence.packet`, `inspection.document`, `commercial.identity.establish`, `geography.locate` | Funzioni reali sugli originali storici, senza sostituire identità o geografia nei nuovi test |
| Interpretazione | `COMMERCIAL_DECISION_1` tramite `agent6.ai` e adattatore esistente | Nei test **risposta fornita manualmente**, non inferenza del modello |
| Validazione | `schema.validate_response` → `decision.validate` | Prove originali, segmenti, soggetto, date, policy, ambito delle azioni |
| Qualificazione e dossier | `decision.materialize` → `memory.save_record` → `commercial_view`/`alignment` → Worklist e API dossier | Un giudizio AI; il vecchio qualificatore viene bloccato esplicitamente nel test |

Il server attualmente aperto, PID **16529**, risulta avviato alle **12:33:38 del 20 ottobre**, prima delle modifiche AI-first. Non è stato riavviato né usato per creare campagne. **Il semplice refresh del browser non carica il nuovo codice Python.** Il GO riguarda il codice aggiornato, non la vecchia istanza ancora in memoria.

Le campagne precedenti conservano il proprio snapshot. L'ultima è la 43, esaurita; la 42 è sospesa. Nessun dato storico è stato riqualificato.

Impostazioni lette dal database, senza modificarle: AI abilitata, REMOTE `gpt-5.4-mini`, modalità configurata Shadow, massimo 100 chiamate/2 USD stimati, 40 per flusso, 4 per candidato, input massimo 8.192. Nel nuovo contratto “Shadow” non significa che due motori eseguano un confronto parallelo: la decisione commerciale è AI-first con validazione. Feed RSS configurati: zero.

## 2. Regressioni commerciali: fatti e limiti

Sono stati riletti gli HTML già presenti nella cache, conservando provenienza e date. Sono distinti tre livelli: revisione delle prove salvate, esecuzione tecnica del percorso, capacità semantica del modello. L'ultimo livello non è misurabile senza inferenza e non viene dichiarato superato.

| Caso | Prove e risultato della revisione | Verifica del nuovo percorso |
|---|---|---|
| **Kondividi** | La pagina invita professionisti digitali con almeno due anni di esperienza e partita IVA. È una **collaborazione aperta / candidatura spontanea possibile**. | Identità verificata, Emilia-Romagna, invito e contatto presenti nell'input effettivo entro 8.192 byte conservativi. Un contratto di revisione INTERESTING attraversa validazione, salvataggio e proiezione senza richiedere data o budget. Nessun incarico pagato dichiarato. |
| **NHW Consulting** | Invito esplicito a collaboratori, freelance, consulenti e professionisti digitali. | Identità e Lombardia verificate. Il nome nei metadati è ora citabile; l'invito non viene perso per esaurimento dell'input. Stesso esito tecnico di Kondividi con risposta fornita manualmente. |
| **Studio Ninarello** | La richiesta riguarda architetti, geometri, ingegneri/periti termotecnici per sopralluoghi e raccolta dati. **Non pertinente allo sviluppo web.** | La professione e la prestazione arrivano al modello, anche nel budget reale di input. Il contratto negativo viene salvato senza trasformare la parola “collaborazione” in affinità professionale. Identità non sufficientemente corroborata: nessuna promozione automatica. |
| **Elice Group / Drupal** | La scheda è del **3 novembre 2015**. Non è una richiesta attuale. | Il testo “Cerchiamo sviluppatore freelance Drupal” resta nella scheda Elice; il titolo e il datore successivi non vengono mescolati. La data numerica resta datata ma a ruolo non assegnato: non diventa pubblicazione recente. Il validator non ammette RECENT_REQUEST senza una pubblicazione provata. |
| **CerealVeneta** | Le pagine descrivono produzione alimentare e semilavorati, non un editore. | `CerealVeneta Srl`, identità verificata, Veneto; nessuna classificazione istituzionale/editoriale imposta dal vecchio gate nel nuovo percorso. Non emerge automaticamente un motivo per rifare il sito. |
| **Agroalimentare La Veneta** | Sede a Loreggia, Padova. L'esistenza dell'azienda non dimostra un progetto digitale da acquistare. | Home e contatti consentono identità verificata e Veneto dopo la correzione della normalizzazione. Una proposta spontanea richiede ancora una motivazione documentata: non è stata inventata. |
| **Portale / richiedente** | Il dettaglio Drupal `/node/21903` riguarda **ilGiornale.it**, non Elice, ed è pubblicato il **3 settembre 2015**. | Nessuna eredità automatica del soggetto della scheda precedente; il portale non acquisisce identità verificata come committente. Metadati del publisher esclusi dalle unità di annunci multipli. |

Fonti conservate: `tests/fixtures/ai_first/commercial-originals.json.gz`; URL, hash e osservazioni in `implementation-report/commercial-validation/evidence-audit.json`. Non sono state ricontrollate online oggi.

**Risultato commerciale della revisione:** due piste utilizzabili per una candidatura spontanea, non due commesse aperte. Nessun nuovo lead generato, nessun contatto effettuato, nessun cliente acquisito da questa attività.

## 3. Problemi bloccanti dimostrati e correzioni

1. **Identità estratta ma non citabile.** NHW veniva riconosciuta tramite metadati, ma il modello non disponeva del corrispondente segmento originale. Ora i metadati sono persistiti come documento con hash e padre; un'ancora letterale del nome entra nel payload, senza attribuirla alle card di altri soggetti.
2. **Inviti eliminati dal limite di input.** Con il massimo attuale di 8.192, il payload poteva mantenere menu/contatti ma perdere la richiesta. La selezione condivisa degli estratti ha una modalità compatta: priorità alle frasi complete di invito, condizioni vicine e ancore; testi identici non vengono ripetuti. **Nessun aumento di budget o limiti.** Anche professioni non pertinenti restano leggibili: il selettore non decide che siano opportunità.
3. **Resolver d'identità non consolidato.** Il ramo nuovo usava l'estrattore più vecchio invece del resolver che isola titolare, footer e riferimenti a terzi. È stato collegato `commercial.identity.establish`, già presente, senza introdurre un altro classificatore.
4. **Provincia cancellata dall'indirizzo.** In indirizzi senza virgola/CAP, la rimozione della via cancellava anche `Loreggia (PD)`. Il numero civico ora delimita la parte stradale. Varianti con “Via Roma” e “Via Milano” verificano che una città nel nome della strada non diventi sede.
5. **Metadati temporali non utilizzati.** Il pacchetto conservava alcuni dati ma non li passava come date tipizzate. Schema.org, `time` e Last-Modified ora alimentano claim con ruoli distinti e origine.
6. **Confini delle schede stampate.** L'estrazione che iniziava da “Organizzazione:” perdeva il titolo precedente e inglobava quello successivo. Nei blocchi con date di fine scheda si usano quei confini; senza tale evidenza non viene inventato un abbinamento.

File interessati: `sales/agent6/research.py`, `evidence.py`, `passages.py`, `sales/extract.py`, `sales/commercial/geography.py`; regressioni in `tests/test_commercial_validation.py`. Nessun nuovo motore, framework, UI o servizio.

## 4. Metadati e date

| Informazione | Utilizzo e attendibilità |
|---|---|
| Titolo, description, canonical, Open Graph | Acquisiti dall'HTML; dichiarazioni della fonte, non identità automaticamente verificata. Nome dichiarato citabile quando pertinente all'unità. |
| JSON-LD / Schema.org | Conservati; JobPosting separati. Date di una singola pagina/articolo attribuibile al suo URL entrano nei claim; oggetti ambigui non datano automaticamente la pagina. |
| `datePublished` / `datePosted` | Pubblicazione, con origine conservata. Può sostenere attualità solo se coerente con il soggetto/unità e non scaduta. |
| `dateModified` | Modifica, mai rinnovo automatico di una richiesta vecchia. |
| `validThrough` | Scadenza; una richiesta scaduta non è RECENT_REQUEST. |
| HTML `time` | Ruolo da `itemprop` esplicito; altrimenti non assegnato. Nessuna trasformazione automatica in pubblicazione. |
| Data visibile dell'annuncio | Le etichette esplicite danno il ruolo; date numeriche senza etichetta restano conservate ma non assegnate. |
| HTTP Last-Modified | Modifica tecnica dichiarata dal server, non data di nascita/rinnovo dell'annuncio. |
| Ultima verifica | Momento dell'acquisizione originale, separato da pubblicazione e modifica. |
| Feed RSS / sitemap | Parser preesistenti disponibili; **non fanno parte della discovery effettiva AI-first verificata qui**, che usa le query del provider. Non si dichiara utilizzato `lastmod` o `pubDate` nella qualificazione nuova. Nessun feed viene aggiunto come funzionalità in questa fase. |

Un invito permanente senza data resta valutabile. Una pagina online da anni non dimostra invece che una vecchia vacancy sia ancora aperta. Le date sono dichiarazioni attribuite alla fonte, non certificazioni indipendenti.

## 5. Cinque canali, sprechi e memoria

La 43 precede il nuovo percorso: i suoi numeri sono una **baseline storica**, non risultati AI-first.

| Canale | Task query | AI | Record con originale* | Query senza risultati |
|---|---:|---:|---:|---:|
| Aziende | 4 | 7 | 20 | 1 |
| Agenzie | 13 | 39 | 7 | 4 |
| Social | 7 | 3 | 0 | 5 |
| Startup | 5 | 11 | 2 | 3 |
| Notizie aziendali | 13 | 40 | 0 | 1 |

*Le viste per flusso possono sovrapporsi: non sommare queste righe come documenti unici. Il report storico conta 27 record originali canonici.

Totale storico: 100 chiamate AI, 47 pienamente valide e 50 parzialmente valide, 3 invalide; costo **stimato** 0,28421475 USD, non fattura. 238 URL distinti scoperti, 216 record canonici, zero qualificati. Quattordici task query senza risultati su 42; nessuna query testualmente identica ripetuta, che non esclude ripetizioni semantiche. Due duplicati segnalati nella discovery storica.

Le 39 chiamate Agenzie e le 40 Notizie concentravano il 79% del consumo, soprattutto sugli snippet. Nel nuovo percorso quello stadio non spende chiamate AI. Pianificazione/ripianificazione sono limitate dentro il totale; le pagine pendenti hanno precedenza e restano validi i tetti per flusso/candidato.

Il test con **100 chiamate totali / massimo 40 per flusso**, su ledger temporaneo, dimostra che il primo flusso viene fermato al suo tetto e che gli altri quattro possono ancora verificare. I cinque planner sono coperti dalle regressioni esistenti. Sono prove di orchestrazione, **non cinque campagne commercialmente riuscite**.

Social resta soggetto a indicizzazione, accesso pubblico e robots. Cinque query social vuote su sette nella 43 mostrano un rischio reale di scarsa copertura; non si aggirano login o restrizioni. Le notizie richiedono ancora un soggetto e un bisogno documentati. Nessuna quantità minima viene riempita abbassando la qualità.

Feedback e ricevute cambiano priorità operative, senza riscrivere la 43 né creare blacklist da un singolo errore. Precisione, falsi positivi e falsi negativi del **nuovo modello** restano non misurati; la revisione storica dimostra due occasioni di collaborazione perse e gli errori tecnici descritti.

## 6. Test, integrità e rischi residui

Risultati definitivi e comandi sono registrati nei log:

| Controllo eseguito | Risultato |
|---|---|
| Baseline mirata | 120 test, OK |
| Regressioni durante la correzione | 44 test, OK |
| Suite completa finale | **1.954 test, OK**, 390 secondi |
| Ultimi contratti commerciali, quote e dossier | **10 test, OK**, inclusi offset delle citazioni confrontati con il testo persistito |
| Integrità database operativo | `integrity_check=ok`, zero violazioni FK, tutte le tabelle e gli stati identici al rilevamento iniziale |
| Database storico clienti | `integrity_check=ok`, contenuto identico all'ultimo snapshot verificato |
| Diff whitespace | `git diff --check`, OK |

La suite emette alcuni `ResourceWarning` preesistenti su connessioni SQLite dei test; non sono fallimenti, non sono stati nascosti e non hanno motivato refactoring marginali in questa fase.

- `implementation-report/commercial-validation/baseline-tests.txt`
- `implementation-report/commercial-validation/regression-tests.txt`
- `implementation-report/commercial-validation/commercial-tests.txt`
- `implementation-report/commercial-validation/full-tests.txt`
- `implementation-report/commercial-validation/database-before.json`
- `implementation-report/commercial-validation/database-after.json`

La suite usa database temporanei, fonti congelate e provider controllati. I controlli reali di estrazione non sono simulati; le risposte commerciali del modello lo sono e vengono dichiarate tali. Database operativo letto soltanto; nessun cambiamento a campagne, CRM, evidenze, configurazioni o budget.

Rischi di spesa ancora presenti:

- Il modello può formulare query poco produttive o interpretazioni commerciali sbagliate: nessun test con risposta fornita dimostra il contrario.
- Accessi bloccati o identità irrisolte possono consumare lavoro senza produrre un dossier.
- Le prove sono estratti entro il limite di input, non una lettura integrale garantita; i casi noti sono ora coperti.
- Un recapito pubblico è un canale attribuito, non una verifica SMTP, un consenso all'invio o una disponibilità a comprare.
- Una candidatura aperta può non generare risposta. Due clienti paganti al mese richiedono misurare anche contatti, risposte, preventivi e contratti.

## 7. Decisione

**GO per una successiva prova reale controllata, con riavvio preliminare del backend e budget esplicitamente verificati.** I blocchi riprodotti sui casi indicati non richiedono altre modifiche preventive o aumenti di spesa. La prova dovrà valutare autonomamente nuove fonti, rivedere tutti gli INTERESTING e un campione dei negativi, separando collaborazioni aperte da incarichi attuali.

**Nessuna prova reale è stata avviata qui.** Non si prosegue con funzionalità aggiuntive, inferenze a pagamento o ottimizzazioni marginali. L'autorizzazione a una campagna e la dimostrazione di efficacia commerciale sono passaggi successivi distinti.
