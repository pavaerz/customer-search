import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sales.db import Store, now
from sales.research_store import ResearchStore
from sales.research_analysis import ResearchWeb
from sales.research_discovery import inspect_source
from sales.source_catalog import BUSINESS_SOURCES, seed_business_sources
from sales.commercial_planner import queries, hypothesis
from sales.prospect_scope import task_in_scope


class BusinessSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.store.init()
        self.rs=ResearchStore(self.store)
        self.c=self.rs.create({'regions':['Veneto','Lombardia'],'projects':['website'],'groups':['direct']})

    def tearDown(self):self.tmp.cleanup()

    def rows(self,kind):
        with self.store.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT payload FROM discovery_frontier WHERE kind=?',(kind,))]

    def test_sources_are_regional_idempotent_and_not_prospects(self):
        self.assertEqual(seed_business_sources(self.rs,self.c),0)
        self.assertEqual(seed_business_sources(self.rs,self.c),0)
        self.assertEqual(self.rows('candidate'),[])
        for row in self.rows('source'):
            self.assertIn(row['region'],self.c['filters']['regions'])
            self.assertTrue(task_in_scope('source','change',row,self.c['filters']))
            self.assertTrue(row['publisher'])

    def test_agency_only_and_stopped_campaign_do_not_add_sources(self):
        self.assertEqual(seed_business_sources(self.rs,{**self.c,'filters':{'groups':['agencies']}}),0)
        self.rs.stop(self.c['id'])
        self.assertEqual(seed_business_sources(self.rs,self.c),0)
        self.assertEqual(self.rows('source'),[])

    def test_stale_archive_stays_in_diagnostics_without_enqueued_work(self):
        campaign={**self.c,'filters':{**self.c['filters'],'regions':['Toscana']}}
        self.assertEqual(seed_business_sources(self.rs,campaign),0)
        self.assertEqual(self.rows('source'),[])
        with self.store.connect() as c:
            row=c.execute("SELECT state,reason FROM research_sources WHERE url='https://www.toscanaeconomy.it/primo-piano/dalle-imprese-toscane/'").fetchone()
        self.assertIsNone(row)  # No new source catalog work in direct customer campaigns.

    def feed(self):
        url=next(url for region,kind,url in BUSINESS_SOURCES if region=='Lombardia')
        page={'url':url,'status':200,'checked_at':now(),'html':'''<?xml version="1.0"?><rss><channel>
        <item><title>Alfa apre una nuova divisione industriale</title><link>https://lombardia.italiaeconomy.it/alfa-divisione/</link></item>
        <item><title>Alfa apre una nuova divisione industriale</title><link>https://lombardia.italiaeconomy.it/alfa-divisione/</link></item>
        <item><title>Bando per finanziamenti regionali</title><link>https://lombardia.italiaeconomy.it/finanziamenti/</link></item>
        <item><title>Beta presenta il nuovo brand</title><link>https://beta.example/brand/</link></item>
        <item><title>Vecchia nuova divisione</title><link>https://lombardia.italiaeconomy.it/vecchia/</link><pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate></item>
        </channel></rss>'''}
        task={'payload':{'url':url,'kind':'rss','publisher':True,'region':'Lombardia','source_scope':'business_news','hypothesis':hypothesis('change','Lombardia'),'research_intent':'signal'}}
        return page,task

    def test_rss_preserves_provenance_filters_strategy_and_deduplicates(self):
        page,task=self.feed()
        with patch.object(ResearchWeb,'get',return_value=page),patch('sales.serper_provider.search',side_effect=AssertionError('No paid search')):
            inspect_source(self.rs,self.c,task,lambda:None)
            inspect_source(self.rs,self.c,task,lambda:None)
        self.assertEqual(self.rows('candidate'),[])  # RSS discovery is not a customer channel.

    def test_curated_index_does_not_spider_full_site_sitemaps(self):
        url='https://news.example/business/'
        page={'url':url,'status':200,'checked_at':now(),'html':'<title>Notizie imprese</title><a href="/alfa">Alfa presenta un nuovo marchio</a>'}
        task={'payload':{'url':url,'kind':'html','publisher':True,'source_scope':'business_news','hypothesis':hypothesis('change','Veneto'),'research_intent':'signal'}}
        with patch.object(ResearchWeb,'get',return_value=page),patch.object(ResearchWeb,'policy',side_effect=AssertionError('No whole-site expansion')):
            inspect_source(self.rs,self.c,task,lambda:None)
        self.assertEqual(self.rows('candidate'),[])
        self.assertEqual(self.rows('source'),[])

    def test_read_failure_remains_unavailable_and_never_creates_candidate(self):
        page,task=self.feed();page['status']=403
        with patch.object(ResearchWeb,'get',return_value=page),self.assertRaises(ValueError):
            inspect_source(self.rs,self.c,task,lambda:None)
        self.assertEqual(self.rows('candidate'),[])
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT state FROM research_sources WHERE url=?',(page['url'],)).fetchone()[0],'unavailable')

    def test_feed_checks_publisher_linked_terms_before_using_entries(self):
        page,task=self.feed();root=page['url'].removesuffix('feed/')
        task['payload']['access_page']=root
        home={**page,'url':root,'html':'<a href="/terms">Condizioni di uso</a>'}
        terms={**page,'url':root+'terms','html':'<p>Vietata la raccolta automatizzata dei contenuti.</p>'}
        pages={page['url']:page,root:home,root+'terms':terms}
        with patch.object(ResearchWeb,'get',side_effect=lambda url:pages[url]),self.assertRaisesRegex(ValueError,'esclude la raccolta'):
            inspect_source(self.rs,self.c,task,lambda:None)
        self.assertEqual(self.rows('candidate'),[])

    def test_new_queries_alternate_sources_and_keep_event_phrase(self):
        for region in ('Veneto','Lombardia','Piemonte','Toscana'):
            q=list(queries('change',region,'b2b'))
            self.assertIn('"nuova linea"',q[0]);self.assertIn(region,q[0])
            self.assertTrue(q[1].startswith('site:'))
            self.assertEqual(len(q),len(set(q)))
            self.assertFalse(any('2026' in x for x in q))
        self.assertTrue(any('site:lombardia.italiaeconomy.it' in q for q in queries('change','Lombardia','b2b')))
        self.assertFalse(any('site:lombardiaeconomy.it' in q for q in queries('change','Lombardia','b2b')))
