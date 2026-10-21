"""C53 saved originals/receipts; synthetic boundaries are labelled explicitly."""
import copy
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_ai_first as h
from sales.agent6 import evidence
from sales.agent6.discovery_intent import source_issue
from sales.agent6.indexed_recovery import candidate_issue
from sales.commercial.inspection import document
from sales.db import digest

ROOT=Path(__file__).parent/'fixtures/ai_first/source56'
PAGE=json.loads(gzip.decompress((ROOT/'article.json.gz').read_bytes()))
RECEIPTS=json.loads((ROOT/'receipts.json').read_text())


class Article(unittest.TestCase):
    def test_real_article_body_replaces_sidebar_without_inventing_currentness(self):
        doc=document(PAGE);p=evidence.packet(PAGE,doc);u=p['units'][0]
        proofs=evidence.passages(p,u,3000,source_content=True)
        text='\n'.join(e['text'] for e in proofs)
        self.assertIn('Digitazon',text)
        self.assertIn('corso per sviluppatore web',text)
        for sidebar in ('TOPIC','ARTICOLI PIÙ LETTI','ULTIMI ARTICOLI','Iscriviti alla newsletter'):
            self.assertNotIn(sidebar,text)
        self.assertLessEqual(sum(len(e['text'].encode()) for e in proofs),3000)
        self.assertTrue(any(d['role']=='published_at' and d['value']=='2021-12-21' for d in u['dates']))
        for e in proofs:
            self.assertEqual(e['text'],doc['text'][e['offset']:e['offset']+len(e['text'])])
            self.assertEqual(e['hash'],digest(e['text']))
        self.assertNotIn('decision',p)

    def test_synthetic_widget_markers_are_exact_and_hidden_content_stays_hidden(self):
        from test_objective_source_context45 import packet
        for marker in ('class="elementor-widget-theme-post-content"',
                       'data-widget_type="theme-post-content.default"'):
            p=packet('<main><p>Layout noise.</p><div '+marker+'><p>Real article body.</p>'
                     '<aside><p>Sidebar noise.</p></aside><div hidden><p>Hidden noise.</p></div>'
                     '</div></main>')
            text='\n'.join(e['text'] for e in evidence.passages(p,p['units'][0],source_content=True))
            self.assertEqual(text,'Real article body.')
        for marker in ('theme-post-excerpt.default','theme-post-title.default','posts.default'):
            p=packet('<main><p>Real main body.</p><div data-widget_type="'+marker+'"><p>Generic widget.</p></div></main>')
            text='\n'.join(e['text'] for e in evidence.passages(p,p['units'][0],source_content=True))
            self.assertIn('Real main body.',text)

    def test_real_body_reaches_original_ai_path_with_dates_and_without_auto_promotion(self):
        base=h.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        seen=[]
        base.w.enqueue('candidate','STARTUPS',{'url':PAGE['url'],'original_page':copy.deepcopy(PAGE),
            'query':'startup Veneto cerca sviluppatore freelance','depth':0},'source56')
        with base.store.connect() as db:
            row=db.execute("SELECT * FROM research_tasks WHERE fingerprint='source56'").fetchone()
            task={**dict(row),'payload':json.loads(row['payload'])}
        def infer(p,c,check):
            seen.append(copy.deepcopy(p));return {'output':{},'usage':{}}
        with patch('sales.agent6.ai.infer',side_effect=infer),patch(
                'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('Offline checkpoint only')):
            base.w.execute(task,lambda:None)
        self.assertEqual(len(seen),1)
        text='\n'.join(e['text'] for e in seen[0]['evidence'])
        self.assertIn('Digitazon',text)
        self.assertNotIn('ARTICOLI PIÙ LETTI',text)
        with base.store.connect() as db:
            bodies=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
        self.assertFalse(any(b.get('decision')=='INTERESTING' for b in bodies))


class Routing(unittest.TestCase):
    def test_real_collections_are_routed_before_single_company_inference(self):
        hosts=('randstad.com','englishjobs.it','michaelpage.it','devjobsscanner.com',
               'applavoro.it','paginegialle.it','regione.veneto.it','unioncamereveneto.it')
        for host in hosts:
            items=[r for r in RECEIPTS if host in r['url']]
            self.assertTrue(items,host)
            for item in items:
                with self.subTest(url=item['url']):
                    result=source_issue(item)
                    self.assertIsNotNone(result)
                    self.assertEqual(result['source_role'],'COLLECTION')

    def test_synthetic_specific_pages_on_same_hosts_and_agency_jobs_are_preserved(self):
        self.assertIsNone(source_issue({'url':'https://agency.example/',
                                       'title':'Alfa: siti per la Regione del Veneto'}))
        for url in ('https://www.randstad.com/jobs/frontend-freelance_123456/',
                    'https://englishjobs.it/job/12345',
                    'https://www.michaelpage.it/job-detail/frontend/ref/jn-123',
                    'https://www.devjobsscanner.com/job/1234/',
                    'https://www.applavoro.it/annuncio-1234',
                    'https://www.paginegialle.it/impresa-alfa',
                    'https://www.regione.veneto.it/notizie/impresa-alfa',
                    'https://www.unioncamereveneto.it/impresa-alfa-espansione/',
                    'https://agency.example/jobs/frontend/',
                    'https://agency.example/lavora-con-noi/'):
            self.assertIsNone(source_issue({'url':url,'title':'Alfa cerca frontend freelance'}),url)

    def test_saved_startup_brand_requires_legal_name_hint_but_never_verifies_identity(self):
        item=next(r for r in RECEIPTS if r['url']=='https://startup-bakery.com/')
        origin={'company_hint':'Startup Bakery srl'}
        self.assertIsNone(candidate_issue(item,origin))
        self.assertIsNotNone(candidate_issue({**item,'snippet':'','content':''},origin))
        self.assertIsNotNone(candidate_issue({**item,'title':'Startup Bakers | Home'},origin))
        self.assertIsNotNone(candidate_issue({**item,'title':'Startup BakeryPlus | Home'},origin))
        club=next(r for r in RECEIPTS if '/en/bakers-club/' in r['url'])
        self.assertIsNotNone(candidate_issue(club,origin))
        self.assertEqual(origin,{'company_hint':'Startup Bakery srl'})

    def test_saved_collections_never_enter_queue_or_consume_inference(self):
        base=h.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        items=[r for r in RECEIPTS if source_issue(r)]
        with patch('sales.agent6.research.acquire',return_value=items),patch(
                'sales.agent6.ai.infer',side_effect=AssertionError('No AI for collection')),patch(
                'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No collection download')):
            base.w.execute({'id':1,'kind':'search','strategy':'AGENCIES',
                            'payload':h.query('agenzia web Veneto cerca freelance frontend')},lambda:None)
        with base.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM research_tasks WHERE kind='candidate'").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM agent6_records').fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM commercial_discovery WHERE decision='exclude'").fetchone()[0],len(items))


class FollowupSpend(unittest.TestCase):
    def test_actual_model_answer_is_kept_but_supplier_only_followup_is_not_dispatched(self):
        from scripts.run_objective_validation_sol import SOL_CONFIG
        output=json.loads((ROOT/'model-response.json').read_text())
        base=h.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        base.c['filters']['commercial']['ai'].update(SOL_CONFIG)
        base.c['filters']['commercial']['ai']['provider']='MOCK'
        base.w.enqueue('candidate','STARTUPS',{'url':PAGE['url'],'original_page':copy.deepcopy(PAGE),
            'query':'startup Veneto "collabora con noi" sviluppatore web freelance -site:linkedin.com',
            'strategy':'technical_cofounder','depth':0},'replay56')
        with base.store.connect() as db:
            row=db.execute("SELECT * FROM research_tasks WHERE fingerprint='replay56'").fetchone()
            task={**dict(row),'payload':json.loads(row['payload'])}
        with patch.object(base.w,'model',return_value={'status':'completed','output':output}),patch(
                'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No network')):
            base.w.execute(task,lambda:None)
        with base.store.connect() as db:
            bodies=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
            self.assertEqual(db.execute("SELECT count(*) FROM research_tasks WHERE kind='search'").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM agent6_memory WHERE kind='research_action_not_scheduled'").fetchone()[0],1)
        b=bodies[0]
        self.assertEqual(b['entity_name'],'Digitazon')
        self.assertEqual(b['decision'],'NEEDS_RESEARCH')
        self.assertEqual(b['freshness']['status'],'STALE')
        self.assertEqual(b['research_action']['type'],'SEARCH_SUBJECT')
        self.assertFalse(b['research_dispatch']['allowed'])

    def test_observed_request_or_gap_can_still_justify_investigation(self):
        from sales.agent6.research_dispatch import assess
        body={'research_action':{'type':'SEARCH_SUBJECT'},
              'commercial_assessment':{'intent':'SUPPLYING_SERVICES'},'facts':[{'field':'signal'}]}
        for action in ('SEARCH_SUBJECT','READ_LINK','INSPECT_BROWSER'):
            body['research_action']['type']=action
            self.assertFalse(assess(body)['allowed'])
            for field in ('request','digital_gap'):
                self.assertTrue(assess({**body,'facts':[{'field':field}]})['allowed'])
        for intent in ('REQUESTING_EXTERNAL','ACCEPTING_EXTERNAL','BUSINESS_EVENT','UNKNOWN'):
            self.assertTrue(assess({**body,'commercial_assessment':{'intent':intent}})['allowed'])
