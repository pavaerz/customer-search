import unittest,tempfile,json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from sales.grant_eligibility import compare,evaluate,validate_rule,explicit_exclusions,GrantAnalyst,rule_key
from sales.grants import DEFAULT,profile,state,answer_requirements
from sales.grant_documents import collect
from sales.db import Store,now,encode

TODAY=date(2026,10,13)
def doc(text='Sono ammesse le ditte individuali con sede in Veneto.\nStato incentivo o strumento\nAttivo'):
 return {'id':'d1','url':'https://www.invitalia.it/incentivi-e-strumenti/test','title':'Bando test','text':text,'checked_at':'2026-10-13T08:00:00+00:00'}
def rule(**kw):return {'label':'Sede in Veneto','field':'region','operator':'in','values':['Veneto'],'quote':'Sono ammesse le ditte individuali con sede in Veneto.','document_id':'d1','question':'In quale regione ha sede l’attività?',**kw}
def bundle(r=None,d=None,**kw):return {'documents':[d or doc()],'rules':[r or rule()],'complete':True,'limitations':[],**kw}

class EligibilityTests(unittest.TestCase):
 def test_freshness_uses_italian_day_across_utc_midnight(self):
  d=doc();d['checked_at']='2026-10-12T22:30:00+00:00'
  self.assertEqual(evaluate(bundle(d=d),DEFAULT,TODAY)['status'],'compatible')
  d['checked_at']='2026-10-12T19:00:00+00:00'
  self.assertNotEqual(evaluate(bundle(d=d),DEFAULT,TODAY)['status'],'compatible')
 def test_compatible_only_complete(self):
  self.assertEqual(evaluate(bundle(),DEFAULT,TODAY)['status'],'compatible')
  for b in (bundle(complete=False),bundle(limitations=['Allegato non letto']),bundle(rules=[])):
   self.assertNotEqual(evaluate(b,DEFAULT,TODAY)['status'],'compatible')
 def test_unknown_profile_is_question_not_positive(self):
  r=rule(field='legal_form',values=['sole_trader'],question='Qual è la tua forma giuridica?')
  ev=evaluate(bundle(r),DEFAULT,TODAY);self.assertEqual(ev['status'],'needs_data');self.assertEqual(ev['questions'][0]['field'],'legal_form')
 def test_excluded_profile(self):
  ev=evaluate(bundle(),{**DEFAULT,'region':'Lazio'},TODAY);self.assertEqual(ev['status'],'excluded');self.assertEqual(ev['checks'][-1]['result'],'fail')
 def test_citation_cannot_be_invented(self):
  r=rule(quote='È ammessa ogni persona senza alcun requisito.')
  self.assertFalse(validate_rule(r,[doc()]));self.assertNotEqual(evaluate(bundle(r),DEFAULT,TODAY)['status'],'compatible')
 def test_closed_and_conflicting_dates(self):
  self.assertEqual(evaluate(bundle(d=doc('Stato incentivo o strumento\nChiuso'),rules=[]),DEFAULT,TODAY)['status'],'excluded')
  d=doc(doc()['text']+'\nScadenza: 01/01/2020')
  self.assertEqual(evaluate(bundle(d=d),DEFAULT,TODAY)['status'],'source_incomplete')
 def test_old_check_cannot_produce_positive_or_exclusion(self):
  d=doc();d['checked_at']='2025-01-01T00:00:00Z'
  self.assertNotEqual(evaluate(bundle(d=d),DEFAULT,TODAY)['status'],'compatible')
  self.assertNotEqual(evaluate(bundle(d=d),{**DEFAULT,'region':'Lazio'},TODAY)['status'],'excluded')
 def test_missing_status_prevents_positive(self):
  d=doc('Sono ammesse le ditte individuali con sede in Veneto.')
  self.assertEqual(evaluate(bundle(d=d),DEFAULT,TODAY)['status'],'source_incomplete')
 def test_age_and_formation_dates(self):
  r=rule(field='birth_date',operator='age_max',values=['35'])
  self.assertEqual(compare(r,{'birth_date':'1990-10-14'},TODAY)[0],'pass')
  self.assertEqual(compare(r,{'birth_date':'1990-10-13'},TODAY)[0],'fail')
  r=rule(field='started_on',operator='months_max',values=['12'])
  self.assertEqual(compare(r,{'started_on':'2025-10-13'},TODAY)[0],'pass')
  self.assertEqual(compare(r,{'started_on':'2025-10-12'},TODAY)[0],'fail')
 def test_ateco_prefix_not_substring(self):
  r=rule(field='ateco',operator='prefix_in',values=['62'])
  self.assertEqual(compare(r,{'ateco':'62.10.00'})[0],'pass');self.assertEqual(compare(r,{'ateco':'46.62.00'})[0],'fail');self.assertEqual(compare(r,{'ateco':''})[0],'missing')
 def test_unknown_money_not_zero(self):
  r=rule(field='investment_amount',operator='min',values=['5000'])
  self.assertEqual(compare(r,{'investment_amount':''})[0],'missing');self.assertEqual(compare(r,{'investment_amount':'4999.99'})[0],'fail')
 def test_or_enum_and_unsupported_complex_rule(self):
  r=rule(field='legal_form',values=['sole_trader','professional'])
  self.assertEqual(compare(r,{'legal_form':'professional'})[0],'pass')
  r=rule(field='unsupported',operator='unsupported',values=[],label='Maggioranza di quote e soci giovani oppure donne')
  self.assertEqual(evaluate(bundle(r),DEFAULT,TODAY)['status'],'source_incomplete')
 def test_explicit_exclusion_and_exception(self):
  d=doc('Sono escluse le ditte individuali, le società semplici.');r=explicit_exclusions([d]);self.assertEqual(len(r),1)
  self.assertEqual(evaluate(bundle(d=d,rules=r,complete=False),{**DEFAULT,'legal_form':'sole_trader'},TODAY)['status'],'excluded')
  self.assertFalse(explicit_exclusions([doc('Sono escluse le ditte individuali salvo le imprese artigiane.')]))
 def test_reviewer_can_block_valid_quote_with_wrong_interpretation(self):
  with tempfile.TemporaryDirectory() as t:
   s=Store(Path(t)/'test.db');s.init();a=GrantAnalyst(s)
   with patch.object(a,'call',side_effect=[{'rules':[rule()],'complete':True,'limitations':[]},{'correct':False,'complete':False,'limitations':['La condizione ha una deroga.']}]):b=a.extract([doc()])
   self.assertEqual(b['rules'],[]);self.assertFalse(b['complete'])
 def test_data_answers_bound_to_exact_rule_and_profile_update(self):
  with tempfile.TemporaryDirectory() as t:
   s=Store(Path(t)/'test.db');s.init();d=doc('Non devono essere stati distribuiti utili.\nStato incentivo o strumento\nAttivo');d['checked_at']=now()
   r=rule(field='declaration',operator='fact',values=['yes'],quote='Non devono essere stati distribuiti utili.',question='Confermi che non sono stati distribuiti utili?')
   with s.connect() as c:
    cid=c.execute("INSERT INTO grant_runs(state,generation,profile,message,created_at,updated_at) VALUES ('completed','x',?,'',?,?)",(encode(DEFAULT),now(),now())).lastrowid
    c.execute('INSERT INTO grant_items(run_id,url,title,body,checked_at) VALUES (?,?,?,?,?)',(cid,d['url'],'Test',encode({'eligibility_bundle':bundle(r,d)}),now()))
   self.assertEqual(state(s)['items'][0]['body']['status'],'needs_data')
   answer_requirements(s,{'answers':{rule_key(r):'yes'}})
   self.assertEqual(state(s)['items'][0]['body']['status'],'compatible')
   profile(s,{'activity':'Web'});self.assertEqual(profile(s)['facts'][rule_key(r)],'yes')
   with self.assertRaises(ValueError):answer_requirements(s,{'answers':{'f'*64:'yes'}})
 def test_pdf_and_navigation_requirements_are_followed(self):
  p={'url':'https://www.invitalia.it/incentivi-e-strumenti/test','html':'<h1>Test</h1><nav><a href="/incentivi-e-strumenti/test/requisiti">Requisiti</a></nav>','checked_at':now(),'status':200}
  q={**p,'url':p['url']+'/requisiti','html':'<h1>Requisiti</h1><p>Imprese registrate.</p>'}
  class Web:
   def get(self,*a,**kw):return q
  docs,limits=collect(Web(),p);self.assertEqual(len(docs),2);self.assertFalse(limits)
 def test_answers_can_be_corrected(self):
  r=rule(field='declaration',operator='fact',values=['yes'],question='Confermi che non sono stati distribuiti utili?')
  p={**DEFAULT,'facts':{rule_key(r):'yes'}}
  self.assertEqual(evaluate(bundle(r),p,TODAY)['status'],'compatible')
  p['facts'][rule_key(r)]='no';self.assertEqual(evaluate(bundle(r),p,TODAY)['status'],'excluded')
 def test_profile_validation_facts_and_amount(self):
  with tempfile.TemporaryDirectory() as t:
   s=Store(Path(t)/'test.db');s.init();profile(s,{'tax_regime':'forfettario','legal_form':'sole_trader'});profile(s,{'ateco':'62.10.00'})
   self.assertEqual(profile(s)['tax_regime'],'forfettario')
   for body in ({'investment_amount':'NaN'},{'investment_amount':'-1'},{'birth_date':'2999-01-01'},{'facts':{'bogus':'yes'}},{'company_size':'invented'}):
    with self.assertRaises(ValueError):profile(s,body)
