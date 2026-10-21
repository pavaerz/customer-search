"""Offline reading-order regressions; metadata never qualifies a company."""
import json
import unittest
from pathlib import Path

from sales.agent6.discovery_intent import source_issue, source_priority
import test_objective_campaign45 as capacity

SAVED = json.loads((Path(__file__).parent / 'fixtures/ai_first/discovery52/receipts.json').read_text())
PROPOSAL = {'strategy': 'external_technical_partner'}


class ReadingOrder(unittest.TestCase):
    def item(self, host):
        return next(r['body'] for r in SAVED if r['campaign_id'] == 51 and host in r['body']['url'])

    def test_saved_invitation_precedes_large_employer_board_and_cv_collection(self):
        invite = self.item('internetimage.it')
        board = self.item('maggioli.com')
        cvs = self.item('ucv.')
        self.assertEqual(source_priority(invite, 'AGENCIES', PROPOSAL)['value'], 2)
        for item in (board, cvs):
            self.assertGreater(source_priority(invite, 'AGENCIES', PROPOSAL)['value'],
                               source_priority(item, 'AGENCIES', PROPOSAL)['value'])
            self.assertIsNone(source_issue(item, PROPOSAL))
            self.assertEqual(source_priority(item, 'AGENCIES', PROPOSAL)['effect'],
                             'reading_order_only_no_company_rejection')

    def test_external_technical_invitation_has_priority_without_declaring_demand(self):
        item = {'url': 'https://agency.example/jobs', 'title': 'Cerchiamo sviluppatori freelance'}
        self.assertEqual(source_priority(item, 'AGENCIES', PROPOSAL), {
            'value': 3, 'basis': 'external_technical_invitation_read_first_not_proven_demand'})

    def test_collection_fragments_cannot_be_combined_into_a_request(self):
        invite = source_priority(self.item('internetimage.it'), 'AGENCIES', PROPOSAL)['value']
        for host in ('postivacanti.it', 'guru.jobs'):
            item = self.item(host)
            self.assertGreater(invite, source_priority(item, 'AGENCIES', PROPOSAL)['value'])
            self.assertIsNone(source_issue(item, PROPOSAL))

    def test_no_legal_form_inference_from_wellness_or_portfolio_client(self):
        for title in ('Web agency: candidatura spontanea; cliente Maggioli SPA',
                      'Lavora con noi: spa e benessere',
                      'Cerchiamo freelance: progetto per cliente Alfa S.p.A.'):
            self.assertGreaterEqual(source_priority({'url': 'https://agency.example/', 'title': title},
                                                    'AGENCIES', PROPOSAL)['value'], 0)

    def test_careers_php_is_a_readable_candidate_and_unknown_is_not_rejected(self):
        item = {'url': 'https://agency.example/lavora-con-noi.php', 'title': ''}
        self.assertEqual(source_priority(item, 'AGENCIES', PROPOSAL)['value'], 1)
        self.assertIsNone(source_issue(item, PROPOSAL))
        item['url'] = 'https://unknown.example/'
        self.assertEqual(source_priority(item, 'AGENCIES', PROPOSAL)['value'], 0)

    def test_proactive_and_bounded_originals_do_not_use_discovery_priority(self):
        for proposal in ({'selection': 'verification'}, {'strategy': 'official_company_sector_region'}):
            self.assertEqual(source_priority(self.item('maggioli.com'), 'AZIENDE', proposal)['value'], 0)

    def test_institutional_news_is_deprioritized_but_not_banned(self):
        item = {'url': 'https://association.example/news/ccrl', 'title': 'Nuovo contratto collettivo CCRL'}
        self.assertEqual(source_priority(item, 'NEWS', PROPOSAL)['value'], -1)
        self.assertIsNone(source_issue(item, PROPOSAL))
        item['title'] = 'Alfa Srl apre uno showroom'
        self.assertEqual(source_priority(item, 'NEWS', PROPOSAL)['value'], 0)

    def test_scheduler_applies_order_without_displacing_saved_original(self):
        base = capacity.FirstCycleReplay(); base.setUp(); self.addCleanup(base.tearDown)
        for host in ('maggioli.com', 'internetimage.it'):
            item = self.item(host)
            task = base.add('candidate', 'AGENCIES', {'url': item['url'],
                'discovery_priority': source_priority(item, 'AGENCIES', PROPOSAL)}, host)
        self.assertEqual(base.choose()[0], task)
        saved = base.add('candidate', 'AGENCIES', {'url': 'https://saved.example/',
            'original_page': {'url': 'https://saved.example/'}, 'discovery_priority': {'value': -2}}, 'saved')
        self.assertEqual(base.choose()[0], saved)

    def test_planner_receives_complete_project_scope_in_all_flows(self):
        from sales.agent6.strategies import brief
        for flow in ('AZIENDE', 'AGENCIES', 'SOCIAL', 'STARTUPS', 'NEWS'):
            scope = brief(flow, ['Veneto'], 0)['professional_profile']
            self.assertIn('Unknown scope/budget stays unknown', scope)
            self.assertIn('ongoing external collaborations allowed', scope)
