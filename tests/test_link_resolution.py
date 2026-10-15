import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urljoin

from sales.db import Store, now
from sales.extract import Document, web_reference
from sales.providers import canonical
from sales.research_analysis import inspect_candidate, ResearchWeb, LocalResearcher


class LinkResolutionTests(unittest.TestCase):
    def test_logo_root_reference_does_not_become_contact_filename(self):
        # Actual markup found in both Freddo logos; repeat at different depths.
        html = '<header><a href="\\" class="logo blu"></a><a href="/contatti/">Contatti</a></header>'
        for base in ('https://freddo.it/', 'https://freddo.it/contatti/'):
            links = [canonical(urljoin(base, link['url'])) for link in Document(html).links]
            self.assertEqual(links, ['https://freddo.it/', 'https://freddo.it/contatti/'])
        self.assertEqual(web_reference('\\en'), '/en')
        self.assertEqual(web_reference('servizi\\catalogo'), 'servizi/catalogo')

    def test_query_fragment_and_encoded_backslash_are_not_rewritten(self):
        for href in ('/contatti/?q=a\\b#c\\d', '/file%5Cname',
                     'mailto:test@example.org?body=a\\b', '#a\\b'):
            self.assertEqual(web_reference(href), href)
        self.assertEqual(web_reference('https://example.org/contatti\\'), 'https://example.org/contatti/')

    def test_ambiguous_authorities_are_not_repaired(self):
        for href in ('https://example.org\\@127.0.0.1/a', '//example.org\\other/a',
                     '\\\\127.0.0.1/a', '/\\127.0.0.1/a'):
            with self.subTest(href=href):
                self.assertIsNone(web_reference(href))
                self.assertFalse(Document('<a href="'+href+'">Contatti</a>').links)
        for url in ('https://example.org/contatti/\\', 'https://example.org\\host/a'):
            with self.assertRaises(ValueError):canonical(url)
        self.assertEqual(web_reference('//shop.example.org/'), '//shop.example.org/')

    def test_inspector_reads_correct_contact_page_without_phantom_404(self):
        home = 'https://freddo.example/'
        contact = home+'contatti/'
        html = ('<title>Freddo Srl</title><header><a href="\\" class="logo blu"></a>'
                '<a href="/contatti/">Contatti</a></header><h1>Prodotti industriali</h1>'
                '<p>Freddo Srl, Padova, Veneto. Partita IVA 12345678901</p>'
                '<a href="mailto:info@freddo.example">Email</a>')
        pages = {url: {'url':url, 'html':html, 'status':200, 'checked_at':now()}
                 for url in (home, contact)}
        visited = []
        def read(url):
            visited.append(url)
            self.assertIn(url, pages, 'Unexpected download caused by a malformed logo link')
            return pages[url]
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/'test.db');store.init()
            with patch.object(ResearchWeb, 'get', side_effect=read), \
                 patch.object(LocalResearcher, 'analyze', return_value=([], {}, {}, [])):
                result = inspect_candidate(store, {'url':contact}, lambda:None)
        self.assertEqual(set(visited), {home, contact})
        self.assertFalse(any('404' in str(reason) for reason in result['assessment'].get('reasons', [])))
        self.assertNotEqual(result['assessment']['status'], 'qualified')


if __name__ == '__main__':unittest.main()
