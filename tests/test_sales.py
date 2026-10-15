import json,sqlite3,tempfile,unittest,threading
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
from sales.db import Store,now
from sales.extract import parse_page,classify
from sales.providers import PublicWeb,RSS,canonical,blocked
from sales.engines import EngineManager
from sales.intelligence import qualify,communication
from sales.advisor import local_advice
TODAY=datetime.now(timezone.utc).date().isoformat()
def page(html,url='https://studio.it/collabora'):
 return {'url':url,'html':html,'status':200,'checked_at':now()}
def parsed(text,extra='',url='https://studio.it/collabora'):
 return parse_page(page('<title>Studio</title><meta property="og:site_name" content="Studio"><meta property="article:published_time" content="'+TODAY+'">'+extra+'<main><p>'+text+'</p></main>',url))
class Extraction(unittest.TestCase):
 def test_explicit_wordpress_freelance(self):
  p=parsed('Cerchiamo uno sviluppatore WordPress freelance per una collaborazione continuativa. Budget: 2500 euro.')
  for engine in ['A','B']:
   s,_=classify(p,engine,'https://studio.it/collabora');self.assertEqual(s['kind'],'request');self.assertTrue(s['ongoing']);self.assertIn('2500',s['budget'])
 def test_blog_not_request(self):
  p=parsed('Cerchiamo uno sviluppatore WordPress freelance? Ecco come trovarlo.', '<script type="application/ld+json">{"@type":"BlogPosting"}</script>')
  self.assertIsNone(classify(p,'A','https://studio.it/blog')[0])
 def test_informative_listing_employee_and_closed_rejected(self):
  for text in ['WordPress freelance, tutti i servizi della nostra agenzia','Cerchiamo sviluppatore WordPress a tempo indeterminato','Cerchiamo sviluppatore WordPress freelance. Posizione chiusa.']:
   self.assertIsNone(classify(parsed(text),'A','https://studio.it/')[0],text)
 def test_c_growth_not_publisher_identity(self):
  p=parsed('Acme annuncia una nuova sede a Milano: il quotidiano riporta tutti i dettagli.')
  self.assertIsNone(classify(p,'C','https://studio.it/notizia')[0])
  p=parsed('Abbiamo inaugurato una nuova sede a Milano. Vogliamo realizzare il nostro nuovo sito web.')
  self.assertEqual(classify(p,'C','https://studio.it/news')[0]['kind'],'signal')
 def test_c_requires_date(self):
  p=parsed('Abbiamo aperto un nuovo showroom e una nuova sede a Padova.');p['published_at']=None
  self.assertIsNone(classify(p,'C','https://studio.it/')[0])
 def test_future_date_not_verified(self):
  p=parse_page(page('<meta property="article:published_time" content="2999-01-01"><p>Test</p>'))
  self.assertIsNone(p['published_at'])
 def test_multi_job_and_expiry(self):
  jobs=[{'@type':'JobPosting','title':'WordPress','description':'Freelance'}]*2
  p=parse_page(page('<script type="application/ld+json">'+json.dumps(jobs)+'</script>'))
  self.assertIsNone(classify(p,'A',p.get('url','https://studio.it'))[0])
  jobs[0]['validThrough']='2020-01-01'
  p=parse_page(page('<script type="application/ld+json">'+json.dumps(jobs[0])+'</script>'))
  self.assertIsNone(classify(p,'A','https://studio.it/')[0])
 def test_navigation_not_hiring_evidence(self):
  p=parse_page(page('<nav>Cerchiamo sviluppatore WordPress freelance</nav><main>Servizi di marketing</main>'))
  self.assertIsNone(classify(p,'A','https://studio.it')[0])
 def test_public_contact_provenance(self):
  p=parse_page(page('<a href="mailto:ciao@studio.it">Scrivi</a>'))
  self.assertEqual(p['contacts'][0]['url'],'https://studio.it/collabora');self.assertIn('non implica consenso',p['contacts'][0]['basis'])
class GrowthRelevance(unittest.TestCase):
 def test_relocation_or_opening_alone_is_not_a_web_project(self):
  for text in ['Studio ha cambiato sede e recapito telefonico!', 'Ci siamo trasferiti nella nostra nuova sede a Milano.', 'Abbiamo inaugurato il nostro nuovo showroom.', 'Abbiamo aperto un nuovo negozio. Visita il nostro sito web.', 'Abbiamo lanciato il nostro nuovo e-commerce.', 'Abbiamo aperto una nuova sede. Non vogliamo realizzare un nuovo sito web.']:
   signal,reason=classify(parsed(text),'C','https://studio.it/news')
   self.assertIsNone(signal,text)
 def test_real_web_need_survives_next_to_an_opening(self):
  signal,_=classify(parsed('Abbiamo aperto il nostro nuovo negozio. Vogliamo realizzare un sito web per la nuova attività.'),'C','https://studio.it/news')
  self.assertIsNotNone(signal)
  self.assertIn('Vogliamo realizzare',signal['statement'])

class DirectProspecting(unittest.TestCase):
 def test_small_business_project_does_not_require_word_freelance(self):
  for text in ['Cerchiamo un professionista per realizzare il sito web del nostro negozio.', 'Abbiamo bisogno di sviluppare un ecommerce per il nostro laboratorio.', 'Cerchiamo un fornitore per il nostro sito web aziendale.']:
   signal,_=classify(parsed(text),'A','https://studio.it/progetto')
   self.assertIsNotNone(signal,text);self.assertEqual(signal['kind'],'request')
 def test_supplier_marketing_not_direct_customer_request(self):
  signal,_=classify(parsed('Realizziamo siti web per negozi e artigiani.'),'A','https://studio.it/servizi')
  self.assertIsNone(signal)
 def test_web_agency_credit_does_not_make_retailer_an_agency(self):
  from sales.prospecting import agency_identity
  self.assertFalse(agency_identity(parsed('Produciamo arredamenti su misura.</p><p>Website by Agenzia web Acme')))
  self.assertTrue(agency_identity(parsed('Siamo una web agency specializzata in WordPress.')))

class RegressionTests(unittest.TestCase):
 def test_supplier_self_description_not_request(self):
  p=parsed('Da buon developer cerco di dare qualità al codice WordPress. Sono un freelance.')
  self.assertIsNone(classify(p,'A','https://studio.it/')[0])
 def test_freelance_word_not_launch_signal(self):
  p=parsed('La nostra agenzia offre collaborazione. Il freelance gestisce autonomamente tempi e consegne.')
  self.assertIsNone(classify(p,'B','https://studio.it/')[0])
 def test_article_path_without_structured_data(self):
  p=parsed('Cerchiamo WordPress freelance, racconta il nostro intervistato.')
  self.assertIsNone(classify(p,'B','https://studio.it/resources/intervista')[0])
 def test_employer_site_application_invitation(self):
  p=parsed('Lavoriamo con professionisti autonomi e collaboratori remoti su progetti di agenzia.</p><p>WordPress developer</p><p>Invia candidatura')
  self.assertEqual(classify(p,'B','https://studio.it/lavora-con-noi/')[0]['kind'],'request')
 def test_growing_company_heading_does_not_hide_own_paragraph(self):
  p=parsed('Nuovo showroom per prodotti di arredo e design.</p><p>Abbiamo inaugurato il nostro nuovo showroom a Padova. Vogliamo realizzare un nuovo sito web.')
  self.assertIsNotNone(classify(p,'C','https://studio.it/news/')[0])
 def test_newsroom_quotation_not_company(self):
  p=parsed('Abbiamo inaugurato una nuova sede, ha dichiarato Acme.', '<meta name="author" content="Redazione">')
  self.assertIsNone(classify(p,'C','https://studio.it/news/')[0])
 def test_visible_italian_date(self):
  today=datetime.now(timezone.utc);months=['gennaio','febbraio','marzo','aprile','maggio','giugno','luglio','agosto','settembre','ottobre','novembre','dicembre']
  p=parse_page(page(f'<p>{today.day} {months[today.month-1]} {today.year}</p><p>Abbiamo aperto una nuova sede a Padova.</p>'))
  self.assertEqual(p['published_at'],TODAY)
class Database(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.s=Store(Path(self.temp.name)/'sales.sqlite3');self.s.init()
 def tearDown(self):self.temp.cleanup()
 def opportunity(self,engine='A',kind='request',text='Cerchiamo WordPress freelance',url='https://studio.it/collabora'):
  cid=self.s.company('https://studio.it/','Studio')
  sid=self.s.source({'url':url,'checked_at':'2026-01-01T00:00:00+00:00'},cid)
  eid=self.s.add_evidence(cid,sid,engine,kind,engine+' signal',text,TODAY,metadata={'skills':['WordPress']})
  pid,_=self.s.prospect(cid,engine,'Collaborazione','WordPress',65,{'Richiesta':30},text,'Da confermare',[],[eid]);return pid
 def runid(self,engine):
  with self.s.connect() as c:return c.execute('INSERT INTO runs(engine,started_at,status) VALUES (?,?,?)',(engine,now(),'running')).lastrowid
 def stats(self):return {'checked':0,'added':0,'duplicates':0,'errors':0,'rejected':0,'queries':0}
 def test_rss_still_runs_when_search_provider_fails(self):
  self.s.configure({'rss_feeds':['https://studio.it/feed']})
  with patch('sales.engines.provider') as provider,patch('sales.engines.RSS.entries',return_value=[{'url':'https://studio.it/news'}]):
   provider.return_value.search.side_effect=ValueError('Quota raggiunta')
   items=list(EngineManager(self.s).candidates('C',self.runid('C'),self.stats(),[],None))
  self.assertEqual(items,[{'url':'https://studio.it/news'}])
 def test_excluded_declared_location(self):
  html='<script type="application/ld+json">{"@type":"Organization","address":{"@type":"PostalAddress","addressLocality":"Napoli"}}</script><p>Cerchiamo sviluppatore WordPress freelance.</p>'
  with patch.object(PublicWeb,'get',return_value=page(html)):
   EngineManager(self.s).run(['A'],['https://studio.it/jobs'])
  self.assertEqual(self.s.list(),[]);self.assertIn('Località dichiarata esclusa',self.s.history()[0]['items'][0]['reason'])
 def test_contact_history_persists_and_is_shared_only_with_same_company(self):
  first=self.opportunity()
  sibling=self.opportunity(engine='C',kind='signal',text='Nuovo showroom',url='https://studio.it/news')
  self.assertIsNone(self.s.detail(first)['contacted_at'])
  self.s.update(first,{'stage':'contacted','interaction':'Contatto confermato manualmente.'})
  stamp=self.s.detail(first)['contacted_at']
  self.assertTrue(stamp)
  self.assertEqual(self.s.detail(sibling)['contacted_at'],stamp)
  self.assertEqual(self.s.detail(sibling)['stage'],'review')
  self.s.update(first,{'stage':'ready'})
  self.opportunity()
  self.assertEqual(Store(self.s.path).detail(first)['contacted_at'],stamp)
  self.assertEqual(self.s.stats()['engines'][0]['contacted'],1)
  other=self.s.company('https://other.example','Altra azienda')
  pid=self.s.prospect(other,'C','Apertura','Sito',50,{},'Apertura','Da verificare',[],[])[0]
  self.assertIsNone(self.s.detail(pid)['contacted_at'])
 def test_dismissal_persists_for_domain_and_keeps_contact_history(self):
  a=self.opportunity('A');other=self.opportunity('D','measurement','LCP 8s',url='https://studio.it/')
  self.s.update_company(a,{'stage':'contacted','notes':'Contatto già effettuato'})
  item=self.s.set_dismissed(other)
  self.assertTrue(item['dismissed_at'])
  self.assertEqual(item['stage'],'contacted')
  self.assertEqual(item['notes'],'Contatto già effettuato')
  fresh=Store(self.s.path)
  self.assertTrue(fresh.company_detail(a)['dismissed_at'])
  self.assertEqual(fresh.target_exclusion('http://www.studio.it/altro')['code'],'user_dismissed')
  self.assertEqual(sum(e['contacted'] for e in self.s.stats()['engines']),1)
  self.s.set_dismissed(a)
  self.assertEqual(sum(i['kind']=='dismissed' for i in self.s.company_detail(a)['interactions']),1)
  with self.assertRaises(ValueError):self.s.update_company(a,{'stage':'ready'})
 def test_deleted_company_is_skipped_by_all_research_engines(self):
  a=self.opportunity();self.s.set_dismissed(a)
  with patch.object(PublicWeb,'get') as read:
   EngineManager(self.s).run(['A','B','C','D','E'],['https://studio.it/news'])
  read.assert_not_called()
  self.assertEqual(len(self.s.list()),1)
  self.assertTrue(all(r['stats']['rejected'] for r in self.s.history()))
 def test_technical_engine_searches_new_sites_with_existing_companies(self):
  self.opportunity();self.s.configure({'technical_limit':1})
  report={'pagespeed':[],'observations':[],'limitations':[]}
  fresh=page('<title>Falegnameria</title>','https://new-business.it/')
  def results(*args):
   yield {'url':'https://new-business.it/contatti'}
   raise AssertionError('Non consumare un’altra query a sessione piena')
  with patch.object(EngineManager,'candidates',side_effect=results) as search,patch.object(EngineManager,'audit',return_value=(fresh,parse_page(fresh),report)) as audit:
   EngineManager(self.s).run(['D'],[])
  search.assert_called_once();self.assertEqual(audit.call_args.args[0],'https://new-business.it/')
  self.assertTrue(audit.call_args.kwargs['direct_only'])
 def test_technical_search_skips_recent_audits_and_keeps_new_businesses(self):
  self.opportunity();self.s.configure({'technical_limit':1})
  with self.s.connect() as c:c.execute('INSERT INTO audits VALUES (?,?,?)',(self.s.list()[0]['company_id'],'{}',now()))
  candidates=[{'url':'https://studio.it/news'},{'url':'https://new-business.it/'}]
  with patch.object(EngineManager,'candidates',return_value=iter(candidates)),patch.object(EngineManager,'audit',side_effect=ValueError('Stop controllo')) as audit:
   EngineManager(self.s).run(['D'],[])
  self.assertEqual(audit.call_count,1);self.assertEqual(audit.call_args.args[0],'https://new-business.it/')
 def test_agency_is_skipped_before_lighthouse_for_automatic_discovery(self):
  from sales.engines import CandidateRejected
  with patch.object(PublicWeb,'get',return_value=page('<title>Acme web agency</title><p>Siamo una web agency.</p>')),patch('sales.engines.subprocess.Popen') as launch:
   with self.assertRaises(CandidateRejected):EngineManager(self.s).audit('https://studio.it/',PublicWeb(self.s),direct_only=True)
   launch.assert_not_called()
 def test_default_run_prioritizes_direct_discovery_then_agencies(self):
  order=[]
  with patch.object(EngineManager,'technical_engine',side_effect=lambda *args:order.append('D')),patch.object(EngineManager,'discovery',side_effect=lambda engine,*args:order.append(engine)),patch.object(EngineManager,'combine',side_effect=lambda *args:order.append('E')):
   EngineManager(self.s).run(['A','B','C','D','E'])
  self.assertEqual(order,['D','A','C','B','E'])
 def test_dismissed_companies_do_not_consume_lighthouse_candidate_slots(self):
  self.opportunity()
  cid=self.s.company('https://deleted.example/','Eliminata')
  ident=self.s.prospect(cid,'D','Audit','SEO',20,{},'Misura','Ipotesi',[],[])[0]
  self.s.set_dismissed(ident);self.s.configure({'technical_limit':1})
  with patch.object(EngineManager,'candidates',return_value=iter([])), patch.object(EngineManager,'audit',side_effect=ValueError('Fine verifica selezione candidati')) as audit:
   EngineManager(self.s).run(['D'],[])
  self.assertEqual(audit.call_count,1)
  self.assertEqual(audit.call_args.args[0],'https://studio.it/')
 def test_dismissal_checked_again_when_saving_research_result(self):
  a=self.opportunity();self.s.set_dismissed(a)
  with patch.object(self.s,'target_exclusion',return_value=None):
   with self.assertRaisesRegex(ValueError,'eliminata'):self.opportunity('D','measurement','Nuova misura')
  self.assertEqual(len(self.s.list()),1)
 def test_restore_keeps_independent_target_exclusions(self):
  a=self.opportunity();self.s.set_dismissed(a)
  self.s.exclude_target('https://studio.it',{'reason':'S.p.A. verificata','url':'https://studio.it','checked_at':now(),'code':'spa'})
  self.s.set_dismissed(a,False)
  self.assertIsNone(self.s.company_detail(a)['dismissed_at'])
  self.assertEqual(self.s.target_exclusion('https://studio.it')['code'],'spa')
 def test_restore_allows_new_results_again(self):
  a=self.opportunity();self.s.set_dismissed(a);self.s.set_dismissed(a,False)
  self.assertIsNone(self.s.target_exclusion('https://studio.it'))
  self.opportunity('D','measurement','LCP 8s',url='https://studio.it/')
  self.assertEqual(len(self.s.company_list()),1)
  self.assertIsNone(self.s.company_list()[0]['dismissed_at'])
 def test_dedup_and_notes_survive_refresh(self):
  p=self.opportunity();self.s.update(p,{'notes':'Nota importante','stage':'ready'});q=self.opportunity();self.assertEqual(p,q);self.assertEqual(self.s.detail(q)['notes'],'Nota importante');self.assertEqual(len(self.s.list()),1)
 def test_cache_date_kept_as_actual_read_date(self):
  p=self.opportunity();self.assertEqual(self.s.detail(p)['evidence'][0]['checked_at'],'2026-01-01T00:00:00+00:00')
 def test_e_does_not_duplicate_same_quote(self):
  self.opportunity('A');self.opportunity('B');stats=self.stats();EngineManager(self.s).combine(self.runid('E'),stats)
  self.assertEqual(stats['added'],0)
 def test_relocation_cannot_be_promoted_by_lighthouse(self):
  self.opportunity('C','signal','Studio ha cambiato sede e recapito telefonico!',url='https://studio.it/news')
  self.opportunity('D','measurement','Lighthouse LCP 8s',url='https://studio.it/')
  stats=self.stats();EngineManager(self.s).combine(self.runid('E'),stats)
  self.assertEqual(stats['added'],0)
  self.assertEqual([r['engine'] for r in self.s.company_list()],['D'])
 def test_saved_relocation_is_requalified_without_losing_audit_or_notes(self):
  c=self.opportunity('C','signal','Studio ha cambiato sede e recapito telefonico!',url='https://studio.it/news')
  d=self.opportunity('D','measurement','Lighthouse LCP 8s',url='https://studio.it/')
  company=self.s.detail(c)['company_id']
  ids=[e['id'] for e in self.s.evidences(company)]
  e=self.s.prospect(company,'E','Combinazione','Sito',70,{},'Cambio sede + Lighthouse','Ipotesi',[],ids)[0]
  self.s.update(c,{'notes':'Nota da conservare'})
  self.assertEqual(set(self.s.requalify_growth()),{c,e})
  self.assertEqual(self.s.requalify_growth(),[])
  card=self.s.company_detail(c)
  self.assertEqual(card['id'],d)
  self.assertEqual(card['matched_engines'],['D'])
  self.assertTrue(all(ev['kind']!='signal' for ev in card['evidence']))
  self.assertEqual(self.s.detail(c)['notes'],'Nota da conservare')
  self.assertTrue(any(r['notes']=='Nota da conservare' for r in card['previous_records']))
 def test_existing_contact_on_a_later_duplicate_is_not_reset(self):
  self.opportunity('A')
  later=self.opportunity('D','measurement','Lighthouse LCP 8s',url='https://studio.it/')
  self.s.update(later,{'stage':'contacted','notes':'Contattato dalla seconda scheda'})
  card=self.s.company_list()[0]
  self.assertEqual(card['id'],later);self.assertEqual(card['stage'],'contacted')
  self.assertEqual(card['notes'],'Contattato dalla seconda scheda')
 def test_one_company_card_has_all_sources_and_one_workflow(self):
  a=self.opportunity('A')
  d=self.opportunity('D','measurement','Lighthouse LCP 8s',url='https://studio.it/')
  EngineManager(self.s).combine(self.runid('E'),self.stats())
  cards=self.s.company_list();self.assertEqual(len(cards),1)
  self.assertEqual(cards[0]['id'],a)
  self.assertEqual(cards[0]['matched_engines'],['A','D','E'])
  self.assertEqual(len(cards[0]['evidence']),2)
  self.s.update_company(d,{'stage':'contacted','notes':'Ho scritto'})
  card=self.s.company_detail(d)
  self.assertEqual(card['id'],a);self.assertEqual(card['stage'],'contacted')
  self.assertTrue(card['contacted_at']);self.assertEqual(card['notes'],'Ho scritto')
  EngineManager(self.s).combine(self.runid('E'),self.stats())
  self.assertEqual(self.s.company_list()[0]['stage'],'contacted')
  self.assertEqual(sum(r['contacted'] for r in self.s.stats()['engines']),1)
  self.s.update_company(d,{'stage':'discarded'})
  self.assertEqual(self.s.company_list()[0]['stage'],'discarded')

 def test_e_combines_independent_measurement(self):
  self.opportunity('C','signal','Abbiamo aperto una nuova sede. Vogliamo realizzare un nuovo sito web.',url='https://studio.it/news')
  self.opportunity('D','measurement','Lighthouse LCP 8s',url='https://studio.it/')
  stats=self.stats();EngineManager(self.s).combine(self.runid('E'),stats)
  e=next(i for i in self.s.list() if i['engine']=='E');self.assertEqual(len(e['evidence']),2);self.assertEqual(stats['added'],1)
 def test_no_funnel_events_invented(self):
  p=self.opportunity();self.s.update(p,{'stage':'won','contract_value':2000,'paid_value':500})
  st=self.s.stats()['engines'][0];self.assertEqual(st['customers'],1);self.assertEqual(st['contacted'],0);self.assertEqual(st['replied'],0);self.assertEqual(st['proposals'],0);self.assertIsNone(st['reply_rate']);self.assertEqual(st['revenue'],500)
 def test_invalid_values_and_transaction_rollback(self):
  p=self.opportunity()
  for data in [{'stage':'won'},{'paid_value':float('nan')},{'stage':'contacted','interaction':['bad']},{'contact_basis':'public_email'}]:
   with self.assertRaises(ValueError):self.s.update(p,data)
  self.assertEqual(self.s.detail(p)['stage'],'review')
 def test_atomic_quota_no_overrun(self):
  self.s.configure({'daily_api_limit':3});errors=[]
  def reserve():
   try:self.s.reserve()
   except ValueError:errors.append(1)
  ts=[threading.Thread(target=reserve) for _ in range(8)]
  for t in ts:t.start()
  for t in ts:t.join()
  self.assertEqual(self.s.usage()['today']['tavily'],3);self.assertEqual(len(errors),5)
 def test_cache_empty_is_a_cache_hit(self):
  self.s.cache_set('empty',[]);self.assertEqual(self.s.cache_get('empty'),[])
 def test_draft_cites_fact_no_budget_invented(self):
  item=self.s.detail(self.opportunity());d=communication(item,self.s.settings());self.assertIn(item['evidence'][0]['url'],d['email']);self.assertIn('Non stimabile',d['proposal']);self.assertNotIn('aumentare le vendite',d['email'])
 def test_advisor_fallback_and_invalid_model_ids(self):
  from contextlib import nullcontext
  item=self.s.detail(self.opportunity());d=local_advice(item,self.s.settings());self.assertEqual(d['ai_status'],'non_configurata')
  with patch('sales.advisor.heavy_slot',return_value=nullcontext()),patch('sales.advisor.api_json',return_value={'message':{'content':'{"evidence_order":[99999],"question_indices":[1]}'}}):
   self.assertEqual(local_advice(item,{**self.s.settings(),'ollama_model':'test'})['ai_status'],'unavailable')
 def test_manual_engine_a_and_b_real_pipeline(self):
  html='<meta property="article:published_time" content="'+TODAY+'"><p>Cerchiamo sviluppatore WordPress freelance a progetto.</p>'
  with patch.object(PublicWeb,'get',return_value=page(html)):
   EngineManager(self.s).run(['A','B'],['https://studio.it/collabora'])
  self.assertEqual(len(self.s.list()),1);self.assertEqual(self.s.list()[0]['matched_engines'],['A','B'])
 def test_c_independent_presence_check(self):
  html='<meta property="article:published_time" content="'+TODAY+'"><p>Abbiamo aperto una nuova sede a Padova. Vogliamo realizzare un nuovo sito web.</p>'
  with patch.object(PublicWeb,'get',side_effect=[page(html),page('<title>Studio sito ufficiale</title>','https://studio.it/')]):
   EngineManager(self.s).run(['C'],['https://studio.it/news'])
  item=self.s.list()[0];self.assertEqual(item['engine'],'C');self.assertEqual(item['source_count'],2);self.assertFalse(item['explicit'])
 def test_d_missing_test_does_not_invent_scores(self):
  report={'pagespeed':[{'status':'unavailable'}],'observations':[{'kind':'fact','label':'Moduli','detail':'0 moduli'}],'limitations':['Lighthouse non disponibile']}
  p=page('<title>Studio</title>');parsedp=parse_page(p)
  with patch.object(EngineManager,'audit',return_value=(p,parsedp,report)):
   EngineManager(self.s).run(['D'],['https://studio.it/'])
  self.assertEqual(self.s.list(),[])
  with self.s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM audits').fetchone()[0],1)
 def test_stop_is_persisted(self):
  manager=EngineManager(self.s)
  def stop(*args,**kwargs):manager.stop_event.set();raise InterruptedError()
  with patch.object(PublicWeb,'get',side_effect=stop):manager.run(['A'],['https://studio.it/'])
  self.assertEqual(self.s.history()[0]['status'],'stopped');self.assertFalse(manager.state()['running'])
 def test_legacy_migration_keeps_original_and_budget(self):
  old=Path(self.temp.name)/'old.db'
  with closing(sqlite3.connect(old)) as c, c:
   c.executescript('CREATE TABLE leads(id INTEGER PRIMARY KEY,domain TEXT,status TEXT);CREATE TABLE search_usage(day TEXT, requests INTEGER);')
   c.execute('INSERT INTO leads VALUES (1,?,?)',('studio.it','sent'));c.execute('INSERT INTO search_usage VALUES (?,7)',(TODAY,))
  before=old.read_bytes();self.s.migrate_legacy(old);self.s.migrate_legacy(old)
  self.assertEqual(old.read_bytes(),before);self.assertEqual(len(self.s.legacy()),1);self.assertEqual(self.s.usage()['today']['tavily'],7)
  self.opportunity();self.assertTrue(self.s.list()[0]['prior_contacted'])
class Boundaries(unittest.TestCase):
 def test_identical_request_same_priority_across_a_b(self):
  signal={'kind':'request','date':TODAY,'skills':['WordPress'],'contacts':[]}
  self.assertEqual(qualify('A',signal),qualify('B',signal))
 def test_priority_caps(self):
  self.assertLessEqual(qualify('D',{'skills':['Frontend']*10},technical_count=10)[0],35)
  self.assertLessEqual(qualify('A',{'kind':'request','skills':['WordPress']*10})[0],49)
 def test_url_constraints(self):
  for url in ['file:///etc/passwd','http://user:pass@example.com','http://example.com:8080']:
   with self.assertRaises(ValueError):canonical(url)
  self.assertEqual(canonical('https://example.org/a?utm_source=x&b=1#here'),'https://example.org/a?b=1')
  self.assertTrue(blocked('https://it.linkedin.com/jobs'));self.assertTrue(blocked('https://freelancer.co.uk/job'))
 def test_private_network_blocked_before_request(self):
  with patch('sales.providers.socket.getaddrinfo',return_value=[(None,None,None,None,('127.0.0.1',80))]):
   with self.assertRaisesRegex(ValueError,'reti private'):PublicWeb(None)._raw('http://example.com',policy=False)
 def test_robots_blocks(self):
  web=PublicWeb(None)
  with patch.object(web,'_raw',return_value=page('User-agent: *\nDisallow: /')):
   with self.assertRaisesRegex(ValueError,'robots.txt'):web.policy('https://example.com/private')
 def test_rss_and_xxe(self):
  class Web:
   def get(self,url):return page('<rss><channel><item><title>Nuova sede</title><link>https://studio.it/news</link><pubDate>Today</pubDate></item></channel></rss>')
  self.assertEqual(RSS(Web()).entries('https://studio.it/feed')[0]['url'],'https://studio.it/news')
  with patch.object(Web,'get',return_value=page('<!DOCTYPE rss><rss/>')):
   with self.assertRaises(ValueError):RSS(Web()).entries('https://studio.it/feed')
if __name__=='__main__':unittest.main()
