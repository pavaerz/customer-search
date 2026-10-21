"""Write the four requested offline deliverables from frozen evidence."""
import html,json,re
from pathlib import Path
from replay_commercial51 import ROOT,replay

def pct(v):return 'non calcolabile' if v is None else f'{v*100:.1f}%'
def safe(v):return html.escape(str(v if v is not None else 'UNKNOWN')).replace('|','\\|').replace('\n',' ')
def main():
 m,rows=replay();byid={r['id']:r for r in rows}
 integrity_path=ROOT/'implementation-report/phase51-integrity.json'
 integrity=json.loads(integrity_path.read_text()) if integrity_path.exists() else {}
 log=ROOT/'implementation-report/phase51-tests-final.txt';text=log.read_text() if log.exists() else ''
 count=re.search(r'Ran (\d+) tests in ([\d.]+)s',text)
 m['tests_passed']=int(count[1]) if count and re.search(r'\nOK\s*$',text) else None
 m['targeted_checks']={'log':'implementation-report/phase51-final-targeted.txt','note':'Additional targeted checks after final refinements; overlap with full suite, do not sum.'}
 targeted=ROOT/m['targeted_checks']['log'];t=targeted.read_text() if targeted.exists() else '';n=re.search(r'Ran (\d+) tests',t)
 m['targeted_checks']['passed']=int(n[1]) if n and re.search(r'\nOK\s*$',t) else None
 m['tests_failed']=0 if m['tests_passed'] else None;m['test_log']='implementation-report/phase51-tests-final.txt'
 m['preservation']={k:integrity.get(k) for k in ('integrity','all_tables_unchanged','different_tables','fixture_records_mismatched')}
 m['ui']=json.loads((ROOT/'implementation-report/phase51-ux.json').read_text()) if (ROOT/'implementation-report/phase51-ux.json').exists() else None
 m['shadow_mock_calls']=3;m['browser_diagnosis']='Only WEBSITE_REBUILD schedules browser audits; absent from campaign 30. No saved rendering gap requiring a new public browser trigger.'
 m['ready_for_manual_campaign']=bool(m['tests_passed'] and integrity.get('all_tables_unchanged') and m['ui'])
 (ROOT/'PHASE-5.1-METRICS.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 (ROOT/'implementation-report/phase51-replay.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 bench=['# Fase 5.1 — Benchmark reale offline','',
 'Corpus congelato: **111 schede**, non 111 aziende uniche. 70 schede dispongono della pagina acquisita; 41 hanno soltanto indizi o accesso incompleto. Ci sono 11 ripetizioni dello stesso URL tra le schede. Le fonti non sono state riaperte.',
 '', '## Etichette e denominatori','',
 '**69 Gold, 6 Silver, 36 Unknown.** Gold vale per le dimensioni esplicitamente etichettate, non per tutti i campi della scheda. Silver indica metadata o testo parziale. Unknown e campi null sono esclusi dai denominatori binari. Le vecchie decisioni non sono ground truth.',
 '', 'Etichette fissate prima delle modifiche: `implementation-report/phase51-audit-before.json`. Il corpus e quelle etichette sono inclusi in `tests/fixtures/commercial51/campaign30.json.gz`. La classificazione di riferimento deriva dalla revisione delle evidenze salvate. Il benchmark è di sviluppo sullo stesso corpus: **non è un holdout indipendente**.',
 '', '## Confronto','', '| Misura | Prima | Dopo | Denominatore / limite |','|---|---:|---:|---|']
 for title,key in [('Domanda riconosciuta','buyer_demand'),('Piste commerciali da verificare','commercial_lead'),('Compatibilità tecnica','technical_fit'),('Opportunità qualificate','qualified')]:
  a=m['metrics'][key]['baseline'];b=m['metrics'][key]['new']
  bench.append(f"| {title}: precision | {pct(a['precision'])} | {pct(b['precision'])} | {a['tp']}/{a['tp']+a['fp']} → {b['tp']}/{b['tp']+b['fp']}; {a['labelled']} etichette utilizzabili |")
  bench.append(f"| {title}: recall | {pct(a['recall'])} | {pct(b['recall'])} | {a['tp']+a['fn']} positivi etichettati |")
 a=m['metrics']['geography']['baseline'];b=m['metrics']['geography']['new'];bench.append(f"| Geografia: accordo con revisione | {a['correct']}/7 | {b['correct']}/7 | 4 ruoli onsite USA e 3 piste con accessibilità non provata |")
 bench += ['', '**Il 100% dopo significa 3 piste corrette su 3 proposte in questo piccolo corpus. Non dimostra precisione futura né capacità di acquisire clienti.** VERIFIED/POTENTIAL restano zero: non esiste un positivo qualificato di riferimento, quindi precision e recall di quella classe sono null.',
 '', 'Per la domanda, il confronto usa il precedente `commercial_intent.commercial_role` rispetto al nuovo riconoscimento contestuale. Per la pertinenza tecnica, la baseline usa presenza di competenze riconosciute: è un proxy dichiarato, non un classificatore 5.0 equivalente. Per le piste, la baseline sono le classi NEEDS_REVIEW/POTENTIAL/VERIFIED; la nuova decisione è conservazione di una richiesta originale specifica o di un invito continuativo.',
 '', '### Tipo pagina: distinguere copertura da errore','',
 'La 5.0 non aveva la stessa tassonomia. La corrispondenza conservativa di `source_kind` permette 4 classificazioni confrontabili su 69; tutte corrette. La 5.1 ne permette **66 su 69**, tutte corrette, con tre astensioni: 978, 984, 1010. Non si tratta di 65 falsi positivi precedenti: gran parte del vecchio contratto non rappresentava questa informazione.',
 '', f"Unknown sul totale 111: {pct(m['unknown_rate']['baseline_page_type'])} → {pct(m['unknown_rate']['new_page_type'])}. La riduzione dei falsi positivi non dipende dall’aumento degli Unknown.",
 '', '### Quote e costi','',
 '111 prenotazioni candidati nella baseline. Il replay segnala 70 pagine escludibili prima dell’approfondimento; le 41 conservate includono 38 casi senza richiesta originale confermata e 3 piste. **Non sono 70 crediti risparmiati**: molte esclusioni richiedono ancora una prima lettura. Le letture, query e latenze controfattuali non sono misurate. I limiti restano invariati.',
 '', '### Resa delle strategie sui candidati già salvati','', '| Strategia | Schede | Escluse | Richieste conservate | Qualificate |','|---|---:|---:|---:|---:|']
 for k,v in sorted(m['strategy_yield'].items()):bench.append(f"| {k} | {v['candidates']} | {v['excluded']} | {v['retained_requests']} | 0 |")
 bench += ['', 'Due schede non sono attribuibili univocamente a una strategia nella traccia disponibile. La resa non equivale a risultati per query: segue schede e motori, include duplicazioni e follow-up. Nessuna strategia è stata aggiunta o dichiarata efficace commercialmente.',
 '', '### Errori operativi','', f"La Campagna 30 contiene {m['operational_errors']['historical_failed_tasks']} task falliti: restrizioni robots/HTTP, pagine troppo grandi e identità non risolta. Non sono stati riprovati e non sono dichiarati risolti. Nessun bypass di autenticazione, robots, CAPTCHA o TLS.",
 '', '## Riproduzione','', '```bash','PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/replay_commercial51.py','PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B scripts/report_commercial51.py','PYTHONPATH=implementation-report/offline-test-guard:.:tests .venv/bin/python -B -m unittest test_commercial51','```','', 'Il replay legge solo il corpus compresso, senza database operativo e senza rete. Il JSON per ciascuno dei 111 casi è `implementation-report/phase51-replay.json`. Le schede storiche rimangono immutate.']
 (ROOT/'PHASE-5.1-BENCHMARK.md').write_text('\n'.join(bench)+'\n')
 cases=['# Fase 5.1 — Casi reali','', 'Revisione offline delle 111 schede. Nessun contenuto mancante è stato inventato. Fatti, riferimenti e limiti sono separati dalle decisioni del replay.', '', '## Casi obbligatori','']
 notes={927:'È un elenco di React Native, non una domanda individuale. Nessun buyer attribuito al portale.',965:'Il contenitore dei risultati non è un incarico WooCommerce; il ruolo individuale 969 viene valutato separatamente.',969:'La descrizione originale richiede C++/Unreal/Unity/3D e presenza a Jacksonville. Entrambe le incompatibilità sono esplicite.',973:'CSB vende assistenza per aprire startup a Cipro. I riferimenti a team remoti e UE descrivono clienti-tipo, non condizioni di un incarico.',975:'Lista di ruoli diversi, inclusa cybersecurity. I contratti di una voce non si trasferiscono alle altre.',998:'La testimonianza dice che il fornitore ha consegnato il negozio. È progetto completato, non domanda attuale.',929:'Domanda WordPress/Figma di un individuo su Twine. Twine è editore; buyer sconosciuto. “Fully remote” non dimostra accessibilità dall’Italia. Nessuna data originale verificata.',931:'Invito reale alla rete freelance IOCOS. Identità verificata, ma nessuna commessa specifica o disponibilità attuale confermata. La sede in Calabria non dimostra il luogo obbligatorio di lavoro: i filtri territoriali e la modalità remota restano da controllare.',950:'Prout Enterprises LLC è il soggetto dichiarato, careers.uw.edu è editore. Data originale 2026-10-07 conservata. Accessibilità dall’Italia e contratto non provati. Il testo salvato aggiunge “Budget: $500 fixed price” e Wix Studio: compatibilità economica/ambito non confermata, nessuna equivalenza inventata con la soglia interna di 2.000 €.',974:'Ruolo .NET con componente frontend presente: non viene inventata una totale assenza di frontend. Il vincolo onsite Jacksonville è sufficiente a escluderlo.'}
 for id,note in notes.items():
  r=byid[id];n=r['new'];cases += [f'### {id}', '',f"Fonte salvata: [{safe(r['url'])}]({r['url']})",'',note,'',f"Prima: **{r['baseline']['state']} / {r['baseline']['classification']}**. Dopo: **{n['page_type']}**, {'esclusa' if n['excluded'] else n['level']}. Motivi: {', '.join(n['reasons'])}.",'',f"Prova disponibile: {safe((r['audit']['excerpts'] or ['Nessun estratto originale'])[0][:400])}",'']
 cases += ['## Audit completo (111 schede)','', 'Ogni scheda riporta i ruoli separati, fonte, richiesta, attualità, compatibilità, attribuzione, duplicazione e limiti. Le osservazioni storiche di contratto/data non costituiscono da sole etichette Gold.', '']
 for r in rows:
  a=r['audit'];n=r['new'];ref=r['reference']
  cases += [f"### Scheda {r['id']} · {r['engine']} · {ref['certainty']}",'',f"[{safe(r['url'])}]({r['url']})",'',f"- Fonte originale disponibile: {'sì' if a['original_available'] else 'no'}. Tipo: {ref['page_type']} (riferimento); {n['page_type']} (replay).",f"- Editore: {safe(n['actors']['publisher'])}. Buyer: {safe(n['actors']['buyer'])}. Stato attribuzione: {n['actors']['buyer_status']}.",f"- Supplier: {safe(n['actors']['supplier'])}. Recruiter: {safe(n['actors']['recruiter'])}. Aggregator: {safe(n['actors']['aggregator'])}. Soggetti menzionati: {safe(', '.join(a['mentioned_entities']) or 'UNKNOWN')}.",f"- Richiesta specifica: {safe(a['specific_request'])}. Contratto osservato: {safe(a['contract'])}; non equivale a contratto verificato del buyer.",f"- Attualità: {n['freshness']['status']}; data: {safe(n['freshness']['published_at'])}; fonte data: {safe(n['freshness']['basis'])}. Invito continuativo: {n['freshness']['standing_exempt']}.",f"- Pertinenza tecnica: {n['technical_fit']['status']}; geografia: {n['geography']['status']}. Livello prove: {n['evidence_level']}.",f"- Duplicato URL della scheda: {safe(a['duplicate_of'])}. I ruoli e i contratti non vengono uniti tra schede.",f"- Baseline: {r['baseline']['state']} / {r['baseline']['classification']}. Replay: {'esclusa' if n['excluded'] else n['level']}; {', '.join(n['reasons'])}.",f"- Motivo del riferimento: {ref['reason']} Incertezze: {a['resolvable_unknowns']}.",f"- Estratto disponibile: {safe((a['excerpts'] or ['UNKNOWN: contenuto originale non salvato'])[0][:250])}.",'']
 (ROOT/'PHASE-5.1-REAL-CASES.md').write_text('\n'.join(cases)+'\n')
 changed=integrity.get('changed_baseline_files',[])+integrity.get('new_source_files',[])+['tests/fixtures/commercial51/campaign30.json.gz','tests/fixtures/commercial51/README.md']
 report=f'''# Customer Search — Fase 5.1

Implementazione offline della verifica della domanda, compatibile con l’orchestrazione 5.0. Analizzate tutte le **111 schede della Campagna 30** prima delle modifiche; 10 NEEDS_REVIEW, 57 REJECTED e 44 UNVERIFIABLE. Nessuna Campagna 31 avviata.

## Risultato misurato

Dei dieci NEEDS_REVIEW, **sette erano falsi positivi dimostrabili**. Il replay elimina questi sette casi e conserva Twine, IOCOS e Prout come piste con verifiche mancanti. Nessuna viene promossa a VERIFIED/POTENTIAL/READY_TO_CONTACT.

La precisione delle piste sul campione etichettato passa da **3/10 a 3/3**, con recall 3/3 in entrambi i casi. Si tratta di tre positivi di sviluppo, non di una misura di efficacia commerciale o di precisione futura. I denominatori completi e le astensioni sono in [benchmark](PHASE-5.1-BENCHMARK.md). Il tipo pagina ha 66 classificazioni corrette su 69 etichette Gold e tre astensioni. Cinque discrepanze geografiche su sette casi etichettati sono corrette.

## Cause dimostrate e correzioni

| Problema | Causa | Correzione | Gravità |
|---|---|---|---|
| Elenco scambiato per richiesta | Keyword nel contenitore e primo JobPosting usato come titolo pagina | Titolo pagina separato dal titolo ruolo, cardinalità JobPosting e struttura lista prima dell’identità | Alta |
| Servizi / testimonial scambiati per domanda | Frasi “looking for” senza direzione temporale/commerciale | Domanda, offerta, progetto concluso e invito continuativo separati | Alta |
| Editore usato come buyer | Proprietario del dominio trasferito alle prove della richiesta | Publisher/buyer/supplier/recruiter/aggregator/menzionati separati; buyer sconosciuto resta nullo | Alta |
| C++/Unreal compatibile perché “developer” | Compatibilità tecnica troppo generale | Ruolo e responsabilità delimitati; componente frontend significativa preservata | Alta |
| Jacksonville e “remote” | Geografia incompleta o presa fuori dalla richiesta | Vincoli originali, onsite USA, remote EU/worldwide/EMEA/unspecified distinti | Alta |
| FREELANCE fermo a 60 | Quota addebitata prima di leggere e filtrare la pagina | Riserva persistente una volta per approfondimento, dopo il primo prefiltro | Alta |
| AI 0 | Identità verificata richiesta anche per interpretazione e contesto perso nella selezione | Gate semantico separato; prove della stessa richiesta e invito/competenze prioritari | Media |

Le correzioni sono in `sales/commercial/demand.py` e integrate nel prefiltro, nell’ispezione, nell’orchestrazione, nella selezione delle prove, nelle raccomandazioni e nella vista commerciale. Non sono regole basate sugli ID del benchmark o whitelist dei nove domini.

## Nuovo contratto e compatibilità

- Tassonomia esplicita: BUYER_DEMAND, SUPPLIER_OFFER, COMPLETED_PROJECT, JOB_AGGREGATION, INDIVIDUAL_JOB, EDITORIAL_CONTENT, DIRECTORY, STANDING_COLLABORATION, UNKNOWN.
- `demand_assessment` è un livello additivo. Gli enum pubblici VERIFIED/POTENTIAL/NEEDS_REVIEW/REJECTED/UNVERIFIABLE restano gli stessi. Il livello aggiuntivo non promuove autonomamente una scheda.
- Nuove campagne: `demand_version=5.1`; strategie `search_version=5.0` conservate. Campagne precedenti e loro quote non sono migrate. Il codice non ricalcola le revisioni storiche.
- Evidenza 0–4 distinta da readiness. Una pagina ufficiale di vendita non è livello 4; un invito continuativo attribuibile può avere prova forte senza diventare commessa aperta.
- Fonte originale, data, relazione contrattuale e geografia sono verifiche indipendenti. Data dell’indice e sola parola “remote” non provano attualità/accessibilità. Limite 14 giorni per singoli annunci; inviti continuativi esenti dalla sola scadenza temporale.
- CRM, esclusioni manuali, contatti, revisioni, API, impostazioni, prevenzione PDF e protezioni HTTP restano operative. Tre test precedenti sono mantenuti come regressioni di campagne storiche; nuove prove coprono la nuova semantica.

## Contatori e arresto

`RAW_RESULTS` indica apparizioni ricevute dal provider (ricevute persistenti); `SCREENED_RESULTS` quelle passate dal prefiltro; `DERIVED_RESULTS` separa i collegamenti derivati; `ADMITTED_CANDIDATES` i task candidati; `DEEP_REVIEW_CANDIDATES` le riserve di approfondimento. Non sono quattro conteggi di aziende.

Nelle nuove campagne il limite `max_candidates_per_engine` continua a esistere, con lo stesso valore configurato: viene consumato da `deep_review_slot`, dopo il controllo della prima pagina e prima delle letture di identità e approfondimento. Il marker `_deep_review_reserved` è persistente e transazionale: retry/ripresa non lo addebitano due volte. I prefilt ri negativi e i fallimenti di accesso prima dell’approfondimento non consumano quella quota. Il motore si arresta quando la quota è effettivamente piena oppure al raggiungimento di un altro limite. Le campagne vecchie continuano a contare le ammissioni.

Query, paginazione, provider, crediti stimati, HTTP, follow-up, browser, AI e runtime mantengono gli stessi massimi. La coda rimane deduplicata e la discovery mantiene una soglia di lavoro pendente. Nessun loop illimitato né aumento di budget. Le pagine aggregate possono fornire soltanto link osservati a singoli ruoli tecnici pertinenti, soggetti a una nuova valutazione e alle quote esistenti.

## Browser e AI

**Browser 0 non è un difetto dimostrato:** il percorso browser è quello di WEBSITE_REBUILD, escluso dalla Campagna 30. Le evidenze dei nove casi mostrano problemi semantici, non una necessità dimostrata di rendering. Non è stato aggiunto un browser per aggirare robots/login/CAPTCHA o per nascondere errori di accesso.

**AI 0:** la Campagna 30 aveva 82 registrazioni (68 skipped, 14 fallback), zero chiamate. I 61 skip per insufficienza di prova erano dominati dal requisito di identità verificata; altri esiti riguardavano ambiguità, soggetto irrisolto o esclusioni deterministiche. La nuova via ammette l’interpretazione di testi originali circoscritti anche con buyer ignoto. Non ammette fonti assenti come prove e non concede autorità di qualificazione.

Tre replay con provider MOCK su Twine, IOCOS e Prout attraversano selezione, gate, prenotazione, risposta e validazione, entro 8.192 token di input, 20 chiamate massime e 1 USD simulato massimo: nessun limite reale cambiato. Le risposte mock mantengono actor null e non modificano il risultato deterministico. Grounding, citazioni, costi, concorrenza e Stop restano controllati. **Chiamate reali OpenAI: 0; Serper: 0; scraping live: 0; spesa: 0.**

## Preservazione

Backup verificato codice/database: `data/backups/phase51`, con integrità SQLite e hash del roundtrip gzip. Manifesto iniziale: `implementation-report/phase51-baseline.json`. Controllo finale: `implementation-report/phase51-integrity.json`.

Integrità: **{integrity.get('integrity','in verifica')}**. Tutte le 58 tabelle immutate: **{integrity.get('all_tables_unchanged','in verifica')}**. Configurazioni, credenziali, budget, Campagna 30 e precedenti non modificati. Nessuna migrazione, commit, push, invio email o candidatura. Backend operativo non riavviato durante questa fase.

## Test

Suite completa: **{m['tests_passed'] if m['tests_passed'] else 'in esecuzione'} test superati**, fallimenti **{m['tests_failed'] if m['tests_failed'] is not None else 'da confermare'}**. Log: `{m['test_log']}`. Controlli mirati finali: **{m['targeted_checks'].get('passed') or 'da confermare'} passati** (in parte sovrapposti, non sommare alla suite). Test specifici in `tests/test_commercial51.py`, inclusi casi reali, tassonomia, identità, geografia, data, limiti, retry/ripresa e AI mock. Suite preesistente include API, sicurezza, CRM, memoria, PDF e deduplicazione.

UI Chromium offline: **1440 e 390 px**, anteprima senza avvio, Deep non preselezionato, invalidazione dell’autorizzazione se cambia il piano, filtri, dossier con testo escaped, contatori separati, nessun overflow o errore JavaScript. Database temporaneo e rotte esterne bloccate. Risultati: `implementation-report/phase51-ux.json`.

## Limiti e passo successivo

- 41 schede non dispongono della pagina originale salvata: rimangono incerte. Nessun problema di accesso è dichiarato risolto senza nuova prova.
- Tre casi Gold restano senza tipo pagina conclusivo (978, 984, 1010); non diventano richieste commerciali.
- Prout dichiara $500 fissi: non è automaticamente compatibile con un sito completo da 2.000 €. Twine non identifica il buyer; IOCOS non dimostra una commessa specifica. Queste sono piste, non clienti pronti.
- Le 70 esclusioni del replay non misurano crediti o tempo risparmiati. La qualità della nuova discovery richiede una campagna futura e una revisione indipendente.
- Nessuna nuova opportunità qualificata è stata inventata. Conversioni, risposte e contratti restano da misurare.

Dopo il riavvio manuale con `.venv/bin/python app.py`, ricaricare la pagina e avviare una **nuova** ricerca quando desiderato; il refresh da solo non aggiorna il backend. La Campagna 31 non è stata avviata.

## File modificati o aggiunti rispetto al backup iniziale

'''.replace('prefilt ri','prefiltri')
 report+='\n'.join('- `'+p+'`' for p in sorted(set(changed)))+'\n'
 report+='\nDocumenti richiesti: [metriche](PHASE-5.1-METRICS.json), [casi reali](PHASE-5.1-REAL-CASES.md), [benchmark](PHASE-5.1-BENCHMARK.md).\n'
 (ROOT/'PHASE-5.1-REPORT.md').write_text(report)
 print(json.dumps({'analyzed':111,'tests_passed':m['tests_passed'],'tables_unchanged':integrity.get('all_tables_unchanged'),'ready':m['ready_for_manual_campaign']}))
if __name__=='__main__':main()
