"""C48 autonomous plans replayed offline; no claim of real new opportunities."""
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
import test_ai_first as harness
from sales.agent6.query_pipeline import prepare,company_coverage

SAVED=json.loads((Path(__file__).parent/'fixtures/ai_first/campaign48/plans.json').read_text())['plans']

class CommercialSearch(unittest.TestCase):
    def test_saved_operating_service_plan_is_admitted_without_declaring_demand(self):
        row=next(p for p in SAVED if p['flow']=='AZIENDE' and p['stage']=='plan')
        q=row['output']['queries'][0]
        prepared,error=prepare(q,'AZIENDE',['Veneto'],ai_first=True)
        self.assertIsNone(error)
        self.assertEqual(prepared['query'],q['query'])
        self.assertEqual(prepared['commercial_policy']['intents'],['official_company_investigation_not_declared_demand'])
        self.assertNotIn('qualified',prepared)

    def test_novel_operating_services_allowed_but_generic_and_out_of_area_queries_not(self):
        for text in ('Veneto noleggio attrezzature sito ufficiale',
                     'Toscana laboratori analisi sito ufficiale',
                     'Piemonte traduzioni tecniche sito ufficiale'):
            q={**harness.query(text),'strategy':'official_company_sector_region'}
            self.assertIsNone(prepare(q,'AZIENDE',['Veneto','Toscana','Piemonte'],ai_first=True)[1])
        for text in ('Veneto aziende sito ufficiale','Veneto prodotti servizi sito ufficiale',
                     'noleggio piattaforme sito ufficiale','Campania noleggio piattaforme sito ufficiale',
                     'Veneto web ecommerce'):
            q={**harness.query(text),'strategy':'official_company_sector_region'}
            self.assertIsNotNone(prepare(q,'AZIENDE',['Veneto'],ai_first=True)[1],text)

    def test_both_valid_modes_survive_but_selection_alternates(self):
        queries=next(p for p in SAVED if p['flow']=='AZIENDE' and p['stage']=='replan')['output']['queries']
        before=copy.deepcopy(queries)
        self.assertEqual(company_coverage(queries,[]),[queries[0]])
        receipts=[{'strategy':queries[0]['strategy'],'results':10}]
        self.assertEqual(company_coverage(queries,receipts),[queries[1]])
        receipts.append({'strategy':queries[1]['strategy'],'results':0})
        self.assertEqual(company_coverage(queries,receipts),[queries[0]])
        self.assertEqual(queries,before)
        self.assertEqual(company_coverage([queries[1]],[]),[queries[1]])
        self.assertEqual(company_coverage(queries,[{'strategy':queries[1]['strategy'],'results':10,'selection':'verification'}]),[queries[0]])

    def test_planner_selects_proactive_when_both_ai_proposals_are_valid(self):
        base=harness.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        plan=next(p for p in SAVED if p['flow']=='AZIENDE' and p['stage']=='replan')['output']
        with patch('sales.agent6.ai.infer',return_value={'output':plan,'usage':{}}),patch(
                'sales.agent6.research.acquire',side_effect=AssertionError('No Serper')):
            base.w.planning({'id':900,'strategy':'AZIENDE','payload':{'round':0}},lambda:None)
        with base.store.connect() as db:
            queued=[json.loads(r[0]) for r in db.execute("SELECT payload FROM research_tasks WHERE kind='search'")]
            saved=json.loads(db.execute("SELECT body FROM agent6_memory WHERE kind='plan'").fetchone()[0])
        self.assertEqual(len(queued),1)
        self.assertEqual(queued[0]['strategy'],'official_company_sector_region')
        self.assertEqual(len(saved['queries']),2)
        self.assertEqual(saved['chosen']['strategy'],'official_company_sector_region')
