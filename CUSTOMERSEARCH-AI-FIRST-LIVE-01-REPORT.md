# CustomerSearch — prima validazione commerciale AI-first

Campagna **44**, 20 ottobre 2026, dalle **16:47:22 alle 16:49:25 CEST**; circa 122 secondi. Una sola campagna, nessuna ripresa, nessuna seconda prova.

## Esito

**NO-GO per una nuova prova a pagamento prima di correzioni offline.** Il percorso AI-first è stato eseguito realmente, ma non ha dimostrato utilità commerciale: **0 opportunità utilizzabili**, 0 decisioni valide INTERESTING e 0 decisioni valide NEEDS_RESEARCH. Questo risultato non dimostra l’assenza di clienti sul mercato: la prova è limitata e presenta problemi tecnici e di strategia.

Sono state effettuate **20 chiamate OpenAI su 30**, con **10 risposte valide**: 5 piani e soltanto 5 delle 15 valutazioni commerciali. Le altre 10 valutazioni sono state invalidate. **8 richieste Serper**, 34 risultati/URL distinti, **16 originali acquisiti**, 35 schede tecniche comprendendo l’alias di un redirect. Questi numeri non sono aziende interessate né clienti.

Costo AI stimato sui token restituiti: **0,06153375 USD**, sotto 0,75 USD. Fatturazione effettiva del provider non verificata. Nessuna email, contatto, candidatura, risposta o acquisizione cliente.

## Preparazione e controlli

- Nessuna campagna attiva prima dell’avvio. La 42 era già sospesa; la 43 esaurita. Nessuna è stata ripresa.
- Verificato il vecchio processo 16529, porta 8765 e directory del progetto; arresto SIGTERM e riavvio con `.venv/bin/python app.py`, nuovo PID 33876. Backend lasciato disponibile, ricerca ferma.
- Chiave disponibile nell’ambiente ereditato, mai stampata. Le 20 risposte reali con token di utilizzo confermano l’accesso effettivo del worker al provider.
- REMOTE, `gpt-5.4-mini`, endpoint OpenAI Chat Completions, modalità configurata Shadow. **Shadow qui non è un confronto parallelo col legacy**: il motore decisionale della nuova campagna è `ai_first_1`.
- Ledger: 5 `RESEARCH_PLAN_6` e 15 `COMMERCIAL_DECISION_1`; nessuna chiamata SCREEN/READ legacy e nessuno screening AI degli snippet.
- Snapshot SQLite prima dell’avvio, integrità verificata, conteggi e impronte. Integrità finale `ok`, nessuna violazione delle chiavi esterne. CRM, impostazioni e tutte le righe delle campagne precedenti invariati, con la sola eccezione diagnostica descritta sotto.
- Eseguiti in questa sessione **35 test AI-first**, **3 test Stop/ripresa/budget** e un probe offline con gli esatti limiti 30/0,75/6 per flusso. Il probe prova 5 piani più 25 originali con provider sintetico e rifiuta ulteriori chiamate non in cache. Non prova la qualità semantica del modello. I 1.954 test citati nella validazione precedente non sono stati tutti rieseguiti.
- Nessun Stop/ripresa live: avrebbe prolungato la prova. L’arresto osservato è automatico per blocco della coda, non un test live di saturazione del tetto 30/0,75.

## Configurazione effettiva

Tutti i cinque flussi abilitati. Limiti specifici della sola campagna: 30 chiamate AI complessive, 0,75 USD stimati, fino a **6 chiamate per flusso** per proteggere la copertura, nessun retry AI aggiuntivo. Restano 8.192 come limite input configurato e 1.500 output; nessun aumento. Le impostazioni generali del database non sono state modificate.

Regioni mantenute: Veneto, Lombardia, Piemonte, Emilia-Romagna, Liguria, Friuli-Venezia Giulia, Trentino-Alto Adige, Valle d’Aosta e Toscana. Modalità Deep precedente; massimi Serper precedenti di 36 richieste per flusso, 180 totali; 24 query per flusso, altri limiti invariati. Consumo Serper effettivo: 8 richieste di rete, circa 8 crediti secondo il contatore stimato dell’app; saldo e tariffa monetaria dell’account non verificati.

Le quote hanno protetto le chiamate iniziali di tutti i flussi. **Non hanno garantito cinque ricerche effettive**: Aziende non ha mai interrogato Serper a causa del piano non eseguibile. Agenzie, Startup e Notizie hanno raggiunto la quota di 6 chiamate; Aziende e Social ne hanno usata una ciascuno. Le dieci chiamate residue non sono state redistribuite né i limiti modificati.

| Flusso | AI | Piani / analisi originali | Risposte valide | Query Serper | Originali | INTERESTING | USD stimati |
|---|---|---|---|---|---|---|---|
| AZIENDE | 1 | 1 / 0 | 1 | 0 | 0 | 0 | 0.003298 |
| AGENCIES | 6 | 1 / 5 | 2 | 1 | 5 | 0 | 0.019245 |
| SOCIAL | 1 | 1 / 0 | 1 | 3 | 0 | 0 | 0.003412 |
| STARTUPS | 6 | 1 / 5 | 3 | 2 | 5 | 0 | 0.018176 |
| NEWS | 6 | 1 / 5 | 3 | 2 | 6 | 0 | 0.017403 |

## Query autonome e qualità della discovery

Tutti gli 8 testi eseguiti provengono dai piani AI di questa campagna; quattro ulteriori selezioni sono state recuperate dai piani salvati senza una seconda inferenza. Nessuna query inserita manualmente per aiutare il pilota. Sono stati proposti 15 testi complessivi: 3 per flusso; quelli non selezionati restano nel ledger/metrica. Due espressioni OR di NEWS sono state normalizzate deterministicamente.

| Task | Flusso | Query effettiva, prima dell’aggiunta automatica -filetype:pdf | Risultati |
|---|---|---|---|
| 7368 | AGENCIES | site:.it Lombardia studio digitale ("collaboriamo" OR "partner tecnici") (ecommerce OR web app) | 10 |
| 7369 | SOCIAL | site:linkedin.com/posts Veneto "cercasi sviluppatore" web | 0 |
| 7370 | STARTUPS | site:.it startup Lombardia "collabora con noi" frontend | 2 |
| 7371 | NEWS | site:ansa.it Veneto azienda annuncia espansione (2026 OR inaugura) nuovo stabilimento 2026 | 1 |
| 7387 | SOCIAL | site:linkedin.com/posts Lombardia "cerco" ecommerce sviluppatore | 1 |
| 7389 | NEWS | site:ilgazzettino.it Veneto impresa lancia nuovo prodotto (2026 OR apre) nuovo mercato 2026 | 10 |
| 7400 | STARTUPS | site:.it startup Piemonte ecommerce sviluppo sito | 10 |
| 7410 | SOCIAL | site:linkedin.com/posts Emilia-Romagna "cerchiamo" "sviluppatore frontend" | 0 |

**Aziende:** tutte le tre proposte iniziano con `site:*.it`, rifiutato dal parser con `invalid_site_operator`: imballaggi Veneto, serramenti Lombardia, lavorazioni meccaniche Piemonte. Il piano è valido come JSON, ma nessuna query è eseguibile. Il recupero successivo viene negato dal tetto condiviso di pianificazione: per 30 chiamate e 5 flussi `budget.available` ammette 5 piani/ripiani in tutto. Sono già consumati dai cinque avvii. La quota economica non è esaurita.

**Agenzie:** “collaboriamo” e “partner tecnici” attirano prevalentemente fornitori che vendono servizi ai clienti. La presenza dei termini non dimostra una disponibilità verso collaboratori esterni.

**Startup:** la prima query produce due corsi ITS; la seconda servizi di agenzie e un avviso regionale. Una descrizione di strategia promettente non rende selettiva una query generica su sviluppo siti.

**Social:** 3 query, 2 senza risultati, 1 post indicizzato. L’originale LinkedIn è escluso dalla policy di accesso; nessun login o aggiramento. Non è verificato un annuncio leggibile e attuale. Questo campione non misura la qualità delle opportunità presenti su LinkedIn in generale.

**Notizie:** una query restituisce un articolo ANSA su Sardegna del 2024; l’altra home, tag, indici e articoli del Gazzettino. Tali URL sono stati restituiti dalla ricerca: non risultano approfondimenti autonomi giustificati da un bisogno già osservato. Inserire “2026” nel testo della query non garantisce la data degli articoli.

## Risultati commerciali e revisione indipendente

Decisioni valide: **5 NOT_INTERESTING, 0 INTERESTING, 0 NEEDS_RESEARCH**. Stati UI: 5 REJECTED, 11 NEEDS_REVIEW, 4 UNVERIFIABLE, 15 DISCOVERED. **NEEDS_REVIEW non equivale a NEEDS_RESEARCH**: qui raccoglie 10 risposte invalide e un originale senza evidenza sufficiente per invocare il modello.

Revisionati tutti i 16 originali, tutti gli 11 NEEDS_REVIEW e tutti i 5 negativi validi. Nessun candidato formalmente promosso. Per completezza sono stati esaminati anche i **due INTERESTING grezzi** nei diagnostici:

- **Polygon Studio, record 1166 / chiamata 1143:** identità commerciale riconoscibile nella pagina, e-commerce affine alle competenze di Diego. Ma l’invito è a richiedere un preventivo come cliente. L’AI lo interpreta erroneamente come opportunità di collaborazione, pur ammettendo l’assenza di un invito tecnico. Email aziendale presente nell’originale, ma nessuna richiesta esterna né disponibilità attuale provata. Last-Modified del 20/10/2026 non è la data di un incarico. **Falso positivo bloccato**, non lead utilizzabile. Prossima azione: non contattare su questa motivazione.
- **Pyramid Web Agency, record 1171 / chiamata 1147:** competenze web affini, ma “Servizi alle Agenzie” indica un’offerta, non una domanda. I valori cercati nei dipendenti non dimostrano lavoro freelance disponibile. Nessuna data di richiesta o compenso verificati. Il link “Lavora con Noi” è una pista da leggere, non la prova di un incarico. L’email del Garante nel testo privacy non è un contatto dell’agenzia. **Falso positivo bloccato**; possibile approfondimento separato, senza promozione.

Entrambi sono stati bloccati per riferimenti alle prove non validi, **non da una dimostrata comprensione corretta dell’intento commerciale**. Correggere soltanto gli ID potrebbe far emergere questi falsi positivi nella shortlist: serve anche valutazione semantica.

| Record | Soggetto / fonte originale | Esito app | Revisione indipendente |
|---|---|---|---|
| 1166 | [Polygon Studio](https://polygonstudio.it/creazione-siti-e-commerce-monza-brianza-e-lombardia/) | NEEDS_REVIEW | Servizi e-commerce offerti ai clienti; richiesta di preventivo, non invito a collaboratori. Nessun incarico o disponibilità a collaboratori dimostrati. Non proporre come lead qualificato. |
| 1168 | [Webbes / Alkimedia: marchio e titolarità da chiarire](https://www.webbes.it/agenzia-di-comunicazione/) | NEEDS_REVIEW | La pagina dichiara una rete di professionisti interni ed esterni. Non dichiara disponibilità attuale a nuove collaborazioni. Verificare titolarità e una pagina collaborazione/lavoro prima di attribuire un invito. Nessuna opportunità persa dimostrata. |
| 1170 | [Inputcomm / Alkimedia: titolarità da chiarire](https://www.inputcomm.it/web-agency-erba-creazione-siti-web-erba-como/) | REJECTED | Pagina di vendita di servizi web. La decisione negativa è corretta; il dominio usato come nome non verifica l’impresa. Scartare questa pagina come richiesta di sviluppo. |
| 1171 | [Pyramid Web Agency](https://www.lapyramid.it/agenzia-di-comunicazione-pyramid-web-agency.aspx) | NEEDS_REVIEW | Servizi alle agenzie e valori aziendali non dimostrano domanda di sviluppo esterno. Il menu contiene Lavora con Noi. Eventuale lettura della pagina lavoro può cambiare il giudizio; non è stata acquisita. Non dichiarare un incarico disponibile. |
| 1175 | [Element / Sanmarco Informatica](https://www.elementdigitalimage.com/) | NEEDS_REVIEW | Fornitore di servizi digitali appartenente a Sanmarco Informatica SpA. Nessun invito corrente a nuovi collaboratori. Non qualificare; appartenenza al gruppo e natura di fornitore sono controprove. |
| 1176 | [ITS Angelo Rizzoli](https://www.itsrizzoli.it/corsi/ifts-ai-solutions-developer/) | NEEDS_REVIEW | Pagina del corso IFTS AI Solutions Developer; formazione per studenti, non commessa startup. Escludere dai lead commerciali. |
| 1177 | [ITS Angelo Rizzoli](https://www.itsrizzoli.it/corsi/its-ai-full-stack-developer-specialist/) | NEEDS_REVIEW | Corso ITS AI Full Stack Developer Specialist: le competenze descritte sono didattiche. Escludere dai lead; non attribuire al committente il fabbisogno formativo degli studenti. |
| 1178 | [ANSA è l’editore; azienda cliente non verificata](https://www.ansa.it/sito/notizie/mondo/americalatina/2024/08/23/il-grande-real-estate-brasiliano-porta-il-lusso-in-sardegna_35192bcb-539d-4efe-9ce3-cec812d529ff.html) | REJECTED | Articolo del 23/08/2024 su real estate brasiliano e Sardegna, non evento Veneto 2026 né bisogno digitale. Escludere la pagina dal percorso attuale; non contattare ANSA come soggetto della notizia. |
| 1180 | [Panificio Nuovo Forno, menzionato in un articolo](https://www.ilgazzettino.it/nordest/treviso/panificio_nuovo_forno_chiude_sindaco_bortolato_comprate_botteghe_mogliano-9254244.html) | NEEDS_REVIEW | Articolo del 19/12/2025 sulla chiusura di un forno a Mogliano. Nessun progetto digitale osservato. Il modello non ha valutato la pagina: evidence_insufficient. Non proporre un rifacimento; verificare stato dell’attività prima di qualsiasi ulteriore indagine. |
| 1181 | [Il Gazzettino, editore](https://www.ilgazzettino.it/) | NEEDS_REVIEW | Home di quotidiano con contenuti eterogenei; non una richiesta attribuibile a un’impresa. Escludere home e indici dall’analisi commerciale a pagamento finché manca un evento/soggetto specifico. |
| 1182 | [Il Gazzettino, sezione Treviso](https://www.ilgazzettino.it/nordest/treviso/) | REJECTED | Archivio territoriale. TREVISO non è un’identità aziendale. Il rifiuto commerciale è corretto. Non trasformare il nome della sezione in un’impresa. |
| 1183 | [Il Gazzettino, tag Coca-Cola](https://www.ilgazzettino.it/t/coca-cola) | NEEDS_REVIEW | Pagina tematica, non un annuncio del marchio. Non dimostra bisogno di un sito o collaborazione. Scartare il tag; non attribuire i contenuti al brand come richiesta. |
| 1184 | [Il Gazzettino, tag Carta Dedicata a Te](https://www.ilgazzettino.it/t/carta-dedicata-a-te) | NEEDS_REVIEW | Archivio su una misura pubblica. Il titolo del tema non è un’azienda. Scartare come opportunità per Diego. |
| 1190 | [Gianmatteo Garrone / MG, fornitore](https://www.matteogarrone.it/realizzazione-siti-web/piemonte.html) | REJECTED | Pagina promozionale di un professionista web. MG Realizzazione Siti Web Piemonte è il nome marketing acquisito, non una startup committente. Decisione negativa corretta; distinguere identità del fornitore dal ruolo di compratore. |
| 1192 | [Regione Piemonte, istituzione](https://www.regione.piemonte.it/web/temi/istruzione-formazione-lavoro/lavoro/sostegno-allimprenditorialita/start-up-innovative-nuove-misure-sostegno-della-regione-piemonte) | NEEDS_REVIEW | Informazioni su incentivi e incubatori; nessuna startup nominata con una richiesta di sviluppo. Non trattare il bando come incarico. I recapiti di Regione/incubatori non identificano clienti. |
| 1193 | [Zoe Web Solutions](https://www.zoewebsolutions.it/web-agency/piemonte) | REJECTED | Pagina commerciale di agenzia. Il modello ha usato il lungo titolo SEO come nome dell’entità. Scarto coerente; correggere l’estrazione del nome prima di usarlo in dossier futuri. |

**Possibili opportunità perse:** nessuna dimostrabile nei materiali esaminati. Webbes dichiara una rete di professionisti esterni e Pyramid espone un link lavoro: due piste per acquisire ulteriori prove, non due commesse né due inviti verificati. I 15 record rimasti DISCOVERED e le fonti non consultabili non possono essere scartati commercialmente sulla base degli snippet. Non sono stati approfonditi fuori budget o mediante chiamate aggiuntive.

## Problemi dimostrati

1. **Riferimenti alle prove: gravità alta.** 9 delle 15 valutazioni commerciali usano `metadata`, `e1` o ID di link `l…` al posto di veri `segment_id` `s…`. Confronto effettuato tra risposta grezza e segmenti effettivamente inviati: riferimenti inesistenti, non collisioni osservate. Una decima fallisce `unsupported_actor`, nominando “Element fa parte di Sanmarco Informatica S.p.A.” come identità. Non allentare i controlli: isolare i namespace, limitare la scelta ai segmenti reali e collaudare il recupero circoscritto offline.
2. **Informazione commerciale troppo compressa: gravità alta.** Nei 15 input commerciali rimangono da 34 a 713 caratteri di prove. ANSA riceve solo 34 caratteri di metadato editore; Webbes solo 133 caratteri di site_name; Regione Piemonte 150. Il codice confronta un conteggio in byte comprensivo di schema/prompt con il massimo input e taglia le prove. Il replay locale delle prove salvate conferma il taglio: Webbes passa da 2.300 caratteri selezionati a 133 inviati, Polygon da 1.443 a 317; Webbes registra 7.913 byte stimati contro 2.169 token input effettivi. Queste misure sono in `evidence-compression.json` e nelle metriche. La perdita di testo è osservata; non si può affermare che ripristinarlo genererà automaticamente clienti. Riprogettare il contenuto minimo leggibile entro i limiti, prima di comprare più chiamate.
3. **Intento commerciale e rumore: gravità alta.** Due proposte INTERESTING confondono offerta di servizi e domanda. Startup e News consumano verifica su corsi, pagine promozionali, tag e istituzioni. Richiedere una direzione esplicita del rapporto commerciale e controllare la coerenza tra ipotesi e URL prima di consumare la quota di verifica.
4. **Recupero pianificazione: gravità alta.** Tutti possono pianificare, ma il tetto di 5 piani impedisce di riparare le 3 query Aziende e di riformulare Social dopo tre tentativi. Mantenere invariati i massimi totali e prevedere una quota/restituzione interna per un recupero mirato; non alzare indiscriminatamente il budget.
5. **Identità semantica: gravità media/alta.** Tra i negativi validi compaiono “TREVISO” e un lungo titolo SEO usato come nome. Una sola scheda ha identity_verified=true, ma è il fornitore MG, non un committente interessato. Gli editori e le etichette delle pagine non sono clienti identificati. Gli scarti sono coerenti, la rappresentazione dell’identità resta difettosa.
6. **Stato finale e metriche: gravità media.** Il blocco HTTP 503 di una fonte determina il messaggio generale di pausa. Al contempo 14 task sono in budget e tre flussi restano marcati running, benché non ci sia un worker attivo. Tutte le ricevute Serper riportano `new_urls=0` malgrado 34 URL ammessi; le operazioni usano `completed_without_decision` anche per negativi validi. Usare ledger e record per questo report, non interpretare questi contatori come assenza di discovery o mancato giudizio.

## Date, accessi e arresto

Le date salvate distinguono pubblicazione, modifica e osservazione: ANSA 23/08/2024, articolo sul forno 19/12/2025, Last-Modified dei siti, orario corrente degli indici senza ruolo di pubblicazione. Non è emersa una promozione basata su data falsa; il limite principale è aver speso quota su fonti non pertinenti e spesso prive di richiesta.

Un HTTP 503 su Fa Studio è differito; due directory Sortlist e un LinkedIn sono bloccati dalla policy. Nessuna restrizione aggirata. **Stato finale `blocked`**, non “completata con successo”. Messaggio app: pausa fonti fino alle 16:53:08 CEST. Rimangono un retry pending per quel sito e 14 task in budget. La prova termina qui: **non ho premuto Riprendi**. Nessuna campagna running/waiting/stopping al controllo finale. Il processo worker 33929 risulta `defunct`: ha terminato il lavoro e non può consumare crediti, ma il processo padre non lo ha ancora raccolto. È un ulteriore dettaglio di pulizia del ciclo di vita da verificare offline.

## Costi e limiti delle misure

41.215 token input e 6.805 output dichiarati dalle 20 risposte. Stima alle tariffe configurate di 0,75 USD/M input e 4,50 USD/M output: **0,06153375 USD**. Tutte le chiamate hanno utilizzo noto; nessun dato di fattura OpenAI. Costo Serper in USD sconosciuto. Nessun costo per opportunità utilizzabile calcolabile perché il denominatore è **zero**; non riportarlo come 0 USD. Nessuna precisione commerciale stimabile su una shortlist vuota.

## Memoria e preservazione

Piani, scelte, feedback di query, ricevute e errori sono persistiti per la pianificazione futura. Le proposte non selezionate sono state effettivamente riutilizzate senza nuove inferenze. Non è dimostrato apprendimento predittivo né miglioramento delle conversioni. Gli esiti tecnici e commerciali devono restare distinti; non creare blacklist permanenti da questa piccola prova. Prima della prossima campagna verificare l’effetto dei contatori `new_urls=0` e degli esiti operativi generici sulla memoria.

**Eccezione al vincolo di nessuna cancellazione:** l’app esistente limita `agent7_diagnostics` a 200 righe e ha ruotato automaticamente **10 diagnostici storici** inserendo i 10 nuovi. Nessun codice è stato cambiato per farlo e nessuna cancellazione è stata eseguita manualmente. Tutti i 10 estratti sono conservati nel backup pre-prova e nel file privato `implementation-report/ai-first-live-01/retained-historical-diagnostics.json`. Non ho alterato il database per reinserirli. Di conseguenza non dichiaro il rispetto assoluto del vincolo “nessuna cancellazione”: le campagne, le prove commerciali e il CRM precedenti sono invariati, i diagnostici storici nel database no.

## Raccomandazione

Prima di una nuova prova, correggere e verificare offline tre aspetti: **prove leggibili e citazioni valide**, **distinzione domanda/offerta e selezione delle fonti**, **recupero di un piano senza aumento del budget complessivo**. Aggiungere alle regressioni gli esiti reali Polygon, Pyramid, Webbes, ITS, ANSA e i titoli usati come identità. Separare gli errori tecnici dai negativi commerciali nella memoria e rendere coerente lo stato dei flussi alla chiusura.

Nessuna di queste modifiche è stata implementata durante la validazione. Nessun invio, nessun commit/push, nessun nuovo acquisto, nessuna campagna 45. Backend disponibile, ricerca 44 ferma.

## Artefatti verificabili

- `CUSTOMERSEARCH-AI-FIRST-LIVE-01-METRICS.json`: configurazione, ledger, query proposte/eseguite, fonti, task, stati, errori, revisione manuale e integrità.
- `implementation-report/ai-first-live-01/offline-tests.txt` e `budget-probe.json`: test di questa sessione.
- `database-before.json`, `integrity-after.json`, `code-hashes.json`: impronte e verifiche.
- `database-before.sqlite3`: snapshot privato completo, circa 1,9 GB, con integrità verificata. Contiene configurazioni e dati privati: non pubblicarlo.

La qualità commerciale resta da dimostrare; nessun cliente è stato acquisito tramite questa prova.
