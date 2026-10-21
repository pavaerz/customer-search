import unittest
from unittest.mock import patch
import test_agent6_campaign32 as support
from sales.agent6.source_access import inspect,require_content
from sales.agent6.api import counts
from sales.access_status import AccessIssue


class Access(unittest.TestCase):
    def page(self,text,url='https://example.test/job'):
        return {'url':url,'html':text,'status':200,'checked_at':'2026-10-19T12:00:00+00:00'}

    def test_challenge_is_not_a_site_analysis_even_with_http_200(self):
        page=self.page('<title>Verifica richiesta</title><p>Abbiamo rilevato traffico insolito. Verifica di non essere un robot.</p>')
        self.assertFalse(inspect(page)['content_read'])
        with self.assertRaises(AccessIssue):require_content(page)

    def test_contact_form_captcha_is_not_an_access_block(self):
        page=self.page('<title>Alfa contatti</title><p>Produciamo componenti meccanici. Richiedi informazioni.</p><form><input type="email"><div class="g-recaptcha">Non sono un robot</div></form>')
        self.assertTrue(inspect(page)['content_read'])

    def test_password_login_is_not_original_post(self):
        page=self.page('<title>Accedi</title><form><input type="password"></form>','https://instagram.com/accounts/login/')
        self.assertEqual(inspect(page)['status'],'LOGIN_REQUIRED')

    def test_worker_does_not_spend_ai_or_count_challenge_as_original(self):
        b=support.Campaign32Fix();b.setUp();self.addCleanup(b.tearDown)
        task={'id':1000,'strategy':'AGENCIES','kind':'candidate','payload':{'url':'https://example.test/job'}}
        page=self.page('<title>Verifica richiesta</title><p>Traffico insolito. Verifica di non essere un robot.</p>')
        with patch('socket.create_connection',side_effect=AssertionError('Offline only')),patch('sales.agent6.coordinator.CompanyWeb.get',return_value=page),patch.object(b.w,'model',side_effect=AssertionError('No AI for access challenge')):
            try:b.w.execute(task,lambda:None)
            except AccessIssue as error:b.w.record_failure(task,error)
            else:self.fail('Access challenge should be blocked')
        data=counts(b.store,b.c['id'])
        self.assertEqual(data['examined'],0)
        self.assertEqual(data['unverifiable'],1)
        self.assertEqual(data['ai']['calls'],0)


if __name__=='__main__':unittest.main()
