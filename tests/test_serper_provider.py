import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from sales.db import Store
from sales.serper_provider import search, CreditLimit
from sales.discovery_control import record_health, available, diagnostics, measure
from sales.research_store import ResearchStore
from sales.research_discovery import search as discover
from sales.providers import provider, Serper
from sales.search_trial import TrialManager


class SerperProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'test.db');self.s.init()
        self.s.configure({'provider':'serper'})
        self.key=patch('sales.serper_provider.api_key',return_value='test-only-key');self.key.start()
        self.raw={'organic':[{'link':'https://alfa.example/','title':'Alfa Srl','snippet':'Impianti industriali Padova'}]}
    def tearDown(self):self.key.stop();self.tmp.cleanup()

    def test_provider_survives_restart_and_is_used_by_legacy_engines(self):
        self.s.init();self.assertEqual(self.s.settings()['provider'],'serper')
        self.assertIsInstance(provider(self.s),Serper)

    def test_cache_paging_italian_locale_and_credit_count(self):
        with patch('sales.serper_provider.transport',return_value=self.raw) as call:
            a,cached=search(self.s,'impianti Padova',2,'year')
            b,again=search(self.s,'impianti Padova',2,'year')
        self.assertFalse(cached);self.assertTrue(again);self.assertEqual(a,b)
        self.assertEqual(call.call_count,1)
        self.assertEqual(call.call_args.args[1],{'q':'impianti Padova','gl':'it','hl':'it','num':10,'page':2,'tbs':'qdr:y'})
        self.assertEqual(self.s.usage()['today']['serper'],1)

    def test_failure_counts_credit_and_never_falls_back(self):
        with patch('sales.serper_provider.transport',side_effect=ValueError('Serper: 429')),patch('sales.research_discovery.api_json',side_effect=AssertionError('No fallback')):
            rs=ResearchStore(self.s);c=rs.create()
            with self.assertRaisesRegex(ValueError,'429'):
                discover(rs,c,{'strategy':'companies','payload':{'query':'test','page':1,'period':''}},lambda:None)
        self.assertEqual(self.s.usage()['today']['serper'],1)
        self.assertFalse(available(self.s))

    def test_old_searxng_failure_does_not_block_serper(self):
        record_health(self.s,'searxng','offline')
        self.assertTrue(available(self.s))

    def test_zero_limit_and_missing_key_make_no_request(self):
        self.s.configure({'daily_api_limit':0})
        with patch('sales.serper_provider.transport') as call:
            with self.assertRaises(CreditLimit):search(self.s,'test')
            call.assert_not_called()
        with patch('sales.serper_provider.api_key',return_value=''),patch('sales.serper_provider.transport') as call:
            with self.assertRaisesRegex(ValueError,'mancante'):search(self.s,'test')
            call.assert_not_called()

    def test_atomic_budget_shared_between_workers(self):
        self.s.configure({'daily_api_limit':3,'monthly_api_limit':3})
        def reserve(n):
            try:self.s.reserve('serper');return True
            except CreditLimit:return False
        with ThreadPoolExecutor(max_workers=8) as pool:accepted=list(pool.map(reserve,range(12)))
        self.assertEqual(sum(accepted),3)

    def test_stop_before_transport_prevents_request(self):
        def stop():raise InterruptedError()
        with patch('sales.serper_provider.transport') as call:
            with self.assertRaises(InterruptedError):search(self.s,'test',check=stop)
            call.assert_not_called()

    def test_provenance_and_diagnostics_use_serper_only(self):
        rs=ResearchStore(self.s);c=rs.create()
        task={'strategy':'companies','kind':'search','payload':{'query':'impianti Padova','page':1,'period':''}}
        with patch('sales.serper_provider.transport',return_value=self.raw),patch('sales.research_discovery.api_json',side_effect=AssertionError('No SearXNG')):
            with measure(rs,c,task):discover(rs,c,task,lambda:None)
        d=diagnostics(rs,c['id'])
        self.assertTrue(d['paid']['serper']['enabled'])
        self.assertEqual(d['providers'][0]['name'],'serper')
        self.assertEqual(d['providers'][0]['credits'],1)
        with self.assertRaisesRegex(ValueError,'disattivato'):TrialManager(self.s).start(True)
