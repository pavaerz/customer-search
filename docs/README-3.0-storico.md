# CustomerSearch 3.0

Workspace commerciale locale per Diego Pavanello: cinque motori, fonti verificabili, dossier, pipeline e risultati commerciali. Interfaccia chiara senza CDN o risorse esterne. Schede con motivo della selezione, fonte originale e prossimo passo; riepilogo «In breve» all’apertura, dettagli e controlli nelle sezioni dedicate.

## Avvio

```bash
.venv/bin/python app.py
```

Apri **http://127.0.0.1:8765**. Il server ascolta soltanto su localhost. Usa questo indirizzo esatto, anche per i controlli Host/Origin/CSRF. Python 3.10+; ambiente del progetto verificato con Python 3.13. `python` su questo Mac punta ancora a Python 2: usa il comando sopra.

## Architettura

- `sales/server.py`: API HTTP locale e protezioni delle operazioni.
- `sales/providers.py`: SearXNG locale gratuito, RSS/Atom e lettura pubblica con robots.txt, redirect verificati e blocco delle reti private.
- `sales/extract.py`: estrazione di richieste, cambiamenti, date, identità e contatti. I frammenti del motore non sono prove.
- `sales/engines.py`: esecuzione indipendente A/B/C/D/E, annullamento, controlli e registrazione dei motivi di esclusione.
- `sales/db.py`: database SQLite nuovo, cache, budget atomici, fonti, evidenze, opportunità, interazioni e archivio precedente.
- `sales/intelligence.py`: priorità trasparente, dossier e bozze basate su fatti citati.
- `sales/advisor.py`: adapter opzionale per un modello Ollama già installato localmente.
- `site_audit.py`, `technical_audit.py`: componenti tecnici riutilizzati. Lighthouse isolato in un processo interrompibile; risultati originali conservati.
- `static/`: interfaccia senza framework/runtime frontend; cinque sezioni dei motori, filtri, shortlist, pipeline, esiti, fonti, archivio, impostazioni e dossier.

La ricostruzione sostituisce il vecchio server monolitico. Il vecchio codice e i test legati alle sue API sono in `archive/v2/`, non fanno parte dell’app attiva. I test del componente Lighthouse riutilizzato sono mantenuti nella suite attuale.

## Come funziona la selezione

**A** cerca richieste esplicite compatibili con la collaborazione freelance. **B** cerca collaboratori/partner e cambiamenti concreti nelle agenzie. **C** considera aggiornamenti aziendali solo quando dichiarano anche un progetto web da realizzare. Trasferimenti, aperture e lanci già completati, da soli, non sono opportunità commerciali. **D** misura problemi specifici su homepage e fino a tre collegamenti importanti, oltre ai test Lighthouse mobile/desktop. **E** collega riscontri commerciali e tecnici sullo stesso dominio aziendale.

L’identità usa il dominio normalizzato: non viene inventata un’associazione tra una testata giornalistica e l’azienda citata. Un annuncio ripubblicato da un intermediario non rende automaticamente quell’intermediario il committente. Le richieste identiche trovate da A e B condividono una scheda; entrambi i motori sono visibili nei riscontri. E non considera la stessa citazione un secondo segnale.

La priorità 0–100 è un indice operativo: richiesta esplicita, recenza, compatibilità, fonte originale, contatto, continuità, misure specifiche, concorrenza e budget quando dichiarati. D da solo è limitato a 35. Data assente: massimo 49 per i segnali commerciali. Segnali oltre 90 giorni: massimo 35. I requisiti obbligatori non documentati nel profilo vengono evidenziati. Non è una probabilità di vendita.

Ogni riscontro espone URL originale, metodo di scoperta, tipo di fonte, data pubblicata quando presente e data di lettura effettiva. Le letture in cache conservano la data originale. Fatti, richieste, segnali, misure, ipotesi e limiti sono distinti nell’interfaccia. Budget assenti, settore/località non verificati e audit falliti restano esplicitamente sconosciuti.

## Provider, credenziali e costi

La ricerca usa esclusivamente **SearXNG locale**, configurato tramite `SEARXNG_URL`. Tavily è disattivato anche con vecchie impostazioni o chiavi ancora presenti: nessun fallback al servizio a crediti. Le credenziali esistenti restano in `.env`, mai nelle API frontend o nei file statici. Lo storico dei vecchi consumi è conservato, ma le sue quote non limitano SearXNG. Le query vengono messe in cache per sei ore; pagine per 24 ore configurabili. Errori dei motori senza risultati vengono segnalati, non memorizzati come ricerca vuota riuscita.

Non ci sono acquisti automatici né nuove sottoscrizioni. Le query e il periodo di ricerca sono modificabili nelle impostazioni. Sono conservate le preferenze geografiche: Veneto, Lombardia, Piemonte e Toscana prioritari; aree escluse configurabili e applicate alle località dichiarate nelle fonti. Località assenti restano da verificare. Nessun limite globale di durata; ogni connessione mantiene un timeout tecnico. Interruzione disponibile: il processo Lighthouse viene terminato insieme ai figli, mentre una chiamata API già partita può richiedere il proprio timeout prima di cedere il controllo.

SearxNG è utilizzabile solo se già installato/configurato con `SEARXNG_URL` locale. RSS supporta feed HTTPS autorizzati: nel collaudo è stato verificato e configurato il feed originale SVAI, senza presentarlo come una banca dati nazionale già integrata. Le pagine pubbliche vengono consultate senza autenticazioni o aggiramenti. I portali con condizioni/accessi specifici non sono integrati tramite scraping; eventuali adapter API richiedono verifica e configurazione separate.

Fonti consultate per la fattibilità:

- [LinkedIn: divieto di scraping](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibition-of-scraping-software).
- [Upwork: automazioni e API](https://support.upwork.com/hc/en-us/articles/43342677368467-Use-bots-and-other-automation-properly).
- [Freelancer: condizioni d’uso](https://www.freelancer.com/about/terms).
- [AddLance: condizioni](https://www.addlance.com/add/terms-of-service/).
- [Ollama: output strutturati](https://docs.ollama.com/capabilities/structured-outputs).

## Advisor e comunicazioni

Il dossier e le bozze funzionano subito con regole locali. Sono etichettati come tali: **senza modello configurato non sono un output generativo AI**. L’adapter Ollama consente a un modello locale di ordinare gli ID delle prove e scegliere domande commerciali entro uno schema validato; non gli permette di inventare fatti o budget. Non viene scaricato o installato un modello automaticamente. Un modello assente o una risposta non valida mantiene il dossier deterministico, con avviso esplicito.

Le bozze citano la fonte usata e possono essere modificate. Del portfolio viene usato solo il link fornito: nessun caso studio, risultato o competenza aggiuntiva viene inventato.

L’app **non esegue invii Gmail API**. Dopo verifica manuale del testo/destinatario, registrazione del presupposto di contatto e conferma, apre il compositore Gmail. Aprire la bozza non significa inviarla: lo stato Contattato cambia solo dopo conferma manuale o aggiornamento esplicito. I vecchi token rimangono nel backup e non sono esposti. “Non contattare” blocca generazione e composizione. Le aziende già contattate nella versione precedente sono segnalate e escluse dalla shortlist.

Il contatto pubblico non equivale al consenso: [Garante, comunicazioni promozionali](https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/29840). I controlli dell’app assistono la revisione, non certificano automaticamente la liceità del singolo invio.

## Pipeline, esperimento ed esiti

Da valutare → Da contattare → Contattato → Risposta ricevuta → Preventivo → Cliente acquisito/Perso; disponibile anche Scartato. Note e conversazioni utili sono registrate nello storico. Valore del contratto e incasso effettivo sono campi separati.

Le statistiche contano gli eventi realmente registrati: acquisire un cliente non inventa retroattivamente email o preventivi. Percentuali solo sopra una soglia configurabile (10 contatti predefiniti), sulla stessa coorte di contatti. Il suggerimento sui motori è descrittivo, non predittivo. Le statistiche riuniscono gli eventi delle schede della stessa azienda e attribuiscono contatti e clienti una sola volta, al canale della scheda di gestione. Gli importi già registrati sulle schede precedenti restano conservati e visibili nei dettagli delle schede riunite.

La verifica di efficacia su 30 giorni richiede esiti reali dell’utente e non può essere dichiarata completata il giorno della ricostruzione.

## Backup e dati

Backup precedente alla ricostruzione: `data/backups/20261012T140600950636Z/`. Contiene snapshot SQLite, progetto/configurazioni, manifest SHA-256. Verificati integrità SQLite, conteggi dei record, lettura ZIP e hash dei file. Permessi restrittivi; nessun download HTTP del backup. Conserva credenziali: va custodito come il progetto originale.

Il database originale `data/customers.sqlite3` rimane intatto. Il nuovo è `data/sales.sqlite3`. I 130 record precedenti sono consultabili nell’archivio, senza essere presentati come nuove opportunità verificate.

Nuovo backup verificato: pulsante nelle impostazioni oppure:

```bash
.venv/bin/python scripts/backup.py
```

## Verifica

```bash
.venv/bin/python -m unittest discover -s tests -v
```

I test HTTP richiedono la possibilità di aprire una porta localhost temporanea; tutti usano database temporanei. I test non inviano email. La verifica browser usa Playwright e Chrome locale. Il resoconto del collaudo reale è in `docs/VERIFICA-3.0.md`.

## Filtro del target commerciale

Le S.p.A. riconosciute nei dati societari del sito sono escluse in tutti i motori, anche quando pubblicano una richiesta freelance. Il controllo legge anche footer e dati strutturati della homepage, senza confondere una spa/centro benessere con la forma societaria.

Sono inoltre escluse le reti strutturate che dichiarano almeno 10 sedi/negozi/showroom, almeno 250 dipendenti/collaboratori o di essere un gruppo multinazionale. Queste soglie servono alla selezione commerciale; non costituiscono una classificazione legale della dimensione dell’impresa. Il solo aspetto grafico o numero di link non basta per affermare che un’azienda sia grande.

Le esclusioni hanno motivazione, URL e data di verifica in `target_exclusions`. Le schede ancora Da valutare/Da contattare passano a Scartato conservando fonti e note. Contratti acquisiti e interazioni pregresse non vengono sovrascritti. Il motore D non avvia nuovi audit per aziende escluse e il motore E non può farle rientrare. Anche i feed delle aziende escluse sono saltati.

Aggiornamento del campione: SVAI esclusa per la dichiarazione di 19 sedi sulla homepage; archiviate le sue tre schede C/D/E. Dopo la revisione dei cambi di sede restano quattro aziende attive: tre con richieste e una con soli riscontri tecnici a bassa priorità. Le query C sono state orientate a laboratori artigianali, studi, negozi indipendenti e showroom regionali.

## Contatti e trattative

«Conferma contatto» registra manualmente un contatto già effettuato, senza richiedere un’apertura di Gmail. Le schede dell’azienda diventano verdi e conservano la data del primo contatto registrato anche dopo un cambio di stato. La conferma non invia messaggi.

In Trattative trascina una scheda tra le colonne; su telefono usa la maniglia «Trascina per spostare». Il bordo della colonna indica la destinazione, lo scorrimento laterale ai bordi raggiunge gli stati fuori schermo. «Sposta in» permette la stessa operazione senza trascinare. Lo stato viene aggiornato dopo il salvataggio; Cliente acquisito richiede il valore del contratto.

Verifica browser (Chrome e Playwright, solo database temporaneo): `.venv/bin/python scripts/check_contact_board.py`. Copre conferma, ricaricamento, drag and drop con mouse e touch, selezione dello stato, errori di salvataggio e valore del contratto.

## Schede riunite e pertinenza dei segnali

La raccolta e le Trattative mostrano una sola scheda per dominio aziendale normalizzato. Le opportunità interne dei motori rimangono conservate, ma fonti, audit e storico sono riuniti. Filtri per motore includono tutti i canali che hanno contribuito. Il record gestito manualmente più di recente mantiene stato e note; in assenza di interazioni si usa il primo record pertinente. I vecchi ID aprono la scheda riunita.

`Store.requalify_growth()` riclassifica i vecchi annunci di sola apertura/trasferimento come limiti della selezione e scarta le relative proposte C/E ancora da valutare. Il motore E applica lo stesso criterio anche prima della riclassificazione: un cambio di sede non può aumentare la priorità di un audit Lighthouse. Fonti, note, bozze, incassi e audit rimangono conservati.

## Proposte eliminate

«Elimina proposta» nasconde l’azienda da panoramica, raccolta attiva e trattative. Il dominio normalizzato viene memorizzato in `dismissed_companies`: tutti i motori lo escludono anche dopo il riavvio, per pagine diverse dello stesso sito e per le varianti www/HTTPS. Il controllo viene ripetuto nella transazione di salvataggio per le ricerche già in corso.

Le proposte si ritrovano in **Tutti → Stato → Eliminate da me**, con «Ripristina proposta». Non vengono cancellati contatti, note, fonti o incassi; le statistiche storiche rimangono conservate. Ripristinare rimuove soltanto l’esclusione manuale, senza annullare gli altri criteri di target. Le scelte riguardano il sito eliminato: non vengono inferite esclusioni di altre aziende simili.

## Ricerca di clienti diretti

A usa query di progetti e fornitori per negozi e piccole aziende; riconosce richieste di siti/e-commerce anche senza la parola «freelance». B mantiene le ricerche di collaborazione con agenzie. C cerca crescita accompagnata da un progetto digitale dichiarato e continua a escludere i soli trasferimenti.

D cerca sempre nuovi siti, anche con un archivio già popolato: query per artigiani, negozi, manifattura, professionisti e ospitalità in Veneto, Lombardia, Piemonte e Toscana. Prima di Lighthouse esclude le agenzie che si presentano come tali, le località escluse e gli altri target non ammessi. I siti misurati negli ultimi sette giorni vengono saltati nelle ricerche automatiche; il controllo manuale di un URL resta disponibile. Se la ricerca è indisponibile o non completa la sessione, usa candidati salvati e vecchie bozze ancora non contattate. Ogni candidato deve comunque superare i controlli attuali.

Con più motori selezionati, l’ordine è D → A → C → B → E, per riservare prima risorse alla ricerca di clienti diretti. La ricerca usa SearXNG gratuito e le categorie mostrano i risultati effettivi, anche quando sono zero.


## Aziende e Privati

Il menu e le tab della raccolta separano **Aziende** (agenzie e partner) e **Privati** (clienti diretti: negozi, artigiani, professionisti e altre attività). «Tutti» riunisce i contatti. I contatori indicano le schede attive, escluse quelle eliminate, perse o scartate.

La categoria è un suggerimento commerciale, non la forma giuridica. Le nuove verifiche usano la presentazione del sito; per le vecchie schede si usano i riscontri B e il settore, indicandolo come suggerimento correggibile. La fonte della classificazione è visibile nel riepilogo quando disponibile. **Stato e note → Categoria del contatto** permette di correggerla: la scelta viene salvata per azienda e ha precedenza sulle ricerche successive, anche con più motori o dopo un ripristino.
