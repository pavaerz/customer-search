import unittest
import test_company_research as fixtures
from sales.research_analysis import identity_from
from sales.research_rules import region_of


class IdentityFormatTests(unittest.TestCase):
    setUp=fixtures.CompanyResearchTests.setUp
    tearDown=fixtures.CompanyResearchTests.tearDown
    page=fixtures.CompanyResearchTests.page
    check=fixtures.CompanyResearchTests.check
    def test_province_in_business_title_is_not_public_body(self):
        result=self.check(self.page(title='Alfa Impianti - Impianti elettrici a Torino e in provincia'))
        self.assertTrue(result['details']['company_ready'])
        self.assertNotEqual(result['state'],'rejected')

    def test_real_institution_remains_a_source(self):
        for title in ('Provincia di Padova', 'Comune di Padova', 'Regione Veneto'):
            with self.subTest(title=title):
                result=self.check(self.page(title=title))
                self.assertFalse(result['details'].get('company_ready'))
                self.assertTrue(result['details'].get('publisher'))

    def test_printed_vat_variants_link_identity(self):
        for label in ('Part. IVA IT ', 'p. i.v.a. ', 'P.I.V.A. ', 'P IVA: ', 'Partita IVA: '):
            with self.subTest(label=label):
                page=self.page()
                page['html']=page['html'].replace('P.IVA 12345678901',label+'12345678901')
                # A company with an external business email still has a literal
                # legal ID and address; don't require a domain email as well.
                page['html']=page['html'].replace('info@alfa.example','alfa@example.net')
                identity=identity_from([page])
                self.assertEqual(identity['legal_id'],'IT12345678901')
                self.assertEqual(identity['identity_status'],'verified')

    def test_unlabelled_tax_number_is_not_assigned_as_vat(self):
        page=self.page()
        page['html']=page['html'].replace('P.IVA 12345678901','Ordine 12345678901')
        self.assertIsNone(identity_from([page])['legal_id'])

    def test_province_before_tax_label_and_typographic_separators(self):
        for dash in ('-', '–', '—'):
            text=f'Via Vittorio Veneto 12/L 35020 {dash} Legnaro {dash} PD C.Fisc. P.iva e Reg.Imprese 04426930287'
            self.assertEqual(region_of(text),'Veneto')
        self.assertIsNone(region_of('Via Padova 12/L - codice PD C.Fisc. 04426930287'))
        self.assertIsNone(region_of('Via Roma 2, 35020 Legnaro - XX C.Fisc. 04426930287'))
