"""Partial browser observations and bounded recovery, never live defects."""
import unittest,copy,json
from sales.commercial.audit_policy import finish,retain_independent_findings
from sales.agent6 import website_audit,audit_recovery,budget,learning
import test_agent8_proactive as fixture
import test_agent9_signals as signals_fixture


class Audit(unittest.TestCase):
    def test_access_restriction_is_not_a_website_defect(self):
        page={**fixture.pages()[fixture.ROOT],'status':403}
        report=website_audit.audit([page])
        self.assertFalse(any(o['status']=='ISSUE' for o in report['observations']))
        self.assertEqual(report['observations'][0]['measurement_status'],'NOT_MEASURED')

    def test_partial_keeps_only_proven_completed_viewport_defects(self):
        pages=list(fixture.pages().values());report=fixture.browser(pages)
        report.update(completed=False,failure_codes=['rendering_timeout'],limits=['Synthetic timeout'])
        report['pages'][-1]['complete']=False
        report['findings'].append({'code':'mobile_content','severity':'major','url':pages[-1]['url'],'viewport':390,'quote':'Unvalidated fake defect'})
        finish(report)
        self.assertEqual(report['findings'],[])
        self.assertEqual(len(report['independent_findings']),1)
        measured=website_audit.audit(pages,report)
        findings=[o for o in measured['observations'] if o['evidence']['method']=='browser_two_measurements']
        self.assertEqual(len(findings),1)
        self.assertEqual(measured['browser_status'],'PARTIAL')
        self.assertEqual(next(o for o in measured['observations'] if o['code']=='performance')['status'],'UNKNOWN')

    def test_targeted_retry_uses_only_missing_viewport_with_remaining_time(self):
        p=list(fixture.pages().values())[:1];root=p[0]['url']
        old={'completed':False,'elapsed_ms':2000,'failure_codes':['rendering_timeout'],'pages':[
            {'url':root,'viewport':390,'complete':True,'scope':'rendered'},
            {'url':root,'viewport':1366,'complete':False,'scope':'partial_dom'}],
            'screenshots':[{'url':root,'viewport':390,'reliability':'CONFIRMED'}]}
        limits={'browser_total_seconds':10,'max_browser_pages':1,'browser_audit_level':'DEEP'}
        self.assertEqual(audit_recovery.targets(old,p,limits),{root:[1366]})
        for code in ('robots','tls_error','access_error'):
            self.assertEqual(audit_recovery.targets({**old,'failure_codes':[code]},p,limits),{})
        self.assertEqual(audit_recovery.targets({**old,'elapsed_ms':9500},p,limits),{})
        retry={'completed':False,'resources_closed':True,'limits':[],'elapsed_ms':3000,
            'pages':[{'url':root,'viewport':1366,'complete':True,'scope':'rendered'}],
            'screenshots':[{'url':root,'viewport':1366,'reliability':'CONFIRMED'}]}
        merged=audit_recovery.merge(old,retry,p,limits)
        self.assertTrue(merged['completed']);self.assertEqual(merged['elapsed_ms'],5000)
        self.assertEqual(audit_recovery.targets(merged,p,limits),{})
        self.assertEqual(len(merged['pages']),2)

    def test_purposes_share_existing_hard_budget_pools(self):
        read={'task':'ORIGINAL_PAGE_READ_6','evidence':[{'original':True}]}
        self.assertEqual(budget.purpose(read),'original_verification')
        self.assertEqual(budget.purpose({**read,'repair':{'code':'missing_identity'}}),'targeted_recovery')
        self.assertEqual(budget.stage_for('page:x',{**read,'repair':{'code':'missing_identity'}}),'verify')
        self.assertEqual(budget.purpose({'task':'WEBSITE_OPPORTUNITY_REVIEW_8'}),'website_audit_interpretation')

    def test_historical_ai_false_negative_does_not_penalize_strategy(self):
        doc=signals_fixture.KOND['source']
        record={'state':'REJECTED','kind':'SUPPLIER_OFFER','original':True,'documents':[doc],'request_key':'k'}
        before=json.dumps(record,sort_keys=True)
        self.assertTrue(learning.contradicted_negative(record))
        events=[{'id':1,'campaign_id':38,'flow':'AGENCIES','kind':'decision',
            'body':{'query':'agenzia cerchiamo freelance WordPress','strategy':'invites','record_id':1,
                'state':'REJECTED','original':True,'negative_feedback_reliable':True}}]
        group=learning.summarize(events,[],{1:record})[0]
        self.assertEqual(group['verified_rejections'],0);self.assertEqual(group['uncertain_decisions'],1)
        self.assertEqual(json.dumps(record,sort_keys=True),before)
