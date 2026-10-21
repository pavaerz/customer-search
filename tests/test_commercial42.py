"""Historical evidence replay and explicitly synthetic trust boundaries; offline."""
import copy,gzip,json,unittest
from pathlib import Path
from functools import lru_cache
from unittest.mock import patch
from test_commercial_engines import CommercialTestCase,page
from sales.commercial.catalog import options,PILOT,EXTENDED,ENGINES
from sales.commercial.discovery import assess,followup_allowed
from sales.commercial.indexed_jobs import resolution_continuity
from sales.commercial.identity import establish
from sales.commercial.geography import locate,resolve_location
from sales.commercial.ats import observed_links,allowed,inspect_portal
from sales.commercial.qualification import evaluate
from sales.commercial.opportunity_view import build
from sales.commercial.inspection import inspect
@lru_cache
def fixture():
 with gzip.open(Path(__file__).parent/'fixtures/commercial42/campaign26.json.gz','rt') as f:return json.load(f)
def pages(host):return sorted([copy.deepcopy(p) for u,p in fixture()['pages'].items() if host in u],key=lambda p:len(p['url']))
class Saved42(CommercialTestCase):
 def test_pilot_unchanged(self):
  _,b=options({'commercial_engines':list(ENGINES),'mode':'pilot'});self.assertEqual({k:b[k] for k in PILOT},PILOT);self.assertEqual(b['max_provider_requests'],7)
 def test_extended_explicit(self):
  _,b=options({'commercial_engines':list(ENGINES),'mode':'extended'});self.assertEqual(b['max_queries_per_engine'],10);self.assertEqual(4*b['max_serper_credits'],60);self.assertEqual(b['max_candidates_per_engine'],40);self.assertEqual(b['max_browser_runs'],4)
 def test_all_agency_traces(self):
  rows=[d for d in fixture()['commercial_discovery'] if d['engine']=='AGENCIES'];self.assertEqual(len(rows),30)
  admitted=[d['url'] for d in rows if assess(d['body'],'AGENCIES')['decision']=='admit'];self.assertEqual(len(admitted),1);self.assertIn('domileastudio',admitted[0])
 def test_dexanet_reseller_not_buyer(self):
  d=next(d for d in fixture()['commercial_discovery'] if 'dexanet' in d['url']);self.assertEqual(assess(d['body'],'AGENCIES')['decision'],'exclude')
 def test_domilea_not_technical_proof(self):
  d=next(d for d in fixture()['commercial_discovery'] if 'domilea' in d['url']);self.assertFalse(assess(d['body'],'AGENCIES')['technical_request_verified'])
 def test_resolution_historical_homonyms(self):
  for d in fixture()['commercial_discovery']:
   if d['body'].get('origin',{}).get('acquisition')!='resolution':continue
   t=next(t for t in fixture()['research_tasks'] if t['id']==d['body']['origin']['task_id'])
   if any(h in d['url'] for h in ('pacer.org','paceretfs','pacerstaffing','pacerpumps','minnesotanonprofits','shazam','tradeindia','rocketreach')):
    with self.subTest(url=d['url']):self.assertEqual(resolution_continuity(t['payload'],d['body'])['status'],'UNRESOLVED')
 def test_official_revool_admitted_not_verified(self):
  d=next(d for d in fixture()['commercial_discovery'] if d['url']=='https://www.revool.it/');t=next(t for t in fixture()['research_tasks'] if t['id']==d['body']['origin']['task_id']);r=resolution_continuity(t['payload'],d['body']);self.assertEqual(r['status'],'SUPPORTED');self.assertFalse(r['identity_verified']);self.assertFalse(r['request_verified'])
 def test_gorfar_owner_not_creator(self):
  p=pages('gorfar.it');i=establish(p);self.assertEqual(i['name'],'Gor.Far. Srl');self.assertEqual(i['identity_status'],'verified');self.assertEqual(locate(p,i)['regions'],['Emilia-Romagna'])
 def test_x2_document_anchor_not_legal_name(self):
  i=establish(pages('x2manufacturing.it'));self.assertEqual(i['name'],'X2 Manufacturing Srl');self.assertEqual(i['identity_status'],'verified')
 def test_guercino_cooperative(self):
  p=pages('guercinocarpenteria.it');i=establish(p);self.assertIn('Guercino',i['name']);self.assertEqual(i['identity_status'],'verified');self.assertEqual(locate(p,i)['regions'],['Emilia-Romagna'])
 def test_revool_offices(self):
  p=pages('revool.it');g=locate(p,establish(p));self.assertIn('Toscana',g['regions']);self.assertIn('Lombardia',g['regions'])
 def test_ats_actual_saved_link(self):
  p=pages('startup-bakery.com');i=establish(p);links=[l for x in p for l in observed_links(x,i)];self.assertEqual(len(links),1);self.assertIn('startupbakery/it/career',links[0]['url']);self.assertEqual(links[0]['ats_binding']['stage'],'PORTAL_FOUND')
 def test_ats_survives_inspection_followup(self):
  p=next(p for p in pages('startup-bakery.com') if '/lavora-con-noi/' in p['url'])
  with patch('sales.commercial.inspection.ResearchWeb.get',side_effect=lambda u:copy.deepcopy(fixture()['pages'][u])):
   r=inspect(self.store,{'url':p['url'],'commercial_engine':'STARTUPS','resolution_company':'Startup Bakery','resolution_role':'Frontend Developer','resolution_stage':'COMPANY_DOMAIN_CANDIDATE'})
  self.assertTrue(any(l.get('ats_binding') for l in r['followups']),r['followups']);self.assertNotIn(r['result']['state'],('VERIFIED','POTENTIAL'))
 def test_browser_saved_partial_no_defects(self):
  for oid in (799,803):
   b=next(r['body'] for r in fixture()['commercial_revisions'] if r['opportunity_id']==oid);v=build(b);self.assertNotEqual(v['status'],'READY_TO_CONTACT');self.assertEqual(v['audit_state'],'PARTIAL')
 def test_historical_qualifications_unchanged(self):
  for r in fixture()['commercial_revisions']:
   b=copy.deepcopy(r['body']);original=copy.deepcopy(b);build(b);self.assertEqual(b,original)
class Synthetic42(CommercialTestCase):
 def test_geography_before_postcode(self):self.assertEqual(resolve_location('Via Montecchio, 3, Carpineti, Emilia-Romagna 42033, IT')['region'],'Emilia-Romagna')
 def test_street_not_city(self):self.assertIsNone(resolve_location('Via Milano 10, 99999 Paese sconosciuto')['region'])
 def test_unknown_stays_unknown(self):self.assertIsNone(resolve_location('sede sconosciuta')['region'])
 def test_service_market_not_office(self):self.assertIsNone(resolve_location('Serviamo clienti a Milano')['region'])
 def test_ats_other_tenant_blocked(self):self.assertFalse(allowed('https://inrecruiting.intervieweb.it/other/it/career',{'portal_url':'https://inrecruiting.intervieweb.it/startupbakery/it/career'}))
 def test_ats_login_pdf_blocked(self):
  b={'portal_url':'https://jobs.lever.co/example'}
  for u in ('https://jobs.lever.co/example/apply','https://jobs.lever.co/example/job.pdf','http://jobs.lever.co/example/job'):
   self.assertFalse(allowed(u,b))
 def test_ats_no_verified_origin(self):
  p=page('<a href="https://jobs.lever.co/example">Careers</a>');self.assertEqual(observed_links(p,{'identity_status':'unknown','website':p['url']}),[])
 def test_generic_partner_not_commission(self):
  p=page('<main><p>Effettuiamo collaborazioni con Freelancer e Agenzie di Comunicazione per creare progetti grafici completi.</p></main>');i={'name':'Example','website':p['url'],'identity_status':'verified','contacts':[]};g={'eligible':True,'regions':['Veneto']}
  r=evaluate('AGENCIES',i,p,g);r['identity']=i;v=build(r);self.assertEqual(r['state'],'NEEDS_REVIEW');self.assertEqual(v['status'],'WORTH_REVIEWING');self.assertIn('nessuna richiesta tecnica',v['reason']);self.assertIsNone(v['budget'])
 def test_ats_portal_not_request(self):
  p=pages('startup-bakery.com');i=establish(p);link=next(l for x in p for l in observed_links(x,i));b=link['ats_binding']
  portal={'url':link['url'],'status':200,'checked_at':p[0]['checked_at'],'html':'<title>Startup Bakery careers</title><a href="/startupbakery/it/jobs/frontend">Frontend developer</a>'}
  class Web:
   def get(self,u):return copy.deepcopy(fixture()['pages'][u])
  r=inspect_portal(self.store,Web(),portal,{'commercial_engine':'STARTUPS','ats_binding':b});self.assertEqual(r['result']['state'],'UNVERIFIABLE');self.assertTrue(r['result']['ats']['portal_verified']);self.assertFalse(r['result']['ats']['job_found']);self.assertEqual(len(r['followups']),1)
 def test_ats_wrong_company_job(self):
  p=pages('startup-bakery.com');i=establish(p);l=next(l for x in p for l in observed_links(x,i))
  portal={'url':l['url'],'status':200,'checked_at':p[0]['checked_at'],'html':'<script type="application/ld+json">'+json.dumps({'@type':'JobPosting','title':'Frontend developer','description':'Cerchiamo freelance WordPress','hiringOrganization':{'@type':'Organization','name':'Other Company'}})+'</script>'}
  class Web:
   def get(self,u):return copy.deepcopy(fixture()['pages'][u])
  r=inspect_portal(self.store,Web(),portal,{'commercial_engine':'STARTUPS','ats_binding':l['ats_binding']});self.assertEqual(r['result']['classification'],'ats_employer_mismatch');self.assertFalse(r['result']['ats']['request_open'])
 def test_extended_no_start_and_per_engine_reservations(self):
  from sales.commercial.resources import Budget,BudgetExceeded
  from sales.research_store import ResearchStore
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
  with patch('sales.campaigns.CampaignManager.launch',side_effect=AssertionError('must not launch')):
   c=self.rs.create({'commercial_engines':list(ENGINES),'mode':'extended'})
  a=Budget(self.store,c,'AGENCIES',c['filters']['work_budget']);f=Budget(self.store,c,'FREELANCE',c['filters']['work_budget'])
  a.reserve('queries',10);f.reserve('queries',1)
  with self.assertRaises(BudgetExceeded):a.reserve('queries')
  self.assertEqual(f.used('queries'),1);self.assertEqual(a.used('queries'),10)
 def test_extended_campaign_ai_global_unchanged(self):
  from sales.commercial.ai_settings import save,read
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);before=read(self.store)
  c=self.rs.create({'commercial_engines':list(ENGINES),'mode':'extended'})
  self.assertEqual(read(self.store),before)
  self.assertEqual(c['filters']['commercial']['ai']['max_calls_per_campaign'],before['max_calls_per_campaign'])
 def test_ats_redirect_cannot_change_tenant(self):
  b={'portal_url':'https://jobs.lever.co/company','origin_url':'https://company.test/'}
  with self.assertRaisesRegex(ValueError,'redirect'):
   inspect_portal(self.store,None,{'url':'https://jobs.lever.co/other/job'},{'commercial_engine':'STARTUPS','ats_binding':b})
 def test_generic_partner_full_inspection(self):
  p=page('Effettuiamo collaborazioni con Freelancer e Agenzie di Comunicazione per creare progetti grafici completi.',url='https://alfa.example/collabora-con-noi/',extra='<p>Siamo una web agency e realizziamo siti WordPress.</p>')
  with patch('sales.commercial.inspection.ResearchWeb.get',side_effect=lambda u:{**p,'url':u}):
   r=inspect(self.store,{'url':p['url'],'commercial_engine':'AGENCIES'})
  self.assertEqual(build(r['result'])['status'],'WORTH_REVIEWING');self.assertNotEqual(r['result']['state'],'VERIFIED')
 def test_source_retry_window_preserved(self):
  from datetime import datetime,timezone
  from sales.access_status import AccessIssue
  from sales.commercial.retry_policy import retry_at,park_until_manual_resume
  t=retry_at(AccessIssue('robots_temporary','temporary',retryable=True,delay=300));self.assertGreater((datetime.fromisoformat(t)-datetime.now(timezone.utc)).total_seconds(),295);self.assertTrue(park_until_manual_resume(t))
 def test_retry_no_busy_wait_for_long_cooldown(self):
  from datetime import datetime,timezone,timedelta
  from sales.commercial.retry_policy import park_until_manual_resume
  now=datetime.now(timezone.utc);self.assertFalse(park_until_manual_resume((now+timedelta(seconds=20)).isoformat(),now));self.assertTrue(park_until_manual_resume((now+timedelta(seconds=90)).isoformat(),now))
 def test_pending_cooldown_survives_resume(self):
  from datetime import datetime,timezone,timedelta
  self.rs.enqueue(self.c['id'],'candidate','AGENCIES',{'url':'https://alfa.example'})
  with self.store.connect() as c:tid=c.execute('select max(id) from research_tasks').fetchone()[0];c.execute("update research_tasks set attempts=1 where id=?",(tid,))
  until=(datetime.now(timezone.utc)+timedelta(seconds=300)).isoformat();self.rs.task_done(tid,'robots_temporary',retry=True,retry_at=until)
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.rs.resume(self.c['id'])
  with self.store.connect() as c:r=c.execute('select state,available_at from research_tasks where id=?',(tid,)).fetchone()
  self.assertEqual(r['state'],'pending');self.assertGreaterEqual(r['available_at'],until)
 def test_name_alone_not_entity_context(self):
  r=resolution_continuity({'resolution_company':'Pacer','resolution_role':'Full Stack Developer','resolution_stage':'COMPANY_DOMAIN_CANDIDATE'},{'url':'https://pacer.test/','title':'Pacer careers','content':'Join our growing team.'});self.assertEqual(r['status'],'UNRESOLVED')
 def test_ats_non_tenant_job_needs_observed_link(self):
  u='https://inrecruiting.intervieweb.it/jobs/frontend-developer-123/en';b={'portal_url':'https://inrecruiting.intervieweb.it/startupbakery/it/career'}
  self.assertFalse(allowed(u,b));self.assertTrue(allowed(u,{**b,'observed_job_url':u}));self.assertFalse(allowed('https://inrecruiting.intervieweb.it/jobs/another-123/en',{**b,'observed_job_url':u}))
 def test_ats_suppression_blocks_opportunity_and_followups(self):
  p=pages('startup-bakery.com');i=establish(p);l=next(l for x in p for l in observed_links(x,i));portal={'url':l['url'],'status':200,'checked_at':p[0]['checked_at'],'html':'<a href="/jobs/frontend-123/it">Frontend developer</a>'}
  class Web:
   def get(self,u):return copy.deepcopy(fixture()['pages'][u])
  with patch('sales.research_store.ResearchStore.suppressed',return_value='Non contattare'):
   r=inspect_portal(self.store,Web(),portal,{'commercial_engine':'STARTUPS','ats_binding':l['ats_binding']})
  self.assertEqual(r['result']['state'],'REJECTED');self.assertEqual(r['followups'],[])
 def test_actor_resolution_queries_include_role_context(self):
  from sales.commercial.indexed_jobs import resolution
  r=resolution({'url':'https://linkedin.com/jobs/view/123','title':'Pacer cerca sviluppatore freelance WordPress'});self.assertIn('WordPress',r['query']);self.assertIn('Italia',r['query'])
