import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store
from sales.providers import SearXNG,provider


class ContactGroups(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'sales.db');self.store.init()
    def tearDown(self):self.tmp.cleanup()
    def add(self,engine='A'):
        cid=self.store.company('https://example.org','Test')
        sid=self.store.source({'url':'https://example.org/work'},cid)
        eid=self.store.add_evidence(cid,sid,engine,'request','Progetto','Cerchiamo un professionista per realizzare il sito web del nostro negozio.')
        pid=self.store.prospect(cid,engine,'Progetto','Sito',60,{},'Richiesta','Da verificare',[],[eid])[0]
        return cid,pid
    def test_manual_category_survives_research_merging_and_reopening(self):
        cid,pid=self.add()
        self.store.update_company(pid,{'contact_group':'agencies','stage':'contacted'})
        self.store.classify_contact(cid,'direct','Suggerita dalla homepage','https://example.org/')
        _,sibling=self.add('B')
        reopened=Store(self.store.path)
        self.assertEqual(len(reopened.company_list()),1)
        item=reopened.company_detail(sibling)
        self.assertEqual(item['contact_group'],'agencies')
        self.assertTrue(item['contact_group_manual'])
        self.assertEqual(item['stage'],'contacted')
        self.store.set_dismissed(pid)
        self.assertTrue(self.store.company_detail(pid)['dismissed_at'])
        self.store.set_dismissed(sibling,False)
        self.assertEqual(self.store.company_detail(pid)['contact_group'],'agencies')
    def test_homepage_classification_overrides_discovery_engine(self):
        cid,pid=self.add('B')
        self.store.classify_contact(cid,'direct','Homepage di un negozio','https://example.org/')
        item=self.store.company_detail(pid)
        self.assertEqual(item['contact_group'],'direct')
        self.assertEqual(item['contact_group_url'],'https://example.org/')
        self.assertFalse(item['contact_group_manual'])
    def test_invalid_category_does_not_update_workflow(self):
        cid,pid=self.add()
        with self.assertRaises(ValueError):self.store.update_company(pid,{'contact_group':'invented','stage':'contacted'})
        self.assertEqual(self.store.company_detail(pid)['stage'],'review')
    def test_legacy_paid_settings_cannot_activate_tavily(self):
        with self.store.connect() as c:c.execute('INSERT OR REPLACE INTO config VALUES (?,?)',('provider',json.dumps('tavily')))
        self.assertEqual(self.store.settings()['provider'],'searxng')
        self.assertIsInstance(provider(self.store),SearXNG)
        with self.assertRaises(ValueError):self.store.configure({'provider':'tavily'})
    @patch.dict(os.environ,{'SEARXNG_URL':'http://127.0.0.1:8080'})
    def test_free_search_provenance_cache_and_no_paid_usage(self):
        data={'results':[{'url':'https://example.org/?utm_source=x','engines':['bing']},{'url':'https://example.org/'},{'url':'javascript:alert(1)'},{'url':'https://linkedin.com/company/test'}]}
        search=provider(self.store)
        with patch('sales.providers.api_json',return_value=data) as call:
            first=search.search('test locale',self.store.settings())
            self.assertEqual(first,search.search('test locale',self.store.settings()))
            self.assertEqual(call.call_count,1)
            self.assertTrue(call.call_args.args[0].startswith('http://127.0.0.1:8080/search?'))
        self.assertEqual(len(first),1)
        self.assertIn('bing',first[0]['discovery_provider'])
        self.assertEqual(self.store.usage()['today'],{'searxng':1})
    @patch.dict(os.environ,{'SEARXNG_URL':'http://127.0.0.1:8080'})
    def test_failure_has_no_fallback_and_is_not_cached_as_empty(self):
        with patch('sales.providers.api_json',return_value={'results':[],'unresponsive_engines':[['bing','timeout']]}) as call:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError,'non hanno risposto'):provider(self.store).search('test',self.store.settings())
            self.assertEqual(call.call_count,2)
        self.assertEqual(self.store.usage()['today'],{'searxng':2})

if __name__=='__main__':unittest.main()
