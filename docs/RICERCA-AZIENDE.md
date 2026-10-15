# Ricerca a partire dalle imprese — 14 ottobre 2026

## Decisione commerciale

Preferenze indicate da Diego: produttori e piccole imprese B2B, siti aziendali completi da 2.000 €. Primo territorio: Veneto. Altre categorie e territori ammessi restano selezionabili. Le soglie sono interne, mai budget attribuiti all'impresa.

Il [portfolio pubblico](https://designerdimontagna.it/it/progetti), consultato durante il lavoro, presenta Presotto Ennio (impiantistica, rinnovabili, contract), MNTP Engineering (portfolio di ingegneria), Atlantic Partners (sito corporate), oltre a transfer ed e-commerce. Questo orienta i settori iniziali, senza attribuire bisogni o risultati economici analoghi ai potenziali clienti.

## Problema e cambiamento

Le precedenti query cercavano concetti digitali e notizie: intercettavano anche chi vende servizi, guide e rapporti di settore. Inoltre una homepage di una vera impresa senza parole di cambiamento veniva esclusa prima di investigarla.

Ora il ramo **Aziende da investigare** cerca attività e territorio, ad esempio `impiantistica industriale Veneto azienda contatti`. Espande progressivamente settori e città; cerca anche elenchi pubblici. I termini delle query e i titoli servono ad acquisire e ordinare pagine, mai a provare un bisogno.

Il percorso è:

1. Leggere pagina, homepage e fino a due pagine di identità/contatti, con le protezioni HTTP esistenti.
2. Verificare identità, sede, attività e compatibilità. Escludere fornitori digitali senza progetti, S.p.A., aree escluse e soggetti già soppressi. Le consulenze tecniche non sono escluse soltanto perché offrono anche supporto finanziario.
3. Registrare **impresa identificata, bisogno da verificare**, senza assegnare una qualifica o un budget.
4. Seguire fino a otto pagine pertinenti del sito e tre query circoscritte al dominio: novità, settori/progetti e soluzioni esistenti. Si conservano i documenti originali, l'impresa e il percorso di acquisizione.
5. Approfondire i segnali effettivi con il motore di verifica esistente. Restano obbligatori bisogno specifico, progetto completo, controprove, fattibilità, contatto e prove sufficienti.

I limiti per singola impresa evitano esplorazioni ricorsive incontrollate; non impongono un numero complessivo di ricerche alla campagna. Le query si deduplicano nella memoria persistente. Riprendi conserva lavori e dati; aggiunge il nuovo ramo anche alle campagne precedenti, senza cancellarne le ricerche.

Aggiornamento successivo alla segnalazione dei risultati estranei: i clienti diretti usano solo discovery di imprese ed elenchi pertinenti, con indagini circoscritte a ciascuna impresa. I feed generalisti non alimentano più le campagne. Ogni impresa compatibile riceve una verifica commerciale anche senza parole chiave di cambiamento. [Dettagli e prova reale](PROSPEZIONE-DIRETTA.md).

Gli elenchi non diventano clienti: collegamenti esterni nominativi, profili pubblici e nomi strutturati riscontrati nel testo possono portare a ulteriori identificazioni. Si controllano robots e condizioni collegate; nessun accesso riservato, acquisto di liste o invio. Un sito trovato per nome deve corrispondere al soggetto citato; i controlli approfonditi mantengono anche le verifiche territoriali.

Le verifiche con identità/sede/contatti riscontrati precedono gli editori. È una priorità operativa separata dal punteggio commerciale. Anche i nuovi confronti Serper applicano tale ordinamento (protocollo 4); i report storici non vengono riscritti. Serper resta disattivato nelle campagne ordinarie.

## Correzioni collaterali necessarie

- Risoluzione degli articoli senza imporre la lettura della homepage dell'editore, che poteva superare il limite tecnico.
- Deduplicazione delle pagine dopo redirect.
- Nome legale letterale utilizzabile quando manca il titolo della pagina.
- Indirizzo già completo non concatenato alle successive voci di navigazione: la provincia finale `PD` resta leggibile.
- `gara` non corrisponde più alla sottostringa di `garantisce` o `garanzia`. Una generica collaborazione con i clienti non giustifica l'analisi commerciale di una pagina aziendale.
- `project=none` non viene descritto come una categoria di progetto incompatibile: rimane assenza di progetto documentato.
- Dopo il cambio di giorno, i test hanno evidenziato un difetto preesistente nei bandi: una lettura UTC della sera risultava vecchia dopo mezzanotte italiana. Il confronto ora usa il giorno Europe/Rome.

## Verifica e limiti

Backup verificato prima delle modifiche: `data/backups/20261013T214422932276Z/` (archivio, hash e integrità SQLite). Nessuna tabella commerciale cancellata e nessuna migrazione distruttiva.

Pilota reale: `scripts/pilot_company_research.py`, database isolato copiato dall'originale per mantenere preferenze ed esclusioni. SearXNG gratuito, tre query iniziali e due query su aziende identificate; nessuna richiesta Serper. Campione alternato tra le query, deduplicato per dominio.

- 12 domini esaminati.
- 3 imprese B2B identificate nella prima esecuzione.
- Un approfondimento completo tentato: nessun bisogno digitale sufficiente; citazioni invalide del modello respinte. Zero qualificati.
- Il ricontrollo delle stesse pagine conservate riconosce 5 imprese dopo le correzioni di nome e indirizzo. **Non è un campione indipendente**, né una misura di conversione.
- Le pagine di servizio che erano passate erroneamente per `garanzia` o collaborazione generica restano ora da approfondire, senza spendere un'analisi completa su quei soli riscontri.

Report originali: [pilota](company-first-pilot.json), [ricontrollo offline](company-first-recheck.json). Non vengono riscritti i risultati della prima esecuzione per farli apparire migliori. Il campione contiene ancora rumore e casi non identificabili. Il modello locale può produrre citazioni invalide: questi casi non vengono qualificati.

La prova dimostra che il nuovo percorso può identificare imprese reali senza un annuncio web esplicito. Non dimostra ancora che produca una shortlist commercialmente efficace. Cinque imprese da investigare non sono cinque clienti né cinque opportunità qualificate.

Secondo campione, distinto dai domini del primo: tre query su Padova, nove nuovi domini esaminati, quattro imprese identificate, quattro casi non verificabili e un'esclusione territoriale. Le pagine di approfondimento disponibili non hanno superato la selezione preliminare; **nessuna qualifica finale eseguita**, quindi il campo `qualified` è `null`, non una misura di precisione. [Report originale Padova](company-first-pilot-padova.json). È emerso anche un nome estratto come URL dai metadati: corretto con preferenza per un nome societario letterale nel titolo. Il report conserva il difetto originale. Una parola incidentale nel footer non trasforma più un'impresa già verificata in un editore.

**293 test automatici superati**, controlli browser senza errori JavaScript. [Rapporto di verifica](company-first-verification.json). I test coprono il percorso senza annuncio esplicito, identità mancanti, corrispondenza con il soggetto della fonte, fornitori, esclusioni, elenchi e restrizioni, deduplicazione, Stop e conteggio distinto. I controlli browser a 390/1440 px verificano anche preferenze B2B/sito/clienti diretti, filtri, dossier, feedback, contatto verde, eliminazione e bacheca. [Conservazione dei dati](company-first-data-preservation.json): tabelle commerciali confrontate riga per riga col backup; SQLite integro, richieste Serper ancora 18.

## Uso

Avvio invariato: `.venv/bin/python app.py`, poi `http://127.0.0.1:8765`.

In **Preferenze e attività** sono preselezionati B2B, clienti diretti e sito aziendale; **Avvia ricerca** crea una campagna con queste preferenze. **Riprendi** mantiene quelle della campagna precedente. Il contatore delle imprese identificate è distinto dai qualificati X/50; le prime sono consultabili in **Tutta la discovery**.

La ricerca ordinaria continua a usare SearXNG. Nessun nuovo costo, email o contatto commerciale avviato da questo intervento.
