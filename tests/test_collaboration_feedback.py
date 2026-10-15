import tempfile
import unittest
from pathlib import Path

from sales.db import Store
from sales.research_api import commercial_feedback
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel


class CollaborationFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db');self.store.init()
        self.rs=ResearchStore(self.store);self.c=self.rs.create();self.f=Funnel(self.rs)

    def candidate(self,host,strategy='partner',path='jobs',verified=True):
        url='https://'+host+'/'+path
        self.f.transition(self.c,{'url':url,'strategy':strategy},'promising','Fixture',
            {'company_ready':True,'identity':{'name':host,'website':'https://'+host+'/',
             'identity_status':'verified' if verified else 'unknown','group':'agencies'}})
        with self.store.connect() as c:return c.execute('SELECT id FROM discovery_candidates WHERE url=?',(url,)).fetchone()[0]

    def outcome(self,cid,kind):self.f.outcome(kind,candidate_id=cid)

    def test_promising_outcomes_can_prioritize_after_two_sufficient_cohorts(self):
        for strategy in ('partner','companies'):
            for n in range(10):
                cid=self.candidate(f'{strategy}{n}.example',strategy)
                self.outcome(cid,'contacted')
                if strategy=='partner':self.outcome(cid,'positive_reply')
        feedback=commercial_feedback(self.store)
        self.assertEqual(feedback['preferred'],'partner')
        partner=next(g for g in feedback['strategies'] if g['strategy']=='partner')
        self.assertEqual((partner['contacted'],partner['replied'],partner['reply_rate']),(10,10,100))
        self.assertEqual(self.rs.campaign(self.c['id'])['qualified'],0)

    def test_duplicate_pages_and_repeated_events_are_one_company(self):
        first=self.candidate('agency.example');second=self.candidate('agency.example',path='contact')
        for cid in (first,second):
            self.outcome(cid,'contacted');self.outcome(cid,'contacted');self.outcome(cid,'positive_reply')
        feedback=commercial_feedback(self.store)
        partner=next(g for g in feedback['strategies'] if g['strategy']=='partner')
        self.assertEqual((partner['contacted'],partner['replied']),(1,1))
        self.assertIsNone(partner['reply_rate']);self.assertIsNone(feedback['preferred'])

    def test_interest_or_unknown_identity_does_not_infer_a_contact(self):
        cid=self.candidate('interest.example');self.outcome(cid,'interesting');self.outcome(cid,'positive_reply')
        unknown=self.candidate('unknown.example',verified=False);self.outcome(unknown,'contacted')
        feedback=commercial_feedback(self.store)
        self.assertEqual(sum(g['contacted'] for g in feedback['strategies']),0)
        self.assertIsNone(feedback['preferred'])

    def test_same_company_in_qualified_crm_and_discovery_is_not_counted_twice(self):
        from test_research import sample
        from sales.research_rules import qualify
        args=sample();args[0]['website']='https://agency.example/'
        self.rs.save(self.c['id'],self.c['generation'],None,args[0],args[1],qualify(*args,strategy='explicit'))
        cid=self.candidate('agency.example')
        self.outcome(cid,'contacted');self.outcome(cid,'positive_reply')
        feedback=commercial_feedback(self.store)
        self.assertEqual(sum(g['contacted'] for g in feedback['strategies']),1)
        self.assertEqual(sum(g['replied'] for g in feedback['strategies']),1)
        self.assertEqual(next(g for g in feedback['strategies'] if g['strategy']=='explicit')['contacted'],1)


if __name__=='__main__':unittest.main()
