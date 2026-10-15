import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sales.db import Store, now
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.research_analysis import ResearchWeb, LocalResearcher, inspect_candidate
from sales.research_triage import triage
from sales.company_research import company_queries, selected_strategies, research_tasks, verification_priority
from sales.discovery_planner import Planner
from sales.research_discovery import search


class CompanyResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'test.sqlite3'); self.store.init()
        self.rs = ResearchStore(self.store)
        self.c = self.rs.create({'regions':['Veneto'], 'projects':['website'], 'groups':['direct'], 'target':'b2b'})
        self.payload = {'url':'https://alfa.example/', 'strategy':'companies', 'filters':self.c['filters']}

    def tearDown(self): self.tmp.cleanup()

    def page(self, content='Realizziamo impianti industriali.', url='https://alfa.example/', title='Alfa Srl', address='35100 Padova (PD)', legal=True):
        footer = f'<footer><p>{title}</p><p>Via Roma 2, {address}</p><p>P.IVA 12345678901</p><a href="mailto:info@alfa.example">info@alfa.example</a></footer>' if legal else ''
        return {'url':url, 'status':200, 'checked_at':now(), 'html':f'<title>{title}</title><main>{content}</main>'+footer}

    def check(self, page, payload=None):
        with patch.object(ResearchWeb, 'get', return_value=page), patch.object(LocalResearcher, 'call', side_effect=AssertionError('No LLM in identity screening')):
            return triage(self.store, payload or self.payload, lambda:None)

    def test_real_company_without_event_survives_but_is_not_an_opportunity(self):
        r = self.check(self.page())
        self.assertEqual(r['state'], 'needs_review')
        self.assertTrue(r['details']['company_ready'])
        self.assertIsNone(r['details']['budget'])
        self.assertNotIn('assessment', r)
        self.assertEqual(r['details']['identity']['region'], 'Veneto')

    def test_contact_page_completes_identity_before_keyword_rejection(self):
        home = self.page('Realizziamo impianti industriali. <a href="/contatti">Contatti</a>', legal=False)
        contact = self.page(url='https://alfa.example/contatti')
        with patch.object(ResearchWeb, 'get', side_effect=[home,contact]):
            r=triage(self.store,self.payload,lambda:None)
        self.assertTrue(r['details']['company_ready'])

    def test_unknown_identity_never_seeds_company_queries(self):
        r=self.check(self.page(legal=False))
        self.assertFalse(r['details']['company_ready'])
        self.assertEqual(research_tasks(self.payload,r),([],[]))

    def test_supplier_and_disallowed_region_excluded_before_model(self):
        for page in [self.page('Siamo sviluppatori e offriamo sviluppo siti per impianti industriali.',title='Realizzazione siti web Alfa'),self.page(address='80100 Napoli (NA)'), self.page(title='Alfa S.p.A.')]:
            r=self.check(page)
            self.assertNotEqual(r['state'],'promising')
            self.assertFalse(r['details'].get('company_ready'))

    def test_client_footer_web_credit_does_not_make_it_a_supplier(self):
        r=self.check(self.page('Realizziamo impianti industriali.<p>Website by: Realizzazione siti web Rossi</p>'))
        self.assertTrue(r['details']['company_ready'])

    def test_own_activity_required_not_only_region(self):
        r=self.check(self.page('Studio legale. Assistenza giudiziale.'))
        self.assertFalse(r['details']['company_ready'])

    def test_directory_is_source_never_a_buyer(self):
        r=self.check(self.page('Elenco aziende associate <a href="https://beta.example/">Beta</a>',title='Elenco aziende associate'))
        self.assertTrue(r['resolve']);self.assertTrue(r['details']['publisher'])
        self.assertNotEqual(r['state'],'promising')

    def test_followups_are_company_scoped_repeatable_and_not_premature_promotion(self):
        r=self.check(self.page('Realizziamo impianti industriali.<a href="/nuovi-servizi">Nuovi servizi</a>'))
        planner=Planner(self.rs)
        planner.follow_company(self.c,self.payload,r);planner.follow_company(self.c,self.payload,r)
        with self.store.connect() as c:
            rows=c.execute('SELECT kind,payload FROM discovery_frontier').fetchall()
        self.assertEqual(len(rows),5)
        checks=[json.loads(x['payload']) for x in rows if x['kind']=='verify']
        self.assertEqual(len(checks),1)
        self.assertEqual(checks[0]['company_host'],'alfa.example')
        queries=[json.loads(x['payload']) for x in rows if x['kind']=='search']
        self.assertTrue(all(q['query'].startswith('site:alfa.example ') for q in queries))
        self.assertTrue(all('progetto digitale' not in q['query'] for q in queries))
        self.assertEqual(research_tasks({**self.payload,'followup_depth':1},r),([],[]))
        self.assertEqual(self.rs.campaign()['qualified'],0)

    def test_stop_rejects_late_followups(self):
        r=self.check(self.page());self.rs.stop(self.c['id'])
        Planner(self.rs).follow_company(self.c,self.payload,r)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM discovery_frontier').fetchone()[0],0)

    def test_resume_investigates_existing_company_without_duplicate_review(self):
        r=self.check(self.page())
        Funnel(self.rs).transition(self.c,self.payload,r['state'],r['reason'],r['details'])
        planner=Planner(self.rs)
        self.assertEqual(planner.restore_company_reviews(self.c),1)
        self.assertEqual(planner.restore_company_reviews(self.c),0)
        with self.store.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM discovery_frontier WHERE kind='verify'").fetchone()[0],1)

    def test_company_query_does_not_require_buying_keywords_and_expands_places(self):
        queries=list(company_queries('Veneto'))
        self.assertTrue(any('Padova' in q for q in queries))
        self.assertTrue(any('impiantistica' in q for q in queries))
        self.assertFalse(any('associati' in q for q in queries))
        self.assertFalse(any('sito web' in q or 'cerchiamo' in q for q in queries))
        self.assertEqual(len(queries),len(set(queries)))
        self.assertEqual(selected_strategies(self.c['filters']),('companies','explicit'))

    def test_verified_business_ranked_ahead_of_editorial_result(self):
        company={'details':{'identity':{'identity_status':'verified','region':'Veneto','contacts':[{}]}}}
        self.assertGreater(verification_priority(company),verification_priority({'details':{'publisher':True}}))

    def test_publisher_resolution_does_not_need_oversized_homepage(self):
        article=self.page('Nuova linea prodotti <a href="https://beta.example/">Beta</a>',url='https://alfa.example/notizia')
        calls=[]
        def get(web,url):
            calls.append(url)
            if url!=article['url']:raise AssertionError('Publisher homepage must not be fetched')
            return article
        with patch.object(ResearchWeb,'get',get):
            r=inspect_candidate(self.store,{'url':article['url'],'publisher':True,'directory':True},lambda:None)
        self.assertTrue(r['publisher']);self.assertEqual(len(r['discovered']),1)
        self.assertEqual(calls,[article['url']])

    def test_search_keeps_company_context_and_does_not_follow_foreign_results(self):
        r=self.check(self.page());_,queries=research_tasks(self.payload,r)
        response={'results':[{'url':'https://alfa.example/novita'},{'url':'https://unrelated.example/'}]}
        with patch('sales.discovery_control.search_capabilities',return_value={'paging':True,'time_range':True}),patch.dict('os.environ',{'SEARXNG_URL':'http://127.0.0.1:8888'}),patch('sales.research_discovery.api_json',return_value=response),patch('sales.research_discovery._last_search',0):
            search(self.rs,self.c,{'strategy':'change','payload':queries[0]},lambda:None)
        with self.store.connect() as c:rows=c.execute("SELECT payload FROM discovery_frontier WHERE kind='candidate'").fetchall()
        self.assertEqual(len(rows),1)
        p=json.loads(rows[0][0]);self.assertEqual(p['company_host'],'alfa.example');self.assertTrue(p['official_link'])

    def test_target_counter_counts_companies_not_pages(self):
        r=self.check(self.page());f=Funnel(self.rs)
        for url in ('https://alfa.example/','https://alfa.example/contatti'):
            f.transition(self.c,{**self.payload,'url':url},r['state'],r['reason'],r['details'])
        self.assertEqual(self.rs.campaign()['target_companies'],1)
        self.assertEqual(self.rs.campaign()['qualified'],0)

    def test_confirmed_dismissal_prevents_investigation(self):
        with patch.object(self.store,'target_exclusion',return_value={'reason':'Eliminata manualmente'}),patch.object(ResearchWeb,'get',side_effect=AssertionError('No request for suppressed domain')):
            r=triage(self.store,self.payload,lambda:None)
        self.assertEqual(r['state'],'rejected')

    def test_redirect_aliases_do_not_duplicate_company_documents(self):
        page=self.page(url='https://alfa.example/it/')
        r=self.check(page)
        self.assertEqual(len(r['details']['company_documents']),1)

    def test_empty_title_can_use_literal_standalone_legal_name(self):
        page=self.page('Realizziamo impianti industriali.',title='')
        page['html']=page['html'].replace('<footer>','<footer><p>ALFA IMPIANTI S.R.L.</p>')
        r=self.check(page)
        self.assertTrue(r['details']['company_ready'])
        self.assertEqual(r['details']['identity']['name'],'ALFA IMPIANTI S.R.L.')

    def test_province_at_end_of_address_is_not_lost_to_next_navigation_line(self):
        page=self.page(address='35040 Urbana PD')
        page['html']=page['html'].replace('Urbana PD</p>','Urbana PD</p><p>Chiama ora</p><p>Contatti</p>')
        self.assertEqual(self.check(page)['details']['identity']['region'],'Veneto')

    def test_labelled_primary_office_is_not_lost_because_of_secondary_branch(self):
        page=self.page('<p>Sede Operativa</p><p>Viale Industria 28</p><p>35010 Curtarolo PD</p><p>Filiale</p><p>Via Fossati 9</p><p>33170 Pordenone PN</p><p>Produciamo impianti industriali.</p>')
        r=self.check(page)
        self.assertEqual(r['details']['identity']['region'],'Veneto')
        self.assertTrue(r['details']['company_ready'])
        # Without a primary label, conflicting own locations remain unknown.
        ambiguous={**page,'html':page['html'].replace('Sede Operativa','Ufficio')}
        self.assertIsNone(self.check(ambiguous)['details']['identity']['region'])

    def test_technical_consultant_is_not_excluded_for_offering_finance_support(self):
        r=self.check(self.page('Siamo uno studio di ingegneria. Offriamo consulenza per finanza agevolata.'))
        self.assertTrue(r['details']['company_ready'])

    def test_directory_can_follow_public_profiles_without_inventing_websites(self):
        html='Elenco aziende associate '+''.join(f'<a href="/azienda/alfa-{n}">Alfa {n} Srl</a>' for n in range(3))
        page=self.page(html,url='https://directory.example/elenco')
        with patch.object(ResearchWeb,'get',return_value=page),patch.object(LocalResearcher,'call',side_effect=AssertionError('Public links do not need model')):
            r=inspect_candidate(self.store,{'url':page['url'],'publisher':True,'directory':True,'strategy':'companies'},lambda:None)
        self.assertEqual(len(r['discovered']),3)
        self.assertTrue(all(x['publisher'] and x['directory_depth']==1 for x in r['discovered']))

    def test_encyclopedia_is_not_investigated_as_a_business(self):
        page=self.page('Ingegneria industriale.',title='Ingegneria - Wikipedia',legal=False)
        with patch.object(ResearchWeb,'get',side_effect=[page]) as get:
            r=triage(self.store,self.payload,lambda:None)
        self.assertEqual(r['state'],'rejected');self.assertEqual(get.call_count,1)

    def test_welding_quality_is_not_a_tender_or_digital_need(self):
        page=self.page('La prefabbricazione garantisce qualità. Il nostro staff è una garanzia. Collaboriamo con i clienti.')
        payload={**self.payload,'strategy':'change','company_host':'alfa.example'}
        with patch.object(ResearchWeb,'get',return_value=page):r=triage(self.store,payload,lambda:None)
        self.assertNotEqual(r['state'],'promising')
        self.assertNotIn('tender',r['details']['strategies'])

    def test_directory_restrictions_stop_resolution(self):
        page=self.page('<a href="/termini">Termini di uso</a><a href="https://beta.example/">Beta</a>')
        terms=self.page('È vietata la raccolta automatizzata dei dati.',url='https://alfa.example/termini')
        with patch.object(ResearchWeb,'get',side_effect=[page,terms]),self.assertRaisesRegex(ValueError,'esclude'):
            inspect_candidate(self.store,{'url':page['url'],'publisher':True,'directory':True},lambda:None)

    def test_structured_directory_names_require_visible_confirmation(self):
        schema={'@type':'ItemList','itemListElement':[{'@type':'LocalBusiness','name':n} for n in ('Beta Srl','Gamma Srl','Delta Srl','Inventata Srl')]}
        page=self.page('Beta Srl\nPadova PD\nGamma Srl\nVicenza VI\nDelta Srl\nTreviso TV',title='Fornitori in Veneto')
        page['html']+='<script type="application/ld+json">'+json.dumps(schema)+'</script>'
        result=self.check(page)
        self.assertTrue(result['details']['publisher'])
        with patch.object(ResearchWeb,'get',return_value=page):
            resolved=inspect_candidate(self.store,{**self.payload,'publisher':True,'directory':True},lambda:None)
        self.assertEqual(len(resolved['resolve_queries']),3)
        self.assertNotIn('Inventata',str(resolved['resolve_queries']))

    def test_named_directory_subject_cannot_be_replaced_by_different_company(self):
        r=self.check(self.page(),{**self.payload,'subject':'Gamma Impianti'})
        self.assertFalse(r['details']['company_ready'])

    def test_url_in_site_name_does_not_override_literal_company_name(self):
        page=self.page(title='Contatti - Alfa Srl')
        page['html']='<meta property="og:site_name" content="https://alfa.example/">'+page['html']
        r=self.check(page)
        self.assertEqual(r['details']['identity']['name'],'Alfa Srl')

    def test_verified_company_does_not_become_publisher_due_to_footer_word(self):
        page=self.page('Nuova linea prodotti. <footer>Redazione dei documenti a cura di Alfa.</footer>')
        r=self.check(page,{**self.payload,'strategy':'change','company_host':'alfa.example'})
        self.assertFalse(r['details']['publisher'])

    def test_unknown_target_is_rejected_by_api(self):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        with self.assertRaisesRegex(ValueError,'Segmento'):
            self.rs.create({'target':'invented'})
