"""Phase 4.5 synthetic tests: no live sites, controlled UTC clock."""
import copy,json,tempfile,unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from test_commercial44 import job,populate,NOW,load
from sales.commercial.job_activity import evaluate,observation,extract_page,early_exclusion,window,utc
from sales.commercial.recommendation_store import listing,record_observation,saved_activity_filter,migrate
from sales.commercial.recommendations import rank
from sales.commercial.catalog import BUDGETS,PILOT,EXTENDED
from sales.db import Store
URL='https://linkedin.com/jobs/view/wordpress-at-alfa-123'
def evidence(kind,value,**kw):
 return observation(kind,value,kw.pop('url',URL),kw.pop('observed_at',NOW.isoformat()),str(value),**kw)
def sample(age=3,geo='Remote Italy',state='OPEN_CONFIRMED'):
 j=job();ev=[evidence('geography',geo)]
 if age is not None:ev.append(evidence('publication',(NOW-timedelta(days=age)).isoformat(),method='JobPosting.datePosted'))
 if state:ev.append(evidence('application',state))
 j['body']['job_activity_evidence']=ev;return j

def activity(j,**kw):return evaluate(j['body'],j['engine'],NOW,**kw)
class Activity45(unittest.TestCase):
 def test_01_three_days_open_italy(self):self.assertEqual(activity(sample())['category'],'recent')
 def test_02_thirteen_days_open_unknown(self):
  a=activity(sample(13,'Italia',None));self.assertEqual(a['category'],'recent');self.assertIn('Apertura da verificare',a['reasons'])
 def test_03_fifteen_days(self):self.assertEqual(activity(sample(15))['category'],'archived')
 def test_04_year_old(self):self.assertEqual(activity(sample(365))['category'],'archived')
 def test_05_unknown_date(self):self.assertEqual(activity(sample(None))['category'],'verify')
 def test_06_yesterday_closed(self):self.assertEqual(activity(sample(1,state='CLOSED_CONFIRMED'))['category'],'archived')
 def test_07_us_only(self):self.assertEqual(activity(sample(1,'Remote US only'))['category'],'archived')
 def test_08_worldwide(self):self.assertEqual(activity(sample(1,'Remote worldwide'))['category'],'recent')
 def test_09_remote_unspecified(self):
  a=activity(sample(1,'Remote'));self.assertEqual(a['category'],'verify');self.assertEqual(a['geographic_eligibility'],'GEO_UNKNOWN')
 def test_10_us_company_europe(self):self.assertEqual(activity(sample(1,'US company. Remote Europe'))['category'],'recent')
 def test_11_crawling_not_publication(self):
  j=sample(None);j['body'].update(checked_at=NOW.isoformat(),published_at=NOW.isoformat(),dates={'published_at':NOW.isoformat(),'publication_basis':'search_index'})
  self.assertEqual(activity(j)['freshness_status'],'DATE_UNKNOWN')
 def test_12_specific_closure(self):
  j=sample(1,state=None);j['body']['evidence']=[{'kind':'request','channel':'visible','quote':'WordPress developer. No longer accepting applications','url':URL,'checked_at':NOW.isoformat()}]
  self.assertEqual(activity(j)['category'],'archived')
 def test_13_negated_closure(self):
  for text in ['We are not closing applications.','Unlike other jobs, applications are not closed.','Applications are not closed.']:
   j=sample(1,state=None);j['body']['evidence']=[{'kind':'request','channel':'visible','quote':text,'url':URL,'checked_at':NOW.isoformat()}]
   self.assertNotEqual(activity(j)['application_status'],'CLOSED_CONFIRMED')
 def test_14_manual_recent_closure(self):
  a=activity(sample(1),manual=[evidence('application','CLOSED_CONFIRMED',provenance='MANUAL_OBSERVATIONS')]);self.assertEqual(a['category'],'archived');self.assertTrue(a['conflicts'])
 def test_15_conflicting_sources(self):
  j=sample(1);j['body']['job_activity_evidence'].append(evidence('publication',(NOW-timedelta(days=15)).isoformat(),method='JobPosting.datePosted',url='https://alfa.example/jobs/42',same_job_verified=True))
  a=activity(j);self.assertTrue(a['conflicts']);self.assertNotEqual(a['category'],'recent')
 def test_16_alternative_bound_original(self):
  j=sample(None);j['body']['job_activity_evidence'].append(evidence('publication',(NOW-timedelta(days=2)).isoformat(),method='JobPosting.datePosted',url='https://alfa.example/jobs/42',same_job_verified=True))
  self.assertEqual(activity(j)['category'],'recent')
 def test_17_snippet_only(self):self.assertEqual(activity(job())['category'],'verify')
 def test_18_score_cannot_bypass_date(self):
  j=sample(100);j['body']['discovery']['title']='WordPress WooCommerce frontend JavaScript freelance remote'
  self.assertGreater(rank([j],NOW)[0]['compatibility_score'],70);self.assertEqual(activity(j)['category'],'archived')
 def test_19_outbound_exempt(self):
  j=sample(300);j['engine']='WEBSITE_REBUILD';self.assertFalse(activity(j)['applicable']);self.assertEqual(activity(j)['category'],'not_applicable')
 def test_20_limits_not_increased(self):
  self.assertEqual(EXTENDED['max_serper_credits'],15);self.assertEqual(EXTENDED['max_http_reads'],350);self.assertEqual(EXTENDED['max_browser_runs'],4);self.assertEqual(BUDGETS['max_runtime_seconds'],3600)
 def test_future_and_invalid(self):
  self.assertEqual(activity(sample(-1))['freshness_status'],'FUTURE_OR_INVALID_DATE')
  j=sample();j['body']['job_activity_evidence'][1]['value']='yesterday-ish';self.assertEqual(activity(j)['freshness_status'],'FUTURE_OR_INVALID_DATE')
 def test_relative_requires_observation_and_meaning(self):
  j=sample(None);e=evidence('publication',None,method='relative_publication',relative_label='5 days ago',relative_meaning='job_publication');j['body']['job_activity_evidence'].append(e)
  a=activity(j);self.assertEqual(a['category'],'recent');self.assertIsNone(a['published_at']);self.assertTrue(a['publication_interval'])
  e['observed_at']=None;self.assertEqual(activity(j)['freshness_status'],'DATE_UNKNOWN')
 def test_relative_boundary_uncertain(self):
  j=sample(None);j['body']['job_activity_evidence'].append(evidence('publication',None,method='relative_publication',relative_label='14 days ago',relative_meaning='job_publication'))
  self.assertEqual(activity(j)['freshness_status'],'DATE_UNKNOWN')
 def test_open_apply_snippet_not_confirmation(self):
  j=sample(1,state=None);j['body']['discovery']['snippet']='WordPress Italy. Apply. Applications open.';self.assertEqual(activity(j)['application_status'],'OPEN_UNKNOWN')
 def test_old_open_evidence_expires(self):
  j=sample(1);j['body']['job_activity_evidence'][-1]['observed_at']=(NOW-timedelta(days=20)).isoformat();self.assertEqual(activity(j)['application_status'],'OPEN_UNKNOWN')
 def test_remote_us_is_not_worldwide(self):
  a=activity(sample(1,'Remote — United States'));self.assertEqual(a['category'],'verify');self.assertEqual(a['geographic_eligibility'],'GEO_UNKNOWN')
 def test_uk_residency(self):self.assertEqual(activity(sample(1,'UK residents only'))['category'],'archived')
 def test_europe_except_italy(self):self.assertEqual(activity(sample(1,'Remote Europe except Italy'))['category'],'archived')
 def test_emea_without_italy_unknown(self):self.assertEqual(activity(sample(1,'Remote EMEA'))['category'],'verify')
 def test_standing_invitation_not_archived(self):
  j=sample(365);j['engine']='AGENCIES';j['body']['classification']='ongoing';self.assertEqual(activity(j)['category'],'not_applicable')
 def test_startup_project_not_job(self):
  j=sample(365);j['engine']='STARTUPS';j['body']['classification']='paid_development';self.assertFalse(activity(j)['applicable'])
 def test_second_source_not_bound(self):
  j=sample(None);j['body']['job_activity_evidence'].append(evidence('publication',NOW.isoformat(),url='https://alfa.example/jobs/99',method='JobPosting.datePosted'))
  self.assertEqual(activity(j)['freshness_status'],'DATE_UNKNOWN')
 def test_early_snippet_dates_and_closure_not_proof(self):
  self.assertIsNone(early_exclusion({'url':URL,'title':'WordPress','snippet':'Applications closed','date':'2025-01-01'},'FREELANCE',NOW))
 def test_early_explicit_geo_excludes(self):self.assertEqual(early_exclusion({'url':URL,'title':'WordPress US only'},'FREELANCE',NOW)['reason'],'job_geo_incompatible')
 def test_window_configurable(self):self.assertEqual(activity(sample(15),max_age_days=20)['category'],'recent')
 def test_timezone_conversion(self):self.assertEqual(utc('2026-10-18T02:00:00+02:00'),NOW)
 def test_input_unchanged(self):
  j=sample();saved=copy.deepcopy(j);activity(j);self.assertEqual(j,saved)
class Extraction45(unittest.TestCase):
 def page(self,description='Cerchiamo sviluppatore WordPress freelance. Applications open. Remote Italy.',extra=''):
  data={'@context':'https://schema.org','@type':'JobPosting','title':'WordPress Developer','description':description,'datePosted':'2026-10-16','hiringOrganization':{'name':'Alfa'},'applicantLocationRequirements':{'@type':'Country','name':'Italy'},'jobLocationType':'TELECOMMUTE'}
  return {'url':'https://alfa.example/jobs/wordpress','html':'<html><title>WordPress Developer</title><script type="application/ld+json">'+json.dumps(data)+'</script><main><h1>WordPress Developer</h1><p>'+description+'</p></main>'+extra+'</html>','checked_at':NOW.isoformat(),'status':200}
 def test_jobposting_and_footer(self):
  p=self.page(extra='<footer>Applications closed</footer>');ev=extract_page(p)
  self.assertTrue(any(e['kind']=='publication' for e in ev));self.assertFalse(any(e.get('value')=='CLOSED_CONFIRMED' for e in ev))
 def test_multiple_jobposting_no_date_transfer(self):
  p=self.page();p['html']+=p['html'];ev=extract_page(p);self.assertFalse(any(e['kind']=='publication' for e in ev))
 def test_apply_is_not_open(self):
  p=self.page(description='Cerchiamo WordPress freelance. Apply');self.assertFalse(any(e.get('value')=='OPEN_CONFIRMED' for e in extract_page(p)))
class Store45(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'test.db');self.store.init();self.cid=populate(self.store,[sample()])
 def tearDown(self):self.temp.cleanup()
 def test_defaults_recent(self):self.assertEqual(listing(self.store,{},NOW)['total'],1)
 def test_manual_preserved_and_no_commercial_write(self):
  with self.store.connect() as c:before=[tuple(r) for r in c.execute('SELECT * FROM commercial_revisions')]
  record_observation(self.store,1,{'revision_id':1,'kind':'closed','observed_at':NOW.isoformat(),'note':'No longer accepting applications'},NOW)
  self.assertEqual(listing(self.store,{},NOW)['total'],0)
  a=listing(self.store,{'category':'archived'},NOW)['items'][0];self.assertTrue(a['activity']['conflicts']);self.assertEqual(a['official_state'],'UNVERIFIABLE')
  with self.store.connect() as c:self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM commercial_revisions')]);migrate(c);migrate(c)
  self.assertEqual(len(listing(self.store,{'category':'archived'},NOW)['items'][0]['manual_observations']),1)
 def test_manual_negative_avoids_retry(self):
  record_observation(self.store,1,{'revision_id':1,'kind':'too_old','observed_at':NOW.isoformat(),'note':'Circa un anno fa'},NOW)
  # Conflicting recent date is retained and does not cause automatic skipping.
  self.assertIsNone(saved_activity_filter(self.store,{'url':URL},'FREELANCE',NOW))
 def test_bad_revision_future_invalid(self):
  for req in ({'revision_id':2,'kind':'closed','observed_at':NOW.isoformat()},{'revision_id':1,'kind':'closed','observed_at':'2099-01-01'},{'revision_id':1,'kind':'closed'}):
   with self.assertRaises(ValueError):record_observation(self.store,1,req,NOW)
 def test_window_validation(self):
  for n in (0,91,True,'2.5',None):
   with self.assertRaises(ValueError):window(n)

class Discovery45(unittest.TestCase):
 def test_provider_period_from_existing_adapter(self):
  from sales.commercial.coordinator import acquire
  class Config:
   def settings(self):return {'provider':'serper'}
  with patch('sales.serper_provider.search',return_value=({'results':[]},True)) as search:
   acquire(Config(),{'query':'WordPress freelance','discovery_period':'month'},lambda:None)
   self.assertEqual(search.call_args.args[3],'month');self.assertIn('-filetype:pdf',search.call_args.args[1])
   acquire(Config(),{'query':'Alfa official','discovery_period':'month','resolution_url':URL},lambda:None)
   self.assertEqual(search.call_args.args[3],'')
 def test_new_families_and_other_engines_stable(self):
  from sales.commercial.strategies import plans
  p=plans('FREELANCE',['Veneto']);q=' '.join(x['query'] for x in p)
  self.assertIn('remote Italy',q);self.assertIn('remote Europe',q);self.assertIn('WooCommerce',q);self.assertLessEqual(len(p),10)
  self.assertTrue(all(x['strategy_version']=='4.3' for x in plans('WEBSITE_REBUILD',['Veneto'])))
 def test_enqueue_uses_snapshot_budget_unchanged(self):
  from sales.research_store import ResearchStore
  from sales.commercial.coordinator import Coordinator
  with tempfile.TemporaryDirectory() as d:
   s=Store(Path(d)/'a.db');s.init();rs=ResearchStore(s);c=rs.create({'commercial_engines':['FREELANCE'],'mode':'extended','max_job_age_days':14});co=Coordinator(s,c)
   co.enqueue('search','FREELANCE',{'query':'WordPress freelance','page':1},'test')
   with s.connect() as db:p=json.loads(db.execute('SELECT payload FROM research_tasks').fetchone()[0])
   self.assertEqual(p['discovery_period'],'month');self.assertEqual(p['max_serper_credits'],15);self.assertEqual(p['max_job_age_days'],14)
 def test_known_negative_no_network(self):
  j=sample(30,state=None)
  with tempfile.TemporaryDirectory() as d:
   s=Store(Path(d)/'a.db');s.init();populate(s,[j]);a=saved_activity_filter(s,{'url':URL},'FREELANCE',NOW)
   self.assertEqual(a['category'],'archived')

class EarlyOriginal45(unittest.TestCase):
 def test_closed_original_stops_after_one_read(self):
  from sales.commercial.inspection import inspect
  p=Extraction45().page(description='Cerchiamo sviluppatore WordPress freelance. No longer accepting applications.')
  with tempfile.TemporaryDirectory() as d:
   s=Store(Path(d)/'a.db');s.init()
   with patch('sales.commercial.inspection.ResearchWeb.get',return_value=p) as get:
    r=inspect(s,{'url':p['url'],'commercial_engine':'FREELANCE','max_reads':6})
   self.assertEqual(get.call_count,1);self.assertEqual(r['followups'],[]);self.assertEqual(r['result']['classification'],'expired')

class ManualMemory45(unittest.TestCase):
 def test_observation_prevents_resolution_search(self):
  from sales.research_store import ResearchStore
  from sales.commercial.coordinator import Coordinator
  with tempfile.TemporaryDirectory() as d:
   s=Store(Path(d)/'a.db');s.init();populate(s,[sample(None,state=None)])
   record_observation(s,1,{'revision_id':1,'kind':'closed','observed_at':NOW.isoformat()},NOW)
   campaign=ResearchStore(s).create({'commercial_engines':['FREELANCE']});co=Coordinator(s,campaign)
   with patch.object(co,'enqueue') as enqueue:
    self.assertFalse(co.offer('FREELANCE',{'url':URL,'title':'WordPress freelance at Alfa'},{}));enqueue.assert_not_called()

class GeographicPriority45(unittest.TestCase):
 def test_italy_eu_higher_than_worldwide(self):
  for place in ('Remote Italy','Remote EU','Padova'):
   self.assertEqual(activity(sample(1,place))['geographic_priority'],'HIGH')
  for place in ('Remote worldwide','Remote Europe','Remote EMEA Italy'):
   self.assertEqual(activity(sample(1,place))['geographic_priority'],'MEDIUM')

class Residence45(unittest.TestCase):
 def test_applicant_country_not_invented_remote(self):
  p=Extraction45().page(description='Cerchiamo WordPress freelance.')
  p['html']=p['html'].replace('"jobLocationType": "TELECOMMUTE"','"jobLocationType": "UNKNOWN"')
  ev=extract_page(p)
  self.assertFalse(any(e['kind']=='geography' and 'Remote' in str(e['value']) for e in ev))
  a=evaluate({'url':p['url'],'job_activity_evidence':ev},'FREELANCE',NOW)
  self.assertEqual(a['geographic_eligibility'],'GEO_UNKNOWN')

class StaleIsNotClosed45(unittest.TestCase):
 def test_early_old_but_open_is_not_expired(self):
  from sales.commercial.inspection import inspect
  p=Extraction45().page();p['html']=p['html'].replace('2026-10-16','2026-09-28')
  with tempfile.TemporaryDirectory() as d:
   s=Store(Path(d)/'a.db');s.init()
   with patch('sales.commercial.inspection.ResearchWeb.get',return_value=p):r=inspect(s,{'url':p['url'],'commercial_engine':'FREELANCE'})
   self.assertEqual(r['result']['classification'],'job_stale')
   self.assertEqual(r['result']['activity']['application_status'],'OPEN_CONFIRMED')

class ExpiryBoundary45(unittest.TestCase):
 def test_date_only_expiry_still_valid_during_day(self):
  j=sample(1,state=None);j['body']['job_activity_evidence'].append(evidence('expiry','2026-10-18',method='JobPosting.validThrough'))
  a=evaluate(j['body'],'FREELANCE',NOW+timedelta(hours=12))
  self.assertEqual(a['application_status'],'OPEN_UNKNOWN')
  self.assertEqual(evaluate(j['body'],'FREELANCE',NOW+timedelta(days=2))['application_status'],'CLOSED_CONFIRMED')
