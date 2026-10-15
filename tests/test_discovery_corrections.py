import json
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store, now
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.providers import PublicWeb
from sales.access_status import AccessIssue, describe, retry_delay
from sales.discovery_relevance import preflight, subject_exclusion, alternative_query
from sales.research_analysis import document, resolve_publisher, LocalResearcher, ResearchWeb
from sales.research_triage import triage
from sales.discovery_trace import paths


class DiscoveryCorrectionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.db');self.store.init()

    def page(self, text, date='2020-01-01'):
        return {'url':'https://editore.example/alfa','status':200,'checked_at':now(),
            'html':'<title>Alfa Srl investe</title><meta property="article:published_time" content="'+date+'">'
            '<script type="application/ld+json">{"@type":"Article","headline":"Alfa Srl investe"}</script>'
            '<div class="td-post-content">'+text+'</div>'}

    def test_archival_pdf_never_downloaded_but_company_catalogue_retained(self):
        url='http://asa.archiviostudiadriatici.it/islandora/object/libria:37336/datastream/PDF/content/libria.pdf'
        with patch.object(ResearchWeb,'get',side_effect=AssertionError('No download')):
            result=triage(self.store,{'url':url},lambda:None)
        self.assertEqual(result['state'],'rejected');self.assertTrue(result['details']['prefetch_rejection'])
        self.assertIsNone(preflight({'url':'https://alfa.example/catalogo-2020.pdf'}, {'company_host':'alfa.example'}))
        self.assertIsNone(preflight({'url':'https://ente.example/capitolato-sito-web.pdf'}, {'strategy':'tender'}))

    def test_unrelated_name_and_dealer_do_not_resolve_brand_identity(self):
        self.assertIsNotNone(preflight({'url':'https://dealer.example/brand/leapmotor','title':'Concessionario Leapmotor'}, {'subject':'Leapmotor'}))
        self.assertIsNone(preflight({'url':'https://leapmotor.example/','title':'Leapmotor sito ufficiale'}, {'subject':'Leapmotor'}))
        self.assertIsNotNone(preflight({'url':'https://example.com/aqua-optima','title':'Aqua Optima filtri'}, {'subject':'Aquaopti'}))
        self.assertIsNotNone(preflight({'url':'https://dgt.mef.gov.it/normativa-ptt','title':'SIGIT processo tributario'}, {'subject':'SIGIT'}))
        self.assertIsNone(preflight({'url':'https://xy.example/','title':'Sito'}, {'subject':'Alfa','official_link':True}))

    def test_names_are_not_automatically_companies(self):
        for name, text in [('MIMIT',''),('SIGIT S.p.A.',''),('Aquaopti','Ferroli cresce con Aquaopti, la nuova gamma di scaldacqua.'),('Stellantis','Stellantis investe 60 miliardi.'),('Mario Rossi','Il ministro Mario Rossi annuncia il piano.')]:
            self.assertTrue(subject_exclusion(name,[{'title':text,'text':text}]),name)
        self.assertIsNone(subject_exclusion('Alfa Srl',[{'text':'Alfa Srl presenta una nuova gamma di prodotti.'}]))
        self.assertIsNone(subject_exclusion('Alfa Srl',[{'text':'Alfa Srl fornisce prodotti alla multinazionale Stellantis che investe 60 miliardi.'}]))

    def test_old_article_identifies_company_without_current_need(self):
        page=self.page('<p><a href="https://alfa.example/">Alfa Srl</a> investe in una nuova linea di prodotti a Padova.</p>')
        with patch.object(ResearchWeb,'get',return_value=page),patch.object(LocalResearcher,'call',side_effect=AssertionError('Explicit link')):
            result=triage(self.store,{'url':page['url'],'publisher':True,'strategy':'change'},lambda:None)
            resolved=resolve_publisher(self.store,page,{'strategy':'change'},lambda:None)
        self.assertTrue(result['resolve']);self.assertNotEqual(result['state'],'promising')
        self.assertEqual(resolved['discovered'][0]['subject'],'Alfa Srl')
        self.assertTrue(resolved['documents'][0]['discovery_only'])
        self.assertEqual(resolved['documents'][0]['published_at'][:4],'2020')

    def test_newspaper_body_excludes_other_article_subjects(self):
        for css in ('td-post-content','content-to-read'):
            p=self.page('<p>Alfa Srl investe a Padova.</p>').copy()
            p['html']=p['html'].replace('td-post-content',css)+'<div class="single-art__content">Beta Srl lancia un marchio.</div>'
            d=document(p);self.assertNotIn('Beta',d['research_text']);self.assertIn('Beta',d['text'])
        p=self.page('<p>Alfa Srl investe a Padova.</p><div class="single-art__content">Beta Srl investe in nuovi servizi.</div>')
        self.assertNotIn('Beta',document(p)['research_text']);self.assertIn('Beta',document(p)['text'])

    def test_excluded_protagonist_does_not_expand_into_partner_network(self):
        p=self.page('<p>Stellantis: 60 miliardi di investimenti.</p><p>Dongfeng presenta nuovi prodotti.</p>',now())
        p['html']=p['html'].replace('Alfa Srl investe','Stellantis: 60 miliardi')
        with patch.object(LocalResearcher,'call',return_value={'companies':[
            {'name':'Stellantis','quote':'Stellantis: 60 miliardi di investimenti.'},
            {'name':'Dongfeng','quote':'Dongfeng presenta nuovi prodotti.'}]}):
            result=resolve_publisher(self.store,p,{'strategy':'change'},lambda:None)
        self.assertEqual(result['resolve_queries'],[])
        self.assertEqual(len(result['excluded_names']),2)

    def test_robots_statuses_are_distinct_and_failure_is_cached(self):
        for status,code,retry in [(403,'robots_unverifiable',False),(429,'robots_temporary',True),(503,'robots_temporary',True)]:
            web=PublicWeb(self.store);host=f'https://site{status}.example'
            with patch.object(web,'_raw',return_value={'status':status,'html':''}) as fetch:
                for suffix in ('/a','/b'):
                    with self.assertRaises(AccessIssue) as cm:web.policy(host+suffix)
                    self.assertEqual(cm.exception.code,code);self.assertEqual(cm.exception.retryable,retry)
                self.assertEqual(fetch.call_count,1)
        web=PublicWeb(self.store)
        with patch.object(web,'_raw',return_value={'status':200,'html':'User-agent: *\nDisallow: /private'}):
            with self.assertRaises(AccessIssue) as cm:web.policy('https://blocked.example/private')
        self.assertEqual(cm.exception.code,'robots_denied')
        web=PublicWeb(self.store)
        with patch.object(web,'_raw',return_value={'status':404,'html':''}):web.policy('https://missing.example/a')

    def test_html_challenge_and_timeout_do_not_authorize_access(self):
        for raw in ({'status':200,'html':'<!DOCTYPE html><html>Login</html>'}, TimeoutError('timed out')):
            web=PublicWeb(self.store)
            with patch.object(web,'_raw',side_effect=raw if isinstance(raw,Exception) else None,return_value=raw):
                with self.assertRaises(AccessIssue) as cm:web.policy('https://'+('timeout' if isinstance(raw,Exception) else 'html')+'.example/a')
            self.assertIn(cm.exception.code,('robots_unverifiable','robots_temporary'))

    def test_ssl_certificate_failure_stops_further_origin_requests(self):
        web=PublicWeb(self.store)
        with patch.object(web,'_raw',side_effect=ssl.SSLCertVerificationError('unable to get local issuer certificate')) as fetch:
            for path in ('/contatti','/document.pdf'):
                with self.assertRaises(ssl.SSLCertVerificationError) as cm:web.get('https://cert.example'+path)
                self.assertEqual(describe(cm.exception)['code'],'tls_certificate')
            self.assertEqual(fetch.call_count,1)
        self.assertTrue(ssl.create_default_context().check_hostname)
        self.assertEqual(ssl.create_default_context().verify_mode,ssl.CERT_REQUIRED)

    def test_retry_honors_origin_backoff_and_alternative_stays_on_subject(self):
        rs=ResearchStore(self.store);c=rs.create();rs.enqueue(c['id'],'candidate','change',{'url':'https://alfa.example/'})
        task=rs.claim(c['id'],c['generation']);issue=describe(AccessIssue('robots_temporary','offline',retryable=True,delay=300))
        rs.task_done(task['id'],'offline',retry=True,retry_at=issue['retry_at'])
        self.assertIsNone(rs.claim(c['id'],c['generation']))
        p={'url':'https://alfa.example/','subject':'Alfa Srl','company_host':'alfa.example'}
        alt=alternative_query(p);self.assertIn('"Alfa Srl"',alt['query']);self.assertIn('-site:alfa.example',alt['query'])
        self.assertIsNone(alternative_query({**p,**alt}))
        self.assertIsNone(alternative_query({'url':'https://unidentified.example/'}))

    def test_retry_after_and_origin_throttle_prevent_repeated_requests(self):
        self.assertEqual(retry_delay('900'),900)
        with patch('sales.access_status.time.time',return_value=0):
            self.assertEqual(retry_delay('Thu, 01 Jan 1970 00:20:00 GMT'),1200)
        web=PublicWeb(self.store)
        with patch.object(web,'_raw',return_value={'status':429,'retry_after':'900'}) as fetch:
            for path in ('/a','/b'):
                with self.assertRaises(AccessIssue) as cm:web.get('https://busy.example'+path)
                self.assertEqual(cm.exception.code,'http_temporary');self.assertGreater(cm.exception.delay,890)
            self.assertEqual(fetch.call_count,1)

    def test_trace_preserves_query_decision_and_prefetch_rejection(self):
        rs=ResearchStore(self.store);c=rs.create();f=Funnel(rs)
        payload={'url':'https://alfa.example/','query':'produttori Padova','strategy':'companies','subject':'Alfa Srl'}
        f.offer(c['id'],'candidate','companies',payload,'first')
        f.transition(c,payload,'needs_review','Bisogno da dimostrare',{'identity':{'name':'Alfa Srl','website':payload['url'],'identity_status':'verified'}})
        rs.event(c['id'],'acquisition_filter','Escluso prima della lettura',details={'query':'produttori Padova','discarded':[{'url':'https://archive.org/stream/book','reason':'Archivio storico'}]})
        report=paths(self.store,c['id']);self.assertEqual(report['total'],2)
        self.assertEqual(report['items'][0]['query'],payload['query']);self.assertIsNone(report['items'][0]['qualification'])
        self.assertEqual(report['items'][0]['company'],'Alfa Srl');self.assertFalse(report['items'][1]['visited'])
        self.assertEqual(paths(self.store,c['id'],1,1)['items'],[report['items'][1]])
