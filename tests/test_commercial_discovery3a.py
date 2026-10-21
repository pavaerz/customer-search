"""Offline 3A acceptance: simulated providers and saved campaign-12 evidence."""
import unittest,json,gzip,sqlite3
from pathlib import Path
from unittest.mock import patch,MagicMock
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from test_commercial_engines import CommercialTestCase,page
from sales.commercial.catalog import ENGINES,options
from sales.commercial.coordinator import Coordinator,run_campaign,acquire
from sales.commercial.discovery import assess,followup_allowed
from sales.commercial.resources import Budget,BudgetExceeded
from sales.commercial.planner import paginate,query_key
from sales.commercial.context import extract,followups
from sales.commercial.social import inspect_social,PublicSocialWeb
from sales.commercial.inspection import inspect
from sales.commercial.attribution import geographic_conflicts
from sales.commercial.geography import region
from sales.content_policy import is_pdf,ExcludedPDF
from sales.providers import PublicWeb
from sales.research_analysis import CompanyWeb

with gzip.open(Path(__file__).parent/'fixtures/commercial3a/campaign12.json.gz','rt') as f:CAPTURED=json.load(f)
POST='https://www.instagram.com/p/DW3VAcqAi2U/'
REQUEST='Ricerchiamo Sviluppatore Web e App. PrestaShop, JavaScript, HTML, CSS. Collaborazione con Freelance con Partita IVA per un progetto digitale da realizzare.'

class Discovery3ATests(CommercialTestCase):
    def worker(self,budget=None,engines=None):
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        self.c=self.rs.create({'commercial_engines':engines or list(ENGINES),'work_budget':budget or {}})
        worker=Coordinator(self.store,self.c);worker.initialize();return worker
    def test_pdf_preflight_all_engines_and_metadata(self):
        w=self.worker()
        for e in ENGINES:
            for item in ({'url':'https://x.example/a.PDF?x=1'},{'url':'https://x.example/a%2Epdf'}, {'url':'https://x.example/download','fileFormat':'PDF'},{'url':'https://x.example/download','contentType':'application/pdf'}, {'url':'https://x.example/d?filename=job.pdf'},{'url':'https://x.example/d','title':'[PDF] Offerta'}):
                with self.subTest(e=e,item=item):self.assertFalse(w.offer(e,item,{'query':'test'}))
        with self.store.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM research_tasks WHERE kind='candidate'").fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM commercial_revisions').fetchone()[0],0)
            self.assertEqual(c.execute("SELECT count(*) FROM commercial_discovery WHERE json_extract(body,'$.reason')='excluded_pdf'").fetchone()[0],24)
        self.assertFalse(is_pdf('https://x.example/a.docx'))
    def test_pdf_headers_close_connection_without_body(self):
        w=PublicWeb(self.store);response=MagicMock();response.status=200
        response.getheader.side_effect=lambda k,d='':'application/pdf' if k=='Content-Type' else d
        conn=MagicMock();conn.getresponse.return_value=response
        sock=MagicMock()
        with patch.object(w,'policy'),patch('sales.providers.socket.getaddrinfo',return_value=[(None,None,None,None,('8.8.8.8',80))]),patch('sales.providers.socket.create_connection',return_value=sock),patch('sales.providers.http.client.HTTPConnection',return_value=conn):
            with self.assertRaises(ExcludedPDF):w._raw('http://x.example/download')
        response.read.assert_not_called();conn.close.assert_called();sock.close.assert_called()
    def test_pdf_redirect_never_connects_to_document(self):
        w=PublicWeb(self.store);response=MagicMock();response.status=302;response.getheader.return_value='/job.pdf'
        conn=MagicMock();conn.getresponse.return_value=response
        with patch.object(w,'policy'),patch('sales.providers.socket.getaddrinfo',return_value=[(None,None,None,None,('8.8.8.8',80))]),patch('sales.providers.socket.create_connection',return_value=MagicMock()),patch('sales.providers.http.client.HTTPConnection',return_value=conn) as make:
            with self.assertRaises(ExcludedPDF):w._raw('http://x.example/start')
        self.assertEqual(make.call_count,1);response.read.assert_not_called()
    def test_pdf_cache_does_not_extract_text(self):
        self.store.cache_set('page:https://x.example/download',{'url':'https://x.example/download','html':'old extracted text','status':200,'content_type':'application/pdf','checked_at':'2026-10-16'})
        with patch('sales.providers.PublicWeb._raw') as raw:
            with self.assertRaises(ExcludedPDF):CompanyWeb(self.store).get('https://x.example/download')
        raw.assert_not_called()
    def test_pdf_queue_legacy_task_excluded_without_opportunity(self):
        w=self.worker(engines=['FREELANCE']);self.rs.enqueue(self.c['id'],'candidate','FREELANCE',{'url':'https://x.example/job','commercial_engine':'FREELANCE'})
        with patch('sales.commercial.search_strategies.plans',return_value=[]),patch('sales.commercial.coordinator.plan',return_value=[]),patch('sales.commercial.inspection.ResearchWeb.get',side_effect=ExcludedPDF('https://x.example/job')),patch('sales.commercial.coordinator.acquire') as api:
            run_campaign(self.store,self.c,lambda:None,lambda x:None)
        api.assert_not_called();self.assertEqual(self.repo.listing()['total'],0)
        c=self.rs.campaign(self.c['id']);self.assertEqual(c['examined'],0);self.assertEqual(c['discovered'],0)
        self.assertEqual(c['tasks']['excluded'],1)
    def test_pdf_followups_and_evidence_rejected(self):
        p=page('Cerchiamo sviluppatore WordPress freelance.',extra='<a href="https://alfa.example/lavora-con-noi.pdf">Sviluppatore freelance</a>')
        self.assertEqual(followups(p),[])
        f=self.inspect(p);f['documents'][0]['content_type']='application/pdf'
        with self.assertRaises(ExcludedPDF):self.repo.save(self.c,f['identity'],f['documents'],f['result'])
    def test_serper_negative_pdf_operator_and_preserved_metadata(self):
        self.worker();self.store.configure({'provider':'serper'})
        with patch('sales.serper_provider.search',return_value=({'results':[]},False)) as search:
            acquire(self.store,{'query':'freelance','page':1},lambda:None)
        self.assertEqual(search.call_args.args[1],'freelance -filetype:pdf')
    def test_verdurazon_a_is_indexed_candidate_not_qualification(self):
        w=self.worker();item={'url':POST,'title':'Verdurazon.it: Ricerchiamo sviluppatore web e app','content':REQUEST}
        self.assertTrue(w.offer('FREELANCE',item,{'query':'simulated fixture','provider':'serper'}))
        t=self.rs.claim(self.c['id'],self.c['generation']);self.assertEqual(t['payload']['discovery']['source_kind'],'instagram_post')
        self.assertEqual(t['payload']['discovery']['accessibility'],'indexed_only');self.assertEqual(self.repo.listing()['total'],0)
    def social(self,p=None,error=None):
        official=page('Sito ufficiale e contatti di esempio.',url='https://alfa.example/',extra='<a href="'+POST+'">Post ufficiale</a>')
        with patch('sales.commercial.social.PublicSocialWeb.get',side_effect=error,return_value=p),patch('sales.commercial.social.CompanyWeb.get',return_value=official):
            return inspect_social(self.store,{'url':POST,'commercial_engine':'FREELANCE','social':'instagram','source_kind':'instagram_post','allowed_regions':['Veneto']})
    def test_verdurazon_b_inaccessible_never_irrelevant(self):
        r=self.social(error=ValueError('robots access denied'))['result'];self.assertEqual(r['state'],'UNVERIFIABLE');self.assertEqual(r['social']['accessibility'],'unavailable');self.assertEqual(r['evidence'],[])
    def test_verdurazon_c_public_text_with_verified_official_link(self):
        p=page(REQUEST,url=POST,extra='<a href="https://alfa.example/">Azienda</a>')
        f=self.social(p);self.assertEqual(f['result']['state'],'VERIFIED',f['result']);self.assertTrue(f['result']['evidence'])
        self.repo.save(self.c,f['identity'],f['documents'],f['result'])
    def test_verdurazon_d_image_requires_multimodal(self):
        r=self.social(page('Guarda la nostra proposta',url=POST,extra='<img src="offer.png">'))['result'];self.assertEqual(r['classification'],'requires_multimodal');self.assertEqual(r['state'],'UNVERIFIABLE');self.assertEqual(r['evidence'],[])
    def test_verdurazon_e_f_no_invented_demand_or_recency(self):
        self.assertEqual(assess({'url':POST,'title':'Le nostre verdure fresche'},'FREELANCE')['decision'],'exclude')
        for dated in (False,True):
            p=page(REQUEST,url=POST,date=dated,extra='<a href="https://alfa.example/">Azienda</a>')
            if dated:p['html']=p['html'].replace(p['checked_at'][:10],'2020-01-01')
            r=self.social(p)['result'];self.assertNotIn(r['state'],('VERIFIED','POTENTIAL'))
        self.assertEqual(r['classification'],'expired')
    def test_social_login_and_facebook_stay_blocked(self):
        web=PublicSocialWeb(self.store)
        for url in ('https://instagram.com/accounts/login/','https://facebook.com/a','https://linkedin.com/jobs/view/12'):self.assertTrue(web.is_blocked(url))
        self.assertFalse(web.is_blocked(POST));self.assertEqual(assess({'url':'https://facebook.com/p/12','title':REQUEST},'FREELANCE')['reason'],'excluded_facebook')
    def test_linkedin_individual_vs_generic_lists(self):
        self.assertEqual(assess({'url':'https://linkedin.com/jobs/developer-veneto','title':REQUEST},'FREELANCE')['decision'],'exclude')
        r=assess({'url':'https://linkedin.com/jobs/view/12','title':'Alfa cerca frontend developer freelance'},'FREELANCE');self.assertEqual(r['decision'],'admit');self.assertEqual(r['source_kind'],'linkedin_job')
    def test_multi_vacancy_real_iobevo_not_one_combined_request(self):
        from sales.commercial.context import position_sections
        self.assertEqual(len(position_sections(CAPTURED['iobevo'])),6)
        blocks=extract(CAPTURED['iobevo'])
        self.assertFalse(any('Excel' in b['text'] for b in blocks))
        self.assertFalse(any(b['end']-b['start']>10000 and not b['segmentation_uncertain'] for b in blocks))
        for b in blocks:
            if not b['segmentation_uncertain']:self.assertLessEqual(b['text'].lower().count('contratto di lavoro:'),1)
        from sales.commercial.qualification import evaluate
        r=evaluate('AGENCIES',{'name':'io bevo','identity_status':'unknown','contacts':[]},CAPTURED['iobevo'],{'eligible':True,'regions':['Toscana']})
        self.assertNotIn(r['state'],('VERIFIED','POTENTIAL'))
    def test_sibling_roles_do_not_lend_contract(self):
        p=page('',extra='<p>Cerchiamo un esperto Excel.</p><p>Collaborazione freelance.</p><p>Cerchiamo uno sviluppatore frontend.</p><p>Contratto a tempo indeterminato.</p>')
        blocks=extract(p);self.assertTrue(blocks);self.assertFalse(any('Excel' in b['text'] for b in blocks))
    def test_definitive_exclusion_blocks_all_followups(self):
        for host in ('diemmebi.com','bucci-composites.com','tecnosystemi.com','mailtogo.it'):
            self.assertFalse(followup_allowed({'classification':'excluded'}, {'url':'https://'+host+'/lavora-con-noi'}))
    def test_campaign12_generic_followups_and_valid_agency(self):
        bad=0
        for r in CAPTURED['results']:
            item=r['item']
            if item.get('depth') and any(x in item['url'] for x in ('trovolavoro','diemmebi','bucci','tecnosystemi','mailtogo')):
                state={'engine':r['engine'],'classification':'excluded' if 'trovolavoro' not in item['url'] else 'irrelevant','source_kind':'job_portal'}
                self.assertFalse(followup_allowed(state,{'url':item['url'],'anchor':item.get('origin',{}).get('anchor','')}));bad+=1
        self.assertGreater(bad,5)
        self.assertTrue(followup_allowed({'engine':'AGENCIES','classification':'no_collaboration','identity':{'group':'agencies'}},{'url':'https://playthinkcreative.it/lavora-con-noi/','anchor':'Collabora con noi'}))
    def test_noise_filters_do_not_use_query_as_evidence(self):
        for item in ({'url':'https://example.org/privacy-policy','title':REQUEST},{'url':'https://dev.example/servizi/startup/web-app-su-misura','title':'Realizziamo app per startup'},{'url':'https://credit.example/collabora','title':'Collaborazione mediatore creditizio'},{'url':'https://news.example/blog/startup','title':'Le migliori startup'}):
            self.assertEqual(assess(item,'STARTUPS',{'query':REQUEST})['decision'],'exclude')
        self.assertEqual(assess({'url':'https://alfa.example/careers','title':'Agenzia web collabora con noi'},'AGENCIES')['reason'],'technical_collaboration_not_attributed')
    def test_atomic_provider_budget_concurrency_and_resume(self):
        w=self.worker({'max_provider_requests':2,'max_serper_credits':2})
        def reserve(i):
            try:Budget(self.store,self.c,'FREELANCE',w.budget).paid();return True
            except BudgetExceeded:return False
        with ThreadPoolExecutor(max_workers=8) as pool:self.assertEqual(sum(pool.map(reserve,range(12))),2)
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.resume(self.c['id'])
        with self.assertRaises(BudgetExceeded):Budget(self.store,self.c,'FREELANCE',w.budget).paid()
        Budget(self.store,self.c,'AGENCIES',w.budget).paid() # independent allocation
    def test_query_candidate_and_followup_budgets_atomic(self):
        w=self.worker({'max_candidates_per_engine':1,'max_followups':1,'max_queries_per_engine':1})
        # Historical campaigns keep the pre-5.1 admission quota after resume.
        self.c['filters'].pop('demand_version',None)
        with self.store.connect() as c:c.execute('UPDATE campaigns SET filters=? WHERE id=?',(json.dumps(self.c['filters']),self.c['id']))
        self.assertTrue(w.offer('FREELANCE',{'url':'https://alfa.example/careers'},{}));self.assertFalse(w.offer('FREELANCE',{'url':'https://beta.example/careers'},{}))
        w.tick();w.tick()
        with self.store.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM research_tasks WHERE kind='search' AND strategy='FREELANCE'").fetchone()[0],0) # candidate limit prevents expansion
    def test_noisy_queries_not_paginated(self):
        w=self.worker()
        for i in range(6):w.offer('STARTUPS',{'url':f'https://news.example/blog/{i}','title':'Articolo startup'}, {'query':'noise'})
        self.assertFalse(paginate(self.store,self.c['id'],'STARTUPS','noise'))
        for i in range(4):w.offer('FREELANCE',{'url':f'https://alfa{i}.example/careers','title':REQUEST},{'query':'good'})
        self.assertTrue(paginate(self.store,self.c['id'],'FREELANCE','good'))
        self.assertEqual(query_key('web freelance -filetype:pdf'),query_key('freelance web'))
    def test_cached_serper_never_reserves_paid_budget(self):
        w=self.worker({'max_serper_credits':1});self.store.configure({'provider':'serper'})
        from sales.serper_provider import search
        from sales.discovery_planner import query_key as provider_key
        self.store.cache_set('serper:search:v2:'+provider_key({'query':'test','page':1,'period':''}),{'results':[]})
        budget=Budget(self.store,self.c,'FREELANCE',w.budget)
        with budget.task(lambda:None),patch('sales.serper_provider.transport') as transport:
            self.assertTrue(search(self.store,'test')[1])
        transport.assert_not_called();self.assertEqual(budget.used('serper_estimated'),0)
    def test_resource_gate_precedes_http_browser_and_runtime(self):
        w=self.worker({'max_http_reads':1,'max_browser_runs':1,'max_runtime_seconds':1})
        b=Budget(self.store,self.c,'FREELANCE',w.budget)
        with b.task(lambda:None):
            b.reserve('http_reads');b.reserve('browser_runs')
            with self.assertRaises(BudgetExceeded):b.reserve('http_reads')
            with self.assertRaises(BudgetExceeded):b.reserve('browser_runs')
        with self.assertRaises(BudgetExceeded):
            with b.task(lambda:None):pass
    def test_remote_italy_not_rejected_by_office_region(self):
        geo={'eligible':True,'regions':['Puglia'],'locations':[],'remote_italy':True,'country':'Italia'}
        self.assertTrue(geographic_conflicts(geo,[],['Veneto'])['eligible'])
        self.assertIsNone(region('Via Veneto 152, Todi'))
    def test_discovery_api_filters_and_history_preserved(self):
        from sales.commercial.storage import discovery_listing
        w=self.worker();w.offer('FREELANCE',{'url':POST,'title':REQUEST},{'query':'test','region':'Veneto'})
        self.assertEqual(discovery_listing(self.store,{'source':'instagram','region':'Veneto'})['total'],1)
        self.assertEqual(discovery_listing(self.store,{'source':'linkedin'})['total'],0)
        self.store.init();self.store.init()
        self.assertEqual(discovery_listing(self.store,{'source':'instagram'})['total'],1)
        with self.store.connect() as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_paid_dispatch_hard_limit_no_transport_after_exhaustion(self):
        from sales.serper_provider import search
        w=self.worker({'max_provider_requests':1,'max_serper_credits':1});self.store.configure({'provider':'serper'})
        budget=Budget(self.store,self.c,'FREELANCE',w.budget)
        with budget.task(lambda:None),patch('sales.serper_provider.api_key',return_value='fixture-key'),patch('sales.serper_provider.MIN_INTERVAL',0),patch('sales.serper_provider.transport',return_value={'organic':[{'link':'https://x.example/download','fileFormat':'PDF'}]}) as transport:
            result,_=search(self.store,'first')
            self.assertTrue(is_pdf(result['results'][0]))
            with self.assertRaises(BudgetExceeded):search(self.store,'second')
        self.assertEqual(transport.call_count,1)
        self.assertEqual(budget.used('provider_requests'),1)
    def test_budget_exhaustion_persists_engine_reason_and_no_false_decision(self):
        w=self.worker({'max_runtime_seconds':1},['FREELANCE'])
        Budget(self.store,self.c,'FREELANCE',w.budget).reserve('runtime_seconds',1)
        self.rs.enqueue(self.c['id'],'candidate','FREELANCE',{'url':'https://alfa.example/careers','commercial_engine':'FREELANCE'})
        with patch('sales.commercial.search_strategies.plans',return_value=[]),patch('sales.commercial.coordinator.plan',return_value=[]),patch('sales.commercial.coordinator.inspect') as inspect_mock:
            run_campaign(self.store,self.c,lambda:None,lambda message:None)
        inspect_mock.assert_not_called();self.assertEqual(self.repo.listing()['total'],0)
        state=self.rs.campaign(self.c['id']);self.assertEqual(state['engine_runs'][0]['state'],'budget_reached');self.assertIn('runtime_seconds',state['engine_runs'][0]['error'])
    def test_stop_guard_blocks_late_resource_and_candidate_insertion(self):
        w=self.worker();b=Budget(self.store,self.c,'FREELANCE',w.budget)
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
        with self.assertRaises(InterruptedError):b.paid()
        self.assertFalse(w.enqueue('candidate','FREELANCE',{'url':'https://alfa.example/careers'},'late'))
    def test_resources_are_shared_across_processes(self):
        import subprocess,sys
        w=self.worker({'max_provider_requests':2,'max_serper_credits':2})
        script="""import json,sys
from sales.db import Store
from sales.commercial.resources import Budget,BudgetExceeded
b=Budget(Store(sys.argv[1]),json.loads(sys.argv[2]),'FREELANCE',json.loads(sys.argv[3]))
n=0
for i in range(4):
 try:b.paid();n+=1
 except BudgetExceeded:pass
print(n)
"""
        args=[sys.executable,'-B','-c',script,str(self.store.path),json.dumps(self.c),json.dumps(w.budget)]
        processes=[subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(3)]
        totals=[]
        for process in processes:
            out,err=process.communicate(timeout=20);self.assertEqual(process.returncode,0,err);totals.append(int(out))
        self.assertEqual(sum(totals),2)
    def test_devology_is_supplier_not_startup_buyer(self):
        r=next(r for r in CAPTURED['results'] if 'devologysystem' in r['item']['url'])
        self.assertEqual(assess(r['item'],'STARTUPS')['reason'],'service_seller')
    def test_pdf_auxiliary_response_is_logged_without_opportunity_for_pdf(self):
        w=self.worker()
        p=page('Cerchiamo sviluppatore WordPress freelance.',extra='<a href="https://alfa.example/contatti/download">Contatti</a>')
        def read(web,url):
            if url.endswith('/download'):return {'url':url,'content_type':'application/pdf','status':200,'html':''}
            return {**p,'url':url}
        with Budget(self.store,self.c,'FREELANCE',w.budget).task(lambda:None),patch('sales.commercial.inspection.ResearchWeb.get',read):
            f=inspect(self.store,{'url':p['url'],'commercial_engine':'FREELANCE'})
        self.assertFalse(any(is_pdf(d) for d in f['documents']))
        with self.store.connect() as c:self.assertGreater(c.execute("SELECT count(*) FROM research_events WHERE kind='excluded_pdf'").fetchone()[0],0)

    def test_mislabelled_pdf_stops_after_signature(self):
        web=PublicWeb(self.store);response=MagicMock();response.status=200
        response.getheader.return_value='text/html';response.read.side_effect=[b'%PDF-',AssertionError('Body must not be downloaded')]
        conn=MagicMock();conn.getresponse.return_value=response
        with patch.object(web,'policy'),patch('sales.providers.socket.getaddrinfo',return_value=[(None,None,None,None,('8.8.8.8',80))]),patch('sales.providers.socket.create_connection',return_value=MagicMock()),patch('sales.providers.http.client.HTTPConnection',return_value=conn):
            with self.assertRaises(ExcludedPDF):web._raw('http://x.example/looks-like-html')
        response.read.assert_called_once_with(5)
