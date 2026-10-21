"""3B.3 saved-evidence regressions + explicitly synthetic isolation tests."""
import copy,json,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from scripts.replay_commercial3b3 import replay,load
from sales.commercial.discovery import assess
from sales.commercial.indexed_jobs import parse_indexed_job,resolution
from sales.commercial.attribution import identity
from sales.commercial.commercial_gate import sufficient,SKIP
from sales.commercial.ai_schema import unknown_output,evidence_bundle,validate_output
from sales.commercial.ai_diagnostics import diagnose

class HistoricalPrecision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.data=load();cls.replay=replay()
    def item(self,needle):return next(d['body'] for d in self.data['commercial_discovery'] if needle in d['url'])
    def test_calabria_group_not_geography_or_freelance(self):
        from sales.commercial.geography import region
        self.assertIsNone(region('Calabria Group'))
        d=self.item('at-calabria-group');r=assess(d,'FREELANCE')
        self.assertEqual(r['decision'],'exclude');self.assertIsNone(resolution(d))
        h=parse_indexed_job(d);self.assertIsNone(h['contract_hint']);self.assertFalse(h['commercial_compatibility']);self.assertEqual(h['components']['LOCATION'],'Tucson, Arizona, US')
    def test_boma_original_footer_not_portfolio_client(self):
        r=next(i for i in self.replay['new_code']['identity'] if 'bomastudio' in i['url'])
        self.assertEqual(r['before']['name'],'Bibite Polara srl')
        self.assertEqual(r['after']['name'],'Boma Studio S.r.l');self.assertEqual(r['after']['legal_id'],'IT01545210880');self.assertEqual(r['after']['identity_status'],'verified')
    def test_divi_project_not_company(self):
        d=self.item('rebuild-at-twine');h=parse_indexed_job(d)
        self.assertNotIn('Rebuild',h['company_candidate']);self.assertEqual(h['components']['PLATFORM_NAME'].lower(),'twine');self.assertIsNone(resolution(d))
    def test_contract_not_company(self):
        d=self.item('contract-at-twine');h=parse_indexed_job(d)
        self.assertNotIn('Contract',h['company_candidate']);self.assertIsNone(resolution(d))
    def test_rende_and_dritara_separated(self):
        h=parse_indexed_job(self.item('at-dritara'))
        self.assertEqual(h['company_candidate'],'Dritara');self.assertEqual(h['components']['LOCATION'],'Rende');self.assertIsNotNone(resolution(self.item('at-dritara')))
    def test_saved_seven_bundles_block_dispatch(self):
        gs=self.replay['new_code']['ai_gates'];self.assertEqual(len(gs),7)
        self.assertTrue(all(not g['would_dispatch'] and g['new_gate']['reason']==SKIP for g in gs))
        self.assertTrue(all(g['output_revalidation'].startswith('not_reproducible') for g in gs))
    def test_subito_qonto_bebee_redemptor_have_no_nucleus(self):
        for a in self.data['commercial_ai_executions']:
            b=next(r['body'] for r in self.data['commercial_revisions'] if str(r['opportunity_id'])==a['candidate_id'])
            if any(host in b['url'] for host in ('subito','qonto','bebee','redemptor')):
                self.assertFalse(sufficient(a['engine'],b,a['body']['evidence'])['allowed'])
    def test_rebuild_pertinent_saved_sites_now_selected_not_remeasured(self):
        rows=self.replay['new_code']['browser_selection'];self.assertEqual(len(rows),7)
        self.assertGreaterEqual(sum(r['new_selection']['selected'] for r in rows),1)
        self.assertTrue(all(not r['audit_executed'] for r in rows))

class SyntheticPrecision(unittest.TestCase):
    """Synthetic: outcomes here are not observations of a real company."""
    def page(self,*args,**kw):
        from test_commercial_engines import page
        return page(*args,**kw)
    def evidence(self,text='Alfa: cerchiamo uno sviluppatore WordPress freelance. Candidature aperte.'):
        e=evidence_bundle(1,[{'url':'https://alfa.example/jobs','text':text}]);o=unknown_output({'candidate_id':'1'})
        ref={'id':e[0]['id'],'quote':e[0]['text']}
        o.update(actor='Alfa',requested_service='WordPress',supporting_evidence=[ref],identity_evidence=[ref])
        return e,o
    def test_conflicting_indexed_employers_do_not_resolve(self):
        d={'url':'https://linkedin.com/jobs/view/wordpress-developer-at-beta-123','title':'WordPress developer freelance at Alfa'}
        self.assertTrue(parse_indexed_job(d)['identity_conflict']);self.assertIsNone(resolution(d))
    def test_conflicting_owners_never_share_vat(self):
        p=self.page('Produciamo beni.',url='https://alfa.example/')
        p['html']+='<footer><p>Beta Srl</p><p>P.IVA 98765432109</p></footer>'
        r=identity([p]);self.assertEqual(r['identity_status'],'uncertain');self.assertIsNone(r['legal_id']);self.assertTrue(r['identity_conflicts'])
    def test_cited_clients_do_not_borrow_footer_legal_id(self):
        p=self.page('Clienti',url='https://alfa.example/',extra='<section class="portfolio"><h2>Beta Srl</h2><p>P.IVA 98765432109</p></section>')
        r=identity([p]);self.assertEqual(r['name'],'Alfa Srl');self.assertEqual(r['legal_id'],'IT12345678901')
    def test_service_terminology_equivalence_only(self):
        e,o=self.evidence();o['requested_service']='Sviluppo WordPress'
        self.assertEqual(validate_output(o,1,e,{})['requested_service'],'Sviluppo WordPress')
        for claim in ('Sviluppo WooCommerce','Sviluppo WordPress con migrazione SAP','WordPress budget 5000 euro'):
            o['requested_service']=claim
            with self.assertRaisesRegex(ValueError,'unsupported_requested_service'):validate_output(o,1,e,{})
    def test_invented_quote_is_never_paraphrase(self):
        e,o=self.evidence();o['supporting_evidence'][0]['quote']='Alfa cerca un esperto WordPress.'
        self.assertEqual(diagnose(o,1,e,{})['category'],'INCORRECT_QUOTE')
    def test_missing_reference(self):
        e,o=self.evidence();o['supporting_evidence'][0]['id']='missing'
        self.assertEqual(diagnose(o,1,e,{})['category'],'EVIDENCE_UNAVAILABLE')
    def test_alias_not_assumed(self):
        e,o=self.evidence();o['actor']='Alfa Group'
        d=diagnose(o,1,e,{});self.assertEqual(d['category'],'ACTOR_ATTRIBUTION');self.assertIsNone(d['contested_value']);self.assertTrue(d['contested_fingerprint'])
    def test_wrong_actor_and_identity_conflicts(self):
        e,o=self.evidence('Alfa cerca WordPress freelance. Beta è un cliente.')
        o['actor']='Beta';r={'company':'Alfa','identity':{'identity_status':'verified'}}
        self.assertEqual(diagnose(o,1,e,r)['code'],'ACTOR_ATTRIBUTION_CONFLICT')
        o['actor']='Alfa';r['identity']['identity_conflicts']=[{'name':'Beta'}]
        self.assertEqual(diagnose(o,1,e,r)['code'],'ACTOR_ATTRIBUTION_CONFLICT')
    def test_unknown_identity_does_not_borrow_named_customer(self):
        e,o=self.evidence('Alfa cerca sviluppatori WordPress freelance. Beta è un cliente.')
        o.update(actor='Beta',commercial_intent='BUYER_INTENT',direction='BUYER')
        self.assertEqual(diagnose(o,1,e,{})['code'],'ACTOR_ATTRIBUTION_CONFLICT')
    def test_date_not_verified_and_role_mismatch(self):
        e,o=self.evidence();o.update(commercial_intent='FREELANCE_OPPORTUNITY',direction='BUYER',relationship_type='CURRENT_OPEN_REQUEST',temporal_evidence=o['supporting_evidence'])
        self.assertEqual(diagnose(o,1,e,{})['category'],'UNVERIFIED_DATE')
        e,o=self.evidence('Alfa WordPress');o['temporal_evidence']=o['supporting_evidence']
        self.assertEqual(diagnose(o,1,e,{})['category'],'EVIDENCE_ROLE')
    def test_schema_and_minimized_diagnostics(self):
        d=diagnose({'actor':'sk-secret token john@example.com'},1,[],{})
        self.assertEqual(d['category'],'SCHEMA_INCOMPATIBLE');self.assertNotIn('sk-secret',json.dumps(d));self.assertNotIn('john@',json.dumps(d))
    def test_valid_ambiguous_request_and_standing_policy_can_pass_gate(self):
        for text in ('Alfa cerchiamo uno sviluppatore WordPress freelance.','Accettiamo collaborazioni con sviluppatori frontend freelance per i nostri progetti.'):
            e=evidence_bundle(1,[{'url':'https://alfa.example/collabora-con-noi','text':text}])
            e.append({'id':'owner','text':'Alfa Srl','url':'https://alfa.example/','roles':['identity']})
            self.assertTrue(sufficient('AGENCIES',{'title':'Collabora con noi','company':'Alfa Srl','identity':{'name':'Alfa Srl','identity_status':'verified'}},e)['allowed'],text)
    def test_skip_persisted_once_and_shadow_unchanged(self):
        from test_commercial_ai3b import AI
        from sales.commercial.ai import summary
        c=AI();c.setUp();self.addCleanup(c.doCleanups);before=copy.deepcopy(c.result)
        c.docs[0]['text']='Menu\nRadar\nTrova lavoro o nuovi clienti\nCrea il tuo profilo gratis'
        with patch('sales.commercial.ai.infer',side_effect=AssertionError('No AI')):
            a=c.call();b=c.call()
        self.assertEqual(a['status'],'skipped');self.assertEqual(a['execution_id'],b['execution_id']);self.assertEqual(c.result,before)
        self.assertEqual(summary(c.store,1)['calls'],0);self.assertEqual(summary(c.store,1)['calls_avoided'],1)
    def test_spa_not_sufficient_size_evidence(self):
        from sales.targeting import exclusion
        p=self.page('Produciamo componenti.',title='Alfa S.p.A.');p['html']=p['html'].replace('Alfa Srl','Alfa S.p.A.')
        self.assertIsNone(exclusion(p,allow_legal_spa=True));self.assertEqual(exclusion(p)['code'],'legal_spa')
        p['html']+='<p>Siamo una multinazionale con 500 dipendenti.</p>'
        self.assertEqual(exclusion(p,allow_legal_spa=True)['code'],'large_company')
    def test_fifteen_candidates_limited_http_complete_simulated_browser(self):
        from sales.db import Store
        from sales.research_store import ResearchStore
        from sales.commercial.resources import Budget,reserve,headroom
        from sales.commercial.inspection import inspect
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.db');store.init()
            campaign=ResearchStore(store).create({'commercial_engines':['WEBSITE_REBUILD'],'mode':'pilot','work_budget':{'max_http_reads':40,'max_browser_runs':1}})
            limits=campaign['filters']['work_budget'];budget=Budget(store,campaign,'WEBSITE_REBUILD',limits);audits=[];results=[]
            def browser(store,pages,*args,**kwargs):
                self.assertTrue(kwargs['limits']['browser_advanced'])
                reserve('browser_runs')
                for _ in range(3):reserve('http_reads')
                audits.append(pages[0]['url'])
                return {'completed':True,'executed':True,'outcome':'completed','findings':[],'links':[],'limits':[],'fixture':'SYNTHETIC_NOT_REAL_MEASUREMENT'}
            def read(web,url):
                reserve('http_reads')
                if 'unknown' in url:return {'url':url,'html':'<title>Impresa</title><p>Produciamo componenti.</p>','status':200,'checked_at':'2026-10-17'}
                return self.page('Produciamo componenti industriali.',url=url)
            for n in range(15):
                item={'url':f'https://directory.example/elenco-aziende/{n}','title':'Directory aziende'} if n<12 else {'url':'https://alfa.example/' if n<14 else 'https://unknown.example/','title':'Produttore componenti Srl'}
                if assess(item,'WEBSITE_REBUILD')['decision']=='exclude':continue
                with budget.task(lambda:None),patch('sales.commercial.inspection.ResearchWeb.get',read),patch('sales.commercial.browser.review',browser):
                    results.append(inspect(store,{**limits,'url':item['url'],'commercial_engine':'WEBSITE_REBUILD'})['result'])
            self.assertEqual(len(results),3);self.assertEqual(len(audits),1)
            self.assertTrue(results[0]['browser']['completed']);self.assertFalse(results[1]['browser']['executed']);self.assertEqual(results[2]['browser_outcome'],'identity_unverified')
            self.assertLessEqual(budget.used('http_reads'),40);self.assertEqual(budget.used('browser_runs'),1)
    def test_outside_geography_does_not_spend_browser(self):
        from sales.commercial.rebuild import browser_selection
        result=browser_selection({'identity_status':'verified'},{'promising':True},{'geography_eligible':False})
        self.assertFalse(result['selected']);self.assertEqual(result['code'],'outside_selected_area')
    def test_pilot_new_defaults_old_budget_explicitly_preserved(self):
        from sales.commercial.catalog import options
        base={'commercial_engines':['FREELANCE'],'mode':'pilot'}
        self.assertEqual(options(base)[1]['max_provider_requests'],7)
        self.assertEqual(options({**base,'work_budget':{'max_provider_requests':4,'max_http_reads':40}})[1]['max_http_reads'],40)
    def test_pdf_and_facebook_stay_out(self):
        for engine in ('FREELANCE','AGENCIES','STARTUPS','WEBSITE_REBUILD'):
            for url,reason in [('https://x.example/test.pdf','excluded_pdf'),('https://facebook.com/post/1','excluded_facebook')]:
                self.assertEqual(assess({'url':url},engine)['reason'],reason)

if __name__=='__main__':unittest.main()
