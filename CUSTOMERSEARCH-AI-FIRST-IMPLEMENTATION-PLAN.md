# CustomerSearch — piano coordinato di implementazione AI-first

**Documento di approvazione, non attività già eseguite.** In questa Fase 1 sono stati prodotti audit, benchmark e progettazione; non si è implementata la nuova architettura.

## Obiettivo verificabile

Una pagina come Kondividi/NHW può diventare una collaborazione interessante e contattabile senza inventare un incarico aperto. Un annuncio 2015 e un editore scambiato per cliente non possono diventare opportunità attuali. Un browser fallito non prova un difetto commerciale. Il sistema deve completare un ciclo di ricerca con meno lavoro sprecato, mantenendo storico, CRM, sicurezza e costi.

## Decisioni da approvare insieme

1. AI come autore del giudizio commerciale con tre decisioni; codice come validatore di prove/policy/esecuzione.
2. Rapporto e servizio separati; partnership/candidature disponibili nella lista utile anche con progetto pagato UNKNOWN; equity in lista distinta.
3. Acquisizione originale prima dello screening semantico costoso, salvo preselezione ambigua giustificata.
4. Documenti/unità/relazioni/date tipizzati e revisioni append-only.
5. Vecchi stati conservati, nessuna riqualifica automatica massiva dello storico.
6. Budget invariati; quote proposte da validare offline prima di approvare un'altra prova reale.

## Inventario delle componenti

| Azione | Componenti | Motivo e confine |
|---|---|---|
| Mantenere | `sales/db.py`, `campaigns.py`, coda `research_store.py`, ledger `commercial/ai.py`, provider `commercial/ai_provider.py` | Storage, lifecycle, prenotazioni, cancellazione e trasporto già testati; estendere contratti, non duplicarli. |
| Mantenere e adattare | `providers.py`, `safe_proxy.py`, `commercial/browser.py`, `content_policy.py`, cache/Serper | Acquisizione protetta e PDF; aggiungere metadati persistenti senza eccezioni di rete. |
| Consolidare | `extract.py`, `research_analysis.document`, `commercial/inspection.document`, `agent6/document_units.py`, `source_scope.py`, `passages.py` | Un EvidenceDocument/Unit; evitare date e redirect persi nei passaggi. |
| Consolidare | `commercial/identity.py`, `entity_scope.py`, `agent6/site_identity.py`, `identity_aliases.py`, `entities.py`, `canonical_records.py` | Ruoli e relazioni espliciti; mantenere alias/merge provati, eliminare eredità implicita. |
| Sostituire nel nuovo percorso | `agent6/qualification.py`, `requirements.py`, parti semantiche di `commercial_policy.py`, `target_fit.py` | Autorità commerciale a decision engine; separare policy utente e sicurezza dalle euristiche di mercato. Il legacy resta per replay. |
| Adattare | `agent6/schema.py`, `grounding.py`, `ai.py`, `diagnostics.py` | Nuovo schema decisionale e action proposal; citazioni e partial recovery conservate. |
| Ridurre/consolidare | `completion.py`, `recovery.py`, `field_recovery.py`, `semantics.py`, `commercial_roles.py` | Una fase di validazione/contestazione, un recupero esplicito per domanda, non più catene di riscritture dello stato. |
| Adattare | `agent6/coordinator.py`, `scheduling.py`, `budget.py`, `strategies.py`, `query_pipeline.py` | Separare esecutore da planner; cinque strategie preservate, completamento prima dell'espansione. |
| Consolidare proiezione | `alignment.py`, `commercial_score.py`, `commercial_view.py`, `worklist.py`, `api.py` | Un significato per interesse, confidenza, readiness e conteggi. |
| Mantenere con nuova receipt | `memory.py`, `learning.py`, `annotations.py`, Store CRM | Apprendimento su azioni eseguite e giudizi umani, con denominatori. |
| Adattare UI | `static/agent6.js`, `worklist.js`, `server.py` | Contratto versionato, nuove liste; pipeline, conferma contatto, elimina, note e bozze preservate. |

Massimo cinque nuove responsabilità locali, come moduli a namespace proposto `sales/intelligence`: contracts, evidence, attribution, decisions, research. Le proiezioni possono restare nei moduli API esistenti. Nessun nuovo agente autonomo per ogni responsabilità. Il nome definitivo del package non è un requisito di prodotto.

## Ordine esatto, dipendenze e completamento

### 0 — Baseline, permessi e backup

Prima di implementare, rilevare campagne attive; non interromperle senza necessità/autorizzazione. Congelare hash codice, schema, configurazioni, righe e CRM; backup con `scripts/backup.py`, verifica ripristino su copia privata, nessun ambiente segreto nelle fixture. Salvare golden data e test del presente audit.

Completamento: ripristino su copia riuscito, integrità e conteggi coerenti, test isolati; chiaro baseline commit/workspace senza commit automatico. Rischio: confondere file non tracciati con file eliminabili. Non fare pulizie in questa fase di implementazione.

### 1 — Contratti e schema additivo

Definire JSON schema/enum/nullability di documenti/unità/claim/decision/action e proiezione. Implementare migrazione `ci_` transazionale/idempotente e adapter legacy di sola lettura. Non introdurre inferenze nel codice di migrazione. Stabilire idempotency e versioni dei contratti prima dei prompt.

Dipende da 0. Test: seconda migrazione no-op, FK e rollback su errore, apertura legacy, report 37–43 invariati, CRM/feedback/esclusioni intatti. Completamento: nessun record storico cambiato, nessuna promozione implicita. Rollback: disabilitare engine nuovo; sidecar rimane, non DROP automatico.

### 2 — Acquisizione, metadati e unità

Adattare PublicWeb/Document/inspection; conservare chain e headers ammessi; estrarre JSON-LD, OG, canonical, time, date visibili, RSS/sitemap. Date per soggetto e ruolo; osservazione non pubblicazione. Card e link di dettaglio conservano lo scope. Raw HTML mancante è dichiarato, non sintetizzato nei dati storici.

Dipende da 1. Test: A–M, varianti date, più JobPosting e conflitti, body limits/PDF/robots invariati, redirect e SSRF. Completamento: hash/spans riproducibili e tutte le date critiche attribuite; nessuna chiamata AI necessaria per estrarre dati espliciti. Rischio: over-segmentation; fallback UNKNOWN con ricerca mirata.

### 3 — Identità, ruoli e consistenza fra documenti

Implementare EntityCandidate/edges e validatore di dettaglio. Separare publisher e subject; confrontare nomi, contesto richiesta e riferimenti ufficiali prima di collegare. Identità giuridica facoltativa quando brand e dominio sono sufficientemente provati; omonimi non uniti. Supplier non diventa owner/group.

Dipende da 2. Test: Elice/ilGiornale, ReportAziende, NHW alias, Punto Infissi, omonimi, dominio esterno/ATS e canonical malevolo. Completamento: zero contaminazioni critiche nei casi noti; mapping storico reversibile. Rischio: falso mancato match; conservare incertezza e domanda di verifica, non inventare merger.

### 4 — Decision engine commerciale

Nuovo contratto AI con INTERESTING/NOT_INTERESTING/NEEDS_RESEARCH, rapporto/servizio, ragioni/controprove e azione. Profilo Diego versionato, fasce indicative, inviti permanenti ammessi, supporto/frontend valutato nel contesto del rapporto. Codice valida riferimenti e policy; un validator lessicale non può imporre SUPPLIER_OFFER perché un'agenzia descrive anche i propri servizi.

Dipende da 1–3. Primo sviluppo con output congelati e fixture chiaramente etichettate; inferenze remote solo con autorizzazione. **Non contare mock e decisioni hardcoded come benchmark AI.** Completamento offline del contratto: casi critici, unsupported claims isolati, zero invii, unknown preservati. Completamento semantico: holdout e soglie del benchmark, ancora da dimostrare. Nessuna switch automatica in produzione dopo i soli unit test.

### 5 — Planner, scheduler e budget

Azioni con domanda/subject/evidence_version; capacità riservata al ciclo completo, stessi hard maxima. Cinque flussi attivi con priorità proposte; nuove query solo se esiste spazio per una valutazione originale. Stop/resume e replay receipt senza addebiti duplicati. Un errore di planner blocca quel ramo, non crea centinaia di task.

Dipende da 4; contratti action già definiti in 1. Test: global/flow/candidate budget, starvation, release riserve, cancellazione in ogni confine, timeout/retry, conclusione senza loop, ripresa fra fetch/infer/save. Completamento: scenario equivalente alla 43 consuma una query per scelta e termina correttamente con input/mock ripetibili. Non dichiarare risparmi live da un replay.

### 6 — Proiezione unica, UI e CRM

Integrare API intelligence e adapter legacy. Schede partnership/progetti/equity, badge freshness e contatti; conteggi coerenti con filtri. Distinguere runtime, schema e API version. Nuove campagne richiedono scelta motore esplicita; campagne vecchie continuano col proprio snapshot. Proporre una nuova voce “Analisi comparativa” soltanto se esiste un vero shadow: doppia decisione senza doppie azioni a pagamento nascoste.

Dipende da 4–5. Test desktop/mobile su server locale isolato: filtri, empty/error/loading, long text, duplicati, conferma verde, pipeline drag/drop, elimina/ripristina, note/bozze. Completamento: nessun dato storico perso; “da contattare” non esclude un invito permanente solo per publication UNKNOWN. Rischio: elenco gonfiato; disaggregare sempre opportunità outreach e incarichi attivi.

### 7 — Memoria operativa e rollout controllato

Agganciare decision/action receipts e feedback al calcolo delle priorità. Non modificare i record della 43: una vista ignora i chosen senza receipt ai fini della resa. Le annotazioni corrette manualmente hanno provenienza e non cancellano il risultato del modello. In assenza di esiti, mostrare “nessun dato di conversione”.

Dipende da 5–6. Test: stessa pagina in due campagne, segnali nuovi, stesso comunicato ripubblicato, azienda contattata/non contattare, feedback contraddittorio, denominatori minimi. Completamento: priorità spiegabili e nessuna blacklist commerciale da un singolo errore tecnico.

### 8 — Validazione finale e decisione live

Eseguire suite regressioni + holdout semantico, revisione indipendente, test migrazione/restore e differenze dati/API/UI. Pubblicare risultati, fallimenti e costi; fermarsi per nuova approvazione se non supera i criteri. Una prova live è fase distinta: esplicita autorizzazione, budget congelati, nessun invio. Dopo la prova, rivedere tutti gli INTERESTING e un campione stratificato dei negativi; nessuna ottimizzazione retroattiva delle soglie sullo stesso test.

Completamento prodotto richiede risultati utili nuovi e revisionati, non soltanto la chiusura degli otto passi tecnici.

## Rollback e compatibilità

Ogni step rilasciabile dietro engine_version/config flag; campagne in corso mantengono il loro motore, niente cambio codice semantico a metà campagna. Nuovi record sidecar linkano IDs esistenti; il legacy non legge sidecar per promuovere automaticamente. Rollback preferito: disabilitare nuovo avvio, lasciare storico consultabile e usare percorso precedente. Ripristino completo DB solo su copia verificata, con backup dello stato corrente e procedura esplicita; non perdere CRM creato dopo il backup. Non annullare spese API o consensi tramite rollback software.

## Rischi e scelte di controllo

| Rischio | Controllo | Evidenza richiesta |
|---|---|---|
| AI più permissiva genera falsi positivi | Gold holdout, controprove, claim/identity/unit gate | Zero falsi positivi critici, precisione ≥90% su campione minimo |
| Più originali aumentano HTTP/tempo | Fetch economico, cache, priorità, browser solo mirato | Latenza p50/p95 e costo per dossier utile; nessun aumento budget implicito |
| Ridurre regex perde protezioni | Separare security/policy da heuristics; suite negativa | SSRF/PDF/CSRF, known-wrong attribution e closed jobs invariati |
| Compatibilità incompleta | Dual-read versionato, conteggi e test migrazione | Report/CRM/feedback storici identici |
| Semantica Shadow ambigua | Autorità ricerca/decisione/invio separate | UI e ricevute spiegano quali output guidano azioni reali |
| Date indefinite inviti obsoleti | TTL verifica e controprove chiusura/abbandono | Evergreen distinto da vacancy vecchia; niente “attivo” senza prova |
| Memoria automatica rinforza errori | Review provenance, sample sizes, esiti tecnici separati | Nessuna priorità causata da 434 errori del planner come se fossero ricerche |

## Stima e primo passo

Non è una patch da poche ore: le fasi 2–5 sono il cambiamento principale e richiedono integrazione, replay e revisione. Non assegno una durata certa senza misurare la prima milestone. Il primo passo dopo approvazione è formalizzare contratti/label e migrazione su copia; poi estrazione/attribuzione dei 13 casi. Non partire da più query o da un nuovo prompt gigantesco.

**Condizione per procedere:** approvazione dell'architettura e della semantica di opportunità outreach. Nessuna implementazione di questo piano è stata avviata autonomamente.
