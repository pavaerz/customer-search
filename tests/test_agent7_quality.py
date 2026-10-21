"""Human quality review is not a synonym for liking, contacting or winning."""
import unittest
import test_agent6_campaign32 as support
from test_agent6 import evaluated
from sales.agent6 import memory,quality,worklist,api


class Quality(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp()
        self.store,self.c=self.base.store,self.base.c
        self.body={**evaluated(),'query':'agenzia cerchiamo freelance WordPress','strategy':'synthetic'}
        self.rid=memory.save_record(self.store,self.c,'AGENCIES',self.body)
    def tearDown(self):self.base.tearDown()

    def test_preferences_and_outcomes_do_not_invent_precision(self):
        for kind in ('interesting','contacted','won','not_interesting'):memory.feedback(self.store,self.rid,kind)
        s=quality.summary(self.store)
        self.assertEqual(s['reviewed_requests'],0);self.assertIsNone(s['observed_precision'])

    def test_audit_requires_a_reason_and_a_previously_qualified_original(self):
        with self.assertRaisesRegex(ValueError,'prove'):memory.feedback(self.store,self.rid,'false_positive')
        rid=memory.save_record(self.store,self.c,'AGENCIES',{**self.body,'url':'https://alfa.example/unverified','state':'NEEDS_REVIEW'})
        with self.assertRaisesRegex(ValueError,'qualificate'):memory.feedback(self.store,rid,'quality_confirmed','Source reviewed')

    def test_latest_quality_counts_once_and_crm_does_not_erase_it(self):
        memory.feedback(self.store,self.rid,'false_positive','The source refers to a completed project.')
        memory.feedback(self.store,self.rid,'quality_confirmed','Reviewed current open invitation on the official source.')
        memory.feedback(self.store,self.rid,'contacted')
        s=quality.summary(self.store)
        self.assertEqual((s['reviewed_requests'],s['confirmed'],s['false_positives']),(1,1,0))
        self.assertEqual(s['observed_precision'],1);self.assertFalse(s['sample_sufficient'])
        groups=memory.history(self.store,'AGENCIES')['strategy_groups']
        self.assertEqual(groups[0]['quality_reviews'],1)
        self.assertEqual(groups[0]['outcomes'],{'contacted':1})
        self.assertEqual(groups[0]['precision'],1)

    def test_false_positive_leaves_ready_view_without_rewriting_qualification(self):
        memory.feedback(self.store,self.rid,'false_positive','Request closed in the cited source.')
        self.assertEqual(worklist.listing(self.store,{'view':'ready'})['total'],0)
        review=worklist.listing(self.store,{'view':'review'})['items'][0]
        self.assertEqual(review['state'],'NEEDS_REVIEW');self.assertEqual(review['saved_state'],'VERIFIED')
        self.assertIn('Request closed',review['worklist']['warning'])
        with self.assertRaisesRegex(ValueError,'contestata'):api.save_contact(self.store,self.rid)
        self.assertEqual(api.dossier(self.store,self.rid)['state'],'VERIFIED')

    def test_false_positive_does_not_blacklist_other_company_requests(self):
        second=memory.save_record(self.store,self.c,'AGENCIES',{**self.body,'url':'https://alfa.example/other-project'})
        memory.feedback(self.store,self.rid,'false_positive','This particular request is not open.')
        self.assertEqual([r['id'] for r in worklist.listing(self.store,{'view':'ready'})['items']],[second])
        self.assertEqual(quality.summary(self.store)['false_positives'],1)

    def test_confirmed_reinspection_restores_eligibility_without_sending(self):
        memory.feedback(self.store,self.rid,'false_positive','Wrong source attribution suspected.')
        memory.feedback(self.store,self.rid,'quality_confirmed','Buyer and open request confirmed against the original.')
        self.assertEqual(worklist.listing(self.store,{'view':'ready'})['total'],1)
        with self.store.connect() as c:self.assertEqual(c.execute('select count(*) from prospects').fetchone()[0],0)
