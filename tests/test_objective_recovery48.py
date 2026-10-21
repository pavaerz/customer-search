"""Saved C48 receipt and synthetic boundaries; no network or production DB."""
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
import test_ai_first as harness
import test_objective_campaign45 as capacity
from sales.agent6 import budget,memory,social
from sales.agent6.discovery_intent import source_issue
from sales.agent6.social_seeds import normalize,links_post

SAVED=json.loads((Path(__file__).parent/'fixtures/ai_first/campaign48/routing.json').read_text())

class PostRouting(unittest.TestCase):
    def test_saved_post_is_not_profile_and_no_commercial_claim_is_added(self):
        post=copy.deepcopy(SAVED['post'])
        self.assertTrue(social.post_url(post['url']))
        self.assertIsNone(source_issue(post))
        self.assertEqual(post,SAVED['post'])
        self.assertEqual(normalize([post['url']]),['https://www.instagram.com/p/DWEVf9MiQBq/'])

    def test_short_and_author_qualified_references_agree_but_not_different_posts(self):
        for kind in ('p','reel'):
            root=f'https://www.instagram.com/{kind}/AbC_123-/'
            named=f'https://instagram.com/agency.name/{kind}/AbC_123-/'
            self.assertTrue(social.same_reference(root,named))
            self.assertEqual(len(normalize([root,named])),1)
            self.assertTrue(links_post({'url':'https://agency.example/jobs','html':f'<a href="{named}">Annuncio</a>'},root))
            self.assertFalse(social.same_reference(root,named.replace('AbC','abc')))
            self.assertFalse(social.same_reference(root,named+'?unknown=other'))
            self.assertFalse(social.same_reference(root,'https://evil.instagram.com/p/AbC_123-/'))

    def test_profiles_collections_comments_and_malformed_paths_stay_excluded(self):
        for path in ('/company/','/company/reels/','/p/','/company/p/',
                     '/company/p/a/comments','/a/b/p/c','/company/p/a%22evil'):
            url='https://instagram.com'+path
            self.assertFalse(social.post_url(url),url)
            self.assertIsNotNone(source_issue({'url':url}))
            with self.assertRaises(ValueError):normalize([url])

    def test_specific_facebook_videos_are_locators_not_access_permission(self):
        from sales.providers import blocked
        for path in ('/Centrodimedicina/videos/299943835860130/','/videos/123456/'):
            url='https://www.facebook.com'+path
            self.assertTrue(social.post_url(url))
            self.assertIsNone(source_issue({'url':url}))
            self.assertTrue(blocked(url))
        for path in ('/Centrodimedicina/videos/','/videos/','/videos/not-an-id/'):
            self.assertFalse(social.post_url('https://facebook.com'+path))

    def test_discovery_keeps_saved_hint_unverified_without_read_or_ai(self):
        base=harness.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        q=harness.query(SAVED['receipt']['query'])
        with patch('sales.agent6.research.acquire',return_value=[SAVED['post']]),patch(
             'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No bypass')),patch(
             'sales.agent6.ai.infer',side_effect=AssertionError('No snippet inference')):
            base.w.execute({'id':1,'kind':'search','strategy':'SOCIAL','payload':q},lambda:None)
        with base.store.connect() as c:
            body=json.loads(c.execute('SELECT body FROM agent6_records').fetchone()[0])
            self.assertEqual(c.execute('SELECT count(*) FROM research_tasks').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
        self.assertEqual(body['validation_status'],'ACCESS_BLOCKED')
        self.assertIsNone(body['decision'])
        self.assertFalse(body['social_source']['original_read'])

class FirstSearchRecovery(unittest.TestCase):
    def setUp(self):
        self.base=capacity.FirstCycleReplay();self.base.setUp();self.addCleanup(self.base.tearDown)
        self.store,self.c,self.cfg=self.base.store,self.base.c,self.base.cfg
        self.base.reserve('AZIENDE','plan:1','replan')

    def receipt(self,changes=None,key='first'):
        row={**SAVED['receipt'],**(changes or {})}
        memory.event(self.store,self.c,'SOCIAL','query',key,row)

    def test_saved_ten_inaccessible_results_allow_one_recovery_with_original_capacity(self):
        self.receipt()
        self.base.add('candidate','AGENCIES',{'url':'https://original.example/'},'pending-other')
        self.assertGreater(budget.remaining(self.store,self.c,'SOCIAL',self.cfg,'replan'),0)
        self.base.reserve('SOCIAL','plan:1','replan')
        self.assertEqual(budget.remaining(self.store,self.c,'SOCIAL',self.cfg,'replan'),0)
        self.assertGreater(budget.remaining(self.store,self.c,'SOCIAL',self.cfg,'verify'),0)
        with self.store.connect() as c:
            count,usd=c.execute('SELECT count(*),sum(reserved_cost) FROM commercial_ai_executions WHERE attempt=1').fetchone()
        self.assertEqual(count,7)
        self.assertLess(usd,1.65)
        self.assertEqual(self.cfg['max_calls_per_campaign'],20)

    def test_no_exception_for_unknown_metadata_technical_failures_or_new_candidates(self):
        for changes in ({'new_urls':1},{'new_urls':None},{'technical_error':'rate_limit'},
                        {'indexed_unverifiable':6},{'results':None},
                        {'indexed_unverifiable':None},{'policy_rejections':None}):
            with self.store.connect() as c:c.execute("DELETE FROM agent6_memory WHERE kind='query'")
            self.receipt(changes)
            self.assertEqual(budget.remaining(self.store,self.c,'SOCIAL',self.cfg,'replan'),0,changes)

    def test_existing_followup_is_completed_before_new_replan(self):
        self.receipt()
        self.base.add('search','SOCIAL',{'selection':'verification','query':'exact post reference'},'followup')
        self.assertEqual(budget.remaining(self.store,self.c,'SOCIAL',self.cfg,'replan'),0)

    def test_second_search_and_completed_original_end_exception(self):
        self.receipt();self.receipt(key='second')
        self.assertEqual(budget.remaining(self.store,self.c,'SOCIAL',self.cfg,'replan'),0)
        with self.store.connect() as c:c.execute("DELETE FROM agent6_memory WHERE kind='query' AND key='second'")
        self.base.reserve('SOCIAL','page:original')
        self.assertEqual(budget.remaining(self.store,self.c,'SOCIAL',self.cfg,'replan'),0)

    def test_hard_cost_and_call_limits_win_and_stop_prevents_reservation(self):
        self.receipt()
        self.assertEqual(budget.remaining(self.store,self.c,'SOCIAL',{**self.cfg,'max_calls_per_campaign':6},'replan'),0)
        self.assertEqual(budget.remaining(self.store,self.c,'SOCIAL',{**self.cfg,'max_estimated_cost':.49},'replan'),0)
        self.base.rs.stop(self.c['id'])
        with self.assertRaises(InterruptedError):self.base.reserve('SOCIAL','plan:1','replan')
