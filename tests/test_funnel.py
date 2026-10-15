import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store,now
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel,migrate
from sales.research_discovery import inspect_source,seed_campaign
from sales.research_analysis import ResearchWeb
from sales.research_triage import triage
from sales.company_research import selected_strategies
from sales.research_strategies import TEMPLATES
from test_research import sample
from sales.research_rules import qualify

class FunnelTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.db');self.store.init();self.rs=ResearchStore(self.store);self.c=self.rs.create({'regions':['Veneto']});self.f=Funnel(self.rs)
 def tearDown(self):self.tmp.cleanup()
 def page(self,text,url='https://alfa.example/'):
  return {'url':url,'status':200,'checked_at':now(),'html':'<title>Alfa Srl</title><main>'+text+'</main><footer><p>Alfa Srl</p><p>Via Roma 2, 35100 Padova (PD)</p><p>P.IVA 12345678901</p><a href="mailto:info@alfa.example">info@alfa.example</a></footer>'}
 def test_additive_repeat_migration(self):
  self.f.transition(self.c,{'url':'https://alfa.example/','strategy':'change'},'discovered','Originale da leggere');migrate(self.store);migrate(self.store)
  self.assertEqual(self.f.listing()['total'],1)
  with self.store.connect() as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
 def test_frontier_bounded_fair_and_incremental(self):
  seed_campaign(self.rs,self.c)
  with self.store.connect() as c:
   self.assertLessEqual(c.execute('SELECT count(*) FROM research_tasks').fetchone()[0],48)
   self.assertEqual({r[0] for r in c.execute("SELECT DISTINCT strategy FROM research_tasks WHERE kind='search'")},set(selected_strategies(self.c['filters'])))
   before=c.execute('SELECT count(*) FROM discovery_frontier').fetchone()[0]
  self.assertLessEqual(before,20)
  t=self.rs.claim(self.c['id'],self.c['generation']);self.rs.task_done(t['id']);self.f.fill(self.c)
  with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM research_tasks').fetchone()[0],before)
 def test_large_sitemap_is_filtered_and_not_enqueued(self):
  xml='<urlset>'+''.join('<url><loc>https://source.example/tag/tag'+str(i)+'</loc></url>' for i in range(5000))+'<url><loc>https://source.example/nuova-linea-prodotti-alfa</loc><lastmod>'+now()+'</lastmod></url></urlset>'
  page={'url':'https://source.example/post-sitemap.xml','status':200,'checked_at':now(),'html':xml}
  with patch.object(ResearchWeb,'get',return_value=page):inspect_source(self.rs,self.c,{'payload':{'url':page['url'],'kind':'sitemap'}},lambda:None)
  with self.store.connect() as c:
   self.assertEqual(c.execute('SELECT count(*) FROM discovery_frontier').fetchone()[0],0)
   self.assertEqual(c.execute('SELECT count(*) FROM research_tasks').fetchone()[0],0)
 def test_old_feed_can_identify_companies_but_feed_self_is_not_candidate(self):
  xml='<rss><channel><link>https://source.example/</link><item><title>Nuova impresa</title><link>https://source.example/old</link><pubDate>Mon, 01 Jan 2001 00:00:00 GMT</pubDate></item></channel></rss>'
  page={'url':'https://source.example/feed','status':200,'checked_at':now(),'html':xml}
  with patch.object(ResearchWeb,'get',return_value=page):inspect_source(self.rs,self.c,{'payload':{'url':page['url'],'kind':'rss'}},lambda:None)
  with self.store.connect() as c:
   rows=c.execute('SELECT payload FROM discovery_frontier').fetchall()
   self.assertEqual(rows,[])  # Archived feeds no longer feed customer campaigns.
 def test_triage_never_calls_model_or_qualifies(self):
  with patch.object(ResearchWeb,'get',return_value=self.page('Abbiamo aperto un nuovo showroom a Padova.')),patch('sales.research_analysis.LocalResearcher.call',side_effect=AssertionError('No model during triage')):
   result=triage(self.store,{'url':'https://alfa.example/','strategy':'change'},lambda:None)
  self.assertEqual(result['state'],'promising');self.assertNotEqual(result['state'],'qualified');self.assertEqual(result['details']['identity']['region'],'Veneto')
 def test_generic_catalogue_is_not_promising(self):
  with patch.object(ResearchWeb,'get',return_value=self.page('Consulta il nostro catalogo. Ordini via email.')):
   self.assertEqual(triage(self.store,{'url':'https://alfa.example/','strategy':'gap'},lambda:None)['state'],'needs_review')
 def test_generic_partner_not_commission(self):
  with patch.object(ResearchWeb,'get',return_value=self.page('Studio grafico, consulenza marketing e collaborazioni creative.')):
   r=triage(self.store,{'url':'https://alfa.example/','strategy':'partner'},lambda:None)
  self.assertEqual(r['state'],'needs_review');self.assertEqual(r['details']['relationship'],'partner')
 def test_employee_not_project(self):
  with patch.object(ResearchWeb,'get',return_value=self.page('Cerchiamo sviluppatore per nuovo sito web. Contratto di lavoro a tempo indeterminato.')):
   self.assertEqual(triage(self.store,{'url':'https://alfa.example/','strategy':'explicit'},lambda:None)['state'],'rejected')
 def test_stop_rejects_late_triage_and_frontier(self):
  self.rs.stop(self.c['id']);self.assertIsNone(self.f.transition(self.c,{'url':'https://alfa.example/'},'promising','Segnale'))
  self.assertFalse(self.f.offer(self.c['id'],'candidate','gap',{'url':'https://alfa.example/'}));self.assertEqual(self.f.fill(self.c),0)
 def test_resume_transition_history(self):
  payload={'url':'https://alfa.example/','strategy':'change'}
  self.f.transition(self.c,payload,'discovered','Pagina da leggere');self.f.transition(self.c,payload,'promising','Evento in originale')
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);fresh=self.rs.resume(self.c['id']);self.f.transition(fresh,payload,'verifying','Verifica ripresa')
  with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM discovery_transitions').fetchone()[0],3)
  self.assertEqual(self.f.listing()['total'],1)
 def test_manual_feedback_denominator_deduplicated(self):
  ident=self.f.transition(self.c,{'url':'https://alfa.example/','strategy':'change'},'promising','Segnale',{'identity':{'name':'Alfa','website':'https://alfa.example/','identity_status':'verified'}})
  self.f.outcome('contacted',candidate_id=ident);self.f.outcome('contacted',candidate_id=ident);self.f.outcome('conversation',candidate_id=ident)
  group=next(r for r in self.f.metrics(self.c['id'])['strategies'] if r['strategy']=='change')
  self.assertEqual(group['contacted'],1);self.assertEqual(group['conversation'],1);self.assertFalse(group['sufficient'])
 def test_funding_not_project_budget(self):
  a=sample();a[2].append({**a[2][0],'id':'budget','kind':'budget','quote':'Il budget del finanziamento ottenuto è di 50000 euro.'});a[3]['budget_signal_id']='budget'
  self.assertIsNone(qualify(*a)['budget'])
 def test_procurement_unknown_and_expired(self):
  from sales.research_procurement import procurement_checks
  d={'official':True,'url':'https://ente.example/avviso','text':'Termine presentazione: 01/01/2020. Sono ammessi liberi professionisti. Unici requisiti: partita IVA. Nessun costo di partecipazione.'}
  checks=procurement_checks([d]);self.assertEqual(checks['deadline']['status'],'expired');self.assertEqual(checks['eligibility']['status'],'verified')
  d['official']=False;self.assertTrue(all(v['status']=='unknown' for v in procurement_checks([d]).values()))
 def test_publisher_not_counted_as_promising_company(self):
  page=self.page('Nuova linea di prodotti annunciata dall’impresa Alfa a Padova.')
  with patch.object(ResearchWeb,'get',return_value=page):r=triage(self.store,{'url':page['url'],'strategy':'change','publisher':True},lambda:None)
  self.assertEqual(r['state'],'needs_review');self.assertTrue(r['resolve']);self.assertFalse(r['details']['identity'])
 def test_legacy_backlog_preserves_ids_and_requeues(self):
  for n in range(80):self.rs.enqueue(self.c['id'],'candidate','change',{'url':f'https://alfa.example/{n}'},str(n))
  self.f.constrain_legacy_queue(self.c)
  with self.store.connect() as c:
   self.assertEqual(c.execute("SELECT count(*) FROM research_tasks WHERE state='pending'").fetchone()[0],48)
   self.assertEqual(c.execute('SELECT count(*) FROM research_tasks').fetchone()[0],80)
  task=self.rs.claim(self.c['id'],self.c['generation']);self.rs.task_done(task['id']);self.f.fill(self.c)
  with self.store.connect() as c:
   self.assertEqual(c.execute("SELECT count(*) FROM research_tasks WHERE state='pending'").fetchone()[0],48)
   self.assertEqual(c.execute('SELECT count(*) FROM research_tasks').fetchone()[0],80)
 def test_negative_feedback_requires_new_content(self):
  payload={'url':'https://alfa.example/','strategy':'change'};page=self.page('Abbiamo aperto un nuovo showroom a Padova.')
  with patch.object(ResearchWeb,'get',return_value=page):r=triage(self.store,payload,lambda:None)
  ident=self.f.transition(self.c,payload,r['state'],r['reason'],r['details']);self.f.outcome('not_relevant',candidate_id=ident)
  with patch.object(ResearchWeb,'get',return_value=page):self.assertEqual(triage(self.store,payload,lambda:None)['state'],'rejected')
 def test_contacted_preliminary_company_is_remembered(self):
  ident=self.f.transition(self.c,{'url':'https://alfa.example/','strategy':'change'},'promising','Segnale',{'identity':{'name':'Alfa','website':'https://alfa.example/','identity_status':'verified'}})
  self.f.outcome('contacted',candidate_id=ident)
  self.assertTrue(self.rs.suppressed({'website':'https://alfa.example/'}))
 def test_worker_promotes_only_after_deep_verification(self):
  from sales.research_worker import run
  args=sample();payload={'url':args[0]['website'],'strategy':'explicit'}
  def seed(rs,c):rs.enqueue(c['id'],'candidate','explicit',payload)
  result={'state':'promising','reason':'Richiesta originale','details':{'identity':args[0]}}
  deep={'identity':args[0],'documents':args[1],'assessment':qualify(*args)}
  with patch('sales.research_worker.seed_campaign',side_effect=seed),patch('sales.research_worker.triage',return_value=result),patch('sales.research_worker.inspect_candidate',return_value=deep) as inspect:
   run(self.store.path,self.c['id'],self.c['generation'])
  self.assertEqual(inspect.call_count,1);self.assertEqual(self.rs.campaign()['qualified'],1)
  with self.store.connect() as c:self.assertEqual([r[0] for r in c.execute('SELECT state FROM discovery_transitions ORDER BY id')],['discovered','promising','verifying','qualified'])
 def test_historical_directory_names_without_model(self):
  from sales.research_analysis import resolve_publisher
  page={'url':'https://fonte.example/startup','html':'<title>Elenco imprese</title><main><p><a href="https://alfa.example/">Alfa Srl</a> produce macchine per il settore alimentare.</p></main><nav><a href="https://credit.example">Credit Design</a></nav>','status':200,'checked_at':now()}
  with patch('sales.research_analysis.LocalResearcher.call',side_effect=AssertionError('Directory links do not need LLM')):
   result=resolve_publisher(self.store,page,{'directory':True,'strategy':'startup'},lambda:None)
  self.assertEqual(len(result['discovered']),1);self.assertEqual(result['discovered'][0]['subject'],'Alfa Srl');self.assertIn('da verificare',result['discovered'][0]['subject_method'])
 def test_invalid_model_name_not_silently_accepted(self):
  from sales.research_analysis import resolve_publisher
  page=self.page('Una nuova linea di prodotti per le aziende italiane.')
  with patch('sales.research_analysis.LocalResearcher.call',return_value={'companies':[{'name':'Inventata Srl','quote':'nuova linea'}]}):
   result=resolve_publisher(self.store,page,{},lambda:None)
  self.assertTrue(result['incomplete']);self.assertEqual(result['discovered'],[])
 def test_old_homepage_creation_is_not_old_business_event(self):
  page=self.page('Abbiamo una nuova linea di prodotti per distributori.')
  page['html']+='<script type="application/ld+json">{"@type":"WebPage","datePublished":"2010-01-01"}</script>'
  with patch.object(ResearchWeb,'get',return_value=page):result=triage(self.store,{'url':page['url'],'strategy':'change'},lambda:None)
  self.assertEqual(result['state'],'promising')
 def test_link_navigation_excluded_from_source(self):
  page=self.page('<nav><a href="/nuova-impresa">Startup menu</a></nav><a href="/notizia-nuova-linea-prodotti">Nuova linea di prodotti</a>')
  page['url']='https://fonte.example/news'
  from types import SimpleNamespace
  with patch('sales.research_discovery.ResearchWeb') as client:
   client.return_value.get.return_value=page;client.return_value.rules={'https://fonte.example':SimpleNamespace(site_maps=lambda:[])}
   inspect_source(self.rs,self.c,{'payload':{'url':page['url'],'kind':'html'}},lambda:None)
  with self.store.connect() as c:
   urls=[json.loads(r[0])['url'] for r in c.execute('SELECT payload FROM discovery_frontier')]
  self.assertEqual(urls,[])
 def test_identity_uses_legal_holder_not_seo_title_and_avoids_privacy_contact(self):
  from sales.research_analysis import identity_from
  home={'url':'https://alfa.example/','html':'<title>Soluzioni facili per te</title>','status':200,'checked_at':now()}
  legal={'url':'https://alfa.example/privacy-policy','html':'<p>Titolare del trattamento dei dati personali è ALFA S.r.l. (Società).</p><p>Sede legale Via Roma 1, 35100 Padova</p><p>P.IVA 12345678901</p><a href="mailto:dpo@alfa.example">dpo@alfa.example</a>','status':200,'checked_at':now()}
  identity=identity_from([home,legal]);self.assertEqual(identity['name'],'ALFA S.r.l.');self.assertEqual(identity['identity_status'],'verified');self.assertEqual(identity['contacts'],[]);self.assertEqual(len(identity['identity_contacts']),1)
 def test_original_publisher_evidence_is_scoped_to_company(self):
  from sales.research_analysis import inspect_candidate,LocalResearcher,document
  home=self.page('I nostri prodotti. <a href="/contatti">Contatti</a>');contact=self.page('Contatti','https://alfa.example/contatti')
  origin=document({'url':'https://editore.example/notizia','html':'<p>Alfa Srl presenta nuovi prodotti per la propria distribuzione.</p><p>Beta Srl cerca un fornitore per un nuovo sito.</p>','status':200,'checked_at':now()})
  quote='Alfa Srl presenta nuovi prodotti per la propria distribuzione.';seen=[]
  def analyze(model,identity,docs,coverage):seen.extend(docs);return [],{}, {'status':'insufficient'},[]
  with patch.object(ResearchWeb,'get',side_effect=lambda url:home if url.endswith('example/') else contact),patch.object(LocalResearcher,'analyze',analyze):
   inspect_candidate(self.store,{'url':home['url'],'subject':'Alfa Srl','subject_quote':quote,'official_link':True,'source_documents':[origin],'strategy':'startup'},lambda:None)
  external=next(d for d in seen if d['url']==origin['url']);self.assertEqual(external['research_text'],quote);self.assertIn('Beta',external['text'])
 def test_pause_does_not_leave_candidates_appearing_active(self):
  self.f.transition(self.c,{'url':'https://alfa.example/','strategy':'change'},'verifying','Controllo in corso')
  self.rs.stop(self.c['id']);self.rs.paused(self.c['id'])
  row=self.f.listing()['items'][0];self.assertEqual(row['state'],'promising');self.assertIn('sospesa',row['reason'])
