# Collaudo CustomerSearch 3.0 — 12 ottobre 2026

## Esito concreto

App ricostruita e verificata in locale. Cinque motori implementati e provati con fonti reali; dashboard dark, dossier con provenienza, filtri, pipeline, bozze e statistiche funzionanti.

**Obiettivo sperimentale di 20 opportunità pertinenti: NON raggiunto.** Le 12 query Tavily del collaudo hanno restituito 160 candidati grezzi. Dopo visite, esclusioni, verifiche supplementari su fonti aziendali e deduplicazione, rimangono **7 schede riferite a 5 aziende distinte**. Tre richieste di collaborazione sono prive di una data di pubblicazione verificabile: non vanno considerate automaticamente recenti o ancora aperte. Le tre schede SVAI descrivono uno stesso soggetto attraverso C, D ed E, non tre possibili clienti.

Il consumo Tavily preesistente è stato conservato: da 17 a 29 richieste giornaliere su 30 disponibili. Nessun acquisto di crediti, nessuna nuova sottoscrizione, nessuna email inviata. La parte generativa AI non è attiva: nessun modello locale è installato/configurato; è disponibile un adapter Ollama con output vincolato. Dossier e bozze attuali usano regole locali dichiarate nell’interfaccia.

## Fonti ammesse dopo revisione

| Azienda | Riscontro | Fonte originale | Limite commerciale |
| --- | --- | --- | --- |
| SVAI | Annuncio del nuovo showroom di Cavaion Veronese, 1 ottobre 2026 | https://www.svai.it/inaugurato-il-nuovo-showroom-della-filiale-di-cavaion-veronese/ | L’apertura non prova che vogliano acquistare un nuovo sito. |
| Deluxe Dreaming Milano | Trasferimento di sede e showroom, 5 ottobre 2026 | https://deluxedreamingmilano.it/informazioni/nuovo-showroom | Il sito pubblica già il cambiamento; non viene dichiarata una sede “mancante”. |
| Alma Creative | Ricerca WordPress freelance con Gutenberg e almeno cinque anni di esperienza | https://alma-creative.it/jobs/ | Data assente; seniority e apertura attuale da confermare. A e B condividono la stessa scheda. |
| ReMedia | Ricerca sviluppatore full stack freelance | https://www.remediagroup.it/it/careers/ | Data assente; Vue.js/Laravel e altri requisiti non sono attestati dal profilo fornito. Priorità ridotta. |
| Understack | Candidature di professionisti autonomi/remoti, profili WordPress e frontend | https://understack.it/lavora-con-noi/ | Pagina permanente senza data; disponibilità di un progetto e budget da verificare. |

Gli URL supplementari scelti durante il collaudo sono etichettati **URL inserito manualmente**, non attribuiti falsamente al motore autonomo. Questo campione non dimostra ancora che il sistema sappia trovare sistematicamente opportunità migliori di una ricerca manuale.

## Test dei cinque motori

- **A — richieste:** due sessioni con Tavily e verifica diretta di pagine aziendali. Molti risultati erano fornitori che vendevano servizi, elenchi di annunci o pagine generiche. Esclusi. Richieste aziendali reali individuate, ma senza data certa.
- **B — agenzie:** ricerche autonome e pagine di candidatura. Duplicazioni A/B unite conservando entrambe le provenienze. Un programma partner che vende servizi non viene promosso automaticamente a richiesta di uno sviluppatore.
- **C — crescita:** ricerche Tavily, lettura dei dettagli collegati da sezioni news aziendali, annunci originali SVAI e Deluxe. Identità del committente, data e homepage verificati separatamente. Notizie riportate da testate rimangono escluse quando il legame con il sito aziendale non è risolto.
- **D — tecnico:** Lighthouse locale completato realmente su https://www.svai.it/, mobile e desktop, più controlli HTML e collegamenti. Nessun invio di form. I report originali sono scaricabili dalla scheda audit.
- **E — combinazione:** SVAI collega l’annuncio aziendale C con misurazioni D. La duplicazione della stessa richiesta in A e B non è considerata un secondo segnale indipendente. Ragione dell’interesse, ipotesi e verifiche mancanti sono esplicite.

Lighthouse SVAI, valori del collaudo:

| Dispositivo | Performance | Accessibilità | Best practices | SEO |
| --- | ---: | ---: | ---: | ---: |
| Mobile | 52 | 88 | 92 | 100 |
| Desktop | 65 | 87 | 92 | 92 |

Sono misure locali di laboratorio soggette a variazioni; non sono dati CrUX, una stima delle vendite perse o un voto GEO/AEO. I controlli SEO/GEO/AEO mostrano i segnali presenti nell’HTML senza inventare un punteggio universale.

Verificato anche il feed RSS originale `https://www.svai.it/feed/`, con 10 voci lette correttamente. È configurato come prima fonte RSS; non equivale a una copertura nazionale. Un errore del provider di ricerca non impedisce l’esecuzione dei feed indipendenti.

## Falsi positivi corretti

Durante il collaudo sono stati rilevati e scartati:

- Sortlist e ProntoPro: directory di fornitori, non committenti identificati.
- Jobeka e NETtoWORK: raccolte/intermediazione e condizioni di posizioni differenti mescolate.
- Presentazione di uno sviluppatore con “cerco di dare qualità al codice”: non una richiesta di personale.
- Articolo/intervista di Mailchimp: citazione informativa, non annuncio.
- Testi di collaborazione generici: la sottostringa “lanc” in “freelance” non è un annuncio di lancio.

Le schede scartate sono consultabili con il filtro Stato → Scartato; non compaiono nella shortlist né nel conteggio attivo. I due duplicati A/B sono conservati nell’archivio tecnico e le loro prove/interazioni sono unite alle schede superstiti. Nessun dato della versione precedente è stato cancellato.

## Verifica automatica e interfaccia

**51 test automatici superati.** Copertura: estrazione, articoli/annunci, ruoli misti, date future/visibili, identità, geografia, deduplica, combinazioni, limiti di priorità, concorrenza sul budget, cache, interruzione, RSS, SSRF, robots, migrazione, transazioni, statistiche, advisor indisponibile, bozze con fonte, protezioni HTTP, conferma manuale e indisponibilità Lighthouse.

Verifica browser con Chrome/Playwright:

- Panoramica, opportunità, pipeline, risultati, fonti/attività, archivio e impostazioni.
- Finestra di ricerca e dossier reali, tutti i tab.
- Otto punteggi Lighthouse e due link ai report originali nella scheda SVAI.
- Desktop 1440 px e telefono 390 px: nessun errore JavaScript, nessun overflow orizzontale della pagina o del dossier.
- Verificato anche il salvataggio delle impostazioni con gli stessi valori e il filtro delle schede scartate.
- Nessuna interazione commerciale reale registrata dai test. I test di bozze/composizione usano database temporanei.

## Limiti e prossimo esperimento

1. La qualità della ricerca autonoma resta il limite principale: molte query restituiscono contenuti commerciali o editoriali non pertinenti. La scoperta di dettagli interni ai siti migliora la raccolta ma non garantisce una domanda di acquisto.
2. I portali chiusi o soggetti ad autorizzazione API restano esclusi. Non sono state aggirate protezioni, autenticazioni o CAPTCHA.
3. Località non dichiarate rimangono sconosciute. Le preferenze geografiche non costituiscono una geolocalizzazione certificata dell’azienda.
4. Advisor generativo non attivato. L’adapter opzionale richiede un modello locale configurato; l’interfaccia espone il funzionamento a regole attuale.
5. L’efficacia commerciale su 30 giorni non è ancora misurabile: non ci sono nuovi contatti, risposte o incassi registrati. Le statistiche mostrano campione insufficiente e non suggeriscono un canale “vincente” senza dati.
6. Prima di un contatto, verificare attualità della richiesta, corrispondenza dei requisiti, referente e presupposto appropriato. Un sito lento o un nuovo showroom non dimostrano intenzione di acquisto.

Backup finale verificato della nuova versione: `data/backups/20261012T144237546491Z/`. Confrontate anche tutte le righe originali di leads (126) e opportunities (4): identiche al backup precedente alla ricostruzione.

## Aggiornamento del target richiesto dopo il collaudo

Escluse S.p.A. riconosciute nelle fonti societarie e reti/gruppi strutturati. Il filtro usa dichiarazioni del sito, non una valutazione estetica della sua grandezza. SVAI è stata rimossa dalla shortlist perché dichiara 19 sedi; le tre schede C/D/E restano negli scarti con motivazione e URL. Restano quattro schede attive su quattro aziende. Il feed SVAI è stato rimosso dalla configurazione e le query C sono state orientate ad attività più piccole e locali.

65 test automatici superati, inclusi casi spa/centro benessere, S.p.A. in footer e dati strutturati, clienti/fornitori citati, persistenza delle esclusioni, nessun rientro via E e nessun nuovo audit D per aziende escluse. Verificato nel browser che SVAI non compaia in shortlist e che le tre schede scartate mostrino motivo e fonte. Backup SQLite precedente alla modifica: `data/backups/target-filter-20261012T145528Z/`.
