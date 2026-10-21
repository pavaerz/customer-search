import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from test_commercial_engines import page
from sales.db import Store
from sales.commercial.browser import _review as review

class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'test.db');self.store.init()
    def review(self,p,raw=None,**kwargs):
        # Actual Chromium, but every document is a fixture and every proxy egress
        # (including browser background traffic) is denied before DNS/connect.
        with patch('sales.heavy.DATA',Path(self.tmp.name)),patch('sales.safe_proxy.public_addresses',side_effect=ValueError('Offline test')),patch('sales.commercial.browser.PublicWeb._raw',side_effect=raw or AssertionError('Unexpected external resource')):
            return review(self.store,[p],capture=False,**kwargs)
    def test_real_mobile_measurements_identify_clipped_content(self):
        p=page('Sito di prova',extra='<style>main{width:1200px}main p{margin-left:500px}</style><main><p>Contenuto di prodotto sufficientemente lungo per misurare il percorso commerciale.</p><p>Secondo blocco con informazioni utili e contatti per il potenziale cliente.</p></main>')
        r=self.review(p);self.assertTrue(r['completed'],r['limits']);self.assertIn('mobile_content',{f['code'] for f in r['findings']});self.assertEqual(len(r['pages']),2)
    def test_missing_resource_is_incomplete_not_a_layout_problem(self):
        p=page('Azienda e servizi di esempio.',extra='<link rel="stylesheet" href="https://alfa.example/style.css">')
        r=self.review(p,TimeoutError('Risorsa non verificabile'));self.assertFalse(r['completed']);self.assertTrue(r['limits'])
    def test_private_resource_never_escapes_network_gate(self):
        p=page('Servizi industriali e catalogo di esempio.',extra='<img src="http://127.0.0.1/private">')
        r=self.review(p,ValueError('Rete privata non consentita'));self.assertFalse(r['completed'])
    def test_stop_propagates(self):
        with self.assertRaises(InterruptedError):review(self.store,[page('Test')],check=lambda:(_ for _ in ()).throw(InterruptedError()))

    def test_healthy_site_rendered_on_both_viewports(self):
        p=page('Un sito con informazioni complete, prodotti e contatti leggibili su entrambi gli schermi.',extra='<meta name="viewport" content="width=device-width"><main><p>Contenuti della nostra offerta e percorsi di navigazione accessibili.</p></main>')
        r=self.review(p);self.assertTrue(r['completed'],r['limits']);self.assertEqual(r['findings'],[])
        self.assertEqual({x['viewport'] for x in r['pages']},{390,1366})

    def test_html_extraction_sparse_but_javascript_renders_content(self):
        p=page('',extra='<script>document.addEventListener("DOMContentLoaded",()=>{document.body.innerHTML="<main><h1>Azienda</h1><p>Descrizione completa dei prodotti e dei servizi della nostra azienda con dettagli utili.</p></main>"})</script>')
        r=self.review(p);self.assertTrue(r['completed'],r['limits']);self.assertEqual(len(r['pages']),2)

    def test_only_mobile_barriers_not_invented_on_desktop(self):
        p=page('Prodotti aziendali.',extra='<style>@media(max-width:600px){main{width:1500px}main p{margin-left:600px}}</style><main><p>Questa descrizione dei servizi è visibile correttamente soltanto sullo schermo ampio.</p><p>Questi contenuti informativi sono al di fuori della larghezza dello schermo mobile.</p></main>')
        r=self.review(p);self.assertTrue(r['completed'],r['limits'])
        self.assertEqual({f['viewport'] for f in r['findings']},{390})

    def test_render_timeout_is_incomplete_not_site_defect(self):
        import time
        p=page('Informazioni aziendali sufficientemente lunghe per il controllo.',extra='<link rel="stylesheet" href="https://alfa.example/slow.css">')
        def slow(url):
            time.sleep(.1)
            return {'url':url,'status':200,'body':b'body{color:black}','content_type':'text/css'}
        r=self.review(p,slow,limits={'browser_timeout_ms':1})
        self.assertFalse(r['completed']);self.assertEqual(r['findings'],[]);self.assertTrue(r['limits'])

    def test_rendered_contact_path_checked_without_submission(self):
        p=page('Informazioni di prodotti e servizi per tutti i nostri clienti.',extra='<main><a href="/contatti">Contatti</a></main>')
        r=self.review(p,lambda url:{'url':url,'status':404,'html':'Non trovata'})
        self.assertTrue(r['completed'],r['limits']);self.assertEqual(r['path_checks'][0]['status'],404)
        self.assertIn('broken_contact',{f['code'] for f in r['findings']})
