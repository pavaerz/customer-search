# Architettura corrente — decisione AI-first

Le nuove campagne pubbliche richiedono i cinque flussi dell'agente e ricevono
`filters.decision_engine=ai_first_1`. È un contratto distinto dalla versione del
contenitore storico (`agent_version=6.0`): non richiede una migrazione SQL.
Il server non crea più implicitamente campagne del vecchio motore.

Il coordinatore, la coda e il ledger restano unici. All'ingresso del task,
`agent6/research.py` esegue soltanto il ramo selezionato dallo snapshot della campagna.
`evidence.py` raccoglie metadati/unità/date e riferimenti alle prove;
`decision.py` valida e materializza la decisione del modello. `INTERESTING`,
`NOT_INTERESTING` e `NEEDS_RESEARCH` sono l'unica autorità commerciale nuova.
`alignment` e `commercial_view` ne proiettano i dati senza applicare i classificatori
commerciali legacy. Suppressioni, esiti CRM, disponibilità e policy restano vincoli.

L'originale viene acquisito e salvato prima dell'inferenza; gli snippet non vengono
analizzati a pagamento. Il modello può proporre un link osservato, una ricerca sul
soggetto o un controllo browser circoscritto. L'esecutore mantiene quote, profondità,
deduplicazione e controlli di accesso. Stop respinge i salvataggi tardivi; Riprendi
riutilizza checkpoint e ricevute. JSON-LD e card hanno documenti/offset verificabili.

Il ramo legacy descritto sotto è necessario per campagne storiche sospese, replay
e rollback; non partecipa alle nuove decisioni. La sua rimozione definitiva richiede
validazione semantica indipendente del nuovo motore e decisione esplicita sulla
possibilità di riprendere le campagne precedenti. I soli test con provider simulato
non dimostrano efficacia commerciale o accuratezza reale del modello.

## Confini

`app.py` delega a `sales.server.main`. Il server acquisisce prima la porta di loopback; solo dopo inizializza lo Store, applica le migrazioni additive e recupera le attività interrotte. Un secondo avvio non deve modificare lo stato del primo. La UI è servita da `static/`; non accede direttamente a SQLite o alle chiavi.

`CampaignManager` coordina il worker separato e la coda persistente. `ResearchStore` gestisce campagne, task e documenti. `sales/agent6/` implementa il motore corrente: il nome della directory non indica la versione del prodotto. La versione del runtime viene registrata nelle nuove campagne. I motori precedenti rimangono disponibili per compatibilità con storico, API e replay; la mancanza di un import diretto non dimostra che siano eliminabili.

I cinque flussi sono AZIENDE, AGENCIES, SOCIAL e STARTUPS, più NEWS. SOCIAL conserva l'alias storico LINKEDIN. Pianificazione, screening, verifica delle fonti e ripianificazione hanno ruoli distinti. Scheduler, prenotazioni e ricevute dei provider impediscono di considerare una risposta tardiva o una richiesta ripetuta come lavoro nuovo gratuito.

## Prove e qualificazione

I provider raccolgono URL e documenti, non clienti già qualificati. L'identità, l'attribuzione delle citazioni, la data e il ruolo commerciale vengono verificati prima della promozione. Documenti originali, revisioni e diagnostica mantengono la provenienza. Un blocco del crawler non è un difetto del sito.

`agent6/alignment.py` separa interesse commerciale, solidità delle prove e disponibilità del contatto. Email aziendali pubbliche attribuite sono accettate; la loro assenza non cancella un'opportunità qualificata. `qualification.py` conserva le condizioni specifiche dei progetti e delle collaborazioni. Le agenzie non richiedono una whitelist di stack. Le startup cofounder/equity sono opportunità imprenditoriali, non commesse remunerate.

`qualitative_audit.py`, `website_audit.py` e i controlli browser producono osservazioni motivate. Un problema minore o un giudizio estetico generico non basta per proporre un rifacimento. Non vengono attribuiti budget sconosciuti. La Worklist deriva i propri filtri dalle dimensioni commerciali senza riscrivere retroattivamente le campagne storiche.

## Persistenza e concorrenza

SQLite usa WAL, chiavi esterne e connessioni chiuse esplicitamente da `Store.connect`. Le transazioni proteggono aggiornamenti e prenotazioni. Campagne, task, prove e revisioni sono persistenti; le configurazioni di campagna sono snapshot. CRM, annotazioni manuali e memoria sono distinti dalla qualificazione automatica.

L'avvio recupera lo stato interrotto senza avviare una nuova campagna nascosta. Stop/Riprendi e i limiti restano nelle componenti già collaudate; la 9.2.2 non cambia i massimi. La memoria modifica priorità operative sulla base di esiti osservati: non è un modello predittivo delle vendite.

## Interventi 9.2.2

- Inizializzazione separata dal possesso del listener HTTP per evitare effetti sul database in caso di porta occupata.
- Backup con snapshot SQLite coerente, lettura/hash in blocchi e verifica di ripristino su copie temporanee.
- Guardiano dei test trasferito da output ignorati a `tests/offline_guard`, così è disponibile anche in un checkout nuovo.
- Lettore dei report storici da ZIP con checksum, usato dagli script che dipendevano dai report rimossi dalla radice.

Restano moduli estesi, globale `STORE` nel server e componenti storiche con responsabilità sovrapposte. Non sono stati riscritti senza una regressione dimostrata: i test sostituiscono esplicitamente Store e servizi, e la documentazione distingue il percorso corrente da quelli storici.
