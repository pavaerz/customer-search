"""Campaign54 saved evidence; generated boundary cases explicitly synthetic."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import test_ai_first as h
from sales.agent6 import decision, memory
from sales.agent6.sector_alignment import assess
from sales.agent6.discovery_intent import source_issue
from sales.agent6.schema import ValidationError

ROOT=Path(__file__).parent/'fixtures/ai_first/discovery58'
RECEIPTS=json.loads((ROOT/'company-receipts.json').read_text())
INVALID=json.loads((ROOT/'invalid.json').read_text())
QUERY=RECEIPTS[0]['query']
PROPOSAL={**h.query(QUERY),'strategy':'official_company_sector_region'}


def saved_payload(row):
    p=h.payload();p.update(evidence=row['evidence'],unit_id=row['evidence'][0]['unit_id'],
        subject_scope_version=1,identity={'verified':False},
        allowed_regions=['Veneto','Lombardia','Piemonte','Emilia-Romagna','Toscana'])
    return p


class SectorRouting(unittest.TestCase):
    def test_saved_unrelated_serp_is_held_not_qualified(self):
        result=assess(RECEIPTS,PROPOSAL)
        self.assertEqual(result['code'],'sector_results_without_query_anchor')
        self.assertEqual(len(result['held_urls']),8) # sparse Gazzetta metadata abstains
        self.assertEqual(result['effect'],'hold_this_query_results_not_reject_companies')
        self.assertNotIn('decision',result)

    def test_saved_set_does_not_download_or_spend_and_planner_gets_feedback(self):
        base=h.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        with patch('sales.agent6.research.acquire',return_value=copy.deepcopy(RECEIPTS)),patch(
                'sales.agent6.ai.infer',side_effect=AssertionError('No inference for unrelated SERP')),patch(
                'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No download')):
            base.w.execute({'id':58,'kind':'search','strategy':'AZIENDE','payload':PROPOSAL},lambda:None)
        with base.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM research_tasks WHERE kind='candidate'").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM agent6_records').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_discovery').fetchone()[0],9)
            self.assertEqual(db.execute("SELECT count(*) FROM commercial_discovery WHERE decision='defer'").fetchone()[0],6)
        receipts=memory.query_receipts(base.store,base.c['id'],'AZIENDE')
        self.assertEqual(receipts[0]['results'],9)
        self.assertEqual(receipts[0]['new_urls'],0)
        self.assertEqual(memory.planning_feedback(base.store,base.c['id'],'AZIENDE')['plan_feedback'][0]['code'],
                         'sector_results_without_query_anchor')

    def test_unknown_sparse_and_mixed_sets_are_not_inferred_unrelated(self):
        related={'url':'https://laundry.example','title':'Lavanderie industriali',
                 'snippet':'Servizi di lavanderia e noleggio biancheria per alberghi e ristoranti.'}
        self.assertIsNone(assess([*RECEIPTS,related],PROPOSAL))
        sparse=[{'url':'https://brand.example','title':'Brand','snippet':''}]*5
        self.assertIsNone(assess(sparse,PROPOSAL))
        self.assertIsNone(assess(RECEIPTS[:2],PROPOSAL))
        # Company outside the lexical scope is not permanently suppressed.
        self.assertIsNone(assess(RECEIPTS,{**PROPOSAL,'selection':'verification'}))
        self.assertIsNone(assess(RECEIPTS,{**PROPOSAL,'expected_entity':'Alfa'}))

    def test_other_channels_and_explicit_requests_are_not_sector_gated(self):
        for strategy in ('freelance_role','technical_cofounder','company_event','external_technical_partner'):
            self.assertIsNone(assess(RECEIPTS,{**PROPOSAL,'strategy':strategy}))

    def test_actual_short_query_results_remain_available_without_becoming_leads(self):
        probe=json.loads((ROOT/'short-query-results.json').read_text())
        items=[{**r,'url':r['link']} for r in probe['results']]
        self.assertIsNone(assess(items,{**PROPOSAL,'query':probe['query']['q']}))
        for item in items[:3]:
            self.assertIsNone(source_issue(item,PROPOSAL))
        self.assertFalse(any('decision' in item for item in items))

    def test_next_plan_receives_hold_reason_with_unchanged_budgets(self):
        base=h.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        limits=copy.deepcopy(base.c['filters'])
        feedback=assess(RECEIPTS,PROPOSAL)
        memory.event(base.store,base.c,'AZIENDE','plan_feedback','sector:58',feedback)
        seen=[]
        def model(flow,key,payload,check):
            seen.append(payload)
            return {'status':'completed','output':{'decision':'stop',
                    'reason':'Synthetic planner boundary, not a commercial result.','queries':[]}}
        with patch.object(base.w,'model',side_effect=model):
            base.w.planning({'id':58,'strategy':'AZIENDE','payload':{'round':1}},lambda:None)
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0]['memory']['plan_feedback'][0]['code'],feedback['code'])
        self.assertEqual(base.c['filters'],limits)

    def test_company_names_mentioning_institution_and_specific_articles_survive(self):
        for item in ({'url':'https://agency.example/','title':'Alfa: siti per Comune di Modena'},
                     {'url':'https://comune.example/notizie/impresa','title':'Comune di Alfa: nuova impresa'},
                     {'url':'https://gazette.example/avviso/123','title':'Gazzetta Ufficiale'}):
            self.assertIsNone(source_issue(item,PROPOSAL))

    def test_stop_interrupts_before_enqueue_or_feedback(self):
        base=h.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        with patch('sales.agent6.research.acquire',return_value=copy.deepcopy(RECEIPTS)):
            with self.assertRaises(InterruptedError):
                base.w.execute({'id':58,'kind':'search','strategy':'AZIENDE','payload':PROPOSAL},
                               lambda:(_ for _ in ()).throw(InterruptedError('Stopped')))
        with base.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM research_tasks WHERE kind='candidate'").fetchone()[0],0)


class NegativeIdentity(unittest.TestCase):
    def test_actual_institution_negative_decisions_are_valid_without_promotion(self):
        for ident in (1389,1384):
            row=next(r for r in INVALID if r['id']==ident)
            out,_=decision.validate(row['response'],saved_payload(row))
            self.assertEqual(out['decision'],'NOT_INTERESTING')
            self.assertEqual(out['action']['type'],'STOP')

    def test_institutions_cannot_be_promoted_or_queried(self):
        row=next(r for r in INVALID if r['id']==1389)
        for kind in ('INTERESTING','NEEDS_RESEARCH'):
            out=copy.deepcopy(row['response']);out['decision']=kind
            with self.assertRaisesRegex(ValidationError,'unsupported_actor'):
                decision.validate(out,saved_payload(row))

    def test_typography_is_not_a_fuzzy_name_match(self):
        row=next(r for r in INVALID if r['id']==1394)
        # Exact original response passes identity after apostrophe normalization,
        # but still fails independently on inconsistent OUT_OF_TARGET region.
        with self.assertRaisesRegex(ValidationError,'unexpected_subject_region'):
            decision.validate(row['response'],saved_payload(row))
        for name in ('Parco Archeologico dell’Appia','Parco Archeologico Appia Antica'):
            out=copy.deepcopy(row['response']);out['entity_name']=name
            # Shortened names are never thereby a verified positive identity.
            out['decision']='INTERESTING'
            with self.assertRaises(ValidationError):decision.validate(out,saved_payload(row))

    def test_multiple_regions_cannot_be_emitted_and_wrong_location_stays_invalid(self):
        from sales.agent6.subject_geography import contract
        choices=contract()['properties']['region']['enum']
        self.assertIn('Emilia-Romagna',choices)
        self.assertNotIn('Piemonte; Emilia-Romagna',choices)
        for ident in (1390,1392,1395):
            row=next(r for r in INVALID if r['id']==ident)
            with self.assertRaises(ValueError):decision.validate(row['response'],saved_payload(row))

    def test_region_diagnostic_explains_rejected_proof_without_source_prose(self):
        row=next(r for r in INVALID if r['id']==1395)
        # The full official registry now resolves Castel Maggiore correctly.
        # Synthetic wrong-region mutation keeps the diagnostic boundary test.
        output=copy.deepcopy(row['response'])
        output['subject_geography']['region']='Lombardia'
        from sales.agent6.subject_geography import validate
        from sales.agent6.grounding import resolve
        from sales.agent6.schema import quote
        facts=[{'field':f['field'],**quote(resolve({'segment_id':f['segment_id']},row['evidence']),row['evidence'])}
               for f in row['response']['facts']]
        try:validate(output,facts,saved_payload(row))
        except ValidationError as exc:
            self.assertEqual(exc.diagnostic['code'],'subject_region_not_supported')
            self.assertTrue(exc.diagnostic['region_allowed'])
            self.assertFalse(exc.diagnostic['cited_region_resolved'])
            self.assertNotIn('Beautimport',json.dumps(exc.diagnostic))
        else:self.fail('Invalid geography must not be silently accepted')
