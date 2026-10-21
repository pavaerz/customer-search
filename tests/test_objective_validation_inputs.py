"""Real-source evaluation preparation cannot infer or leak review labels."""
import unittest
from unittest.mock import patch

from scripts.prepare_objective_validation import fixtures,capture
from sales.agent6.grounding import segments
from sales.commercial.ai_tasks import request_schema


class EvaluationInputs(unittest.TestCase):
    def test_original_corpus_and_blocked_social_are_explicitly_separate(self):
        cases,blocked=fixtures()
        self.assertEqual(len(cases),13)
        self.assertEqual(sum(c['review']['expected']=='INTERESTING' for c in cases),2)
        self.assertEqual(len(blocked),1)
        self.assertFalse(blocked[0]['original_read'])
        self.assertFalse(blocked[0]['ai_input_prepared'])
        self.assertFalse(any('linkedin.com' in c['page']['url'] for c in cases))

    def test_actual_budgeted_payloads_preserve_invitation_without_review_labels(self):
        cases,_=fixtures()
        for key in ('historical-A','historical-B'):
            with self.subTest(key=key),patch('sales.commercial.ai_provider._request',side_effect=AssertionError('No paid calls')):
                item=capture(next(c for c in cases if c['id']==key))
            payload=item['payload']
            self.assertLessEqual(item['token_estimate']['tokens'],8192)
            self.assertTrue(payload['identity']['verified'])
            self.assertTrue(payload['geography_allowed'])
            self.assertIn('cerchiamo collaboratori','\n'.join(e['text'] for e in payload['evidence']).lower())
            for forbidden in ('review','expected','allowed','positive_means','record_id','campaign_id'):
                self.assertNotIn(forbidden,payload)
                self.assertNotIn(forbidden,item['wire_payload'])
            schema=request_schema(payload)
            ids=schema['properties']['facts']['items']['properties']['segment_id']['enum']
            self.assertEqual(set(ids),{s['segment_id'] for e in payload['evidence'] for s in segments(e)})

    def test_expired_request_keeps_own_subject_and_publication_date(self):
        cases,_=fixtures()
        item=capture(next(c for c in cases if c['id']=='historical-F'))
        payload=item['payload']
        text='\n'.join(e['text'] for e in payload['evidence'])
        self.assertIn('Elice Group',text)
        self.assertNotIn('QUANTA',text)
        self.assertIn('2015-11-03',[d['value'] for d in payload['dates']])
        self.assertFalse(payload['identity']['verified'])

    def test_supplier_page_is_not_relabelled_as_positive_in_input(self):
        cases,_=fixtures()
        case=next(c for c in cases if c['id']=='campaign44-1166')
        item=capture(case)
        self.assertEqual(case['review']['expected'],'NOT_INTERESTING')
        self.assertNotIn('decision',item['payload'])
        self.assertNotIn('commercial_review',item['payload'])
        self.assertEqual(item['payload']['identity']['name'],'Polygon Studio')
