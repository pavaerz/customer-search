import unittest
from unittest.mock import Mock
from scripts.pilot50_cycle import PilotRequests
from sales.serper_provider import CreditLimit


class PilotRequestTests(unittest.TestCase):
    def test_no_request_ceiling_when_budget_is_unspecified(self):
        store=Mock();report={'requests':10000,'queries':[]}
        def search(store,*args):store.reserve('serper');return {'results':[]},False
        pilot=PilotRequests(store,report,None,lambda:None,search)
        pilot(store,'one');pilot(store,'two')
        self.assertEqual(report['requests'],10002)
        self.assertEqual(store.reserve.call_count,2)

    def test_transport_failure_counts_and_boundary_prevents_next_reservation(self):
        store=Mock();report={'requests':0,'queries':[]};save=Mock()
        def fail(store,*args):store.reserve('serper');raise ValueError('Network error')
        pilot=PilotRequests(store,report,1,save,fail)
        with self.assertRaises(ValueError):pilot(store,'first')
        self.assertEqual(report['requests'],1);self.assertEqual(report['queries'][0]['requests'],1)
        with self.assertRaises(CreditLimit):pilot(store,'second')
        self.assertEqual(store.reserve.call_count,1);self.assertEqual(report['queries'][1]['requests'],0)
        self.assertEqual(save.call_count,2)

    def test_cache_does_not_spend_even_after_sample_boundary(self):
        store=Mock();report={'requests':1,'queries':[]}
        pilot=PilotRequests(store,report,1,lambda:None,lambda *args:({'results':[]},True))
        self.assertTrue(pilot(store,'cached')[1]);store.reserve.assert_not_called()
        self.assertEqual(report['queries'][0]['requests'],0)
