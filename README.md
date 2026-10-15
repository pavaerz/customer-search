# CustomerSearch 4.1

Ricerca commerciale locale basata su prove, per progetti completi di siti aziendali, e-commerce e web app. Il traguardo è **50 aziende uniche qualificate per campagna**; le verifiche incomplete e gli scarti non riempiono la shortlist.

## Avviare

```bash
.venv/bin/python app.py
```

Apri **http://127.0.0.1:8765**. Usa questo indirizzo esatto: Host, Origin e CSRF proteggono le operazioni. Sul Mac attuale `python` è Python 2: usa `.venv/bin/python`.

**Correzioni della campagna 4:** filtro di pertinenza prima del download, identificazione distinta dall’età delle notizie, errori di accesso classificati, pause per dominio e percorso query → decisione → azienda. La ricerca resta avviata dall’utente. [Analisi, confronto sui dati salvati e test](docs/CAMPAGNA4-CORREZIONI.md).

**Installazione attuale: solo Serper (Google).** SearXNG è spento e non è un fallback. La chiave già salvata sul Mac è riutilizzata dalla ricerca ordinaria; credenziali da sole non attivano provider. La scelta viene conservata ai riavvii. Le nuove installazioni prive di una scelta esplicita mantengono il default gratuito storico.

In **Impostazioni → Serper e analisi** sono visibili richieste registrate e limiti volontari giornalieri/mensili. Campo vuoto = nessun tetto locale; zero blocca le richieste. La migrazione 5.0 rimuove i vecchi default 30/930, preservando limiti personalizzati. Saldo e addebiti effettivi dell’account restano sconosciuti. Ogni tentativo viene contato prima dell'invio, anche se fallisce; le risposte in cache non consumano altre richieste. Raggiunto il limite, la campagna si ferma conservando i progressi: modificare il limite o attendere il nuovo periodo, poi premere Riprendi. Nessun acquisto, rinnovo o ricarica automatica. Il contatore locale non è il saldo dell'account Serper.

**Configurazione confermata il 14 ottobre 2026:** nessun tetto giornaliero o mensile Serper, come richiesto. Anche il banco di prova `scripts/pilot50_cycle.py` non impone un budget di richieste predefinito. I campioni di collaudo possono terminare dopo un numero dichiarato di verifiche; questo non limita le campagne dell’app.

**Modalità di lavoro concordata:** le ricerche reali vengono avviate dall’utente nell’app. Durante lo sviluppo si migliorano criteri e funzionamento usando test e dati già raccolti; non si avviano piloti, richieste Serper o consultazioni di nuovi siti senza una nuova istruzione esplicita dell’utente.

I confronti precedenti restano consultabili in Impostazioni, insieme al campo della chiave API. In modalità Serper il confronto con SearXNG è disabilitato anche sul server. [Attivazione e collaudo](docs/SOLO-SERPER.md).

**Ollama e Qwen2.5 7B sono già installati nel progetto.** L’avvio dell’app avvia il runtime locale, se necessario, ma non scarica nulla. Modello in `.runtime/models`, una inferenza alla volta, cloud disabilitato nel runtime gestito dall’app. Per reinstallarli esplicitamente sul Mac Apple Silicon:

```bash
.venv/bin/python scripts/setup_ollama.py
```

Il modello richiede circa 4,7 GB su disco. Le altre piattaforme richiedono l’installazione ufficiale di Ollama e `ollama pull qwen2.5:7b`. Il servizio deve ascoltare su `127.0.0.1:11434`. Senza modello, l’identificazione deterministica può continuare, ma l’analisi commerciale incompleta non viene promossa. Log locale: `.runtime/ollama.log`.

## Utilizzo

**Ricerca a partire dalle imprese:** le nuove campagne includono sempre insieme produttori/piccole aziende B2B, negozi/marchi e servizi/professionisti. Non serve scegliere un settore. Le query alternano i tre gruppi e includono annunci freelance LinkedIn indicizzati e pagine aziendali “Lavora con noi”, “Jobs” e “Careers”. I link alle pagine lavoro presenti nella navigazione del sito vengono seguiti fino agli annunci web pertinenti. Le imprese identificate restano distinte dalle opportunità qualificate. [Metodo, collaudo e limiti reali](docs/RICERCA-AZIENDE.md).

1. Premi **Avvia ricerca**. Si parte dal Veneto; nelle preferenze puoi scegliere servizio, tipo di cliente e ampliare il territorio.
2. Segui URL scoperti/scartati e aziende promettenti/in verifica/qualificate **X/50**. Riepilogo, categorie ed elenco deduplicano le aziende con gli stessi criteri. Usa le schede **Opportunità qualificate**, **Candidati promettenti**, **Aziende esaminate**.
3. Apri una scheda: motivo, tempestività, progetto proponibile, citazioni e fonti originali. Il dossier mostra requisiti, obiezioni, incognite e contributi al punteggio.
4. **Ferma ricerca** conserva risultati e coda; **Riprendi** mantiene la stessa campagna. Dopo un riavvio l’app sospende il lavoro interrotto, senza ripartire di nascosto.
5. **Conferma contatto** rende verde la scheda. Trascina le schede in **Contatti → Bacheca**, oppure usa il selettore di stato. **Elimina proposta** esclude il dominio finché lo ripristini da **Contatti → Elenco → Eliminate da me**.

**Aziende** raccoglie agenzie e partner, comprese quelle che dichiarano disponibilità a collaborazioni freelance WordPress/frontend senza una commessa aperta. **Privati** indica clienti diretti: negozi, artigiani, professionisti e imprese; non persone private. Filtri per progetto, territorio, qualità, nome e stato commerciale. Le categorie corrette manualmente restano valide.

In **Candidati promettenti**, le richieste di collaborazione freelance riscontrate
sul sito ufficiale mostrano citazione, ruolo, condizioni contrattuali quando
pubblicate e contatto aziendale. Identità, territorio e richiesta devono essere
verificati. Sono contatti da approfondire: disponibilità, ambito e compenso vanno
concordati; non vengono contati tra i 50 progetti completi qualificati. La data
di creazione di una pagina “Lavora con noi” non viene attribuita automaticamente
ai singoli annunci. Il sito di un'agenzia che vende servizi non costituisce una
richiesta di collaborazione. PDF e allegati sono esclusi dalla ricerca clienti;
la ricerca bandi conserva il proprio lettore di documenti.

I **Partner disponibili · da contattare** sono distinti dalle richieste attive:
la pagina originale deve dichiarare sia le competenze web sia l'apertura a
collaborazioni freelance. Una generica candidatura spontanea non basta.
Questa preferenza, confermata dall'utente, è applicata alle nuove verifiche;
non trasforma automaticamente gli scarti storici in risultati qualificati.

Correzioni, campioni reali e limiti misurati: [rapporto sulla domanda commerciale](docs/DOMANDA-COMMERCIALE.md).

Le vecchie schede, gli ID, le note, i contratti, le bozze e le interazioni sono conservati in **Contatti** e nei backup privati, secondo le pulizie esplicite già richieste. Sono etichettati “Non ancora validata con i criteri 4.0”: non diventano automaticamente nuove opportunità.

Nella scheda puoi registrare **Interessante, Non pertinente, Contattato, Nessuna risposta, Risposta negativa/positiva, Conversazione avviata, Preventivo richiesto, Cliente acquisito**, con una nota. Le date e gli esiti rimangono nello storico. Un contatto pubblico non equivale a consenso. Nessuna risposta viene dedotta automaticamente.

**Preferenze e attività → Confronta le strategie** mostra metriche automatiche e risultati commerciali manuali della campagna. Il programma di 30 giorni è una finestra di osservazione, non uno stop automatico.

## Cosa qualifica un’azienda

Il nuovo ramo di identificazione aziendale precede la ricerca del bisogno. Le strategie complementari vengono selezionate secondo il progetto e il tipo di cliente; le dodici strategie precedenti rimangono nello storico. La correlazione combina prove e non produce query autonome. Una lettura preliminare senza modello precede le verifiche approfondite. I motori A/B/C/D/E precedenti rimangono per consultazione dello storico e controlli tecnici manuali; non governano la nuova ricerca.

Servono identità e territorio verificati, prove pertinenti e attuali, bisogno specifico, progetto completo, verifica di alternative e soluzioni già presenti, fattibilità delimitata, contatto pubblico e validazione approfondita. Per bisogni impliciti occorrono riscontri complementari. Il modello estrae citazioni e propone un’interpretazione; le regole applicano requisiti obbligatori e priorità almeno 70/100.

La valutazione considera anche aziende che non dichiarano una carenza. Un evento recente può essere confrontato con una condizione effettiva del canale, per esempio un nuovo pubblico rispetto a un catalogo riservato ai rivenditori. La relazione richiede una revisione separata, fonti attribuite all’impresa, controllo delle soluzioni esistenti e motivazione del progetto completo rispetto a interventi minori. Nel dossier **Come abbiamo collegato i fatti** distingue questa inferenza dalle citazioni. Non significa che l’azienda abbia deciso di acquistare. Le pagine di marchi collegati vengono considerate come possibili soluzioni già presenti.

Un trasferimento, un sito datato, un punteggio Lighthouse basso, un catalogo o ordini via email **non bastano**. Candidature generiche e assunzioni dipendenti non sono commesse. Per una web app, sicurezza, integrazioni, dati o manutenzione critici non chiariti impediscono la qualifica.

Soglie interne: **2.000 €** per un sito completo, **5.000 €** per e-commerce. Budget aziendale ignoto = sconosciuto e zero punti economici. Nessuna stima automatica della capacità di spesa. Lighthouse e i controlli SEO/GEO/AEO restano misure di supporto, senza promettere ranking, citazioni AI o vendite.

Priorità Veneto, Lombardia, Piemonte e Toscana, poi altre regioni settentrionali e Lazio. Marche, Umbria, Sud, S.p.A. e grandi gruppi esclusi. Un indirizzo sconosciuto non viene considerato favorevole.

## Fonti, memoria e limiti

L’ottimizzazione della discovery introduce pianificazione progressiva, pause tecniche dei provider e diagnostica in **Preferenze e attività → Come sta andando la ricerca**. [Diagnosi, architettura, confronto e limiti verificati](docs/DISCOVERY-ADATTIVA.md). I controlli commerciali restano invariati; il miglioramento di acquisizione clienti non è ancora dimostrato.

- Ricerca clienti: Serper paginato per settore e territorio, identificazione delle imprese e verifica commerciale sui loro siti. Anche senza annunci espliciti. [Correzione dei risultati estranei e collaudo](docs/PROSPEZIONE-DIRETTA.md).
- La ricerca clienti attuale visita siti ufficiali di imprese e agenzie, pagine di recruiting e richieste freelance. Directory, notizie economiche generiche, feed territoriali e allegati non alimentano nuove esplorazioni. Gli annunci LinkedIn indicizzati sono soltanto indizi da verificare sul sito aziendale: nessun accesso automatico al social. I lettori editoriali storici e la ricerca bandi restano separati; non sono fallback della ricerca clienti.
- Negli articoli con un corpo esplicito l’analisi separa testo principale e notizie correlate, conservando il testo originale nel dossier. Le anteprime per abbonati rimangono non verificabili e non avviano la ricerca delle aziende citate. La disponibilità di una fonte non dimostra la qualità delle opportunità.
- Lettura delle pagine originali: snippet esclusi dalle prove. Documenti conservati con URL, impronte, date, provider e citazioni controllate. Un comunicato ripubblicato non diventa più segnali indipendenti.
- Le prove diverse dello stesso comunicato restano consultabili, comprese le controprove; una copia non aumenta indipendenza, punteggio o confidenza. Il confronto dei documenti usa il corpo selezionato dell’articolo quando disponibile, per non confondere menu comuni con notizie copiate.
- Prima della proposta, un controllo locale separato cerca dichiarazioni di strumenti digitali già disponibili negli estratti pertinenti. Le citazioni restano letterali; strumenti dichiarati sospesi o futuri non vengono presentati come operativi. Una soluzione esistente richiede una valutazione di adeguatezza rispetto al progetto: la sua presenza non equivale automaticamente a uno scarto.
- Identità collegata a dominio e dati societari; domini diversi si riuniscono quando l’identità legale coincide. Un editore non viene automaticamente trattato come l’azienda citata. Omonimie e collegamenti incerti restano incompleti.
- Una sede operativa esplicitamente indicata può distinguersi dalle filiali; indirizzi discordanti senza indicazioni restano incerti. I controlli riconoscono anche dichiarazioni editoriali nella homepage e denominazioni S.p.A. prive del suffisso commerciale del marchio, richiedendo riscontri letterali e coerenti con il dominio.
- Le espressioni territoriali nei titoli aziendali, come “Torino e provincia”, non identificano un ente pubblico. Sono riconosciute anche le diciture `Part. IVA` e `p. i.v.a.` e gli indirizzi con provincia separata da trattini tipografici; numeri senza etichetta e sedi non dimostrate restano sconosciuti.
- La citazione usata per identificare l’impresa non limita l’intera analisi: vengono conservati anche gli altri paragrafi del corpo dell’articolo che la nominano, verificandoli contro il testo originale. Paragrafi adiacenti senza attribuzione e notizie correlate non vengono assegnati automaticamente all’azienda.
- Nessun limite complessivo di query o durata. La frontiera di strategie è finita e può esaurirsi; l’app lo dichiara. Timeout tecnici, limiti per documento, rate limit e tentativi differiti rimangono attivi.
- Le verifiche ancora in coda per la stessa identità e lo stesso dominio vengono unite, conservando pagine, prove e provenienza. Nella stessa campagna una pagina invariata già compresa in un controllo completato riutilizza quell’esito. Nuove prove, controlli incompleti, identità diverse e campagne precedenti non vengono saltati con questa scorciatoia.
- Le anteprime datate delle notizie non vengono scambiate per sezioni servizi o pagine legali. La lettura approfondita cerca anche gli annunci del sito già rifatto e gli sviluppi commerciali recenti, aprendo le pagine originali; queste selezioni non assegnano punti né qualificano da sole.
- Lettore HTML e PDF testuali: PDF cifrati, scansionati o troppo estesi, contenuti esclusivamente JavaScript e pagine bloccate o non accessibili possono impedire la verifica. Non viene dichiarata assente una soluzione solo perché non è stata trovata.
- Le eliminazioni e “Non contattare” persistono; aziende già gestite non rientrano nei nuovi 50. Scarti automatici senza nuovi riscontri significativi non vengono riproposti. Le priorità possono cambiare solo con almeno due coorti sufficienti (minimo 10 contatti ciascuna) e risposte effettive: al massimo un turno su cinque favorisce la strategia migliore; il resto resta esplorazione. Nessuna modifica dei requisiti.

Le bozze citano fatti e richiedono revisione manuale. Nessun invio automatico, acquisto o pubblicazione. Il compositore Gmail rimane un’azione esplicita e separata dalla conferma di contatto.

## Backup e verifica

**Pulizia del 15 ottobre 2026:** eliminati backup superati, copie sperimentali inutilizzate e il modello sperimentale non attivo; recuperati circa **12,1 GB** complessivi. Dati commerciali e modello attivo conservati. Backup corrente verificato: `data/backups/cleanup-20261015T090037Z/restore.zip`. [Dettagli, controlli e ripristino](docs/PULIZIA-PROGETTO.md). I percorsi storici nei vecchi report possono riferirsi ad artefatti rimossi; le basi richiamate dai test di migrazione e confronto restano disponibili.

Prima della 4.1: `data/backups/20261013T181253135811Z/`. Snapshot SQLite, progetto, configurazioni e credenziali con hash SHA-256 e permessi restrittivi. Non sono serviti dal server HTTP. I pesi e il runtime scaricabile in `.runtime` sono esclusi dai backup successivi; le istruzioni di reinstallazione sono sopra.

```bash
.venv/bin/python scripts/backup.py
.venv/bin/python scripts/verify_migration41.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_research_ui.py
.venv/bin/python scripts/check_visual_quality.py
.venv/bin/python scripts/check_funnel_ui.py
```

La verifica della migrazione e del ripristino usa copie temporanee e confronta le righe precedenti, non soltanto i conteggi. I test browser usano fixture isolate, Chrome e Playwright. I test HTTP richiedono una porta localhost temporanea.

[Diagnosi e architettura 4.1](docs/ARCHITETTURA-4.1.md) · [Collaudo e pilota 4.1](docs/VERIFICA-4.1.md) · [Esperimento commerciale di 30 giorni](docs/ESPERIMENTO-30-GIORNI.md) · [Migrazione e ripristino](docs/migration41.json).

Il pilota non dimostra efficacia commerciale: risposte, preventivi e contratti devono essere misurati nell’uso reale. La soglia di qualità prevista è almeno 90% di conferme su 20 opportunità revisionate, senza falsi positivi critici; campioni più piccoli non certificano il risultato.

## Evoluzione 5.0 in corso

Pianificazione per ipotesi verificabili, conservazione delle prove editoriali, limiti Serper facoltativi e correzioni del riconoscimento degli editori. [Audit, misure e lavoro ancora da completare](docs/EVOLUZIONE-5.0.md). I nuovi percorsi non hanno ancora dimostrato una precisione commerciale superiore.

Il controllo delle soluzioni esistenti legge anche siti dedicati richiamati da un testo aziendale vicino a pulsanti generici come “Scopri di più”. I collegamenti vengono verificati anche dopo la lettura dei contatti; errori, blocchi e copertura insufficiente restano espliciti. Un collegamento non certifica proprietà, funzionamento o necessità di rifare il sito.
