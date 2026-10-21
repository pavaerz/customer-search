"""Manual social links: all transport/model responses are offline doubles."""
import copy
import json
import unittest
from unittest.mock import patch

import test_ai_first as harness
from sales.agent6 import api
from sales.agent6.coordinator import AgentCoordinator
from sales.agent6.social_seeds import normalize,recovery_query,links_post
from sales.db import encode

POST='https://www.instagram.com/p/ExampleRequest/'


class InputPolicy(unittest.TestCase):
    def test_accepts_post_jobs_reel_and_strips_viewer_parameters(self):
        self.assertEqual(normalize([POST+'?igsh=private#comment',POST]),[POST])
        for url in ('https://linkedin.com/jobs/view/123456789/',
                    'https://linkedin.com/posts/alfa-activity-1234567890123/',
                    'https://instagram.com/reel/Example/'):
            self.assertEqual(len(normalize([url])),1)

    def test_rejects_profiles_credentials_unsupported_hosts_and_non_urls(self):
        for url in ('https://www.instagram.com/company/','https://linkedin.com/company/alfa/',
                    'https://linkedin.com.evil.example/posts/a/','https://127.0.0.1/p/a/',
                    'https://user:secret@instagram.com/p/a/','javascript:alert(1)',
                    'https://www.instagram.com/p/a\\secret/',
                    'https://instagram.com/p/a%22%20OR%20secret/',
                    'https://instagram.com:80/p/a/',12):
            with self.subTest(url=url),self.assertRaises(ValueError):normalize([url])
        with self.assertRaises(ValueError):normalize([POST]*21)
        with self.assertRaises(ValueError):normalize(POST)

    def test_lookup_is_bounded_by_the_supplied_post_not_generic_topics(self):
        query=recovery_query(POST)
        self.assertIn('"ExampleRequest"',query['query'])
        self.assertEqual(query['social_origin']['url'],POST)
        self.assertIn('-site:instagram.com',query['query'])
        self.assertFalse(query['social_origin']['original_read'])
        long='https://www.linkedin.com/posts/'+('longslug-'*30)+'activity-12345678901234/'
        self.assertLess(len(recovery_query(long)['query']),300)
        self.assertIn('12345678901234',recovery_query(long)['query'])
        self.assertIsNone(recovery_query('https://linkedin.com/posts/'+'a'*300))

    def test_reference_requires_actual_link_not_snippet_or_visible_mention(self):
        page={'url':'https://alfa.example/jobs','html':'<p>'+POST+'</p>'}
        self.assertFalse(links_post(page,POST))
        page['html']='<a href="'+POST+'?utm_source=social">Annuncio</a>'
        self.assertTrue(links_post(page,POST))


class QueuePath(unittest.TestCase):
    def setUp(self):
        self.base=harness.IntegratedPath();self.base.setUp()
        self.store,self.rs=self.base.store,self.base.rs

    def tearDown(self):
        self.base.tearDown()

    def filters(self):
        f=copy.deepcopy(self.base.filters)
        f.update(decision_engine='ai_first_1',commercial_engines=['SOCIAL'],social_urls=[POST])
        return f

    def start(self):
        f=self.filters()
        f['deep_plan_token']=api.preview(self.store,f)['approval_token']
        self.rs.stop(self.base.c['id']);self.rs.paused(self.base.c['id'])
        c=self.rs.create(f);worker=AgentCoordinator(self.store,c);worker.initialize()
        return c,worker

    def task(self,kind):
        with self.store.connect() as c:
            row=c.execute('SELECT * FROM research_tasks WHERE kind=? ORDER BY id DESC',(kind,)).fetchone()
            return {**dict(row),'payload':json.loads(row['payload'])}

    def test_preview_no_queue_or_calls_and_token_bound_to_manual_urls(self):
        f=self.filters()
        with patch('socket.create_connection',side_effect=AssertionError('Preview has no transport')):
            result=api.preview(self.store,f)
            changed=api.preview(self.store,{**f,'social_urls':['https://instagram.com/p/Another/']})
        self.assertEqual(result['social_urls'],[POST])
        self.assertNotEqual(result['approval_token'],changed['approval_token'])
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM research_tasks').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
        with self.assertRaises(ValueError):api.preview(self.store,{**f,'commercial_engines':['AGENCIES']})

    def test_initialize_resume_and_blocked_read_keep_one_hint_and_one_lookup(self):
        campaign,worker=self.start()
        worker.initialize()
        task=self.task('candidate')
        with patch('sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No social scraping')),patch(
                'sales.agent6.ai.infer',side_effect=AssertionError('No snippet qualification')):
            worker.execute(task,lambda:None)
            worker.execute(task,lambda:None)
        with self.store.connect() as c:
            tasks=dict(c.execute('SELECT kind,count(*) FROM research_tasks WHERE campaign_id=? GROUP BY kind',(campaign['id'],)))
            self.assertEqual(tasks,{'candidate':1,'search':1})
            body=json.loads(c.execute('SELECT body FROM agent6_records WHERE campaign_id=?',(campaign['id'],)).fetchone()[0])
            self.assertEqual(body['state'],'UNVERIFIABLE')
            self.assertIsNone(body['decision'])
            self.assertFalse(body['social_source']['original_read'])
            self.assertEqual(c.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
        self.rs.stop(campaign['id'])
        with self.assertRaises(InterruptedError):worker.execute(task,lambda:None)

    def test_alternative_without_reference_stays_unverified_without_ai_spend(self):
        campaign,worker=self.start()
        worker.enqueue('candidate','SOCIAL',{'url':'https://alfa.example/jobs',
                       'social_origin':recovery_query(POST)['social_origin']},'alternative')
        page={'url':'https://alfa.example/jobs','status':200,'checked_at':harness.DATE,
              'html':'<title>Alfa Srl</title><p>Pagina generica senza riferimento al post.</p>'}
        with patch('sales.agent6.research.CompanyWeb.get',return_value=page),patch(
                'sales.agent6.ai.infer',side_effect=AssertionError('Unrelated alternative')):
            worker.execute(self.task('candidate'),lambda:None)
        with self.store.connect() as c:
            b=json.loads(c.execute('SELECT body FROM agent6_records ORDER BY id DESC').fetchone()[0])
        self.assertEqual(b['validation_status'],'SOURCE_ATTRIBUTION_UNVERIFIED')
        self.assertIsNone(b['decision'])

    def test_exhausted_query_budget_preserves_hint_without_raising_limits(self):
        from sales.commercial.resources import BudgetExceeded
        campaign,worker=self.start()
        limits=copy.deepcopy(worker.budget)
        with patch.object(worker,'enqueue',side_effect=BudgetExceeded('queries')),patch(
                'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No bypass')):
            worker.execute(self.task('candidate'),lambda:None)
        self.assertEqual(worker.budget,limits)
        with self.store.connect() as c:
            b=json.loads(c.execute('SELECT body FROM agent6_records ORDER BY id DESC').fetchone()[0])
            self.assertEqual(b['state'],'UNVERIFIABLE')
            self.assertIsNone(b['decision'])
            event=json.loads(c.execute("SELECT body FROM agent6_memory WHERE kind='social_recovery'").fetchone()[0])
            self.assertEqual(event['reason'],'configured_budget_exhausted')
            self.assertEqual(c.execute("SELECT count(*) FROM research_tasks WHERE kind='search'").fetchone()[0],0)

    def test_official_alternative_keeps_social_original_unverified(self):
        campaign,worker=self.start()
        worker.enqueue('candidate','SOCIAL',{'url':'https://alfa.example/jobs',
                       'social_origin':recovery_query(POST)['social_origin']},'official-alternative')
        page={'url':'https://alfa.example/jobs','status':200,'checked_at':harness.DATE,
              'html':'<title>Alfa Srl</title>'+''.join('<p>'+line+'</p>' for line in harness.TEXT.splitlines())+
                     '<a href="'+POST+'">Il nostro annuncio social</a>'}
        identity={'identity_status':'verified','name':'Alfa Srl','website':page['url'],'contacts':[]}
        with patch('sales.agent6.research.CompanyWeb.get',return_value=page),patch(
                'sales.agent6.research.identity_from',return_value=identity),patch(
                'sales.agent6.research.locate',return_value={'eligible':True,'regions':['Veneto'],'remote_italy':False}),patch(
                'sales.agent6.ai.infer',side_effect=lambda p,c,g:{'output':harness.response(p),'usage':{}}):
            worker.execute(self.task('candidate'),lambda:None)
        with self.store.connect() as c:
            b=json.loads(c.execute('SELECT body FROM agent6_records ORDER BY id DESC').fetchone()[0])
        self.assertEqual(b['decision'],'INTERESTING',b.get('technical_error'))
        self.assertEqual(b['url'],'https://alfa.example/jobs')
        self.assertTrue(b['original'])
        self.assertFalse(b['social_origin']['original_read'])
        self.assertEqual(b['open_paid_project'],'UNKNOWN')
