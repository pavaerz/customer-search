import ssl,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store,now
from sales.providers import PublicWeb,PageConnectionError
from sales.discovery_control import free_search,health

class NetworkRecoveryTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.s=Store(Path(t.name)/'test.db');self.s.init();self.web=PublicWeb(self.s)
 def test_one_broken_engine_does_not_disable_working_empty_engine(self):
  result={'results':[],'unresponsive_engines':[['bing','HTTP connection error']]}
  self.assertEqual(free_search(self.s,lambda:result,['bing','yahoo']),result);self.assertEqual(health(self.s)['failures'],0)
 def test_all_broken_engines_still_open_circuit(self):
  result={'results':[],'unresponsive_engines':[['bing','HTTP connection error'],['yahoo','CAPTCHA']]}
  with self.assertRaises(ValueError):free_search(self.s,lambda:result,['bing','yahoo'])
  self.assertEqual(health(self.s)['failures'],1)
 def test_eof_retry_keeps_verification_and_can_recover(self):
  page={'status':200,'html':'ok','url':'https://example.org/','checked_at':now()}
  with patch.object(self.web,'_raw',side_effect=[ssl.SSLEOFError('EOF'),page]) as fetch,patch('sales.providers.time.sleep'):
   self.assertEqual(self.web.get('https://example.org/'),page);self.assertEqual(fetch.call_count,2)
 def test_eof_failure_suspends_only_that_origin(self):
  with patch.object(self.web,'_raw',side_effect=ssl.SSLEOFError('EOF')) as fetch,patch('sales.providers.time.sleep'):
   with self.assertRaises(PageConnectionError):self.web.get('https://example.org/a')
   with self.assertRaises(PageConnectionError):self.web.get('https://example.org/b')
   self.assertEqual(fetch.call_count,2)
  with patch.object(self.web,'_raw',return_value={'status':200,'url':'https://other.example/','html':'ok','checked_at':now()}) as fetch:self.web.get('https://other.example/');self.assertEqual(fetch.call_count,1)
 def test_bad_certificates_are_never_retried_or_ignored(self):
  with patch.object(self.web,'_raw',side_effect=ssl.SSLCertVerificationError('bad cert')) as fetch:
   with self.assertRaises(ssl.SSLCertVerificationError):self.web.get('https://example.org/')
   self.assertEqual(fetch.call_count,1)
 def test_stop_during_retry(self):
  self.web.stop=lambda:(_ for _ in ()).throw(InterruptedError())
  with patch.object(self.web,'_raw',side_effect=ssl.SSLEOFError('EOF')) as fetch:
   with self.assertRaises(InterruptedError):self.web.get('https://example.org/')
   self.assertEqual(fetch.call_count,1)
