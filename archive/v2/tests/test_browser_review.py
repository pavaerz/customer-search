import os
import unittest
from pathlib import Path
from mobile_review import review_mobile


@unittest.skipUnless(os.getenv('RUN_BROWSER_TESTS') == '1', 'Chrome integration test, opt in explicitly')
class BrowserReviewTest(unittest.TestCase):
    def test_redirected_stylesheet_and_responsive_layout(self):
        text = 'Informazioni sui servizi della nostra azienda e sulle lavorazioni offerte ai clienti. '*4
        html = '<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/redirect.css"><main><p>'+text+'</p></main>'
        for width, expected in [('900px',True),('100%',False)]:
            def fetch(url):
                self.assertEqual(url,'https://fixture.invalid/redirect.css')
                return 200, ('main{width:'+width+'}').encode(), 'text/css', 'https://fixture.invalid/style.css'
            result = review_mobile('https://fixture.invalid/',html,Path('/private/tmp'),fetch,lambda:None)
            self.assertIsNotNone(result)
            self.assertFalse(result['incomplete'])
            self.assertEqual(result['qualifies'],expected)

    def test_captcha_background_call_does_not_invalidate_layout(self):
        text = 'Informazioni sui servizi della nostra azienda e sulle lavorazioni offerte ai clienti. '*4
        for endpoint, incomplete in [('https://www.google.com/recaptcha/api2/reload', False),
                                     ('https://fixture.invalid/application-data', True)]:
            html = ('<meta name="viewport" content="width=device-width, initial-scale=1">'
                    '<main style="width:900px"><p>'+text+'</p></main>'
                    '<script>fetch("'+endpoint+'",{method:"POST",body:"test"}).catch(()=>{})</script>')
            def fetch(url):
                self.fail('No POST request may reach the network')
            result = review_mobile('https://fixture.invalid/', html, Path('/private/tmp'), fetch, lambda:None)
            self.assertIsNotNone(result)
            self.assertEqual(result['incomplete'], incomplete)
            self.assertEqual(result['qualifies'], not incomplete)

    def test_old_desktop_layout_is_detected_without_semantic_tags(self):
        text = 'La nostra azienda realizza lavorazioni e servizi per tutti i clienti. '*8
        for viewport, width, expected in [('', '980px', True),
                                          ('<meta name="viewport" content="width=device-width, initial-scale=1">', '100%', False)]:
            html = viewport+'<table style="width:'+width+'"><tr><td>'+text+'</td></tr></table>'
            result = review_mobile('https://fixture.invalid/',html,Path('/private/tmp'),lambda url:None,lambda:None)
            self.assertFalse(result['incomplete'])
            self.assertEqual(result['qualifies'], expected)
            if expected:
                self.assertIn('desktop_scaled_mobile', [f['code'] for f in result['ux_findings']])

    def test_moderately_small_text_is_not_selected(self):
        text = 'Informazioni sui servizi e sulle lavorazioni offerte dalla nostra azienda. '
        for size, expected in [(13, False), (14, False), (16, False)]:
            html = ('<meta name="viewport" content="width=device-width, initial-scale=1">'
                    f'<main style="font-size:{size}px"><p>{text}</p><p>{text}</p></main>')
            result = review_mobile('https://fixture.invalid/', html, Path('/private/tmp'), lambda url:None, lambda:None)
            self.assertIsNotNone(result)
            self.assertFalse(result['incomplete'])
            self.assertEqual(result['qualifies'], expected)

    def test_accessory_failure_is_ignored_but_stylesheet_failure_is_not(self):
        text = 'Informazioni sui servizi della nostra azienda e sulle lavorazioni offerte ai clienti. '*4
        for tag, incomplete in [('<link rel="icon" href="/favicon.ico">', False),
                                ('<link rel="stylesheet" href="/missing.css">', True)]:
            html = ('<meta name="viewport" content="width=device-width, initial-scale=1">'+tag+
                    '<main style="width:900px"><p>'+text+'</p></main>')
            result = review_mobile('https://fixture.invalid/', html, Path('/private/tmp'),
                                  lambda url:(404,b'', 'text/css',url),lambda:None)
            self.assertIsNotNone(result)
            self.assertEqual(result['incomplete'], incomplete)
            self.assertEqual(result['qualifies'], not incomplete)

    def test_redirected_stylesheet_resolves_relative_font_from_final_directory(self):
        text = 'Informazioni sui servizi della nostra azienda e sulle lavorazioni offerte. '*4
        html = '<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/redirect.css"><main><p>'+text+'</p></main>'
        seen=[]
        def fetch(url):
            seen.append(url)
            if url.endswith('/redirect.css'):
                return 200, b'@import "layout.css";', 'text/css', 'https://fixture.invalid/assets/style.css'
            self.assertEqual(url,'https://fixture.invalid/assets/layout.css')
            return 200, b'main{width:900px}', 'text/css', url
        result = review_mobile('https://fixture.invalid/',html,Path('/private/tmp'),fetch,lambda:None)
        self.assertFalse(result['incomplete'])
        self.assertTrue(result['qualifies'])
        self.assertIn('https://fixture.invalid/assets/layout.css',seen)
