# Domanda commerciale: correzioni e verifica del 14 ottobre 2026

## Diagnosi

La campagna 5 aveva sei pagine «promettenti», ma una sola azienda ammissibile
all'elenco. Tre pagine di Fusion Work e due di Digitalia descrivevano servizi
venduti, non commesse. Il controllo combinava parole lontane nel testo:
«cerchiamo di creare una collaborazione» e una descrizione di sviluppo web
potevano attivare verifiche costose. Alcune analisi arrivavano poi al limite del
contesto locale senza produrre un bisogno documentato.

Il percorso opposto perdeva richieste pertinenti: un annuncio di un'agenzia
poteva essere sottoposto al profilo industriale B2B; i metadati JobPosting
venivano trattati come assunzione dipendente senza verificare condizioni
freelance. Una richiesta di collaborazione non specifica ancora il budget o
l'intero progetto: non deve diventare una commessa qualificata né scomparire
perché quel perimetro resta sconosciuto.

## Interventi

- Richiesta e competenza web devono essere collegate nel testo originale.
  Espressioni di marketing, negazioni, richieste chiuse e lavori dipendenti
  non dimostrano domanda freelance.
- Nelle pagine con più annunci, la condizione freelance viene associata alla
  stessa sezione/ruolo. Si conservano separatamente citazione della richiesta
  e citazione contrattuale. Se l'indice non basta, lettura di massimo due
  annunci pertinenti collegati dal sito, rispettando gli stessi controlli HTTP.
- Le collaborazioni con identità, territorio e contatto verificati restano
  promettenti e visibili, con ambito e compenso sconosciuti. Non attivano
  l'indagine generica sui mercati dell'agenzia né il modello per inventare
  un progetto. Nessuna promozione ai 50 qualificati.
- La data della pagina careers resta distinta dalla data attribuita al singolo
  JobPosting. Una pagina creata anni fa non prova che ogni ruolo sia scaduto.
  Disponibilità dell'annuncio senza data da confermare con l'azienda.
- Le sedi osservate vengono conservate senza inventare una sede principale.
  Una collaborazione può superare il controllo territoriale con sedi tutte
  verificate nelle aree selezionate; gli altri requisiti rimangono necessari.
- Query per collaborazioni basate su pagine careers e competenze precise;
  eliminata la formulazione generica «partita IVA frontend», che nella prova
  restituiva soprattutto guide fiscali. Esclusioni di aggregatori e PDF nelle
  query di domanda; guide fiscali/formative riconoscibili escluse prima della lettura.
- PDF, documenti Office e archivi esclusi prima del download quando riconoscibili
  dall'URL. PDF dichiarati dall'HTTP respinti prima di leggere il corpo, anche
  senza estensione; cache PDF non utilizzata nella ricerca clienti. Il lettore
  dei bandi resta distinto. Robots, TLS e limitazioni di accesso conservati.
- Scheda della collaborazione con fonte, citazioni, contatto e limiti espliciti.
  Nessun invio, contatto inventato, budget attribuito o risultato fittizio.

Backup di riferimento verificato prima degli interventi:
`data/backups/20261014T161155549946Z/`. Nessuna migrazione distruttiva, modifica
ai contatti o avvio della campagna durante questa verifica. I piloti scrivono
catture e rapporti separati; non inseriscono aziende nel CRM.

## Prove reali e confronto

Otto richieste Serper effettive nel complesso: quattro per lo sviluppo, due
per il primo campione separato, due per la seconda valutazione. Le ripetizioni
su cache e i replay non hanno eseguito nuove richieste. Nessuna inferenza locale
nel collaudo del triage. I crediti residui dell'account non sono deducibili da
questo conteggio. Nessun tetto alle campagne è stato introdotto.

| Campione | Prima | Dopo | Interpretazione |
|---|---:|---:|---|
| Sviluppo, 2 aziende | 0 promettenti | 2 collaborazioni documentate con canale pubblico | Risolve falsi negativi noti; non dimostra generalizzazione |
| Valutazione separata finale, 6 domini | 0 promettenti | 0 promettenti | Nessun miglioramento commerciale dimostrato su questo campione |
| Progetti completi qualificati | 0 | 0 | Nessun budget, commessa o qualifica inventati |

Esempi del campione di sviluppo:

- [Adviva, lavora con noi](https://www.adviva.it/job/): richiesta di collaborazioni
  continuative WordPress/PrestaShop; identità e sede veneta riscontrate,
  canale aziendale pubblico. È una possibilità di collaborazione, non un
  incarico già assegnabile.
- [Jampaa, lavora con noi](https://www.jampaa.it/lavora-con-noi/): ruolo WordPress
  con condizioni freelance/P.IVA nella stessa sezione. Identità, email pubblica
  e sedi riscontrate. Non attribuire il budget annuo della formazione al progetto.

Nel primo campione separato la revisione ha rilevato un falso positivo critico:
la P.IVA di un commerciale era stata collegata al ruolo WordPress in un'altra
parte di un indice. Il campione è stato riclassificato come sviluppo, la causa
corretta e verificata con un test negativo. Non viene usato per dichiarare successo.

Nel campione successivo: un errore di accesso robots, identità incomplete,
formazione, guida, intermediazione e una fonte datata. Nessuno è stato promosso.
Altre quattro pagine non usate per sviluppare il filtro, provenienti da una
query già acquisita, non hanno prodotto nuovi contatti: uno già gestito/escluso,
una sede fuori dalle quattro regioni della prova e due identità/località
incomplete. Esclusioni e limiti sono conservati nelle catture. Non sono falsi
negativi dimostrati; gli accessi incompleti non sono giudizi commerciali.

Rapporti:

- `benchmark50-demand-development.json`: confronto sulle due aziende di sviluppo.
- `benchmark50-direct-demand-round1.json`: include il falso positivo rilevato.
- `benchmark50-direct-demand.json`: valutazione separata finale, sei domini.
- `data/benchmarks50/direct-demand-unread-originals.json`: quattro ulteriori letture.

Il confronto usa il codice precedente del backup e quello aggiornato sulle
stesse pagine congelate, con hash. I replay impediscono rete e modello. La
revisione è dell'assistente di sviluppo, non di un valutatore umano indipendente.
Precision@10/20 resta non calcolabile: campioni insufficienti e nessuna shortlist
qualificata. Non è dimostrato un aumento di risposte, preventivi o clienti.

## Collaudo e riproduzione

507 test superati: `tests50-demand.txt`. Browser desktop/mobile senza errori:
`ui50-demand.json`. Coperti richiesta/contratto nello stesso ruolo, annunci
multipli, date, scarti geografici, budget ignoto, allegati, conteggi, escaping,
Stop/Riprendi e funzioni commerciali esistenti su database isolati.

Replay senza chiamate esterne:

```bash
.venv/bin/python scripts/check_direct_demand.py
.venv/bin/python scripts/check_direct_demand.py --sample data/benchmarks50/direct-demand-development-replay.json --report docs/benchmark50-demand-development.json
```

`--live` esegue esplicitamente una nuova prova controllata: due query e fino a
sei domini. È un limite del benchmark, non della ricerca nell'app. Per usare
l'app: `.venv/bin/python app.py`, aprire `http://127.0.0.1:8765`, Avvia/Riprendi;
le collaborazioni compaiono in **Candidati promettenti**, categoria **Aziende**.

## Verifica successiva: ordine delle visite e nuovi contatti

Backup precedente a questo passaggio: `data/backups/20261014T164352300920Z/`.
La ricerca ora dà precedenza alle pagine aziendali di recruiting con richiesta
web e condizioni freelance. Le guide professionali riconoscibili sono escluse
prima della lettura. Questa priorità decide cosa leggere, non chi qualificare.
Le query partner includono le città delle regioni selezionate. Non ampliano
silenziosamente il territorio della campagna.

Un ramo con una collaborazione verificata e contattabile viene approfondito
anche se gli altri nove risultati sono scarti. Prima poteva essere abbandonato
perché non raggiungeva il 25% di risultati utili. Rimangono deduplicazione,
diversificazione e controlli commerciali; nessun punteggio è stato alzato.

Due nuove query Serper su Padova e Milano hanno prodotto un campione di sei
domini mai letti prima (`data/benchmarks50/city-demand-originals.json`). Nessuna
collaborazione promossa: Doozy cercava altri ruoli dipendenti, DVwebmarketing
raccoglieva candidature spontanee, NexWeb e NextAdv non avevano sede verificata,
PDR cercava dipendenti e DSI non dimostrava una richiesta freelance compatibile.
Questi esiti restano nel rapporto, senza trasformare candidature generiche in
incarichi aperti. Totale di questa serie di prove: dieci richieste Serper, non
il consumo totale storico dell'app. Il replay finale non consuma API.

Tre ulteriori originali già presenti nei risultati acquisiti sono stati letti
con tutte le regioni precedentemente ammesse. È un campione esplorativo distinto,
non un confronto della resa fra quattro regioni e tutta l'area consentita.
Le catture originali sono in `data/benchmarks50/allowed-regions-demand.json`.
Il replay applica a entrambe le versioni lo stesso filtro `website`:

| Azienda | Versione precedente | Versione aggiornata | Revisione delle prove |
|---|---|---|---|
| Adrias Online, Rimini | Da approfondire: interpretata come assunzione | Collaborazione promettente, categoria agenzie | Ruolo Frontend Developer / Freelance, HTML/CSS/WordPress, sede e `info@adriasonline.it` sul sito ufficiale |
| Business Click, Firenze | Da approfondire | Da approfondire | Richiesta senior PHP/Laravel: compatibilità con siti vetrina/frontend non dimostrata |
| Innform, Potenza | Scartata | Scartata | Territorio escluso |

La [richiesta Adrias](https://www.adriasonline.it/lavora-con-noi/) è stata letta
il 14 ottobre 2026. Data di pubblicazione, compenso e disponibilità effettiva
restano da confermare. È una ragione concreta per presentarsi, non una commessa
garantita né un progetto qualificato da 2.000 €. Il contatto del pilota non viene
inserito nella campagna 5, limitata al Veneto, e non è stato contattato.

Il confronto congelato registra **0 → 1 collaborazioni contattabili**, zero
progetti completi qualificati in entrambe le versioni. È la correzione di un
falso negativo su un originale nuovo. La correzione della categoria dell'agenzia
e del filtro PHP/Laravel è successiva alla lettura: questi aspetti costituiscono
regressioni di sviluppo, non una misura indipendente di generalizzazione.
Precision@10/20 rimane sconosciuta. Nessuna prova di aumento di risposte o vendite.

Riproduzione senza rete, Serper o modello:

```bash
.venv/bin/python scripts/check_direct_demand.py --sample data/benchmarks50/allowed-regions-demand.json --project website --report docs/benchmark50-allowed-regions.json
```

Corretto inoltre il contatto inesistente generato unendo l'etichetta «Email» al
valore di un link mailto. La scheda dà precedenza a recruiting/collaborazioni,
poi agli indirizzi generali; non riversa tutto l'elenco del personale nel contatto
consigliato. Le prove originali rimangono conservate.

Collaudo finale: **512 test superati** (`tests50-visit-priority.txt`) e controlli
browser desktop/mobile superati, nessun errore JavaScript
(`ui50-visit-priority.json`). Campagne e CRM reali non modificati dai test.
L'acquisizione ripetibile di un insieme consistente di nuovi contatti e le
conversioni commerciali restano da misurare; un solo nuovo caso non le dimostra.

## Verifica del worker e contatti utilizzabili

`scripts/check_collaboration_worker.py` riproduce un risultato Serper realmente
raccolto e le pagine originali Adrias attraverso il worker, la coda, il triage e
il database dell'app. Si tratta di un caso positivo selezionato esplicitamente:
non misura la precisione della discovery. Provider e lettura pagine sono
sostituiti dalle catture; la pianificazione di ulteriori query è disabilitata nel
solo replay. Nessuna modifica al motore o ai limiti reali della ricerca.

Esito (`worker50-collaboration.json`): dopo Stop nessuna promozione tardiva;
Riprendi completa il controllo senza ripetere la query. Una sola agenzia
promettente, email e fonte conservate anche riaprendo il database, zero qualificati,
zero verifiche pesanti o inferenze, zero chiamate API. Il database è temporaneo.

```bash
.venv/bin/python scripts/check_collaboration_worker.py
```

`contatti-pilota-2026-10-14.csv` raccoglie i tre casi documentati dei piloti:
Adviva (modulo pubblico), Jampaa e Adrias (email generali pubbliche). Include
fonte, citazione, data e limiti; distingue sviluppo e campione esplorativo. Non
sono nuovi risultati della campagna 5 e non sono stati contattati o importati
nel CRM. L'esportazione consente di esaminare le richieste senza aprire i JSON
tecnici. Non contiene un budget stimato o una disponibilità garantita.

## Chiusura delle incoerenze nelle metriche e negli esiti

La diagnostica per strategia/provider usa ora la stessa selezione di aziende
dell'elenco: non somma più vecchie pagine promettenti a una valutazione successiva
negativa o incompleta. Nella campagna 5: sette aziende identificate, una
promettente, quattro non verificabili e zero qualificate anche nella diagnostica.
I motivi di scarto degli URL rimangono statistiche di pagine, esplicitamente distinti.

Le priorità commerciali ora includono gli esiti manuali dei candidati promettenti,
prima ignorati se non avevano una valutazione qualificata. La stessa azienda in
più pagine o anche nel CRM conta una sola volta. «Interessante» non equivale a un
contatto. Servono due strategie con almeno dieci contatti ciascuna (o il minimo
configurato, se maggiore) prima di proporre una preferenza. Le soglie commerciali
non cambiano; è una priorità descrittiva, non un modello predittivo.

Backup dei moduli prima di queste correzioni:
`data/backups/diagnostics-20261014T170309Z/`. Suite completa: **517 test superati**
(`tests50-delivery.txt`), inclusi duplicati CRM/candidati, campioni insufficienti
e statistiche coerenti. Il replay del worker passa anche dopo l'integrazione.
Confronto integrale di undici tabelle commerciali con il backup completo delle
16:43 UTC: nessuna riga modificata, integrità SQLite `ok`
(`preservation50-delivery.json`). Le prove non avviano la campagna reale.

## Preferenza confermata: partner con disponibilità dichiarata

Il 14 ottobre l'utente ha confermato l'inclusione di agenzie disponibili a
collaborazioni freelance WordPress/frontend anche senza commessa aperta.
Ora sono mostrate come **Partner disponibile · da contattare**, nei promettenti.
La prova deve contenere nello stesso paragrafo originale competenza web,
disponibilità freelance e invito/candidatura; restano necessari identità,
territorio, canale pubblico e assenza di esclusioni. Budget e incarico restano
sconosciuti. Non vengono promosse ai 50 progetti qualificati.

Il replay delle sei aziende già salvate in `city-demand-originals.json` recupera
DVwebmarketing, Grantorto (PD), come disponibilità dichiarata. Gli altri cinque
esiti non vengono promossi. È una regressione sulla preferenza appena confermata,
non un campione indipendente o un miglioramento statistico della discovery.
Il sito dichiara candidature spontanee WordPress e collaborazioni freelance;
non viene presentato come un annuncio di commessa attiva.

```bash
.venv/bin/python scripts/check_direct_demand.py --sample data/benchmarks50/city-demand-originals.json --project website --report docs/benchmark50-standing-partners.json
```

Nessuna nuova ricerca Serper, inferenza o modifica dei dati commerciali nel replay.
**520 test superati** (`tests50-standing-partners.txt`), browser desktop/mobile
senza errori (`ui50-standing-partners.json`). Backup dei moduli:
`data/backups/standing-partners-20261014T210845Z/`. Le campagne restano avviate
dall'utente e gli scarti storici non vengono trasformati automaticamente.

## 15 ottobre: tutti i settori e pagine lavoro

Su istruzione dell'utente, la selezione esclusiva B2B/negozi/servizi è stata
rimossa dall'interfaccia. Il profilo `all` alterna i settori dei tre gruppi fin
dalle prime query e ne riconosce le attività nel controllo preliminare. Le nuove
campagne usano `all` anche se il client omette il parametro; i profili espliciti
storici restano compatibili per i replay.

La ricerca partner aggiunge query mirate a URL Jobs/Careers. Gli annunci LinkedIn
indicizzati restano inclusi, senza accesso automatico al social. Dalle homepage
aziendali si seguono i link espliciti interni a Jobs/Lavora con noi/Careers e poi
gli annunci web pertinenti. Si verifica richiesta, contratto freelance, identità,
geografia e contatto; un link Jobs non qualifica un'azienda da solo. Nessun URL
di pagina lavoro viene inventato e le protezioni HTTP rimangono attive.

Aggiornata la campagna 6 sospesa e dieci lavori non completati, senza modificare
risultati, valutazioni o storico. Regione Veneto e progetto website conservati.
Query già eseguite e decisioni completate non sono riscritte. Rapporto:
`migration50-all-segments.json`. Backup completo verificato:
`data/backups/20261014T223558649753Z/` (timestamp UTC).

**523 test superati** (`tests50-all-segments.txt`). I nuovi test verificano
rotazione precoce dei tre segmenti, migrazione dei soli lavori incompleti e
percorso homepage → Jobs → annuncio freelance, senza rete o modello. Collaudo
browser riuscito (`ui50-all-segments.json`): menu esclusivo assente e avvio con
`target=all`. Nessuna ricerca reale avviata durante lo sviluppo.
