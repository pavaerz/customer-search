"""Build Phase 5.0 deliverables from saved offline artifacts; no DB or network."""
import gzip,json,re
from pathlib import Path
from collections import Counter,defaultdict
from urllib.parse import urlsplit
from sales.commercial.catalog import ENGINES,PROFILES
from sales.commercial.search_strategies import plans,catalog
from sales.commercial.strategies import plans as old_plans
from sales.commercial.planner import query_key
ROOT=Path(__file__).resolve().parents[1]
def read(n):return json.loads((ROOT/'implementation-report'/('phase50-'+n+'.json')).read_text())
def ratio(n,d):return {'numerator':n,'denominator':d,'value':n/d if d else None}
def table(headers,rows):
 def cell(x):return str(x).replace('|','/').replace('\n',' ')
 return '| '+' | '.join(headers)+' |\n|'+'|'.join('---' for _ in headers)+'|\n'+'\n'.join('| '+' | '.join(cell(x) for x in row)+' |' for row in rows)
def tests(path):
 text=Path(path).read_text();m=re.search(r'Ran (\d+) tests in ([\d.]+)s',text)
 if not m or not text.rstrip().endswith('OK'):raise ValueError('Test results not complete/passing: '+path)
 return {'tests':int(m[1]),'seconds':float(m[2]),'failed':0,'result':'OK','log':str(Path(path).relative_to(ROOT))}
def main():
 h,p,b,i,ux=(read(k) for k in ('history','plan','benchmark','integrity','ux'))
 with gzip.open(ROOT/'tests/fixtures/commercial50/campaign29.json.gz','rt') as f:s=json.load(f)
 regions=list(dict.fromkeys(q['region'] for q in p['queries'] if q['engine']=='WEBSITE_REBUILD'))
 old=[q for e in ENGINES for q in old_plans(e,regions)];new=[q for e in ENGINES for q in plans(e,regions)]
 oldunique=len({query_key(q['query']) for q in old});newunique=len({query_key(q['query']) for q in new})
 done=[q for q in h['query_history'] if q['state']=='done' and q['engine'] in ENGINES and q['payload'].get('query')]
 keys=[(q['engine'],query_key(q['payload']['query']),q['payload'].get('discovery_period',''),q['payload'].get('page',1)) for q in done]
 qstats=defaultdict(Counter)
 for t in s['traces']:qstats[t['query']][t['decision']]+=1
 sources=p['history']['sources'];top=sorted(sources.items(),key=lambda kv:kv[1]['appearances'],reverse=True)[:12]
 full=tests(ROOT/'implementation-report/phase50-full-final.log');targeted=tests(ROOT/'implementation-report/phase50-final-targeted.log')
 metrics={'phase':'5.0','scope':'OFFLINE_NO_CAMPAIGN_30','as_of':p['generated_at'],
  'history':{'campaigns_present':[c['id'] for c in h['campaigns']],'missing_campaigns':[], 'commercial_campaigns':[c['id'] for c in h['campaigns'] if c['revisions']], 'commercial_revision_observations':sum(c['revisions'] for c in h['campaigns']), 'campaigns':h['campaigns'],'feedback_counts':h['feedback_counts']},
  'strategies_available':len(catalog()),'strategies_tested':sorted(q['id'] for q in catalog()),
  'queries':{'regions':regions,'baseline_generated':len(old),'baseline_distinct':oldunique,'baseline_duplicates':len(old)-oldunique,'new_generated':len(new),'new_distinct':newunique,'new_duplicates':len(new)-newunique,'planned_deep':p['planned_queries'],'executed_phase50':0,'baseline_duplicate_rate':ratio(len(old)-oldunique,len(old)),'new_duplicate_rate':ratio(len(new)-newunique,len(new))},
  'geographic_coverage':{'tiers':p['geography_tiers'],'outbound_regions':regions,'remote_eligibility':'Requires original request evidence allowing Italy; EMEA/remote alone insufficient'},'languages':p['languages'],
  'precision':b['new']['precision'],'recall':b['new']['recall'],'false_positives':b['new']['false_positives'],'baseline':b['baseline'],'new_pipeline':b['new'],'benchmark_provenance':b['by_provenance'],'fixture_sha256':b['fixture_sha256'],
  'historical_duplicate_query_observations':{'scope':'Completed four-engine search/resolve rows; same engine/query/period/page across campaigns. Repeats are not automatically waste.', 'observations':len(keys),'distinct':len(set(keys)),'repeated':len(keys)-len(set(keys)),'rate':ratio(len(keys)-len(set(keys)),len(keys))},
  'source_quality':{'scope':'Historical observations, not labelled source precision or domain reputation','sources':sources},
  'strategy_observations':p['history']['strategies'],'campaign29_query_decisions':{q:dict(v) for q,v in qstats.items()},
  'benchmark_details':b,'cost_efficiency':b['cost_efficiency'],
  'tests':{'full_suite':full,'final_changed_modules':targeted,'counts_overlap_do_not_sum':True,'browser':ux},
  'regressions':b['regressions'],'integrity':i,'profiles_unchanged':PROFILES==h['profiles'],
  'costs':{'development_serper_calls':0,'development_ai_calls':0,'development_scraping':0,'campaign30_proposed':p['maximums'],'authorization_required':True},
  'limits':['Small curated benchmark: 8 historical + 24 synthetic; no independent holdout','Positive admission is not a verified opportunity','No live precision, recall, yield per credit or conversion measured','Historical ledger fields not present in older versions cannot reconstruct unknown calls','Browser incompleteness and ambiguous company identity remain explicit','Standing metadata memory uses bounded TTL; new content without changed snippets may be revisited only after expiry']}
 (ROOT/'PHASE-5.0-METRICS.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
 rows=[(x['id'],x['engine'],x['objective'],x['time_policy']) for x in catalog()]
 campaigntable=table(['Campagna','Schede/revisioni','VERIFIED','POTENTIAL','NEEDS_REVIEW','REJECTED','UNVERIFIABLE'],[(c['id'],c['revisions'],*(c['revision_states'].get(k,0) for k in ('VERIFIED','POTENTIAL','NEEDS_REVIEW','REJECTED','UNVERIFIABLE'))) for c in h['campaigns']])
 source_table=table(['Dominio','Tracce attribuite','Ammesse','Escluse','Richieste verificate osservate'],[(host,v['appearances'],v['admitted'],v['excluded'],v.get('verified_request_observations','non misurato')) for host,v in top])
 query_table=table(['Query Campagna 29 (discovery + risoluzioni)','Tracce','Ammesse','Escluse'],[(q,sum(v.values()),v['admit'],v['exclude']) for q,v in sorted(qstats.items(),key=lambda kv:-kv[1]['exclude'])])
 files=i['changed_baseline_files']+i['new_source_files']
 report=f'''# Customer Search — Fase 5.0: Search Intelligence Rebuild

## 1. Executive summary

Implementato un livello di strategie commerciali nel coordinatore esistente: 15 strategie, query italiane e inglesi, ricerca nazionale e remota, memoria delle richieste, priorità adattive limitate e anteprima locale dei costi. Non è stata eseguita la Campagna 30.

Il benchmark di ammissione sugli stessi 32 casi congelati passa da 10 a 0 falsi positivi, conservando 9/9 positivi e tutti gli 8 ambigui. È un miglioramento dimostrato **su questo campione selezionato**, composto da 8 casi storici e 24 sintetici, non una misura del mercato. L'unico positivo storico è una collaborazione da approfondire, non una nuova commessa verificata.

Suite completa: **{full['tests']} test superati**; controllo finale moduli modificati: **{targeted['tests']} superati**, conteggi sovrapposti. Desktop e telefono verificati. Database: 58 tabelle identiche al baseline, integrità SQLite ok. Nessuna chiamata Serper/OpenAI, scraping, email, commit o push.

## 2. Diagnosi della discovery

Il problema non era l'assenza dimostrata di clienti: il Pilot esplorava poche query, spesso regionalizzate, e approfondiva indizi non pertinenti. Nella Campagna 29: 11 query discovery, 128 tracce, 26 schede, 6 nuove nello storico; 0 VERIFIED/POTENTIAL, 2 NEEDS_REVIEW, 20 UNVERIFIABLE, 4 REJECTED. Le risoluzioni di dominio aggiungono query alle 11 di discovery: le righe seguenti non sono tutte query iniziali.

{query_table}

L'ammissione delle query agenzie riguardava Internetimage e Understack già note. I prospect outbound ammessi non dimostravano una richiesta. Il vecchio catalogo conteneva già esplorazione nazionale/remoto e feedback per famiglie: sono stati mantenuti e resi espliciti per intento, lingua, fonte e perimetro geografico, non presentati come assenti.

## 3. Analisi campagne storiche

Presenti tutte le campagne 1–29. Le campagne 1–7 appartengono al motore precedente e non hanno revisioni dei quattro motori; zero in tabella non significa zero attività. Le campagne 8–29 contengono complessivamente {sum(c['revisions'] for c in h['campaigns'])} osservazioni/revisioni, non altrettante aziende uniche. Stati come salvati, senza ricalcolo o riscrittura.

{campaigntable}

Feedback manuali registrati nelle quattro tabelle consultate: 0. Nessuna preferenza è stata inventata. Le query completate dei quattro motori, incluse risoluzioni e pagine, sono {len(keys)}; {len(keys)-len(set(keys))} ripetono la stessa chiave motore/query/periodo/pagina nello storico. Una ripetizione lontana nel tempo può essere legittima: questo conteggio non equivale a crediti sprecati.

## 4. Problemi strutturali

- Moltiplicazione regionale: sul medesimo insieme di nove regioni, {len(old)} voci del catalogo precedente e {oldunique} query distinte. Il nuovo catalogo ne ha {len(new)}, tutte distinte. Ridurre sinonimi ripetuti rende più utile la copertura; non si afferma che più stringhe equivalgano a più clienti.
- Ammissione basata su contesto careers e parole tecniche: passavano Lidl vendite, Citycomm tirocinio e un articolo OpenAI/Hugging Face.
- Risoluzione per somiglianza: PACER associato a una pagina prodotto per piscine. Ora la continuità rifiuta quel risultato e conserva identità irrisolta.
- Collaborazioni note riutilizzate: ora memoria per richiesta e metadati, distinta dalla memoria aziendale.
- Limiti piccoli non mostrati come copertura: ora anteprima delle famiglie effettivamente assegnate e delle query escluse dai tetti.
- Assenza di riscontri originali, browser parziale, identità e attualità sconosciute restano limiti reali. Non sono risolti abbassando la qualifica.

## 5. Nuove strategie

{table(['Strategia stabile','Motore','Obiettivo','Politica temporale'],rows)}

Ogni strategia definisce intento, fonti target, competenze, geografia, tempi, ammissione minima, segnali, priorità, quota massima e metriche. I template sono configurabili in `search_strategies.py`; l'interfaccia configura motori, regioni, finestra e profilo, non espone un editor arbitrario di query. Domanda esplicita di rifacimento segue FREELANCE; WEBSITE_REBUILD rimane prospect outbound.

## 6. Query generation e copertura

Combinazioni sparse di intento, lingua, fonte e mercato: nessun prodotto cartesiano completo. Italiano e inglese sono scritti per le rispettive richieste, non tradotti meccanicamente. Tier 1 Padova/Veneto/Italia; Tier 2 Italia/Europa/UE da remoto; Tier 3 worldwide esplicitamente accessibile dall'Italia. Post pubblici LinkedIn e jobs/view, pagine careers e partnership sono percorsi distinti. Nessun accesso autenticato.

Il limite di 14 giorni resta verificato sulla fonte originale; `month` è soltanto il prefiltro Serper disponibile. Collaborazioni continuative e outbound non ricevono quel filtro. Le regioni selezionate restano vincolanti per presenza e outbound, con precedenza Veneto, Lombardia, Piemonte e Toscana e rotazione che copre tutte le nove regioni nel piano Deep. Nazionalità e remoto ricavati dalla query non sono prove di candidabilità.

## 7. Source intelligence

Le famiglie fonte sono ipotesi basate su URL/titolo/snippet, etichettate come tali; nessun dominio noto è automaticamente affidabile. I registri aggregano accessibilità osservata, duplicati, date originali, compatibilità geografica e richieste verificate. I dati legacy mancanti restano un limite, non una conferma di qualità.

{source_table}

Questi conteggi descrivono tracce attribuibili e revisioni nello storico; non sono un benchmark etichettato dei domini e non autorizzano un blacklist generale. Fonti social incomplete restano indizi con possibilità di revisione e risoluzione ufficiale, senza aggirare accessi.

## 8. Candidate admission

Esclusione preventiva del ruolo principale incompatibile, stage/junior, richiesta unpaid/equity esplicita, articolo informativo senza richiesta, pagina prodotto e restrizione geografica esplicita. Una richiesta di nuovo sito, migrazione o checkout può essere ammessa senza titolo “developer”, ma deve ancora superare tutte le verifiche commerciali. Le pagine careers ambigue non sono scartate in blocco. Nessun punteggio/snippet promuove da solo a VERIFIED.

## 9. Entity resolution

PACER → Baracuda Pacer è ora `UNRESOLVED / resolution_product_not_employer`. I controlli di continuità esistenti su nome, contesto, ruolo dell'editore e dominio restano attivi. Una pagina prodotto non prova l'identità del datore. Il risultato corretto può essere “non risolto”; questa fase non ha trovato offline l'azienda giusta. Le regole commerciali sono versionate 16 (15 per outbound), evitando il riuso di scarti con le vecchie regole; nessuna revisione storica cambia.

## 10. Deduplicazione

Chiave per URL canonico della richiesta e firma titolo/testo, distinta dal dominio aziendale. Richiesta invariata continuativa: riuso storico entro 24 ore. HTTP 404 documentato: backoff 7 giorni se i metadati non cambiano. URL nuovo della stessa azienda o metadati cambiati possono essere approfonditi. Esclusioni e contatti manuali restano persistenti. Dedup di annunci ripubblicati e CRM preesistenti conservati.

Stessa query/periodo già assegnata non riparte nella campagna. Query completata nelle ultime 6 ore non viene riacquistata subito; dopo può tornare utile per nuove pubblicazioni. La cache HTTP/provider rimane distinta da nuove aziende. Le TTL sono euristiche documentate, non una prova che una pagina non sia cambiata.

## 11. Performance learning

Metriche ricavate dai registri esistenti, senza nuove tabelle: query generate/eseguite/cache, risultati e URL unici, ammissioni/esclusioni, richieste plausibili/verificate, attualità/geografia, errori, crediti e tempo. Retry e paginazioni sommano tutte le ricevute, senza perdere i tentativi precedenti. Le famiglie legacy sono separate dalle nuove strategie; i loro successi non vengono attribuiti retroattivamente alla 5.0.

Ogni rapporto conserva numeratore/denominatore; denominatore nullo produce `null`. La precision richiede casi etichettati, non il numero di ammessi. I vecchi registri non sempre registravano ogni campo di rete: non si ricostruiscono spese inesistenti da uno zero tecnico. Feedback reale riutilizzabile, ma attualmente assente.

## 12. Adaptive allocation

Il coordinatore sceglie realmente la prossima query usando storico e risultati già salvati nella campagna corrente. Priorità modificabile soltanto con almeno 5 query distinte, 30 URL e 10 valutazioni. Aggiustamento descrittivo limitato a ±12, ulteriore feedback ±3 soltanto con almeno 10 valutazioni personali. Non è un modello di conversione calibrato.

Prima esplorazione delle famiglie, turno di riequilibrio ogni quattro assegnazioni, quota massima nominale 60% per famiglia con minimo di esplorazione, bilanciamento lingue/territori. Nessuna famiglia sparisce per due fallimenti; nessun trasferimento o aumento dei budget motore. In caso di esaurimento del catalogo si dichiara fine copertura, non si generano query infinite.

## 13. Research planner

Nuovo endpoint locale `POST /api/commercial/search-plan`, protetto da Host/Origin/CSRF. Legge impostazioni e storico senza scrivere né chiamare provider. UI: anteprima fuori dalle impostazioni avanzate; query, strategie, lingue, geografie, motivi di esclusione e massimali. Il piano è iniziale, non un'esecuzione simulata.

Deep richiede checkbox dopo anteprima e token legato a motori, regioni, finestra, budget e AI. Modifiche invalidano la conferma; un piano obsoleto è respinto prima dell'inserimento della campagna. Pilot/Extended invariati, impostazioni AI effettive incluse nella proposta. Non viene verificato il saldo remoto dell'account.

## 14. Modifiche implementate

Esteso il coordinatore persistente, senza riscrivere server, worker o browser engine. Nuove campagne marcate `search_version=5.0`; le campagne legacy conservano il vecchio planner. Integrati source intelligence, tracciamento strategia nei follow-up, memoria delle richieste e geografia delimitata ai blocchi della richiesta. Separato filtro impiego dipendente dal ranking di collaborazioni; unpaid/equity non prioritari. Target-fit intercetta appartenenza documentata a gruppo (caso Gor.Far.) prima dell'audit, senza inventare dimensioni aziendali.

Backup verificato codice/database in `data/backups/phase50`, hash e conteggi in `implementation-report/phase50-baseline.json`. Nessuna migrazione necessaria. I report 29 non sono stati sovrascritti. Il backend operativo non è stato riavviato.

## 15. File modificati

Differenza rispetto allo snapshot di inizio fase, non rispetto a Git (il repository conteneva modifiche pregresse):

{chr(10).join('- `'+f+'`' for f in files)}

Aggiunti inoltre fixture/README, artefatti `implementation-report/phase50-*`, questo report, metriche JSON e piano Campagna 30. Il README principale contiene istruzioni di utilizzo.

## 16. Test

Suite offline completa: {full['tests']} test in {full['seconds']} s, 0 fallimenti. Controllo finale mirato dopo gli ultimi ritocchi: {targeted['tests']} test in {targeted['seconds']} s, 0 fallimenti; non sommare i due conteggi. Due viewport Chrome (1440 e 390 px), anteprima, Deep non preconfermato, invalidazione conferma, elenco query, filtro impiego, assenza overflow/errori JS. Endpoint verificato con protezioni CSRF/Host/Origin e assenza scritture.

Il primo tentativo sotto sandbox stretta non poteva aprire server loopback/processi browser. Rieseguita la suite con permesso locale e guard offline mantenuto, senza accesso ai provider o dati operativi. Le regressioni emerse (careers troppo restrittivo, compatibilità planner legacy, mock PDF, geografia worldwide) sono state corrette. Replay e fixture riproducibili con i comandi nel README. Integrità: tutte le 58 tabelle invariate; ulteriori 81 revisioni e 100 documenti della fixture Campagna 28 identici.

## 17. Benchmark prima/dopo

{table(['Misura ammissione','Prima','Dopo'],[('Precision sui 24 binari','9/19 (47,37%)','9/9 (100%)'),('Recall sui positivi etichettati','9/9','9/9'),('Falsi positivi','10','0'),('Ambigui conservati (fuori denominatori)','8/8','8/8'),('Qualifiche commerciali nuove','0','0'),('Query duplicate nel catalogo sulle stesse regioni',len(old)-oldunique,len(new)-newunique)])}

Solo casi storici: precision 1/5 → 1/1, recall 1/1 conservata; 4 falsi positivi eliminati. Il positivo storico è Understack, non una nuova commessa. Non c'è holdout indipendente: non generalizzare il 100%.

Replay separato delle 128 tracce non etichettate: {b['raw_trace_replay']['new_decisions']}. Descrive ammissione semantica, non applica nuovamente coda, budget e dedup: non confrontare direttamente questi ammessi con le 26 aziende esaminate. Ranking: Citycomm e 404 rimossi; Internetimage e Understack rimangono consultabili, da verificare. PACER irrisolto. Attualità/geografia sono riportate separatamente nel JSON; date sconosciute restano sconosciute, stale non significa automaticamente chiuso.

## 18. Regressioni e controlli storici

{table(['Caso','Esito/limite'],[
('Lidl vendite','Escluso per ruolo incompatibile, non per sola vecchia data'),('PACER prodotto','Identità non risolta; prodotto respinto'),('Articolo OpenAI/Hugging Face','Escluso prima di letture costose'),('Citycomm tirocinio','Escluso da ammissione e annunci consigliati'),('404 iprogrammatori','Ranking escluso, retry differito se richiesta identica'),('LinkedIn vecchio o chiuso','Verifica data/apertura originale conservata; test 4.5'),('Remote US / EMEA','Non equivalgono a Italia; Europa/worldwide originali ammessi'),('Internetimage / Understack','Richiesta identica riutilizzata nello storico, URL nuovo non bloccato'),('Outbound / browser timeout','Non domanda verificata; incompleto non diventa difetto'),('Gor.Far. gruppo','Appartenenza documentata impone revisione pre-audit; dimensione ignota'),('Query esaurite','Nessuna ripetizione nella campagna, backoff tra campagne'),('Copertura nazionale','Italia più remoto espliciti, regioni outbound preservate'),('Dipendenti','Filtro separato, default collaborazioni'),('Cache','Ricevute cache separate da chiamate e crediti'),('Social incompleto','Resta possibile revisione senza login'),('Data assente','DATE_UNKNOWN, nessuna data da indicizzazione'),('Publisher diverso','Attribuzione/continuità originali richieste'),('Strategia senza risultati','Rotazione e feedback limitato, campione minimo, nessun loop infinito')])}

Nessuna perdita di positivo nel benchmark. Nessuna regressione grave nella suite. Restano rischi di euristiche lexicali e di ranking su pagine ambigue: la disponibilità generale non certifica un posto aperto. Non tutti i casi storici hanno prove sufficienti per attribuire un'azienda o un progetto.

## 19. Costi

Sviluppo offline: 0 Serper, 0 OpenAI, 0 scraping. Pilot/Extended e budget salvati invariati. Proposta Deep: massimo **144 richieste provider/crediti Serper stimati**, **20 chiamate AI**, **1 USD AI massimo stimato**; nessuna ricarica/acquisto. Il costo monetario Serper e il saldo sono sconosciuti e non vengono consultati. Il tetto AI è un controllo stimato locale, non un massimale di fatturazione garantito dal provider.

78 query iniziali selezionate su 101 disponibili, fino a 2 pagine e follow-up nei medesimi tetti; query e richieste API non sono sinonimi. Massimi: 240 candidati, 1800 letture HTTP, 16 browser, 7200 secondi somma lavoro motori. La somma non è una promessa di durata a parete: backoff, pause e ripresa la allungano. Limiti tecnici per singola richiesta restano attivi. Nessuna misurazione live di opportunità per credito è disponibile.

## 20. Limiti

La discovery è ora più diversificata e riduce errori noti nel replay, ma il rendimento delle nuove query non è stato misurato su Google. Campione piccolo, selezionato, con esempi sintetici e nessun set indipendente. Nessuna conversione osservata. Storico feedback vuoto; niente affermazioni di apprendimento delle preferenze. Gli audit storici parziali rimangono tali; il browser engine non è stato ricostruito.

La classificazione di fonti da snippet è una ipotesi. Un annuncio può cambiare senza che lo snippet cambi: le TTL limitano il riuso, non garantiscono attualità. La risoluzione di tutte le omonimie non è garantita. I registri legacy incompleti limitano l'attribuzione quantitativa dei consumi. Nuove strategie non ereditano un'efficacia dimostrata dalle vecchie famiglie.

## 21. Proposta prossima campagna

Campagna 30 tecnicamente pronta come **piano**, non creata né avviata. Consultare [PHASE-5.0-SEARCH-PLAN.md](PHASE-5.0-SEARCH-PLAN.md), riavviare manualmente il backend con `.venv/bin/python app.py` dopo aver arrestato l'istanza precedente, ricaricare il browser e generare l'anteprima. Deep resta una scelta esplicita con conferma dei costi. L'AI rimane REMOTE gpt-5.4-mini Shadow, 20 chiamate e 1 USD; nessuna modifica al database.

Valutare la ricerca futura per richieste originali pertinenti, nuove/già note, candidabilità dall'Italia, data e apertura documentate, impiego/collaborazione/outbound separati, opportunità qualificate e costo effettivo. Revisionare un campione di ammessi e scartati senza adattare le etichette al risultato. Non riempire risultati o cambiare soglie per arrivare a 50.
'''
 (ROOT/'PHASE-5.0-REPORT.md').write_text(report)
 plan_report=f'''# Campagna 30 — Piano proposto, non avviato

Generato offline da impostazioni e storico locali. Nessuna chiamata API o creazione campagna. L'ordine è iniziale: può cambiare in base agli esiti entro gli stessi tetti. Il saldo Serper non è noto.

## Profilo proposto e autorizzazione

**Deep**, tutti e quattro i motori, {len(regions)} regioni già configurate: {', '.join(regions)}. Nessun cambiamento dei profili Pilot/Extended. Lingue: italiano e inglese. Annunci: 14 giorni, da verificare sulle fonti originali. Collaborazioni continuative e outbound hanno politiche temporali distinte.

{table(['Limite','Per motore','Totale massimo'],[
('Query discovery',24,96),('Query iniziali effettivamente selezionate','24 / 15 / 15 / 24',p['planned_queries']),('Pagine per query',2,'entro tetti provider'),('Richieste provider / crediti Serper stimati',36,144),('Letture HTTP',450,1800),('Candidati approfonditi',60,240),('Esecuzioni browser',4,16),('Follow-up',12,48),('Budget tempo lavoro (secondi)',1800,7200),('Chiamate AI','condiviso',20),('AI massimo stimato USD','condiviso',1)])}

I tetti sono indipendenti: esaurire prima crediti, letture, tempo o candidati può impedire tutte le query previste. AI REMOTE, gpt-5.4-mini, Shadow: impostazioni salvate invariate. Costo monetario Serper non noto; non è corretto indicare 144 crediti come 144 euro/dollari. Budget AI stimato dall'app, fattura effettiva da verificare nel provider. 7200 secondi sono una somma dei tetti di lavoro, non limite garantito di tempo trascorso con backoff e pause.

Per attivare: riavviare il backend, selezionare Deep, generare anteprima, leggere i massimali, selezionare la conferma e premere Avvia. Cambiare preferenze richiede una nuova anteprima. **Questo documento non autorizza l'esecuzione** e nessun profilo è stato attivato automaticamente.

## Strategie e copertura

{table(['Strategia','Motore','Query selezionate','Fonte target','Priorità iniziale'],[(x['id'],x['engine'],sum(q['strategy_id']==x['id'] for q in p['queries']),x['source_family'],x['priority']) for x in catalog()])}

15 strategie su 15 presenti, 78 query selezionate su 101 disponibili, 23 rinviate dal tetto query del motore. Tier 1 Italia/Padova/Veneto; Tier 2 Italia/Europa/UE da remoto; Tier 3 worldwide. La sede estera non è esclusa se l'annuncio originale ammette lavoro dall'Italia. “Remote” o “EMEA” da soli non bastano. Per presenza/outbound restano i territori selezionati. I settori outbound sono imprese specializzate, servizi B2B e marchi indipendenti, non generica anzianità del sito.

## Query iniziali

Le stringhe sono quelle del planner prima dell'aggiunta centrale di `-filetype:pdf` nell'adattatore Serper. Non sono state eseguite.

{table(['#','Strategia','Lingua / tier','Fonte','Query'],[(n,q['strategy_id'],q['language']+' / '+q['geography_tier'],q['source_preference'],q['query']) for n,q in enumerate(p['queries'],1)])}

## Query non selezionate

`engine_query_cap` significa rinviata perché il piano iniziale raggiunge il limite di query di quel motore. Non significa inefficace, già visitata o scartata commercialmente.

{table(['Strategia','Query','Motivo'],[(q['strategy_id'],q['query'],q['reason']) for q in p['excluded_queries']])}

Nessuna strategia esclusa completamente in questa proposta. Con Pilot alcune famiglie non entrano nel tetto di tre query per motore: l'anteprima mostra questa copertura limitata senza fingere che siano state esplorate.

## Rischi e criteri di valutazione

Fonti social potrebbero restare incomplete; niente account/cookie o aggiramento robots. Le query inglesi potrebbero trovare aziende non aperte a contractor italiani; verificare la richiesta, non il titolo. Domanda di progetto, disponibilità continuativa, impiego dipendente e prospect devono rimanere separati. La riduzione dei falsi positivi offline non garantisce il rendimento live.

Misurare query effettive, cache, crediti, fonti originali accessibili, nuove richieste distinte, date/apertura/geografia verificate, vere collaborazioni esterne e qualifiche commerciali. Per ogni strategia riportare numeratore e denominatore. Rivedere manualmente almeno un campione di ammessi e scartati e distinguere fonte insufficiente da classificazione errata. Senza un campione rappresentativo non dichiarare precision di mercato o ricavi attesi. Conservare i casi negativi e l'esito incompleto degli audit, senza promuoverli per aumentare i numeri.
'''
 (ROOT/'PHASE-5.0-SEARCH-PLAN.md').write_text(plan_report)
 print(json.dumps({'reports_written':3,'tests':full,'targeted':targeted,'queries':metrics['queries'],'database_unchanged':i['all_tables_unchanged']},ensure_ascii=False))
if __name__=='__main__':main()
