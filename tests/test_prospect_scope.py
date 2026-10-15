import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from sales.db import Store
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.research_discovery import seed_campaign, search
from sales.research_triage import triage
from sales.research_analysis import ResearchWeb
from sales.prospect_scope import apply_scope, task_in_scope, excluded_url


class ProspectScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.db');self.store.init()
        self.rs=ResearchStore(self.store)
        self.c=self.rs.create({'groups':['direct'],'target':'b2b','projects':['website'],'regions':['Veneto']})
        self.f=Funnel(self.rs)

    def tearDown(self):self.tmp.cleanup()

    def test_reported_pages_are_rejected_without_network_or_model(self):
        urls=['https://zhidao.baidu.com/question/605130784.html',
              'https://corrieredelveneto.corriere.it/',
              'https://venetoup.com/bandi/voucher-3i-investire-innovazione/']
        with patch.object(ResearchWeb,'get',side_effect=AssertionError('Do not fetch unrelated pages')):
            for url in urls:
                r=triage(self.store,{'url':url,'strategy':'companies'},lambda:None)
                self.assertEqual(r['state'],'rejected')
                self.assertTrue(r['details']['acquisition_excluded'])
        self.assertIsNone(excluded_url('https://corriere-imballaggi.example/'))

    def test_search_routes_only_relevant_urls_and_pins_enabled_engine(self):
        results={'results':[{'url':'https://zhidao.baidu.com/question/1','engines':['bing']},
            {'url':'https://corrieredelveneto.corriere.it/'},
            {'url':'https://venetoup.com/bandi/a'},
            {'url':'https://unrelated.example/','title':'如何设置电脑显示器的问题'},
            {'url':'https://alfa.example/','title':'Alfa Srl impianti industriali Padova','engines':['yahoo']}], 'unresponsive_engines':[]}
        with patch.dict(os.environ,{'SEARXNG_URL':'http://127.0.0.1:8888'}),patch('sales.discovery_control.search_capabilities',return_value={'engines':['yahoo'],'paging':True,'time_range':False}),patch('sales.research_discovery.api_json',return_value=results) as request,patch('sales.research_discovery._last_search',0):
            search(self.rs,self.c,{'strategy':'companies','payload':{'query':'impianti industriali Padova','page':1,'period':''}},lambda:None)
        self.assertEqual(parse_qs(urlsplit(request.call_args.args[0]).query)['engines'],['yahoo'])
        with self.store.connect() as c:
            rows=c.execute("SELECT payload FROM discovery_frontier WHERE kind='candidate'").fetchall()
            self.assertEqual([json.loads(r[0])['url'] for r in rows],['https://alfa.example/'])
            self.assertTrue(c.execute("SELECT 1 FROM research_events WHERE kind='acquisition_filter'").fetchone())

    def test_customer_campaign_does_not_seed_global_sources(self):
        seed_campaign(self.rs,self.c)
        with self.store.connect() as c:
            jobs=c.execute('SELECT kind,strategy FROM discovery_frontier').fetchall()
        self.assertTrue(jobs)
        self.assertEqual({tuple(j) for j in jobs},{('search',s) for s in ('companies','explicit')})
        with self.store.connect() as c:
            sources=[json.loads(r[0]) for r in c.execute("SELECT payload FROM discovery_frontier WHERE kind='source'")]
        self.assertEqual(sources,[])
        self.assertTrue(task_in_scope('search','change',{'company_host':'alfa.example'},self.c['filters']))
        self.assertFalse(task_in_scope('source','sources',{'url':'https://news.example'},self.c['filters']))

    def test_unknown_publisher_is_not_relabelled_as_business_directory(self):
        from sales.db import now
        page={'url':'https://new-publisher.example/','status':200,'checked_at':now(),
              'html':'<title>Il Quotidiano Locale</title><main>Le ultime notizie delle imprese del Veneto.</main><footer>Direttore responsabile Mario Rossi</footer>'}
        with patch.object(ResearchWeb,'get',return_value=page):
            result=triage(self.store,{'url':page['url'],'strategy':'companies'},lambda:None)
        self.assertEqual(result['state'],'rejected')
        self.assertFalse(result.get('resolve'))

    def test_privacy_policy_is_not_commercial_evidence(self):
        from sales.research_analysis import LocalResearcher
        doc={'id':'privacy-document','url':'https://alfa.example/dichiarazione-sulla-privacy-ue/',
             'text':'Trasferimento internazionale dei dati. Nuovi servizi digitali.'}
        with patch.object(LocalResearcher,'call',side_effect=AssertionError('Policy is not a business signal')):
            signals,proposal,review,limits=LocalResearcher(self.store).analyze({},[doc],{})
        self.assertEqual(signals,[])
        self.assertEqual(proposal,{})

    def test_scope_migration_preserves_completed_history_and_company_followups(self):
        self.rs.enqueue(self.c['id'],'candidate','change',{'url':'https://news.example/sport'})
        self.rs.enqueue(self.c['id'],'candidate','change',{'url':'https://alfa.example/news','company_host':'alfa.example'})
        self.rs.enqueue(self.c['id'],'candidate','change',{'url':'https://news.example/done'})
        with self.store.connect() as c:c.execute("UPDATE research_tasks SET state='done' WHERE json_extract(payload,'$.url')='https://news.example/done'")
        self.assertEqual(apply_scope(self.rs,self.c),1)
        self.assertEqual(apply_scope(self.rs,self.c),0)
        with self.store.connect() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT state FROM research_tasks ORDER BY id')],['superseded','pending','done'])

    def test_company_view_deduplicates_and_diagnostics_keep_sources(self):
        identity={'name':'Alfa','website':'https://alfa.example/','identity_status':'verified','legal_id':'12345678901'}
        self.f.transition(self.c,{'url':'https://alfa.example/'},'needs_review','Identificata',{'identity':identity,'company_ready':True})
        self.f.transition(self.c,{'url':'https://alfa.example/news'},'promising','Prova da verificare',{'identity':identity,'company_ready':True})
        self.f.transition(self.c,{'url':'https://other.example/'},'discovered','Sconosciuta')
        self.f.transition(self.c,{'url':'https://news.example/'},'needs_review','Editore',{'publisher':True,'identity':{**identity,'website':'https://news.example/','legal_id':'other'}})
        self.f.transition(self.c,{'url':'https://off-target.example/'},'rejected','Sede fuori target',{'identity':{**identity,'website':'https://off-target.example/','legal_id':'other2'}})
        self.assertEqual(self.f.listing()['total'],5)
        view=self.f.listing({'company_only':'1','limit':1})
        self.assertEqual(view['total'],1)
        self.assertEqual(view['items'][0]['state'],'promising')
        self.assertEqual(self.f.listing({'company_only':'1','offset':1})['items'],[])
