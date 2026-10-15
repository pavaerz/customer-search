import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sales.db import Store,now
from sales.research_analysis import document,identity_from,LocalResearcher,resolve_publisher,ResearchWeb
from sales.research_triage import triage
from sales.discovery_planner import variants


def page(html,url='https://alfa.example/'):
    return {'url':url,'html':html,'checked_at':now(),'status':200}


class EvidenceScopingTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store(Path(tmp.name)/'test.db');self.store.init()
    def test_evergreen_article_metadata_never_dates_a_business_event(self):
        for path in ('/','/chi-siamo/','/it/contatti'):
            p=page('<title>Alfa</title><script type="application/ld+json">{"@type":"Article","datePublished":"2017-01-01"}</script><p>Nuova linea di prodotti</p>','https://alfa.example'+path)
            doc=document(p);self.assertIsNone(doc['published_at']);self.assertEqual(doc['page_published_at'],'2017-01-01')
            with patch.object(ResearchWeb,'get',return_value=p):result=triage(self.store,{'url':p['url'],'strategy':'change'},lambda:None)
            self.assertNotIn('Data non attuale',result['reason'])
    def test_real_article_retains_date(self):
        doc=document(page('<script type="application/ld+json">{"@type":"Article","datePublished":"2026-10-01"}</script>','https://alfa.example/news/nuova-linea'))
        self.assertEqual(doc['published_at'],'2026-10-01')
    def test_generic_webpage_date_never_dates_event(self):
        doc=document(page('<script type="application/ld+json">{"@type":"WebPage","datePublished":"2026-10-01"}</script>','https://alfa.example/catalogo'))
        self.assertIsNone(doc['published_at'])
    def test_dealer_address_not_manufacturer_address(self):
        markup='<title>Alfa · Rivenditori</title><meta property="og:site_name" content="Alfa"><p>Beta Srl Via Roma 2, 35100 Padova (PD)</p><p>P.IVA 12345678901</p><a href="mailto:beta@alfa.example">Contatto</a>'
        markup+='<script type="application/ld+json">'+json.dumps({'@type':'LocalBusiness','url':'https://beta.example','address':{'@type':'PostalAddress','addressLocality':'Padova','addressCountry':'IT'}})+'</script>'
        identity=identity_from([page(markup,'https://alfa.example/rivenditori')])
        self.assertIsNone(identity['region']);self.assertIsNone(identity['legal_id']);self.assertEqual(identity['identity_status'],'unknown');self.assertEqual(identity['contacts'],[])
    def test_owned_schema_and_footer_survive_dealer_page(self):
        markup='<title>Alfa Rivenditori</title><p>Beta Via Firenze 1, 50100 Firenze</p><footer>Alfa Srl<p>Sede legale Via Roma 2, 35100 Padova (PD)</p><p>P.IVA 12345678901</p><a href="mailto:info@alfa.example">Info</a></footer>'
        identity=identity_from([page(markup,'https://alfa.example/rivenditori')])
        self.assertEqual(identity['region'],'Veneto');self.assertEqual(identity['identity_status'],'verified')
    def test_job_employer_schema_is_not_host_identity(self):
        schema={'@type':'JobPosting','hiringOrganization':{'@type':'Organization','name':'Alfa','url':'https://jobs.example','vatID':'12345678901','address':{'addressLocality':'Padova','addressCountry':'IT'}}}
        identity=identity_from([page('<title>Recruiter</title><script type="application/ld+json">'+json.dumps(schema)+'</script>','https://jobs.example/annuncio')])
        self.assertEqual(identity['identity_status'],'unknown');self.assertIsNone(identity['region'])
    def test_employee_hiring_not_deep_candidate(self):
        p=page('<title>Responsabile e-commerce</title><p>Cerchiamo responsabile e-commerce per azienda cliente. Tempo indeterminato, RAL 50000 euro.</p>')
        with patch.object(ResearchWeb,'get',return_value=p):result=triage(self.store,{'url':p['url'],'strategy':'hiring'},lambda:None)
        self.assertEqual(result['state'],'needs_review');self.assertNotIn('resolve',result)
    def test_clean_consent_retains_original_and_business(self):
        p=page('<p>Ordini B2B con configurazioni dipendenti.</p><div class="cookie-consent"><div>Privacy cookie <b>marketing</b></div></div><p>Il portale già attivo gestisce gli ordini.</p>')
        doc=document(p)
        self.assertIn('Privacy cookie',doc['text']);self.assertNotIn('Privacy cookie',doc['research_text'])
        self.assertIn('portale già attivo',doc['research_text']);self.assertEqual(doc['removed_consent_blocks'],1)
    def test_duplicate_pages_and_consent_do_not_trigger_repeated_model_calls(self):
        first=document(page('<p>La nostra nuova linea di prodotti.</p><div id="cookie-banner">Privacy</div>'))
        second=document(page('<p>La nostra nuova linea di prodotti.</p>','https://alfa.example/alias'))
        with patch.object(LocalResearcher,'call',return_value={'claims':[]}) as call:
            LocalResearcher(self.store).analyze({},[first,second],{})
        self.assertEqual(call.call_count,1)
    def test_claim_from_hidden_original_rejected_if_not_in_model_excerpt(self):
        doc=document(page('<p>La nuova linea di prodotti.</p><div id="cookie-banner">Il budget del progetto è di 5000 euro.</div>'))
        with patch.object(LocalResearcher,'call',return_value={'claims':[{'document_id':doc['id'],'kind':'budget','quote':'Il budget del progetto è di 5000 euro.'}]}):
            signals,_,_,limits=LocalResearcher(self.store).analyze({},[doc],{})
        self.assertEqual(signals,[]);self.assertTrue(limits)
    def test_article_follows_named_official_link_without_model(self):
        p=page('<title>Alfa investe nella distribuzione</title><p><a href="https://alfa.example/">Alfa Srl</a> presenta una nuova linea di prodotti a Padova.</p>','https://editore.example/news/alfa')
        with patch.object(LocalResearcher,'call',side_effect=AssertionError('No model needed')):
            result=resolve_publisher(self.store,p,{'strategy':'change'},lambda:None)
        self.assertEqual(len(result['discovered']),1);self.assertTrue(result['discovered'][0]['official_link'])
    def test_initial_variants_differ_in_meaning(self):
        queries=list(variants('change','Veneto'))
        self.assertNotEqual(queries[0].replace('"',''),queries[1].replace('"',''))
        self.assertEqual(len(queries),len(set(queries)))
    def test_trade_association_is_source_not_customer(self):
        p=page('<title>Unioncamere del Veneto</title><p>Nuova linea di prodotti alimentari.</p>','https://unioncamere.example/notizia')
        with patch.object(ResearchWeb,'get',return_value=p):result=triage(self.store,{'url':p['url'],'strategy':'change'},lambda:None)
        self.assertTrue(result['details']['publisher']);self.assertEqual(result['details']['identity'],{});self.assertTrue(result['resolve'])
    def test_old_visible_date_with_comma_prevents_deep_analysis(self):
        p=page('<title>Nuova linea prodotti</title><p>15 Marzo, 2019</p><p>Abbiamo una nuova linea di prodotti.</p>','https://alfa.example/nuova-linea')
        self.assertEqual(document(p)['published_at'],'2019-03-15')
        with patch.object(ResearchWeb,'get',return_value=p):result=triage(self.store,{'url':p['url'],'strategy':'change'},lambda:None)
        self.assertEqual(result['state'],'needs_review');self.assertIn('Data non attuale',result['reason'])
    def test_generic_guide_is_not_business_need(self):
        p=page('<title>Come aprire un ecommerce: guida definitiva</title><p>Aprire un e-commerce richiede un investimento. Ecco le configurazioni possibili.</p>','https://alfa.example/guida')
        with patch.object(ResearchWeb,'get',return_value=p):result=triage(self.store,{'url':p['url'],'strategy':'investment'},lambda:None)
        self.assertEqual(result['state'],'needs_review');self.assertIn('Guida',result['reason'])
    def test_separate_mentions_do_not_invent_job_vacancy(self):
        from sales.research_evidence import preliminary_disposition
        from sales.extract import parse_page
        p=page('<title>Nuovi prodotti</title><p>La normativa sull’assunzione.</p><p>'+'Descrizione prodotti. '*60+'</p><p>Il prodotto è candidato al premio.</p>')
        self.assertIsNone(preliminary_disposition(p,parse_page(p),document(p)['research_text']))
    def test_assunzione_al_bilancio_is_not_employee_hiring(self):
        from sales.research_evidence import preliminary_disposition
        from sales.extract import parse_page
        p=page('<title>PNRR sito web</title><p>Candidatura ammessa PNRR. Decreto assunzione al bilancio. Certificato regolare esecuzione sito web.</p><p>Pubblicato: 09.06.2023 - Revisione: 27.06.2023</p>','https://scuola.example/documento/progetto')
        self.assertIsNone(preliminary_disposition(p,parse_page(p),document(p)['research_text']))
        self.assertEqual(document(p)['published_at'],'2023-06-09')
    def test_publisher_parent_domain_and_institution_are_not_companies(self):
        p=page('<title>Bando imprese</title><div><a href="https://regione.veneto.it/">la Regione</a> pubblica un bando per nuovi progetti. <a href="https://associazione.example/">CNA</a> promuove una nuova linea.</div>','https://bur.regione.veneto.it/decreto')
        with patch.object(LocalResearcher,'call',return_value={'companies':[{'name':'la Regione','quote':'la Regione pubblica un bando per nuovi progetti.'}]}):
            result=resolve_publisher(self.store,p,{},lambda:None)
        self.assertEqual(result['discovered'],[]);self.assertEqual(result['resolve_queries'],[])


if __name__=='__main__':unittest.main()
