# Originali e coda della Campagna 58

Questi dati congelati provengono da acquisizioni già effettuate dalla Campagna 58.
I test non accedono ai siti, non eseguono inferenze e non aprono il database operativo.

- `originals.json.gz`: HTML originale già salvato per i record 1877
  (OpenInnovation, proposta DPP), 1882 (QDP, Latteria Soligo), 1885
  (Occhi, Caseificio San Rocco). Il testo delle pagine non è sintetico.
- `san-rocco-response.json`: risposta AI diagnostica effettiva della Campagna 58,
  esecuzione 1476. Viene riprodotta senza cambiare decisione, citazioni o nomi.
- `queue.json`: estratto sanificato dello snapshot finale della Campagna 58.
  Conserva stati, scadenze dei tentativi, configurazione AI e 19 tentativi
  effettivi. Esclude credenziali, token di autorizzazione e dati non necessari.

Il provider è sostituito da un doppio di test. Per i primi due originali la
risposta volutamente vuota serve solo a osservare l'input effettivo: non misura
la capacità commerciale del modello. Il terzo riproduce una risposta storica
`NEEDS_RESEARCH`, con compenso sconosciuto e fonte datata; non è un'opportunità
qualificata. I test degli stati della coda usano esclusivamente SQLite temporaneo.

I casi aggiuntivi di layout, indirizzi e query negative sono sintetici e sono
indicati come tali nei test. Non rappresentano aziende o richieste reali.
