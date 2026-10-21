# CustomerSearch — implementazione AI-first

Data: 20 ottobre 2026. Implementazione locale e collaudo offline; nessuna campagna, inferenza remota, richiesta Serper, email, commit o push effettuati.

## Risultato e confini

Le nuove campagne create dalla UI/API utilizzano `decision_engine=ai_first_1`. Il coordinatore, i cinque flussi, la coda persistente, i budget, il trasporto AI e il CRM restano quelli esistenti. Non è stato introdotto un secondo worker o framework.

Il nuovo percorso è:

1. Pianificazione AI con ipotesi, domanda verificabile, fonte attesa e condizione di arresto.
2. Query validate e deduplicate, rispettando quote e disponibilità della verifica.
3. Lettura protetta dell'originale e checkpoint persistente. Nessuna inferenza commerciale a pagamento sugli snippet.
4. Decisione AI con prove: `INTERESTING`, `NOT_INTERESTING`, `NEEDS_RESEARCH`.
5. Eventuale lettura di un link osservato, ricerca sul soggetto oppure verifica browser circoscritta, entro profondità e risorse configurate.
6. Proiezione del giudizio nella Worklist, con interesse, solidità delle prove e disponibilità del contatto separati.

Una collaborazione aperta o una candidatura spontanea può essere interessante anche senza budget o data di pubblicazione: la scheda non la presenta come incarico pagato disponibile. Proposta proattiva, equity e richiesta esplicita hanno etichette distinte. Il valore economico ignoto resta ignoto.

## Un'autorità commerciale

`sales/agent6/decision.py` definisce il contratto e materializza il giudizio del modello. I validator controllano struttura, citazioni, identità, geografia, attualità, ambito delle azioni e policy; non sostituiscono il giudizio con i vecchi classificatori commerciali.

`alignment.py` e `commercial_view.py` riconoscono il nuovo contratto prima del ramo legacy. Non ricalcolano il giudizio AI con `qualification`, `completion`, `semantics`, `commercial_roles` o `commercial_score`. Soppressioni e risultati CRM continuano a impedire contatti indesiderati. La scadenza della verifica può togliere una scheda da “pronta”, senza inventare un nuovo giudizio commerciale.

I tre nuovi moduli, nello stesso package esistente, sono:

| Modulo | Responsabilità |
|---|---|
| `evidence.py` | Metadati, unità, date per ruolo, link osservati, citazioni e offset |
| `decision.py` | Schema, validazione e materializzazione della decisione AI |
| `research.py` | Esecuzione del percorso originale → decisione → approfondimento |

Si riutilizzano estrazione HTML, identità, acquisizione HTTP, cache, ricevute, budget e scheduler. Il parser canonical duplicato è stato consolidato in `sales.extract.Document`; il controllo della struttura JSON è condiviso tramite `schema.shape`.

## Prove, isolamento e recupero

- Conservati URL iniziale/finale, redirect disponibili, canonical, HTTP, intestazioni ammesse, JSON-LD, Open Graph, titoli, date e momento di osservazione.
- Le card con organizzazioni distinte e gli oggetti JobPosting diventano unità separate. Gli offset delle card rimandano al documento originale; il JSON-LD ha una rappresentazione persistita con hash e documento padre.
- Una pagina collegata non eredita l'identità del risultato precedente solo perché è raggiungibile da un link. Il collegamento richiede il soggetto nuovamente verificato e la destinazione coerente.
- Citazioni inesistenti, snippet usati come originali e riferimenti ad altre unità sono respinti.
- Una richiesta scaduta o datata non diventa attuale grazie alla data di consultazione. Una data numerica senza ruolo resta non assegnata.
- Un fallimento tecnico del modello non significa “azienda non interessante”. Un replay incompleto sullo stesso snapshot conserva l'ultima decisione valida e registra il tentativo. Una fonte cambiata richiede una nuova valutazione.
- Un fallimento browser non viene trasformato in difetto del sito. Le misure disponibili hanno documenti e provenienza separati.

## Budget, memoria e lifecycle

I massimi configurati non sono aumentati. Il ramo nuovo elimina la quota per screening semantico degli snippet e riserva capacità alla verifica delle pagine, usando il ledger comune e i limiti globali, per flusso e candidato. Una ricerca non viene pianificata come lavoro utile se manca capacità per verificarla.

Checkpoint originali, cache e ricevute evitano una nuova acquisizione/inferenza nel replay verificato. Stop impedisce scritture tardive; le campagne sospese mantengono lo snapshot del proprio motore.

La memoria considera le query effettivamente eseguite, non soltanto proposte. Feedback, aziende contattate ed esclusioni restano persistenti. Le priorità sono descrittive: nessuna dichiarazione di apprendimento predittivo o probabilità di vendita.

## Compatibilità e scelta architetturale

Nessuna migrazione del database operativo: il discriminante e i dati nuovi usano i campi JSON e le revisioni esistenti. È una semplificazione rispetto al piano iniziale di introdurre nuove tabelle `ci_`.

Il nome `agent6` e la versione del contenitore storico restano per compatibilità; `decision_engine` identifica il nuovo comportamento. Il percorso HTTP di creazione richiede esplicitamente i flussi dell'agente e usa AI-first; il vecchio percorso rimane per replay, ripresa di campagne storiche e rollback.

Il motore legacy completo **non è stato eliminato**: una campagna precedente è ancora sospesa e il nuovo modello non ha una validazione semantica indipendente. La sua rimozione richiede tale validazione, verifica del rollback e una decisione esplicita sulle riprese storiche. La lettura dei dati storici non autorizza a conservare due percorsi per nuove decisioni: il ramo pubblico nuovo è uno solo.

La configurazione chiamata Shadow non costituisce un confronto fra due decisori: l'anteprima lo chiarisce. Nel ramo AI-first il modello decide, mentre codice e policy validano. Nessuna doppia inferenza nascosta.

## Test e benchmark

| Verifica | Esito |
|---|---|
| Baseline | 1.909 test; due errori preesistenti per metriche archiviate non trovate |
| Suite completa dopo implementazione | **1.943 test, OK**, 389 secondi |
| Ultime integrazioni | **91 test, OK** |
| Hardening finale su citazioni, scadenze e replay | **120 test, OK** |
| UI Chromium isolata | 1440 e 390 px: schede, filtri, dossier, nessun overflow o errore JavaScript |
| JavaScript e whitespace | `node --check` e `git diff --check`, OK |
| Database e archivio | Entrambi integri, tutte le tabelle invariate; 557 membri ZIP verificati |

I due test baseline sono stati corretti usando il lettore ZIP esistente, conservando gli stessi controlli. Un comando intermedio di hardening indicava due nomi di moduli inesistenti: corretto il comando, i 120 test effettivi passano. I log intermedi non sono occultati.

La suite copre cinque flussi, quote condivise, candidato, Stop/Resume, cache, attribuzione, PDF, policy, CRM, HTTP e regressioni UI. Il test del nuovo percorso impedisce esplicitamente l'esecuzione del vecchio qualificatore e verifica acquisizione originale → decisione salvata → Worklist → replay senza nuova inferenza.

Il benchmark di estrazione usa **13 casi storici e 33 documenti congelati**, verificandone gli hash; conserva 21 date esplicite o non assegnate. Non scarica nuove fonti e non sintetizza HTML mancante. Le due opportunità di collaborazione note non erano promosse nella baseline: questo è un dato storico, **non** una misura dell'accuratezza del modello nuovo.

I provider simulati verificano contratti ed esecuzione, non intelligenza commerciale. Precisione, recall su holdout, resa reale delle query e conversioni rimangono **non misurate**. Non è corretto dichiarare risolto l'acquisto di clienti sulla base di questi test.

Artefatti:

- `implementation-report/ai-first/final-tests.txt`
- `implementation-report/ai-first/final-changes-tests.txt`
- `implementation-report/ai-first/hardening-final.txt`
- `implementation-report/ai-first/ui-tests.json`
- `implementation-report/ai-first/benchmark.json`
- `implementation-report/ai-first/integrity-after.json`

Riproduzione senza crediti:

```bash
PYTHONPATH=tests/offline_guard:.:tests .venv/bin/python -B -m unittest discover -s tests
PYTHONPATH=tests/offline_guard:.:tests .venv/bin/python -B scripts/benchmark_ai_first.py --ai-first-extraction --output implementation-report/ai-first/benchmark.json
PYTHONPATH=tests/offline_guard:.:tests .venv/bin/python -B scripts/check_agent921_ux.py --ai-first
```

I test browser/HTTP richiedono la possibilità di aprire un listener locale e Chromium; i provider esterni e le scritture al database operativo sono bloccati dal guardiano dei test.

## Limiti e prossimo controllo

L'identità non risolta, i blocchi legittimi delle fonti, il contesto limitato e la separazione non riconosciuta di card possono ancora lasciare candidati da approfondire. La lettura seleziona estratti: non equivale a una revisione integrale del sito. Nessun accesso autenticato o aggiramento è stato introdotto.

Prima di dichiarare efficacia o rimuovere il rollback servono una validazione semantica indipendente e una prova reale autorizzata, con revisione di positivi e negativi e budget espliciti. Le soglie del benchmark restano da dimostrare.

Per caricare il codice, arrestare il backend attuale e riavviare dalla radice con `.venv/bin/python app.py`, poi aggiornare il browser. Questo intervento non ha riavviato né avviato campagne. L'anteprima mostra il motore e i massimi prima dell'avvio manuale.
