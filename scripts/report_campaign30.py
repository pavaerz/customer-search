"""Read-only operational Campaign 30 report. Never invokes providers or starts work."""
import json,sqlite3,contextlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collections import Counter,defaultdict
from datetime import datetime,timezone
from sales.commercial.job_activity import evaluate as activity
from sales.commercial.recommendations import assess as recommend
from sales.commercial.storage import Opportunities
ROOT=Path(__file__).resolve().parents[1]
def counts(xs):return dict(Counter(xs))
def ratio(n,d):return {'numerator':n,'denominator':d,'value':n/d if d else None}
def table(head,rows):
 def clean(v):return str(v if v is not None else 'non disponibile').replace('|',' / ').replace('\n',' ')
 return '\n'.join(['| '+' | '.join(head)+' |','|'+'|'.join('---' for _ in head)+'|']+['| '+' | '.join(clean(v) for v in r)+' |' for r in rows])
def snapshot():
 c=sqlite3.connect('file:'+str(ROOT/'data/sales.sqlite3')+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('pragma query_only=on');c.execute('begin')
 class RO:
  path=ROOT/'data/sales.sqlite3'
  @contextlib.contextmanager
  def connect(self):yield c
 def rows(table):
  result=[dict(r) for r in c.execute('SELECT * FROM '+table+' WHERE campaign_id=30 ORDER BY rowid')]
  for r in result:
   for k in ('body','payload','details'):
    if k in r:r[k]=json.loads(r[k] or '{}')
  return result
 now=datetime.now(timezone.utc).isoformat();campaign=dict(c.execute('SELECT * FROM campaigns WHERE id=30').fetchone());campaign.pop('generation',None);campaign['filters']=json.loads(campaign['filters']);campaign['filters'].pop('deep_plan_token',None)
 previous=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('SELECT id,campaign_id,body FROM commercial_revisions WHERE campaign_id<30 ORDER BY id')]
 items=[dict(r) for r in c.execute('''SELECT o.*,r.body,r.state,r.score,r.campaign_id AS evaluation_campaign_id,r.id AS selected_revision FROM commercial_opportunities o JOIN commercial_revisions r ON r.id=(SELECT max(x.id) FROM commercial_revisions x WHERE x.campaign_id=30 AND x.opportunity_id=o.id)''')]
 for item in items:
  item['body']=json.loads(item['body']);Opportunities(RO()).workflow(item,previous)
  item['activity']=activity(item['body'],item['engine'],now);item['recommendation']=recommend(item,now,include_inactive=True)
 docids=sorted({d for item in items for d in item['body'].get('document_ids',[])})
 documents=[dict(r) for r in c.execute('SELECT * FROM research_documents WHERE id IN (SELECT value FROM json_each(?))',(json.dumps(docids),))]
 for d in documents:d['details']=json.loads(d['details'] or '{}')
 result={'snapshot_at':now,'campaign':campaign,'items':items,'documents':documents,**{t:rows(t) for t in ('research_tasks','commercial_resources','commercial_engine_runs','commercial_discovery','commercial_ai_executions','discovery_operations','research_events')}}
 c.close();return result

def build():
 x=snapshot();cp=x['campaign'];items=x['items'];tasks=x['research_tasks'];traces=x['commercial_discovery'];ops=x['discovery_operations'];ai=x['commercial_ai_executions'];now=x['snapshot_at']
 from scripts.analysis_archive import read_text
 plan=json.loads((ROOT/'implementation-report/campaign30-search-plan.json').read_text());old=json.loads(read_text('analysis-report/CAMPAIGN-29-METRICS.json'))
 taskmap={t['id']:t for t in tasks};querymap={(t['strategy'],t['payload'].get('query')):t for t in tasks if t['kind'] in ('search','resolve')}
 def sid(payload):return payload.get('strategy_id') or payload.get('origin',{}).get('strategy_id')
 def trace_strategy(t):return sid(t['body']) or sid(querymap.get((t['engine'],t['query']),{}).get('payload',{})) or 'UNATTRIBUTED'
 def item_strategy(it):
  d=it['body'].get('discovery',{});return sid(d) or sid(querymap.get((it['engine'],d.get('query')),{}).get('payload',{})) or 'UNATTRIBUTED'
 def plausible(it):return bool(it['body'].get('request_blocks') or it['body'].get('partner_hint')) and it['state']!='REJECTED'
 def verified(it):return bool(it['body'].get('verification',{}).get('request_verified'))
 def new(it):return it['commercial_view'].get('novelty',{}).get('status')=='NEW'
 resources={e:{} for e in cp['filters']['commercial_engines']}
 for r in x['commercial_resources']:resources.setdefault(r['engine'],{})[r['resource']]=r['used']
 credits=sum(r.get('serper_estimated',0) for r in resources.values());provider=sum(r.get('provider_requests',0) for r in resources.values())
 search=[t for t in tasks if t['kind']=='search'];searchops=[o for o in ops if o['kind']=='search'];executed=[t for t in search if t['state']=='done']
 strategies=[]
 for st in plan['available_strategies']:
  if st['engine'] not in resources:continue
  stid=st['id'];ts=[t for t in tasks if sid(t['payload'])==stid];ds=[d for d in traces if trace_strategy(d)==stid];its=[v for v in items if item_strategy(v)==stid];os=[o for o in ops if sid(taskmap.get(o['task_id'],{}).get('payload',{}))==stid]
  strategies.append({'id':stid,'engine':st['engine'],'planned_queries':sum(q['strategy_id']==stid for q in plan['queries']),'assigned_queries':sum(t['kind']=='search' for t in ts),'executed_search_tasks':sum(t['kind']=='search' and t['state']=='done' for t in ts),'distinct_executed_queries':len({t['payload'].get('query') for t in ts if t['kind']=='search' and t['state']=='done'}),'query_cache_receipts':sum(bool(o['details'].get('cache_hit')) for o in os if o['kind']=='search'),'provider_returned_results':sum(o['details'].get('returned_urls',0) for o in os),'trace_appearances':len(ds),'admitted_traces':sum(d['decision']=='admit' for d in ds),'excluded_traces':sum(d['decision']=='exclude' for d in ds),'duplicates_or_memory':sum(d['decision'] in ('duplicate','memory') for d in ds),'new_plausible_requests':sum(new(it) and plausible(it) for it in its),'new_verified_requests':sum(new(it) and verified(it) for it in its),'opportunity_records':len(its),'credits_estimated':sum(o['details'].get('credits_estimated',o['details'].get('credits',0)) or 0 for o in os),'operation_errors':counts(o['status'] for o in os if o['status']!='ok'),'task_failures':counts(t['error'] for t in ts if t.get('error')),'exclusions':counts(d['body'].get('reason') for d in ds if d['decision']=='exclude'),'classifications':counts(it['body'].get('classification') for it in its)})
 totals={'opportunity_records':len(items),'new_opportunity_records':sum(new(i) for i in items),'known_records':sum(i['commercial_view'].get('novelty',{}).get('status')=='ALREADY_SEEN' for i in items),'novelty':counts(i['commercial_view'].get('novelty',{}).get('status') for i in items),'distinct_requests':len({i['commercial_view']['request_key'] for i in items if i['commercial_view'].get('request_key')}),'plausible_requests':sum(plausible(i) for i in items),'verified_requests':sum(verified(i) for i in items),'states':counts(i['state'] for i in items),'commercial_statuses':counts(i['commercial_view']['status'] for i in items),'confirmed_recent_jobs':sum(i['activity']['freshness_status']=='FRESH_CONFIRMED' for i in items),'date_unknown':sum(i['activity']['freshness_status']=='DATE_UNKNOWN' for i in items),'closed':sum(i['activity']['application_status']=='CLOSED_CONFIRMED' for i in items),'geographically_incompatible':sum(i['activity']['geographic_eligibility']=='GEO_INCOMPATIBLE' for i in items),'readiness':sum(i['commercial_view']['status']=='READY_TO_CONTACT' for i in items),'relationships':counts(str(i['body'].get('relationship',{}).get('contract_type','UNKNOWN')) for i in items),'trace_appearances':len(traces),'unique_trace_urls':len({d['url'] for d in traces}),'trace_decisions':counts(d['decision'] for d in traces),'candidate_tasks':sum(t['kind']=='candidate' for t in tasks),'candidate_task_states':counts(t['state'] for t in tasks if t['kind']=='candidate'),'documents':len(x['documents']),'documents_checked_during_campaign':sum(d['checked_at']>=cp['created_at'] for d in x['documents'])}
 evaluations=[]
 for it in items:
  b=it['body'];a=it['activity'];v=it['commercial_view'];evaluations.append({'id':it['id'],'engine':it['engine'],'strategy':item_strategy(it),'title':b.get('title') or b.get('discovery',{}).get('title') or 'Titolo non disponibile','company':b.get('company') or b.get('identity',{}).get('name'),'original_url':b.get('discovery',{}).get('original_url') or b.get('url'),'verified_domain':v.get('official_domain'),'published_at':a.get('published_at'),'freshness':a['freshness_status'],'applications':a['application_status'],'geography':a['geographic_eligibility'],'relationship':b.get('relationship'),'contract':b.get('contract'),'skills':b.get('skills'),'evidence':b.get('evidence',[]),'request_blocks':b.get('request_blocks',[]),'request_verified':verified(it),'plausible':plausible(it),'official_state':it['state'],'classification':b.get('classification'),'commercial_status':v['status'],'novelty':v.get('novelty'),'reason':b.get('reason'),'limits':b.get('limits'),'missing':v.get('missing'),'recommended':it['recommendation']['recommended']})
 manual_review=json.loads((ROOT/'implementation-report/campaign30-review.json').read_text())
 totals['reviewed_needs_review']=sum(e['id'] in {r['id'] for r in manual_review['cases']} and e['official_state']=='NEEDS_REVIEW' for e in evaluations)
 totals['manual_specific_unverified']=sum(r['verdict']=='SPECIFIC_REQUEST_UNVERIFIED' for r in manual_review['cases'])
 totals['manual_standing_collaborations']=sum(r['verdict']=='STANDING_COLLABORATION_TO_REVIEW' for r in manual_review['cases'])
 totals['manual_irrelevant_review_candidates']=sum(r['verdict'] in ('FALSE_POSITIVE_REVIEW_CANDIDATE','OUT_OF_PRIMARY_SCOPE') for r in manual_review['cases'])
 totals['freelance_relationships']=sum(i['body'].get('contract')=='external' for i in items)
 terminal=cp['status'] not in ('running','waiting','stopping');end=cp.get('finished_at') or now;duration=(datetime.fromisoformat(end)-datetime.fromisoformat(cp['created_at'])).total_seconds()
 airesult={'calls':sum(bool(a['attempt']) for a in ai),'statuses':counts(a['status'] for a in ai),'attempt_statuses':counts(a['status'] for a in ai if a['attempt']),'input_tokens':sum(a['input_tokens'] or 0 for a in ai),'output_tokens':sum(a['output_tokens'] or 0 for a in ai),'estimated_cost_usd':sum(a['estimated_cost'] or 0 for a in ai),'skip_reasons':counts(a['reason'] for a in ai if not a['attempt']),'provider_reported_cost_usd':sum(a['reported_cost'] for a in ai if a['reported_cost'] is not None) if any(a['reported_cost'] is not None for a in ai) else None,'errors':[{'id':a['id'],'engine':a['engine'],'status':a['status'],'error':a['body'].get('error')} for a in ai if a['status'] in ('invalid','error')]}
 engine_rows=[]
 for e,res in resources.items():
  its=[i for i in items if i['engine']==e];engine_rows.append({'engine':e,'queries_completed':sum(t['strategy']==e for t in executed),'opportunities':len(its),'new':sum(new(i) for i in its),'states':counts(i['state'] for i in its),'verified_requests':sum(verified(i) for i in its),'recent':sum(i['activity']['freshness_status']=='FRESH_CONFIRMED' for i in its),'resources':res})
 metrics={'campaign_id':30,'phase':'5.0','snapshot_at':now,'terminal':terminal,'campaign':cp,'duration_seconds':duration,'backup':json.loads((ROOT/'implementation-report/campaign30-backup.json').read_text()),'backend':json.loads((ROOT/'implementation-report/campaign30-backend.json').read_text()),'plan':{'strategies':plan['selected_strategies'],'planned_queries':plan['planned_queries'],'limits':plan['maximums']},'queries':{'assigned_tasks':len(search),'completed_tasks':len(executed),'distinct_completed':len({t['payload'].get('query') for t in executed}),'cache_receipts':sum(bool(o['details'].get('cache_hit')) for o in searchops),'network_search_receipts':sum(bool(o['details'].get('network_attempted')) for o in searchops),'details':[{k:t[k] for k in ('id','strategy','state','error')}|{'payload':t['payload']} for t in search]},'provider':{'requests_reserved':provider,'credits_estimated':credits,'credits_actual':None,'balance_checked':False},'ai':airesult,'counts':totals,'engines':engine_rows,'engine_stops':x['commercial_engine_runs'],'strategies':strategies,'unattributed':{'traces':sum(trace_strategy(d)=='UNATTRIBUTED' for d in traces),'items':sum(item_strategy(i)=='UNATTRIBUTED' for i in items)},'evaluations':evaluations,'errors':[{'id':t['id'],'kind':t['kind'],'engine':t['strategy'],'state':t['state'],'error':t['error'],'url':t['payload'].get('url')} for t in tasks if t.get('error')],'events':x['research_events'],'operations':ops,'ratios':{'verified_requests_per_estimated_credit':ratio(totals['verified_requests'],credits),'new_records_per_estimated_credit':ratio(totals['new_opportunity_records'],credits),'duplicate_trace_rate':ratio(sum(d['decision'] in ('duplicate','memory') for d in traces),len(traces))},'comparison29':{'not_controlled_experiment':True,'reason':'Pilot four engines versus Deep three engines; different queries, cache and sources','old_queries':old['counts']['search_tasks_done'],'old_credits':old['provider']['serper_estimated_credits'],'old_new_records':old['counts']['new_opportunity_records'],'old_duration_seconds':old['duration_seconds'],'old_new_per_credit':ratio(old['counts']['new_opportunity_records'],old['provider']['serper_estimated_credits'])},'manual_review':manual_review,'final_checks':json.loads((ROOT/'implementation-report/campaign30-final-checks.json').read_text()) if (ROOT/'implementation-report/campaign30-final-checks.json').exists() else None,'report_external_calls':0,'report_database_writes':0,'metric_definitions':{'plausible':'Original request blocks or partner hint, excluding REJECTED; not verified or active by definition','verified_request':'Saved verification.request_verified; not necessarily full commercial qualification','new':'Operational novelty against preceding revisions; not automatically a new company','estimated_credit':'App reservation/operation ledger; not provider invoice','runtime':'During execution includes leased task time, refunded on normal completion'}}
 out=ROOT
 (out/'CAMPAIGN-30-METRICS.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
 (ROOT/'implementation-report/campaign30-snapshot.json').write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
 r=f'''# Customer Search — Campagna 30 · Deep Search Intelligence 5.0

## 1. Stato {'finale' if terminal else 'provvisorio — ricerca in corso'}

Campagna **30**, stato **{cp['status']}**. {cp['message']}

Snapshot {now}. Arresto previsto del motore Freelance al tetto di 60 candidati; Agenzie e Startup hanno esaurito le strategie disponibili. Non è esaurimento del saldo Serper. Backend lasciato operativo su http://127.0.0.1:8765. Nessuna campagna aggiuntiva, email o candidatura. Ricerca reale autorizzata con Serper e AI Shadow entro i limiti salvati; questo report legge soltanto i dati locali.

## 2. Durata e ambiente

{duration:.1f} secondi {'fino allo stato terminale' if terminal else 'trascorsi, non durata finale'}. Avvio {cp['created_at']}; fine {cp.get('finished_at') or 'non ancora terminata'}. Python 3.13.2, backend 5.0 verificato via /api/state, frontend e API locali HTTP 200. Backup consistente verificato: `{metrics['backup']['database']}`, SQLite integrity ok e hash SHA-256 nel JSON. Nessuna credenziale riportata.

## 3. Motori eseguiti

FREELANCE, AGENCIES, STARTUPS. WEBSITE_REBUILD escluso solo da questa campagna; budget non trasferito.

{table(['Motore','Query concluse','Schede','Nuove','VERIFIED','POTENTIAL','NEEDS_REVIEW','REJECTED','UNVERIFIABLE','Serper stimato'],[(e['engine'],e['queries_completed'],e['opportunities'],e['new'],*(e['states'].get(s,0) for s in ('VERIFIED','POTENTIAL','NEEDS_REVIEW','REJECTED','UNVERIFIABLE')),e['resources'].get('serper_estimated',0)) for e in engine_rows])}

## 4. Strategie eseguite

{sum(s['executed_search_tasks']>0 for s in strategies)} strategie con almeno una query completata, su {len(plan['selected_strategies'])} previste. Una strategia pianificata non è necessariamente stata eseguita. Attribuzione mancante: {metrics['unattributed']['traces']} tracce, {metrics['unattributed']['items']} schede; non ripartita artificialmente.

## 5. Query previste ed eseguite

{plan['planned_queries']} query iniziali nel piano; {len(search)} task discovery assegnati, {len(executed)} completati, {metrics['queries']['distinct_completed']} query testuali distinte completate. {metrics['queries']['cache_receipts']} ricevute discovery da cache; {metrics['queries']['network_search_receipts']} ricevute discovery con richiesta di rete. Paginazione e risoluzione non sono nuove strategie. Piano integrale in [CAMPAIGN-30-SEARCH-PLAN.md](CAMPAIGN-30-SEARCH-PLAN.md).

## 6. Budget previsto ed effettivo

{table(['Motore','Serper / 36','HTTP / 450','Candidati / 60','Browser / 4','Follow-up / 12','Secondi lavoro / 1800'],[(e,*(v.get(k,0) for k in ('serper_estimated','http_reads','candidates','browser_runs','followups','runtime_seconds'))) for e,v in resources.items()])}

Richieste provider prenotate: {provider}; crediti Serper stimati: {credits}/108. Saldo/addebito effettivo non disponibili. AI: {airesult['calls']}/20 invii; costo stimato {airesult['estimated_cost_usd']:.6f}/1 USD; token dichiarati {airesult['input_tokens']} input, {airesult['output_tokens']} output. Costo riportato direttamente dal provider: {airesult['provider_reported_cost_usd']}. Gli eventuali errori possono consumare richieste; il contatore non è il saldo. Le riserve di tempo in corso non equivalgono a tempo già trascorso.

## 7. Risultati per motore

{table(['Motore','Richieste verificate salvate','Annunci recenti confermati','Classificazioni'],[(e['engine'],e['verified_requests'],e['recent'],json.dumps(e['states'])) for e in engine_rows])}

Annuncio consigliato, richiesta verificata e opportunità VERIFIED sono misure diverse. I contatori seguenti non attribuiscono budget aziendali o probabilità di acquisizione.

## 8. Risultati per strategia

{table(['Strategia','Previste','Query concluse','URL restituiti','Ammessi','Esclusi','Duplicati/memoria','Nuove plausibili','Nuove verificate','Crediti stimati'],[(s['id'],s['planned_queries'],s['executed_search_tasks'],s['provider_returned_results'],s['admitted_traces'],s['excluded_traces'],s['duplicates_or_memory'],s['new_plausible_requests'],s['new_verified_requests'],s['credits_estimated']) for s in strategies])}

'''
 for st in strategies:
  reasons=sorted(st['exclusions'].items(),key=lambda kv:-kv[1])[:3]
  r+=f"- **{st['id']}**: esclusioni principali {reasons or 'nessuna registrata'}; classificazioni {st['classifications'] or 'nessuna scheda valutata'}; errori operazioni {st['operation_errors'] or 'nessuno'}.\n"
 r+=f'''
## 9. Opportunità nuove

{totals['opportunity_records']} schede complessive; {totals['new_opportunity_records']} nuove secondo la memoria commerciale, {totals['known_records']} già note. Ripartizione completa novità: {totals['novelty']}. Richieste distinte per chiave commerciale: {totals['distinct_requests']}. “Nuova scheda” non certifica una nuova azienda, una richiesta aperta o un cliente acquisito.

## 10. Opportunità verificabili

Richieste plausibili secondo il classificatore (prima della revisione manuale): {totals['plausible_requests']}; request_verified: {totals['verified_requests']}; VERIFIED: {totals['states'].get('VERIFIED',0)}; POTENTIAL: {totals['states'].get('POTENTIAL',0)}; READY_TO_CONTACT: {totals['readiness']}. La plausibilità automatica qui significa blocco originale o indizio partner conservato, escludendo REJECTED; non dimostra apertura/compatibilità completa. Revisione di tutte le {totals['reviewed_needs_review']} schede NEEDS_REVIEW: {totals['manual_irrelevant_review_candidates']} non utilizzabili per questa ricerca, {totals['manual_specific_unverified']} richieste specifiche ancora non verificabili e {totals['manual_standing_collaborations']} collaborazione continuativa da approfondire. Queste tre piste non sono opportunità qualificate.

## 11. Attualità e geografia

Recenti confermati: {totals['confirmed_recent_jobs']}; data sconosciuta: {totals['date_unknown']}; candidature chiuse: {totals['closed']}; geografia incompatibile: {totals['geographically_incompatible']}. Finestra 14 giorni, con maggiore recenza distinta da disponibilità. Collaborazioni continuative non escluse solo per assenza data. Nessuna data di indicizzazione usata come data originale. Collaborazioni con contratto esterno riconosciuto: {totals['freelance_relationships']} (non equivale a disponibilità attuale). Il campo relazione e le prove di ogni scheda sono nel JSON: non tutte le pagine con “freelance” dimostrano una collaborazione.

## 12. Schede e link originali

Tutte le schede salvate sono riportate, comprese quelle negative, per non nascondere la qualità della ricerca. Solo il campo “stato” rappresenta la qualifica; i link non sono automaticamente fonti originali verificate.

{table(['ID','Motore / strategia','Titolo / soggetto','Stato','Attualità / geografia','Fonte trovata'],[(e['id'],e['engine']+' / '+e['strategy'],str(e['title'])+' / '+str(e['company']),e['official_state'],e['freshness']+' / '+e['geography'],'['+str(e['id'])+']('+str(e['original_url'])+')') for e in evaluations])}

'''
 for e in evaluations:
  if e['plausible'] or e['freshness']=='FRESH_CONFIRMED' or e['official_state'] in ('VERIFIED','POTENTIAL','NEEDS_REVIEW'):
   proofs=e['evidence'][:3]
   r+=f"### Scheda {e['id']} — {e['title']}\n\nSoggetto: {e['company']}. Strategia: {e['strategy']}. Fonte: {e['original_url']}. Pubblicazione: {e['published_at'] or 'sconosciuta'}. Candidature: {e['applications']}. Geografia: {e['geography']}. Contratto: {e['contract']}. Competenze: {e['skills']}. Stato: {e['official_state']} / {e['classification']}. Novità: {e['novelty']}.\n\nMotivo: {e['reason']}. Mancanze: {e['missing']}. Limiti: {e['limits']}.\n\n"
   for proof in proofs:r+='- Prova salvata: '+str(proof.get('quote',''))[:700]+' — '+str(proof.get('url'))+'\n'
 r+=f'''
## 13. Errori e blocchi

{table(['Motore','Stato','Motivo'],[(e['engine'],e['state'],e['error']) for e in x['commercial_engine_runs']])}

{table(['Task','Motore','Stato','Errore'],[(e['id'],e['engine'],e['state'],e['error']) for e in metrics['errors']])}

Errori AI: {airesult['errors'] or 'nessuno registrato'}. Invii evitati/fallback locali: {airesult['skip_reasons']}. Errori di accesso non sono difetti del sito né prove di disinteresse. I limiti di budget sono condizioni previste; non sono un saldo Serper esaurito. Nessun aumento dei limiti, riavvio automatico della campagna o aggiramento di restrizioni.

## 14. Duplicati e memoria

Tracce: {len(traces)}, URL distinti: {totals['unique_trace_urls']}. Decisioni: {totals['trace_decisions']}. Tasso duplicate/memory: {metrics['ratios']['duplicate_trace_rate']}. Ripetizioni di traccia non equivalgono necessariamente a aziende duplicate. Riutilizzo documenti: {totals['documents_checked_during_campaign']} documenti consultati durante la campagna su {totals['documents']} associati; gli altri sono prove precedenti, non nuove letture.

## 15. Confronto con Campagna 29

{table(['Misura','29 Pilot / quattro motori','30 Deep / tre motori'],[('Query discovery completate',old['counts']['search_tasks_done'],len(executed)),('Crediti Serper stimati',old['provider']['serper_estimated_credits'],credits),('Schede nuove',old['counts']['new_opportunity_records'],totals['new_opportunity_records']),('VERIFIED',old['counts']['states_latest_per_opportunity'].get('VERIFIED',0),totals['states'].get('VERIFIED',0)),('Durata secondi',round(old['duration_seconds'],1),round(duration,1)),('Nuove schede/credito',metrics['comparison29']['old_new_per_credit'],metrics['ratios']['new_records_per_estimated_credit'])])}

Confronto descrittivo, non esperimento controllato: cambiano budget, motori, query, cache e fonti; soprattutto manca outbound nella 30. Nuove schede/credito non misura clienti o qualità. Il report 29 conserva 0 annunci recenti confermati e 0 opportunità pronte al contatto. Richieste verificate/credito nella 30: {metrics['ratios']['verified_requests_per_estimated_credit']}.

## 16. Valutazione della nuova discovery

**Il miglioramento commerciale non è dimostrato.** La copertura è più ampia, ma i risultati salvati non contengono richieste qualificate e la revisione mostra rumore residuo sostanziale. Le metriche positive del benchmark offline non possono essere estese a questa campagna reale.

Revisione separata delle evidenze salvate, senza cambiare il database:

{table(['Scheda','Esito revisione','Motivo'],[(v['id'],v['verdict'],v['reason']) for v in manual_review['cases']])}

La copertura effettiva va valutata sulle strategie con query concluse, non sul numero pianificato. {totals['verified_requests']} richieste verificate e {totals['readiness']} pronte al contatto sono i risultati salvati a questo snapshot; non si riempiono le classificazioni positive. {'La ricerca è ancora in corso: nessuna conclusione definitiva sul rendimento.' if not terminal else 'Lo stato terminale non garantisce copertura completa: leggere i motivi di arresto dei singoli motori.'}

## 17. Limiti

Dati da fonti accessibili: identità, date, apertura e contratto possono restare sconosciuti. Le fonti social non sono state consultate con account autenticati. Nessun contatto effettuato, nessuna conversione misurata. Budget AI e crediti sono contatori/stime dell’app, non fattura provider. Gli errori e le esclusioni complete sono nel JSON. Nessuna correzione al motore applicata durante l'esecuzione per forzare i risultati.

## 18. Raccomandazioni e controllo successivo

{'Non riavviare o duplicare la campagna. Aprire l’app e attendere lo stato terminale; rieseguire il report per uno snapshot aggiornato.' if not terminal else 'Non creare automaticamente una nuova campagna. Rivedere prima le prove delle schede pertinenti e i motivi di scarto per strategia.'} Distinguere richiesta aperta, collaborazione continuativa e semplice competenza tecnica. Tre correzioni proposte sulla base delle prove: (1) separare richieste attuali da testimonianze di progetti consegnati e pagine che vendono servizi; (2) segmentare i listing e attribuire ogni ruolo al vero committente, escludendo prima della coda backend/security/3D e presenza obbligatoria estera; (3) distinguere collaborazione continuativa da annuncio datato e verificare il remoto in relazione al lavoro, evitando che sede aziendale o frasi generiche sull’Europa determinino da sole la geografia. Queste correzioni non sono state implementate durante la campagna. Prima di aumentare budget, validarle con i casi reali qui documentati. Nessuna email/candidatura autorizzata.

App: http://127.0.0.1:8765. Stato: `GET /api/campaigns/30`. Rigenerazione read-only: `.venv/bin/python -B scripts/report_campaign30.py`. Log operativo: `data/research-logs/campaign-30.log`. Le tre consegne sono questo report, `CAMPAIGN-30-METRICS.json`, `CAMPAIGN-30-SEARCH-PLAN.md`.
'''
 (out/'CAMPAIGN-30-REPORT.md').write_text(r)
 print(json.dumps({'id':30,'status':cp['status'],'terminal':terminal,'queries':len(executed),'credits_estimated':credits,'new_records':totals['new_opportunity_records'],'verified_requests':totals['verified_requests'],'recent':totals['confirmed_recent_jobs'],'ai_calls':airesult['calls']},ensure_ascii=False))
if __name__=='__main__':build()
