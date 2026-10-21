# Fixture Fase 3A.2

- `campaign14.json.gz`: snapshot locale della campagna 14 (task, query, tracce, revisioni, risorse ed eventi). Nessuna acquisizione remota.
- `campaign14-pages.json.gz`: 46 documenti referenziati dalle revisioni e 45 pagine HTML presenti nella cache locale. Le pagine ammesse coincidono sia per hash del testo del documento sia per canali di evidenza e coordinate. Una cache non coincidente è elencata nel file e non usata. Gli hash HTML e testo sono distinti.
- Non sono inclusi credenziali, cookie o token. I contenuti sono dati pubblici già raccolti dalla campagna, conservati per la regressione.
- Il replay usa database temporanei e letture simulate da questi HTML reali. Un dato assente non viene sostituito con un falso 404. Audit browser parziali sono riqualificati come prove parziali, senza fingere nuove misurazioni.
- Le fixture sintetiche nei test e i server HTTP/browser locali non rappresentano risultati commerciali reali.

Comando: `PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/replay_commercial32.py`.
