"""Real Chromium, local transport and explicit policy/transport fault injection."""
import subprocess,sys
from unittest.mock import patch
from sales.db import now
from sales.commercial.browser import review
import test_commercial_browser35 as previous
import test_commercial_browser32 as baseline

class Browser36(previous.Browser35):
    def render(self,extra='',level='STANDARD',body=baseline.TEXT):
        p={'url':self.origin+'/','status':200,'checked_at':now(),'html':'<!doctype html><title>Local company</title><meta name="viewport" content="width=device-width">'+body+extra}
        def launch(source,output,errors):return subprocess.Popen([sys.executable,'-m','browser36_harness'],stdin=source,stdout=output,stderr=errors,start_new_session=True,close_fds=True)
        with patch('sales.commercial.browser._launch_worker',launch):
            r=review(self.store,[p],capture=level!='BASIC',limits={'browser_audit_level':level,'browser_total_seconds':8,'browser_timeout_ms':1000,'browser_render_timeout_ms':1000,'browser_resource_timeout_ms':200,'browser_max_resources':60})
        self.assert_closed(r);return r
    def test_politeness_wait_is_not_transfer_timeout(self):
        r=self.render('<link rel="stylesheet" href="/policy1.css"><link rel="stylesheet" href="/policy2.css">')
        self.assertTrue(r['completed'],r)
        self.assertEqual(len(self.server.seen),2)
        waits=[d['wait_ms'] for d in r['diagnostics'] if d['phase']=='resource_policy']
        self.assertEqual(len(waits),2);self.assertTrue(all(w>=280 for w in waits))
        self.assertTrue(all(p['complete'] for p in r['pages']))
    def test_parser_blocking_script_preserves_partial_only(self):
        r=self.render('<script src="/slow.js"></script>'+baseline.TEXT,body='<head>')
        self.assertFalse(r['completed']);self.assertEqual(r['findings'],[])
        self.assertEqual(self.server.seen.count('/slow.js'),1)
        self.assertTrue(any(d.get('status')=='not_retried' or d.get('wait_until')=='reuse_pending_document' for d in r['diagnostics']))
    def test_failed_dependency_with_js_error_cannot_be_complete(self):
        r=self.render('<script src="/slow.js"></script><script>missingDependency.start()</script>')
        self.assertFalse(r['completed']);self.assertEqual(r['findings'],[])
        self.assertTrue(any('missingDependency' in str(d.get('error')) for d in r['diagnostics']))
