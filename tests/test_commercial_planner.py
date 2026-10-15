import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from sales.db import Store, now
from sales.research_store import ResearchStore
from sales.discovery_planner import CommercialIntelligencePlanner
from sales.research_discovery import seed_campaign
from sales.prospect_scope import acquisition_exclusion, task_in_scope
from sales.research_triage import triage
from sales.research_analysis import ResearchWeb
from sales.company_research import inspect_company, company_verification
from sales.source_identity import verified_origins
from sales.serper_provider import search, CreditLimit
from sales.search_trial import SerperHTTPError


class CommercialPlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'db.sqlite3');self.s.init()
        self.rs=ResearchStore(self.s);self.c=self.rs.create({'regions':['Veneto'],'projects':['website'],'groups':['direct']})
    def tearDown(self):self.tmp.cleanup()
    def test_alternative_query_without_region_preserves_unknown_location(self):
        from sales.discovery_planner import Planner
        from sales.discovery_relevance import alternative_query
        payload=alternative_query({'url':'https://alfa.example/contatti/',
            'subject':'Alfa Srl','company_host':'alfa.example','region':None})
        self.assertIsNotNone(Planner(self.rs).offer_query(self.c,'companies',payload))
        with self.s.connect() as c:
            saved=json.loads(c.execute("SELECT payload FROM discovery_frontier WHERE kind='search'").fetchone()[0])
        self.assertIsNone(saved['region'])
        self.assertEqual(saved['hypothesis']['territory'],'')
    def test_every_query_has_verifiable_intent_and_survives_scope(self):
        seed_campaign(self.rs,self.c)
        with self.s.connect() as c:rows=c.execute('SELECT * FROM discovery_frontier').fetchall()
        self.assertEqual({r['strategy'] for r in rows},{'companies','explicit'})
        for r in rows:
            p=json.loads(r['payload']);self.assertTrue(p['hypothesis']['required_evidence']);self.assertTrue(p['hypothesis']['counterevidence'])
            self.assertEqual(p['hypothesis']['project'],'website')
            self.assertTrue(task_in_scope(r['kind'],r['strategy'],p,self.c['filters']))
    def test_news_article_read_as_source_publisher_never_prospect(self):
        url='https://corrieredelveneto.corriere.it/economia/2026/alfa-nuova-linea.html'
        payload={'url':url,'strategy':'change','hypothesis':{'id':'change'},'filters':self.c['filters']}
        self.assertIsNone(acquisition_exclusion({'url':url,'title':'Alfa nuova linea'},payload))
        page={'url':url,'status':200,'checked_at':now(),'html':'<title>Alfa lancia una nuova linea</title><main>Alfa Srl di Padova lancia una nuova linea di componenti industriali per il mercato tedesco.</main>'}
        with patch.object(ResearchWeb,'get',return_value=page):r=triage(self.s,payload,lambda:None)
        self.assertTrue(r['resolve']);self.assertEqual(r['details']['identity'],{});self.assertNotEqual(r['state'],'promising')
    def test_original_event_survives_domain_resolution(self):
        text='Alfa Srl di Padova lancia una nuova linea per il mercato tedesco.'
        original={'id':'event','url':'https://news.example/event','text':text,'research_text':text,'official':False}
        p={'url':'https://alfa.example/','subject':'Alfa Srl','subject_quote':text,'source_documents':[original],'filters':self.c['filters'],'root_query_key':'original-search'}
        page={'url':p['url'],'status':200,'checked_at':now(),'html':'<title>Alfa Srl</title><main>Produciamo componenti industriali.</main><footer>Alfa Srl<br>Via Roma 1, 35100 Padova (PD)<br>P.IVA 12345678901<br>info@alfa.example</footer>'}
        with patch.object(ResearchWeb,'get',return_value=page):r=inspect_company(self.s,p,page,lambda:None)
        self.assertTrue(r['details']['company_ready'])
        v=company_verification(p,r);doc=next(d for d in v['source_documents'] if d['id']=='event')
        self.assertFalse(doc['official']);self.assertEqual(doc['research_text'],text)
        self.assertEqual(v['root_query_key'],'original-search')
        from sales.company_research import research_tasks
        children,queries=research_tasks(p,r)
        self.assertTrue(queries)
        self.assertTrue(all(child['root_query_key']=='original-search' for child in children+queries))
    def test_namesake_elsewhere_cannot_borrow_event(self):
        payload={'subject':'Alfa Srl','subject_quote':'Alfa Srl di Torino investe.', 'source_documents':[{'text':'Alfa Srl di Torino investe.'}]}
        docs,limits=verified_origins(payload,{'name':'Alfa Srl','region':'Veneto','location':'35100 Padova'})
        self.assertEqual(docs,[]);self.assertTrue(limits)
    def test_custom_caps_preserved_default_caps_migrated_once(self):
        self.s.configure({'daily_api_limit':30,'monthly_api_limit':100})
        with self.s.connect() as c:c.execute('DELETE FROM research_schema WHERE version=50')
        self.s.init();self.assertIsNone(self.s.settings()['daily_api_limit']);self.assertEqual(self.s.settings()['monthly_api_limit'],100)
        self.s.configure({'daily_api_limit':30});self.s.init();self.assertEqual(self.s.settings()['daily_api_limit'],30)
        self.s.configure({'daily_api_limit':None,'monthly_api_limit':None})
        for _ in range(35):self.s.reserve('serper')
        self.assertEqual(self.s.usage()['today']['serper'],35)
    def test_concurrent_equivalent_queries_charge_once(self):
        self.s.configure({'provider':'serper'})
        with patch('sales.serper_provider.MIN_INTERVAL',0),patch('sales.serper_provider.api_key',return_value='test-key'),patch('sales.serper_provider.transport',return_value={'organic':[]}) as call:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda q:search(self.s,q),['Padova officina','officina Padova','Padova  officina','OFFICINA Padova']))
        self.assertEqual(call.call_count,1);self.assertEqual(self.s.usage()['today']['serper'],1)
        self.assertEqual(sum(not cached for _,cached in results),1)
    def test_provider_exhaustion_is_blocking_no_purchase(self):
        self.s.configure({'provider':'serper'})
        with patch('sales.serper_provider.api_key',return_value='test-key'),patch('sales.serper_provider.transport',side_effect=SerperHTTPError(402,'Serper: crediti esauriti')):
            with self.assertRaises(CreditLimit):search(self.s,'test')
        self.assertEqual(self.s.usage()['today']['serper'],1)

    def test_company_address_and_association_membership_are_not_publishers(self):
        from sales.source_roles import publisher_identity
        for text in ['La sede è nel Comune di Cartigliano.', 'Siamo associati a Confindustria Veneto Est.', 'Lavoriamo per la Camera di Commercio.']:
            page={'url':'https://alfa.example/','html':'<title>Alfa Srl — Officina meccanica</title><main>Produciamo componenti.</main><footer>'+text+'</footer>','status':200,'checked_at':now()}
            self.assertFalse(publisher_identity(page))
        page['html']='<title>Confindustria Veneto Est</title><main>Comunicati delle imprese</main>'
        self.assertTrue(publisher_identity(page))
        page['html']='<title>Economia locale</title><footer>Testata giornalistica, direttore responsabile Mario Rossi.</footer>'
        self.assertTrue(publisher_identity(page))

    def test_literal_article_subject_and_role_extraction(self):
        from sales.source_identity import source_entities
        page={'url':'https://news.example/article','html':'<title>Alfa cresce</title><main>Alfa Srl di Padova lancia una nuova linea di prodotti.</main>','status':200,'checked_at':now()}
        entities=source_entities(page,{'text':'Alfa Srl di Padova lancia una nuova linea di prodotti.'})
        self.assertEqual(entities[0]['name'],'Alfa Srl');self.assertEqual(entities[0]['role'],'COMPANY')
        page['html']='<title>Notizia</title><main>Nessuna impresa identificata.</main>'
        self.assertEqual(source_entities(page,{'text':'Nessuna impresa identificata.'}),[])

    def test_directory_calendar_links_are_never_companies(self):
        from sales.research_analysis import resolve_publisher
        page={'url':'https://directory.example/','status':200,'checked_at':now(),'html':'<title>Elenco aziende</title><main><p><a href="https://www.google.com/calendar/render?cid=webcal">Google Calendar</a></p><p><a href="https://outlook.live.com/owa?path=calendar">Outlook Live</a></p><p><a href="https://alfa.example/">Alfa</a></p></main>'}
        with patch.object(ResearchWeb,'get',return_value=page):
            r=resolve_publisher(self.s,page,{'directory':True,'strategy':'companies'},lambda:None)
        self.assertEqual([x['subject'] for x in r['discovered']],['Alfa'])

    def test_empty_identity_lookup_adapts_once_preserving_full_subject(self):
        planner=CommercialIntelligencePlanner(self.rs)
        p={'query':'"Alessandrin & C. Srl" sito ufficiale Veneto','subject':'Alessandrin & C. Srl','region':'Veneto','page':1,'period':'','source_documents':[{'text':'Fonte conservata'}]}
        fp=planner.offer_query(self.c,'companies',p)
        planner.observed(self.c,{'payload':{**p,'query_key':fp}},[],0)
        self.assertEqual(planner.resolve_pending_subjects(self.c),1)
        self.assertEqual(planner.resolve_pending_subjects(self.c),0)
        with self.s.connect() as c:
            alternate=json.loads(c.execute('SELECT payload FROM discovery_frontier ORDER BY id DESC LIMIT 1').fetchone()[0])
        self.assertEqual(alternate['subject'],p['subject']);self.assertEqual(alternate['source_documents'],p['source_documents'])
        self.assertEqual(alternate['query'],'Alessandrin Veneto azienda contatti')
        planner.observed(self.c,{'payload':alternate},[],0)
        self.assertEqual(planner.resolve_pending_subjects(self.c),0)

    def test_identity_retry_does_not_spend_on_technical_failure_or_after_stop(self):
        from sales.research_funnel import Funnel
        planner=CommercialIntelligencePlanner(self.rs)
        p={'query':'"Alfa Srl" sito ufficiale','subject':'Alfa Srl','region':'Veneto','page':1,'period':''}
        fp=planner.offer_query(self.c,'companies',p);url='https://alfa.example/'
        Funnel(self.rs).transition(self.c,{'url':url},'unverifiable','HTTP 503')
        planner.observed(self.c,{'payload':{**p,'query_key':fp}},[url],1)
        self.assertEqual(planner.resolve_pending_subjects(self.c),0)
        with self.s.connect() as c:self.assertEqual(c.execute('SELECT decision FROM discovery_queries WHERE fingerprint=?',(fp,)).fetchone()[0],'technical')
        p={**p,'query':'"Beta Srl" sito ufficiale','subject':'Beta Srl'}
        fp=planner.offer_query(self.c,'companies',p)
        planner.observed(self.c,{'payload':{**p,'query_key':fp}},[],0)
        self.rs.stop(self.c['id'])
        self.assertEqual(planner.resolve_pending_subjects(self.c),0)
        with self.s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM discovery_queries').fetchone()[0],2)
