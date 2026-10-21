"""Synthetic edge cases explicitly separate from the real campaign 28 fixture."""
import copy,gzip,json,sqlite3,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from sales.db import Store,encode
from sales.research_store import ResearchStore
from sales.commercial.recommendations import assess,rank
from sales.commercial.recommendation_store import listing,review
from sales.commercial.storage import migrate
from sales.commercial.opportunity_view import build
NOW=datetime(2026,10,18,tzinfo=timezone.utc)
def load():
 with gzip.open(Path(__file__).parent/'fixtures/commercial44/campaign28.json.gz','rt') as f:return json.load(f)
def job(title='WordPress Developer at Alfa',snippet='Cerchiamo sviluppatore WordPress freelance.',url='https://linkedin.com/jobs/view/wordpress-at-alfa-123',ident=1,**body):
 b={'engine':'FREELANCE','state':'UNVERIFIABLE','classification':'social_incomplete','url':url,'title':title,'company':'linkedin.com','discovery':{'title':title,'snippet':snippet,'url':url},'identity':{'identity_status':'unknown'},'verification':{'status':'incomplete'},**body}
 return {'id':ident,'engine':b['engine'],'state':b['state'],'selected_revision':ident,'manual_state':'','body':b}
def populate(store,items):
 rs=ResearchStore(store);camp=rs.create({'commercial_engines':['FREELANCE','AGENCIES','STARTUPS','WEBSITE_REBUILD']})
 for item in items:
  b=item['body'];identity=b.get('identity') or {};identity={**identity,'name':identity.get('name') or b.get('company') or 'Unknown','website':identity.get('website') or b['url']};entity=rs.entity(identity)
  with store.connect() as c:
   c.execute('INSERT INTO commercial_opportunities(id,entity_id,engine,opportunity_key,latest_revision,manual_state,created_at) VALUES(?,?,?,?,?,?,?)',(item['id'],entity,item['engine'],str(item['id']),item['selected_revision'],item.get('manual_state',''),'2026-10-18T00:00:00+00:00'))
   c.execute('INSERT INTO commercial_revisions VALUES(?,?,?,?,?,?,?,?)',(item['selected_revision'],item['id'],camp['id'],str(item['id']),item['state'],0,encode(b),'2026-10-18T00:00:00+00:00'))
 rs.stop(camp['id']);rs.paused(camp['id']);return camp['id']
class Ranking44(unittest.TestCase):
 def test_indexed_job_is_recommended_not_verified(self):
  j=job();before=copy.deepcopy(j);r=assess(j,NOW)
  self.assertTrue(r['recommended']);self.assertEqual(r['official_state'],'UNVERIFIABLE');self.assertEqual(r['evidence_confidence'],'LOW');self.assertEqual(j,before)
 def test_snippet_contract_not_original(self):
  r=assess(job(),NOW);self.assertEqual(r['relationship']['type'],'EXTERNAL');self.assertFalse(r['relationship']['verified_on_original']);self.assertEqual(r['relationship']['provenance'],'SEARCH_SNIPPET')
 def test_employee_remains_interesting(self):
  r=assess(job('WordPress WooCommerce Developer','Assunzione dipendente a tempo indeterminato.'),NOW)
  self.assertTrue(r['recommended']);self.assertEqual(r['relationship']['type'],'EMPLOYEE')
 def test_fulltime_is_not_employee(self):
  self.assertEqual(assess(job(snippet='WordPress full-time.'),NOW)['relationship']['type'],'UNKNOWN')
 def test_negated_freelance_is_not_positive(self):
  self.assertNotEqual(assess(job(snippet='Non accettiamo freelance. Assunzione dipendente WordPress.'),NOW)['relationship']['type'],'EXTERNAL')
 def test_not_employee_but_freelance(self):
  self.assertEqual(assess(job(snippet='Non cerchiamo un dipendente ma un freelance WordPress.'),NOW)['relationship']['type'],'EXTERNAL')
 def test_sap_not_highly_ranked(self):
  r=assess(job('Full Stack Developer SAP freelance'),NOW);self.assertFalse(r['recommended']);self.assertEqual(r['exclusion'],'different_primary_specialism')
 def test_seller_not_job(self):self.assertFalse(assess(job(classification='seller'),NOW)['recommended'])
 def test_general_search_not_specific(self):self.assertFalse(assess(job(url='https://example.com/search?q=wordpress'),NOW)['recommended'])
 def test_closed_evidence(self):self.assertEqual(assess(job(snippet='WordPress. No longer accepting applications'),NOW)['exclusion'],'explicitly_closed')
 def test_no_index_date_as_publication(self):
  j=job(published_at='2026-10-17',dates={'published_at':'2026-10-17','publication_basis':'search_index'});r=assess(j,NOW);self.assertIsNone(r['published_at']);self.assertIn('Data non verificata.',r['missing'])
 def test_old_date_penalty_not_closed_proof(self):
  j=job(dates={'published_at':'2025-01-01','publication_basis':'JobPosting.datePosted'});r=assess(j,NOW)
  self.assertTrue(r['recommended']);self.assertEqual(next(d['points'] for d in r['score_detail'] if d['dimension']=='recency'),-10)
 def test_remote_without_company_location(self):
  a=assess(job('WordPress Developer remote'),NOW);b=assess(job('WordPress Developer'),NOW);self.assertGreater(a['compatibility_score'],b['compatibility_score'])
 def test_no_remote_from_url(self):
  r=assess(job(url='https://linkedin.com/jobs/view/remote-wordpress-at-alfa-123',snippet='WordPress'),NOW);self.assertIsNone(r['location']['value'])
 def test_no_title_contract_from_slug(self):
  r=assess(job(url='https://linkedin.com/jobs/view/wordpress-freelance-at-alfa-123',snippet='WordPress'),NOW);self.assertEqual(r['relationship']['type'],'UNKNOWN')
 def test_duplicate_linkedin_locale(self):
  a=job();b=job(url='https://it.linkedin.com/jobs/view/another-title-123?trk=x',ident=2);rr=rank([a,b],NOW)
  self.assertEqual(sum(r['recommended'] for r in rr),1);self.assertEqual(sum(r['duplicate_of'] is not None for r in rr),1)
 def test_cross_portal_duplicate(self):
  a=job();b=job(url='https://jobs.example/jobs/42',ident=2);rr=rank([a,b],NOW);self.assertEqual(sum(r['recommended'] for r in rr),1)
 def test_distinct_companies_not_merged(self):
  a=job();b=job('WordPress Developer at Beta',url='https://jobs.example/jobs/42',ident=2);self.assertEqual(sum(r['recommended'] for r in rank([a,b],NOW)),2)
 def test_outbound_never_job(self):self.assertEqual(assess(job(engine='WEBSITE_REBUILD'),NOW)['exclusion'],'outbound_not_job')
 def test_biography_before_request_not_technical_evidence(self):
  r=assess(job('Post di Autore','WordPress HTML CSS JavaScript. Cambia come cerchiamo informazioni.',url='https://linkedin.com/posts/autore-123'),NOW);self.assertFalse(r['recommended'])
 def test_sales_post_with_web_signature(self):
  r=assess(job('Post di Autore','Cerchiamo un freelance. Sviluppatore web in abbonamento.',url='https://linkedin.com/posts/cerchiamo-un-commerciale-da-inserire-activity-123'),NOW);self.assertFalse(r['recommended'])
 def test_generic_full_stack_has_insufficient_skills(self):
  self.assertFalse(assess(job('Full Stack Developer','Cerchiamo sviluppatore full stack.'),NOW)['recommended'])
 def test_unsafe_urls(self):
  for url in ('javascript:alert(1)','https://user:password@example.com/jobs/123','https://example.com/jobs/a\\b'):
   self.assertFalse(assess(job(url=url),NOW)['recommended'])
 def test_pdf(self):self.assertEqual(assess(job(url='https://example.com/jobs.pdf'),NOW)['exclusion'],'excluded_pdf')
 def test_excluded_contact(self):
  j=job();j['do_not_contact']=True;self.assertEqual(assess(j,NOW)['exclusion'],'user_exclusion')
class Historical44(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.x=load();cls.items={i['id']:i for i in cls.x['items']}
 def test_internetimage_no_external_claim(self):
  v=build(self.items[856]['body']);self.assertNotIn('Richiesta tecnica esterna',v['reason']);self.assertIn('contratto',v['reason']);self.assertEqual(v['official_state'],'NEEDS_REVIEW')
 def test_understack_not_third_party(self):
  v=build(self.items[857]['body']);self.assertNotIn('fonte terza',v['reason']);self.assertIsNone(v['official_domain'])
 def test_cosmico_sap_not_recommended(self):self.assertFalse(assess(self.items[797],NOW)['recommended'])
 def test_social_false_positives_blocked(self):
  for ident in (862,904,894,902,872):self.assertFalse(assess(self.items[ident],NOW)['recommended'],ident)
 def test_historical_immutable_reproducible(self):
  before=copy.deepcopy(self.x);a=rank(self.x['items'],self.x['snapshot_at']);self.assertEqual(a,rank(self.x['items'],self.x['snapshot_at']));self.assertEqual(before,self.x)
 def test_partial_browser_no_confirmed_issues(self):
  for ident in (799,801,803,805):
   v=build(self.items[ident]['body']);self.assertEqual(v['site_assessment']['technical_findings'],[]);self.assertNotEqual(v['audit_state'],'COMPLETE')
 def test_budget_profiles_unchanged(self):
  from sales.commercial.catalog import PROFILES
  self.assertEqual(self.x['campaign']['filters']['work_budget'],PROFILES['extended'])
class Persistence44(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.db');self.store.init();self.cid=populate(self.store,[job(),job(ident=2,url='https://it.linkedin.com/jobs/view/wordpress-at-alfa-123')])
 def tearDown(self):self.tmp.cleanup()
 def test_migration_repeatable_and_old_schema_readable(self):
  with self.store.connect() as c:c.execute('DROP TABLE commercial_job_reviews');c.execute('DELETE FROM research_schema WHERE version=65')
  self.assertEqual(listing(self.store,{'category':'all'},as_of=NOW)['total'],1)
  migrate(self.store);migrate(self.store)
  with self.store.connect() as c:self.assertEqual(c.execute('select count(*) from commercial_revisions').fetchone()[0],2)
 def test_review_preserves_qualifications_and_crm(self):
  with self.store.connect() as c:before=[tuple(r) for r in c.execute('SELECT * FROM commercial_revisions')]
  review(self.store,1,{'status':'interesting','revision_id':1});self.assertEqual(listing(self.store,{'category':'all','review':'interesting'},NOW)['total'],1)
  review(self.store,2,{'status':'not_interesting','revision_id':2});self.assertEqual(listing(self.store,{'category':'all'},as_of=NOW)['total'],0)
  self.assertEqual(listing(self.store,{'category':'all','review':'not_interesting'},NOW)['total'],1)
  with self.store.connect() as c:
   self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM commercial_revisions')]);self.assertEqual(c.execute('SELECT count(*) FROM prospects').fetchone()[0],0)
 def test_wrong_revision_cannot_write(self):
  with self.assertRaises(ValueError):review(self.store,1,{'status':'interesting','revision_id':2})
 def test_invalid_state(self):
  with self.assertRaises(ValueError):review(self.store,1,{'status':'VERIFIED','revision_id':1})
 def test_campaign_filter_and_pagination(self):
  self.assertEqual(listing(self.store,{'category':'all','campaign':self.cid},NOW)['total'],1);self.assertEqual(listing(self.store,{'category':'all','campaign':self.cid+1},NOW)['total'],0)
  self.assertEqual(listing(self.store,{'category':'all','offset':1},NOW)['items'],[])
if __name__=='__main__':unittest.main()

class Admission44(unittest.TestCase):
 def test_employee_reaches_manual_projection_not_verified(self):
  from sales.commercial.discovery import assess as discover
  r=discover({'url':'https://linkedin.com/jobs/view/wordpress-developer-at-alfa-123','title':'WordPress Developer at Alfa','snippet':'Cerchiamo WordPress developer dipendente a tempo indeterminato.'},'FREELANCE')
  self.assertEqual(r['decision'],'admit');self.assertTrue(r['recommendation_only'])
  self.assertNotIn('state',r)
 def test_employee_sap_stays_out(self):
  from sales.commercial.discovery import assess as discover
  r=discover({'url':'https://linkedin.com/jobs/view/sap-at-alfa-123','title':'SAP Developer at Alfa','snippet':'Contratto dipendente a tempo indeterminato.'},'FREELANCE')
  self.assertEqual(r['decision'],'exclude')
 def test_audit_summary_does_not_reclassify(self):
  from sales.commercial.audit_summary import coverage
  b={'completed':False,'pages':[{'viewport':390,'complete':False,'measurements':{'text_excerpt':'Testo osservato','fonts_loaded':True}}],'failure_codes':['rendering_timeout']}
  before=copy.deepcopy(b);r=coverage(b);self.assertFalse(r['completed']);self.assertTrue(r['viewports'][0]['observed']);self.assertTrue(r['viewports'][0]['missing']);self.assertEqual(before,b)

class FinalRankingEdges44(unittest.TestCase):
 def test_same_employer_distinct_projects_not_merged(self):
  a=job(snippet='Cerchiamo WordPress freelance per un portale turistico.');b=job(snippet='Cerchiamo WordPress freelance per un portale industriale.',url='https://other.example/jobs/567',ident=2)
  self.assertEqual(sum(r['recommended'] for r in rank([a,b],NOW)),2)
 def test_future_publication_unknown_and_not_bonus(self):
  r=assess(job(dates={'published_at':'2027-01-01','publication_basis':'JobPosting.datePosted'}),NOW)
  self.assertIsNone(r['published_at']);self.assertIn('Data non verificata.',r['missing'])
