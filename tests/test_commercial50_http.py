"""Local HTTP preview never creates a campaign or changes budgets."""
import test_commercial44_http as base
from unittest.mock import patch
class PlannerHttp50(base.RecommendationHttp44):
 def test_plan_authorization_headers(self):
  path='/api/commercial/search-plan';body={'filters':{'mode':'deep','regions':['Veneto']}}
  for h in ({'X-CSRF-Token':'bad'},{'Origin':'https://evil.test'},{'Host':'evil.test'}):self.assertEqual(self.request(path,body,h)[0],403)
 def test_plan_no_campaign_or_provider(self):
  with self.store.connect() as c:before=c.execute('select count(*) from campaigns').fetchone()[0];config=c.execute('select * from config order by key').fetchall()
  with patch('sales.commercial.coordinator.acquire',side_effect=AssertionError('No network')):
   code,r=self.request('/api/commercial/search-plan',{'filters':{'mode':'deep','regions':['Veneto']}})
  self.assertEqual(code,200);self.assertTrue(r['authorization_required']);self.assertEqual(r['maximums']['max_serper_credits'],144)
  with self.store.connect() as c:self.assertEqual(c.execute('select count(*) from campaigns').fetchone()[0],before);self.assertEqual(c.execute('select * from config order by key').fetchall(),config)
 def test_invalid_plan(self):
  self.assertEqual(self.request('/api/commercial/search-plan',{'filters':{'regions':['Moon']}})[0],400)
  self.assertEqual(self.request('/api/commercial/search-plan',{'filters':{'mode':'random'}})[0],400)
