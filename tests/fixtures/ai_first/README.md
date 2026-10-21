# Fixture dell'audit AI-first — Fase 1

`historical.json` contiene 13 casi reali delle campagne 41 e 43, estratti in sola lettura dal database operativo il 20 ottobre 2026. I testi sono prove pubbliche già acquisite: non sono stati riscaricati durante l'audit.

Ogni caso distingue:

- `observed`: giudizio e dati storici, non corretti retroattivamente;
- `documents`: testi originali salvati, riferimenti e SHA-256 dello snapshot;
- `expected`: annotazione commerciale di audit, ancora da sottoporre a seconda revisione;
- `opportunity_type`: tipo ipotizzato per la valutazione, non prova di commessa aperta.

Le richieste storiche F/H sono `EXPLICIT_REQUEST`: l'annotazione non attesta compensi o incarichi attuali. Per A/B, INTERESTING indica un invito pertinente alla collaborazione, non un progetto già disponibile.

Eseguire dalla radice:

```bash
PYTHONPATH=tests/offline_guard:.:tests .venv/bin/python -B scripts/benchmark_ai_first.py
```

Il runner verifica gli hash e chiama funzioni pure esistenti. Le label non vengono passate a un classificatore. Le 12 sonde aggiuntive sono sintetiche e separate dai casi reali; tre espongono lacune del codice attuale. Non si eseguono inferenze AI, richieste web o accessi al database operativo.

Il campione è selezionato per regressioni note, non rappresentativo del mercato. Non dimostra la generalizzazione del futuro motore. Contiene contatti aziendali pubblici: nessuna pubblicazione automatica o autorizzazione all'invio deriva dalla presenza del file.

## Validazione commerciale offline

`commercial-originals.json.gz` contiene gli HTML originali delle pagine dei casi
A–G, recuperati dalla cache HTTP locale il 20 ottobre 2026 senza richieste esterne.
Non sono ricostruzioni HTML a partire dal testo. URL e date di acquisizione sono
conservati; gli hash sono in
`implementation-report/commercial-validation/fixture-provenance.json`.

`tests/test_commercial_validation.py` usa estrazione, identità, geografia,
selezione degli estratti, budget di input, validazione, persistenza e proiezione
effettivi. Sostituisce soltanto l'acquisizione di rete e il provider AI.
Le risposte del provider sono contratti di revisione scritti a mano, esplicitamente
simulati: il superamento dei test NON misura la capacità del modello di produrli.
La fonte Ninarello è negativa per professione; Kondividi/NHW sono inviti aperti,
non prove di incarichi pagati disponibili.
