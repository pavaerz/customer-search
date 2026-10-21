# Campagna 13 — fixture della Fase 3A.1

`campaign13.json.gz` contiene un sottoinsieme congelato dello snapshot locale della campagna 13: tracce discovery, task, revisioni commerciali con prove salvate, contatori risorse e operazioni. Non contiene credenziali né dati acquisiti durante questa implementazione. Le revisioni storiche non vengono modificate.

Il campione comprende **100 righe discovery: 98 apparizioni dirette e 2 follow-up**, 52 task e 36 revisioni. Il provider aveva restituito **100 apparizioni dirette**: due non hanno una traccia discovery salvata. Non conosciamo da queste righe quali fossero i due URL mancanti; il replay non li inventa. Il totale 100 delle righe salvate non è una riconciliazione dei risultati provider, perché include i follow-up.

Verdurazon, revisioni 691/693, è un indizio Instagram trovato realmente nella campagna 13. Gli snippet differiscono: non devono essere fusi in una sola prova, né usati come conferma dell'identità, della data o dell'attualità del post. Le fonti Instagram erano bloccate da robots.txt. Nessun accesso al post viene effettuato nei test.

`test_commercial_intent31.py` ricostruisce piccoli contenitori HTML dai **soli estratti già salvati** per Inputcomm, Freelancedev e DSI. Questi contenitori non sono il DOM originale: verificano la classificazione del testo disponibile, non la correttezza della segmentazione della pagina completa. Gli altri controesempi grammaticali e le opportunità positive sono dichiaratamente sintetici.

Il replay si esegue dalla radice del progetto:

```sh
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/replay_commercial31.py
```

Produce `implementation-report/phase-3a1-replay.json` separando:

- **Osservazioni storiche:** query, fonti, regioni, risultati, consumi e due timeout browser restano quelli registrati.
- **Confronto dei filtri:** le stesse righe passano nel nuovo pre-filtro; ammissione preliminare, deduplicazione e qualificazione restano concetti distinti.
- **Replay della coda:** le 98 apparizioni note passano in `Coordinator.receive` su SQLite temporaneo, con budget Pilot e memoria commerciale inizialmente vuota. Tutte devono conservare un esito tracciabile. I follow-up sono contati separatamente; il percorso da Bliss viene fermato dall'esclusione della pagina di origine.
- **Pianificazione sintetica:** dodici query, tre per motore, con risultati vuoti restituiti da un mock. Mostra la diversificazione del planner e il limite persistente, senza attribuire risultati reali a LinkedIn o alle nuove query.

I test separati di contabilità aggiungono URL sintetici per esercitare budget, duplicati, PDF e Stop; questi URL non sostituiscono quelli mancanti nella campagna reale. I test browser utilizzano server locali e non vengono presentati come nuovi audit dei siti storici.

Nessuna chiamata Serper, acquisizione HTTP esterna, inferenza, invio o modifica al database reale è necessaria. I file SQLite di replay sono temporanei e rimossi al termine. Queste metriche non misurano precisione sul mercato, conversione commerciale o opportunità ottenute con le query nuove.
