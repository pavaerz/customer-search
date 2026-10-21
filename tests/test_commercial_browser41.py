"""Local Chromium: per-feature resource failure, not external site success claims."""
import subprocess,sys
from unittest.mock import patch
import test_commercial_browser36 as previous
from sales.commercial.browser import review
from sales.db import now
class Browser41(previous.Browser36):
    def render(self,extra='',level='STANDARD',body=previous.baseline.TEXT):
        p={'url':self.origin+'/','status':200,'checked_at':now(),'html':'<!doctype html><title>Local company</title><meta name="viewport" content="width=device-width">'+body+extra}
        def launch(source,output,errors):return subprocess.Popen([sys.executable,'-m','browser41_harness'],stdin=source,stdout=output,stderr=errors,start_new_session=True,close_fds=True)
        with patch('sales.commercial.browser._launch_worker',launch):
            r=review(self.store,[p],capture=level!='BASIC',limits={'browser_audit_level':level,'browser_total_seconds':8,'browser_timeout_ms':1000,'browser_render_timeout_ms':1000,'browser_resource_timeout_ms':200,'browser_max_resources':60})
        self.assert_closed(r);return r
    def test_form_robots_does_not_invalidate_visible_homepage(self):
        r=self.render('<script src="https://www.google.com/recaptcha/api.js"></script>')
        self.assertTrue(r['completed'],r);self.assertEqual(r['unverified_features'][0]['feature'],'form');self.assertTrue(all(p['measurements']['visible_content'] for p in r['pages']));self.assertEqual(r['missing_resources'][0]['role'],'FORM');self.assertNotIn('/recaptcha/api.js',self.server.seen)
    def test_form_failure_with_hidden_content_remains_partial(self):
        r=self.render('<style>body{opacity:0}</style><script src="https://www.google.com/recaptcha/api.js"></script>')
        self.assertFalse(r['completed']);self.assertEqual(r['findings'],[]);self.assertEqual(r['independent_measurements'],[])
    def test_visible_homepage_but_failed_script_not_complete(self):
        r=self.render('<script src="https://cdn.example.test/unknown.js"></script>');self.assertFalse(r['completed']);self.assertEqual(r['findings'],[])
