import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from sales.db import Store,now
from sales.company_research import directory_profiles,directory_names
from sales.research_analysis import resolve_publisher,ResearchWeb
from sales.research_triage import triage
from sales.research_store import ResearchStore
from sales.source_catalog import seed_directories

class SectorDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'db');self.s.init()
    def tearDown(self):self.tmp.cleanup()
    def page(self,html,url='https://directory.example/regione/veneto'):
        return {'url':url,'html':html,'status':200,'checked_at':now()}
    def test_structured_image_links_need_visible_name_and_actual_link(self):
        schema=[{'@type':'LocalBusiness','name':'Alfa Srl','url':'https://directory.example/fornitori/alfa'},
                {'@type':'LocalBusiness','name':'Finta Srl','url':'https://directory.example/fornitori/finta'}]
        p=self.page('<title>Officine in Veneto</title><script type="application/ld+json">'+json.dumps(schema)+'</script><main><p>Alfa Srl</p><a href="/fornitori/alfa"><img src="x"></a></main>')
        self.assertEqual(directory_profiles(p),[{'url':'https://directory.example/fornitori/alfa','name':'Alfa Srl'}])
    def test_profiles_take_priority_over_publisher_external_links(self):
        p=self.page('<title>Elenco aziende</title><main><p><a href="/aziende/alfa">Alfa Srl</a></p><p><a href="/aziende/grande">Grande Spa</a></p><p><a href="https://giornale.example">Giornale</a></p></main>')
        r=resolve_publisher(self.s,p,{'directory':True,'region':'Veneto'},lambda:None)
        self.assertEqual([x['directory_subject'] for x in r['discovered']],['Alfa Srl'])
        self.assertEqual(r['excluded_names'],['Grande Spa'])
        self.assertEqual(r['discovered'][0]['region'],'Veneto')
    def test_directory_profile_routes_even_without_directory_keywords(self):
        p=self.page('<title>Alfa Srl</title><main>Alfa Srl — Padova</main>','https://directory.example/fornitori/alfa')
        with patch.object(ResearchWeb,'get',return_value=p):r=triage(self.s,{'url':p['url'],'company_stage':'identify','publisher':True,'directory':True,'directory_subject':'Alfa Srl'},lambda:None)
        self.assertTrue(r['resolve']);self.assertFalse(r['details']['identity'])
    def test_plain_names_all_retained_except_excluded_legal_forms(self):
        p=self.page('<title>Elenco aziende</title><main>'+''.join('<p>Molino '+str(i)+' Srl</p><p>Padova Veneto</p>' for i in range(8))+'<p>Grande Spa</p></main>')
        r=resolve_publisher(self.s,p,{'directory':True,'region':'Veneto'},lambda:None)
        self.assertEqual(len(r['resolve_queries']),8);self.assertEqual(r['excluded_names'],['Grande Spa'])
    def test_profile_generic_site_link_scoped_to_only_the_named_company(self):
        p=self.page('<title>Alfa Srl</title><main><p>Alfa Srl di Padova</p><a href="https://ar-industria.example">Sito web</a><p><a href="https://vendor.example">Vendor</a></p></main>')
        r=resolve_publisher(self.s,p,{'directory':True,'directory_depth':1,'directory_subject':'Alfa Srl','region':'Veneto'},lambda:None)
        self.assertEqual([(x['subject'],x['url']) for x in r['discovered']],[('Alfa Srl','https://ar-industria.example')])
    def test_catalog_seed_idempotent_and_scoped(self):
        rs=ResearchStore(self.s);c=rs.create({'regions':['Veneto'],'target':'b2b','groups':['direct']})
        self.assertEqual(seed_directories(rs,c),3);self.assertEqual(seed_directories(rs,c),0)
        c['filters']['target']='services';self.assertEqual(seed_directories(rs,c),0)
    def test_additional_regions_seed_only_selected_territories(self):
        rs=ResearchStore(self.s);campaign=rs.create({'regions':['Piemonte','Toscana'],'target':'b2b','groups':['direct']})
        self.assertEqual(seed_directories(rs,campaign),2)
        with self.s.connect() as c:payloads=[json.loads(r[0]) for r in c.execute('SELECT payload FROM discovery_frontier')]
        self.assertEqual({p['region'] for p in payloads},{'Piemonte','Toscana'})
        self.assertTrue(all(p['publisher'] and p['directory'] for p in payloads))

    def test_own_company_navigation_is_not_a_directory(self):
        p=self.page('<title>Alfa Srl</title><main>Produciamo componenti industriali.<p><a href="/azienda/storia">La nostra storia</a></p><p><a href="/azienda/contatti">Contatti</a></p><p><a href="/azienda/parco-macchine">Parco macchine</a></p></main><footer>Alfa Srl<br>Via Roma 1, 35100 Padova (PD)<br>P.IVA 12345678901<br>info@directory.example</footer>','https://directory.example/')
        self.assertEqual(directory_profiles(p),[])
        with patch.object(ResearchWeb,'get',return_value=p):r=triage(self.s,{'url':p['url'],'strategy':'companies','filters':{'target':'b2b','regions':['Veneto']}},lambda:None)
        self.assertFalse(r.get('resolve'));self.assertTrue(r['details']['company_ready'])

    def test_identity_search_prioritizes_company_ahead_of_registries(self):
        from sales.company_research import acquisition_rank
        official={'url':'https://alessandrin.it/','title':'Alessandrin officina meccanica'}
        registry={'url':'https://registroaziende.it/azienda/alessandrin-c-srl','title':'Alessandrin & C Srl'}
        self.assertGreater(acquisition_rank(official,subject='Alessandrin & C. Srl'),acquisition_rank(registry,subject='Alessandrin & C. Srl'))
