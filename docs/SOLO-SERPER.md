# Ricerca ordinaria con Serper — 14 ottobre 2026

Su richiesta esplicita dell'utente, SearXNG viene fermato e Serper diventa l'unico provider dell'installazione. La chiave privata già configurata viene riutilizzata; nessuna nuova sottoscrizione o ricarica. Backup verificato prima delle modifiche: `data/backups/20261013T225342709505Z/`.

## Funzionamento

- La campagna e i motori precedenti passano entrambi dall'adattatore Serper. Nessun fallback a SearXNG o Tavily, neppure per errori, quote o crediti esauriti.
- Query con localizzazione Italia, lingua italiana, paginazione e periodo opzionale. Gli snippet servono solo a selezionare pagine da leggere; la qualifica richiede fonti originali e prove commerciali.
- Cache condivisa per query, pagina e periodo, valida sei ore. Non vengono riutilizzati risultati SearXNG come risposta a una richiesta Serper.
- Controlli di pertinenza, deduplicazione, esclusioni commerciali e protezioni HTTP rimangono attivi.
- Scelta del provider persistente: l'inizializzazione del database non la riscrive più. Le impostazioni Tavily storiche non possono abilitarlo. Installazioni nuove non attivano servizi a pagamento soltanto perché trovano una chiave.
- I confronti storici restano consultabili; nuovi confronti con SearXNG sono bloccati dal server e nascosti nell'interfaccia quando è selezionato Serper.

## Consumi

Si mantengono i tetti già configurati: **30 richieste al giorno e 930 al mese**, modificabili in Impostazioni. Conteggio in UTC, come i contatori API esistenti. Zero blocca le richieste. La prenotazione transazionale precede la chiamata: anche gli errori incerti consumano il contatore locale, senza rimborso automatico. Le risposte in cache e la lettura diretta dei siti non consumano richieste Serper.

Al raggiungimento del tetto il coordinatore termina in stato bloccato, conserva il lavoro e indica come riprendere; non esegue tentativi infiniti né cambia provider. Le pause tecniche sono separate per provider: vecchi errori SearXNG non bloccano Serper.

Le richieste dei vecchi confronti restano nel loro registro separato; il nuovo contatore riguarda la ricerca ordinaria. Non rappresenta il saldo remoto e non distingue crediti gratuiti da acquistati. Il costo in euro non viene inventato nelle metriche.

## Verifica

Suite: **309 test superati**, comprendenti cache, parametri italiani e paginazione, quota atomica concorrente, assenza di fallback, provenienza nelle metriche, credenziali mancanti, Stop e persistenza dopo riavvio. Test del browser su database isolato con Serper selezionato: impostazioni, limiti, confronto disabilitato, ricerca e controlli commerciali.

[Prova reale](serper-only-smoke.json): una richiesta su lavorazioni meccaniche a Padova, dieci risultati organici. Tra i siti restituiti: Vecom, PF, Alesa, OFZ, Tecom e Rettifica Nord; presenti anche due directory. Ripetizione servita dalla cache, nessuna seconda richiesta. Si verifica il funzionamento dell'adattatore e la pertinenza iniziale, non la qualificazione commerciale di queste imprese.

Avvio locale invariato: `.venv/bin/python app.py`, quindi `http://127.0.0.1:8765`. Docker/SearXNG non serve per la modalità attiva.
