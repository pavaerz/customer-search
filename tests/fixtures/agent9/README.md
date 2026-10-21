# Replay CustomerSearch 9.0

`campaign38.json.gz` conserva il testo originale, l’HTML e l’impronta del testo di Kondividi (scheda 200) e Bakeca (193), acquisiti dalla Campagna 38 il 19 ottobre 2026. Per Kondividi include l’interpretazione effettivamente salvata e i passaggi forniti al modello: l’invito era presente, ma ignorato. Non è una nuova consultazione né una conferma della disponibilità attuale.

`redirects38.json.gz` contiene gli HTML già acquisiti di Progetto Quid ed Eleventy. Il vecchio client non registrava gli hop: i test verificano URL iniziale/finale e identità disponibile senza inventare la catena storica. Eleventy conserva l’incertezza sull’identità.

I provider dei test sono sostituti offline: la risposta corretta nel recupero Kondividi è una simulazione che seleziona citazioni reali. Non dimostra che il modello remoto risponderà correttamente. Alfa e gli altri esempi sono fixture sintetiche, mai opportunità commerciali reali. Le campagne dei test usano database temporanei; nessuna richiesta remota, modifica dei dati operativi o invio.
