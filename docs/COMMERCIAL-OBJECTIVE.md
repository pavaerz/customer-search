# Obiettivo commerciale — attuazione e verifica

Fonte: obiettivo utente del 20 ottobre 2026, allegato
`73214235-7c38-4721-83a8-23a46576abc7/pasted-text-1.txt`.
Questa matrice non sostituisce né restringe l'obiettivo. Lavoro in corso:
nessuna dichiarazione di efficacia commerciale prima di prove adeguate.

## Requisiti e prove necessarie

| Requisito | Implementazione / prova da completare |
|---|---|
| Aziende con bisogno digitale osservabile | Decisione con segnale, lacuna, perimetro e controprove; casi reali positivi e negativi |
| Agenzie con disponibilità freelance / partita IVA | Distinzione domanda/offerta; inviti permanenti ammessi senza inventare incarichi |
| Startup, incarichi e partnership distinti | Prodotto/bisogno, compenso sconosciuto o equity esplicita, fattibilità |
| LinkedIn e Instagram | Discovery distinta; autore, post, date e ruolo; originali accessibili e limiti documentati |
| Social non consultabili | Piste non verificate e conferme su fonti autorizzate, senza bypass |
| Link social inserito dall'utente | API e interfaccia, coda persistente, verifica entro budget, test HTTP/UX |
| Progetti completi e collaborazioni | Soglie interne 2.000/5.000 non attribuite al cliente; agenzie a giornata separate |
| Bisogni impliciti | Proposta specifica sostenuta da prove; piccoli difetti e funding non bastano |
| Esclusioni e geografia | PA, SpA/grandi gruppi, impiego esclusivo e manutenzione; Italia remota verificata |
| Quattro esiti comprensibili | Dichiarata, motivata, da approfondire, fonte non verificabile |
| Schede utili | Identità, ragione, proposta, fonti/date, contatto attribuito, obiezioni e incognite |
| Campagna 44: testo e citazioni | Replay dei payload reali, prove leggibili, identificativi chiusi e recupero limitato |
| Campagna 44: discovery e piani | Query coerenti e recuperabili; capacità per tutti senza aumento dei massimi |
| Identità | Niente titoli SEO, editori o luoghi spacciati per committenti |
| Misura qualità | Campione annotato reale, positivi/negativi/ambigui, falsi positivi e opportunità perse |
| Preservazione | Impronte DB/CRM prima/dopo, niente migrazioni sul DB operativo durante sviluppo |
| Consenso spese e contatti | Solo test offline; nessuna nuova campagna, inferenza pagata o invio |

## Ordine di lavoro

1. Lettura delle prove: contesto in token stimati localmente, selezione citazioni
   vincolata e recupero tecnico circoscritto.
2. Decisione commerciale: direzione della domanda, identità, bisogni impliciti,
   esclusioni, attualità e rappresentazione distinta degli errori.
3. Discovery: qualità URL, ipotesi, pianificazione/recupero, memoria e contatori.
4. Social: integrazioni realmente disponibili, fonti alternative e link manuali.
5. Dossier/interfaccia, test integrati offline, regressioni e rapporto con limiti.

## Vincoli di validazione

I provider sintetici misurano contratti e pipeline, non accuratezza del modello.
Le risposte reali congelate possono dimostrare regressioni e falsi positivi;
non dimostrano che un prompt nuovo produrrà risposte migliori.
Un futuro confronto a pagamento richiede risultati offline e limiti presentati
all'utente prima dell'autorizzazione. Nessun avvio implicito.

Backup del codice verificato e baseline del DB in
`implementation-report/commercial-objective/`. Non modificare i report storici.

## Avanzamento verificato — 20 ottobre 2026

- Tokenizer locale con vocabolario incluso e hash verificato; nessun download
  durante l'inferenza. Stima comprensiva dello schema dinamico e margine,
  non conteggio server garantito.
- I sei originali congelati della Campagna 44 conservano i passaggi commerciali
  verificati dai test entro 8.192 token stimati, senza aumentare il limite.
- Riferimenti selezionabili alle prove, recupero massimo singolo per riferimenti
  invalidi e nomi non sostenuti; budget del candidato, flusso e campagna invariati.
- Con 30 chiamate sono verificati offline cinque avvii e cinque recuperi di
  pianificazione, seguiti da venti verifiche originali.
- Contratto commerciale esplicito: direzione della richiesta, ambito, soluzione
  esistente, interpretazione e obiezioni con riferimenti alle prove. Le proposte
  proattive richiedono segnale, lacuna, perimetro e soluzione esaminata.
  Sono controlli di coerenza, non un secondo classificatore né una prova
  dell'accuratezza delle nuove risposte AI.
- Recapiti di terzi e privacy non diventano canali del committente. Un indirizzo
  esterno può essere usato se il sito ufficiale lo indica per le candidature.
  Le fonti editoriali richiedono ancora ulteriore attribuzione. Per un originale
  social isolato, il collegamento autore–azienda richiede ora un riferimento
  reciproco dal sito ufficiale; una semplice citazione non basta.
- Il dossier distingue l'interpretazione AI e le obiezioni dalle prove originali.
- Le operazioni AI-first aggiornano nuovi candidati in coda, duplicati, PDF
  esclusi, accessi non consentiti ed esito della valutazione.
- Pianificazione social: priorità alla piattaforma non ancora ricercata tra
  LinkedIn e Instagram. Le proposte salvate solo per LinkedIn non impediscono
  più un piano Instagram. Il test integrato usa due chiamate simulate, senza
  query inventate dall'orchestratore né aumento delle quote.
- Link manuali LinkedIn/Instagram nel modulo, anteprima senza chiamate e coda
  persistente deduplicata. Il post bloccato resta non verificato; una ricerca
  circoscritta cerca un riferimento al post, entro i massimi esistenti.
- Originali social: testo e autore isolati tramite metadati e corrispondenza
  letterale nel documento; commenti, date e link estranei non entrano nelle
  prove. JobPosting esterni devono riferirsi all'URL specifico. Mancanza di
  delimitazione = fonte non verificabile, senza inferenza commerciale.
- Un riscontro reciproco sul sito ufficiale può verificare l'attribuzione del
  post. La geografia viene controllata sulla richiesta, non sulla sede del
  datore; date originali conservate. I recapiti restano legati al committente.
- Browser offline a 1440 e 390 px: modulo, selezione Social, invalidazione del
  riepilogo, cambio vista e refresh verificati senza avvii o richieste esterne
  (`social-manual-ux.json`). Nessun errore JavaScript né overflow osservato.

Prove: `tests/test_commercial_objective.py`, `tests/test_ai_first.py`,
`tests/test_commercial_validation.py` e log in
`implementation-report/commercial-objective/`. Il primo giro completo nel
sandbox è fallito per permessi su server/browser locali: non va conteggiato
come suite superata. Il successivo giro con i permessi locali ha superato
1.973 test (`tests-full-permitted.txt`). Le ultime modifiche a scadenze,
etichette economiche e copertura social sono verificate anche nel successivo
gruppo mirato di 152 test (`tests-assessment-final.txt`).
L'incremento social è coperto da 1.999 test completi in 380,544 secondi
(`tests-full-social.txt`) e 8 test finali dedicati, compreso il dossier.
La verifica read-only ha confermato le stesse impronte di tutte le 66 tabelle
operative rispetto alla baseline (`database-preservation-social.json`).

**Ancora da completare:** misura dell'efficacia delle query, audit delle
identità non derivate dai titoli e casi d'autore personale o originali senza metadati sufficienti,
esiti e schede completi, corpus reale allargato con errori/mancate opportunità
misurati, attribuzione dei canali direttamente nelle unità social o annunci multipli,
preservazione finale e rapporto conclusivo. Nessuna campagna avviata.

## Canali pubblici oltre alle email

Il reader AI-first offre ora al modello controlli osservati sulle pagine del
titolare verificato: telefono, modulo di contatto/candidatura e collegamento
esplicito per candidarsi, anche verso un ATS esterno. Il modello deve citarne
la prova originale e ritenerla pertinente; l'esistenza del controllo da sola
non produce una qualifica commerciale.

Il modulo conserva come canale la pagina pubblica, mai l'endpoint di invio.
Nessun valore di input, token nascosto o invio viene utilizzato. Campi di
newsletter, login, commenti e reclami non diventano contatti. Per evitare
attribuzioni trasversali questo estrattore opera sulle unità di pagina del
titolare, non su footer social, schede multi-azienda o elenchi di annunci.
I contatti email già attribuiti mantengono il percorso esistente.

Prove: `tests/test_ai_first_response_channels.py`, gruppo di regressione
`implementation-report/commercial-objective/tests-response-channels.txt`,
replay di sei originali C44 in `response-channels-replay.json`.
I sei controlli del replay non sono sei opportunità: due sono collegamenti
a iscrizioni formative. Nessuna nuova valutazione AI o misura di conversione.

## Incremento discovery e criteri del titolare

- Prima dell'invio e al riuso dei piani, ogni ramo OR deve esprimere una
  richiesta/invito, un evento aziendale specifico o un'indagine proattiva con
  settore e territorio. Sono ammesse candidature spontanee e collaborazioni;
  non sono trasformate in incarichi disponibili. Un rifiuto restituisce al
  pianificatore il motivo e una correzione, entro la quota già configurata.
- Replay delle otto query realmente eseguite in C44: due tornano al
  pianificatore, sei restano ammesse. Venti delle 34 righe discovery storiche
  provenivano dalle due query generiche. Questo non dimostra che tutti quei
  risultati fossero inutili o che nuove ricerche avrebbero prodotto clienti.
- Archivi, indici editoriali riconosciuti e profili social non vengono valutati
  come una singola azienda/richiesta. Lo scarto riguarda l'URL, non un'azienda
  REJECTED/UNVERIFIABLE. Gli articoli specifici e i siti aziendali restano ammessi.
- Un indizio indicizzato di invito tecnico può attivare una sola ricerca
  circoscritta del riferimento social. Resta non verificato; niente inferenza
  sullo snippet, login o aggiramenti. Consigli generici e promozione di servizi
  non giustificano questo approfondimento.
- Le esclusioni per pubblica amministrazione, forma societaria e gruppo
  multinazionale richiedono identità verificata e prove del titolare. Citazioni
  di clienti/fornitori/investitori e la parola SPA nel wellness non bastano.
  Motivi e fonti sono conservati nel dossier, senza stimare budget.
- Corretto un errore della memoria: le ricevute storiche con `url` ma senza
  `domain` potevano causare KeyError alla pianificazione successiva. Ora vengono
  lette compatibilmente, senza modificare le righe storiche.

Questi controlli migliorano l'ammissione delle ricerche; non certificano
l'intenzione commerciale dei risultati. Le espressioni non riconosciute
possono richiedere una riformulazione: non esiste una blacklist permanente.
Resta necessaria la misura su originali reali, soprattutto social, oltre ai
test della pipeline con provider sintetici.

Verifica di questo incremento: 2.016 test completi e 13 controlli finali sui
criteri del titolare/dossier; 66 tabelle operative ancora identiche alla
baseline in lettura `mode=ro`. Log, replay delle query e confronto d'integrità
in `implementation-report/commercial-objective/`.

## Riferimenti tecnici

Aggiornamento del 20 ottobre: il confronto autorizzato sui 13 originali
congelati ha prodotto 12 decisioni valide con Sol contro 6 con Mini,
recuperando entrambi gli inviti pertinenti. Costo stimato Sol 0,222554 USD,
14 chiamate. Report completo e limiti in
`implementation-report/commercial-objective/VALIDATION-AI-SOL-01-REPORT.md`.
Configurazione dell'app invariata; nessuna nuova campagna.

Le successive correzioni offline conservano gli indirizzi `mailto:` del
titolare associati ai controlli di candidatura e confrontano gli alias
espliciti LinkedIn/Instagram senza confondere post, profili o committenti.
Caso reale: “Invia il tuo CV” di Kondividi. Nessun destinatario o contenuto
di messaggio generato; prova da selezionare esplicitamente dal modello.
Dettagli, 49 test mirati e 180 d'integrazione (gruppi sovrapponibili) in
`implementation-report/commercial-objective/CONTACT-SOCIAL-FOLLOWUP.md`.
La lettura reale di originali social e l'efficacia su nuove fonti restano
da dimostrare.

- [Conteggio token OpenAI](https://developers.openai.com/api/docs/guides/token-counting):
  un tokenizer locale stima il testo, non il conteggio server esatto con framing.
  Nessuna chiamata all'endpoint di conteggio durante lo sviluppo offline.
- [Output strutturati](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat):
  usare valori enumerati per limitare i riferimenti alle prove effettivamente fornite;
  rimane obbligatoria la validazione locale di contenuto, soggetto e date.

## Verifiche successive — fonti, recupero e nomi del titolare

L'autorizzazione successiva dell'utente («Autorizzo tutte le prove che ti servono»)
consente prove ulteriori entro limiti annunciati e controllati; non autorizza invii,
acquisti automatici o modifiche indiscriminate allo storico. I vincoli iniziali sopra
sono la fotografia della preparazione, non una revoca di quel consenso successivo.

Report recenti: `analysis-report/CUSTOMERSEARCH-SOURCE-QUALITY-REPORT.md` e
`analysis-report/CUSTOMERSEARCH-SOCIAL-RECOVERY-REPORT.md`, con metriche affiancate.
Sono verificati il corpo editoriale reale, l'esclusione preventiva di otto raccolte,
il blocco degli approfondimenti su fornitori senza domanda/lacuna e il recupero
prudente del nome legale nel footer con partita IVA coincidente. Il filtro social
non interpreta più la crescita commerciale come sviluppo web.

Startup Bakery è stata verificata su homepage, careers e portale ufficialmente
collegato: due stage commerciali e candidatura generica, nessuna richiesta frontend
attuale confermata. Questo è un controllo negativo utile, non una nuova opportunità.
Le 533 regressioni finali e la conservazione di DB/CRM non dimostrano il raggiungimento
dell'intero obiettivo. Restano necessarie richieste pertinenti nuove e verificabili,
con completamento dei dossier e misura degli errori; non si abbassano i criteri
per produrre risultati.
