# CustomerSearch — benchmark offline AI-first, Fase 1

## Scopo e limiti

Questo benchmark misura lacune dell'attuale sistema e definisce la prova di accettazione del futuro decisore. **Non implementa il nuovo decisore e non simula inferenze AI come se fossero state eseguite.** I risultati attesi sono annotazioni di audit sulle prove congelate, non risposte inserite nel classificatore.

Campione intenzionale di regressione: 13 casi reali da campagne 41/43, non campione rappresentativo del web. Giudizi prodotti in questo audit, non ancora validati da un secondo revisore umano. Sono necessari doppia revisione e nuovi casi non visti prima di dichiarare precisione commerciale.

## Materiale e riproducibilità

- [Snapshot pubblici congelati](tests/fixtures/ai_first/historical.json): record/campagna, stato storico, prove originali, document IDs, URL, date di acquisizione e SHA-256 del testo. Non contiene configurazioni, chiavi o dump del database.
- [Runner](scripts/benchmark_ai_first.py): chiama esclusivamente funzioni pure esistenti; niente Store, rete, campagne o inferenze.
- [Risultati diagnostici](analysis-report/ai-first/benchmark-results.json).
- [Replay del codice attuale](analysis-report/ai-first/current-code-replay.json), ricavato dalla fixture già esistente di NHW/Punto Infissi con HTML e output AI storici. Non è una nuova risposta AI.
- [92 regressioni offline](analysis-report/ai-first/regression-tests.txt): lifecycle, identità, scope, scheduling, HTTP, backup, provider e allineamento.

Comandi, dalla radice:

```bash
PYTHONPATH=tests/offline_guard:.:tests .venv/bin/python -B scripts/benchmark_ai_first.py
PYTHONPATH=tests/offline_guard:.:tests .venv/bin/python -B scripts/replay_agent92.py --output analysis-report/ai-first/current-code-replay.json
```

Il guardiano impedisce accessi al DB operativo e connessioni esterne. I file estratti dal database sono stati creati prima, con lettura `mode=ro`; i replay non rileggeranno la produzione. Le fixture contengono dati di siti pubblici, inclusi contatti aziendali: non pubblicarle automaticamente.

## Casi reali e criterio indipendente

“INTERESTING” significa opportunità utile di outreach secondo il nuovo obiettivo; non automaticamente richiesta pagata. I campi sconosciuti rimangono ignoti. Tutti gli URL sotto sono riferimenti alle prove già salvate, non pagine visitate durante l'audit.

| Caso | Record / campagna | Fonte e prova | Atteso e condizioni | Cosa non si può affermare |
|---|---|---|---|---|
| A Kondividi | 1021 / 43 | `kondividi.it/web-agency-modena/`, originale `805aca98…`; professionisti web, partita IVA, cv@kondividi.it | INTERESTING, OPEN_FREELANCE_COLLABORATION; invito permanente e compatibilità documentati | Incarico aperto, compenso, volumi, risposta garantita |
| B NHW Consulting | 781 / 41 | `nhwconsulting.it/lavora-con-noi/`, `a76eaffb…`; freelance/professionisti digitali, Garlasco, info@nhwconsulting.it | INTERESTING; il replay attuale conferma identità e canale, senza data pubblicazione | Che l'agenzia abbia già una commessa per Diego |
| C Studio Ninarello | 1043 / 43 | `studioninarello.it/collabora-con-noi/`, `54459767…`; architetti, geometri, periti termotecnici | NOT_INTERESTING per sviluppo web | Che ogni pagina “collabora” sia una domanda compatibile |
| D CerealVeneta | 953 / 43 | `cerealveneta.it`, `1c6ba4d0…`; produttore farine/semilavorati, Padova | NEEDS_RESEARCH se esiste una domanda commerciale da verificare; riconoscere produttore | Necessità di rifacimento, budget, ruolo di ente formativo |
| E Agroalimentare La Veneta | 952 / 43 | `agroalimentarelaveneta.it`, `8a462f60…`; attività e Veneto presenti | NEEDS_RESEARCH, territorio estratto dalle prove, nessuna penalità per ignorarlo | Nuovo sito necessario o capacità di spesa |
| F Elice Group | 1132 / 43 | `drupal.it/lavoro?order=created&page=23&sort=asc`, `31ed977e…`; Vicenza, freelance, 03/11/2015 | NOT_INTERESTING come richiesta attuale; entità storica conservabile | Che la data di fetch renda attuale il lavoro |
| G Elice / ilGiornale | 1139 / 43 | `/node/21903`, `914e897c…`, contiene ilGiornale e 03/09/2015, non Elice | NEEDS_RESEARCH sulla relazione o chiusura della pista; nessuna associazione accettata | Attribuire il dettaglio a Elice ereditando il contesto della bacheca |
| H Camperlife | 1130 / 43 | `drupal.it/lavoro?page=6`, `c1e84c91…`; manutenzione/sviluppo 27/11/2015 | NOT_INTERESTING come incarico attuale; perimetro completo non provato | Commessa recente o rifacimento completo |
| I ReportAziende | 955 / 43 | `reportaziende.it`, `b8a4e2c9…`; editore distinto da Veneta Lavorazioni Alimentari | NEEDS_RESEARCH sul produttore solo se motivato; niente audit del publisher come cliente | Media Asset Spa uguale al produttore cercato |
| J Cantieri Navali di Sestri | 1001 / 43 | `cantierisestri.it`, originali e audit PARTIAL | NEEDS_RESEARCH; tecnico parziale separato dal commerciale | Timeout/blocco del crawler = sito da rifare |
| K Punto Infissi | 756 / 41 | `puntoinfissi.it`, `f6008a1d…`; partner/rivenditore Oknoplast | NEEDS_RESEARCH; produttore/rivenditore locale, relazione fornitore distinta | Che sia il gruppo multinazionale citato |
| L Bacheca geometri Bologna | 1023 / 43 | offerta personale di collaborazione edilizia | NOT_INTERESTING per Diego, direzione dell'offerta corretta | Annunciante che offre servizi = buyer web |
| M CNA Genova | 1007 / 43 | `cna.ge.it`, associazione; nessuna richiesta web nelle prove esaminate | NOT_INTERESTING per questa pista cantieristica | Impossibilità assoluta che un'associazione commissioni mai un sito |

A–M non sono una whitelist di aziende: il futuro decisore non riceverà case ID, expected label o descrizione di audit. Riceverà profilo, documenti e metadati. I document IDs completi e gli hash sono nello snapshot.

## Risultati effettivamente misurati ora

### Stato storico e visibilità attuale

Proiezione esplicita dello stato storico attraverso `alignment.dimensions`: INTERESTING se OPPORTUNITY_QUALIFIED; NOT_INTERESTING se storico REJECTED; altrimenti NEEDS_RESEARCH. È una misura della **superficie attuale**, non dell'intelligenza di una nuova inferenza.

- Casi positivi annotati: 2 (A, B); visibili come qualificati tramite questa proiezione: 0; richiamo sul campione noto 0/2.
- Precisione dei qualificati: non definibile, nessun positivo predetto. Zero falsi positivi qualificati nel campione non significa 100% precisione.
- Accordo a tre decisioni: 4/13 (30,8%). NON presentarlo come accuracy del futuro modello.
- Il replay storico con codice corrente recupera identità e contatto NHW ma lascia `missing=['publication']`. Punto Infissi passa `SUITABLE_FOR_AUDIT`; non esistono nel replay un browser nuovo o una nuova valutazione commerciale.
- Gli scarti CerealVeneta/La Veneta provano errori intermedi, non commesse perdute. L'annotazione NEEDS_RESEARCH non è un'automatica promozione a prospect utile.

### Sonde di contratto e generalizzazione limitata

12 sonde, 9 conformi e 3 non conformi. Non cambiano il codice e non nascondono i fallimenti dietro expectedFailure.

| Gruppo | Varianti | Osservato |
|---|---|---|
| Date | ISO etichettata vecchia/recente/futura; italiana “Postato il”; data numerica di card; data oltre 1600 caratteri; invito senza data; copyright | Tre lacune: slash italiano, card numerica, ISO oltre il prefisso. Le altre 5 rispettano il contratto temporale della sonda. |
| Relazione fornitore | Due aziende nuove e due fornitori diversi rispetto a Punto Infissi | Il gruppo del fornitore non è attribuito al rivenditore, 2/2. |
| Contratto incompatibile | Due nomi nuovi, assunzione dipendente con rifiuto freelance | Controprova employee_job presente, 2/2. |

Le sonde non interrogano un modello e non dimostrano generalizzazione semantica dell'AI. La trasformazione dei nomi dimostra solo che la regola locale esercitata non è una lista dei nomi di questo audit. Il ruolo commerciale delle date senza data rimane da valutare: UNKNOWN temporale è corretto per un invito permanente, non sufficiente per NOT_INTERESTING.

## Suite di accettazione da costruire nella fase autorizzata

Separare sviluppo (13 casi noti) e holdout di almeno 50 casi mai usati nei prompt/test di sviluppo: almeno 20 outreach utili, 20 negativi difficili e 10 ambigui. Split per dominio **e per evento/richiesta**, così repubblicazioni non passano da training a test. Almeno due annotatori, uno Diego per compatibilità commerciale; disaccordi adjudicati o etichettati ambiguous. Congelare i criteri prima delle inferenze.

Varianti obbligatorie oltre ai casi reali:

- Agenzia digitale con sola candidatura per dipendenti; agenzia che accetta freelance ma pagina dichiara ricerca chiusa; pagina che vende servizi e invita davvero collaboratori in altra sezione.
- Invito permanente senza data e con email generica; stessa pagina con nome azienda cambiato, layout diverso e sinonimi. Attore, motivazione e contatto devono seguire i nuovi riferimenti.
- Post condiviso che cita un buyer diverso dall'autore, commento di un fornitore, snippet con testo non presente nell'originale, post originale inaccessibile.
- Due omonimi, directory con editore verificato ma soggetto irrisolto, redirect a dominio estraneo, sottodominio/ATS ufficialmente collegato, canonical malizioso.
- Due annunci nella stessa pagina con date/compensi opposti; validThrough futuro con datePosted vecchia; published/modified in conflitto; giorno senza timezone, solo mese/anno, data relativa con incertezza; copyright recente su annuncio antico.
- Startup equity-only, unpaid esplicito, contratto pagato con cifra ignota, grant/funding citato per sbaglio come budget progetto, MVP con dati sanitari/integrazioni critiche non delimitate.
- Produttore con sito funzionale e nessun bisogno; mobile difettoso ma piccola correzione sufficiente; impresa che ha già shop esterno ufficiale; ampliamento mercati gestito già dal sito.
- Prompt injection in HTML, JSON-LD, metadati e memoria: non deve causare visita privata, esfiltrazione, invio o citazioni inventate.

Per ogni scenario conservare originali, acquisizione, label, ragioni, claim gold e fonti negative. La label deve riguardare ciò che le prove permettono, non una categoria del dominio. Varianti sintetiche marcate come tali, escluse dai conteggi di opportunità reali.

## Misure e soglie proposte

| Metrica | Definizione / denominatore | Accettazione iniziale motivata |
|---|---|---|
| Precisione commerciale | Interessanti confermati / decisioni INTERESTING, almeno 20 predetti revisionati | ≥90%; limita tempo perso. Se meno di 20, esito insufficiente, non pass artificiale. |
| Richiamo | Interessanti trovati / positivi gold (≥20) | ≥85%; consente incertezza prudente ma impedisce il blocco sistematico di inviti. |
| Identità e attribuzione | Claim di attore/relazione corretti / claim valutati, per unità | ≥98% e **zero errori critici nei qualificati**: soggetto sbagliato/citazione inventata impediscono il rilascio. |
| Date | Ruolo, soggetto, precisione, valore o corretta incertezza / claim temporali | ≥95%; nessun annuncio 2015 presentato come attuale. Non premiare una data inventata per riempire il campo. |
| Prove | Citazioni risolvibili e hash/offset coerenti / citazioni | 100% strutturale; entailment e attribuzione verificati separatamente. |
| Motivazione | 0–2 per specificità, compatibilità Diego, distinzione inferenza, controprove, azione utile | ≥8/10 su ≥20 INTERESTING, nessuno zero in attribuzione/veridicità. Rubrica prima del test. |
| Contatti | Canali pubblici corretti e attribuiti / contatti mostrati | 100% no indirizzi inventati; quota disponibile misurata, non obbligo per qualificare. |
| Incertezza | Unknown preservati, assenza non negativa / casi ambigui | Zero budget/fatturato/spesa inventati; nessuna inferenza trattata come richiesta dichiarata. |
| Robustezza | Invarianza semantica al cambio nome/ordine; cambiamento corretto con controprova | Tutte le regressioni critiche A–M e negativi di sicurezza; risultato per variante pubblicato. |
| Costo utile | Spesa attribuita / dossier unici confermati utili | Calcolabile solo con utili >0; limite deciso dal budget reale, non saldo ipotizzato. |
| Pipeline | Completezza, retry, cancellazione, dedup, no late writes, preserved history | Test offline tutti verdi sul nuovo percorso; Stop entro cinque secondi nei test controllati. |

Le soglie sono criteri di rilascio proposti, non risultati già ottenuti. Con 20 positivi l'incertezza statistica resta ampia: pubblicare conteggi e intervalli binomiali, non dichiarare precisione di mercato. Nessuna soglia di conversione può essere valutata senza contatti reali.

## Confronto e ripetibilità futura

Congelare modello/schema/prompt/profilo, input e hash; conservare output completi in archivio privato e diagnostica sanificata. Eseguire ogni caso senza label nel contesto, poi valutare contro gold. Ripetere almeno tre volte su un sottoinsieme ambiguo per misurare instabilità, senza scegliere solo la risposta migliore. Queste inferenze, se remote, richiedono autorizzazione della fase successiva; **non sono state eseguite ora**.

Distinguere: costo totale campagna, costo di originali riusati, costo di query, costo candidato e tempo umano di revisione. Miglioramento rispetto al legacy sugli stessi input è necessario ma non sufficiente. Una successiva prova live richiederà opportunità non viste e review prima di contattare; nessuna nuova campagna è autorizzata implicitamente da questo benchmark.
