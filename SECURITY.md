# Sicurezza — controlli e limiti

## Modello di utilizzo

CustomerSearch è un'app locale per un singolo operatore. Ascolta su `127.0.0.1`, controlla Host, Origin e token CSRF nelle mutazioni. Non è un servizio autenticato multiutente: un processo locale con gli stessi privilegi dell'utente può accedere a file e API. Non esporre la porta con tunnel, proxy pubblico o bind su tutte le interfacce.

## Segreti e dati

Le chiavi si configurano in `.env` o nell'ambiente del processo; non vanno inserite in report, fixture, screenshot o commit. `.gitignore` esclude ambiente, database, runtime, backup, archivi e report locali. Questo non rimuove file già tracciati: controllare il diff prima di pubblicare.

I backup completi possono contenere `.env`, contatti e prove: cartella privata 0700 e file 0600 dalla creazione. Gli ZIP storici sono sanificati e verificati ma possono contenere informazioni aziendali: restano esclusi da Git. Gli originali sono conservati nel rollback privato. Non servire queste directory tramite un server statico.

## API e rete

Le mutazioni hanno limiti al corpo della richiesta e validazione dei campi; le query applicative usano parametri per i valori. I nomi di tabelle nelle procedure di manutenzione provengono dallo schema e vengono quotati. Le risposte hanno CSP e protezioni MIME/referrer; la UI esegue escaping dei dati non attendibili. Le risorse statiche e gli artefatti visualizzabili sono selezionati da percorsi consentiti.

I fetch pubblici verificano schema, DNS/IP pubblici, redirect, TLS, timeout, dimensioni e robots. Il browser usa il proxy controllato e limiti propri; non deve bypassare login, CAPTCHA o divieti. I PDF sono esclusi dai flussi commerciali; la libreria PDF resta necessaria ad altre funzionalità, inclusi i bandi. Le prove originali non vengono cancellate come cache.

## AI e costi

Documenti e snippet sono dati non attendibili. Gli output strutturati devono rispettare schema, citazioni e attribuzione; il modello non può rendere vero un fatto senza una fonte. Prenotazioni, budget per campagna/flusso/stadio/candidato e contatori restano vincolanti. I costi locali sono stime, non il saldo o la fattura del provider. Nessun acquisto o invio automatico.

## Verifiche 9.2.2 e rischi residui

L'audit e i test locali verificano regressioni su API, XSS/CSRF, SSRF, PDF, fonti, scheduler, costi e CRM. I test usano `tests/offline_guard`, database temporanei e fonti congelate. Il guardiano Python protegge il processo di test; non è una sandbox universale per codice ostile o subprocessi arbitrari. I test browser bloccano inoltre le richieste esterne nei propri fixture/proxy.

Il nuovo controllo di porta precede migrazioni e recupero; i backup non seguono symlink e il ripristino di prova rifiuta percorsi traversal e checksum errati. Le copie SQLite vengono verificate senza confrontarle con un database vivo che potrebbe cambiare nel frattempo.

Non è stata effettuata una scansione invasiva esterna né una verifica live dei provider. `pip check` verifica compatibilità delle dipendenze, non CVE. In assenza di un database locale aggiornato di vulnerabilità non si certifica l'assenza di vulnerabilità note. Restano i limiti di una piattaforma locale, dei parser e delle fonti pubbliche; nessuna dichiarazione di sicurezza assoluta.
