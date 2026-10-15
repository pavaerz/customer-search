import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sales.db import Store,now
from sales.research_store import ResearchStore
from sales.research_triage import triage
from sales.research_analysis import ResearchWeb,CompanyWeb,LocalResearcher,identity_from
from sales.company_research import research_tasks,company_verification
from sales.direct_channels import request_excerpt,route_exclusion,digital_supplier,collaboration_evidence,standing_partner_evidence
from sales.extract import parse_page
from sales.discovery_planner import searchable_query


class CommercialDemandTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.db');self.store.init();self.rs=ResearchStore(self.store)
        self.payload={'url':'https://alfa.example/lavora-con-noi/','direct_channels':True,'strategy':'partner',
            'hypothesis':{'required_evidence':'Collaborazione web'},'filters':{'regions':['Veneto'],'target':'b2b'}}

    def page(self,text,title='Alfa Srl | Agenzia web',place='35100 Padova (PD)'):
        return {'url':self.payload['url'],'status':200,'checked_at':now(),'html':f'<title>{title}</title><main><p>{text}</p></main><footer><p>Alfa Srl</p><p>Via Roma 2, {place}</p><p>P.IVA 12345678901</p><a href="mailto:info@alfa.example">info@alfa.example</a></footer>'}

    def run_triage(self,page,**changes):
        with patch.object(ResearchWeb,'get',return_value=page),patch.object(LocalResearcher,'call',side_effect=AssertionError('No heavy model')):
            return triage(self.store,{**self.payload,**changes},lambda:None)

    def test_marketing_request_words_do_not_trigger_a_buyer(self):
        text='Con ogni cliente cerchiamo di creare una collaborazione solida. Realizzazione sito web completo.'
        self.assertIsNone(request_excerpt(text))
        result=self.run_triage(self.page(text))
        self.assertEqual(result['state'],'rejected');self.assertFalse(result['details'].get('company_ready'))

    def test_real_freelance_request_survives_industrial_profile_without_fake_qualification(self):
        result=self.run_triage(self.page('Cerchiamo uno sviluppatore WordPress freelance per collaborazioni continuative con il nostro team.'))
        self.assertEqual(result['state'],'promising');d=result['details']
        self.assertTrue(d['company_ready']);self.assertEqual(d['identity']['group'],'agencies')
        self.assertIsNone(d['collaboration']['budget']);self.assertIn('freelance',d['collaboration']['quote'])
        self.assertTrue(d['identity']['contacts']);self.assertNotIn('assessment',result)
        self.assertEqual(research_tasks(self.payload,result),([],[]));self.assertIsNone(company_verification(self.payload,result))

    def test_standing_partner_is_contactable_without_inventing_open_project(self):
        text='Accettiamo collaborazioni freelance WordPress e frontend. Inviaci il portfolio per entrare nella nostra rete.'
        result=self.run_triage(self.page(text))
        self.assertEqual(result['state'],'promising')
        proof=result['details']['collaboration']
        self.assertEqual(proof['kind'],'standing_invitation')
        self.assertEqual(proof['quote'],text)
        self.assertIsNone(proof['budget']);self.assertIsNone(proof['published_at'])
        self.assertIn('nessuna commessa aperta',result['reason'])
        self.assertIsNone(company_verification(self.payload,result))
        self.assertEqual(research_tasks(self.payload,result),([],[]))
        self.assertEqual(self.run_triage(self.page(text),filters={'regions':['Lombardia']})['state'],'rejected')

    def test_generic_spontaneous_applications_do_not_prove_web_freelance_availability(self):
        for text in ('Accettiamo candidature spontanee. Siamo una web agency WordPress.',
                     'Non accettiamo collaborazioni freelance WordPress.',
                     'Se accettiamo collaborazioni freelance WordPress, cosa cambia?',
                     'Accettiamo candidature spontanee per commerciali freelance.\nWordPress Developer a tempo indeterminato.',
                     'Offro servizi WordPress freelance alle agenzie. Candidature spontanee.'):
            with self.subTest(text=text):self.assertIsNone(standing_partner_evidence(self.page(text)))

    def test_shared_invitation_with_explicit_web_skill_is_not_assumed_employee_only(self):
        text='Raccogliamo candidature spontanee per SEO e Web Developer WordPress: valutiamo collaborazioni freelance e tirocini, da concordare al colloquio.'
        result=self.run_triage(self.page(text))
        self.assertEqual(result['state'],'promising')
        self.assertEqual(result['details']['collaboration']['kind'],'standing_invitation')
        self.assertNotIn('assessment',result)

    def test_employee_closed_selfpromotion_and_footer_coincidence_do_not_pass(self):
        for text in ['Cerchiamo WordPress developer a tempo indeterminato. No freelance.',
                     'Cerco lavoro come freelance WordPress.',
                     'Cerchiamo freelance WordPress. Posizione chiusa.',
                     'Se cerchiamo sviluppatori freelance WordPress, come valutarli?',
                     'Cerchiamo di aumentare i clienti. Sviluppo siti web freelance.',
                     'Cerchiamo un magazziniere.\n\nWeb designer freelance: sito realizzato da Mario.']:
            with self.subTest(text=text):self.assertIsNone(request_excerpt(text,external=True))
        index='Stiamo cercando\nAgente commerciale con partita IVA\n'+('Specialista marketing e vendite\n'*8)+'Sviluppatore WordPress'
        self.assertIsNone(request_excerpt(index,external=True))

    def test_contactable_request_still_respects_geography_and_category(self):
        text='Cerchiamo uno sviluppatore WordPress freelance per collaborazioni continuative.'
        result=self.run_triage(self.page(text,place='80100 Napoli (NA)'))
        self.assertEqual(result['state'],'rejected')
        result=self.run_triage(self.page(text),filters={'regions':['Veneto'],'groups':['direct'],'target':'b2b'})
        self.assertEqual(result['state'],'rejected')

    def test_contract_belongs_to_same_role_not_neighbouring_vacancy(self):
        page=self.page('')
        page['html']+='<h2>WordPress Developer</h2><p>Siamo alla ricerca di un WordPress Developer.</p>'+('<p>Competenze tecniche e attività del ruolo.</p>'*12)+'<p>Collaborazione freelance con partita IVA.</p><h2>Commerciale</h2><p>Assunzione a tempo indeterminato.</p>'
        proof=collaboration_evidence(page)
        self.assertEqual(proof['role'],'WordPress Developer')
        self.assertIn('partita IVA',proof['contract_quote'])
        page['html']=page['html'].replace('Collaborazione freelance con partita IVA.','Assunzione a tempo indeterminato.').replace('<h2>Commerciale</h2><p>Assunzione a tempo indeterminato.</p>','<h2>Commerciale</h2><p>Collaborazione freelance con partita IVA.</p>')
        self.assertIsNone(collaboration_evidence(page))

    def test_outdated_request_is_not_ready_to_contact(self):
        page=self.page('Cerchiamo sviluppatori WordPress freelance per collaborazioni continuative.')
        page['html']+='<script type="application/ld+json">'+json.dumps({'@type':'JobPosting','datePosted':'2020-01-01','datePublished':'2020-01-01'})+'</script>'
        result=self.run_triage(page)
        self.assertNotEqual(result['state'],'promising')
        self.assertFalse(result['details'].get('collaboration'))

    def test_careers_page_creation_date_is_not_invented_vacancy_date(self):
        page=self.page('Cerchiamo uno sviluppatore WordPress freelance per collaborazioni continuative.')
        page['html']+='<meta property="article:published_time" content="2020-01-01">'
        result=self.run_triage(page)
        self.assertEqual(result['state'],'promising')
        self.assertIsNone(result['details']['collaboration']['published_at'])
        self.assertEqual(result['details']['collaboration']['page_published_at'][:10],'2020-01-01')

    def test_client_footer_is_not_supplier_presentation(self):
        page=self.page('Produciamo arredamento. Website by agenzia web Rossi.',title='Alfa Srl | Produzione arredamento')
        self.assertFalse(digital_supplier(parse_page(page)))
        self.assertTrue(digital_supplier(parse_page(self.page('',title='Alfa – Realizzazione siti e web marketing a Padova'))))

    def test_backend_ecommerce_request_is_not_assumed_fit_for_website_service(self):
        page=self.page('Cerchiamo sviluppatore senior PHP/Laravel freelance per la nostra piattaforma e-commerce.')
        result=self.run_triage(page,filters={'projects':['website'],'regions':['Veneto'],'target':'b2b'})
        self.assertEqual(result['state'],'needs_review')
        self.assertFalse(result['details'].get('collaboration'))

    def test_contact_label_cannot_create_a_nonexistent_email(self):
        page=self.page('Email<a href="mailto:hello@alfa.example">hello@alfa.example</a>')
        contacts=identity_from([page])['contacts']
        self.assertIn('hello@alfa.example',[c['value'] for c in contacts])
        self.assertNotIn('Emailhello@alfa.example',[c['value'] for c in contacts])

    def test_multiple_branch_regions_preserved_without_inventing_primary_office(self):
        page=self.page('Cerchiamo sviluppatori WordPress freelance per collaborazioni continuative.')
        page['html']+='<footer><p>Ufficio secondario</p><p>Via Milano 8, 20100 Milano (MI)</p></footer>'
        identity=identity_from([page])
        self.assertIsNone(identity['region'])
        self.assertEqual(set(identity['regions']),{'Veneto','Lombardia'})
        result=self.run_triage(page,filters={'regions':['Veneto','Lombardia'],'target':'b2b'})
        self.assertTrue(result['details'].get('collaboration'))
        self.assertNotIn('assessment',result)

    def test_documents_are_blocked_before_fetch_and_cached_pdf_cannot_sneak_in(self):
        for url in ('https://alfa.example/brochure.PDF','https://alfa.example/download?file=catalogo%2Epdf','https://alfa.example/prezzi.xlsx'):
            self.assertIsNotNone(route_exclusion({'url':url}))
            with patch.object(ResearchWeb,'get',side_effect=AssertionError('No download')):
                self.assertEqual(triage(self.store,{**self.payload,'url':url},lambda:None)['state'],'rejected')
        with patch.object(ResearchWeb,'get',return_value={'content_type':'application/pdf','plain_text':'Cached PDF'}):
            with self.assertRaisesRegex(ValueError,'PDF'):CompanyWeb(self.store).get('https://alfa.example/download')

    def test_demand_queries_exclude_aggregators_and_guides(self):
        query=searchable_query({'query':'WordPress freelance lavora con noi','strategy':'partner'})
        self.assertIn('-filetype:pdf',query);self.assertIn('-site:indeed.com',query)
        self.assertIsNotNone(route_exclusion({'url':'https://guide.example/info','title':'Aprire partita IVA per sviluppatori web'}))

if __name__=='__main__':unittest.main()
