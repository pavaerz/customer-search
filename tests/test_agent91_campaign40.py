"""Offline regressions over original Campaign 40 pages; no new opportunities."""
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from sales.agent6.site_identity import resolve
from sales.commercial.entity_scope import profile
from sales.commercial.target_fit import source_role, evaluate
from sales.extract import parse_page

FIXTURE = json.loads(gzip.decompress((Path(__file__).parent / 'fixtures/agent91/campaign40.json.gz').read_bytes()))
CASES = {c['record_id']: c for c in FIXTURE['cases']}


class Campaign40Identity(unittest.TestCase):
    def test_cartoveneta_owner_address_resolves_veneto_without_query_geography(self):
        c = CASES[556]
        pages, identity, provenance = resolve(c['pages'], c['url'])
        self.assertEqual(identity['name'], 'Cartoveneta APCI Srl')
        self.assertEqual(identity['region'], 'Veneto')
        self.assertEqual(identity['identity_status'], 'verified')
        self.assertTrue(provenance['relationship_verified'])
        fit = evaluate(identity, pages, {'eligible': identity['region'] == 'Veneto'})
        self.assertTrue(fit['audit_allowed'], fit['reasons'])
        # Eligibility for measurement proves no defect, buyer intent or budget.
        self.assertIsNone(fit['purchase_intent'])
        self.assertIsNone(fit['budget'])

    def test_publisher_cannot_borrow_listed_company_identity(self):
        c = CASES[736]
        pages, identity, _ = resolve(c['pages'], c['url'])
        self.assertNotEqual(identity['identity_status'], 'verified')
        self.assertNotEqual(identity['name'], 'MICROINGRANAGGI SRL')
        self.assertFalse(identity.get('legal_id'))
        self.assertFalse(identity.get('contacts'))
        self.assertTrue(profile(pages[0])['multi_subject'])
        self.assertFalse(evaluate(identity, pages, {'eligible': True})['audit_allowed'])

    def test_portal_discovery_and_home_stop_before_audit(self):
        for page in CASES[736]['pages'][:2]:
            parsed = parse_page(page)
            self.assertIn(source_role(page['url'], parsed['title'], parsed['text']),
                          ('directory', 'multi_company_catalog'))

    def test_health_authority_is_not_food_manufacturer(self):
        for page in CASES[678]['pages'][:2]:
            parsed = parse_page(page)
            self.assertEqual(source_role(page['url'], parsed['title'], parsed['text']), 'institution')

    def test_evidence_replay_requires_neither_database_nor_network(self):
        with patch('sqlite3.connect', side_effect=AssertionError('Production DB forbidden')), \
             patch('socket.create_connection', side_effect=AssertionError('Offline')):
            for c in CASES.values():
                resolve(c['pages'], c['url'])


class ScopeControls(unittest.TestCase):
    def page(self, text, title='Alfa Srl'):
        return {'url': 'https://alfa.example/', 'status': 200, 'checked_at': '2026-10-20T00:00:00Z',
                'html': '<title>' + title + '</title>' + text}

    def test_supplier_mentioning_directory_or_health_customer_remains_company(self):
        for text in ('<p>Produciamo macchine. Il portale delle imprese parla di noi.</p>',
                     '<p>Cliente: Azienda Unità Sanitaria Locale. Forniamo mobili su misura.</p>',
                     '<p>Progettiamo il portale delle piccole imprese per i nostri clienti.</p>'):
            p = self.page(text)
            self.assertFalse(profile(p)['multi_subject'])
            self.assertEqual(source_role(p['url'], 'Alfa Srl', parse_page(p)['text']), 'company_candidate')

    def test_region_is_not_guessed_from_requested_region_or_markets(self):
        p = self.page('<footer>Alfa Srl<br>P. IVA 12345678901<br>info@alfa.example<br>Serviamo clienti in Veneto</footer>')
        _, identity, _ = resolve([p], p['url'])
        self.assertIsNone(identity['region'])

    def test_conflicting_owner_addresses_stay_unresolved(self):
        p = self.page('<footer>Alfa Srl<br>P. IVA 12345678901<br>info@alfa.example<br>'
                      'Sede operativa: Via Roma 1, 35100 Padova (PD)<br>'
                      'Sede operativa: Via Milano 2, 20100 Milano (MI)</footer>')
        _, identity, _ = resolve([p], p['url'])
        self.assertIsNone(identity['region'])


class PipelineReplay(unittest.TestCase):
    def setUp(self):
        import test_agent6_campaign32 as support
        self.base = support.Campaign32Fix()
        self.base.setUp()
        self.addCleanup(self.base.tearDown)

    def test_saved_sources_stop_after_first_read_without_browser_or_ai(self):
        b = self.base
        for rid in (736, 678):
            case = CASES[rid]
            pages = {p['url']: p for p in case['pages']}
            b.rs.enqueue(b.c['id'], 'candidate', 'AZIENDE',
                         {'url': case['url'], 'query': 'offline fixture', 'proactive': True}, 'case40:' + str(rid))
            with patch('sales.agent6.proactive.CompanyWeb.get', side_effect=lambda u: pages[u]) as reads, \
                 patch('sales.commercial.browser.review', side_effect=AssertionError('Wrong audit subject')), \
                 patch.object(b.w, 'model', side_effect=AssertionError('Wrong AI subject')):
                task = b.rs.claim(b.c['id'], b.c['generation'])
                b.w.execute(task, lambda: None)
                b.rs.task_done(task['id'])
            self.assertEqual(reads.call_count, 1)
        with b.store.connect() as connection:
            rows = [json.loads(r[0]) for r in connection.execute('select body from agent6_records')]
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertFalse(row['identity_verified'])
                self.assertFalse(row['commercial_fit']['audit_allowed'])
                self.assertNotIn(row['state'], ('VERIFIED', 'POTENTIAL'))


if __name__ == '__main__':
    unittest.main()
