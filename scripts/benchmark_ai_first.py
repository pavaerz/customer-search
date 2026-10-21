"""Offline audit plus optional AI-first extraction on frozen originals.

Run under tests/offline_guard. Reads frozen public originals, calls pure existing
functions, writes diagnostic measurements. The default remains the Phase-1
legacy diagnostic; --ai-first-extraction measures extraction, not AI accuracy.
Never opens the production database,
starts a worker, or invokes an AI/search provider. Gold labels are evaluation
criteria; they are never input to a classifier.
"""
import argparse
import hashlib
import json
from pathlib import Path
from sales.agent6.alignment import dimensions
from sales.agent6.qualification import temporal, objective
from sales.agent6.document_units import extract
from sales.commercial.target_fit import group_evidence, source_role

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/ai_first/historical.json'
NOW='2026-10-20T12:00:00+02:00'

def run():
    frozen=json.loads(FIXTURE.read_text());records=[]
    for case in frozen['cases']:
        for d in case['documents']:
            assert hashlib.sha256(d['text'].encode()).hexdigest()==d['snapshot_text_sha256']
        b=case['observed'];a=dimensions(b)
        # This is a labelled projection of the LEGACY state, not an AI decision.
        decision=('INTERESTING' if a['OPPORTUNITY_QUALIFIED'] else
                  'NOT_INTERESTING' if b['state']=='REJECTED' else 'NEEDS_RESEARCH')
        records.append({'case':case['case'],'record_id':case['record_id'],
            'expected':case['expected'],'historical_state':b['state'],
            'legacy_projection':decision,'matches_proposed_label':decision==case['expected'],
            'current_alignment_on_historical_record':a,
            'documents':[{'id':d.get('id',d.get('document_id')),'url':d['url'],
                'sha256':d['snapshot_text_sha256'],
                'temporal_from_current_function':temporal(d['text'],d.get('checked_at') or NOW,True),
                'units_recognized_by_current_extractor':len(extract(d)),
                'source_role_current':source_role(d['url'],d.get('title') or '',d['text'])}
                for d in case['documents']]})
    probes=[]
    def probe(name,expected,actual,scope):
        probes.append({'name':name,'expected':expected,'actual':actual,'matches':expected==actual,'scope':scope})
    # Equivalent date meanings with different labels, positions and languages.
    for name,text,expected in [
        ('iso_label','Pubblicato il 2015-11-03','STALE'),
        ('italian_slash_label','Postato il: 03/11/2015 - 11:19','STALE'),
        ('numeric_card_date','Organizzazione: Nuova Alfa\nCerchiamo sviluppatore freelance\n03/11/2015 - 11:19','STALE'),
        ('late_iso_label','Contenuto introduttivo. '*100+'Pubblicato il 2015-11-03','STALE'),
        ('recent_label','Pubblicato il 2026-10-19','RECENT'),
        ('future_label','Pubblicato il 2099-10-19','UNKNOWN'),
        ('undated_evergreen','Invia portfolio: collaboriamo con freelance frontend.','UNKNOWN'),
        ('footer_year','Cerchiamo freelance. Copyright 2026','UNKNOWN')]:
        probe(name,expected,temporal(text,NOW,True)['status'],'synthetic temporal extraction, not a commercial classification')
    for actor,supplier in [('Falegnameria Aurora Srl','Oknoplast'),('Officina Nord Srl','Gruppo Delta')]:
        text=f'{actor}\nSiamo rivenditori ufficiali e partner {supplier}, gruppo multinazionale specializzato in prodotti.'
        probe('supplier_not_owner:'+actor,[],group_evidence(text,actor),'synthetic relation permutation')
    for company in ['Studio Aurora Srl','Laboratorio Nuova Riva']:
        source={'url':'https://example.org/careers','title':company,'text':f'{company}\nPubblicato il 2026-10-19\nAssumiamo solo dipendenti a tempo indeterminato. Non accettiamo freelance.', 'checked_at':NOW,'original':True}
        probe('employee_only:'+company,True,'employee_job' in objective(source)['counterevidence'],'synthetic negative relation')
    positives=[r for r in records if r['expected']=='INTERESTING'];pred=[r for r in records if r['legacy_projection']=='INTERESTING']
    tp=sum(r['expected']=='INTERESTING' for r in pred)
    return {'mode':'offline_diagnostic_current_code_and_historical_states',
        'historical_cases':records,'contract_probes':probes,
        'legacy_surface_metrics':{'interesting_labels':len(positives),'surfaced_interesting':len(pred),
            'true_positive':tp,'false_positive':len(pred)-tp,'missed_interesting':len(positives)-tp,
            'recall_on_two_known_outreach_cases':tp/len(positives) if positives else None,
            'precision':tp/len(pred) if pred else None,
            'three_way_agreement':sum(r['matches_proposed_label'] for r in records)/len(records)},
        'contract_summary':{'total':len(probes),'met':sum(p['matches'] for p in probes),'unmet':sum(not p['matches'] for p in probes)},
        'limitations':['No new AI decision engine exists in Phase 1; no AI generalization measurement.',
            'Legacy state projection is not an evaluation of a fresh AI run.',
            'Purposive regression sample, not market precision or conversion estimate.',
            'Synthetic probes are explicit variants, not real opportunities.'],
        'paid_calls':0,'production_database_accesses':0}

def extraction():
    """Inspect frozen originals with the new date extractor, not a model double."""
    from sales.agent6.evidence import dates
    frozen=json.loads(FIXTURE.read_text())
    cases=[]
    for case in frozen['cases']:
        documents=[]
        for d in case['documents']:
            assert hashlib.sha256(d['text'].encode()).hexdigest()==d['snapshot_text_sha256']
            documents.append({'url':d['url'],'sha256':d['snapshot_text_sha256'],
                              'date_claims':dates(d['text'])})
        cases.append({'case':case['case'],'documents':documents})
    return {'mode':'offline_ai_first_extraction_only','cases':cases,'paid_calls':0,
            'production_database_accesses':0,'model_accuracy':None,
            'limitations':['Frozen public text only; missing raw HTML is not synthesized.',
                           'No model calls: semantic precision, recall and conversion are unmeasured.',
                           'Unlabelled numeric dates remain unassigned, not publication dates.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='analysis-report/ai-first/benchmark-results.json')
    parser.add_argument('--ai-first-extraction',action='store_true');args=parser.parse_args()
    result=extraction() if args.ai_first_extraction else run()
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('mode','legacy_surface_metrics','contract_summary','paid_calls') if k in result},ensure_ascii=False))
