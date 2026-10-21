# Campagna 21 — fixture storica 3B.4

`campaign21.json.gz` contiene lo snapshot di sola lettura della campagna 21 usato per il report, con 64 pagine HTML originali della cache il cui `checked_at` coincide con il documento salvato. Una pagina collegata non ha una copia originale temporalmente corrispondente: il replay non la ricostruisce. `fixture_provenance` elenca il limite.

Sono dati pubblici già acquisiti dall'applicazione, non nuove visite. Possono contenere nomi e recapiti aziendali pubblicati nelle fonti; la fixture non deve essere pubblicata automaticamente. Non contiene configurazione segreta o chiavi API.

- `Historical34`: metadata, testi originali e replay parziale storico.
- `Synthetic34`: fixture sintetiche, funzioni pure e HTTP simulato; database temporanei.
- `Browser34`: Chromium reale contro CSS sintetici su localhost, nessun sito esterno.
- `check_commercial3b4_ux.py`: UI desktop/telefono, AI MOCK e CRM temporaneo.

Il replay confronta preselezione, target fit, attribuzione e ammissibilità dei bundle. Non riesegue una campagna, non genera risposte AI, non misura nuovi siti e non dimostra nuove opportunità o risparmi effettivi.
