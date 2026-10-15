"""Commercial negatives must close a branch, technical gaps must not."""
import copy
import json
import unittest

from test_research import sample
import test_discovery_control as adaptive_fixture
from sales.discovery_planner import company_yield
from sales.research_rules import qualify


class CompletedInvestigationTests(unittest.TestCase):
    def negative(self):
        identity,docs,signals,proposal,review=sample()
        signals[0].update(kind='business',quote=docs[1]['text'])
        proposal.update(project='none',support_ids=[],scope='unknown',feasibility='unknown')
        review.update(status='insufficient',support_ids=[],outcome='no_documented_project')
        return identity,docs,signals,proposal,review

    def test_completed_no_project_closes_investigation_without_claiming_no_need_exists(self):
        result=qualify(*self.negative())
        self.assertEqual(result['status'],'rejected')
        self.assertIn('fonti esaminate',result['reasons'][0])
        self.assertIn('nuovi elementi',result['next_action'])
        self.assertIsNone(result['budget'])
        self.assertFalse(next(g for g in result['gates'] if g['key']=='need')['passed'])

    def test_empty_extraction_or_partial_coverage_cannot_be_commercial_rejection(self):
        args=self.negative()
        for section in ('identity','offer','contact','solutions'):
            incomplete=copy.deepcopy(args)
            incomplete[3]['checked_sections'].remove(section)
            self.assertEqual(qualify(*incomplete)['status'],'needs_review')
        args[3].pop('project');args[4].pop('outcome');args[2].clear()
        self.assertEqual(qualify(*args)['status'],'needs_review')

    def test_technical_failure_and_single_page_do_not_close_commercially(self):
        args=self.negative()
        self.assertEqual(qualify(*args,limits=['Shop: HTTP 503'])['status'],'unverifiable')
        args[1][1]=copy.deepcopy(args[1][0])
        self.assertEqual(qualify(*args)['status'],'needs_review')

    def test_one_company_many_urls_does_not_outvote_final_review(self):
        identity=sample()[0]
        rows=[{'url':identity['website']+str(i),'state':'needs_review',
               'details':json.dumps({'identity':identity,'company_ready':True})} for i in range(8)]
        rows[-1].update(assessment_id=2,assessment_status='rejected')
        self.assertEqual(company_yield(rows),[{'state':'rejected','useful':False,'contactable':False}])
        rows[-1]['assessment_status']='unverifiable'
        self.assertEqual(company_yield(rows),[{'state':'unverifiable','useful':False,'contactable':False}])
        rows[-1]['assessment_status']='qualified'
        self.assertEqual(company_yield(rows),[{'state':'qualified','useful':True,'contactable':False}])


class CompletedBranchTests(unittest.TestCase):
    setUp=adaptive_fixture.AdaptiveTests.setUp
    tearDown=adaptive_fixture.AdaptiveTests.tearDown
    branch=adaptive_fixture.AdaptiveTests.branch
    query=adaptive_fixture.AdaptiveTests.query

    def test_wait_for_commercial_review_then_change_query_on_negative(self):
        task=self.branch();root=task['payload']['query_key']
        args=CompletedInvestigationTests().negative()
        payload={'url':args[0]['website'],'strategy':'change','root_query_key':root}
        self.f.transition(self.c,payload,'needs_review','Impresa identificata',{'identity':args[0],'company_ready':True})
        self.p.observed(self.c,task,[payload['url']],1)
        self.f.offer(self.c['id'],'verify','change',payload,'deep-check')
        self.assertEqual(self.p.tick(self.c),0)
        assessment=qualify(*args)
        aid=self.rs.save(self.c['id'],self.c['generation'],None,args[0],args[1],assessment)
        self.f.transition(self.c,payload,assessment['status'],assessment['reasons'][0],assessment_id=aid)
        with self.store.connect() as c:
            c.execute("UPDATE discovery_frontier SET state='done' WHERE fingerprint='deep-check'")
        self.p.tick(self.c)
        next_task=self.query()
        self.assertEqual(next_task['payload']['page'],1)
        self.assertNotEqual(next_task['payload']['query'],task['payload']['query'])
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT decision FROM discovery_queries WHERE fingerprint=?',(root,)).fetchone()[0],'dry')

    def test_publisher_does_not_turn_company_technical_failure_into_dry_branch(self):
        task=self.branch();root=task['payload']['query_key']
        url='https://publisher.example/article'
        self.f.transition(self.c,{'url':url,'root_query_key':root},'needs_review','Fonte risolta',{'publisher':True})
        self.f.transition(self.c,{'url':'https://alfa.example/','root_query_key':root},'unverifiable','HTTP 503',{'company_ready':True})
        self.p.observed(self.c,task,[url],1)
        self.p.tick(self.c)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT decision FROM discovery_queries WHERE fingerprint=?',(root,)).fetchone()[0],'technical')
            self.assertEqual(c.execute('SELECT dry_streak FROM discovery_branches').fetchone()[0],0)
