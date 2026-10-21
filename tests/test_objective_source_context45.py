"""Actual C45 HTML, offline extraction and explicitly synthetic AI transport."""
import copy
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_ai_first as harness
from sales.agent6 import evidence, decision
from sales.agent6.source_context import select_links, editorial
from sales.commercial.inspection import document
from sales.db import digest

SAVED = json.loads(gzip.decompress((Path(__file__).parent /
    'fixtures/ai_first/campaign45/news-originals.json.gz').read_bytes()))


def packet(html):
    page = {'url': 'https://publisher.example/story', 'html': html,
            'status': 200, 'checked_at': harness.DATE, 'content_type': 'text/html'}
    return evidence.packet(page, document(page))


class SavedSources(unittest.TestCase):
    def test_real_named_business_links_survive_the_eight_link_cap(self):
        row = SAVED[0]
        p = evidence.packet(row['page'], document(row['page']))
        before = p['links'][:8]
        after = select_links(p, p['units'][0], 'NEWS', False)
        target = 'https://www.mtvveneto.it/cantina/villa-sandi/'
        self.assertNotIn(target, [l['url'] for l in before])
        self.assertIn(target, [l['url'] for l in after])
        self.assertEqual(len(after), 8)
        self.assertTrue(all(l['context'] == 'source_content' for l in after))
        self.assertTrue(all(l['id'] in {x['id'] for x in p['links']} for l in after))
        self.assertFalse(any(l['label'] == 'CONTATTI' for l in after))

    def test_real_company_mentions_replace_publisher_newsletter_excerpt(self):
        p = evidence.packet(SAVED[0]['page'], document(SAVED[0]['page']))
        u = p['units'][0]
        old = '\n'.join(e['text'] for e in evidence.passages(p, u, 3000))
        new = '\n'.join(e['text'] for e in evidence.passages(p, u, 3000, source_content=True))
        self.assertNotIn('Villa Sandi', old)
        self.assertIn('Villa Sandi', new)
        self.assertIn('Villa Meneghello', new)
        self.assertNotIn('Lost your password', new)
        self.assertNotIn('Sede legale:', new)

    def test_regional_article_contains_distinct_companies_not_just_event_intro(self):
        p = evidence.packet(SAVED[1]['page'], document(SAVED[1]['page']))
        u = p['units'][0]
        old = '\n'.join(e['text'] for e in evidence.passages(p, u, 3000))
        new = '\n'.join(e['text'] for e in evidence.passages(p, u, 3000, source_content=True))
        self.assertNotIn('Ca’ Rugate', old)
        self.assertIn('Ca’ Rugate', new)
        self.assertNotIn('P.IVA 01101300521', new)

    def test_all_real_quotes_keep_original_offsets_hashes_and_size(self):
        saved_before = copy.deepcopy(SAVED)
        for row in SAVED:
            doc = document(row['page']); p = evidence.packet(row['page'], doc)
            proofs = evidence.passages(p, p['units'][0], 3000, source_content=True)
            self.assertLessEqual(sum(len(e['text'].encode()) for e in proofs), 3000)
            for e in proofs:
                self.assertEqual(doc['text'][e['offset']:e['offset']+len(e['text'])], e['text'])
                self.assertEqual(e['hash'], digest(e['text']))
                self.assertEqual(e['document_id'], doc['id'])
                self.assertTrue(e['original'])
            self.assertNotIn('decision', p)
        self.assertEqual(SAVED, saved_before)


class SourceBoundaries(unittest.TestCase):
    def test_hidden_comments_related_and_navigation_are_not_article_links(self):
        html = '<nav><a href="/contact">Contatti</a></nav><main><article>'
        html += '<div class="entry-content"><p>Impresa Gamma apre un laboratorio.</p><a href="/gamma">Impresa Gamma</a>'
        for mark in ('hidden', 'aria-hidden="true"', 'style="display:none"', 'class="comments"', 'class="related-posts"'):
            html += '<div '+mark+'><p>Falso bisogno nascosto.</p><a href="/hidden">Falso</a></div>'
        html += '<form><a href="/form">Invia</a></form></div></article></main>'
        p = packet(html)
        self.assertEqual(p['content_context']['links'], ['https://publisher.example/gamma'])
        self.assertEqual([l['url'] for l in select_links(p, p['units'][0], 'NEWS', False)],
                         ['https://publisher.example/gamma'])
        proofs = evidence.passages(p, p['units'][0], 3000, source_content=True)
        self.assertNotIn('Falso', '\n'.join(e['text'] for e in proofs))

    def test_theme_layout_flags_do_not_hide_the_article(self):
        p = packet('<body class="menu-link-color"><div class="has-no-sidebar"><article class="share-simple">'
                   '<p>Un fatto osservato.</p><a href="/alfa">Alfa</a></article></div></body>')
        self.assertTrue(p['content_context']['ranges'])
        self.assertIn('https://publisher.example/alfa', p['content_context']['links'])

    def test_article_header_is_content_but_site_header_is_not(self):
        p = packet('<header><a href="/publisher">Editore</a></header><article>'
                   '<header><p>Il fatto dell’articolo.</p><a href="/subject">Soggetto citato</a></header></article>')
        links = select_links(p, p['units'][0], 'NEWS', False)
        self.assertEqual([l['label'] for l in links], ['Soggetto citato'])
        self.assertNotIn('Editore', '\n'.join(e['text'] for e in evidence.passages(p, p['units'][0], source_content=True)))

    def test_duplicate_menu_label_cannot_supply_a_company_quote(self):
        p = packet('<div>Nome ripetuto</div><main><p>Un fatto unico.</p>'
                   '<p>Nome ripetuto</p></main><div>Nome ripetuto</div>')
        quotes = evidence.passages(p, p['units'][0], source_content=True)
        self.assertEqual([e['text'] for e in quotes], ['Un fatto unico.'])

    def test_safe_link_filters_and_ids_are_not_bypassed_by_context(self):
        p = packet('<main><a href="/brochure.pdf">Progetto</a><a href="/delete">Cancella</a>'
                   '<a href="/info?token=secret">Riservato</a><a href="/gamma">Gamma</a></main>')
        links = select_links(p, p['units'][0], 'NEWS', False)
        self.assertEqual([l['url'] for l in links], ['https://publisher.example/gamma'])

    def test_unknown_boundary_keeps_existing_quote_selection(self):
        p = packet('<div>Un fatto senza contenitore esplicito.</div>')
        u = p['units'][0]
        self.assertEqual(p['content_context']['basis'], 'no_explicit_content_boundary')
        self.assertEqual(evidence.passages(p, u), evidence.passages(p, u, source_content=True))

    def test_agency_careers_priority_and_scoped_social_units_preserved(self):
        p = packet('<nav><a href="/careers">Lavora con noi</a></nav><main>'+
                   ''.join('<a href="/product/'+str(i)+'">Prodotto '+str(i)+'</a>' for i in range(12))+'</main>')
        u = p['units'][0]
        self.assertEqual(select_links(p, u, 'AGENCIES', True)[0]['label'], 'Lavora con noi')
        for origin in ('JobPosting', 'SocialMediaPosting', 'labelled_card'):
            unit = {**u, 'origin': origin}
            self.assertFalse(editorial(p, unit, 'NEWS', False))
            self.assertEqual(select_links(p, unit, 'NEWS', False), p['links'][:8])

    def test_own_news_can_prioritize_content_without_changing_owner_identity(self):
        p = packet('<nav><a href="/contact">Contatti</a></nav><main><a href="/product">Linea nuova</a></main>')
        u = p['units'][0]
        self.assertEqual(select_links(p, u, 'NEWS', True)[0]['label'], 'Linea nuova')
        self.assertNotIn('identity', p['content_context'])

    def test_editorial_windows_do_not_cut_names_at_the_end(self):
        # Use unique paragraphs, otherwise context mapping deliberately refuses
        # to guess which occurrence is the article.
        p = packet('<main>'+''.join('<p>'+str(i)+' '+('Una frase completa. '*35)+
                   ' Impresa Alfa Beta Gamma.</p>' for i in range(6))+'</main>')
        for e in evidence.passages(p, p['units'][0], 3000, source_content=True):
            self.assertTrue(e['text'].endswith('.'), e['text'][-40:])


class Pipeline(unittest.TestCase):
    def test_real_page_context_reaches_ai_with_no_automatic_promotion(self):
        base = harness.IntegratedPath(); base.setUp()
        self.addCleanup(base.tearDown)
        page = copy.deepcopy(SAVED[0]['page']); captured = []
        base.w.enqueue('candidate', 'NEWS', {'url': page['url'], 'original_page': page,
            'title': 'Cantine Aperte', 'query': 'evento Veneto', 'strategy': 'company_event'}, 'context45')
        with base.store.connect() as db:
            r = db.execute("SELECT * FROM research_tasks WHERE fingerprint='context45'").fetchone()
            task = {**dict(r), 'payload': json.loads(r['payload'])}
        def model(payload, cfg, check):
            captured.append(payload)
            return {'output': {'invalid_offline_test': True}, 'usage': {'input_tokens': 20, 'output_tokens': 5}}
        with patch('sales.agent6.ai.infer', side_effect=model), patch('sales.agent6.research.identity_from',
                   return_value={'name': 'Editore', 'identity_status': 'unknown', 'contacts': []}), patch(
                   'sales.agent6.research.locate', return_value={'eligible': True, 'regions': ['Veneto']}):
            base.w.execute(task, lambda: None)
        self.assertTrue(captured)
        self.assertIn('Villa Sandi', '\n'.join(e['text'] for e in captured[0]['evidence']))
        self.assertIn('Villa Sandi', [l['label'] for l in captured[0]['links']])
        self.assertLessEqual(len(captured[0]['links']), 8)
        with base.store.connect() as db:
            bodies = [json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
            self.assertTrue(bodies)
            self.assertFalse(any(b.get('decision') == 'INTERESTING' for b in bodies))
