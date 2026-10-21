"""Original campaign27 finding: publisher/member data must never merge."""
import copy,gzip,json,unittest
from pathlib import Path
from sales.commercial.discovery import assess
from sales.commercial.entity_scope import profile
from sales.commercial.identity import establish
from sales.commercial.opportunity_view import build,source_contacts
from sales.commercial.target_fit import evaluate
class Federation42(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  with gzip.open(Path(__file__).parent/'fixtures/commercial42/campaign27-federation.json.gz','rt') as f:cls.x=json.load(f)
 def test_member_profile_excluded_before_http(self):
  r=assess({'url':'https://www.federazionegommaplastica.it/aziende-associate/nespak-spa/','title':'Nespak Spa','content':'Produzione packaging'},'WEBSITE_REBUILD');self.assertEqual(r['decision'],'exclude')
 def test_member_original_not_publisher_identity(self):
  p=next(p for u,p in self.x['pages'].items() if '/aziende-associate/' in u);self.assertTrue(profile(p)['multi_subject']);i=establish([p]);self.assertEqual(i['identity_status'],'unknown');self.assertIsNone(i['legal_id']);self.assertEqual(i['contacts'],[])
 def test_projection_hides_false_positive_preserves_original(self):
  b=copy.deepcopy(self.x['revisions'][0]['body']);original=copy.deepcopy(b);v=build(b,self.x['documents']);self.assertEqual(v['status'],'NOT_ACTIONABLE');self.assertEqual(v['contacts'],[]);self.assertIsNone(v['official_domain']);self.assertEqual(b,original);self.assertTrue(v['data_issues'])
 def test_original_fit_not_suitable(self):
  b=self.x['revisions'][0]['body'];p=list(self.x['pages'].values());f=evaluate(b['identity'],p,b['geography']);self.assertFalse(f['audit_allowed'])
 def test_member_contacts_never_inherit_owner(self):
  b=self.x['revisions'][0]['body'];contacts=source_contacts(b,b['identity']);self.assertFalse(any('nespak' in str(c) for c in contacts))
 def test_manufacturer_named_institution_client_not_excluded(self):
  r=assess({'url':'https://manufacturer.test','title':'Alfa packaging','content':'Produzione; clienti della Federazione Gomma Plastica'},'WEBSITE_REBUILD');self.assertEqual(r['decision'],'admit')
 def test_explicit_spa_preference_not_wellness_spa(self):
  from sales.commercial.target_fit import excluded_legal_form
  self.assertTrue(excluded_legal_form('Copyright 2026 Centrufficio S.p.A.'));self.assertFalse(excluded_legal_form('Hotel Alba Spa'));self.assertFalse(excluded_legal_form('Spazio Srl'))
 def test_spa_advisory_excluded_without_mutating_state(self):
  b=copy.deepcopy(self.x['revisions'][0]['body']);b['identity']['name']='Centrufficio S.p.A.';b['identity']['name_fields']['page_title']='Centrufficio arredi';b['url']='https://centrufficio.example/';old=copy.deepcopy(b);v=build(b);self.assertEqual(v['status'],'NOT_ACTIONABLE');self.assertIn('S.p.A.',v['reason']);self.assertEqual(b,old)
 def test_copyright_not_company_name(self):
  from test_commercial_engines import page
  p=page('Contatti',url='https://alfa.example/contatti',extra='<footer>© Copyright 2026 © Alfa Srl - P.IVA 12345678901</footer>')
  self.assertEqual(establish([p])['name'],'Alfa Srl')
