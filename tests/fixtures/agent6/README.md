# Fonti congelate della Campagna 31

`campaign31.json.gz` contiene 19 casi estratti da `implementation-report/campaign31-snapshot.json`: 13 hanno un documento testuale salvato; gli altri conservano soltanto metadati/snippet disponibili. Non vengono recuperate nuove pagine. La data del test è fissata al 19 ottobre 2026; non significa che una pagina sia stata riletta oggi.

Gli output usati nei test del contratto AI sono **ricostruzioni controllate**, non risposte OpenAI originali. Il logger 5.1 conservava solo hash e codici delle quattro risposte invalide. Sono quindi riprodotte le condizioni di errore (attore/fonte errati, intervallo inesistente, data indicizzata, ruolo temporale errato), senza falsificare un replay esatto.

I test con servizi iniettati verificano l'orchestrazione e i requisiti di promozione. Non misurano la precisione del modello remoto né nuove opportunità commerciali.
