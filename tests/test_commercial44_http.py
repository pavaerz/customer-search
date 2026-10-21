"""Local HTTP contract, temp SQLite; no provider or production access."""
import tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import test_sales_http as base
from test_commercial44 import job,populate
from sales import server
from sales.db import Store
from sales.engines import EngineManager
class RecommendationHttp44(unittest.TestCase):
 request=base.HttpTest.request
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.store=Store(Path(cls.temp.name)/'http.db');cls.store.init();cls.cid=populate(cls.store,[job()])
  cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.port=cls.http.server_port;cls.origin='http://127.0.0.1:'+str(cls.port)
  cls.patches=[patch.object(server,'STORE',cls.store),patch.object(server,'MANAGER',EngineManager(cls.store)),patch.object(server,'PORT',cls.port),patch.object(server,'ORIGIN',cls.origin)]
  for p in cls.patches:p.start()
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.http.shutdown();cls.http.server_close();cls.thread.join()
  for p in cls.patches:p.stop()
  cls.temp.cleanup()
 def test_read_separate_from_commercial_list(self):
  code,r=self.request('/api/commercial/recommendations?category=all');self.assertEqual(code,200);self.assertEqual(r['items'][0]['official_state'],'UNVERIFIABLE');self.assertEqual(r['items'][0]['evidence_confidence'],'LOW')
 def test_csrf_origin_and_host_preserved(self):
  path='/api/commercial/opportunities/1/job-review';b={'revision_id':1,'status':'interesting'}
  for h in ({'X-CSRF-Token':'bad'},{'Origin':'https://evil.test'},{'Host':'evil.test'}):self.assertEqual(self.request(path,b,h)[0],403)
 def test_explicit_review_no_promotion(self):
  code,r=self.request('/api/commercial/opportunities/1/job-review',{'revision_id':1,'status':'interesting'});self.assertEqual(code,200);self.assertFalse(r['commercial_state_changed'])
  with self.store.connect() as c:self.assertEqual(c.execute('select state from commercial_revisions where id=1').fetchone()[0],'UNVERIFIABLE');self.assertEqual(c.execute('select count(*) from prospects').fetchone()[0],0)
 def test_bad_revision_and_invalid_action(self):
  for b in ({'revision_id':999,'status':'interesting'},{'revision_id':1,'status':'apply'}):self.assertEqual(self.request('/api/commercial/opportunities/1/job-review',b)[0],400)
if __name__=='__main__':unittest.main()
