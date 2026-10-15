import unittest
from company_finance import extract_vat, reported_profit, valid_vat
from ux_checks import evaluate_pair, qualifies


class UXFinanceTest(unittest.TestCase):
    def vat(self, prefix='1234567890'):
        return next(prefix+str(n) for n in range(10) if valid_vat(prefix+str(n)))

    def test_finance_requires_identity_year_and_explicit_net_profit(self):
        vat=self.vat()
        text=f'Partita IVA {vat}. Utile netto 2024: € 125.300,00'
        result=reported_profit(text,vat)
        self.assertEqual(result[0]['amount_eur'],125300)
        self.assertEqual(result[0]['year'],2024)
        self.assertEqual(reported_profit(text.replace('Utile netto','Fatturato'),vat),[])
        self.assertEqual(reported_profit(text.replace('2024',''),vat),[])
        self.assertEqual(reported_profit(text.replace(vat,'00000000000'),vat),[])
        self.assertEqual(reported_profit(f'P. IVA {vat} Utile netto 2024: euro 2 milioni',vat),[])
        self.assertEqual(reported_profit(f'P. IVA {vat} Utile netto 2024: euro 2%',vat),[])

    def test_multiple_company_identities_are_ambiguous(self):
        self.assertEqual(extract_vat(f'P. IVA {self.vat()} P. IVA {self.vat("9876543210")}'),'')

    def test_ux_requires_repeated_and_complete_evidence(self):
        good=dict(overflow=0,clipped=0,small=0,smallChars=0,blocks=3,targets=0,nav=5,samples=[])
        bad={**good,'overflow':400,'clipped':3}
        self.assertFalse(qualifies(evaluate_pair(good,good,'Mobile')))
        self.assertTrue(qualifies(evaluate_pair(bad,bad,'Mobile')))
        self.assertFalse(qualifies(evaluate_pair(bad,good,'Mobile')))
        self.assertFalse(qualifies(evaluate_pair(bad,bad,'Mobile',True)))
        tiny={**good,'small':3,'smallChars':300,'targets':4}
        self.assertFalse(qualifies(evaluate_pair(tiny,tiny,'Mobile')))
        nav={**good,'targets':4}
        self.assertFalse(qualifies(evaluate_pair(nav,nav,'Mobile')))

    def test_small_text_alone_is_not_a_selection_reason(self):
        tiny=dict(overflow=0,clipped=0,small=2,smallChars=180,blocks=2,targets=0,nav=0,samples=[])
        normal={**tiny,'small':0,'smallChars':0}
        self.assertFalse(qualifies(evaluate_pair(tiny,tiny,'Mobile')))
        self.assertFalse(qualifies(evaluate_pair(tiny,normal,'Mobile')))
        self.assertFalse(qualifies(evaluate_pair(tiny,tiny,'Mobile',True)))

    def test_moderate_overflow_requires_repeated_clipped_text(self):
        base=dict(overflow=25,clipped=1,small=0,smallChars=0,targets=0)
        self.assertTrue(qualifies(evaluate_pair(base,base,'Mobile')))
        for changed in ({'overflow':20}, {'clipped':0}):
            self.assertFalse(qualifies(evaluate_pair(base,{**base,**changed},'Mobile')))

    def test_short_small_text_does_not_select_site(self):
        base=dict(overflow=0,clipped=0,small=2,smallChars=120,targets=0)
        self.assertFalse(qualifies(evaluate_pair(base,base,'Mobile')))
        self.assertFalse(qualifies(evaluate_pair(base,{**base,'smallChars':119},'Mobile')))
