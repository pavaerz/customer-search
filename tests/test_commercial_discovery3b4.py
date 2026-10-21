"""3B.4 provenance: Historical = snapshot/replay; Synthetic = fixture/mock."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts.replay_commercial3b4 import load,replay
from sales.commercial.discovery import assess
from sales.commercial.target_fit import evaluate,source_role
from sales.commercial.request_profile import hosted_request,agency_signal,startup_type,freshness
from sales.commercial.commercial_gate import sufficient,SKIP
from sales.commercial.intent import classify_block,request_clause
from sales.commercial.catalog import plan,PILOT,BUDGETS
from sales.commercial.browser import adaptive_phase_limit,audit_state

class Historical34(unittest.TestCase):
    """Saved originals and partial replay; no simulated campaign presented as real."""
    @classmethod
    def setUpClass(cls):cls.x=load();cls.r=replay()
    def item(self,needle):return next(d for d in self.x['commercial_discovery'] if needle in d['url'])
    def revised(self,needle):
        d=self.item(needle);return assess(d['body'],d['engine'],d['body'].get('origin'))
    def test_prada_group_preflight(self):self.assertEqual(self.revised('pradagroup')['decision'],'exclude')
    def test_fab_documented_size_not_audit(self):
        t=next(t for t in self.r['replay']['target_fit'] if t['revision']==851)['target_fit']
        self.assertFalse(t['audit_allowed']);self.assertEqual(t['size']['employees'],630)
    def test_prototal_migration_counterproof(self):
        t=next(t for t in self.r['replay']['target_fit'] if t['revision']==855)['target_fit']
        self.assertFalse(t['audit_allowed']);self.assertIn('existing_new_platform',[f['kind'] for f in t['counterevidence']])
    def test_database_directory_portal_cluster(self):
        for host,role in [('bancomail.it','database_provider'),('ufficiocamerale.it','company_information_portal'),('furnishingidea.it','sector_portal'),('archiproducts.com','directory'),('marche-manufacturing.it','cluster')]:
            with self.subTest(host=host):
                d=self.revised(host);self.assertEqual(d['decision'],'exclude');self.assertEqual(d['commercial_source_role'],role)
    def test_loris_not_web_buyer(self):self.assertEqual(self.revised('loris-maroli')['decision'],'exclude')
    def test_photosi_related_snippet_not_primary_role(self):self.assertEqual(self.revised('4475474899')['decision'],'exclude')
    def test_pronesis_shopify_not_request(self):
        a=next(a for a in self.x['commercial_ai_executions'] if a['id']==32)
        r=next(r['body'] for r in self.x['commercial_revisions'] if r['id']==853)
        self.assertIsNone(request_clause('Pronesis diventa partner della piattaforma E-Commerce Shopify'))
        self.assertFalse(sufficient('FREELANCE',r,a['body']['evidence'])['allowed'])
    def test_geminit_ambiguous_contact(self):
        p=self.x['pages']['https://www.geminit.it/contatti/']
        from sales.extract import parse_page
        self.assertEqual(agency_signal(parse_page(p)['text']),'C_INDIRECT_AMBIGUOUS')
    def test_calab_distinct_publisher_and_historical_fulltime(self):
        p=self.x['pages']['https://www.reggiotoday.it/annunci/co-founder-cto-5p8e9.job'];a=hosted_request(p)
        self.assertEqual(a['requesting_actor'],'CaLab Ai');self.assertNotEqual(a['publisher'],'CaLab Ai')
        self.assertEqual(a['freshness']['publication_date'],'2025-11-04');self.assertTrue(a['employment_full_time']);self.assertEqual(a['request_type'],'TECHNICAL_COFOUNDER')
    def test_six_saved_ai_bundles_skipped(self):
        rows=self.r['replay']['ai_gates'];self.assertEqual(len(rows),6)
        self.assertTrue(all(not g['saved_bundle_gate']['allowed'] for g in rows))
    def test_replay_never_promotes_or_measures(self):
        self.assertIsNone(self.r['new_opportunities_verified']);self.assertEqual(self.r['external_calls'],0)
        self.assertEqual(self.r['replay']['historical_audits_no_longer_selected'],2)
    def test_counterproof_preserved_in_reselection(self):
        gs=self.r['replay']['ai_gates']
        self.assertTrue(all(g['counterproof_selected']>0 for g in gs if g['id'] in (30,34)))

class Synthetic34(unittest.TestCase):
    """Synthetic originals, deterministic helpers and mocked HTTP; no external IO."""
    def page(self,text):
        from test_commercial_engines import page
        return page(text,url='https://alfa.example/')
    def identity(self,p):
        from sales.commercial.attribution import identity
        return identity([p])
    def test_unknown_size_is_not_large(self):
        p=self.page('Produciamo serramenti su misura. Il nostro catalogo comprende prodotti per clienti aziendali.');f=evaluate(self.identity(p),[p],{'eligible':True})
        self.assertTrue(f['audit_allowed'],f);self.assertEqual(f['size']['status'],'UNKNOWN');self.assertIsNone(f['budget']);self.assertIsNone(f['purchase_intent'])
    def test_large_size_deprioritizes_without_universal_rejection(self):
        from sales.db import Store
        from sales.commercial.inspection import inspect
        p=self.page('Produciamo componenti specializzati su misura. Abbiamo 300 lavoratori.')
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db');store.init()
            with patch('sales.commercial.inspection.ResearchWeb.get',return_value=p),patch('sales.commercial.browser.review',side_effect=AssertionError('Audit quota must be preserved')):
                r=inspect(store,{'url':p['url'],'commercial_engine':'WEBSITE_REBUILD'})['result']
            self.assertEqual(r['target_fit']['status'],'LOW_PRIORITY');self.assertEqual(r['state'],'NEEDS_REVIEW')
            self.assertEqual(r['audit_state'],'NOT_EXECUTED')
    def test_missing_contact_does_not_grant_fit(self):
        p=self.page('Produciamo prodotti specializzati su misura.');i=self.identity(p);i['contacts']=[]
        self.assertFalse(evaluate(i,[p],{'eligible':True})['audit_allowed'])
    def test_future_platform_not_completed_counterproof(self):
        p=self.page('Produciamo macchinari industriali. Cerchiamo un fornitore per una nuova piattaforma globale.')
        self.assertNotIn('existing_new_platform',[f['kind'] for f in evaluate(self.identity(p),[p])['counterevidence']])
    def test_selected_regions_only_and_distinct_families(self):
        for e in ('FREELANCE','AGENCIES','STARTUPS','WEBSITE_REBUILD'):
            ps=[p for p in plan(e) if p['region'] in ('Veneto','Lombardia','Emilia-Romagna')]
            self.assertEqual({p['region'] for p in ps},{'Veneto','Lombardia','Emilia-Romagna'})
            self.assertTrue(all(p['region']+' Italia' in p['query'] or (p['search_geography_scope']=='national_discovery_selected_regions_checked_on_company' and 'Italia' in p['query']) or (p['search_geography_scope']=='remote_italy_eligibility' and 'remote' in p['query']) for p in ps));self.assertGreater(len({p['family'] for p in ps}),3)
            self.assertTrue(all(p.get('source_preference') for p in ps))
    def test_startup_never_generic_founder_search(self):
        self.assertTrue(all(any(w in p['query'] for w in ('cerchiamo','commissionare')) for p in plan('STARTUPS')))
    def test_rebuild_specific_segments(self):
        ps=plan('WEBSITE_REBUILD');self.assertGreater(len({p['segment'] for p in ps}),5)
        self.assertTrue(all(p['segment'] and 'azienda contatti' not in p['query'] for p in ps))
    def test_freshness_unknown_index_date_and_availability(self):
        self.assertEqual(freshness()['date_status'],'UNKNOWN')
        f=freshness('2026-10-10',index_hint=True);self.assertIsNone(f['publication_date']);self.assertEqual(f['date_status'],'INFERRED');self.assertEqual(f['availability'],'UNVERIFIABLE')
        self.assertEqual(freshness('2026-10-10',verified=True,text='Candidature aperte')['availability'],'OPEN_DECLARED')
    def test_request_types_not_cash_invented(self):
        self.assertEqual(startup_type('Cerchiamo cofounder tecnico full-time'),'TECHNICAL_COFOUNDER')
        self.assertEqual(startup_type('Cerchiamo sviluppatore freelance retribuito per MVP'),'PAID_FREELANCE_PROJECT')
        self.assertEqual(startup_type('Cerchiamo partner tecnico per piattaforma'),'TECHNICAL_PARTNERSHIP')
    def test_agency_signal_classes(self):
        for text,expected in [('Cerchiamo sviluppatori WordPress freelance','A_'),('Collaboriamo con sviluppatori WordPress freelance','B_'),('Commerciale / Nuove collaborazioni','C_'),('Chi siamo','D_'),('Realizziamo siti web','E_')]:
            self.assertTrue(agency_signal(text).startswith(expected),(text,agency_signal(text)))
    def test_real_partner_invitation_not_existing_partnership(self):
        self.assertIsNotNone(request_clause('Diventa partner tecnico WordPress freelance del nostro team.'))
        self.assertIsNone(request_clause('Pronesis diventa partner della piattaforma E-Commerce Shopify'))
    def test_agency_policy_not_stopped_by_services_on_same_page(self):
        from sales.commercial.commercial_gate import page_relevance
        p=self.page('Realizziamo siti WordPress. Collaboriamo con sviluppatori WordPress freelance sui nostri progetti.')
        self.assertTrue(page_relevance(p,'AGENCIES')['allowed'])
    def test_rebuild_ai_empty_screen_does_not_suffice(self):
        r={'identity':{'identity_status':'verified'},'screening':{'findings':[]}}
        self.assertFalse(sufficient('WEBSITE_REBUILD',r,[{'id':'e','text':'CONTATTACI','url':'https://alfa.example/'}])['allowed'])
        self.assertFalse(sufficient('WEBSITE_REBUILD',r,[{'id':'e','text':'Benvenuti nella nostra nuova casa digitale!','url':'https://alfa.example/'}])['allowed']) # no subject proof after trimming
    def test_adaptive_phase_is_bounded_and_respects_override(self):
        self.assertEqual(adaptive_phase_limit(5000,4,100000),10000)
        self.assertEqual(adaptive_phase_limit(5000,0,100000),5000)
        self.assertEqual(adaptive_phase_limit(5000,4,100000,True),5000)
        self.assertLessEqual(adaptive_phase_limit(5000,4,6000),2000)
    def test_audit_states(self):
        for r,expected in [({},'NOT_EXECUTED'),({'completed':True},'COMPLETE'),({'pages':[{}]},'PARTIAL'),({'failure_codes':['rendering_timeout']},'TIMEOUT'),({'outcome':'robots'},'BLOCKED'),({'executed':False},'NOT_EXECUTED')]:self.assertEqual(audit_state(r),expected)
    def test_no_budget_increase(self):
        self.assertEqual((PILOT['max_queries_per_engine'],PILOT['max_provider_requests'],PILOT['max_http_reads'],PILOT['max_browser_runs'],PILOT['max_runtime_seconds']),(3,7,200,2,600))
        self.assertEqual((BUDGETS['browser_max_resources'],BUDGETS['browser_total_seconds']),(60,120))
    def test_pdf_exclusion_before_target(self):self.assertEqual(assess({'url':'https://alfa.example/a.pdf'},'WEBSITE_REBUILD')['reason'],'excluded_pdf')
    def test_hosted_inspection_keeps_client_and_no_browser(self):
        from test_commercial_engines import CommercialTestCase
        from sales.db import Store
        from sales.commercial.inspection import inspect
        from sales.research_store import ResearchStore
        from sales.commercial.storage import Opportunities
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db');store.init();rs=ResearchStore(store);c=rs.create();repo=Opportunities(store)
            p=copy.deepcopy(load()['pages']['https://www.reggiotoday.it/annunci/co-founder-cto-5p8e9.job'])
            with patch('sales.commercial.inspection.ResearchWeb.get',return_value=p),patch('sales.commercial.browser.review',side_effect=AssertionError('No browser')):
                result=inspect(store,{'url':p['url'],'commercial_engine':'STARTUPS'})
            self.assertEqual(result['identity']['name'],'CaLab Ai');self.assertIsNone(result['identity']['website']);self.assertEqual(result['result']['state'],'REJECTED')
            before=store.settings();ids=[repo.save(c,result['identity'],result['documents'],result['result']) for _ in range(2)]
            self.assertEqual(ids[0],ids[1]);self.assertEqual(len(repo.get(ids[0])['revisions']),1);self.assertEqual(store.settings(),before)
    def test_ai_measurement_kept_as_observation(self):
        from sales.commercial.evidence import select
        r={'engine':'WEBSITE_REBUILD','browser':{'completed':True},'evidence':[{'kind':'measurement','url':'https://alfa.example/','quote':'Due controlli coperti a 390 px.'}]}
        es,m=select(1,[],result=r)
        self.assertEqual(es[0]['kind'],'measurement');self.assertFalse(sufficient('WEBSITE_REBUILD',r,es)['allowed']) # measurements alone do not establish the actor
