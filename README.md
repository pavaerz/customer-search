# CustomerSearch — AI-first

Le **nuove campagne avviate dall'interfaccia** usano `decision_engine=ai_first_1`:
ricerca → originale → decisione AI motivata → verifica mirata. Le campagne
precedenti conservano il proprio percorso e i propri risultati.

Il decisore distingue richieste, collaborazioni aperte, candidature spontanee,
proposte proattive ed equity. Un invito permanente può essere interessante senza
una data di pubblicazione o un budget dichiarato: non diventa una commessa certa.
Letture, browser e inferenze rispettano i massimi già configurati.

Avvio locale: `.venv/bin/python app.py`. Un backend già aperto deve essere
riavviato per caricare il codice nuovo; non avviare due copie sulla stessa porta.
Apri la ricerca, controlla l'anteprima e avvia solo quando vuoi consumare crediti.
Il refactoring non ha avviato campagne o chiamate esterne.

Dettagli: [implementazione AI-first](CUSTOMERSEARCH-AI-FIRST-IMPLEMENTATION-REPORT.md),
[pulizia](CUSTOMERSEARCH-CLEANUP-REPORT.md),
[ultime cinque campagne](reports/recent/README.md).

Applicazione locale per ricercare e verificare opportunità commerciali. I cinque flussi **AZIENDE, AGENCIES, SOCIAL, STARTUPS e NEWS** condividono prove e memoria, mantenendo distinti aziende identificate, ipotesi, opportunità potenziali e richieste verificate. Una qualifica non garantisce una vendita.

## Installazione

Ambiente collaudato: macOS, Python 3.13, Chromium tramite Playwright. Da questa cartella:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env
chmod 600 .env
```

Copia `.env.example` solo durante una nuova installazione: non sovrascrivere un `.env` esistente. Compila le chiavi localmente, senza condividerle. L'ambiente del Terminale ha precedenza sui valori in `.env`.

```bash
.venv/bin/python app.py
```

Apri **http://127.0.0.1:8765**. Il backend deve restare aperto. `Ctrl+C` nel suo Terminale lo ferma; un refresh della pagina non riavvia Python. Una porta occupata ora interrompe il secondo avvio prima di migrazioni e recupero delle campagne.

## Uso

1. Controlla provider, regioni, canali, modalità AI e massimi nelle impostazioni.
2. Premi **Prepara nuova ricerca** e verifica l'anteprima: non esegue ricerche a pagamento.
3. Avvia esplicitamente con i massimi approvati. **Stop** conserva i risultati; **Riprendi** prosegue la stessa campagna e i suoi consumi.
4. Leggi prove, limiti e stato commerciale nella Worklist. La disponibilità di un contatto è distinta dalla qualifica.
5. Revisiona manualmente le bozze. L'app non invia email automaticamente.

La configurazione AI salvata riguarda le nuove campagne; le precedenti conservano la propria. Shadow non equivale ad AI gratuita: le inferenze effettuate possono consumare il budget configurato. Il saldo effettivo dei provider non è deducibile dai contatori locali.

## Struttura

| Percorso | Responsabilità |
|---|---|
| `app.py`, `sales/server.py` | Avvio e API HTTP locali |
| `sales/agent6/` | Motore corrente 9.2.2; il nome storico della cartella è conservato |
| `sales/commercial/` | Contratti AI, browser, qualificazione e componenti commerciali condivisi |
| `sales/` | SQLite, provider, coordinamento, CRM e funzioni storiche ancora supportate |
| `static/` | Interfaccia senza build frontend obbligatoria |
| `tests/`, `tests/fixtures/` | Regressioni permanenti e prove congelate |
| `scripts/` | Backup, verifiche, replay e strumenti operativi; alcuni pilot sono live, non lanciarli indiscriminatamente |
| `data/` | Database, prove, memoria, log operativi e backup privati |
| `reports/recent/` | Indice delle ultime cinque campagne e configurazioni sanificate |
| `archives/` | ZIP verificato delle analisi storiche, escluso da Git |
| `implementation-report/` | Evidenze locali dei collaudi; non è codice applicativo |

## Test offline

Il guardiano dei test blocca connessioni esterne, porte dei servizi operativi e accessi al database di produzione. Usare sempre questi comandi dalla radice:

```bash
PYTHONPATH=tests/offline_guard:.:tests .venv/bin/python -B -m unittest discover -s tests -v
PYTHONPATH=tests/offline_guard:.:tests .venv/bin/python -B scripts/check_agent921_ux.py
PYTHONPATH=tests/offline_guard:.:tests .venv/bin/python -B scripts/simulate_agent92.py
```

I test browser richiedono Chromium e il permesso di aprire porte locali. Non sono campagne reali e non misurano conversioni commerciali.

Il percorso commerciale AI-first stima il contesto con `tiktoken` (in
`requirements.txt`). Il vocabolario `o200k_base` è incluso in
`sales/tokenizer_data/`, con licenza, provenienza e verifica SHA-256:
non viene scaricato durante una ricerca. La stima include schema e margine;
non equivale al conteggio esatto del provider. Per modelli non riconosciuti
rimane una stima conservativa in byte. I massimi configurati non cambiano.

## Documentazione

- [Architettura](ARCHITECTURE.md)
- [Sicurezza e limiti](SECURITY.md)
- [Operazioni, backup e ripristino](OPERATIONS.md)
- [Qualificazione 9.2.1 conservata](CUSTOMERSEARCH-9.2.1-IMPLEMENTATION.md)
- [Pulizia e verifiche 9.2.2](CUSTOMERSEARCH-9.2.2-CLEANUP.md)
- [Ricerca bandi](docs/BANDI.md), separata dalla ricerca clienti

Le vecchie istruzioni sono nell'archivio storico e descrivono versioni precedenti: non usarle per configurare l'app corrente. Il database esistente non viene sostituito dalla pulizia.
