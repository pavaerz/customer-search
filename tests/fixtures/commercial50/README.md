# Benchmark discovery 5.0

`campaign29.json.gz` è uno snapshot locale di 128 tracce, 26 schede e 38 documenti della Campagna 29. Nessuna nuova acquisizione. Le date sono valutate rispetto all'istante dello snapshot, non all'orologio del replay.

`benchmark.json` contiene 32 casi etichettati prima di modificare l'ammissione: 8 ricavati dallo storico e 24 esempi sintetici dichiarati. Le decisioni baseline sono state catturate con il codice precedente. Il replay confronta queste decisioni congelate con il codice attuale sugli stessi input; non esegue due campagne e non ritocca le etichette per raggiungere una soglia.

24 casi hanno etichetta binaria (9 positivi, 15 negativi); 8 sono ambigui e restano fuori dai denominatori di precision/recall. Positivo significa **merita approfondimento**, non cliente qualificato. L'unico positivo storico è la collaborazione Understack: non prova l'esistenza di una nuova commessa aperta. Gli altri 8 positivi sono sintetici. Il campione è piccolo, selezionato sugli errori noti, non indipendente e non rappresentativo del mercato.

Le 128 tracce senza etichetta sono un replay descrittivo separato. Le valutazioni di attualità, geografia, attribuzione e ranking sono conservate separatamente dall'ammissione. Nessun risultato del benchmark viene salvato nel CRM o promosso a VERIFIED/POTENTIAL.

Riproduzione dalla radice:

```bash
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/replay_commercial50.py
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B -m unittest test_commercial50 test_commercial50_http
```

L'hash della fixture etichettata è registrato nelle metriche. Il guard blocca rete esterna e accesso al database operativo; i test usano database temporanei. Gli endpoint HTTP richiedono una macchina che consenta server loopback locali.
