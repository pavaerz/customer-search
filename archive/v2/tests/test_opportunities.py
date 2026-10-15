import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from opportunities import OpportunityService, analyze, blocked, canonical, draft

TODAY = date(2026, 10, 12)
DEMAND = 'Cerchiamo uno sviluppatore WordPress freelance per creare template personalizzati e nuovi siti web per i clienti della nostra agenzia.'


def page(text=DEMAND, **values):
    job = {'@type':'JobPosting','title':'WordPress Developer freelance','description':text+' Collaborazione continuativa da remoto. Invia il portfolio.', 'datePosted':'2026-10-10','hiringOrganization':{'name':'Studio Test'}, **values}
    return '<html><script type="application/ld+json">'+json.dumps(job)+'</script><p>'+text+'</p></html>'


class AnalysisTest(unittest.TestCase):
    def analyze(self, html):
        return analyze(html, 'https://agency.it/jobs/wordpress', TODAY)

    def test_explicit_demand_and_facts(self):
        item, reason = self.analyze(page())
        self.assertIsNone(reason)
        self.assertEqual(item['category'], 'B')
        self.assertEqual(item['company'], 'Studio Test')
        self.assertGreater(item['score'], 70)
        self.assertIsNone(item['budget'])
        self.assertIsNone(item['location'])
        self.assertEqual(item['date_source'], 'JobPosting.datePosted')
        self.assertIn('WordPress', item['technologies'])

    def test_editorial_content_with_demand_is_not_a_job(self):
        for kind in ('Article', 'BlogPosting', 'NewsArticle'):
            schema={'@graph':[{'@type':kind,'datePublished':'2026-10-10'}]}
            html='<script type="application/ld+json">'+json.dumps(schema)+'</script><p>'+DEMAND+'</p>'
            item, reason=self.analyze(html)
            self.assertIsNone(item)
            self.assertIn('editoriale',reason)

    def test_explicit_jobposting_not_rejected_for_article_metadata(self):
        html=page()+'<script type="application/ld+json">{"@type":"Article"}</script>'
        self.assertIsNotNone(self.analyze(html)[0])

    def test_plugin_search_in_article_is_not_professional_demand(self):
        html='<p>Lo stesso discorso vale per WordPress: serve una funzione, si cerca un plugin; poi si aggiunge altro codice.</p><p>Freelance e agenzie lavorano da remoto.</p>'
        self.assertIsNone(self.analyze(html)[0])

    def test_marketplace_advertising_is_not_a_client_request(self):
        html='<p>Hire programmers and developers on Freelancer. Whether you’re looking for experts in WordPress, we’ve got you covered. Freelance remote work.</p>'
        self.assertIsNone(self.analyze(html)[0])
        self.assertIsNone(analyze(page(), 'https://play.google.com/store/apps/details?id=test', TODAY)[0])

    def test_undated_page_capped(self):
        item, _ = self.analyze(page(datePosted=None))
        self.assertIsNone(item['published'])
        self.assertLessEqual(item['score'], 59)

    def test_employee_only_excluded(self):
        item, reason = self.analyze(page('Cerchiamo sviluppatore WordPress. Assunzione a tempo indeterminato. No freelance.'))
        self.assertIsNone(item)
        self.assertIn('freelance', reason)

    def test_no_assumption_that_remote_means_freelance(self):
        item, _ = self.analyze('<p>Cerchiamo sviluppatore WordPress da remoto. Assunzione a tempo indeterminato.</p>')
        self.assertIsNone(item)

    def test_old_expired_future_and_invalid_dates(self):
        for data in ({'datePosted':'2025-01-01'}, {'validThrough':'2026-10-01'}):
            self.assertIsNone(self.analyze(page(**data))[0])
        for value in ('2099-01-01', '2026-02-31', 'ieri'):
            item, _ = self.analyze(page(datePosted=value))
            self.assertIsNone(item['published'])
            self.assertLessEqual(item['score'], 59)
        item, _ = self.analyze(page(datePosted='2026-08-01'))
        self.assertLessEqual(item['score'], 69)

    def test_service_and_informational_pages_rejected(self):
        for text in ('Siamo sviluppatori WordPress freelance. Realizziamo siti web.', 'Come trovare uno sviluppatore WordPress freelance per la tua azienda.', 'I nostri clienti cercano un sito migliore. WordPress è il nostro CMS.'):
            self.assertIsNone(self.analyze('<p>'+text+'</p>')[0])

    def test_unrelated_role_cannot_borrow_skills_from_footer(self):
        html = '<p>Cerchiamo social media manager freelance.</p><footer>WordPress React siti web</footer>'
        self.assertIsNone(self.analyze(html)[0])
        html = '<p>Cerchiamo un copywriter freelance per landing page e siti web.</p>'
        self.assertIsNone(self.analyze(html)[0])

    def test_live_false_positive_job_boards(self):
        text='Sei alla ricerca di lavori creativi in Italia o vuoi trovare i migliori talenti per la tua azienda? Crebs.it è la job board dedicata a tutti i professionisti. Sviluppatore freelance WordPress.'
        self.assertIsNone(self.analyze('<p>'+text+'</p>')[0])
        self.assertIsNone(self.analyze('<title>WordPress - 783 offerte di lavoro</title><p>'+DEMAND+'</p>')[0])

    def test_remote_jobs_catalog_is_not_employer_demand(self):
        html='<p>Explore the fully remote Next.js jobs in Europe. Whether you are seeking freelance work, start your search today!</p>'
        self.assertIsNone(self.analyze(html)[0])

    def test_same_generic_demand_different_employers_not_merged(self):
        from opportunities import fingerprint
        a=self.analyze(page())[0]
        b={**a,'company':'Other company'}
        self.assertNotEqual(fingerprint(a),fingerprint(b))
        self.assertIsNone(fingerprint({**a,'company':None}))

    def test_script_text_not_evidence(self):
        self.assertIsNone(self.analyze('<script>'+DEMAND+'</script>')[0])

    def test_distinct_roles_do_not_share_eligibility(self):
        html = '<p>Cerchiamo sviluppatore WordPress. Assunzione a tempo indeterminato.</p><p>Cerchiamo designer freelance.</p>'
        self.assertIsNone(self.analyze(html)[0])

    def test_web_designer_role_is_recognized(self):
        html='<h1>Siamo alla ricerca di un Web Designer Freelance</h1><p>HTML CSS JavaScript. Sede di lavoro: Verona/telelavoro.</p>'
        item,_=self.analyze(html)
        self.assertIsNotNone(item)
        self.assertIn('UI/UX',item['technologies'])
        self.assertEqual(item['location'],'Verona/telelavoro')

    def test_direct_project(self):
        item, _ = self.analyze('<p>Cerco uno sviluppatore per rifare il sito web aziendale con WordPress.</p>')
        self.assertEqual(item['category'], 'A')

    def test_international_requires_remote_and_no_country_restriction(self):
        html = '<p>We are hiring a freelance Next.js developer, remote Europe. Apply now.</p>'
        self.assertIsNotNone(analyze(html,'https://agency.com/job',TODAY)[0])
        self.assertIsNone(analyze(html.replace('remote Europe', 'US only remote'),'https://agency.com/job',TODAY)[0])
        self.assertIsNone(analyze(html.replace('remote Europe', 'on site'),'https://agency.com/job',TODAY)[0])

    def test_aggregated_structured_jobs_rejected(self):
        html='<script type="application/ld+json">'+json.dumps([{'@type':'JobPosting'}, {'@type':'JobPosting'}])+'</script>'
        self.assertIsNone(self.analyze(html)[0])

    def test_draft_contains_only_user_skills_no_invented_experience(self):
        item,_=self.analyze(page(DEMAND+' Richiesti 5 anni di esperienza PHP e MySQL.'))
        message=draft(item)
        self.assertNotIn('5 anni',message)
        self.assertNotIn('PHP',message)
        self.assertIn('WordPress',message)
        self.assertIn(item['url'],message)
        self.assertIn('designerdimontagna.it',message)

    def test_url_and_platform_policy(self):
        self.assertEqual(canonical('https://agency.it/jobs/12/?utm_source=x&id=2#apply'),'https://agency.it/jobs/12?id=2')
        for url in ('file:///etc/passwd', 'javascript:alert(1)', 'https://u:p@agency.it', 'https://agency.it:9999/'):
            with self.assertRaises(ValueError): canonical(url)
        for host in ('linkedin.com', 'it.linkedin.com', 'freelancer.es', 'de.indeed.com'):
            self.assertTrue(blocked('https://'+host+'/job'))
        self.assertFalse(blocked('https://linkedin.com.other.it/job'))


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'test.sqlite'
        @contextmanager
        def db():
            c=sqlite3.connect(self.path)
            c.row_factory=sqlite3.Row
            try:
                with c: yield c
            finally: c.close()
        self.db=db
        with db() as c:
            c.execute('CREATE TABLE leads(id INTEGER, name TEXT)')
            c.execute("INSERT INTO leads VALUES (1,'Preserve')")
        self.search=Mock(return_value=[])
        self.fetch=Mock(return_value=(200,page(),'https://agency.it/job'))
        self.service=OpportunityService(db,self.search,self.fetch)
        self.service.init()
        self.item=analyze(page(), 'https://agency.it/job',TODAY)[0]

    def tearDown(self):
        self.temp.cleanup()

    def test_migration_is_additive_idempotent(self):
        self.service.init()
        with self.db() as c:
            self.assertEqual(c.execute('SELECT name FROM leads').fetchone()[0],'Preserve')

    def test_dedup_persistence_and_preserve_actions(self):
        self.assertTrue(self.service.save(self.item))
        ident=self.service.state()['items'][0]['id']
        self.service.update(ident,{'status':'contacted','notes':'Spoke Tuesday','generate_draft':True})
        alias={**self.item,'url':'https://mirror.it/project/2','sources':['https://mirror.it/project/2']}
        self.assertFalse(self.service.save(alias))
        items=self.service.state()['items']
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['status'],'contacted')
        self.assertEqual(items[0]['notes'],'Spoke Tuesday')
        self.assertTrue(items[0]['draft'])
        self.assertEqual(len(items[0]['sources']),2)
        self.service.update(ident,{'status':'discarded'})
        self.service.save(self.item)
        self.assertEqual(self.service.state()['items'][0]['status'],'discarded')

    def test_different_demands_same_company_preserved(self):
        self.service.save(self.item)
        other=analyze(page(DEMAND.replace('WordPress','React')), 'https://agency.it/react',TODAY)[0]
        self.assertTrue(self.service.save(other))
        self.assertEqual(len(self.service.state()['items']),2)

    def test_validation(self):
        for body in ({'queries':[]},{'queries':['good query'],'batch_size':0},{'queries':['good query'],'provider':'untrusted'}):
            with self.assertRaises(ValueError): self.service.configure(body)
        self.service.save(self.item)
        ident=self.service.state()['items'][0]['id']
        for body in ({'status':'sent'},{'notes':[]},{'draft':None}):
            with self.assertRaises(ValueError): self.service.update(ident,body)
        with self.assertRaises(ValueError): self.service.update(999,{})

    def test_worker_uses_original_page_not_snippet(self):
        self.service.configure({'queries':['test query'],'batch_size':1})
        self.search.return_value=[{'url':'https://agency.it/job','title':DEMAND,'content':DEMAND}]
        self.fetch.return_value=(200,'<p>Services for WordPress</p>','https://agency.it/job')
        self.service.run()
        state=self.service.state()
        self.assertEqual(state['items'],[])
        self.assertEqual(state['runs'][0]['summary']['checked'],1)
        self.assertTrue(state['runs'][0]['summary']['rejected'])

    def test_network_error_preserves_partial_results_and_history(self):
        self.service.configure({'queries':['test query'],'batch_size':1})
        self.search.return_value=[{'url':'https://agency.it/job'},{'url':'https://other.it/job'}]
        self.fetch.side_effect=[(200,page(datePosted=None),'https://agency.it/job'), OSError('Unavailable')]
        self.service.run()
        state=self.service.state()
        self.assertEqual(len(state['items']),1)
        self.assertEqual(state['runs'][0]['status'],'partial')
        self.assertFalse(state['job']['running'])

    def test_blocked_platform_not_fetched(self):
        self.service.configure({'queries':['test query'],'batch_size':1})
        self.search.return_value=[{'url':'https://linkedin.com/jobs/123'}]
        self.service.run()
        self.fetch.assert_not_called()

    def test_stop_is_independent_and_persisted(self):
        self.service.stop.set()
        self.service.run()
        self.search.assert_not_called()
        self.assertEqual(self.service.state()['runs'][0]['status'],'stopped')

    def test_robots_fail_closed(self):
        self.fetch.return_value=(200,'User-agent: *\nDisallow: /job','https://agency.it/robots.txt')
        with self.assertRaises(ValueError): self.service.policy('https://agency.it/job')
        self.service.robots={}
        self.fetch.return_value=(403,'','https://agency.it/robots.txt')
        with self.assertRaises(ValueError): self.service.policy('https://agency.it/job')
        self.service.robots={}
        self.fetch.return_value=(404,'','https://agency.it/robots.txt')
        self.service.policy('https://agency.it/job')

    def test_weekly_metric_excludes_undated_old_and_discarded(self):
        recent={**self.item,'published':date.today().isoformat()}
        self.service.save(recent)
        self.assertEqual(self.service.state()['weekly_recent'],1)
        ident=self.service.state()['items'][0]['id']
        self.service.update(ident,{'status':'discarded'})
        self.assertEqual(self.service.state()['weekly_recent'],0)
        self.service.update(ident,{'status':'new'})
        with self.db() as c:
            c.execute('UPDATE opportunities SET payload=?',(json.dumps({**recent,'published':None}),))
        self.assertEqual(self.service.state()['weekly_recent'],0)


if __name__=='__main__': unittest.main()

class ProviderIntegrationTest(unittest.TestCase):
    def setUp(self):
        import app
        self.app=app
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(app,'DB',Path(self.temp.name)/'test.sqlite'),patch.object(app,'DATA',Path(self.temp.name)),patch.dict(app.os.environ,{'TAVILY_API_KEY':'test-key','SEARXNG_URL':''})]
        for p in self.patches: p.start()
        app.init()

    def tearDown(self):
        self.app.STOP_SEARCH.clear()
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def test_shared_quota_and_independent_cancellation(self):
        app=self.app
        app.STOP_SEARCH.set()
        with patch.object(app,'api_json',return_value={'results':[]}) as network:
            self.assertEqual(app.opportunity_search('test query','tavily','week'),[])
            payload=network.call_args.args[1]
            self.assertEqual(payload['time_range'],'week')
            self.assertFalse(payload['include_raw_content'])
            self.assertIn('linkedin.com',payload['exclude_domains'])
        self.assertEqual(app.search_usage(),1)
        with app.db() as c:
            c.execute('UPDATE search_usage SET requests=30 WHERE day=?',(app.today(),))
        with patch.object(app,'api_json') as network:
            with self.assertRaises(ValueError): app.opportunity_search('test query','tavily')
            network.assert_not_called()

    def test_failed_call_still_reserves_quota(self):
        with patch.object(self.app,'api_json',side_effect=OSError('Unavailable')):
            with self.assertRaises(OSError): self.app.opportunity_search('test query','tavily')
        self.assertEqual(self.app.search_usage(),1)

    def test_stop_company_does_not_stop_opportunities(self):
        self.app.STOP_SEARCH.set()
        self.app.OPPORTUNITIES.stop.clear()
        self.app.OPPORTUNITIES.check_stop()

    def test_policy_prevents_private_network_request(self):
        with patch.object(self.app.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',80))]), patch.object(self.app.socket,'create_connection') as connect:
            with self.assertRaises(ValueError): self.app.opportunity_page('http://example.it/robots.txt',robots=True)
            connect.assert_not_called()
