# CustomerSearch 9.2 — recupero e qualificazione commerciale

Implementazione e collaudo offline del 20 ottobre 2026. Nessuna Campagna 42,
richiesta Serper, chiamata OpenAI, email, modifica ai budget, commit o push.

**Esito verificato:** le prove salvate di NHW Consulting producono ora una pista
commerciale identificata e consultabile, ancora **NEEDS_REVIEW**. Punto Infissi
supera la preselezione che prima gli attribuiva le dimensioni del fornitore.
Questo non dimostra una nuova commessa né un bisogno di rifacimento del sito.
Le decisioni delle campagne storiche restano identiche nel database operativo.

## 1. Ricostruzione del percorso e cause

Il percorso corrente parte da `ResearchStore.create` e dal coordinatore commerciale.
`sales/agent6/coordinator.py` gestisce planning, query, screening e lettura;
`qualification.py`, `completion.py` e i moduli proattivi/notizie producono le
decisioni. `memory.save_record` conserva revisioni e provenienza; `entities.py`
costruisce il dossier aziendale; `worklist.py` applica storico e preferenze CRM.

La coda persistente è `research_tasks`; campagne e configurazioni sono in
`campaigns`. I consumi sono contabilizzati in `commercial_ai_executions` e
`commercial_resources`. Prove e decisioni utilizzano `agent6_records`,
`agent6_record_revisions`, documenti acquisiti e `agent6_memory`. Feedback e
correzioni manuali restano separati in `agent6_feedback` e `agent8_annotations`;
`companies` e `prospects` conservano il CRM. Non occorrono migrazioni 9.2.

| Problema dimostrato | Causa nel codice | Intervento |
|---|---|---|
| NHW perde identità e contatti | Confronto nominale a token: NHWCONSULTING ≠ NHW Consulting | Alias grafico corroborato dal dominio ufficiale e dalla fonte originale |
| Una collaborazione richiede budget/gap | La checklist AI viene unita indiscriminatamente ai requisiti obbligatori | Profili di qualificazione e requisiti non applicabili distinti |
| “E-commerce & API” diventa competenza richiesta | Etichetta isolata dei servizi citata come prova tecnica | Esclusione delle etichette senza contesto di invito; dato tecnico sconosciuto |
| Punto Infissi diventa multinazionale | Ricerca della parola in tutta la pagina, senza soggetto | Attributi del proprietario separati da partner, clienti, fornitori e investitori |
| AZIENDE esegue solo query proattive | Riuso delle proposte prima del controllo di bilanciamento | Stesso controllo in preparazione e al dispatch, per tutte le origini |
| SOCIAL ripete ricerche vuote | Firma troppo legata alle parole/piattaforme della query | Famiglia semantica aggiuntiva; sospensione dopo esiti ripetuti nella campagna |
| Verifiche scarse rispetto al planning | Poche piste ammesse; identità/gap impropri interrompono i completamenti | Recupero delle piste, verifiche mirate e riuso/alternative senza nuovo planning AI |
| Audit parziali poco leggibili | Esiti aggregati insufficienti a spiegare copertura e limiti | Registro progressivo dei controlli indipendenti, con stati e prove |

Il meccanismo di precedenza e riserva per gli originali **esisteva già** nella
9.1. I test confermano che funziona quando riceve candidati eseguibili: non è
corretto attribuire le sole due verifiche della 41 esclusivamente allo scheduler.
La 9.2 interviene anche sui blocchi che impedivano alle piste di raggiungerlo.

## 2. Identità, ruoli e attribuzione

`identity_aliases.py` normalizza Unicode NFKC, maiuscole, spazi e punteggiatura,
senza modificare il nome pubblico né il testo citato. Un alias compatto è valido
solo con identità già verificata, fonte originale sul dominio ufficiale,
assenza di conflitti e un riscontro del marchio nel dominio o nella dichiarazione
di titolarità. Fonti editoriali, social e documenti multi-annuncio non possono
utilizzare questo collegamento per attribuirsi il soggetto.

Iniziali, sottostringhe e somiglianze approssimative non bastano. Il comparatore
globale dei nomi non è stato indebolito. Due omonimi su domini differenti non
vengono fusi; il dossier continua a usare domini verificati e prove societarie
compatibili. Sono conservati nome originale, nome pubblico e motivo del legame.
Lo stesso controllo vale per il soggetto atteso negli approfondimenti.

Il filtro dimensionale usa ora dichiarazioni attribuibili al proprietario.
Menzioni di clienti, partner, rivenditori, distributori e investitori non possono
attribuire al titolare dipendenti o dimensioni altrui. Il test storico sul gruppo
Prada resta valido sul suo dominio: la vecchia esclusione non si estende a un
rivenditore o a un articolo che lo nomina. Non sono introdotte eccezioni per NHW
o Punto Infissi.

Restano coperti KONDiVIDI (servizi offerti e invito freelance possono coesistere),
Bakeca (annunci adiacenti separati), directory, inserzionisti e redirect ufficiali
salvati della Campagna 38. Un redirect estraneo non acquisisce fiducia dal solo
nome del dominio finale.

## 3. Qualificazione per tipo

| Tipo | Requisiti principali | Dati non obbligatori | Esito ammesso |
|---|---|---|---|
| Richiesta esplicita | Originale, soggetto, richiesta, competenze, rapporto esterno, territorio, attualità, contatto | Budget non pubblicato; gap del sito non pertinente alla prova della richiesta | VERIFIED quando tutti i controlli passano |
| Collaborazione con agenzia | Identità, invito esterno, compatibilità tecnica, contatto e verifiche territoriali/temporali | Budget, volume e incarico specifico non presunti; gap/segnale non richiesti | Pista NEEDS_REVIEW se incompleta; POTENTIAL quando qualificata |
| Problema digitale osservato | Azienda/sito ufficiali, misure affidabili, impatto commerciale, verifica delle alternative e perimetro | Budget e intenzione di acquisto non inventati | POTENTIAL solo dopo il percorso proattivo già previsto |
| Segnale indiretto | Soggetto, evento, data, lacuna pertinente indipendente, soluzione esistente, ambito e fattibilità | Budget ignoto | Pista da approfondire; POTENTIAL solo con riscontri completi |
| Startup/MVP | Richiesta attribuita e rapporto esterno; per web app, vincoli su dati, sicurezza, integrazioni e manutenzione | Finanziamento non equivale a budget di progetto | Come richiesta esplicita; requisiti critici ignoti impediscono la qualifica |

Impiegati esclusivi, lavori chiusi, attività fuori ambito, proposte non retribuite
o equity-only e controprove economiche dichiarate restano esclusioni. Un budget
esplicitamente insufficiente continua a essere una controprova. Un budget
sconosciuto non è un esito negativo e non viene stimato automaticamente.

La 9.2 conserva il requisito temporale per la promozione: una pagina permanente
senza data può essere una pista interessante, ma non prova disponibilità attuale.
Le condizioni di sicurezza/fattibilità di una web app non diventano facoltative.

Il dossier distingue ora interesse commerciale, qualifica, incarico attivo e
contratto acquisito. L’ultimo non viene mai desunto dalla ricerca. Eventuali
affermazioni del modello restano conservate come interpretazione: nella scheda
di collaborazione la motivazione usa l’invito documentato e limiti espliciti,
senza suggerire incarichi WordPress/e-commerce non dimostrati.

## 4. Planning, query e completamento

`query_pipeline.prepare` è il controllo comune per query nuove, riutilizzate,
recuperate o deterministiche. Viene ripetuto al dispatch prima del provider.
Controlla sintassi, ipotesi commerciale, settore, territorio, anno, saturazione
e bilanciamento AZIENDE. Storico e budget restano controlli obbligatori del
coordinatore. La ripresa di un piano persistito non paga un altro planning e
passa comunque dal controllo prima dell’esecuzione della query.

Dopo due query in eccesso di una modalità AZIENDE, il percorso comune richiede
l’altra. Le query mirate a completare un soggetto non falsano questo bilancio.
I rifiuti del riuso hanno una traccia specifica `query_policy`.

Alle famiglie lessicali è aggiunta una firma social per intento, sviluppo e tipo
di soggetto. Tre ricevute distinte senza risultati, o prevalentemente escluse
dalla preselezione, sospendono la famiglia nella campagna. Cambiare regione,
tecnologia equivalente o piattaforma non azzera quel campione. Errori tecnici
non sono risultati vuoti; ricevute duplicate non aumentano il campione; non
vengono create blacklist permanenti.

Il pianificatore prova prima proposte salvate ancora valide. Dopo ripetuti esiti
vuoti o uno squilibrio AZIENDE può scegliere poche alternative deterministiche
esplicite, anch’esse sottoposte a tutti i controlli. La provenienza viene
registrata: non sono presentate come nuove idee generate dall’AI. Non vengono
aumentate regioni, quote o disponibilità del provider.

La preselezione riconosce archivi/tag/categorie e banche dati legislative:
non sono una singola richiesta o un evento attribuibile. Un articolo specifico
rimane ammissibile come fonte; editore, soggetto, attore e destinatario restano
distinti. I titoli professionali come “Innovation developer - Torino” non
possono diventare identità da cercare. Le fonti multiple strutturate conservano
il percorso separato di identificazione dei soggetti.

Le verifiche di candidati e i percorsi mirati precedono il replanning quando
eseguibili; originali già salvati e dossier quasi completi hanno priorità.
Riserve condivise/per flusso e limiti per candidato restano atomici e invariati.
Gli esiti tecnici differiti non diventano disponibilità fittizia.

Le tracce distinguono DISCOVERY, SCREENING, SOURCE_ACQUISITION e
ORIGINAL_VERIFICATION. Il dossier espone inoltre IDENTITY_RESOLUTION,
QUALIFICATION, DOSSIER_COMPLETION e FINALIZATION come controlli, senza inventare
lavori eseguiti. Le metriche separano planning, replanning, screening, originali,
recupero mirato, completamento dossier e interpretazione audit, oltre a cache,
capacità residua e piste lasciate incomplete con motivi.

## 5. Audit progressivi e UI

Il registro `controls` espone quattro livelli: HTTP, HTML, risorse e rendering.
Ogni controllo contiene stato, URL, timestamp disponibile, prova, errore,
copertura e affidabilità. Gli stati sono PASS, FAIL_OBSERVED, NOT_TESTED,
BLOCKED, PARTIAL e INCONCLUSIVE. Gli stati legacy delle osservazioni sono
conservati per compatibilità con le regole e gli audit precedenti.

Un errore di robots, timeout o dipendenza non diventa un difetto del sito.
Misure valide di una pagina/viewport restano utilizzabili se un altro controllo
fallisce. L’audit complessivo non diventa completo per questo. Una prestazione
non misurata resta sconosciuta. Non sono aumentati timeout o limiti browser.

La Worklist mostra il prossimo controllo in italiano, distingue informazioni
mancanti da facoltative e chiarisce che un invito non garantisce un incarico.
Rimossa la duplicazione della stessa etichetta di stato. Nel dettaglio audit
sono consultabili copertura e stati dei singoli controlli. I consumi sono
esposti per scopo effettivo. Restano i cinque flussi, le citazioni, eliminazioni,
contatti confermati, stati commerciali e correzioni manuali.

Il replay NHW è stato mostrato su desktop e telefono in un database **temporaneo**.
Non è stato reinserito o promosso nel database della Campagna 41.

## 6. Memoria e storico

La memoria già presente è conservata. Errori tecnici e attribuzioni dubbie non
sono segnali di scarso interesse dell’azienda. La lettura per l’apprendimento
neutralizza scarti dimensionali contraddetti dai soggetti nelle prove salvate,
senza riscrivere la decisione originale. Il giudizio commerciale umano conserva
la precedenza anche quando viene riconosciuto un errore automatico.

Il campione minimo e i denominatori già presenti restano visibili. Interpretazioni
AI, conferme umane, contatti e contratti sono distinti; nessun apprendimento
predittivo viene dichiarato. Le fonti tra flussi mantengono origine e ruoli nel
dossier unico, senza fondere società sulla somiglianza del nome.

## 7. Replay reale e confronto

Input congelati: `tests/fixtures/agent92/campaign41.json.gz`. Contengono HTML,
risposta AI salvata, record/task, query/piani e audit; non risposte attese create
al posto degli originali. Regressioni precedenti usano anche le fixture 38–40.

| Stesso input storico | Prima | Dopo nel replay offline |
|---|---|---|
| NHW, record 781 | Identità non collegata, nessun dossier promettente | Identità/contatto collegati; pista promettente NEEDS_REVIEW |
| Requisiti NHW | entity, contact, geography, budget, signal, digital_gap, publication, technical | Restano publication e technical; budget UNKNOWN e facoltativo |
| Competenze NHW | Citazione isolata “E-commerce & API” | Trattenuta nella diagnostica, non usata come competenza richiesta |
| Punto Infissi, record 756 | REJECTED per large_group | Ammissibile all’audit; nessuna qualifica simulata |
| Query già eseguite | 72 tentativi storici | 18 tentativi avrebbero incontrato i nuovi controlli: 16 SOCIAL, 1 AZIENDE, 1 STARTUPS |

Il conteggio delle query è **controfattuale**: ogni tentativo è valutato contro le
ricevute precedenti. Non misura crediti davvero risparmiati né le query alternative
che il modello avrebbe prodotto. I 72 tentativi della Campagna 41 restano invariati.

Recuperati un falso negativo di identità e un errore di attribuzione dimensionale.
Nessuna nuova opportunità reale VERIFIED/POTENTIAL è dimostrata da questo lavoro.
Per NHW mancano le risposte agli approfondimenti; per Punto Infissi mancano audit
e valutazione commerciale che non furono eseguiti. Non sono inventati.

## 8. Simulazioni, test e verifica finale

Simulazione distinta dal replay: cinque flussi insieme, originali sintetici
disponibili, **stessi massimi della 41: 100 chiamate AI e 2 USD**; provider MOCK.
Il ciclo effettivo di coda esegue 31 chiamate simulate: 5 planning, 5 replanning,
3 screening, 17 verifiche originali e 1 interpretazione audit. Quota planning:
32,26%. Tutti i cinque flussi raggiungono originali; la coda termina senza task
residui. Verificati anche separatamente in cinque scenari aggiuntivi.

Questa prova dimostra che le verifiche possono utilizzare le risorse entro i
massimi quando esistono fonti verificabili. **Non è un confronto causale con il
42% reale della 41**: il carico e le fonti sintetiche sono differenti. Nei piccoli
scenari isolati con un solo candidato, planning e decisione di arresto possono
pesare di più; non viene imposta una percentuale fissa alla ricerca reale.

| Verifica | Risultato |
|---|---|
| Suite `test_agent*.py` | 412 test superati |
| Sette suite commerciali coinvolte | 203 test superati |
| `test_sales_http` su server temporaneo | 14 test superati |
| Revisione finale mirata a presentazione/memoria/CRM | 53 test superati, sottoinsieme già incluso dove applicabile |
| UI Worklist/CRM desktop 1440 e mobile 390 | Passata, nessun errore JavaScript |
| UI NHW con originali salvati, entrambe le larghezze | Passata; pista incompleta e limiti visibili |
| Browser reale su tre pagine locali | Utilizzabile: PASS; overflow: difetto misurato; incompleta: UNKNOWN senza difetti inventati |
| Sintassi `static/agent6.js` e `static/worklist.js` | Verificata con Node |
| SQLite operativo vs backup | Tutte le righe di 66 tabelle identiche; integrità OK |

La suite comprende i 18 ambiti richiesti: identità/qualifica/onestà NHW, Punto
Infissi, KONDiVIDI, Bakeca, riuso, bilanciamento, saturazione, articolo NEWS,
audit parziali, redirect, budget, dossier tra flussi, storico, flussi isolati e
congiunti e controlli negativi. Stop/ripresa, prenotazioni concorrenti, esclusioni
CRM e feedback restano coperti dalle regressioni precedenti.

Durante il collaudo sono stati trovati e corretti altri due problemi: il prompt
allungato sottraeva spazio a un originale AFM, quindi è stato compattato senza
aumentare il limite; la correzione dimensionale lasciava passare un risultato
storico del gruppo Prada, quindi è stata preservata l’esclusione sul dominio
del gruppo. Il controllo visivo ha inoltre eliminato dalla scheda l’ipotesi AI
non provata sulle tecnologie richieste da NHW, mantenendola come interpretazione
diagnostica separata.

Comandi riproducibili:

```bash
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B -m unittest discover -s tests -p 'test_agent*.py' -q
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/replay_agent92.py
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/simulate_agent92.py
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/check_agent92_ux.py
```

Il test UI richiede Chrome e il permesso di aprire un server locale temporaneo.
La guardia blocca database operativo e connessioni esterne; non blocca i soli
server temporanei necessari al collaudo. I provider sono sostituiti nei test.

## 9. File, backup e integrità

L’elenco esatto dei **21 file modificati e 10 aggiunti** rispetto al preflight è
in [CHANGES.json](implementation-report/customersearch92/CHANGES.json).
Include coordinatore, qualificazione, completamento, policy query, memoria,
audit, API, UI e test. I nuovi moduli sono `identity_aliases.py`,
`requirements.py`, `progressive_audit.py` e `pipeline_metrics.py`; i nuovi script
sono `replay_agent92.py`, `simulate_agent92.py` e `check_agent92_ux.py`.

Backup ripristinabile: `data/backups/customersearch92-preflight/`, directory 700,
file 600. Copia SQLite verificata con integrity_check e conteggi; archivio
codice/configurazione verificato e hash nel manifest. Contiene configurazione
privata: non va pubblicato. Nessuna chiave è stata mostrata.

[PRESERVATION.json](implementation-report/customersearch92/PRESERVATION.json)
confronta tutte le righe di tutte le 66 tabelle con il backup e verifica anche
che `.env` sia invariato. Ultima campagna presente: **41**. Nessuna migrazione
necessaria, nessuna modifica retroattiva a decisioni, memoria, configurazioni o
CRM. I report originali delle campagne precedenti non vengono riscritti.

## 10. Limiti e prontezza

- Non sono state generate nuove risposte AI: il replay non verifica come il
  modello reale risponderà al prompt aggiornato.
- Le famiglie semantiche sono regole spiegabili, non una comprensione universale
  delle query. La validazione commerciale resta necessaria.
- L’attribuzione prudente può lasciare ambiguità da approfondire. Un soggetto
  non riconoscibile non viene ricostruito per somiglianza.
- Le limitazioni reali di robots, social e browser restano. La 9.2 migliora la
  copertura dichiarata, senza rendere complete le quattro letture parziali della 41.
- Nessuna risposta aggiuntiva è disponibile per qualificare definitivamente NHW.
  Il database operativo conserva la classificazione storica; il recupero è
  dimostrato nel replay e nella Worklist isolata.
- Il tasso di falsi positivi commerciale, le conversioni e cinque opportunità
  utili a settimana restano da misurare sul campo.

**Prontezza:** i controlli offline passano; è tecnicamente possibile una futura
prova autorizzata, mantenendo i limiti e revisionando ogni promozione. Non è una
garanzia di efficacia commerciale. Nessuna Campagna 42 è stata avviata.

Il backend operativo non è stato riavviato durante questo incarico, per mantenere
invariati i dati. Per usare la 9.2 occorre riavviarlo, poi aggiornare la pagina.
Il comando locale resta `.venv/bin/python app.py`; il processo precedente deve
prima essere arrestato. La ricerca rimane un’azione manuale successiva.

Metriche: [CUSTOMERSEARCH-9.2-METRICS.json](CUSTOMERSEARCH-9.2-METRICS.json).
Prove aggiuntive, log e replay: [implementation-report/customersearch92](implementation-report/customersearch92/).
