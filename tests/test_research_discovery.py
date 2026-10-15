import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store,now,digest
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.research_discovery import search,inspect_source
from sales.research_analysis import identity_from,ResearchWeb
from sales.research_rules import qualify,validate_signals
from sales.safe_proxy import public_addresses
from test_research import sample

class DiscoveryTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.db');self.store.init();self.rs=ResearchStore(self.store);self.c=self.rs.create()
 def tearDown(self):self.tmp.cleanup()
 def test_search_pages_and_no_repeat(self):
  task={'strategy':'change','payload':{'query':'nuova linea prodotti Veneto','page':1,'period':'year'}}
  result={'results':[{'url':'https://alfa.example/evento','engines':['brave']}],'unresponsive_engines':[]}
  with patch('sales.discovery_control.search_capabilities',return_value={'paging':True,'time_range':True}),patch.dict('os.environ',{'SEARXNG_URL':'http://127.0.0.1:8888'}),patch('sales.research_discovery.api_json',return_value=result),patch('sales.research_discovery._last_search',0):
   search(self.rs,self.c,task,lambda:None);search(self.rs,self.c,task,lambda:None)
  with self.store.connect() as c:
   rows=c.execute('SELECT kind,payload FROM discovery_frontier').fetchall()
  self.assertEqual(len(rows),1);self.assertFalse(any(json.loads(r['payload']).get('page')==2 for r in rows))
 def test_rss_independent_of_search(self):
  page={'url':'https://territorio.example/feed','status':200,'checked_at':now(),'html':'<?xml version="1.0"?><rss><channel><item><title>Nuova impresa</title><link>https://territorio.example/notizia</link></item></channel></rss>'}
  with patch.object(ResearchWeb,'get',return_value=page),patch('sales.research_discovery.api_json',side_effect=AssertionError('SearXNG must not be used')):
   inspect_source(self.rs,self.c,{'payload':{'url':page['url'],'kind':'rss'}},lambda:None)
  with self.store.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM discovery_frontier WHERE kind='candidate'").fetchone()[0],0)
 def test_feed_entities_forbidden(self):
  page={'url':'https://territorio.example/feed','status':200,'checked_at':now(),'html':'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><rss>&xxe;</rss>'}
  with patch.object(ResearchWeb,'get',return_value=page),self.assertRaisesRegex(ValueError,'entità'):
   inspect_source(self.rs,self.c,{'payload':{'url':page['url'],'kind':'rss'}},lambda:None)
 def test_identity_multiline_address(self):
  page={'url':'https://alfa.example/','status':200,'checked_at':now(),'html':'<title>Alfa Srl</title><footer><p>Alfa Srl</p><p>Via Roma 2</p><p>35100 Padova (PD)</p><p>P.IVA 12345678901</p><a href="mailto:info@alfa.example">info@alfa.example</a></footer>'}
  i=identity_from([page]);self.assertEqual(i['identity_status'],'verified');self.assertEqual(i['region'],'Veneto');self.assertTrue(i['contacts'])
 def test_postcode_and_city_on_separate_lines_combined_vat_label(self):
  page={'url':'https://alfa.example/','status':200,'checked_at':now(),'html':'<title>Alfa Srl</title><footer><p>Via Tremarende 22, 35010</p><p>Santa Giustina in Colle (PD)</p><p>Italy</p><p>P.iva/Cod. Fisc. 12345678901</p><p>info@alfa.example</p><p>Designer: info@vendor.example</p></footer>'}
  i=identity_from([page]);self.assertEqual(i['identity_status'],'verified');self.assertEqual(i['region'],'Veneto');self.assertEqual(i['legal_id'],'IT12345678901')
  self.assertIn('Santa Giustina in Colle (PD)',i['location'])
  self.assertEqual([c['value'] for c in i['contacts'] if c['type']=='email'],['info@alfa.example'])
 def test_postcode_does_not_borrow_an_unrelated_later_province(self):
  page={'url':'https://alfa.example/','status':200,'checked_at':now(),'html':'<title>Alfa Srl</title><footer><p>Via Roma 22, 35010</p><p>I nostri clienti</p><p>Torino (TO)</p><p>P.IVA 12345678901</p></footer>'}
  self.assertIsNone(identity_from([page])['region'])
 def test_ipv4_and_ipv6_private_denied(self):
  for ip in ('127.0.0.1','10.0.0.2','169.254.169.254','::1','fc00::1'):
   with patch('socket.getaddrinfo',return_value=[(None,None,None,None,(ip,443))]),self.assertRaisesRegex(ValueError,'privata'):public_addresses('site.example',443)
 def test_mixed_dns_not_public(self):
  with patch('socket.getaddrinfo',return_value=[(None,None,None,None,('8.8.8.8',443)),(None,None,None,None,('127.0.0.1',443))]),self.assertRaises(ValueError):public_addresses('site.example',443)
 def test_email_orders_and_technical_gaps_not_full_projects(self):
  for kind,quote in [('process','Gli ordini vanno inviati per email al nostro ufficio commerciale.'),('gap','Il punteggio Lighthouse del sito è basso e la SEO è insufficiente.')]:
   args=sample();args[2][0].update(kind='business',quote='Produciamo e distribuiamo arredamenti in tutta Europa.')
   second={**args[2][0],'id':'second','kind':kind,'quote':quote,'event_key':'second'};args[2].append(second);args[3]['support_ids'].append('second');args[4]['support_ids'].append('second')
   self.assertNotEqual(qualify(*args)['status'],'qualified')
 def test_implicit_need_can_qualify_without_website_request(self):
  args=sample();args[2][0].update(kind='event',quote='La nuova rete commerciale B2B è ora presente in Germania e Francia.')
  second={**args[2][0],'id':'second','kind':'gap','quote':'La piattaforma attuale non permette ai distributori di gestire gli ordini multilistino e le varianti configurabili.','event_key':'second'}
  args[2].append(second);args[3]['support_ids'].append('second');args[4]['support_ids'].append('second')
  self.assertEqual(qualify(*args)['status'],'qualified')
 def test_different_quotes_from_syndicated_article(self):
  text='Alfa presenta una nuova linea di prodotti dedicata agli artigiani. '+ 'La nuova sede sarà inaugurata a Padova nel mese di ottobre.'
  docs=[{'id':str(n),'text':text,'url':f'https://editore{n}.example/news','checked_at':now()} for n in range(2)]
  claims=[{'document_id':'0','kind':'event','quote':text.split('. ')[0]+'.'},{'document_id':'1','kind':'event','quote':text.split('. ')[1]}]
  signals,invalid=validate_signals(claims,docs);self.assertEqual(invalid,[])
  self.assertEqual(len(signals),2)  # Preserve both facts, count one copied origin.
  self.assertEqual(len({s['event_key'] for s in signals}),1)

 def test_official_link_to_external_shop_is_examined(self):
  from sales.research_analysis import inspect_candidate,LocalResearcher
  footer='<footer><p>Alfa Srl</p><p>Via Roma 2, 35100 Padova (PD)</p><p>P.IVA 12345678901</p><a href="mailto:info@alfa.example">info@alfa.example</a></footer>'
  pages={
   'https://alfa.example/':'<title>Alfa Srl</title><p>Prodotti per la casa</p><a href="/contatti">Contatti</a><a href="https://shop-esterno.example/">Shop online</a>'+footer,
   'https://alfa.example/contatti':'<title>Contatti Alfa</title>'+footer,
   'https://shop-esterno.example/':'<title>Negozio Alfa</title><p>Il nostro shop è ora online e puoi acquistare tutti i prodotti.</p>'}
  fetched=[]
  def get(web,url):
   fetched.append(url);return {'url':url,'html':pages[url],'status':200,'checked_at':now()}
  def analyze(model,identity,docs,coverage):
   external=next(d for d in docs if 'shop-esterno' in d['url'])
   signals,_=validate_signals([{'document_id':external['id'],'kind':'counterevidence','quote':'Il nostro shop è ora online e puoi acquistare tutti i prodotti.'}],docs)
   return signals,{}, {'status':'contradicted','reason':'Shop già disponibile'},[]
  with patch.object(ResearchWeb,'get',get),patch.object(LocalResearcher,'analyze',analyze):
   result=inspect_candidate(self.store,{'url':'https://alfa.example/','strategy':'gap'},lambda:None)
  self.assertIn('https://shop-esterno.example/',fetched);self.assertEqual(result['assessment']['status'],'rejected')

 def test_interrupted_seeding_resumes_idempotently(self):
  from sales.research_discovery import seed_campaign
  from sales.discovery_planner import Planner
  original=Planner.offer_query;calls=[]
  def interrupted(*args,**kwargs):
   calls.append(args)
   if len(calls)>2:raise InterruptedError('Stop durante preparazione')
   return original(*args,**kwargs)
  with patch.object(Planner,'offer_query',autospec=True,side_effect=interrupted),self.assertRaises(InterruptedError):seed_campaign(self.rs,self.c)
  seed_campaign(self.rs,self.c)
  with self.store.connect() as c:before=c.execute('SELECT count(*) FROM discovery_frontier').fetchone()[0]
  self.assertLessEqual(before,20)
  seed_campaign(self.rs,self.c)
  with self.store.connect() as c:self.assertEqual(before,c.execute('SELECT count(*) FROM discovery_frontier').fetchone()[0])
