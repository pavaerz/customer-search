import json
import unittest
from unittest.mock import patch
from sales.source_roles import publisher_identity
from sales.company_research import inspect_company
from sales.research_analysis import ResearchWeb
from sales.db import now


def page(html,url='https://daily.example/'):
    return {'url':url,'html':html,'checked_at':now(),'status':200}


class PublisherSelfDescriptionTests(unittest.TestCase):
    def test_own_news_website_schema_is_not_a_customer(self):
        data={'@type':'WebSite','url':'https://daily.example/','alternateName':'Daily Tutte le notizie di Venezia'}
        html='<script type="application/ld+json">'+json.dumps(data)+'</script>'
        self.assertTrue(publisher_identity(page(html)))
        self.assertFalse(publisher_identity(page(html,'https://manufacturer.example/')))

    def test_registered_periodical_can_be_identified_without_word_giornale(self):
        p=page('<footer>Daily è un periodico iscritto nel Registro della stampa del Tribunale di Padova.</footer>')
        self.assertTrue(publisher_identity(p))
        self.assertFalse(publisher_identity(page('<footer>Alfa Srl iscritta nel Registro delle imprese di Padova.</footer>')))

    def test_homepage_identity_routes_unknown_article_to_company_resolution(self):
        article=page('<title>Alfa inaugura una nuova linea</title><p>Alfa Srl inaugura una nuova linea di prodotti.</p>','https://daily.example/news/alfa')
        home=page('<footer>Daily è un periodico iscritto nel Registro della stampa del Tribunale di Padova.</footer>')
        with patch.object(ResearchWeb,'get',return_value=home):
            result=inspect_company(None,{'url':article['url']},article,lambda:None)
        self.assertTrue(result['resolve']);self.assertTrue(result['details']['publisher'])
        self.assertEqual(result['details']['identity'],{})
        self.assertEqual(result['details']['document']['url'],article['url'])
        self.assertFalse(result['details']['document']['official'])
