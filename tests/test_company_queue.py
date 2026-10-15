import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store, now
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.research_analysis import ResearchWeb,LocalResearcher,inspect_candidate,select_pages
from sales.discovery_planner import Planner
from sales.company_pages import news_links
from sales.company_queue import completed_review
from datetime import date


class CompanyQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.sqlite3');self.store.init()
        self.rs=ResearchStore(self.store);self.c=self.rs.create({'regions':['Veneto'],'projects':['website']});self.f=Funnel(self.rs)
        self.p={'url':'https://alfa.example/','company_key':'IT12345678901','company_host':'alfa.example','official_link':True,'strategy':'companies','root_query_key':'one','subject':'Alfa Srl'}
    def tearDown(self):self.tmp.cleanup()
    def rows(self,table='discovery_frontier'):
        with self.store.connect() as c:return [dict(x) for x in c.execute('SELECT * FROM '+table)]
    def add(self,p,key):return self.f.offer(self.c['id'],'verify','companies',p,key)

    def test_pending_and_assigned_merge_preserves_all_evidence_and_resume_id(self):
        self.add({**self.p,'source_documents':[{'id':'original','text':'lancio'}]},'first')
        self.f.fill(self.c);tid=self.rows('research_tasks')[0]['id']
        extra={**self.p,'url':'https://alfa.example/new','root_query_key':'two','source_documents':[{'id':'second','text':'controprova'}],'investigation_question':{'id':'q','question':'Già realizzato?'}}
        self.assertTrue(self.add(extra,'second'));self.assertFalse(self.add(extra,'second'))
        task=self.rows('research_tasks')[0];payload=json.loads(task['payload'])
        self.assertEqual(len(self.rows()),1);self.assertEqual(task['id'],tid)
        self.assertEqual({d['id'] for d in payload['source_documents']},{'original','second'})
        self.assertEqual({d['root_query_key'] for d in payload['review_inputs']},{'one','two'})
        self.assertEqual(payload['investigation_plan'][0]['id'],'q')
        _,pending=Planner(self.rs).query_evidence(self.c,{'fingerprint':'two','urls':'[]'})
        self.assertTrue(pending)
        self.rs.stop(self.c['id']);self.assertFalse(self.add(extra,'late'));self.rs.paused(self.c['id'])
        resumed=self.rs.resume(self.c['id']);task=self.rs.claim(resumed['id'],resumed['generation'])
        self.assertEqual(task['id'],tid);self.assertEqual(task['payload'],payload)

    def test_namesakes_publishers_and_unverified_keys_do_not_merge(self):
        self.add(self.p,'first')
        for i,p in enumerate([{**self.p,'company_key':'IT99999999999'}, {**self.p,'publisher':True}, {**self.p,'official_link':False}, {**self.p,'url':'https://other.example/','company_host':'other.example'}]):
            self.assertTrue(self.add(p,str(i)))
        self.assertEqual(len(self.rows()),5)

    def test_running_review_is_immutable_and_new_evidence_can_follow_completed_work(self):
        self.add(self.p,'first');self.f.fill(self.c);task=self.rs.claim(self.c['id'],self.c['generation'])
        self.add({**self.p,'url':'https://alfa.example/new'},'new')
        self.assertEqual(len(self.rows()),2)
        self.assertNotIn('review_inputs',json.loads(self.rows('research_tasks')[0]['payload']))
        self.rs.task_done(task['id']);self.f.fill(self.c)
        task2=self.rs.claim(self.c['id'],self.c['generation']);self.rs.task_done(task2['id'])
        self.assertTrue(self.add({**self.p,'url':'https://alfa.example/later'},'later'))
        self.assertEqual(len(self.rows()),3)

    def test_merged_originals_are_read_by_real_inspector_before_analysis(self):
        extra={**self.p,'url':'https://alfa.example/new'};self.add(self.p,'one');self.add(extra,'two')
        payload=json.loads(self.rows()[0]['payload']);seen=[];analyzed=[]
        def read(web,url):
            seen.append(url)
            return {'url':url,'status':200,'checked_at':now(),'html':'<title>Alfa Srl</title><p>Produciamo impianti.</p><footer><p>Via Roma 1, 35100 Padova (PD)</p><p>P.IVA 12345678901</p><a href="mailto:info@alfa.example">info@alfa.example</a></footer>'}
        def analyze(owner,identity,docs,coverage):analyzed.extend(d['url'] for d in docs);return [],{},{},[]
        with patch.object(ResearchWeb,'get',read),patch.object(LocalResearcher,'analyze',analyze):
            result=inspect_candidate(self.store,payload,lambda:None)
        self.assertIn(extra['url'],seen);self.assertIn(extra['url'],analyzed)
        self.assertNotEqual(result['assessment']['status'],'qualified')

    def test_dated_articles_do_not_replace_sections_and_counterproof_is_read(self):
        links=[{'url':'https://alfa.example/legalita','label':'7 Agosto 2014 Rating legalità: azienda e servizi'},
               {'url':'https://alfa.example/contatti','label':'Contatti'},
               {'url':'https://alfa.example/privacy','label':'Privacy'},
               {'url':'https://alfa.example/new-site','label':'9 Dicembre 2025 Online il nuovo sito web aziendale'},
               {'url':'https://alfa.example/europa','label':'11 Giugno 2026 Evoluzione Europea nei mercati esteri'}]
        sections=select_pages(links)
        self.assertIn(links[1]['url'],sections);self.assertIn(links[2]['url'],sections)
        self.assertNotIn(links[0]['url'],sections)
        self.assertEqual(news_links(links,date(2026,10,14)),[links[3]['url'],links[4]['url']])
        self.assertEqual(news_links([{'url':'https://alfa.example/future','label':'1 Gennaio 2027 Nuovo sito web online'}],date(2026,10,14)),[])

    def test_completed_review_only_reused_for_exact_sources_and_current_campaign(self):
        identity={'name':'Alfa Srl','website':self.p['url'],'legal_id':self.p['company_key'],'identity_status':'verified','region':'Veneto','contacts':[]}
        doc={'id':'d1','url':self.p['url'],'text':'Testo originale','research_text':'Testo originale','content_hash':'h1','checked_at':now()}
        result={'state':'promising','details':{'document':doc}}
        payload={**self.p,'followup_depth':1,'source_documents':[doc]}
        assessment={'status':'rejected','analysis_status':'completed','score':0,'project':'none','signals':[]}
        aid=self.rs.save(self.c['id'],self.c['generation'],None,identity,[doc],assessment)
        self.assertEqual(completed_review(self.rs,self.c,payload,result)['id'],aid)
        changed={'state':'promising','details':{'document':{**doc,'research_text':'Nuova prova'}}}
        self.assertIsNone(completed_review(self.rs,self.c,payload,changed))
        self.assertIsNone(completed_review(self.rs,{**self.c,'id':999},payload,result))
        self.assertIsNone(completed_review(self.rs,self.c,{**payload,'company_key':'IT99999999999'},result))
        self.assertIsNone(completed_review(self.rs,self.c,payload,{'state':'rejected','details':result['details']}))
        # A technical or incomplete latest review must not be overwritten by a
        # completed older result, even when every text hash matches.
        self.rs.save(self.c['id'],self.c['generation'],None,identity,[doc],{**assessment,'status':'unverifiable','analysis_status':'incomplete'})
        self.assertIsNone(completed_review(self.rs,self.c,payload,result))

    def test_directory_reads_do_not_starve_company_queries_or_other_strategies(self):
        # Reproduce the pilot: directory work exists before any company query.
        for i in range(8):
            self.rs.enqueue(self.c['id'],'candidate','companies',{'url':f'https://directory.example/{i}'},str(i))
        with self.store.connect() as c:c.execute("UPDATE research_tasks SET state='done',attempts=1")
        for strategy in ('explicit','startup','companies'):
            for i in range(2):self.f.offer(self.c['id'],'search',strategy,{'query':strategy+str(i)},strategy+str(i))
        self.f.fill(self.c);order=[]
        for _ in range(6):
            task=self.rs.claim(self.c['id'],self.c['generation']);order.append(task['strategy']);self.rs.task_done(task['id'])
        self.assertEqual(order[0],'companies')
        self.assertEqual(set(order[:3]),{'companies','explicit','startup'})
        self.assertEqual(set(order[3:]),{'companies','explicit','startup'})

    def test_directory_candidates_are_not_counted_as_company_screenings(self):
        for i in range(8):self.rs.enqueue(self.c['id'],'candidate','companies',{'url':f'https://directory.example/{i}','publisher':True},str(i))
        self.rs.enqueue(self.c['id'],'candidate','change',{'url':'https://news.example/done'},'news-done')
        with self.store.connect() as c:c.execute("UPDATE research_tasks SET state='done'")
        self.f.offer(self.c['id'],'candidate','change',{'url':'https://news.example/next'},'next-news')
        self.f.offer(self.c['id'],'candidate','companies',{'url':'https://alfa.example/'},'first-company')
        self.f.fill(self.c);task=self.rs.claim(self.c['id'],self.c['generation'])
        self.assertEqual(task['payload']['url'],'https://alfa.example/')
