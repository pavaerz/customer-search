"""Local Chromium experiment: pending document reused without false completeness."""
import subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from sales.commercial.browser import review
from sales.db import Store,now
class Browser43(unittest.TestCase):
 def test_pending_resource_not_aborted_on_desktop_transition(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=Store(Path(tmp)/'test.db');store.init()
   page={'url':'https://fixture.example/','status':200,'checked_at':now(),'html':'<!doctype html><meta name="viewport" content="width=device-width"><main><p>Contenuto aziendale completo e visibile prima della dipendenza asincrona.</p></main><script async src="/phase43slow.js"></script>'}
   def launch(source,output,errors):return subprocess.Popen([sys.executable,'-m','browser43_harness'],stdin=source,stdout=output,stderr=errors,start_new_session=True,close_fds=True)
   with patch('sales.commercial.browser._launch_worker',launch):
    result=review(store,[page],capture=False,limits={'browser_audit_level':'STANDARD','browser_total_seconds':7,'browser_timeout_ms':1000,'browser_render_timeout_ms':400,'browser_resource_timeout_ms':2000})
   self.assertFalse(result['completed']);self.assertEqual(result['findings'],[])
   self.assertTrue(any(d.get('wait_until')=='reuse_pending_document' for d in result['diagnostics']),result)
   self.assertEqual(result['resource_requests'],1)
   self.assertTrue(result['worker_reaped']);self.assertTrue(result['resources_closed'])
   self.assertTrue(any(d.get('queue_wait_ms') is not None for d in result['diagnostics']))
