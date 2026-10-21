"""Generate Phase 4.4 delivery artifacts from offline replay and test logs."""
import json,re
from pathlib import Path
from collections import Counter
from scripts.replay_commercial44 import evaluate
ROOT=Path(__file__).resolve().parents[1]
def testlog(name):
 p=ROOT/'implementation-report'/name;s=p.read_text() if p.exists() else '';m=re.search(r'Ran (\d+) tests in ([\d.]+)s',s)
 return {'file':str(p.relative_to(ROOT)),'count':int(m[1]) if m else None,'seconds':float(m[2]) if m else None,'passed':bool(re.search(r'^OK$',s,re.M))}
def table(headers,rows):
 def cell(x):return str(x if x is not None else 'Non verificato').replace('|',' / ').replace('\n',' ')
 return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+['| '+' | '.join(cell(x) for x in row)+' |' for row in rows])+'\n'
def build_report():
 m=evaluate();m['tests']={'full_suite':testlog('phase44-tests.txt'),'targeted':testlog('phase44-final-targeted.txt'),'final_ranking':testlog('phase44-ranking-final.txt'),'ui':json.loads((ROOT/'implementation-report/phase44-ux.json').read_text())}
 m['integrity']=json.loads((ROOT/'implementation-report/phase44-integrity.json').read_text())
 m['backup']=json.loads((ROOT/'implementation-report/phase44-baseline.json').read_text())['backup']
 for e in m['engines'].values():
  reasons=e['excluded_reasons'];e['clearly_irrelevant_or_negative_source']=sum(reasons.get(k,0) for k in ('negative_or_irrelevant_source','different_primary_specialism'))
  e['insufficient_information']=sum(reasons.get(k,0) for k in ('insufficient_technical_information','no_request_context'))
  e['not_specific_opportunity_url']=reasons.get('not_specific_opportunity',0)
 m['weights']={'technical_max':65,'external_hint':12,'geography_max':10,'recency_max':8,'original_request_bonus':5,'recommendation_minimum':40,'medium_minimum':50,'high_minimum':75,'internship_penalty':-10,'unpaid_equity_penalty':-15,'old_publication_penalty':-10,'nonpreferred_nonremote_area_penalty':-15,'unknown_bonus':0,'not_conversion_probability':True}
 rec=m['recommended'];r='''# Customer Search — Fase 4.4: Opportunity Discovery & Intelligent Ranking

**Recuperati 13 annunci da aprire e valutare: 11 dei 23 risultati Freelance e 2 da Agenzie. Fra i 15 `social_incomplete` Freelance, 9 sono consigliabili.** Nessuno è diventato VERIFIED, POTENTIAL o READY_TO_CONTACT. Sono raccomandazioni basate sulle informazioni salvate, non nuovi clienti, incarichi aperti o candidature inviate.

La fase è interamente offline: zero campagne, Serper, OpenAI, scraping esterno, invii, cookie/sessioni social, commit o push. Backend non riavviato; budget e credenziali invariati. Lo snapshot riproducibile è quello della Campagna 28, non una nuova verifica di disponibilità odierna.

## 1. Problema originale e architettura

La campagna 28 ha 81 schede, non 81 commesse. Conserva già i titoli, snippet, URL e motivi di accesso incompleto. La vista commerciale `opportunity_view.build()` richiede prove e identità; molti social sono quindi NOT_ACTIONABLE e scompaiono dal filtro predefinito. La discovery esclude inoltre alcune posizioni dipendenti prima della verifica: l’assenza della possibilità freelance non equivale a irrilevanza professionale.

L’app resta Python / SQLite / server HTTP locale e JavaScript/CSS esistenti. `commercial_opportunities` identifica le schede, `commercial_revisions` conserva le valutazioni, `commercial_discovery` registra le apparizioni e `research_documents` conserva gli originali. I worker di campagna, le quote e il CRM non sono ricostruiti.

## 2. Implementazione

- Proiezione pura `recommendations.assess/rank`, con data esplicita nel replay, senza rete/AI/scritture. Legge la revisione selezionata; punteggio e affidabilità restano distinti dalla qualifica ufficiale.
- API GET `/api/commercial/recommendations`, filtri e paginazione dopo ranking e deduplicazione. Ricostruisce gli annunci della 28 senza nuove ricerche.
- API POST `/api/commercial/opportunities/{id}/job-review`: valutazioni personali append-only, con riferimento alla revisione effettivamente vista. Host, Origin e CSRF già presenti sono conservati; nessuna candidatura o mutazione del CRM.
- Migrazione additiva 65 per `commercial_job_reviews`, transazionale, ripetibile e provata su database temporanei. La lettura funziona anche prima della migrazione, con stato personale “Da verificare”.
- L’ammissione non esclude automaticamente un annuncio tecnico individuale solo per rapporto dipendente: passa il ranking minimo come `recommendation_only`. Gli altri filtri, le esclusioni e la qualifica commerciale restano rigorosi. Le esclusioni storiche della discovery non sono riscritte né trasformate in schede.
- “Non contattare”, esclusioni CRM, contatti già gestiti, eliminazioni e revisioni social negative prevalgono nella nuova vista. Le decisioni personali sui duplicati si propagano alla rappresentazione raggruppata, senza modificare i record sottostanti.

## 3. Ranking spiegabile

Tecnica: massimo 65, ottenuto dalla competenza più pertinente più 5 per ulteriore competenza, con tetto. WordPress/WooCommerce hanno base 55, frontend 50, sviluppo web/e-commerce 45, JavaScript 40; PHP, React, Next.js e API hanno pesi secondari. Full-stack o IT da soli non bastano. Un ruolo principale SAP, mobile nativo, commerciale o altro ambito incompatibile non diventa pertinente per una firma o un commento che cita WordPress.

Contratto: segnale esterno +12; dipendente 0 (può restare interessante); stage -10; equity/senza compenso -15. Full-time non equivale a dipendente. Negazioni come “non accettiamo freelance” non generano bonus. Lo slug URL non certifica il contratto. Un segnale solo nei metadati resta esplicitamente non verificato sulla pagina.

Geografia: Veneto/remoto fino a +10, altre località risolte +6, area nota non preferita e non remota -15. Nessun bonus per l’area della query. La risoluzione geografica locale non copre tutte le città: ad esempio Rende è conservata come indicazione da verificare, senza dedurne automaticamente la regione. Il lavoro remoto non viene inventato dalla sede lontana o dal solo URL.

Attualità: +8 entro 30 giorni, +4 entro 90, -10 oltre 180; solo data originale con base registrata. Indicizzazione, consultazione e date future non sono spacciate per pubblicazione. Un annuncio datato perde priorità; solo chiusura/scadenza esplicita ne comporta l’esclusione per inattività.

Fonte: +5 per blocco originale acquisito, 0 per metadati. `evidence_confidence` è HIGH con originale e identità corroborata, MEDIUM con originale ma identità non corroborata, LOW con soli metadati. Non è una garanzia su contratto o attualità.

Soglie iniziali: consigliato da 40; bassa 40–49, media 50–74, alta 75–100. Sono criteri editoriali testabili, non probabilità scientifiche né pesi calibrati sui clienti acquisiti. Nessun punto per budget sconosciuti.

## 4. Fonti, duplicati e LinkedIn

Titolo di ricerca, snippet, pagina originale, pagina aziendale, terzi e origine sconosciuta conservano etichette separate. Un nome ricavato dallo slot azienda dell’URL è un indizio, non un’identità verificata. Le pagine non consultabili mostrano “Contenuto non completamente verificato. Apri l’annuncio per controllare i dettagli.” Non vengono riaperti URL nei replay.

Pagine di ricerca generiche, servizi del venditore, documenti PDF, ruoli incompatibili, assenza di competenze e chiusura esplicita sono motivi distinti. I post richiedono un contesto di richiesta vicino alle competenze: le biografie dei commentatori non bastano.

Deduplicazione per URL canonico (compresi ID LinkedIn e varianti di locale/tracking); tra portali diversi richiede anche stesso soggetto, ruolo, testo sostanziale, località e data. Due progetti diversi della stessa azienda non sono fusi solo perché hanno lo stesso titolo. Restano possibili duplicati con testi fortemente riscritti: non viene inventata una corrispondenza.

## 5. Interfaccia

“Annunci consigliati” è una vista distinta e raggiungibile dai risultati. Mostra titolo, azienda/località note, fonte/data, compatibilità, affidabilità, competenze, tipo di rapporto, contributi al punteggio e dati mancanti. Prove estese sono espandibili. L’azione principale **Apri annuncio** è un link in nuova scheda con `noopener noreferrer`: il test controlla la destinazione senza aprire il sito esterno.

Filtri: Tutti, Alta compatibilità, Da verificare, Interessanti, Già valutati, Non interessanti, motore, campagna e ricerca testuale. “Tutti” nasconde i non interessanti; il filtro dedicato li recupera. Le quattro azioni personali non salvano un contatto nel CRM né cambiano la qualifica. Nessun nuovo framework.

## 6. Risultati offline sulla Campagna 28

'''
 r+=table(['Motore','Schede','Consigliati','Social incompleti','Social recuperati','Alta / media / bassa'],[[k,v['records'],v['recommended'],v['social_incomplete'],v['social_recovered'],' / '.join(str(v['recommended_tiers'].get(t,0)) for t in ('HIGH','MEDIUM','LOW'))] for k,v in m['engines'].items()])
 r+='''
I 13 consigliati hanno tutti un URL individuale apribile dal browser; **non significa che oggi la pagina risponda o che l’annuncio sia aperto**. Tutti i 23 Freelance conservano URL formalmente validi, ma 3 puntano a pagine non specifiche. Fra Freelance: 5 fonti chiaramente negative/ruoli estranei, 3 con dati tecnici insufficienti, 3 URL non specifici e 1 sotto soglia. Le fasce dei consigliati Freelance sono 3 alte, 7 medie, 1 bassa.

Sono presenti due URL duplicati fra motori (Michele Cesario 860/894 e Pietro Agasi 861/886), già non consigliabili per competenze diverse o insufficienti. Nessun duplicato tra i 13 consigliati di questa fixture; la soppressione cross-portale è testata su casi sintetici dichiarati. Non è stato inventato un elenco di venti annunci.

### Annunci consigliati, in ordine di compatibilità

'''
 r+=table(['ID / motore','Titolo e fonte originale','Azienda indicata','Località','Compatibilità','Affidabilità','Stato originale'],[[str(a['id'])+' / '+a['engine'],f"[{a['title']}]({a['original_url']})",a['company']['value'],a['location']['value'],a['compatibility_score'],a['evidence_confidence'],a['official_state']] for a in rec])
 for a in rec:
  r+=f"\n#### {a['id']} — {a['title']}\n\n"
  r+='Motivi: '+'; '.join(d['reason']+f" ({d['points']:+d})" for d in a['score_detail'] if d['points'])+'.\n\n'
  r+='Rapporto: '+a['relationship']['label']+(' — dichiarato nel blocco originale, apertura da confermare.' if a['relationship']['verified_on_original'] else ' — non confermato sulla pagina originale.')+'\n\n'
  r+='Da verificare: '+'; '.join(a['missing'])+'\n'
 r+='''
Le prime piste sono Understack (87, affidabilità media), il risultato Creative Retail Visual Design (77, nome suggerito dall’URL, affidabilità bassa), XWP (77, bassa) e SuiteFit (77, bassa). Internetimage è meno in alto (70), ma ha identità e sede in Veneto corroborate: il contratto resta sconosciuto. Il punteggio tecnico non ordina da solo la facilità reale di ottenere una commessa.

Attenzioni concrete: Dritara ed Emira Digital compaiono come soggetti diversi nei metadati della scheda 871; l’attribuzione va chiarita. ESA/Etinars 888 conserva la data originale 05/12/2025 e una penalità per età, senza annullare lo stato storico REJECTED; non è dichiarata aperta. IT Partner 858 ha punteggio basso e ultimo accesso HTTP 404, esplicitamente mostrato: il link salvato non certifica raggiungibilità. Le richieste su manutenzione possono essere annunci professionali interessanti, senza diventare progetti di rifacimento da 2.000 €.

### Esiti di tutti i record non consigliati

'''
 r+=table(['ID','Motore','Titolo','Motivo'],[[a['id'],a['engine'],a['title'],a['exclusion']] for a in m['evaluations'] if not a['recommended'] and a['engine']!='WEBSITE_REBUILD'])
 r+='''
## 7. Internetimage, Understack e Cosmico

Internetimage 856: descrizione consultiva corretta in “Ricerca di un profilo tecnico; contratto e disponibilità attuale da verificare.” Non viene più affermata la natura esterna; un rapporto non verificato impedisce anche la promozione consultiva a READY. La revisione storica resta NEEDS_REVIEW.

Understack 857: la descrizione distingue sito apparentemente aziendale da fonte terza, senza verificare automaticamente titolare, sede, recapito o apertura. Il risultato può essere consigliato con affidabilità media, ma resta RESEARCH_REQUIRED commercialmente e NEEDS_REVIEW ufficialmente.

Cosmico 797: resta irrisolto il soggetto del publisher. Il ruolo principale è SAP; non diventa un annuncio consigliato soltanto perché contiene “full stack” e “freelance”. Nessuna identità è forzata.

## 8. Browser: diagnosi separata

I quattro audit storici hanno tutti riusato il documento pendente: non è mancata l’attivazione della 4.3. Restano timeout DOM/rendering, dipendenze pendenti e, in alcuni casi, restrizioni robots/errori di accesso. Le attese per dominio si sovrappongono: non vanno sommate come tempo cronologico. Le dipendenze di rendering non possono essere ignorate solo per far risultare completo il controllo. Il codice già distingue tracking/media opzionali e risorse necessarie, verifica font e document.readyState e annulla i finding se l’audit globale non è completo.

'''
 r+=table(['Scheda','Sito','Durata ms','Riuso documento','Audit completo','Limiti'],[[b['id'],b['company'],b['elapsed_ms'],b['coverage']['document_reused'],b['coverage']['completed'],', '.join(b['coverage']['failure_codes'])] for b in m['browser']['audits']])
 r+='''
**Nessun incremento del completamento browser è dimostrato o dichiarato.** Non è stato introdotto un workaround che salta CSS/script/font, robots o attese obbligatorie. Nessun timeout, quota o budget è aumentato. Una modifica affidabile al trasporto richiede ulteriori esperimenti controllati: i dati storici non dimostrano che togliere una dipendenza sia sicuro.

Implementata una sintesi consultiva dei viewport: testo DOM acquisito, contenuto visibile/font osservati, rendering verificato oppure mancante, codici d’errore e stato globale. Osservazione parziale non significa controllo certificato. Nessuna modifica ai vecchi audit né alcuna visita live durante i test.

## 9. Integrità, migrazione e recupero

'''
 r+=f"Backup verificato: `{m['backup']['path']}`, ZIP del codice e SQLite compresso con round-trip hash. Integrità SQLite **{m['integrity']['integrity']}**, tutte le **56 tabelle operative invariate**: {m['integrity']['all_tables_unchanged']}. Confronto completo di conteggi e hash logici. Le 81 revisioni e i 100 documenti della fixture coincidono con il database; discrepanze: {len(m['integrity']['fixture_records_mismatched'])}.\n\n"
 r+='La migrazione 65 è stata applicata soltanto a copie temporanee. Il backend attivo non è stato riavviato. Al prossimo avvio l’aggiunta è automatica; nessuna campagna riparte automaticamente. Per recupero, il backup conserva codice e database; il codice precedente può ignorare la tabella aggiuntiva senza eliminarla e senza perdere le nuove revisioni personali.\n\n## 10. Test eseguiti\n\n'
 for k,t in m['tests'].items():
  if k!='ui':r+=f"- {k}: {t['count']} test, {t['seconds']} s, {'OK' if t['passed'] else 'IN CORSO / NON CONCLUSO'}, `{t['file']}`.\n"
 r+='''- Chromium locale su 1440 e 390 px: 13 schede, link, origine delle prove, contratto sconosciuto, filtri, revisione persistita dopo reload, passaggio alla vista commerciale; nessun overflow o errore JavaScript.
- HTTP locale: Host/Origin/CSRF, revisione inesistente, azione non autorizzata, nessuna promozione o scrittura CRM.
- Fixture reale separata dai test sintetici: fonte LinkedIn incompleta, contratto nel solo snippet, dipendente, SAP, duplicazione tra portali, progetti distinti della stessa azienda, venditore, data ignota/futura, negazioni, link pericolosi/PDF, esclusioni, migrazione ripetuta, storico e quote invariati.
- Suite generale include i controlli browser locali esistenti. Nessuno scraping live. La guardia blocca rete esterna, endpoint operativi e scritture ai dati dell’app.
- Suite e test mirati si sovrappongono: non sommare i conteggi come casi unici.

## 11. Regressioni e correzioni durante lo sviluppo

Due primi test hanno rilevato contratto dipendente omesso senza verbo di richiesta nello snippet e perdita della negazione prima di “cerchiamo”. Corretti e ricontrollati. La revisione del campione ha individuato falsi consigli da firme/commenti (Marius Maxim e Andrea Pollaci); il contesto tecnico è ora legato alla richiesta e al ruolo principale. Una località come Firenze non viene più usata come nome aziendale; nomi LinkedIn con suffisso “Jobs” restano indizi, non identità certificate.

Il primo harness UI falliva sul telefono perché la decisione “Interessante” salvata sul desktop era correttamente persistita: il test è stato corretto per riportare esplicitamente lo stato a “Da verificare” prima di esercitare di nuovo l’azione. Nessun reset dei dati reali. Test aggiunti contro fusione di progetti diversi della stessa azienda e date future.

Il collaudo completo ha inoltre rilevato un’aspettativa della fase 3.2 ormai superata: esclusione incondizionata di un annuncio frontend dipendente. Il test ora verifica l’ammissione soltanto per revisione personale (`recommendation_only`), senza stato commerciale assegnato; il nuovo requisito non autorizza a trattarlo come commessa freelance. Suite completa rieseguita dopo l’aggiornamento.

## 12. File modificati

'''
 for f in m['integrity']['changed_baseline_files']+m['integrity']['new_source_files']:r+=f'- `{f}`\n'
 r+='''
Aggiunti anche fixture/README in `tests/fixtures/commercial44/`, log e screenshot locali in `implementation-report/` e i due deliverable della fase. Nessun commit/push.

## 13. Limiti e prossima campagna

- I tredici annunci non sono verificati oggi e non garantiscono freelance, budget, disponibilità o risposta. Zero nuove opportunità commerciali qualificate dalla proiezione.
- Il ranking copre le schede salvate, non crea retroattivamente schede per tutti gli URL esclusi dalla vecchia discovery. Il filtro di ammissione aggiornato vale per future ricerche.
- Limiti geografici e ambiguità dei nomi restano visibili; i segnali remote/contratto nei metadati non sono fatti verificati sulla pagina.
- Nessun aumento di audit completi: il problema browser rimane aperto. Gli outbound restano separati e non diventano annunci.
- Non è stato validato un miglioramento di risposta, candidatura o conversione; servono valutazioni manuali ed esiti reali.

Per utilizzare la funzione: dopo questa fase arrestare la vecchia istanza, avviare `.venv/bin/python app.py`, ricaricare la pagina e scegliere **Annunci consigliati → Campagna attuale**. È possibile rivedere subito la 28 senza spendere crediti. Aprire gli annunci manualmente, poi registrarne interesse o valutazione.

Per una futura prova mantenere i budget e confrontare annunci pertinenti confermati manualmente / annunci aperti, oltre alle qualifiche commerciali separate. Non rilanciare automaticamente una ricerca per riempire un numero: la Campagna 29 **non è stata avviata**.
'''
 (ROOT/'PHASE-4.4-METRICS.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');(ROOT/'PHASE-4.4-REPORT.md').write_text(r)
 print(json.dumps({'recommended':len(rec),'tests':m['tests'],'integrity':m['integrity']['all_tables_unchanged']},ensure_ascii=False))
if __name__=='__main__':build_report()
