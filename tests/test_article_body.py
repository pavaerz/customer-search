import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sales.db import Store,now
from sales.research_analysis import document,resolve_publisher,LocalResearcher,ResearchWeb
from sales.research_triage import triage


def page(body):
    return {'url':'https://publisher.example/alfa/','status':200,'checked_at':now(),
            'html':'<title>Alfa presenta il nuovo marchio</title><script type="application/ld+json">{"@type":"Article","headline":"Alfa presenta il nuovo marchio"}</script>'+body}


class ArticleBodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'test.db');self.store.init()

    def tearDown(self):self.tmp.cleanup()

    def test_main_body_only_but_full_evidence_preserved(self):
        p=page('<div class="elementor-widget-theme-post-content"><p>Alfa Srl presenta il nuovo marchio.</p></div><aside><p>Beta Srl apre una nuova divisione.</p><a href="https://beta.example/">Beta Srl</a></aside>')
        d=document(p)
        self.assertIn('Alfa Srl',d['research_text']);self.assertNotIn('Beta Srl',d['research_text'])
        self.assertIn('Beta Srl',d['text']);self.assertTrue(d['body_scope'])
        with patch.object(LocalResearcher,'call',return_value={'companies':[{'name':'Beta Srl','quote':'Beta Srl apre una nuova divisione.'}]}):
            r=resolve_publisher(self.store,p,{'strategy':'change'},lambda:None)
        self.assertEqual(r['discovered'],[])
        self.assertFalse(any(q['subject']=='Beta Srl' for q in r.get('resolve_queries',[])))

    def test_ambiguous_article_cards_do_not_select_first(self):
        p=page('<div class="entry-content">Prima scheda</div><div class="entry-content">Seconda scheda</div>')
        d=document(p);self.assertIsNone(d['body_scope'])
        self.assertIn('Prima scheda',d['research_text']);self.assertIn('Seconda scheda',d['research_text'])

    def test_articlebody_visible_content_not_hidden_schema_text(self):
        p=page('<main itemprop="articleBody"><p>Contenuto visibile.</p><script>Ordini impossibili inventati</script></main><aside>Testo estraneo</aside>')
        d=document(p);self.assertEqual(d['research_text'],'Contenuto visibile.')

    def test_subscription_preview_is_unverifiable_without_resolution_or_model(self):
        p=page('<div class="entry-content">Anteprima dell’articolo.</div><h4>Accedi ai contenuti esclusivi riservati ai nostri abbonati e continua la lettura senza interruzioni.</h4><aside>Beta apre una nuova divisione.</aside>')
        with patch.object(ResearchWeb,'get',return_value=p),patch.object(LocalResearcher,'call',side_effect=AssertionError('Do not analyze paywall')):
            r=triage(self.store,{'url':p['url'],'publisher':True,'strategy':'change'},lambda:None)
            resolved=resolve_publisher(self.store,p,{},lambda:None)
            signals,_,_,limits=LocalResearcher(self.store).analyze({},[document(p)],{})
        self.assertEqual(r['state'],'unverifiable');self.assertFalse(r.get('resolve'))
        self.assertEqual(resolved['discovered'],[]);self.assertTrue(resolved['incomplete'])
        self.assertEqual(signals,[]);self.assertTrue(limits)

    def test_newsletter_invitation_is_not_paywall(self):
        p=page('<div class="entry-content">Alfa Srl presenta il nuovo marchio.</div><p>Iscriviti alla newsletter.</p>')
        self.assertIsNone(document(p)['access_limit'])

    def test_related_paid_article_does_not_restrict_main_article(self):
        p=page('<div class="entry-content">Alfa Srl presenta il nuovo marchio.</div><script type="application/ld+json">{"@type":"Article","headline":"Altro articolo riservato","isAccessibleForFree":false}</script>')
        self.assertIsNone(document(p)['access_limit'])

    def test_printed_domain_does_not_become_company_name(self):
        p=page('<div class="entry-content"><p>Alfa Srl presenta il nuovo marchio dedicato alla produzione di componenti industriali per il mercato tedesco.</p><a href="https://alfasrl.example/">www.alfasrl.example</a></div>')
        r=resolve_publisher(self.store,p,{'strategy':'change'},lambda:None)
        self.assertEqual([x['subject'] for x in r['discovered']],['Alfa Srl'])

    def test_bare_name_quote_recovers_observed_event_not_sidebar(self):
        from sales.source_identity import subject_context
        event='Alfa Srl presenta il nuovo marchio dedicato alla produzione di componenti industriali per il mercato tedesco.'
        d=document(page('<div class="entry-content"><p>'+event+'</p></div><aside>Beta Srl investe nella nuova divisione.</aside>'))
        self.assertEqual(subject_context(d,'Alfa Srl','Alfa Srl'),event)
        self.assertIsNone(subject_context(d,'Beta Srl','Beta Srl'))

    def test_custom_editor_must_follow_matching_h1_in_same_parent(self):
        article='<div><h1>Alfa presenta il nuovo marchio</h1><div id="editor"><p>Il nuovo sito è disponibile ai clienti.</p></div></div>'
        d=document(page(article+'<aside>Notizie su Beta Srl.</aside>'))
        self.assertEqual(d['research_text'],'Il nuovo sito è disponibile ai clienti.')
        for body in [article.replace('il nuovo marchio</h1>','altra notizia</h1>'),
                     article.replace('id="editor"','id="editor" contenteditable="true"'),
                     '<div id="editor">Editor prima del titolo</div><h1>Alfa presenta il nuovo marchio</h1>',
                     '<h1>Alfa presenta il nuovo marchio</h1><aside><div id="editor">Editor estraneo</div></aside>']:
            self.assertIsNone(document(page(body))['body_scope'])

    def test_encoded_headline_still_matches_visible_article(self):
        p=page('<div><h1>Le novità di Alfa</h1><div id="editor">Contenuto originale di Alfa.</div></div>')
        p['html']=p['html'].replace('Alfa presenta il nuovo marchio</title>','Le novità di Alfa</title>').replace('"headline":"Alfa presenta il nuovo marchio"','"headline":"Le novit&#224; di Alfa"')
        self.assertEqual(document(p)['research_text'],'Contenuto originale di Alfa.')

    def test_valueless_html_attributes_do_not_break_original_page_reading(self):
        p=page('<div class itemprop><p>Contenitore esterno.</p><div class="entry-content">Il fatto commerciale originale.</div></div>')
        self.assertEqual(document(p)['research_text'],'Il fatto commerciale originale.')
