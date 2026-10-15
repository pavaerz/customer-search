import unittest
from sales.claim_selection import evidence_units,selection_schema,materialize


class ClaimSelectionTests(unittest.TestCase):
    def test_literals_offsets_accents_and_long_paragraphs(self):
        text='  È attivo il nostro portale B2B.\n'+('Una configurazione comprende molte varianti e dipendenze. '*45)+'\nIl budget del progetto è di 8.000 euro.'
        units=evidence_units('doc',text)
        self.assertGreater(len(units),3)
        for u in units:
            self.assertEqual(text[u['start']:u['end']],u['text']);self.assertLessEqual(len(u['text']),500)
        response={'claims':[{'unit_id':units[-1]['id'],'kind':'budget'}]}
        claims,errors=materialize('doc',text,units,response)
        self.assertFalse(errors);self.assertEqual(claims[0]['quote'],'Il budget del progetto è di 8.000 euro.')
        self.assertEqual(selection_schema(units)['properties']['claims']['items']['properties']['unit_id']['enum'],[u['id'] for u in units])
    def test_unknown_unit_or_generated_quote_is_rejected(self):
        text='Ordini ricevuti attraverso il portale clienti.';units=evidence_units('doc',text)
        claims,errors=materialize('doc',text,units,{'claims':[{'unit_id':'invented','kind':'gap'},{'unit_id':units[0]['id'],'kind':'gap','quote':'Il sito non funziona.'}]})
        self.assertEqual(claims,[]);self.assertEqual(len(errors),2)
    def test_document_mismatch_and_tampered_offsets(self):
        text='Il portale clienti è già operativo e completo.'
        units=evidence_units('doc',text);other=evidence_units('other',text)
        claims,errors=materialize('other',text,other,{'claims':[{'unit_id':units[0]['id'],'kind':'counterevidence'}]})
        self.assertEqual(claims,[]);self.assertTrue(errors)
        units[0]['start']=2
        self.assertTrue(materialize('doc',text,units,{'claims':[{'unit_id':units[0]['id'],'kind':'counterevidence'}]})[1])
    def test_all_long_paragraph_words_are_present_in_a_window(self):
        text=' '.join('parola'+str(n) for n in range(600))
        units=evidence_units('doc',text)
        self.assertEqual(set(text.split()),set(' '.join(u['text'] for u in units).split()))
