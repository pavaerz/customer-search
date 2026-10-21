"""Phase 2.1: frozen public HTML from campaign 8, temporary DBs only."""
import gzip,json,unittest
from pathlib import Path
from unittest.mock import patch
from test_commercial_engines import CommercialTestCase,page
from sales.commercial.context import extract,source_kind,followups,channels
from sales.commercial.inspection import inspect
from sales.commercial.attribution import identity,geographic_conflicts
from sales.commercial.geography import locate
from sales.commercial.qualification import evaluate
from sales.commercial.coordinator import Coordinator,campaign_counts
from sales.commercial.rebuild import screen,browser_selection
from sales.commercial.catalog import options

with gzip.open(Path(__file__).parent/'fixtures/commercial21/campaign8.json.gz','rt') as f:
    SNAPSHOTS=json.load(f)


class ContextTests(CommercialTestCase):
    def captured(self,name,engine='FREELANCE',**extra):
        case=SNAPSHOTS[name]
        def read(web,url):
            if url not in case['pages']:
                return {'url':url,'html':'','status':404,'checked_at':'2026-10-16T08:00:00+00:00'}
            return case['pages'][url]
        with patch('sales.commercial.inspection.ResearchWeb.get',read):
            return inspect(self.store,{'url':case['source_url'],'commercial_engine':engine,**extra})

    def test_sicis_recognized_not_automatically_commercially_compatible(self):
        f=self.captured('sicis');r=f['result']
        self.assertEqual(r['contract'],'external');self.assertEqual(r['classification'],'external')
        self.assertEqual(r['state'],'NEEDS_REVIEW') # intermediary, no invented client
        self.assertEqual(r['dates']['publication_basis'],'JobPosting.datePosted')
        self.repo.save(self.c,f['identity'],f['documents'],r)

    def test_parklab_standing_partner_is_recognized_and_grounded(self):
        f=self.captured('parklab','AGENCIES');r=f['result']
        self.assertEqual(r['classification'],'ongoing');self.assertEqual(r['state'],'NEEDS_REVIEW')
        self.assertTrue(any('Sviluppatori web' in e['quote'] for e in r['evidence']))
        self.repo.save(self.c,f['identity'],f['documents'],r)

    def test_tready_routed_to_agencies_and_not_invented_project(self):
        f=self.captured('tready');self.assertEqual(f['result']['route_to'],'AGENCIES')
        self.assertTrue(any(l.get('engine')=='AGENCIES' for l in f['followups']))
        self.assertEqual(self.captured('tready','AGENCIES')['result']['classification'],'ongoing')
        self.assertIsNone(f['result']['compensation']['amount'])

    def test_salento_request_recognized_area_constraint_preserved(self):
        r=self.captured('salento',allowed_regions=['Veneto'])['result']
        self.assertEqual(r['contract'],'external')
        self.assertNotIn(r['state'],('VERIFIED','POTENTIAL'))
        # The role is a real invitation; geography is not fabricated from query.
        self.assertTrue(r['request_blocks'])
        partner=self.captured('salento','AGENCIES',allowed_regions=['Veneto'])['result']
        self.assertEqual(partner['contract'],'external')
        self.assertNotIn(partner['state'],('VERIFIED','POTENTIAL'))
        self.assertFalse(partner['geography']['eligible'])

    def test_business_click_webpage_date_is_not_job_expiration(self):
        r=self.captured('business_click')['result']
        self.assertEqual(r['dates']['page_published_at'],'2022-05-27')
        self.assertIsNone(r['published_at']);self.assertIsNone(r['dates']['expires_at'])
        self.assertEqual(r['contract'],'external');self.assertNotEqual(r['classification'],'expired')

    def test_startup269_cto_equity_and_location_conflict(self):
        r=self.captured('startup269','STARTUPS')['result']
        self.assertEqual(r['classification'],'cofounder');self.assertEqual(r['compensation']['type'],'equity')
        self.assertNotIn(r['state'],('VERIFIED','POTENTIAL'))
        self.assertTrue(r['geography']['conflicts'])

    def test_bitboss_expiration_and_structured_evidence_save(self):
        f=self.captured('bitboss');r=f['result']
        self.assertEqual(r['classification'],'expired');self.assertTrue(r['skills'])
        self.assertEqual(r['dates']['expires_at'],'2022-12-31')
        self.assertTrue(any(e['channel'].startswith('job:') for e in r['evidence']))
        ident=self.repo.save(self.c,f['identity'],f['documents'],r)
        self.assertEqual(self.repo.get(ident)['state'],'REJECTED')

    def test_counterexamples_do_not_create_demand(self):
        for name in ('armari','salatin','quinck','zest'):
            with self.subTest(name=name):
                p=SNAPSHOTS[name]['pages'][SNAPSHOTS[name]['source_url']]
                self.assertEqual(extract(p),[])

    def test_pmi_does_not_borrow_microingranaggi_identity(self):
        f=self.captured('pmi','WEBSITE_REBUILD')
        self.assertEqual(f['result']['classification'],'excluded')
        self.assertEqual(f['identity']['identity_status'],'unknown')
        self.assertEqual(f['identity']['contacts'],[])
        self.assertNotIn('MICROINGRANAGGI',f['identity']['name'])

    def test_webproject_null_address_does_not_crash(self):
        self.captured('webproject','AGENCIES')

    def test_cma_and_aleide_do_not_follow_portfolio_or_service_keywords(self):
        for name in ('cma','aleide'):
            p=SNAPSHOTS[name]['pages'][SNAPSHOTS[name]['source_url']]
            self.assertFalse(any('/lavoro/' in x['url'] or '/sviluppo-web/' in x['url'] for x in followups(p)))

    def test_distinct_vacancies_never_share_contract(self):
        p=page('',extra='<h2>Frontend developer</h2><p>Cerchiamo sviluppatore frontend.</p><p>Contratto a tempo indeterminato.</p><h2>Marketing manager</h2><p>Cerchiamo consulente freelance con Partita IVA.</p>')
        r=self.inspect(p)['result'];self.assertEqual(r['state'],'REJECTED');self.assertEqual(r['classification'],'employee')
        self.assertFalse(any('Partita IVA' in e['quote'] for e in r['evidence']))

    def test_sibling_job_cards_without_headings_are_separate(self):
        p=page('',extra='<article><p>Cerchiamo sviluppatore frontend.</p><p>Contratto a tempo indeterminato.</p></article><article><p>Cerchiamo commerciale freelance con Partita IVA.</p></article>')
        r=self.inspect(p)['result'];self.assertEqual(r['classification'],'employee')
        self.assertFalse(any('Partita IVA' in e['quote'] for e in r['evidence']))

    def test_multiple_jobpostings_keep_employer_date_and_contract_separate(self):
        first={'@type':'JobPosting','title':'Frontend developer','description':'Cerchiamo frontend con contratto a tempo indeterminato.','datePosted':'2026-10-01'}
        second={'@type':'JobPosting','title':'Commerciale','description':'Cerchiamo commerciale freelance con Partita IVA.','datePosted':'2026-10-02'}
        p=page('',extra='<script type="application/ld+json">'+json.dumps([first,second])+'</script>')
        blocks=extract(p);self.assertEqual(len(blocks),1);self.assertEqual(blocks[0]['channel'],'job:0')
        self.assertEqual(blocks[0]['dates']['published_at'],'2026-10-01');self.assertEqual(blocks[0]['contract'],'employee')

    def test_explicit_campaign_area_is_preserved(self):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        c=self.rs.create({'commercial_engines':['FREELANCE'],'regions':['Veneto']})
        self.assertEqual(c['filters']['regions'],['Veneto'])

    def test_related_faq_footer_testimonials_are_not_request_evidence(self):
        p=page('Vendiamo servizi professionali.',extra='<aside><h2>Cerchiamo CTO freelance</h2></aside><section class="testimonial">Cerchiamo WordPress freelance.</section><h2>Domande frequenti</h2><p>Cerchiamo sviluppatori WordPress freelance?</p><footer>Cerchiamo frontend freelance.</footer>')
        self.assertEqual(extract(p),[])

    def test_article_and_service_seller_are_not_buyers(self):
        for p in (page('Cerchiamo WordPress freelance.',url='https://alfa.example/blog/mercato'),page('Offro servizi di sviluppo WordPress freelance.')):
            self.assertEqual(extract(p),[])

    def test_verbs_and_contract_on_separate_lines(self):
        for verb in ('seleziona','selezioniamo','cerchiamo','ricerca','ricercasi'):
            p=page('',extra=f'<h2>Web developer</h2><p>Alfa {verb} professionisti per il team.</p><p>Sviluppatori web, WordPress e frontend.</p><p>Collaboratori esterni con Partita IVA.</p>')
            blocks=extract(p);self.assertTrue(blocks,verb);self.assertEqual(blocks[0]['contract'],'external')

    def test_tampered_offsets_or_quote_rejected(self):
        f=self.captured('sicis');f['result']['evidence'][0]['start']+=1
        with self.assertRaisesRegex(ValueError,'Prova'):self.repo.save(self.c,f['identity'],f['documents'],f['result'])

    def test_technical_role_does_not_inherit_google_ads_contract(self):
        p=SNAPSHOTS['bee_social']['pages'][SNAPSHOTS['bee_social']['source_url']]
        for b in extract(p):
            if b.get('role') and 'Web Designer' in b['role']:
                self.assertNotEqual(b['contract'],'external')

    def test_sample_selection_and_sparse_html_are_distinct(self):
        i={'identity_status':'verified','website':'https://alfa.example/'}
        negative=screen([page('Una descrizione completa dei prodotti e servizi della nostra azienda. '*3,extra='<meta name="viewport" content="width=device-width">')],[])
        self.assertEqual(negative['status'],'negative')
        self.assertTrue(browser_selection(i,negative,{'browser_sample_percent':100})['selected'])
        self.assertTrue(browser_selection(i,negative,{'browser_sample_percent':0})['selected'])  # 3B.3 pertinence replaces random sampling
        sparse=screen([page('')],[])
        self.assertEqual(sparse['status'],'incomplete')
        self.assertTrue(browser_selection(i,sparse,{'browser_sample_percent':0})['selected'])
        self.assertNotIn('empty_offer',{f['code'] for f in screen([page('',url='https://servizi.example/')],[])['findings']})

    def test_budgets_validated(self):
        self.assertEqual(options({'commercial_engines':['FREELANCE'],'work_budget':{'browser_sample_percent':0}})[1]['browser_sample_percent'],0)
        with self.assertRaises(ValueError):options({'commercial_engines':['FREELANCE'],'work_budget':{'browser_sample_percent':101}})

    def test_counts_and_paused_engine_states(self):
        f=self.captured('sicis');self.repo.save(self.c,f['identity'],f['documents'],f['result'])
        with self.store.connect() as db:db.execute("INSERT INTO commercial_engine_runs(campaign_id,engine,state) VALUES (?,'FREELANCE','running')",(self.c['id'],))
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        r=campaign_counts(self.store,self.c['id'])
        self.assertEqual(r['engine_runs'][0]['state'],'paused');self.assertEqual(r['identified_companies'],1)
        self.assertEqual(r['complete_verifications'],1);self.assertEqual(r['incomplete_verifications'],0)

    def test_access_errors_distinguished_and_not_site_defects(self):
        import ssl
        from sales.access_status import AccessIssue
        from sales.operation_outcomes import error_outcome
        for exc,code in [(TimeoutError('temporaneo'),'timeout'),(ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED'),'tls_certificate'),(AccessIssue('robots_denied','Vietato'),'robots_denied')]:
            worker=Coordinator(self.store,{**self.c,'filters':{'commercial_engines':['FREELANCE']}})
            worker.record_failure({'kind':'candidate','strategy':'FREELANCE','payload':{'url':'https://alfa.example/'+code}},exc)
            row=next(r for r in self.repo.listing()['items'] if r['body']['url'].endswith(code))
            self.assertEqual(row['body']['access']['code'],code);self.assertEqual(row['state'],'UNVERIFIABLE');self.assertEqual(row['body']['evidence'],[])
        self.assertFalse(error_outcome(AccessIssue('robots_denied','Vietato'),'candidate')['retryable'])

    def test_linkedin_resolution_is_bounded_and_never_fetches_linkedin(self):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.c=self.rs.create({'commercial_engines':['FREELANCE']});worker=Coordinator(self.store,self.c)
        item={'url':'https://www.linkedin.com/jobs/view/123','title':'Alfa Srl sta assumendo Frontend developer in Italia'}
        self.assertTrue(worker.offer('FREELANCE',item,{'query':'original'}));self.assertFalse(worker.offer('FREELANCE',item,{}))
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM research_tasks WHERE campaign_id=? AND kind='resolve'",(self.c['id'],)).fetchone()
        task={**dict(row),'payload':json.loads(row['payload'])};self.assertEqual(task['kind'],'resolve')
        with patch('sales.commercial.coordinator.acquire',return_value=[]) as search,patch('sales.commercial.inspection.ResearchWeb.get') as fetch:
            with self.store.connect() as db:
                candidate=db.execute("SELECT * FROM research_tasks WHERE campaign_id=? AND kind='candidate'",(self.c['id'],)).fetchone()
            worker.execute({**dict(candidate),'payload':json.loads(candidate['payload'])},lambda:None)
            worker.execute(task,lambda:None)
        search.assert_called_once();fetch.assert_not_called()
        self.assertEqual(self.repo.listing()['items'][0]['state'],'UNVERIFIABLE')

    def test_partner_routing_persists_origin_without_automatic_crm(self):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.create({'commercial_engines':['FREELANCE','AGENCIES']})
        worker=Coordinator(self.store,self.c);found=self.captured('tready')
        task={'kind':'candidate','strategy':'FREELANCE','payload':{'url':SNAPSHOTS['tready']['source_url'],'origin':{'query':'fixture'}}}
        with patch('sales.commercial.coordinator.inspect',return_value=found):worker.execute(task,lambda:None)
        with self.store.connect() as db:
            self.assertEqual(db.execute("select count(*) from research_tasks where strategy='AGENCIES'").fetchone()[0],1)
            self.assertEqual(db.execute('select count(*) from prospects').fetchone()[0],0)
