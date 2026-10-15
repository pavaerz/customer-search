# Ripristino della ricerca — 13 ottobre 2026

## Problema verificato

SearXNG era configurato con il solo Bing attivo. L’adattatore Bing installato abilitava HTTP/3; i log registravano disconnessioni di `curl_cffi`. La connessione TLS standard a Bing riusciva. Dopo aver disabilitato HTTP/3 per quell’adattatore, le query hanno ripreso a restituire risultati senza errori. È una correzione del trasporto, non un aggiramento di CAPTCHA o restrizioni.

Yahoo è stato provato separatamente: 7 risultati per la query di controllo, con provenienza `yahoo`. Ora è attivo insieme a Bing. Google, Brave e DuckDuckGo restano disattivati dopo i blocchi precedentemente osservati. La prova con il nome Mojeek non era valida: l’istanza non lo esponeva e restituiva Bing come fallback; non è stato attivato né conteggiato come motore funzionante.

Configurazione documentata: [opzioni di rete per motore](https://docs.searxng.org/admin/settings/settings_engines.html), in particolare `enable_http3`. Nessun servizio a pagamento.

## Cambiamenti applicativi

- Risposta vuota di un motore funzionante più errore di un altro: non viene più trattata come indisponibilità totale di SearXNG.
- Cache delle query legata anche ai motori configurati; metadati aggiornati ogni cinque minuti. Invalidata la sola vecchia cache dei metadati dopo il collaudo.
- Circuito di indisponibilità aggiornato dopo prove reali riuscite. Le query bloccate tornano recuperabili dopo un successo del provider, oltre che alla scadenza del rinvio.
- Le connessioni interrotte in lettura/TLS hanno un solo nuovo tentativo; se fallisce, pausa di 15 minuti per quell’origine. Gli altri siti continuano a essere leggibili. Certificati, robots, pinning IP e protezioni dalle reti private invariati.
- Storico degli errori conservato; aggiunto un evento di ripristino nella campagna. La campagna sospesa dall’utente rimane sospesa: usare **Riprendi ricerca** conserva la coda.

## Prove reali

`scripts/check_search_recovery.py` usa il motore dell’app su un database temporaneo. Tre query consecutive: 17, 17 e 16 URL nuovi; nessun errore del provider. Entrambi i motori hanno contribuito. Due pagine originali lette con HTTP 200.

Questi 50 URL **non sono 50 opportunità qualificate**. Il campione include risultati generici o poco pertinenti (anche un vocabolario); la qualificazione commerciale resta necessaria. Le risposte positive dimostrano il ripristino del trasporto nel collaudo, non disponibilità futura garantita o efficacia commerciale.

`geniai.it` interrompe la sessione TLS anche fuori dall’app. Il nuovo client restituisce un errore comprensibile dopo il tentativo limitato e impedisce nuovi accessi alla stessa origine durante la pausa. Verifica reale: primo controllo 0,631 s, successivo 0,009 s dalla memoria dell’errore, senza una nuova connessione. Non è stato risolto il problema remoto del sito.

Rapporti: `search-transport-probe.json`, `search-recovery-pilot.json`. Backup: `data/backups/20261013T201915705608Z` e backup precedente `20261013T200223003514Z`. Nessun contatto, email o candidato di prova inserito nel CRM.
