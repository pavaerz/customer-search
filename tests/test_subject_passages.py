import unittest

from sales.source_identity import subject_document,verified_origins
from sales.claim_selection import grounded_units
from sales.research_rules import normalize


class SubjectPassagesTests(unittest.TestCase):
    def sample(self):
        paragraphs=['Alfa Srl presenta la nuova linea di prodotti destinata al mercato francese.',
                    'Beta Srl cerca un fornitore per un nuovo sito con budget di 9000 euro.',
                    'Alfa Srl ha aperto una rete di distributori per la nuova offerta.',
                    'La società aprirà anche un nuovo showroom.']
        return {'id':'doc','text':'\n'.join(paragraphs),'research_text':'\n'.join(paragraphs)},paragraphs

    def test_multiple_named_facts_survive_without_borrowing_other_company(self):
        doc,p=self.sample();r=subject_document(doc,'Alfa Srl',p[0])
        self.assertEqual(r['subject_passages'],[p[0],p[2]])
        self.assertNotIn('9000',r['research_text']);self.assertNotIn('showroom',r['research_text'])
        self.assertEqual(r['text'],doc['text'])

    def test_scoping_twice_does_not_shrink_to_identity_quote(self):
        doc,p=self.sample();first=subject_document(doc,'Alfa Srl',p[0])
        self.assertEqual(subject_document(first,'Alfa Srl',p[0]),first)

    def test_quote_units_remain_contiguous_in_original(self):
        doc,p=self.sample();r=subject_document(doc,'Alfa Srl',p[0])
        units=grounded_units(doc['id'],r['research_text'],doc['text'])
        self.assertEqual(len(units),2)
        self.assertTrue(all(normalize(u['text']) in normalize(doc['text']) for u in units))

    def test_quote_outside_selected_body_and_fabricated_paragraph_excluded(self):
        doc,p=self.sample();doc['text']+='\nAlfa Srl ha aperto un nuovo brand nella barra laterale.'
        self.assertIsNone(subject_document(doc,'Alfa Srl','Alfa Srl ha aperto un nuovo brand nella barra laterale.'))
        doc['research_text']+='\nAlfa Srl vuole un ecommerce non presente nella fonte.'
        r=subject_document(doc,'Alfa Srl',p[0]);self.assertNotIn('ecommerce',r['research_text'])

    def test_mixed_company_paragraph_does_not_expand_context(self):
        doc,p=self.sample();doc['text']+='\nBeta Srl ha venduto ad Alfa Srl un nuovo portale.';doc['research_text']=doc['text']
        self.assertNotIn('portale',subject_document(doc,'Alfa Srl',p[0])['research_text'])

    def test_namesakes_still_require_identity_and_location(self):
        doc,p=self.sample();payload={'subject':'Alfa Srl','subject_quote':p[0],'source_documents':[doc]}
        identity={'name':'Alfa Srl','region':'Veneto','location':'Padova'}
        origins,limits=verified_origins(payload,identity)
        self.assertFalse(origins);self.assertTrue(limits)
        origins,limits=verified_origins({**payload,'official_link':True},identity)
        self.assertEqual(len(origins[0]['subject_passages']),2);self.assertFalse(limits)
        origins,limits=verified_origins({**payload,'official_link':True},{**identity,'name':'Beta Srl'})
        self.assertFalse(origins);self.assertTrue(limits)
