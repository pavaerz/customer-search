"""Read-only operational Campaign 31 report. Never invokes providers or starts work."""
import json,sqlite3,contextlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collections import Counter,defaultdict
from datetime import datetime,timezone
from sales.commercial.job_activity import evaluate as activity
from sales.commercial.recommendations import assess as recommend, rank
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
  result=[dict(r) for r in c.execute('SELECT * FROM '+table+' WHERE campaign_id=31 ORDER BY rowid')]
  for r in result:
   for k in ('body','payload','details'):
    if k in r:r[k]=json.loads(r[k] or '{}')
  return result
 now=datetime.now(timezone.utc).isoformat();campaign=dict(c.execute('SELECT * FROM campaigns WHERE id=31').fetchone());campaign.pop('generation',None);campaign['filters']=json.loads(campaign['filters']);campaign['filters'].pop('deep_plan_token',None)
 previous=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('SELECT id,campaign_id,body FROM commercial_revisions WHERE campaign_id<31 ORDER BY id')]
 items=[dict(r) for r in c.execute('''SELECT o.*,r.body,r.state,r.score,r.campaign_id AS evaluation_campaign_id,r.id AS selected_revision FROM commercial_opportunities o JOIN commercial_revisions r ON r.id=(SELECT max(x.id) FROM commercial_revisions x WHERE x.campaign_id=31 AND x.opportunity_id=o.id)''')]
 for item in items:
  item['body']=json.loads(item['body']);Opportunities(RO()).workflow(item,previous)
  item['activity']=activity(item['body'],item['engine'],now);item['recommendation']=recommend(item,now,include_inactive=False)
 ranked={r['id']:r for r in rank(items,now,include_inactive=False)}
 for item in items:item['recommendation']=ranked[item['id']]
 docids=sorted({d for item in items for d in item['body'].get('document_ids',[])})
 documents=[dict(r) for r in c.execute('SELECT * FROM research_documents WHERE id IN (SELECT value FROM json_each(?))',(json.dumps(docids),))]
 for d in documents:d['details']=json.loads(d['details'] or '{}')
 result={'snapshot_at':now,'campaign':campaign,'items':items,'documents':documents,**{t:rows(t) for t in ('research_tasks','commercial_resources','commercial_engine_runs','commercial_discovery','commercial_ai_executions','discovery_operations','research_events')}}
 c.close();return result

def build():
 x=snapshot();cp=x['campaign'];items=x['items'];tasks=x['research_tasks'];traces=x['commercial_discovery'];ai=x['commercial_ai_executions']
 from scripts.analysis_archive import read_text
 old=json.loads(read_text('CAMPAIGN-30-METRICS.json'))
 audit_path=ROOT/'implementation-report/campaign31-review.json'
 audit=json.loads(audit_path.read_text()) if audit_path.exists() else {'cases':[],'complete':False}
 reviewed={r['id'] for r in audit['cases']}
 def demand(i):return i['body'].get('demand_assessment',{})
 def promoted(i):
  return i['state'] in ('VERIFIED','POTENTIAL','NEEDS_REVIEW') or i.get('commercial_view',{}).get('status') in ('READY_TO_CONTACT','WORTH_CONTACTING','WORTH_REVIEWING') or demand(i).get('level') in ('NEEDS_REVIEW','POTENTIAL','VERIFIED','READY_TO_CONTACT') or bool(i.get('recommendation',{}).get('recommended'))
 resources={e:{} for e in cp['filters']['commercial_engines']}
 for r in x['commercial_resources']:resources.setdefault(r['engine'],{})[r['resource']]=r['used']
 engines=[]
 for e,res in resources.items():
  its=[i for i in items if i['engine']==e]
  engines.append({'engine':e,'states':counts(i['state'] for i in its),'records':len(its),'resources':res,'queries_done':sum(t['kind']=='search' and t['state']=='done' and t['strategy']==e for t in tasks),'reasons':counts(i['body'].get('classification') for i in its),'page_types':counts(demand(i).get('page_type','UNASSESSED') for i in its)})
 search=[t for t in tasks if t['kind']=='search'];ops=x['discovery_operations'];searchops=[o for o in ops if o['kind']=='search']
 counts31={'records':len(items),'states':counts(i['state'] for i in items),'commercial_statuses':counts(i.get('commercial_view',{}).get('status') for i in items),'page_types':counts(demand(i).get('page_type','UNASSESSED') for i in items),'demand_levels':counts(demand(i).get('level','UNASSESSED') for i in items),'exclusion_reasons':counts(i['body'].get('classification') for i in items),'promoted_ids':[i['id'] for i in items if promoted(i)],'promoted_review_missing':[i['id'] for i in items if promoted(i) and i['id'] not in reviewed],'new_records':sum(i.get('commercial_view',{}).get('novelty',{}).get('status')=='NEW' for i in items),'novelty':counts(i.get('commercial_view',{}).get('novelty',{}).get('status') for i in items),'original_documents':len(x['documents']),'candidate_tasks':sum(t['kind']=='candidate' for t in tasks),'deep_candidates':sum(r.get('candidates',0) for r in resources.values()),'traces':len(traces),'raw_results':sum(bool(t['body'].get('appearance_id')) for t in traces),'trace_decisions':counts(t['decision'] for t in traces),'unique_trace_urls':len({t['url'] for t in traces}),'trace_exclusions':counts(t['body'].get('reason') for t in traces if t['decision']=='exclude'),'browser_runs':sum(r.get('browser_runs',0) for r in resources.values())}
 cost={'calls':sum(bool(a['attempt']) for a in ai),'statuses':counts(a['status'] for a in ai),'attempt_statuses':counts(a['status'] for a in ai if a['attempt']),'skip_reasons':counts(a['reason'] for a in ai if not a['attempt']),'input_tokens':sum(a['input_tokens'] or 0 for a in ai),'output_tokens':sum(a['output_tokens'] or 0 for a in ai),'estimated_cost_usd':sum(a['estimated_cost'] or 0 for a in ai),'provider_reported_cost_usd':sum(a['reported_cost'] for a in ai if a['reported_cost'] is not None) if any(a['reported_cost'] is not None for a in ai) else None,'errors':[{'id':a['id'],'status':a['status'],'reason':a['reason'],'error':a['body'].get('error')} for a in ai if a['status'] in ('invalid','error','fallback')]}
 cfg=cp['filters']['commercial']['ai']
 cost['usage_based_estimate_at_configured_rates_usd']=sum(((a['input_tokens'] or 0)*cfg['input_cost_per_million']+(a['output_tokens'] or 0)*cfg['output_cost_per_million'])/1e6 for a in ai if a['attempt'])
 cost['usage_known_calls']=sum(a['attempt'] and a['input_tokens'] is not None and a['output_tokens'] is not None for a in ai)
 cost['ledger_cost_kind']='Conservative app estimate retains reserved upper bound for invalid responses; not provider invoice.'
 counts31['recommended_ids']=[i['id'] for i in items if i['recommendation'].get('recommended')]
 counts31['official_promoted_ids']=[i['id'] for i in items if i['state'] in ('VERIFIED','POTENTIAL','NEEDS_REVIEW')]
 provider={'estimated_serper_credits':sum(r.get('serper_estimated',0) for r in resources.values()),'provider_requests_reserved':sum(r.get('provider_requests',0) for r in resources.values()),'actual_credits':None,'cash_cost':None,'balance_checked':False}
 queries={'completed_tasks':sum(t['state']=='done' for t in search),'distinct_completed':len({t['payload'].get('query') for t in search if t['state']=='done'}),'cache_receipts':sum(bool(o['details'].get('cache_hit')) for o in searchops),'network_receipts':sum(bool(o['details'].get('network_attempted')) for o in searchops),'tasks':[{k:t[k] for k in ('id','strategy','state','error','payload')} for t in search]}
 duration=(datetime.fromisoformat(cp.get('finished_at') or x['snapshot_at'])-datetime.fromisoformat(cp['created_at'])).total_seconds()
 comparison={'same_limits':all(cp['filters'][k]==old['campaign']['filters'][k] for k in ('commercial','work_budget','commercial_engines','regions','mode','max_job_age_days')),'baseline':{'campaign':30,'counts':old['counts'],'provider':old['provider'],'ai':old['ai'],'duration_seconds':old['duration_seconds']},'controlled_AB':False,'limitations':['Le query sono adattive; cambiano fonti, cache, disponibilità e memoria delle campagne precedenti.','La revisione è manuale sulle prove originali salvate, separata dalle etichette del classificatore; non è una valutazione cieca di un secondo operatore.','Contatti, risposte, preventivi e conversioni non sono misurati.'],'manual_baseline30':{'needs_review':10,'false_positive_or_out_of_scope':7,'plausible_unverified':3,'source':'implementation-report/phase51-audit-before.json'}}
 baseline_review=ROOT/'implementation-report/campaign31-baseline30-review.json'
 comparison['independent_baseline30_review']=json.loads(baseline_review.read_text()) if baseline_review.exists() else None
 checks=ROOT/'implementation-report/campaign31-final-checks.json'
 metrics={'campaign_id':31,'phase':'5.1','snapshot_at':x['snapshot_at'],'terminal':cp['status'] not in ('running','waiting','stopping'),'campaign':cp,'duration_seconds':duration,'counts':counts31,'engines':engines,'engine_stops':x['commercial_engine_runs'],'queries':queries,'provider':provider,'ai':cost,'manual_review':audit,'comparison30':comparison,'errors':[{'id':t['id'],'kind':t['kind'],'engine':t['strategy'],'url':t['payload'].get('url'),'error':t['error']} for t in tasks if t.get('error')],'operations':ops,'events':x['research_events'],'evaluations':[{'id':i['id'],'engine':i['engine'],'state':i['state'],'url':i['body'].get('url'),'classification':i['body'].get('classification'),'reason':i['body'].get('reason'),'demand':demand(i),'commercial_view':i.get('commercial_view'),'recommendation':i.get('recommendation')} for i in items],'final_checks':json.loads(checks.read_text()) if checks.exists() else None,'report_external_calls':0,'report_database_writes':0}
 (ROOT/'implementation-report/campaign31-snapshot.json').write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
 (ROOT/'CAMPAIGN-31-METRICS.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
 summary=audit.get('summary','Revisione manuale in corso: nessuna conclusione commerciale definitiva.')
 r=f'''# Customer Search — Campagna 31 · validazione reale Fase 5.1

## Esito

{summary}

Stato **{cp['status']}**: {cp['message']}. Avvio {cp['created_at']}; fine {cp.get('finished_at') or 'ricerca ancora in corso'}. Durata {duration/60:.1f} minuti. Snapshot {x['snapshot_at']}.

## Configurazione e limiti

FREELANCE, AGENCIES, STARTUPS; WEBSITE_REBUILD disattivato. Modalità Deep, stesse regioni della 30. Corrispondenza completa dei limiti salvati: **{comparison['same_limits']}**. AI REMOTE gpt-5.4-mini in Shadow, massimo 20 chiamate e 1 USD stimato. Nessun aumento, acquisto, email o candidatura. Backend riavviato sulla 5.1; backup verificato registrato in `implementation-report/campaign31-backup.json`.

## Risultati per motore

{table(['Motore','Query concluse','Schede','VERIFIED','POTENTIAL','NEEDS_REVIEW','REJECTED','UNVERIFIABLE','Approfondimenti','Serper stimato'],[(e['engine'],e['queries_done'],e['records'],*(e['states'].get(s,0) for s in ('VERIFIED','POTENTIAL','NEEDS_REVIEW','REJECTED','UNVERIFIABLE')),e['resources'].get('candidates',0),e['resources'].get('serper_estimated',0)) for e in engines])}

Le schede sono valutazioni, non aziende utili o commesse. {counts31['raw_results']} apparizioni di risultati provider, {counts31['traces']} tracce totali, {counts31['unique_trace_urls']} URL distinti; {counts31['candidate_tasks']} task candidati, {counts31['deep_candidates']} prenotazioni di approfondimento. Una prenotazione non prova che l'analisi sia terminata. {counts31['original_documents']} documenti salvati. Browser {counts31['browser_runs']}, coerente con WEBSITE_REBUILD disattivato. Query concluse {queries['completed_tasks']}, distinte {queries['distinct_completed']}, risposte dalla cache {queries['cache_receipts']}.

## Confronto con la Campagna 30

{table(['Misura','Campagna 30','Campagna 31'],[
 ('Schede',old['counts']['opportunity_records'],len(items)),
 ('VERIFIED',old['counts']['states'].get('VERIFIED',0),counts31['states'].get('VERIFIED',0)),
 ('POTENTIAL',old['counts']['states'].get('POTENTIAL',0),counts31['states'].get('POTENTIAL',0)),
 ('NEEDS_REVIEW',old['counts']['states'].get('NEEDS_REVIEW',0),counts31['states'].get('NEEDS_REVIEW',0)),
 ('Serper: crediti stimati',old['provider']['credits_estimated'],provider['estimated_serper_credits']),
 ('Chiamate AI',old['ai']['calls'],cost['calls']),
 ('AI: costo stimato USD',old['ai']['estimated_cost_usd'],cost['estimated_cost_usd']),
 ('Durata minuti',round(old['duration_seconds']/60,2),round(duration/60,2))])}

La revisione della 30 aveva trovato **7 falsi positivi o casi fuori ambito su 10 NEEDS_REVIEW** e 3 piste non qualificate (Twine, IOCOS, Prout). Sono piste, non tre richieste già recenti, idonee e contattabili. I risultati offline 5.1 sullo stesso campione sono un test di sviluppo e non vengono sommati alla presente prova reale.

{chr(10).join('- '+v for v in comparison['limitations'])}

## Consumi AI e provider

{cost['calls']} tentativi AI; token input {cost['input_tokens']}, output {cost['output_tokens']}. Il registro dell'app conserva **{cost['estimated_cost_usd']:.6f} USD** come stima prudenziale: per risposte invalide conserva il massimale prenotato, non il consumo calcolato sui token. Usando i token restituiti ({cost['usage_known_calls']} chiamate con uso noto) e le tariffe già configurate, la stima è **{cost['usage_based_estimate_at_configured_rates_usd']:.6f} USD**, senza applicare eventuali sconti cache. Nessuna delle due cifre è una fattura. Costo dichiarato dal provider: {cost['provider_reported_cost_usd'] if cost['provider_reported_cost_usd'] is not None else 'non disponibile'}. Serper {provider['estimated_serper_credits']} crediti stimati: dato contabile dell'app, non saldo verificato o fattura. Un'esecuzione AI saltata non è una chiamata pagata.

{table(['Esito AI','Numero'],cost['statuses'].items())}

{table(['Motivo AI saltata','Numero'],cost['skip_reasons'].items())}

## Revisione indipendente delle opportunità promosse

Inclusi tutti VERIFIED, POTENTIAL, NEEDS_REVIEW e gli ulteriori candidati promossi dal livello commerciale/domanda o dalla raccomandazione. Stato della revisione: **{audit.get('complete',False)}**. ID ancora da revisionare: {counts31['promoted_review_missing']}.

{table(['ID','Verdetto manuale','Richiesta autentica','Recente/attiva','Italia','Collaborazione esterna','Prova e limiti'],[(v['id'],v['verdict'],v.get('authentic_request'),v.get('fresh_active'),v.get('italy_compatible'),v.get('external_collaboration'),v.get('reason')) for v in audit['cases']])}

## Diagnosi: classificazioni, errori e arresto

{table(['Classificazione','Numero'],counts31['exclusion_reasons'].items())}

{table(['Tipo pagina 5.1','Numero'],counts31['page_types'].items())}

{table(['Motore','Stato','Causa'],[(e['engine'],e['state'],e.get('error')) for e in x['commercial_engine_runs']])}

{table(['Errore task','Numero'],counts(t['error'] for t in tasks if t.get('error')).items())}

## Query eseguite

{table(['Motore','Stato','Query'],[(t['strategy'],t['state'],t['payload'].get('query')) for t in search])}

## Schede revisionate e fonti

'''
 for case in audit['cases']:
  r+=f"\n### {case['id']} — {case.get('name','')}\n\nFonte: {case.get('url','')}\n\n{case.get('reason','')}\n\nEvidenza salvata: {case.get('evidence','non disponibile')}\n\nVerdetto: **{case['verdict']}**. {case.get('next_action','')}\n"
 r+='\n## Copertura e confronto manuale a criteri omogenei\n\n'
 r+=table(['Misura revisione 31','Numero'],audit.get('coverage',{}).items())+'\n\n'
 baseline=comparison['independent_baseline30_review']
 if baseline:
  r+=baseline['previous_phase51_count_explanation']+'\n\n'
  r+=table(['ID 30','Esito della rilettura','Motivo'],[(v['id'],v['verdict'],v['reason']) for v in baseline['cases']])+'\n\n'
  r+='Nella rilettura dei 10 NEEDS_REVIEW della 30: 9 presentano controindicazioni documentate; IOCOS è una partnership reale ma con sede fuori dalle regioni scelte. Nella 31: 3/4 presentano controindicazioni, 1/4 è una partnership plausibile non qualificata. Campioni troppo piccoli e selezione diversa: nessuna conclusione statistica di incremento della precisione. Contatti pronti confermati: zero in entrambe.\n'
 r+='\n## Campione degli scarti e dei filtri discovery\n\nCampione ragionato, non casuale e non sufficiente a stimare il richiamo sull’intero web. Le pagine non consultate non possono diventare falsi negativi certi.\n\n'
 r+=table(['ID','Esito','Revisione fonte'],[(v['id'],v['verdict'],v['reason']) for v in audit.get('rejection_sample',[])])+'\n\n'
 r+=table(['URL','Esito','Revisione metadati'],[(v['url'],v['verdict'],v['reason']) for v in audit.get('discovery_exclusion_sample',[])])+'\n'
 r+='''
## Diagnosi e tre interventi prioritari

1. **Unificare ammissione, qualificazione e raccomandazioni su prove dello stesso annuncio.** Le schede 929 e 1057 riportano rispettivamente “Posted 20 days ago” e “3 months ago”, ma restano NEEDS_REVIEW. La 950 dichiara 500 USD. Le raccomandazioni ammettono anche offerte di fornitori (1040, 1056) e un articolo (1055). Servono date relative ancorate all’acquisizione e alla sezione giusta, budget dichiarati e natura del rapporto come controlli condivisi; dato sconosciuto separato da controprova presente. Le quote massime non risolvono questi errori.

2. **Seguire la fonte del committente, evitando deviazioni verso altri annunci e la home del portale.** Da AFM 1053 sono stati seguiti i “Similar jobs” di AJS 1057 e Wobu Fit 1059: l’ancora conteneva già “3 months ago”. Il payload conserva WeAreDevelopers come company. Gli annunci rimandano invece a arc.dev/Indeed: provare il percorso autorizzato dell’annuncio, mantenendo separati committente, editore e dominio ufficiale; niente aggiramento dei blocchi. Sulle agenzie, query “white label” intercettano numerosi venditori: richiedere frasi in cui l’agenzia recluta un collaboratore e permettere una lettura economica delle pagine “lavora con noi” con snippet incompleto.

3. **Rendere utilizzabili le analisi AI, senza indebolire la validazione.** Quattro chiamate, quattro output invalidi: unsupported_actor, invented_quote, temporal_evidence_not_independently_verified, temporal_role_mismatch. Tre ulteriori fallback per evidence_insufficient non hanno chiamato il provider. Alcune prove selezionate riguardano il portale anziché il committente; la richiesta 1033 è visibile ma il classificatore principale non la estrae. Prima di nuove campagne, riprodurre offline queste risposte/prove, correggere attribuzione e citazioni, conservare sconosciuti e rifiutare affermazioni non supportate. In Shadow l’AI non promuove comunque le schede.

Questi sono problemi dimostrati dai dati del test, non correzioni applicate durante la campagna. L’eventuale presenza di commesse perse nelle pagine bloccate resta un’ipotesi. Non è dimostrato che basti aumentare crediti o budget AI.

## Arresto e affidabilità

Freelance si ferma al limite invariato di 24 query distinte; task di paginazione possono portare il numero di ricerche concluse oltre 24. Agenzie e Startup esauriscono i piani disponibili. Lo stato complessivo `blocked` conserva controlli falliti riprendibili: non significa crediti Serper finiti. Nessuna ripresa automatica o seconda campagna è stata avviata.

Confronto del database con il backup pre-campagna: configurazioni, campagne 1–30, loro revisioni/task/eventi/consumi e stati commerciali manuali preservati. Le nuove revisioni della 31 possono aggiornare l’ultima scheda, senza cancellare quelle precedenti. Controlli e hash in `implementation-report/campaign31-final-checks.json`.

## Riproducibilità e limiti

Snapshot e revisione: `implementation-report/campaign31-snapshot.json`, `campaign31-review.json`; rilettura baseline: `campaign31-baseline30-review.json`. Metriche complete: `CAMPAIGN-31-METRICS.json`. Rigenerazione del report in sola lettura: `.venv/bin/python -B scripts/report_campaign31.py`. La revisione legge le prove salvate; non verifica una risposta del committente e non dimostra possibilità di acquisizione o conversioni. Nessuna modifica al motore, ai limiti o alle impostazioni durante il test; nessun commit/push.
'''
 (ROOT/'CAMPAIGN-31-REPORT.md').write_text(r)
 print(json.dumps({'status':cp['status'],'counts':counts31,'ai':cost,'provider':provider},ensure_ascii=False))
 return metrics

if __name__=='__main__':build()
