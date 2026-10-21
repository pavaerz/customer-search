# Accesso social — verifica delle integrazioni

Valutazione tecnica iniziata il 20 ottobre 2026. Non sono state usate credenziali
social, interrogate API di account, effettuate campagne o rimosse restrizioni.

## LinkedIn

La [documentazione ufficiale Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2026-07)
consultata distingue lettura per organizzazioni con ruoli autorizzati e lettura
dei post dei membri con permessi riservati agli utenti approvati. Non dimostra
la disponibilità di una ricerca generale su qualunque post pubblico.

Conseguenza progettuale: un login personale non è una soluzione sufficiente per
leggere automaticamente tutte le richieste. Non implementare un login simulato
o trasferimento di cookie. Conservare gli indizi indicizzati e cercare eventuali
conferme ufficiali accessibili, mantenendo separata la verifica del post.
Un futuro connettore deve dimostrare permessi e ambito prima dell'abilitazione.

## Instagram

La [raccolta Meta Instagram API su Postman](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-af579d08-121e-4897-8f45-5fd41ace49df)
indica nell'estratto indicizzato che la variante con Facebook Login non accede
agli account consumer. La pagina completa non è stata resa leggibile dallo
strumento di consultazione: questo riscontro parziale non certifica permessi,
campi o condizioni del possibile connettore.

La documentazione primaria di
[Business Discovery](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/business-discovery)
e [oEmbed](https://developers.facebook.com/docs/instagram-platform/oembed/)
ha restituito HTTP 429 durante la verifica. Nessuna affermazione sulle attuali
condizioni di oEmbed è stata presa da mirror o blog. In particolare non è
dimostrato che un endpoint per incorporare post autorizzi l'analisi commerciale
automatica del testo.

**Stato:** integrazione API Instagram non abilitata né dichiarata funzionante.
Resta da verificare la documentazione primaria completa, quando accessibile,
prima di scegliere un connettore. Nessun aggiramento dei blocchi.

## Percorso applicativo verificato offline

1. URL inseriti dall'utente e risultati indicizzati come piste con provenienza.
2. Fonti originali leggibili solo tramite modalità autorizzate.
3. Se non leggibili, conferma sul sito ufficiale entro i budget configurati.
4. Testo, autore, date e contatto attribuiti alla stessa richiesta.
5. Conferma su altra fonte distinta dall'affermazione «post verificato».
6. Fonte non verificabile senza giudizio commerciale positivo o negativo.

Il modulo accetta fino a 20 URL di post/reel/annunci LinkedIn e Instagram;
profili e URL non supportati vengono rifiutati. L'anteprima non esegue ricerche.
La coda conserva i link nella nuova campagna e non li duplica in ripresa.
Per i link manuali non consultabili, la ricerca alternativa usa il riferimento
esatto al post (o l'activity ID presente nell'URL lungo), senza inventare
argomenti. Un risultato alternativo deve contenere un collegamento al post:
la sola menzione o lo snippet non dimostrano la correlazione.

Un originale pubblico ottenuto tramite il client autorizzato deve permettere
di isolare testo e autore. Il percorso AI-first usa un solo SocialMediaPosting
con testo individuabile letteralmente nella pagina, oppure un JobPosting
riferito esattamente a quell'URL. Non usa commenti, date o link della piattaforma.
Prima di attribuire la richiesta all'impresa richiede anche un riscontro sul
sito ufficiale: profilo autore collegato per i post aziendali, annuncio specifico
per un JobPosting. Geografia e date restano quelle della richiesta originale.

I test usano risposte HTTP e AI di collaudo, esplicitamente sintetiche. Provano
i confini delle evidenze e il percorso applicativo, **non** la disponibilità
di lettura live di LinkedIn/Instagram. Nessuna restrizione è stata rimossa.

Anche un post indicizzato non manuale può ora generare una ricerca del
riferimento esatto, se lo snippet contiene un invito tecnico da verificare.
È un criterio per ammettere un approfondimento, mai una qualifica. Nessuna
inferenza sullo snippet; un solo lavoro deduplicato, budget invariati. Profili
social e contenuti che non esprimono un invito non attivano questo recupero.

Per un autore personale diverso dall'azienda, il reader conserva ora separati
autore, profilo e soggetto della richiesta. L'azienda deve essere nominata nel
testo isolato e il suo sito verificato deve collegare quel post specifico.
Un link al profilo della persona, il suo `worksFor` o un nome nei commenti
non bastano. Il dossier non inventa un ruolo lavorativo: dichiara soltanto
il riferimento ufficiale al post, lasciando sconosciuto il rapporto professionale.
Collegamenti nei commenti, testimonianze o contenuti nascosti sono esclusi.
Test del ciclo completo con provider sintetici: `tests/test_objective_person_social.py`.

Restano da completare: corpus social reale autorizzato, misura dell'attribuzione
persona-azienda su casi reali e gestione di originali leggibili senza metadati
sufficienti. Questi ultimi restano
non verificabili; non vanno conteggiati come scarti commerciali.

## Seconda verifica di disponibilità

Consultazione del 20 ottobre 2026, senza credenziali o installazioni:

- I due endpoint ufficiali Meta sopra hanno restituito nuovamente HTTP 429
  allo strumento di consultazione. Nessun tentativo di aggiramento o deduzione
  dei permessi da fonti non ufficiali.
- Il catalogo plugin interrogato per «LinkedIn Instagram» ha restituito Canva,
  Clay, Windsor.ai e Metricool, nessuno installato. Le descrizioni di Canva
  riguardano creazione grafica; Windsor.ai e Metricool riguardano account/brand
  collegati, analytics e pubblicazione. Clay indica ricerca di prospect, senza
  documentare nel risultato la lettura autorizzata degli originali social.
- Nessuna delle capacità descritte dimostra una ricerca generale e lettura dei
  post altrui, né fornisce automaticamente un connettore Python per l'app
  locale. Non vengono proposti come soluzione già funzionante o attivati.
  Il risultato non è un elenco esaustivo: possono esistere altri strumenti nel
  [catalogo plugin](https://chatgpt.com/plugins).

Conclusione verificabile: non è stato individuato in questa consultazione un
connettore documentato pronto a colmare il limite sugli originali social.
La ricerca pubblica e le conferme sul sito del committente rimangono distinte
da un'eventuale integrazione futura, da valutare con permessi e condizioni.
