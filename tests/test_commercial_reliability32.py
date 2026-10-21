"""3A.2 orchestration on temporary databases and frozen campaign-14 evidence."""
import gzip,json,unittest
from pathlib import Path
from unittest.mock import patch
from test_commercial_engines import CommercialTestCase,page
from sales.commercial.indexed_jobs import parse_indexed_job,resolution
from sales.commercial.discovery import assess,followup_allowed
from sales.commercial.coordinator import Coordinator,run_campaign
from sales.commercial.resources import Budget,BudgetExceeded
from sales.commercial.catalog import ENGINES,plan
from sales.commercial.inspection import inspect
from sales.commercial.social import inspect_social

with gzip.open(Path(__file__).parent/'fixtures/commercial32/campaign14.json.gz','rt') as f:SAVED=json.load(f)

def saved_revision(n):return next(r['body'] for r in SAVED['commercial_revisions'] if r['id']==n)

class IndexedJobs32Tests(unittest.TestCase):
    def test_saved_linkedin_titles_resolve_without_claiming_contract_or_date(self):
        for n,company in [(741,'NUMERAWAY'),(744,'Digisourced')]:
            item=saved_revision(n)['discovery'];r=parse_indexed_job(item)
            self.assertEqual(r['company_candidate'],company)
            self.assertIsNone(r['contract']);self.assertIsNone(r['published_at'])
            self.assertFalse(r['identity_verified'])
            if n==744:self.assertIsNone(resolution(item))  # 3B: do not spend on demonstrated embedded mismatch.
            else:self.assertIsNotNone(resolution(item))
            self.assertEqual(r['snippet'],item['snippet'])
        self.assertFalse(parse_indexed_job(saved_revision(744)['discovery'])['commercial_compatibility'])
    def test_title_formats(self):
        for title in ['Frontend developer freelance at Alfa','Frontend developer freelance - Alfa','Alfa cerca Frontend developer freelance','Alfa sta assumendo Frontend developer freelance in Italia']:
            r=parse_indexed_job({'url':'https://linkedin.com/jobs/view/1','title':title})
            self.assertEqual(r['company_candidate'],'Alfa',r)
            self.assertEqual(r['contract_hint'],'external');self.assertIsNone(r['contract'])
    def test_url_freelance_never_proves_contract(self):
        r=parse_indexed_job({'url':'https://linkedin.com/jobs/view/freelance-web-developer-at-alfa-123','title':'Web developer at Alfa','content':'Related: freelance software engineer elsewhere'})
        self.assertIsNone(r['contract_hint']);self.assertIsNone(r['contract']);self.assertEqual(r['company_candidate'],'Alfa')
    def test_employee_and_ambiguous_identity(self):
        r=parse_indexed_job({'url':'https://linkedin.com/jobs/view/1','title':'Frontend tempo indeterminato at Alfa'})
        self.assertEqual(r['contract_hint'],'employment');self.assertIsNone(r['contract'])
        self.assertIsNone(resolution({'url':'https://linkedin.com/jobs/view/1','title':'Opportunità web in Italia'}))
    def test_social_hint_is_not_verified_and_employee_title_not_request(self):
        # Phase 4.4 retains compatible employee vacancies for personal review,
        # without treating them as verified freelance commissions.
        employee=assess({'url':'https://linkedin.com/jobs/view/1','title':'Frontend a tempo indeterminato at Alfa'},'FREELANCE')
        self.assertEqual(employee['decision'],'admit')
        self.assertTrue(employee['recommendation_only'])
        self.assertNotIn('state',employee)
        self.assertEqual(assess(saved_revision(741)['discovery'],'FREELANCE')['decision'],'admit')
        self.assertEqual(assess(saved_revision(744)['discovery'],'FREELANCE')['reason'],'incompatible_requested_role')
    def test_individual_aggregator_survives_listing_exclusion(self):
        item={'url':'https://jobs.example/offerta/frontend-alfa','title':'Alfa cerca frontend freelance','content':'Annunci di terzi. Compenso e contratto da verificare.'}
        r=assess(item,'FREELANCE');self.assertEqual(r['decision'],'admit');self.assertEqual(r['source_kind'],'job_portal')
        item['url']='https://jobs.example/';self.assertEqual(assess(item,'FREELANCE')['decision'],'exclude')
    def test_directory_paths_not_host_blacklist(self):
        for url in ['https://atoka.io/public/it/azienda/alfa/123','https://www.tradenordest.com/Beni_di_consumo/Arredamento.php']:
            self.assertEqual(assess({'url':url,'title':'Aziende arredamento'},'WEBSITE_REBUILD')['reason'],'directory')
        r=assess({'url':'https://atoka.io/jobs/frontend','title':'Cerchiamo sviluppatore frontend freelance'},'FREELANCE')
        self.assertEqual(r['decision'],'admit')
    def test_saved_followups_require_local_request(self):
        for row in SAVED['commercial_discovery']:
            origin=row['body'].get('origin',{})
            if origin.get('parent_task'):
                self.assertFalse(followup_allowed(saved_revision(735),origin))
    def test_all_engines_queries_pdf_and_geography(self):
        from sales.content_policy import search_query
        for engine in ENGINES:
            plans=plan(engine)
            self.assertEqual(len({p['region'] for p in plans}),20)
            self.assertGreaterEqual(len({p['family'] for p in plans}),3)
            self.assertTrue(all(search_query(p['query']).count('-filetype:pdf')==1 for p in plans))
            self.assertEqual(assess({'url':'https://a.example/doc.pdf','title':'Cerchiamo freelance WordPress'},engine)['reason'],'excluded_pdf')

class Reliability32Tests(CommercialTestCase):
    def worker(self,engine='WEBSITE_REBUILD',extra=None):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.c=self.rs.create({'commercial_engines':[engine],'mode':'pilot','regions':['Veneto'],'work_budget':{'max_queries_per_engine':1,'max_browser_runs':1,**(extra or {})}})
        w=Coordinator(self.store,self.c);w.initialize();return w
    def test_exhausted_browser_keeps_http_result_and_does_not_start_browser(self):
        w=self.worker();b=Budget(self.store,self.c,'WEBSITE_REBUILD',w.budget);b.reserve('browser_runs')
        p=page('Produciamo componenti per aziende italiane. Catalogo completo e servizio clienti.',url='https://alfa.example/')
        with b.task(lambda:None),patch('sales.commercial.inspection.ResearchWeb.get',return_value=p),patch('sales.commercial.browser._launch_worker') as heavy:
            r=inspect(self.store,{'commercial_engine':'WEBSITE_REBUILD','url':p['url'],'browser_sample_percent':100})['result']
        heavy.assert_not_called()
        self.assertEqual(r['state'],'UNVERIFIABLE');self.assertEqual(r['browser_outcome'],'budget_deferred')
        self.assertFalse(r['browser']['executed']);self.assertTrue(r['screening']);self.assertEqual(b.used('browser_runs'),1)
    def test_whole_worker_continues_http_after_browser_budget(self):
        w=self.worker();b=Budget(self.store,self.c,'WEBSITE_REBUILD',w.budget);b.reserve('browser_runs')
        b.reserve('queries')
        with self.store.connect() as c:c.execute("UPDATE commercial_engine_runs SET state='budget_reached',error='Budget operativo esaurito: queries' WHERE campaign_id=?",(self.c['id'],))
        for i in [1,2]:w.enqueue('candidate','WEBSITE_REBUILD',{'url':f'https://alfa{i}.example/','browser_sample_percent':100},'candidate'+str(i))
        def read(web,url):
            p=page('Produciamo componenti e servizi per le imprese italiane.',url=url)
            p['html']=p['html'].replace('alfa.example',url.split('/')[2])
            if 'alfa2' in url:p['html']=p['html'].replace('Alfa Srl','Alfa S.p.A.')+'<p>Siamo una multinazionale con 500 dipendenti.</p>'  # 3B.3 size, not legal form
            return p
        # Deterministic selection keeps this test independent of the domain hash.
        with patch('sales.commercial.inspection.ResearchWeb.get',read),patch('sales.commercial.rebuild.browser_selection',return_value={'selected':True,'code':'sampled'}):
            run_campaign(self.store,self.c,lambda:None,lambda _:None)
        with self.store.connect() as c:
            tasks=[dict(r) for r in c.execute("SELECT state,error FROM research_tasks WHERE kind='candidate' ORDER BY id")]
            revisions=[json.loads(r[0]) for r in c.execute('SELECT body FROM commercial_revisions ORDER BY id')]
        self.assertEqual([t['state'] for t in tasks],['budget','done'])
        self.assertEqual([r['state'] for r in revisions],['UNVERIFIABLE','REJECTED'])
        self.assertEqual(revisions[0]['browser_outcome'],'budget_deferred');self.assertEqual(b.used('browser_runs'),1)
    def test_linkedin_resolution_followup_budget_persistent(self):
        w=self.worker('FREELANCE')
        self.assertTrue(w.offer('FREELANCE',saved_revision(741)['discovery'],{'query':'test'}))
        self.assertFalse(w.offer('FREELANCE',saved_revision(744)['discovery'],{'query':'test'}))
        with self.store.connect() as c:tasks=c.execute("SELECT count(*) FROM research_tasks WHERE kind='resolve'").fetchone()[0]
        self.assertEqual(tasks,1)  # 3B.2: incompatible embedded role excluded before candidate/resolution work.
        b=Budget(self.store,self.c,'FREELANCE',w.budget);self.assertEqual(b.used('followups'),1);self.assertEqual(b.used('queries'),0)
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);resumed=self.rs.resume(self.c['id'])
        self.assertEqual(Budget(self.store,resumed,'FREELANCE',w.budget).used('followups'),1)
    def test_linkedin_saved_hints_remain_incomplete(self):
        w=self.worker('FREELANCE')
        item=saved_revision(741)['discovery']
        with patch('sales.commercial.social.CompanyWeb.get') as get:
            r=inspect_social(self.store,{**item,'social':'linkedin','commercial_engine':'FREELANCE'})['result']
        get.assert_not_called();self.assertEqual(r['state'],'UNVERIFIABLE')
        self.assertEqual(r['social']['indexed_job']['company_candidate'],'NUMERAWAY')
        self.assertIsNone(r['published_at']);self.assertIsNone(r['contract'])
    def test_verdurazon_saved_indication_persisted_without_network(self):
        w=self.worker('FREELANCE');prior=saved_revision(733);item=prior['discovery']
        with patch('sales.commercial.social.PublicSocialWeb.get',side_effect=ValueError('robots.txt: divieto esplicito')),patch('sales.commercial.social.CompanyWeb.get',side_effect=ValueError('Fonte non disponibile nel replay')):
            f=inspect_social(self.store,{**item,'social':'instagram','commercial_engine':'FREELANCE'})
        r=f['result'];self.assertEqual(r['state'],'UNVERIFIABLE');self.assertEqual(r['social']['post_url'],prior['url'])
        self.assertIsNone(r['social']['author']);self.assertIsNone(r['published_at']);self.assertTrue(r['social']['official_checks'])
        r['discovery']=item;oid=self.repo.save(self.c,f['identity'],[],r)
        persisted=self.repo.get(oid);self.assertEqual(persisted['body']['discovery']['snippet'],item['snippet'])

    def test_failed_resolution_does_not_erase_original_social_revision(self):
        w=self.worker('FREELANCE');item=saved_revision(741)['discovery']
        with patch('sales.commercial.social.CompanyWeb.get'):
            found=inspect_social(self.store,{**item,'social':'linkedin','commercial_engine':'FREELANCE'})
        found['result']['discovery']=item
        oid=self.repo.save(self.c,found['identity'],[],found['result'])
        before=self.repo.get(oid)
        task={'id':999,'kind':'resolve','strategy':'FREELANCE','payload':{'query':'official source','resolution_company':'NUMERAWAY','resolution_role':'Freelance esperti in Python','resolution_url':item['url'],'origin':{'query':'original'}}}
        with patch('sales.commercial.coordinator.acquire',return_value=[]):w._execute(task,lambda:None)
        after=self.repo.get(oid)
        self.assertEqual(before['body'],after['body']);self.assertEqual(len(before['revisions']),len(after['revisions']))
        with self.store.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM research_events WHERE kind='resolution_incomplete'").fetchone()[0],1)
    def test_resolved_company_requires_whole_name_not_substring(self):
        w=self.worker('FREELANCE')
        p=page('Cerchiamo sviluppatore frontend freelance.',url='https://alfa.example/jobs/web')
        p['html']=p['html'].replace('Alfa Srl','SuperAlfa Srl')
        with patch('sales.commercial.inspection.ResearchWeb.get',side_effect=lambda web,url:{**p,'url':url},autospec=True):
            found=inspect(self.store,{'url':p['url'],'commercial_engine':'FREELANCE','resolution_company':'Alfa','resolution_role':'Frontend developer'})
        self.assertEqual(found['identity']['identity_status'],'unknown')
        self.assertNotIn(found['result']['state'],('VERIFIED','POTENTIAL'))
        from sales.commercial.indexed_jobs import same_company_name
        self.assertTrue(same_company_name('Alfa','Alfa S.r.l.'));self.assertFalse(same_company_name('Alfa','SuperAlfa Srl'))
    def test_individual_aggregator_remains_unresolved_not_publisher_client(self):
        p=page('Annunci di terzi. Alfa cerca sviluppatore frontend freelance.',title='Alfa cerca frontend freelance',url='https://jobs.example/offerta/frontend-alfa')
        with patch('sales.commercial.inspection.ResearchWeb.get',return_value=p):
            r=inspect(self.store,{'url':p['url'],'commercial_engine':'FREELANCE'})['result']
        self.assertEqual(r['state'],'UNVERIFIABLE');self.assertEqual(r['classification'],'publisher_unresolved')
        self.assertEqual(r['indexed_job']['company_candidate'],'Alfa')
    def test_additive_init_does_not_rewrite_revision_or_manual_state(self):
        found=self.inspect(page('Cerchiamo sviluppatore WordPress freelance.'))
        oid=self.repo.save(self.c,found['identity'],found['documents'],found['result'])
        self.repo.action(oid,'interesting')
        with self.store.connect() as c:
            before=[tuple(r) for r in c.execute('SELECT * FROM commercial_revisions')]
            actions=[tuple(r) for r in c.execute('SELECT * FROM commercial_outcomes')]
        self.store.init();self.store.init()
        with self.store.connect() as c:
            self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM commercial_revisions')])
            self.assertEqual(actions,[tuple(r) for r in c.execute('SELECT * FROM commercial_outcomes')])
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
