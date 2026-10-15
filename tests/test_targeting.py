import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store,now
from sales.targeting import exclusion
from sales.engines import EngineManager
from sales.providers import PublicWeb

def page(body,name='Acme'):
 return {'url':'https://acme.it/','html':f'<title>{name}</title><meta property="og:site_name" content="{name}">'+body,'checked_at':now(),'status':200}

class TargetRules(unittest.TestCase):
 def test_spa_legal_footer_variants(self):
  for form in ['S.p.A.','S. P. A.','SpA','SPA','spa','Società per azioni']:
   self.assertEqual(exclusion(page(f'<footer>Acme {form}<br>P.IVA 12345678901</footer>'))['code'],'legal_spa',form)
 def test_own_legal_name_distinct_brand(self):
  p=page('<script type="application/ld+json">{"@type":"Organization","url":"https://acme.it/","legalName":"Altra Ragione Sociale SPA"}</script>')
  self.assertEqual(exclusion(p)['code'],'legal_spa')
 def test_marketing_suffix_requires_exact_legal_base_on_own_page(self):
  p={'url':'https://alfasolutions.example/it/chi-siamo','html':'<title>Chi siamo</title><p>Il sistema qualità di ALFA S.P.A. è certificato.</p>','checked_at':now(),'status':200}
  self.assertEqual(exclusion(p)['code'],'legal_spa')
  for html in ['<p>Il sistema qualità di ALFABET S.P.A. è certificato.</p>', '<p>Cliente: ALFA S.P.A.</p>','<p>Website by ALFA S.P.A.</p>']:
   self.assertIsNone(exclusion({**p,'html':html}))
  self.assertIsNone(exclusion({**p,'url':'https://alfasolutions.example/news/alfa'}))
 def test_spa_wellness_not_legal_form(self):
  self.assertIsNone(exclusion(page('<p>La nostra spa offre massaggi e percorsi benessere.</p>','Oasi SPA')))
  self.assertIsNone(exclusion(page('<footer>Oasi Spa S.r.l. — P.IVA 12345678901</footer>','Oasi Spa')))
 def test_customer_and_web_author_not_owner(self):
  for text in ['Clienti: Acme S.p.A.','Website by Acme S.p.A.','Partner Acme S.p.A.']:
   self.assertIsNone(exclusion(page('<footer>'+text+'</footer>')))
 def test_large_chain_own_statement(self):
  p=page('<p>Con 19 sedi nel nord Italia siamo sempre vicini alle persone.</p>')
  self.assertEqual(exclusion(p)['code'],'large_company')
 def test_large_chain_can_mention_its_customers(self):
  self.assertEqual(exclusion(page('<p>Con 19 sedi siamo sempre vicini ai clienti.</p>'))['code'],'large_company')
 def test_staff_threshold(self):
  self.assertEqual(exclusion(page('<p>Abbiamo 350 dipendenti in Italia.</p>'))['code'],'large_company')
  self.assertIsNone(exclusion(page('<p>Abbiamo 12 dipendenti e due showroom.</p>')))
 def test_agency_serving_large_customers_retained(self):
  self.assertIsNone(exclusion(page('<p>Aiutiamo i nostri clienti con 150 sedi a gestire i siti web.</p>')))
 def test_polished_site_and_small_expansion_not_size_evidence(self):
  self.assertIsNone(exclusion(page('<p>Abbiamo aperto il nostro secondo showroom.</p>'+''.join(f'<a href="/p/{i}">Prodotto</a>' for i in range(200)))))

class TargetPersistence(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'sales.db');self.store.init()
  self.cid=self.store.company('https://acme.it/','Acme')
  self.sid=self.store.source({'url':'https://acme.it/','checked_at':now()},self.cid)
 def tearDown(self):self.tmp.cleanup()
 def opportunity(self,engine):
  eid=self.store.add_evidence(self.cid,self.sid,engine,'signal' if engine=='C' else 'measurement',engine,'Riscontro')
  return self.store.prospect(self.cid,engine,'Titolo','Sito',50,{},'Motivo','Ipotesi',[],[eid])[0]
 def exclude(self):self.store.exclude_target('https://www.acme.it/news',exclusion(page('<footer>Acme S.p.A.</footer>')))
 def test_archives_all_engines_and_keeps_history(self):
  ids=[self.opportunity(e) for e in ['C','D','E']];self.exclude()
  for ident in ids:
   detail=self.store.detail(ident);self.assertEqual(detail['stage'],'discarded');self.assertIn('S.p.A.',detail['target_exclusion']['reason']);self.assertTrue(detail['evidence']);self.assertTrue(detail['interactions'])
  self.exclude();self.assertEqual(len(self.store.detail(ids[0])['interactions']),1)
 def test_new_prospect_and_combined_cannot_revive(self):
  self.opportunity('C');self.opportunity('D');self.exclude()
  with self.assertRaises(ValueError):self.opportunity('E')
  EngineManager(self.store).run(['E'])
  self.assertFalse(any(i['engine']=='E' for i in self.store.list()))
 def test_won_value_and_stage_preserved(self):
  ident=self.opportunity('C');self.store.update(ident,{'stage':'won','contract_value':2500,'paid_value':1000});self.exclude()
  detail=self.store.detail(ident);self.assertEqual(detail['stage'],'won');self.assertEqual(detail['paid_value'],1000);self.assertTrue(detail['target_exclusion'])
 def test_spa_in_homepage_excludes_explicit_request(self):
  request=page('<p>Cerchiamo sviluppatore WordPress freelance.</p>');request['url']='https://acme.it/careers'
  with patch.object(PublicWeb,'get',side_effect=[request,page('<footer>Acme S.p.A.</footer>')]):
   EngineManager(self.store).run(['A'],[request['url']])
  self.assertEqual(self.store.list(),[]);self.assertTrue(self.store.target_exclusion(request['url']))
 def test_technical_test_not_started_for_excluded_target(self):
  self.exclude()
  with patch.object(EngineManager,'audit') as audit:EngineManager(self.store).run(['D'],['https://acme.it/'])
  audit.assert_not_called()
