# CustomerSearch — audit architetturale e commerciale, Fase 1

20 ottobre 2026. Baseline: codice presente nel workspace, runtime dichiarato 9.2.2, inclusa la correzione del pianificatore effettuata durante la Campagna 43. Non è un audit di un commit pulito: il repository contiene molte modifiche preesistenti. Non sono state modificate sorgenti operative, configurazioni, campagne o dati commerciali durante questa fase.

## Conclusione

Il problema non è dimostrato essere la scarsità di clienti in Italia né il saldo dei provider. Il sistema trova alcune prove utili, ma la loro utilizzabilità commerciale viene subordinata a una combinazione di classificazioni, campi mancanti e controlli temporali pensati soprattutto per annunci. Parallelamente, buona parte della capacità AI viene impiegata prima di leggere gli originali. Una citazione testualmente corretta può inoltre essere collegata al soggetto o all'annuncio sbagliato.

**Raccomandazione:** conservare l'infrastruttura locale, ricostruire il confine fra interpretazione commerciale e verificabilità delle prove. Non sostituire tutte le regole con un prompt onnipotente. L'AI deve decidere se proporre un contatto; il software deve impedire che lo faccia con fonti inventate, relazioni non provate, azioni non autorizzate o dati incoerenti.

Sono disponibili due piste documentate di collaborazione, Kondividi e NHW Consulting, da proporre secondo la nuova semantica di outreach. Non sono due commesse, due preventivi o due clienti. Il CRM e il feedback dell'agente risultano vuoti nello snapshot: nessuna conversione commerciale è misurabile.

## Metodo e perimetro

- Stato iniziale: backend Python PID 16529 in ascolto su 127.0.0.1:8765; nessuna campagna running/waiting/stopping; 42 paused, 43 exhausted. Il processo non è stato interrotto.
- Database letto con URI `mode=ro`, `query_only` e snapshot transazionale per l'estrazione iniziale. Non è stato chiamato `Store.init()` sul database operativo.
- Fonti: codice, README/ARCHITECTURE/SECURITY/OPERATIONS, report 38/39/41/43, ledger SQLite, documenti originali salvati e fixture storiche. I report sono confrontati col database, non assunti come verità indipendente.
- 172 moduli Python sotto `sales/`; inventario di funzioni e dipendenze in [code-map.json](analysis-report/ai-first/code-map.json). L'analisi degli import, compresi quelli lazy, trova un componente fortemente connesso di 124 moduli: prova di accoppiamento statico, **non** di un errore runtime di import circolare.
- 92 test offline mirati superati; 13 casi reali congelati; 12 sonde diagnostiche, 9 conformi e 3 lacune. Nessuna inferenza o ricerca a pagamento. Nessun nuovo test browser live o audit di vulnerabilità esterno.
- Integrità SQLite: `quick_check = ok`. Hash di database/WAL e sorgenti applicative confrontati in [preservation-result.json](analysis-report/ai-first/preservation-result.json). Questa verifica non è una prova universale di sicurezza.

## Architettura effettiva

`app.py → sales.server.main → CampaignManager → research_worker → commercial.coordinator.run_campaign → AgentCoordinator` per i filtri agent6. Esiste ancora un percorso di ricerca precedente: una campagna priva del discriminante dell'agente non usa automaticamente i cinque flussi nuovi.

| Responsabilità | Codice effettivo | Osservazione |
|---|---|---|
| Avvio/API/UI | `sales/server.py:214,231`, `static/agent6.js`, `static/worklist.js` | Server locale, API diverse per storico, commercial e agent6; `state()` espone ancora version `6.0` mentre il runtime è 9.2.2. Disambiguare versione API e versione motore. |
| Lifecycle persistente | `sales/campaigns.py`, `sales/research_store.py:161,188` | Worker separato, generation token, Stop/Riprendi, configurazione snapshot, coda SQLite. Da preservare. |
| Coordinamento | `sales/agent6/coordinator.py` (600 righe), `sales/commercial/coordinator.py` (452) | Ereditarietà del coordinatore commerciale; pianificazione, acquisizione, screening, lettura, salvataggio, errori e follow-up nella stessa classe. |
| Provider e acquisizione | `sales/providers.py:42`, `sales/research_analysis.py:18,38`, `sales/serper_provider.py` | TLS, IP pubblici, robots, PDF, cache e ricevute già disponibili. |
| Interpretazione | `agent6/schema.py`, `grounding.py`, `ai.py` | L'AI produce kind, citazioni e missing; non produce direttamente una decisione commerciale autonoma INTERESTING/NOT_INTERESTING/NEEDS_RESEARCH. |
| Decisione effettiva | `qualification.py:117,163`, `requirements.py`, `completion.py`, `semantics.py`, `commercial_roles.py`, `alignment.py` | Più passaggi possono aggiungere missing, cambiare kind, correggere identità e riscrivere stato. |
| Proattivo/browser | `agent6/proactive.py`, `website_audit.py`, `website_review.py`, `commercial/target_fit.py`, `commercial/browser.py` | Percorso distinto con preselezione, browser e valutazione del progetto. Non è lo stesso percorso delle richieste. |
| Fonti e identità | `extract.py`, `research_analysis.identity_from`, `commercial/identity.py`, `entity_scope.py`, `agent6/site_identity.py`, `document_units.py` | Strati utili ma contratti non uniformi, dati persi fra parser e chiamata AI. |
| Memoria e presentazione | `agent6/memory.py`, `learning.py`, `commercial_view.py`, `commercial_score.py`, `worklist.py` | Memoria osservazionale; tre rappresentazioni parzialmente sovrapposte della qualità commerciale. |

Le dipendenze non giustificano microservizi o un nuovo framework. Il vantaggio maggiore viene da contratti interni univoci e da un solo punto decisionale.

## Campagne storiche: denominatori corretti

Fonte riproducibile: [historical-metrics.json](analysis-report/ai-first/historical-metrics.json). “Originali” indica **record canonici con `original=true`**, non numero di pagine HTTP lette, né originali validati commercialmente. “Identità” indica record con identità verificata, non tutti clienti compatibili. Esclusi dal conteggio canonico i record con `canonical_record_id`.

| Campagna | Stato | Richieste provider contabilizzate | AI | Originali | Identità | VERIFIED/POTENTIAL | USD AI stimati |
|---|---|---:|---:|---:|---:|---:|---:|
| 37 | exhausted | 16 | 100 | 8 | 0 | 0 | 0,329416 |
| 38 | exhausted | 37 | 100 | 22 | 12 | 0 | 0,279178 |
| 39 | exhausted | 35 | 100 | 21 | 9 | 0 | 0,249648 |
| 41 | exhausted | 72 | 100 | 26 | 11 | 0 | 0,291775 |
| 42 | paused, percorso precedente | 242 tentativi di rete nelle ricevute legacy | 0 nel ledger commercial AI | n.c. | n.c. | 0 qualified nelle 77 assessment legacy | non attribuibile integralmente |
| 43 | exhausted | 43 | 100 | 27 | 5 | 0 | 0,284215 |

La 42 ha filtri soltanto `target, regions`: 251 task search, 245 done; 242 ricevute search con rete dichiarata e 242 crediti stimati. Non va riportata come ricerca gratuita perché il ledger nuovo ha zero righe. Le 77 assessment sono 30 needs_review, 37 rejected, 10 unverifiable. Nessun confronto causale con il motore nuovo.

| Campagna | Plan | Replan | Screen, incluse riparazioni | Verify, incluse riparazioni/completamenti |
|---|---:|---:|---:|---:|
| 37 | 3 | 47 | 40 | 10 |
| 38 | 5 | 37 | 50 | 8 |
| 39 | 5 | 16 | 72 | 7 |
| 41 | 5 | 37 | 56 | 2 |
| 43 | 5 | 16 | 66 | 13 |

Per 37/38 è ricostruito lo stadio salvato nel ledger: non inventato un `purpose` inesistente. Per 43 i 13 verify comprendono 9 original_verification, 2 recuperi su originale e 2 dossier_completion. I cinque flussi consumano rispettivamente 7, 39, 3, 11, 40 chiamate (AZIENDE, AGENCIES, SOCIAL, STARTUPS, NEWS). NEWS usa 33 screening e non arriva a record originali.

### Cosa dimostra ogni campagna

- **37:** 19 record fermati con `no_potential_buyer_identity`, 16 classificati EMPLOYEE_JOB; 50 chiamate di pianificazione e zero identità verificate. Il report 38 conferma 79 output validi, 10 parziali, 11 invalidi nella 37. Non sono stati riesaminati manualmente tutti gli annunci della 37: non si quantificano commesse perse.
- **38:** l'acquisizione aumenta, ma 34 record restano senza soggetto e 22 vengono classificati dipendenti. Il report e la prova salvata di Kondividi identificano una disponibilità a collaborare, non un incarico retribuito confermato. Robots HTML e dimensione delle pagine bloccano alcune letture.
- **39:** meno pianificazione (21 chiamate), ma 72 screening contro 7 verify. 52 record fermati senza identità, 36 senza ragione commerciale citata. Migliorare solo il planner ha spostato il consumo sullo screening; non prova un miglioramento della selezione finale.
- **41:** 88 record senza identità, 43 senza ragione citata. NHW perde l'identità per la forma del nome; Punto Infissi eredita il ruolo del fornitore multinazionale. **Il replay col codice attuale recupera entrambi questi passaggi**: NHW resta NEEDS_REVIEW solo per publication; Punto Infissi diventa adatto all'audit, non qualificato. Non riproporre come ancora irrisolto il vecchio bug di alias/gruppo.
- **42:** percorso legacy ancora raggiungibile, 77 valutazioni ma zero qualified. 12 task registrano esclusione PDF e altri accessi robots/403. Gli errori PDF non sono qui aziende scartate automaticamente: non sommare task esclusi e assessment.
- **43:** 238 URL distinti, 216 record canonici: 170 DISCOVERED, 17 NEEDS_REVIEW, 25 REJECTED, 4 UNVERIFIABLE. Una pista partnership utile e diversi errori intermedi dimostrabili. 434 operazioni di pianificazione fallite prima del recupero origin; 473 piani salvati, solo 21 chiamate AI di pianificazione. I contatori di memoria non rappresentano altrettante strategie testate.

Costi per opportunità qualificata: **non definibili**, denominatore zero. Per le due piste di outreach trovate retrospettivamente non è corretto dividere la spesa e dichiarare un costo di acquisizione: il campione è selezionato, le aziende ricompaiono e non esistono clienti acquisiti registrati.

## Registro dei problemi sistemici

F = fatto verificato; H = ipotesi da misurare; R = raccomandazione. Le cause seguenti si riferiscono al codice attuale salvo indicazione storica.

| ID / priorità | Modulo e comportamento | Evidenza e causa | Conseguenza commerciale | R: soluzione progettuale |
|---|---|---|---|---|
| A1 / P0 | `qualification._evaluate`, `requirements.PROFILES` | **F:** AGENCY_PARTNERSHIP richiede publication; anche `standing=true` finisce con missing publication se non RECENT. Kondividi 1021; replay NHW 781. | Inviti permanenti utili non diventano contatti proponibili. | Distinguere stato temporale dell'invito permanente da scadenza di una vacancy; decisione commerciale autonoma. |
| A2 / P0 | `alignment.dimensions`, `commercial_score.dimensions`, `commercial_view.enrich` | **F:** qualified deriva da VERIFIED/POTENTIAL; interest SUPPORTED e READY dipendono da qualified. “Dimensioni indipendenti” non lo sono pienamente. | Informazione mancante sulla data si propaga fino alla lista da contattare. | Decision, confidence, readiness separati; proiezione unica per API/UI. |
| A3 / P0 | `coordinator.reading:449–455`, `document_units.extract:9–45` | **F:** originali precedenti riaggiunti allo stesso result_id r1; unità riconosciute solo con Azienda/Company/Employer e Candidati/Apply ripetuti. Drupal usa Organizzazione. Record 1139 Elice associato a dettaglio ilGiornale. **H:** l'eredità delle prove è il vettore più probabile; non attribuita la responsabilità a una singola risposta AI senza replay completo. | Citazioni valide del documento A usate come conferma del documento B. | Grafo documento→unità→attore→richiesta; relazione di dettaglio verificata prima di unire prove. |
| A4 / P0 | `qualification.temporal:17–46`, `extract.parse_page:92–118`, `coordinator.reading:419` | **F:** date numeriche italiane non etichettate e “Postato il” non riconosciute; lettura temporale limitata ai primi 1600 caratteri. Trasferito job_date solo da JobPosting. Tre sonde offline falliscono. | Richieste 2015 restano UNKNOWN; ripetuti approfondimenti inutili. | Date candidate tipizzate per unità con fonte, precisione e conflitti; parser non unico scalare. |
| A5 / P1 | `providers.PublicWeb._raw`, `inspection.document`, `coordinator.reading:397` | **F:** redirect chain presente nel fetch ma checkpoint richieste conserva solo url/status/html/checked_at/content_type; Last-Modified non esposto; canonical/modified/expiry non hanno un contratto unico verso AI. | Ricostruzione incompleta di provenienza e validità; si ripaga la ricerca di dati già presenti. | Snapshot HTTP/DOM unico e immutabile, riusato senza perdita di metadati. |
| A6 / P0 | `commercial_policy.investigation`, `coordinator.offer6`, `budget.available`, `scheduling.choose` | **F:** accesso alla verifica subordinato a kind/nome/regex; nella 43 156 record riportano no_identity/no_reason. Riserve proteggono soprattutto lavoro già ammesso. | Se non si ammette una pista, il budget destinato alla sua verifica può essere consumato altrove. | Acquisizione originale economica prima della decisione semantica; scheduler su azioni decisive, non numero di snippet. |
| A7 / P1 | `target_fit.source_role`, `proactive.run:82–113` | **F:** università/camera di commercio entro i primi 16000 caratteri può attribuire institution all'intero sito; CerealVeneta originale classificato institution nella sonda corrente. | Produttore escluso per una notizia accessoria, non per la propria attività. | Ruolo riferito a soggetto e sezione; classificazione AI con prove di ruolo e controprove. |
| A8 / P1 | `source_subjects.directory_subjects`, `site_identity.resolve`, `proactive.run` | **F:** handoff directory supporta solo JSON-LD ItemList/Organization con dominio esterno, massimo tre soggetti. Record 955 arriva all'editore ReportAziende. | Audit su editore/associazione anziché sul soggetto cercato. | EntityCandidate separato da SourceOwner; link di ruolo e relazione verificati, nessun fallback automatico al dominio root. |
| A9 / P1 | `schema.validate_fields`, `grounding.segments`, `ai.call` | **F:** 43: 83 unsupported_actor, 14 unsupported_kind, 9 unknown_or_ambiguous_segment, 1 non_company_identity. Il limite input conta byte includendo schema; prova può essere troncata. **H:** contributo di granularità segmenti rispetto agli errori semantici non quantificato. | Riparazioni costose e prove decisive omesse; allentare validazione non risolve il significato. | Tenere riferimenti forti; separare invalidità strutturale da disaccordo commerciale, registrare copertura e ragioni dei tagli. |
| A10 / P1 | `proactive.run`, `website_review`, `commercial/browser.py` | **F:** 43 tre audit PARTIAL, zero COMPLETE; due target di scarso interesse, nessun viewport completato. | Browser oneroso prima che il caso commerciale sia chiaro. | Browser solo se risolve una domanda concreta non risolvibile da HTML; errore tecnico non diventa difetto del sito. |
| A11 / P1 | `memory.history`, `learning.summarize` | **F:** selection_count conta piani chosen anche falliti prima del dispatch; 43 contiene centinaia di tali selezioni. **H:** quanto altera esplorazione futura non misurato live. | Statistiche di strategia e pianificazione possono essere influenzate da guasti, non dal mercato. | LearningReceipt soltanto per azione realmente eseguita; proiezione versionata che esclude fallimenti tecnici senza cancellare storico. |
| A12 / P1 | `agent6.ai.call`, `coordinator.model/planning/reading` | **F:** mode shadow è trasportato nel ledger, ma gli output pianificano e alimentano il percorso reale; non c'è confronto sperimentale separato fra due decision engine. | “Shadow” suggerisce un'autorità diversa da quella reale. | Esplicitare research enabled, decision mode, execution authority; migrazione senza attivazioni automatiche. |
| A13 / P2 | `server.state`, API legacy/commercial/agent6 e worklist | **F:** percorso 42 e versioni API/runtime differenti, molte proiezioni dello stesso stato. | L'utente non sa quale motore stia lanciando né perché una pista sparisca. | Versione motore richiesta nei nuovi avvii, nessun fallback silenzioso, unica scheda/proiezione canonica. |

### Cosa è già corretto e va conservato

Correzione origin della 43 e isolamento dell'errore del planner; identità NHW/Punto Infissi nel replay corrente; citazioni per segmenti hashati; rifiuto di budget inventati; distinzione equity/retribuzione; contatti pubblici generici ammessi; esclusioni manuali e CRM; stop con generation; prenotazioni atomiche; checkpoint; deduplicazione e revisioni; esclusione PDF; robots/TLS/SSRF e proxy browser. Il nuovo sistema deve dimostrare di non perderli.

## Sicurezza e affidabilità: evidenze, non certificazioni

| Area | Verifica nel codice/test | Limite o requisito residuo |
|---|---|---|
| SQL | Valori parametrizzati in Store/ResearchStore e API esaminate; transazioni e foreign_keys. | Non è revisione esaustiva di ogni query dinamica; testare nuovi filtri con payload SQL. |
| XSS/CSRF | `Handler.reply` CSP, nosniff; `do_POST:118` Host/Origin/token e corpo ≤100000; rendering `esc`/helper link; test HTTP offline. | Non autenticazione multiutente. Un processo locale con stessi privilegi rimane nel trust boundary. |
| SSRF/redirect/TLS | `PublicWeb._raw` risolve e fissa IP pubblico, ricontrolla redirect, usa default TLS; `SafeProxy.public_addresses` restringe 80/443; browser intercetta GET e blocca altri metodi, websocket/service worker/download. | Attestazione di controlli e regressioni, non penetration test esaustivo; parser ostili e ambiente Chromium restano superficie d'attacco. |
| Prompt injection | SYSTEM tratta fonti/memoria come dati; schema/segmenti e worker senza strumenti di invio. | Una citazione valida può sostenere una conclusione sbagliata; non basta il prompt. Budget, strumenti ed entity edges devono restare fuori dall'autorità AI. |
| Segreti/log | Provider non serializza error body o headers; diagnostics.scrub/purge; test provider. | Prove e backup possono contenere dati personali/debug dei siti: vault locale privato, export minimizzato; evitare logging completo di prompt e ambiente. |
| Retry/Stop | generation e reservation ledger; scheduler persistente; 43 ha mostrato un buco del planner già corretto. | Restart e migrazione non devono avviare lavoro; contare tentativi reali, distinguere retryable da semantic invalid. |
| Integrità/backup | SQLite quick_check ok; test backup/ripristino su copie e startup prima delle migrazioni. | Nessun ripristino della produzione eseguito in questa fase. Le nuove migrazioni richiedono prova su copie complete. |

I 92 test includono lifecycle, scheduling, allineamento commerciale, identità, scope, backup, HTTP, adattatore OpenAI e trasporto simulato. [Log completo](analysis-report/ai-first/regression-tests.txt). Non dimostrano che le query trovino clienti: il benchmark aggiuntivo evidenzia lacune che la suite esistente non copriva.

## Decisione proposta

Approvare il disegno dei contratti e della semantica nei documenti allegati; implementare solo dopo una nuova autorizzazione. Prima milestone: estrazione e attribuzione dei 13 casi congelati, confronto indipendente delle decisioni commerciali, UI coerente con partnership/commesse. Non aumentare budget per compensare queste lacune.
