import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from technical_audit import selection_evidence, technical_report, valid_report, local_lighthouse

class TechnicalSelectionTest(unittest.TestCase):
    def test_selection_boundaries_and_failed_tests_are_not_zero(self):
        for score, expected in ((89,True),(90,False),(0,True),(None,False),(True,False),(-1,False),(100,False)):
            r={'url':'https://example.org','pagespeed':[{'status':'ok','strategy':'mobile','scores':{'seo':score}}]}
            self.assertEqual(bool(selection_evidence(r)),expected,score)
        self.assertFalse(selection_evidence({'pagespeed':[{'status':'unavailable','scores':{'seo':0}}]}))
    def test_each_category_can_select_a_prospect(self):
        for category in ('seo','performance','accessibility','best-practices'):
            self.assertTrue(selection_evidence({'pagespeed':[{'status':'ok','strategy':'desktop','scores':{category:88}}]}))
    def test_foreign_redirect_and_http_error_do_not_become_good_scores(self):
        r={'finalUrl':'https://example.org','categories':{'seo':{'score':1}},'audits':{}}
        self.assertTrue(valid_report(r,'https://www.example.org'))
        self.assertFalse(valid_report(r,'https://other.org'))
        self.assertFalse(valid_report({**r,'runtimeError':{'code':'FAILED'}},'https://example.org'))
        self.assertFalse(valid_report({**r,'audits':{'http-status-code':{'score':0}}},'https://example.org'))
    def test_report_runs_mobile_and_desktop_without_layout(self):
        with patch('technical_audit.local_lighthouse',side_effect=lambda url,strategy,*args:{'strategy':strategy,'status':'ok','scores':{'seo':65}}) as run:
            r=technical_report('https://example.org','<title>Example</title>',Path('/tmp'),lambda:None)
        self.assertEqual(run.call_count,2)
        self.assertEqual(len(r['selection_findings']),2)
        self.assertNotIn('layout',r)
    def test_cancellation_is_not_swallowed(self):
        def stop(): raise InterruptedError('stop')
        with self.assertRaises(InterruptedError):local_lighthouse('https://example.org','mobile',Path('/tmp'),stop)
    def test_no_runtime_returns_unavailable_not_fake_scores(self):
        with tempfile.TemporaryDirectory() as temp,patch('technical_audit.runtime_paths',return_value=('','','')):
            r=local_lighthouse('https://example.org','mobile',Path(temp),lambda:None)
        self.assertEqual(r['status'],'unavailable');self.assertNotIn('scores',r)
