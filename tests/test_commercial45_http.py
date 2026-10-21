"""Phase 4.5 HTTP checks with temporary SQLite and local requests only."""
import test_commercial44_http as base
from test_commercial44 import NOW
class ActivityHttp45(base.RecommendationHttp44):
 def test_45_default_recent_unknown_goes_to_verify(self):
  code,r=self.request('/api/commercial/recommendations');self.assertEqual(code,200);self.assertEqual(r['total'],0)
  self.assertEqual(self.request('/api/commercial/recommendations?category=verify')[1]['total'],1)
 def test_46_observation_auth_and_validation(self):
  path='/api/commercial/opportunities/1/job-observation';b={'revision_id':1,'kind':'closed','observed_at':'2026-10-17T12:00:00Z'}
  for headers in ({'X-CSRF-Token':'bad'},{'Origin':'https://evil.test'},{'Host':'evil.test'}):self.assertEqual(self.request(path,b,headers)[0],403)
  self.assertEqual(self.request(path,{**b,'revision_id':999})[0],400)
 def test_47_observation_persisted_without_crm(self):
  path='/api/commercial/opportunities/1/job-observation';b={'revision_id':1,'kind':'closed','observed_at':'2026-10-17T12:00:00Z','note':'No longer accepting applications'}
  code,r=self.request(path,b);self.assertEqual(code,200);self.assertFalse(r['commercial_state_changed'])
  r=self.request('/api/commercial/recommendations?category=archived')[1]
  self.assertEqual(r['items'][0]['activity']['application_status'],'CLOSED_CONFIRMED')
  with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM prospects').fetchone()[0],0)
