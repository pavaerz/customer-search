import json,unittest
from unittest.mock import patch
from test_commercial_engines import CommercialTestCase,page
from sales.commercial.catalog import ENGINES,VERSIONS,plan
from sales.commercial.coordinator import Coordinator,run_campaign,preflight
from sales.commercial.geography import locate,REGIONS
from sales.research_analysis import identity_from
from sales.research_api import annotate
from sales.db import encode

class PipelineTests(CommercialTestCase):
    def campaign(self,engines=None,target=50):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.c=self.rs.create({'commercial_engines':engines or list(ENGINES),'work_budget':{'max_candidates_per_engine':8}},target)
        return Coordinator(self.store,self.c)
    def save(self,text='Cerchiamo sviluppatore WordPress freelance.',engine='FREELANCE'):
        found=self.inspect(page(text),engine);return self.repo.save(self.c,found['identity'],found['documents'],found['result'])
    def test_plan_covers_north_centre_south_and_never_requires_region(self):
        self.campaign()
        self.assertEqual(self.c['filters']['regions'],list(REGIONS))
        for engine in ENGINES:
            areas=list(dict.fromkeys(q['region'] for q in plan(engine)))
            self.assertEqual(areas,list(REGIONS));self.assertLess(areas.index('Veneto'),areas.index('Lazio'));self.assertLess(areas.index('Lazio'),areas.index('Sicilia'))
    def test_geography_all_italy_and_remote(self):
        for city,code,area in [('Padova','PD','Veneto'),('Perugia','PG','Umbria'),('Napoli','NA','Campania')]:
            p=page('Cerchiamo freelance WordPress',city=city,code=code,region=area)
            geo=locate([p],identity_from([p]));self.assertTrue(geo['eligible']);self.assertIn(area,geo['regions'])
        self.assertTrue(locate([],{},'WordPress freelance remote worldwide')['eligible']) # 5.0: explicit worldwide original request includes Italy
        self.assertTrue(locate([],{},'WordPress freelance da remoto in Italia')['eligible'])
        self.assertFalse(locate([],{'country':'US'},'WordPress freelance remote')['eligible'])
    def test_persistent_queue_stop_late_results_resume_without_duplicate(self):
        worker=self.campaign();worker.initialize();worker.tick()
        first=self.rs.claim(self.c['id'],self.c['generation']);self.rs.task_done(first['id'])
        found=self.inspect(page('Cerchiamo freelance WordPress.'))
        old=self.c
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.assertFalse(worker.enqueue('candidate','FREELANCE',{'url':'https://alfa.example'},'late'))
        self.assertIsNone(self.repo.save(old,found['identity'],found['documents'],found['result']))
        self.c=self.rs.resume(self.c['id']);worker=Coordinator(self.store,self.c);worker.initialize();worker.tick()
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT state FROM research_tasks WHERE id=?',(first['id'],)).fetchone()[0],'done')
            self.assertEqual(c.execute('SELECT count(*)-count(DISTINCT fingerprint) FROM research_tasks').fetchone()[0],0)
    def test_worker_routes_opt_in_campaign_to_four_engine_runner(self):
        from sales.research_worker import run
        self.campaign()
        with patch('sales.commercial.coordinator.run_campaign') as runner,patch('sales.research_worker.seed_campaign') as legacy:
            run(self.store.path,self.c['id'],self.c['generation'])
        runner.assert_called_once();legacy.assert_not_called()
    def test_full_pipeline_all_four_engines_failure_isolated(self):
        self.campaign()
        def query(store,payload,check):
            if payload['commercial_engine']=='FREELANCE':raise ValueError('Provider non configurato per questa fixture')
            if payload['commercial_engine']=='WEBSITE_REBUILD':return [{'url':'https://alfa.example/WEBSITE_REBUILD','title':'Alfa produzione industriale','content':'Catalogo prodotti industriali'}]
            return [{'url':'https://alfa.example/'+payload['commercial_engine'],'title':'Cerchiamo sviluppatore WordPress freelance per MVP retribuito','content':'Web agency e startup con richiesta tecnica esterna.'}]
        def read(web,url):
            return page('Siamo una startup e web agency. Cerchiamo partner tecnico freelance WordPress per MVP retribuito.',url=url)
        one=lambda engine:[{'query':engine,'region':'Veneto','page':1}]
        with patch('sales.commercial.coordinator.plan',one),patch('sales.commercial.coordinator.acquire',query),patch('sales.commercial.inspection.ResearchWeb.get',read):
            run_campaign(self.store,self.c,lambda:None,lambda message:None)
        rows=self.repo.listing()['items'];self.assertEqual({r['engine'] for r in rows},{'AGENCIES','STARTUPS','WEBSITE_REBUILD'})
        self.assertEqual(self.rs.campaign(self.c['id'])['status'],'blocked')
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM prospects').fetchone()[0],0)
    def test_counts_and_results_use_same_decisions(self):
        self.campaign();self.save();self.save('Cerchiamo uno sviluppatore frontend senza contratto specificato.')
        c=self.rs.campaign(self.c['id']);self.assertEqual(c['examined'],2);self.assertEqual(c['qualified'],1);self.assertEqual(c['needs_review'],1)
        self.assertEqual(self.repo.listing({'state':'VERIFIED','campaign':self.c['id']})['total'],c['qualified'])
    def test_same_entity_distinct_engine_opportunities(self):
        self.campaign();self.save('Siamo una web agency. Cerchiamo WordPress freelance.')
        self.save('Siamo una web agency. Cerchiamo WordPress freelance.','AGENCIES')
        rows=self.repo.listing()['items'];self.assertEqual(len(rows),2);self.assertEqual(len({r['entity_id'] for r in rows}),1)
    def test_revision_scope_and_manual_discard_survive_rule_change(self):
        self.campaign();ident=self.save();old=self.c['id'];self.repo.action(ident,'discard');self.campaign()
        with patch.dict(VERSIONS,{'FREELANCE':VERSIONS['FREELANCE']+1}):self.save()
        self.assertEqual(self.repo.get(ident)['state'],'REJECTED')
        historic=self.repo.listing({'campaign':old,'include_discarded':'1'})['items'][0]
        self.assertEqual(historic['state'],'VERIFIED');self.assertEqual(len(self.repo.get(ident)['revisions']),2)
    def test_same_request_new_url_deduplicates(self):
        self.campaign();first=self.save()
        p=page('Cerchiamo sviluppatore WordPress freelance.',url='https://alfa.example/careers/new-url')
        f=self.inspect(p);second=self.repo.save(self.c,f['identity'],f['documents'],f['result'])
        self.assertEqual(first,second)
    def test_memory_uses_engine_version_not_legacy_url_decision(self):
        worker=self.campaign();self.save()
        self.assertFalse(worker.offer('FREELANCE',{'url':'https://alfa.example/jobs/web'},{}))
        with patch.dict(VERSIONS,{'FREELANCE':VERSIONS['FREELANCE']+1}):self.assertTrue(worker.offer('FREELANCE',{'url':'https://alfa.example/jobs/web'},{}))
    def test_crm_manual_actions_idempotent_contact_and_do_not_contact(self):
        self.campaign();ident=self.save()
        first=self.repo.action(ident,'save');pid=first['prospect_id']
        self.assertEqual(self.repo.action(ident,'deal')['prospect_id'],pid)
        self.assertEqual(self.repo.action(ident,'deal')['prospect_id'],pid)
        self.assertEqual(len(self.store.list()),1)
        self.repo.action(ident,'contacted');self.assertEqual(self.store.detail(pid)['stage'],'contacted')
        self.assertEqual(self.rs.campaign(self.c['id'])['useful_companies'],0)
        self.assertEqual(annotate(self.store,self.store.company_list())[0]['qualification'],'commercial')
        with self.store.connect() as c:c.execute('UPDATE companies SET do_not_contact=1')
        with self.assertRaisesRegex(ValueError,'escluso'):self.repo.action(ident,'deal')
    def test_explicit_domain_dismissal_is_preserved(self):
        self.campaign();ident=self.save();pid=self.repo.action(ident,'save')['prospect_id']
        self.store.set_dismissed(pid,True)
        with self.assertRaises(ValueError):self.repo.action(ident,'contacted')
        worker=Coordinator(self.store,self.c);self.assertFalse(worker.offer('AGENCIES',{'url':'https://alfa.example/careers'},{}))
    def test_unverifiable_candidate_persisted_without_fake_identity(self):
        worker=self.campaign();worker.record_failure({'kind':'candidate','strategy':'FREELANCE','payload':{'url':'https://alfa.example/jobs','origin':{'query':'test'}}},TimeoutError('Timeout'))
        r=self.repo.listing()['items'][0];self.assertEqual(r['state'],'UNVERIFIABLE');self.assertEqual(r['body']['identity']['identity_status'],'unknown');self.assertEqual(r['body']['evidence'],[])
    def test_preflight_rejects_noise_before_download(self):
        for url in ['https://example.org/old.pdf','https://paginegialle.it/foo','https://confindustriavenest.it/news']:
            self.assertIsNone(preflight({'url':url})[0])
        self.assertIsNotNone(preflight({'url':'https://www.linkedin.com/jobs/view/123'})[0])
    def test_linkedin_lead_never_fetched(self):
        from sales.commercial.inspection import inspect
        with patch('sales.commercial.inspection.ResearchWeb.get') as fetch:
            with self.assertRaises(ValueError):inspect(self.store,{'commercial_engine':'FREELANCE','url':'https://www.linkedin.com/jobs/view/123'})
        fetch.assert_not_called()
    def test_read_budget_is_enforced(self):
        from sales.commercial.inspection import inspect
        with patch('sales.commercial.inspection.ResearchWeb.get',return_value=page('Cerchiamo freelance WordPress')) as fetch:
            with self.assertRaisesRegex(ValueError,'Budget'):inspect(self.store,{'commercial_engine':'FREELANCE','url':'https://alfa.example/jobs/web','max_reads':1})
        self.assertEqual(fetch.call_count,1)
    def test_fabricated_quote_rejected(self):
        found=self.inspect(page('Cerchiamo WordPress freelance.'));found['result']['evidence'][0]['quote']='Inventato'
        with self.assertRaisesRegex(ValueError,'Prova'):self.repo.save(self.c,found['identity'],found['documents'],found['result'])
    def test_optional_budget_and_unpaid_equity(self):
        r=self.inspect(page('Cerchiamo WordPress freelance, budget di 4.000 euro.'))['result'];self.assertEqual(r['compensation']['amount'],4000)
        r=self.inspect(page('Startup: cerchiamo co-founder CTO per MVP, collaborazione non retribuita con equity.'),'STARTUPS')['result'];self.assertEqual(r['compensation']['type'],'equity')
    def test_migration_repeatable_and_preserves_crm_notes(self):
        self.campaign();ident=self.save();pid=self.repo.action(ident,'save')['prospect_id'];self.store.update(pid,{'notes':'Nota privata'})
        self.store.init();self.store.init();self.assertEqual(self.store.detail(pid)['notes'],'Nota privata')
        with self.store.connect() as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_providers_are_mocked_and_never_fallback(self):
        from sales.commercial.coordinator import acquire
        
        self.store.configure({'provider':'serper'})
        with patch('sales.serper_provider.search',return_value=({'results':[]},False)) as serper,patch('sales.providers.SearXNG.search') as searx:
            acquire(self.store,{'query':'test','page':2},lambda:None)
        serper.assert_called_once();searx.assert_not_called()
    def test_repaired_access_updates_same_opportunity(self):
        worker=self.campaign();worker.record_failure({'kind':'candidate','strategy':'FREELANCE','payload':{'url':'https://alfa.example/jobs/web'}},TimeoutError())
        first=self.repo.listing()['items'][0]['id'];self.assertEqual(self.save(),first)
        self.assertEqual(self.repo.listing()['total'],1);self.assertEqual(self.repo.get(first)['state'],'VERIFIED')
    def test_crm_contact_updates_all_cards_and_target(self):
        self.campaign();one=self.save();two=self.save('Siamo una web agency. Accettiamo collaborazioni WordPress freelance.','AGENCIES')
        pid=self.repo.action(one,'save')['prospect_id'];self.store.update(pid,{'stage':'contacted'})
        self.assertEqual(self.repo.get(two)['manual_state'],'contacted');self.assertEqual(self.rs.campaign(self.c['id'])['useful_companies'],0)
    def test_workspace_reset_archives_phase_two_and_preserves_exclusions(self):
        from sales.workspace import reset_results
        self.campaign();ident=self.save();self.repo.action(ident,'discard');self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        report=reset_results(self.store,'test-backup');self.assertEqual(report['archived_rows']['commercial_opportunities'],1)
        self.assertEqual(self.repo.listing()['total'],0);self.assertIsNotNone(self.rs.suppressed({'website':'https://alfa.example/'}))
    def test_third_party_request_not_assigned_to_publisher(self):
        p=page('Beta Srl cerca uno sviluppatore freelance WordPress.',url='https://alfa.example/notizie/beta')
        self.assertEqual(self.inspect(p)['result']['state'],'REJECTED')
    def test_foreign_vacancy_not_made_italian_by_employer_headquarters(self):
        job={'@type':'JobPosting','jobLocation':{'@type':'Place','address':{'addressLocality':'New York','addressCountry':'US'}}}
        p=page('Cerchiamo freelance WordPress per la sede americana.',job=job)
        self.assertEqual(self.inspect(p)['result']['state'],'REJECTED')
    def test_foreign_address_does_not_borrow_italian_city_name(self):
        geo=locate([],{'location':'Via Roma 1, Padova','country':'US'})
        self.assertFalse(geo['eligible'])
