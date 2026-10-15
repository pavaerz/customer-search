import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sales.db import Store, now
from sales.research_store import ResearchStore
from sales.research_discovery import seed_campaign, search
from sales.research_triage import triage
from sales.research_analysis import ResearchWeb
from sales.company_research import company_queries, selected_strategies
from sales.discovery_planner import variants
from sales.direct_channels import linkedin_notice, indexed_notice
from sales.prospect_scope import task_in_scope, apply_scope


class DirectChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db');self.store.init();self.store.configure({'provider':'serper'})
        self.rs=ResearchStore(self.store);self.c=self.rs.create({'groups':['direct','agencies'],'regions':['Veneto'],'projects':['website']})

    def notice(self, **fields):
        return {'url':'https://www.linkedin.com/posts/alfa_richiesta-123',
                'title':'Alfa Srl su LinkedIn: Cerchiamo sviluppatore WordPress freelance',
                'search_snippet':'Progetto nuovo sito aziendale. Collaborazione a partita IVA.',**fields}

    def test_recruiting_pages_are_queued_first_and_guides_are_not_downloaded(self):
        results=[{'url':'https://guide.example/blog','title':'Sviluppatore freelance: guida per aziende'},
                 {'url':'https://unknown.example/','title':'Servizi digitali'},
                 {'url':'https://agency.example/lavora-con-noi/','title':'Lavora con noi','content':'Cerchiamo WordPress freelance.'}]
        with patch('sales.serper_provider.search',return_value=({'results':results},False)):
            search(self.rs,self.c,{'strategy':'partner','payload':{'query':'WordPress freelance Veneto','page':1}},lambda:None)
        with self.store.connect() as c:
            tasks=[json.loads(r[0]) for r in c.execute("SELECT payload FROM discovery_frontier WHERE kind='candidate' ORDER BY id")]
            self.assertEqual(c.execute('SELECT count(*) FROM research_assessments').fetchone()[0],0)
        self.assertEqual(tasks[0]['url'],'https://agency.example/lavora-con-noi/')
        self.assertIn('recruiting',tasks[0]['acquisition_reason'])
        self.assertNotIn('https://guide.example/blog',[p['url'] for p in tasks])

    def test_partner_queries_cover_selected_region_towns_without_other_regions(self):
        from sales.discovery_planner import variants,query_key
        queries=list(variants('partner','Veneto'))
        self.assertTrue(any('Padova' in q and 'WordPress' in q for q in queries))
        self.assertTrue(any('Treviso' in q for q in queries))
        self.assertFalse(any('Milano' in q for q in queries))
        self.assertEqual(len(queries),len({query_key({'query':q}) for q in queries}))

    def test_new_campaign_has_only_direct_channels_and_no_source_crawls(self):
        self.store.configure({'rss_feeds':['https://news.example/feed']})
        seed_campaign(self.rs,self.c)
        with self.store.connect() as c:rows=c.execute('SELECT kind,strategy FROM discovery_frontier').fetchall()
        self.assertEqual({tuple(r) for r in rows},{('search','companies'),('search','explicit'),('search','partner')})
        self.assertFalse(any('associati' in q or 'elenco' in q for q in company_queries('Veneto')))
        self.assertTrue(any('site:linkedin.com/posts/' in q for q in variants('explicit','Veneto')))
        self.assertEqual(selected_strategies({'groups':['agencies']}),('partner','explicit'))

    def test_reported_directory_and_economic_report_never_downloaded(self):
        urls=['https://www.paginegialle.it/alfa','https://firmania.it/alfa',
              'https://www.confindustriavenest.it/stampa-e-media/comunicati-stampa/veneto-est-export-resiliente-per-ora-a-dazi-e-germania-nel-2026-trend-in-crescita-per-4-aziende-su-dieci']
        with patch.object(ResearchWeb,'get',side_effect=AssertionError('No download')):
            for url in urls:
                result=triage(self.store,{'url':url,'direct_channels':True},lambda:None)
                self.assertEqual(result['state'],'rejected')
        self.assertFalse(task_in_scope('search','companies',{'query':'elenco aziende meccanica Veneto associati'},{}))
        self.assertTrue(task_in_scope('candidate','companies',{'url':'https://alfa.example/'},{}))

    def test_unknown_publisher_does_not_spawn_company_resolution(self):
        page={'url':'https://publisher.example/report','status':200,'checked_at':now(),
              'html':'<title>Quotidiano Veneto: export</title><p>Alfa Srl cresce sui mercati esteri.</p><footer>Testata giornalistica</footer>'}
        with patch.object(ResearchWeb,'get',return_value=page):
            result=triage(self.store,{'url':page['url'],'direct_channels':True},lambda:None)
        self.assertEqual(result['state'],'rejected');self.assertFalse(result.get('resolve'))

    def test_indexed_freelance_post_is_hint_not_company_or_verified_document(self):
        with patch.object(ResearchWeb,'get',side_effect=AssertionError('Never fetch LinkedIn')):
            result=triage(self.store,self.notice(),lambda:None)
        self.assertEqual(result['state'],'needs_review')
        self.assertFalse(result['details']['company_ready'])
        self.assertFalse(result['details']['search_hint']['verified'])
        self.assertEqual(result['resolve_queries'][0]['subject'],'Alfa Srl')
        self.assertNotIn('source_documents',result['resolve_queries'][0])
        self.assertNotIn('document',result['details'])

    def test_dependent_jobs_profiles_and_self_promotion_are_not_freelance_demand(self):
        for change in ({'search_snippet':'Contratto a tempo indeterminato, no freelance.'},
                       {'search_snippet':'Cerco lavoro. Sono un freelance WordPress.'},
                       {'search_snippet':'Cerchiamo freelance per correzioni CSS.'},
                       {'url':'https://linkedin.com/company/alfa'},
                       {'url':'https://linkedin.com/in/mario'},
                       {'url':'https://linkedin.com.evil.example/posts/alfa'}):
            with self.subTest(change=change):self.assertFalse(linkedin_notice(self.notice(**change)))
        self.assertTrue(linkedin_notice(self.notice(url='https://it.linkedin.com/jobs/view/frontend-123')))

    def test_unknown_employer_is_not_invented(self):
        result=indexed_notice(self.notice(title='Cerchiamo web designer freelance per nuovo sito'))
        self.assertFalse(result['resolve_queries']);self.assertEqual(result['details']['identity'],{})

    def test_search_keeps_specific_notice_without_unblocking_linkedin_downloads(self):
        from sales.providers import blocked
        response={'results':[self.notice(),self.notice(url='https://linkedin.com/jobs/search/') ,
                    {'url':'https://paginegialle.it/alfa','title':'Alfa Srl'},
                    {'url':'https://alfa.example/','title':'Alfa Srl'}]}
        with patch('sales.serper_provider.search',return_value=(response,False)),patch.object(ResearchWeb,'get',side_effect=AssertionError('No crawl')):
            search(self.rs,self.c,{'strategy':'explicit','payload':{'query':'WordPress freelance Veneto','page':1,'period':''}},lambda:None)
        with self.store.connect() as c:
            rows=[json.loads(r[0]) for r in c.execute("SELECT payload FROM discovery_frontier WHERE kind='candidate'")]
        self.assertEqual({r['url'] for r in rows},{self.notice()['url'],'https://alfa.example/'})
        notice=next(r for r in rows if 'linkedin.com' in r['url'])
        self.assertTrue(blocked(notice['url']))
        self.assertEqual(triage(self.store,notice,lambda:None)['state'],'needs_review')

    def test_resume_retires_old_sources_but_keeps_company_reviews_and_history(self):
        for kind,strategy,payload in [('source','change',{'url':'https://news.example/feed','hypothesis':{}}),
            ('search','change',{'query':'nuova linea Veneto','hypothesis':{'id':'old'}}),
            ('verify','companies',{'url':'https://alfa.example/','company_host':'alfa.example'})]:
            self.rs.enqueue(self.c['id'],kind,strategy,payload)
        self.assertEqual(apply_scope(self.rs,self.c),2)
        with self.store.connect() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT state FROM research_tasks ORDER BY id')],['superseded','superseded','pending'])


if __name__=='__main__':unittest.main()
