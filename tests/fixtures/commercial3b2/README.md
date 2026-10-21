# Snapshot 3B.2 — dati storici, non fixture simulate

Campagne 15, 16 e 19: esportazioni locali già disponibili dei report, sole tabelle di discovery/valutazione, task, risorse e tracce AI. Nessuna impostazione, chiave API, email inviata o tabella CRM esportata.

Le pagine HTML 16/19 sono state lette dalla cache SQLite in modalità `mode=ro`: inclusione solo quando `checked_at` coincide con il documento storico. HTML mancante o aggiornato non viene inventato. Per la campagna 15 il replay usa `../commercial3b/campaign15-pages.json.gz`.

I testi possono contenere contatti pubblicati nelle fonti originali: sono prove locali di sviluppo, non una lista autorizzata a invii. L'input AI minimizza email e telefoni; non viene effettuata alcuna inferenza nel replay.

Riesecuzione dalla radice:

```bash
PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/replay_commercial3b2.py
```

Hash SHA-256 in `PHASE-3B.2-METRICS.json`. Le etichette storiche sono decisioni del sistema, non ground truth indipendente. I casi sintetici sono separati nella classe `SyntheticIntelligenceTests`.
