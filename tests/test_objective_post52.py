"""Actual C52 query failures and directory priorities; no live inference."""
import json
import unittest
from pathlib import Path
from sales.agent6.query_pipeline import prepare
from sales.agent6.discovery_intent import source_priority, source_issue
import test_ai_first as harness

SAVED=json.loads((Path(__file__).parent/'fixtures/ai_first/discovery52/campaign52.json').read_text())

class SavedFailures(unittest.TestCase):
    def test_four_rejected_commercial_directions_can_be_investigated(self):
        rows=[(p['flow'],q) for p in SAVED['plans'] for q in p['body'].get('rejected_queries',[])
              if q.get('reason')=='query_commercial_direction_missing']
        self.assertEqual(len(rows),4)
        for flow,q in rows:
            prepared,error=prepare({**harness.query(q['query']),'strategy':q.get('strategy','investigation')},
                                   flow,['Veneto','Lombardia'],ai_first=True)
            self.assertIsNone(error,(q,error))
            self.assertTrue(prepared['commercial_policy']['allowed'])
            self.assertEqual(prepared['commercial_policy']['basis'],'search_direction_only_originals_still_required')
            self.assertNotIn('qualified',prepared)

    def test_information_and_supplier_queries_still_fail(self):
        for flow,text in (
            ('AGENCIES','come gestire collaborazione esterna sviluppo web Veneto'),
            ('AGENCIES','agenzia richiedi preventivo ecommerce Veneto'),
            ('NEWS','azienda acquisizione clienti Veneto'),
            ('NEWS','azienda acquisto plugin WordPress Veneto'),
            ('STARTUPS','startup Veneto ecommerce sviluppo sito'),
            ('SOCIAL','site:instagram.com agenzia "collaborazione esterna" senza ruolo Veneto'),
        ):
            self.assertIsNone(prepare(harness.query(text),flow,['Veneto'],ai_first=True)[0],text)

    def test_first_five_directory_results_do_not_precede_possible_official_sites(self):
        rows=[r['body'] for r in SAVED['discovery'] if r['flow']=='AZIENDE']
        self.assertEqual(len(rows),10)
        p={'strategy':'official_company_sector_region'}
        official=[r for r in rows if 'gardenparadiso.it' in r['url'] or 'miramarevenezia.it' in r['url']]
        self.assertEqual(len(official),2)
        for directory in rows[:5]:
            self.assertIsNone(source_issue(directory,p))
            for candidate in official:
                self.assertLess(source_priority(directory,'AZIENDE',p)['value'],
                                source_priority(candidate,'AZIENDE',p)['value'])
            self.assertEqual(source_priority(directory,'AZIENDE',{'selection':'verification'})['value'],0)

    def test_product_catalog_and_single_company_not_mistaken_for_business_directory(self):
        for text in ('I nostri migliori prodotti e servizi', 'Catalogo aziendale: selezione di componenti',
                     'Camping Alfa, piazzole prenotabili', 'Agenzia Alfa: progetti per hotel e imprese'):
            self.assertEqual(source_priority({'url':'https://alfa.example','title':text},'AZIENDE',
                                            {'strategy':'official_company_sector_region'})['value'],0)
