"""Build Phase 4.5 reports exclusively from saved replay and offline logs."""
import json,re
from pathlib import Path
from scripts.replay_commercial45 import evaluate_saved
ROOT=Path(__file__).resolve().parents[1]
def testlog(name):
 text=(ROOT/'implementation-report'/name).read_text();match=re.search(r'Ran (\d+) tests in ([\d.]+)s',text)
 return {'file':'implementation-report/'+name,'count':int(match[1]) if match else None,'seconds':float(match[2]) if match else None,'passed':bool(re.search(r'^OK$',text,re.M))}
def table(headers,rows):
 def cell(x):return str(x if x is not None else 'Non verificato').replace('|',' / ').replace('\n',' ')
 return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+['| '+' | '.join(cell(x) for x in row)+' |' for row in rows])+'\n'
def main():
 m=evaluate_saved();m['tests']={'full_suite':testlog('phase45-tests.txt'),'regressions_and_rules':testlog('phase45-regressions.txt'),'http_memory_discovery':testlog('phase45-final-targeted.txt'),'final_activity_semantics':testlog('phase45-final-activity.txt'),'ui':json.loads((ROOT/'implementation-report/phase45-ux.json').read_text())}
 m['integrity']=json.loads((ROOT/'implementation-report/phase45-integrity.json').read_text());m['backup']=json.loads((ROOT/'implementation-report/phase45-baseline.json').read_text())['backup']
 m['policy']={'max_job_age_days_default':14,'configurable_range':[1,90],'open_evidence_ttl_days':14,'serper_period_for_default_window':'month','search_filter_certifies_publication':False,'official_qualification_unchanged':True,'manual_negative_conflicts_conservative':True,'ranking_is_not_conversion_probability':True}
 m['readiness']={'offline_checks_passed':m['tests']['full_suite']['passed'] and m['tests']['regressions_and_rules']['passed'] and all(x['passed'] for x in m['tests']['ui']['checks']),'backend_restart_required':True,'live_validation_performed':False,'campaign_29_started':False}
 cats={'recent':'Recenti','verify':'Da verificare','archived':'Archiviati'};saved=m['saved_summary'];manual=m['manual_scenario']['summary']
 report='''# Customer Search — Fase 4.5: Fresh & Active Opportunities

## Esito

La data non è più soltanto un contributo al punteggio: per entrare in **Recenti** servono una pubblicazione documentata entro la finestra e indicazioni compatibili con lavoro dall’Italia, senza chiusura documentata o conflitti. **OPEN_UNKNOWN è ammesso ma sempre etichettato “Apertura da verificare”.** Un annuncio senza data resta consultabile in Da verificare. Quelli certamente vecchi, chiusi o incompatibili restano in Archiviati, senza riscrivere le revisioni commerciali.

La fase è offline: nessuna campagna 29, chiamata Serper/OpenAI, visita a LinkedIn o scraping esterno, candidatura, email, cambio budget, credenziale, commit o push. Il backend operativo non è stato riavviato durante lo sviluppo.

## 1. Problema identificato

Nella 4.4 era possibile consigliare un ruolo tecnicamente compatibile senza data verificata. Un’età oltre 180 giorni riduceva soltanto il punteggio. La ricerca Serper della pipeline commerciale non applicava un periodo, benché l’adattatore `/search` supportasse già `week`, `month`, `year`. Il solo termine “remote” migliorava il ranking, senza accertare dove potesse lavorare il candidato.

La nuova proiezione mantiene `compatibility_score`, `score_detail`, `evidence_confidence`, provenienza e stato commerciale. Aggiunge `freshness_status`, `application_status`, `geographic_eligibility`, priorità geografica, ragioni, prove, conflitti e categoria. I punteggi tecnici della 4.4 e il suo replay restano disponibili; la nuova ammissione è separata dal ranking.

## 2. Discovery e risparmio delle risorse

FREELANCE usa otto famiglie finite: WordPress freelance, frontend partita IVA, WooCommerce, annunci LinkedIn WordPress, richieste pubbliche LinkedIn, WordPress remote Italy, frontend contractor remote Europe, e-commerce contract Italia. Le nuove famiglie sostituiscono la precedente esplorazione Instagram in questo catalogo; il supporto ai risultati pubblici già presenti non viene eliminato. Il planner conserva rotazione, deduplicazione, quote, rate limit, cache e limiti per campagna. Le varianti remote hanno ambito esplicito di eleggibilità dall’Italia e non attribuiscono all’azienda la regione della query.

Si riusa il **periodo mensile già supportato dall’adattatore Serper** per la finestra predefinita di 14 giorni. Per finestre fino a 7 giorni si usa `week`; fino a 31 `month`; per finestre maggiori `year`. È un filtro di discovery più ampio della condizione finale, non una certificazione. Non è stato introdotto o presunto un parametro API “ultimi 14 giorni”, né verificato live il comportamento del servizio. La cache esistente include già il periodo nella chiave. Le ricerche di risoluzione del dominio ufficiale restano senza filtro temporale.

`max_job_age_days` è validato da 1 a 90 e salvato nei filtri delle nuove campagne; i limiti operativi rimangono identici. La vista dei risultati consente anche una finestra di consultazione indipendente. I task nuovi ereditano la finestra della loro campagna; i task storici non sono riscritti. La versione delle regole dei tre motori di annunci viene incrementata, così una decisione recente della vecchia versione non nasconde automaticamente la nuova valutazione. WEBSITE_REBUILD conserva la sua versione.

Tre livelli di filtro:

1. Metadati: incompatibilità geografica esplicita e irrilevanza; una data Serper, un generico Apply o una chiusura solo nello snippet non certificano il fatto originale.
2. Memoria: osservazioni negative documentate e senza conflitti impediscono nuovi approfondimenti o risoluzioni dello stesso URL. La verifica è ripetuta prima dei retry; nessuna query aggiuntiva serve a questa verifica locale.
3. Prima pagina originale: dati del singolo JobPosting/blocco permettono un arresto dopo una lettura, conservando documenti, estratti, competenze e motivi. Nessuna ulteriore lettura aziendale, browser, AI o follow-up per quel candidato. I conflitti restano da valutare, senza uno scarto precoce certo.

**Non è dimostrato un risparmio di crediti reali.** I test provano il percorso di arresto con una sola lettura e la soppressione di risoluzioni già inutili. Il replay misura soltanto quanti record dispongono delle prove necessarie; una futura campagna dovrà misurare le chiamate effettivamente risparmiate.

## 3. Date e clock

Stati: `FRESH_CONFIRMED`, `STALE_CONFIRMED`, `DATE_UNKNOWN`, `FUTURE_OR_INVALID_DATE`. La finestra predefinita è inclusiva di 14 giorni. Il clock è passato esplicitamente al valutatore; timestamp con offset vengono convertiti in UTC. Le date senza orario sono normalizzate all’inizio del giorno UTC, senza inventare un’ora di pubblicazione osservata. Una scadenza senza orario non viene dichiarata trascorsa prima della fine del giorno indicato.

Si usano `JobPosting.datePosted`, date specifiche del blocco dell’annuncio o osservazioni manuali tipizzate. Non si usano crawling, indicizzazione, ricerca, campagna, ultima modifica generica o acquisizione dello snippet. JSON-LD con più posizioni non trasferisce automaticamente la data di una posizione alle altre. Data futura o illeggibile non diventa “oggi”.

Le etichette relative in giorni sono utilizzate solo con URL, osservazione datata e semantica di pubblicazione. Viene conservata l’etichetta e calcolato un intervallo per l’arrotondamento: “14 days ago” al confine resta incerto. Mesi/anni relativi non diventano date esatte. L’utente può registrare “oltre la finestra” e il testo osservato; il limite della finestra al momento della verifica è conservato. Se la finestra viene successivamente ampliata oltre ciò che l’osservazione dimostra, il dato torna insufficiente.

## 4. Stato candidature e geografia

`OPEN_CONFIRMED` richiede una dichiarazione esplicita di apertura nel blocco specifico originale, oppure una verifica manuale, osservata negli ultimi 14 giorni. Non basta che la pagina esista, che una data sia recente o che Apply sia presente nello snippet. Per prudenza neppure il solo pulsante Apply acquisito viene promosso automaticamente a conferma. La UI precisa che un’apertura osservata non garantisce che la candidatura sia accettata.

Le chiusure esplicite (inglese/italiano) e le scadenze documentate prevalgono. Negazioni e contesto sono controllati; footer, cataloghi multisoggetto e frasi su altre posizioni non sono usati come stato del singolo annuncio. Una vecchia dichiarazione positiva scade a OPEN_UNKNOWN. Una chiusura non viene silenziosamente cancellata da un successivo dato positivo: entrambe le osservazioni restano visibili e il caso resta prudenzialmente fuori da Recenti.

La compatibilità geografica riguarda la posizione e i requisiti del candidato, non l’indirizzo di `hiringOrganization`. Italia/UE hanno priorità alta; worldwide/Europe ed EMEA con Italia esplicita media. Remote generico, Remote — United States ed EMEA senza inclusione dimostrata restano UNKNOWN. US/UK only, restrizioni esplicite e presenza obbligatoria estera riconosciuta sono incompatibili. Una società americana con una posizione remote Europe può essere compatibile. Il solo paese di residenza ammesso nel JSON-LD non viene trasformato in un lavoro remoto inventato.

I pattern non coprono tutte le lingue e tutte le restrizioni nazionali. I casi non riconosciuti rimangono sconosciuti, non compatibili per default. Le indicazioni geografiche in titolo/snippet restano etichettate come metadati, non diventano informazioni aziendali ufficiali.

## 5. Fonti originali e conflitti

Le prove conservano tipo, valore, estratto, URL, momento dell’osservazione, metodo, ambito e provenienza. Date assolute diverse o stati/geografie discordanti generano un conflitto visibile. La raccomandazione non diventa una qualifica commerciale.

Una fonte alternativa può contribuire soltanto se è associata esplicitamente allo stesso annuncio (`same_job_verified`). Il test usa un’identità di annuncio controllata; non si deduce un’equivalenza dal solo nome dell’azienda. Non è stato introdotto un risolutore universale di annunci cross-portale: nei casi ambigui la data resta sconosciuta. Non vengono aggirati accessi, robots, CAPTCHA o limiti.

## 6. Interfaccia e osservazioni manuali

Tre viste: **Recenti** predefinita, **Da verificare**, **Archiviati**, con conteggi e filtri personali già presenti. Ogni scheda mostra compatibilità tecnica distinta dall’affidabilità, pubblicazione/età quando documentate, apertura, lavoro dall’Italia, prove e limiti. Conservati Apri annuncio, Interessante, Non interessante, Da verificare e Già valutato. Non viene effettuata alcuna candidatura automatica.

“Registra una verifica manuale” richiede data/ora effettiva della verifica, esito e una nota facoltativa (obbligatoria per descrivere la restrizione geografica). L’orario locale del browser viene convertito in UTC. Le osservazioni sono append-only, associate a opportunità e revisione, con provenienza MANUAL_OBSERVATIONS. Restano separate dalle preferenze personali, dalle prove automatiche e dal CRM. Gli endpoint mantengono Host/Origin/CSRF, validazione della revisione e divieto di osservazioni future.

Le pagine di collaborazione continuativa AGENCIES non sono datate artificialmente né archiviate perché senza data: restano in Da verificare con esenzione esplicita. STARTUPS applica le regole alle posizioni, non alle richieste di progetti, equity o partnership. WEBSITE_REBUILD non entra nella proiezione degli annunci e non riceve il filtro temporale.

## 7. Replay storico della Campagna 28

'''
 report+=table(['Insieme','Recenti','Da verificare','Archiviati','Pubblicazioni esatte documentate','Apertura confermata'],[['13 consigliati della 4.4',saved['categories'].get('recent',0),saved['categories'].get('verify',0),saved['categories'].get('archived',0),saved['publication_verified'],saved['opening_verified']]])
 report+=f"\nDai soli dati salvati: {saved['certainly_stale']} annuncio certamente vecchio, {saved['certainly_closed']} certamente chiusi, {saved['certainly_incompatible']} certamente incompatibili. Geografia classificabile nei dati disponibili: {saved['geography_known']}; le restanti indicazioni sono insufficienti. Fra i 12 Da verificare è inclusa una collaborazione continuativa esente dalla finestra, non un annuncio recente.\n\n"
 report+=table(['ID / motore','Annuncio originale','Stato 4.4 / commerciale','Freshness','Candidature','Geografia','Categoria 4.5','Motivo / provenienza'],[[str(r['id'])+' / '+r['engine'],f"[{r['title']}]({r['original_url']})",'Consigliato / '+r['official_state'],r['freshness_status'] if r['applicable'] else 'Non applicabile',r['application_status'],r['geographic_eligibility'],cats[r['category']],'; '.join(r['reasons'])+' · '+', '.join(sorted({e['provenance'] for e in r['evidence']}))] for r in m['previous_recommendations']])
 report+='''
Nessuna apertura attuale è stata verificata live. Il confronto è riproducibile al clock dello snapshot della fixture; nell’app il passare del tempo cambia la proiezione, non la revisione commerciale. La data futura o sconosciuta non può far salire un record in Recenti grazie al solo punteggio tecnico.

### Scenario distinto: MANUAL_OBSERVATIONS

Le informazioni riferite dall’utente su 774, 866 e 870 non sono presenti necessariamente nelle revisioni storiche: sono in una fixture separata, non mescolata nel replay sopra. Il clock della fixture è un riferimento di test esplicito, **non l’ora reale dichiarata della visita a LinkedIn**. Nessuna data di pubblicazione esatta è ricavata da “circa un anno” o “circa cinque mesi”.

'''
 report+=table(['ID','Freshness','Candidature','Geografia','Categoria','Ragione'],[[r['id'],r['freshness_status'],r['application_status'],r['geographic_eligibility'],cats[r['category']],'; '.join(r['reasons'])] for r in m['manual_scenario']['items']])
 report+='''
Tutti e tre sono archiviati nello scenario. XWP è certamente oltre la finestra; Remote — United States resta GEO_UNKNOWN, non una restrizione US-only inventata. Apply disponibile rimane un’osservazione del pulsante. Creative Retail e SuiteFit hanno chiusura esplicita; per SuiteFit non è inventata una data mancante. Nessuno di questi controlli è stato inserito nel database operativo.

Per registrare verifiche reali: aprire **Da verificare**, cercare il titolo/azienda, aprire la fonte, espandere **Registra una verifica manuale** e inserire ciò che è effettivamente osservabile con la data/ora reale. Per un’età relativa usare “oltre la finestra” e annotare la dicitura. Per XWP non dichiarare “aperto” solo perché compare Apply.

## 8. Risparmio e costi misurati

'''
 resource=m['resource_measurement']
 report+=f"Esaminati offline i metadati dei {resource['saved_freelance_metadata_examined']} record FREELANCE: **{resource['certain_metadata_exclusions']} esclusioni certe** per le nuove regole precoci. Il resto richiede dati migliori: gli snippet non vengono trattati come prove sufficienti pur di mostrare risparmi. Crediti Serper, richieste HTTP e chiamate AI realmente risparmiati durante questa fase: **non misurabili con un confronto live**, perché nessuna ricerca viene eseguita; i contatori operativi della fase sono zero.\n\n"
 report+='''## 9. Integrità e compatibilità

'''
 integrity=m['integrity']
 report+=f"Backup verificato in `{m['backup']['path']}`: codice ZIP con controllo CRC, SQLite con integrity_check e compressione verificata tramite round-trip hash. Integrità finale: **{integrity['integrity']}**; **{len(integrity['tables'])} tabelle operative invariate: {integrity['all_tables_unchanged']}**. Le {integrity['fixture_revisions']} revisioni e i {integrity['fixture_documents']} documenti della fixture reale coincidono col database.\n\n"
 report+='''Migrazione additiva 66: tabella `commercial_job_observations`, indice e versione schema, all’interno della transazione esistente. Verificata su database temporanei e ripetuta senza perdita di osservazioni. Nessuna migrazione applicata al database operativo durante lo sviluppo. Il codice precedente può ignorare la tabella aggiuntiva senza cancellarla; il backup consente recupero. Le osservazioni personali della 4.4 e le revisioni precedenti restano conservate.

## 10. Test e regressioni

'''
 for name,t in m['tests'].items():
  if name!='ui':report+=f"- {name}: {t['count']} test in {t['seconds']} s — {'OK' if t['passed'] else 'NON CONCLUSO / FALLITO'} (`{t['file']}`).\n"
 report+='''- Chromium locale 1440 e 390 px: viste e conteggi, filtri, link senza navigazione esterna, contratto ignoto, distinzione affidabilità/punteggio, revisioni personali, osservazione di chiusura e persistenza dopo reload; nessun overflow o errore JavaScript.
- Venti casi richiesti, più confini temporali, timestamp UTC, negazioni, fonti discordanti, footer, più JobPosting, residenza diversa dal lavoro remoto, fonti alternative non associate, memoria negativa prima della rete, configurazione, scope dei motori, migrazioni e protezioni HTTP.
- Rete esterna, endpoint operativi e scritture ai dati reali bloccati dalla guardia dei test; solo server e browser locali con database temporanei. I test mirati e la suite si sovrappongono: non sommare i conteggi come casi unici.

Il primo passaggio generale ha trovato quattro regressioni: due dovute al controllo anticipato che non conservava la classificazione/estrazione degli annunci scaduti, due a vecchie aspettative sulla versione delle strategie e sul territorio delle query. Il percorso anticipato ora richiama la qualificazione locale della fonte già acquisita, conserva estratti, competenze e scadenza, senza ulteriori letture. I test delle query accettano il nuovo scope remote Italy/Europe esplicito e la versione 4.5 solo per FREELANCE. Nessun requisito commerciale è stato allentato per far passare i test.

## 11. File modificati

'''
 for name in integrity['changed_baseline_files']+integrity['new_source_files']:report+='- `'+name+'`\n'
 report+='''
Aggiunti anche `tests/fixtures/commercial45/`, log e screenshot in `implementation-report/`, questo report e il JSON delle metriche. Il log della prima suite fallita è conservato separatamente per trasparenza.

## 12. Limiti e prontezza per Campagna 29

- La fase dimostra filtri e comportamento su dati salvati e casi controllati, non che esistano nuovi annunci recenti accessibili o un miglioramento delle conversioni.
- Il periodo Serper mensile è più ampio di 14 giorni e l’indicizzazione può essere imprecisa. La data originale resta necessaria. Nessuna verifica live del provider durante questa fase.
- Fonti che non espongono pubblicazione/geografia restano Da verificare; non si deducono date dal crawling. Etichette relative in mesi/anni restano testo/manuale, non date inventate.
- Il riconoscimento geografico e linguistico è conservativo e non universale. Una posizione estera remota non diventa automaticamente accessibile dall’Italia.
- Un annuncio riaperto con lo stesso URL e una vecchia chiusura conservata può generare un conflitto; non viene riammesso automaticamente senza una verifica esplicita. Non è stato introdotto un comando per cancellare silenziosamente osservazioni precedenti.
- Nessun risolutore cross-portale universale, nessun login LinkedIn, nessuna promessa di “aperto” basata soltanto su Apply.
- Il problema dei quattro audit browser parziali della 28 non viene modificato in questa fase. WEBSITE_REBUILD e le sue quote restano separati.

Dopo il collaudo offline, la 4.5 è utilizzabile **previo riavvio del backend** e ricaricamento della pagina. La Campagna 29 non è stata avviata. Per una futura verifica mantenere i budget e le regioni esistenti e controllare, separatamente, pubblicazioni documentate entro 14 giorni, aperture confermate, accessibilità dall’Italia e scarti precoci. Il successo non sarà il numero di schede ma la conferma manuale delle poche opportunità Recenti realmente candidabili.
'''
 (ROOT/'PHASE-4.5-METRICS.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');(ROOT/'PHASE-4.5-REPORT.md').write_text(report)
 print(json.dumps({'saved':saved,'manual':manual,'tests':{k:v for k,v in m['tests'].items() if k!='ui'},'integrity':integrity['all_tables_unchanged']},ensure_ascii=False))
if __name__=='__main__':main()
